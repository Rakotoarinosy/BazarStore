"""Création et consultation des commandes liées à l'utilisateur connecté."""

import logging
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, object_session, selectinload, sessionmaker

from src.domain.errors import DomainError
from src.domain.user import Role, User
from src.features.order.events import count_open_orders_in, order_events
from src.features.order.schemas import (
    MvolaCallbackIn,
    MvolaPaymentIn,
    OpenOrdersCountOut,
    OrderCreateIn,
    OrderOut,
    OrderStatusUpdateIn,
    PaymentConfigOut,
    StripeCheckoutOut,
)
from src.features.order.serialization import serialize_order
from src.infrastructure.config import Settings, get_settings
from src.infrastructure.documents.invoice_pdf import (
    DEFAULT_LOGO,
    InvoiceData,
    InvoiceLine,
    InvoiceSeller,
    render_invoice_pdf,
)
from src.infrastructure.external.mvola_client import MvolaClient, get_mvola_client
from src.infrastructure.external.stripe_payments import (
    CheckoutLine,
    StripePayments,
    get_stripe_payments,
)
from src.infrastructure.persistence.database import get_db, get_session_factory
from src.infrastructure.persistence.models import (
    OrderItemModel,
    OrderModel,
    ProductCategoryModel,
    ProductModel,
)
from src.infrastructure.security.deps import get_current_user, require_roles

router = APIRouter(prefix="/orders", tags=["orders"])
logger = logging.getLogger(__name__)

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    # Désactive la mise en tampon des proxys (nginx) : chaque événement part tout de suite.
    "X-Accel-Buffering": "no",
}
SSE_DOC = {200: {"content": {"text/event-stream": {}}, "description": "Flux Server-Sent Events"}}

# Délai après lequel un paiement resté « pending » (non validé sur le téléphone) peut être relancé.
PAYMENT_RETRY_AFTER = timedelta(minutes=3)


class OrderProductConflictError(DomainError):
    def __init__(self, product_id: str) -> None:
        super().__init__(
            f"Le produit {product_id} n'est plus disponible ou le stock est insuffisant."
        )


class OrderConflictError(DomainError):
    def __init__(self) -> None:
        super().__init__("La commande n'a pas pu être enregistrée. Veuillez réessayer.")


class OrderNotFoundError(DomainError):
    def __init__(self) -> None:
        super().__init__("Commande introuvable.")


class OrderNotPayableConflictError(DomainError):
    def __init__(self) -> None:
        super().__init__("Cette commande est déjà payée ou ne peut plus être payée.")


class OrderCancelledConflictError(DomainError):
    def __init__(self) -> None:
        super().__init__("Une commande annulée ne peut pas être facturée.")


class PaymentsUnavailableError(DomainError):
    def __init__(self) -> None:
        super().__init__("Le paiement en ligne est désactivé pour le moment.")


def require_payments_enabled(settings: Settings = Depends(get_settings)) -> None:
    """Coupe toutes les routes de paiement (aucun appel à Stripe ni à MVola) si désactivées."""
    if not settings.payments_enabled:
        raise PaymentsUnavailableError()


# Dépendance de route : résolue avant celles des paramètres (clients Stripe / MVola).
PAYMENTS_GUARD = [Depends(require_payments_enabled)]


class OrderPaymentPendingConflictError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "Un paiement est déjà en attente de validation sur le téléphone. "
            "Validez-le ou réessayez dans quelques minutes."
        )


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: OrderCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OrderOut:
    requested = {item.product_id: item.quantity for item in payload.items}
    products = db.scalars(
        select(ProductModel)
        .join(ProductCategoryModel)
        .where(
            ProductModel.id.in_(requested),
            ProductModel.is_active.is_(True),
            ProductCategoryModel.is_active.is_(True),
        )
        .order_by(ProductModel.id)
        .with_for_update()
    ).all()
    products_by_id = {product.id: product for product in products}

    for product_id, quantity in requested.items():
        product = products_by_id.get(product_id)
        if product is None or product.quantity < quantity:
            raise OrderProductConflictError(product_id)

    lines = [
        OrderItemModel(
            product_id=product.id,
            product_name=product.name,
            product_image_url=(
                f"/api/v1/products/images/{product.image_key}"
                if product.image_key
                else product.image_url
            ),
            unit_price=product.price,
            quantity=requested[product.id],
            line_total=product.price * requested[product.id],
        )
        for product in products
    ]
    order = OrderModel(
        reference=f"CMD-{secrets.token_hex(5).upper()}",
        user_id=user.id,
        customer_name=user.name,
        customer_email=user.email,
        status="pending",
        total_amount=sum(line.line_total for line in lines),
        items=lines,
    )
    db.add(order)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise OrderConflictError() from exc
    db.refresh(order)
    return OrderOut.model_validate(order)


@router.get("/mine", response_model=list[OrderOut])
def list_my_orders(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[OrderOut]:
    orders = db.scalars(
        select(OrderModel)
        .options(selectinload(OrderModel.items).selectinload(OrderItemModel.product))
        .where(OrderModel.user_id == user.id)
        .order_by(OrderModel.created_at.desc())
    ).all()
    return [serialize_order(order) for order in orders]


def _get_user_order(db: Session, order_id: str, user: User) -> OrderModel:
    order = db.scalars(
        select(OrderModel)
        .options(selectinload(OrderModel.items))
        .where(OrderModel.id == order_id, OrderModel.user_id == user.id)
    ).first()
    if order is None:
        raise OrderNotFoundError()
    return order


def _as_aware(value: datetime) -> datetime:
    # SQLite renvoie des datetimes naïfs : on les considère en UTC.
    return value if value.tzinfo else value.replace(tzinfo=UTC)


@router.get("/mine/stream", response_class=StreamingResponse, responses=SSE_DOC)
async def stream_my_orders(
    request: Request,
    user: User = Depends(get_current_user),
    factory: sessionmaker[Session] = Depends(get_session_factory),
) -> StreamingResponse:
    """Temps réel client : `order` à chaque changement d'une de ses commandes."""
    return StreamingResponse(
        order_events(request.is_disconnected, factory, user_id=user.id),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


# ─── Cycle de vie et stock ──────────────────────────────────────────

# Transitions autorisées depuis le backoffice (livrée et annulée sont des états finaux).
ORDER_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"confirmed", "cancelled"},
    "confirmed": {"processing", "cancelled"},
    "processing": {"shipped", "cancelled"},
    "shipped": {"completed"},
}


class OrderStatusTransitionConflictError(DomainError):
    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"Impossible de passer une commande « {current} » au statut « {target} ».")


class OrderStockConflictError(DomainError):
    def __init__(self, product_name: str) -> None:
        super().__init__(
            f"Stock insuffisant pour « {product_name} » : la commande ne peut pas être confirmée."
        )


def _locked_products(order: OrderModel) -> dict[str, ProductModel]:
    db = object_session(order)
    product_ids = [item.product_id for item in order.items if item.product_id]
    if db is None or not product_ids:
        return {}
    products = db.scalars(
        select(ProductModel)
        .where(ProductModel.id.in_(product_ids))
        .order_by(ProductModel.id)
        .with_for_update()
    ).all()
    return {product.id: product for product in products}


def _deduct_stock(order: OrderModel, *, strict: bool) -> None:
    """Retire les quantités commandées du stock (une seule fois par commande).

    strict=True (confirmation manuelle) refuse si le stock manque ; après un paiement
    déjà encaissé (strict=False), le stock est ramené à zéro et l'écart est journalisé.
    """
    if order.stock_deducted:
        return
    products = _locked_products(order)
    for item in order.items:
        product = products.get(item.product_id or "")
        if product is None:
            continue
        if product.quantity < item.quantity:
            if strict:
                raise OrderStockConflictError(item.product_name)
            logger.warning(
                "Stock insufficient for %s on paid order %s", product.code, order.reference
            )
        product.quantity = max(product.quantity - item.quantity, 0)
    order.stock_deducted = True


def _restore_stock(order: OrderModel) -> None:
    if not order.stock_deducted:
        return
    products = _locked_products(order)
    for item in order.items:
        product = products.get(item.product_id or "")
        if product is not None:
            product.quantity += item.quantity
    order.stock_deducted = False


def _confirm_order(order: OrderModel, *, strict: bool) -> None:
    _deduct_stock(order, strict=strict)
    order.status = "confirmed"


def _refresh_mvola_status(order: OrderModel, mvola: MvolaClient) -> None:
    """Relit le statut chez MVola et l'applique à la commande (sans commit)."""
    if order.payment_status != "pending" or not order.payment_correlation_id:
        return

    result = mvola.get_status(order.payment_correlation_id)
    if result.status == "completed":
        order.payment_status = "completed"
        order.payment_reference = result.transaction_reference
        order.paid_at = datetime.now(UTC)
        _confirm_order(order, strict=False)
    elif result.status == "failed":
        order.payment_status = "failed"


@router.post("/{order_id}/payments/mvola", response_model=OrderOut, dependencies=PAYMENTS_GUARD)
def start_mvola_payment(
    order_id: str,
    payload: MvolaPaymentIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    mvola: MvolaClient = Depends(get_mvola_client),
) -> OrderOut:
    """Envoie une demande de paiement MVola : le client la valide sur son téléphone."""
    order = _get_user_order(db, order_id, user)
    _refresh_mvola_status(order, mvola)
    if order.status != "pending" or order.payment_status == "completed":
        db.commit()
        raise OrderNotPayableConflictError()
    if (
        order.payment_status == "pending"
        and order.payment_requested_at is not None
        and datetime.now(UTC) - _as_aware(order.payment_requested_at) < PAYMENT_RETRY_AFTER
    ):
        raise OrderPaymentPendingConflictError()

    initiation = mvola.initiate_payment(
        amount=order.total_amount,
        customer_msisdn=payload.phone,
        description=f"Paiement commande {order.reference}",
        reference=f"{order.reference}-{secrets.token_hex(2).upper()}",
    )
    order.payment_provider = "mvola"
    order.payment_status = "pending"
    order.payment_phone = payload.phone
    order.payment_correlation_id = initiation.server_correlation_id
    order.payment_reference = None
    order.payment_requested_at = datetime.now(UTC)
    db.commit()
    db.refresh(order)
    return OrderOut.model_validate(order)


@router.get("/{order_id}/payments/mvola", response_model=OrderOut, dependencies=PAYMENTS_GUARD)
def get_mvola_payment_status(
    order_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    mvola: MvolaClient = Depends(get_mvola_client),
) -> OrderOut:
    """Statut du paiement (interrogé régulièrement par le frontend tant qu'il est « pending »)."""
    order = _get_user_order(db, order_id, user)
    _refresh_mvola_status(order, mvola)
    db.commit()
    db.refresh(order)
    return OrderOut.model_validate(order)


@router.put(
    "/payments/mvola/callback",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=PAYMENTS_GUARD,
)
def mvola_callback(
    payload: MvolaCallbackIn,
    db: Session = Depends(get_db),
    mvola: MvolaClient = Depends(get_mvola_client),
) -> Response:
    """Notification envoyée par MVola (X-Callback-URL).

    Le corps n'est pas signé : on ne lui fait pas confiance et on relit le statut chez MVola.
    """
    order = db.scalars(
        select(OrderModel).where(OrderModel.payment_correlation_id == payload.serverCorrelationId)
    ).first()
    if order is None:
        logger.warning("MVola callback for unknown correlation id")
    else:
        _refresh_mvola_status(order, mvola)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Paiement par carte : Stripe Checkout ───────────────────────────


def _mark_stripe_paid(order: OrderModel) -> None:
    order.payment_status = "completed"
    order.paid_at = datetime.now(UTC)
    _confirm_order(order, strict=False)


def _refresh_stripe_status(order: OrderModel, payments: StripePayments) -> None:
    """Relit la session Stripe de la commande et applique son état (sans commit)."""
    if (
        order.payment_provider != "stripe"
        or order.payment_status != "pending"
        or not order.payment_correlation_id
    ):
        return
    state = payments.get_session_state(order.payment_correlation_id)
    if state.order_id != order.id:
        logger.warning("Stripe session does not belong to order %s", order.reference)
        return
    if state.paid:
        _mark_stripe_paid(order)
    elif state.expired:
        order.payment_status = "failed"


@router.get("/payments/config", response_model=PaymentConfigOut)
def get_payment_config(settings: Settings = Depends(get_settings)) -> PaymentConfigOut:
    """Indique au frontend si le paiement par carte est proposé."""
    return PaymentConfigOut(
        card_enabled=settings.payments_enabled and bool(settings.stripe_secret_key)
    )


@router.post(
    "/{order_id}/payments/stripe", response_model=StripeCheckoutOut, dependencies=PAYMENTS_GUARD
)
def start_stripe_payment(
    order_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    payments: StripePayments = Depends(get_stripe_payments),
    settings: Settings = Depends(get_settings),
) -> StripeCheckoutOut:
    """Crée une session Stripe Checkout ; le frontend redirige le client vers `checkout_url`."""
    order = _get_user_order(db, order_id, user)
    _refresh_stripe_status(order, payments)
    if order.status != "pending" or order.payment_status == "completed":
        db.commit()
        raise OrderNotPayableConflictError()

    return_url = f"{settings.public_frontend_url.rstrip('/')}/my-orders?order={order.id}"
    checkout = payments.create_checkout(
        order_id=order.id,
        reference=order.reference,
        customer_email=order.customer_email,
        lines=[
            CheckoutLine(
                name=item.product_name, unit_price_ar=item.unit_price, quantity=item.quantity
            )
            for item in order.items
        ],
        success_url=f"{return_url}&payment=success",
        cancel_url=f"{return_url}&payment=cancelled",
    )
    order.payment_provider = "stripe"
    order.payment_status = "pending"
    order.payment_phone = None
    order.payment_correlation_id = checkout.session_id
    order.payment_reference = None
    order.payment_requested_at = datetime.now(UTC)
    db.commit()
    db.refresh(order)
    return StripeCheckoutOut(checkout_url=checkout.url, order=OrderOut.model_validate(order))


@router.get("/{order_id}/payments/stripe", response_model=OrderOut, dependencies=PAYMENTS_GUARD)
def get_stripe_payment_status(
    order_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    payments: StripePayments = Depends(get_stripe_payments),
) -> OrderOut:
    """Statut du paiement par carte (interrogé au retour de Stripe)."""
    order = _get_user_order(db, order_id, user)
    _refresh_stripe_status(order, payments)
    db.commit()
    db.refresh(order)
    return OrderOut.model_validate(order)


@router.post(
    "/payments/stripe/webhook",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=PAYMENTS_GUARD,
)
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db),
    payments: StripePayments = Depends(get_stripe_payments),
) -> Response:
    """Notification signée de Stripe (`checkout.session.completed`)."""
    result = payments.parse_webhook(await request.body(), request.headers.get("stripe-signature"))
    if result is not None:
        session_id, state = result
        order = db.get(OrderModel, state.order_id) if state.order_id else None
        if order is None or order.payment_correlation_id != session_id:
            logger.warning("Stripe webhook for an unknown order/session")
        elif state.paid and order.payment_status != "completed":
            _mark_stripe_paid(order)
            db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Backoffice ─────────────────────────────────────────────────────

ORDER_STAFF = [Depends(require_roles(Role.COMMERCIAL))]  # ADMIN toujours autorisé


@router.get("/manage", response_model=list[OrderOut], dependencies=ORDER_STAFF)
def list_orders_for_staff(db: Session = Depends(get_db)) -> list[OrderOut]:
    """Toutes les commandes, les plus récentes d'abord (filtres et recherche côté backoffice)."""
    orders = db.scalars(
        select(OrderModel)
        .options(selectinload(OrderModel.items).selectinload(OrderItemModel.product))
        .order_by(OrderModel.created_at.desc())
    ).all()
    return [OrderOut.model_validate(order) for order in orders]


@router.get("/manage/open-count", response_model=OpenOrdersCountOut, dependencies=ORDER_STAFF)
def count_open_orders(db: Session = Depends(get_db)) -> OpenOrdersCountOut:
    """Nombre de commandes ni livrées ni annulées (badge du menu backoffice)."""
    return OpenOrdersCountOut(count=count_open_orders_in(db))


@router.get(
    "/manage/stream",
    response_class=StreamingResponse,
    responses=SSE_DOC,
    dependencies=ORDER_STAFF,
)
async def stream_orders_for_staff(
    request: Request,
    factory: sessionmaker[Session] = Depends(get_session_factory),
) -> StreamingResponse:
    """Temps réel backoffice : `open-count` (badge) et `order` (commande créée ou modifiée)."""
    return StreamingResponse(
        order_events(request.is_disconnected, factory, include_open_count=True),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.patch("/{order_id}/status", response_model=OrderOut, dependencies=ORDER_STAFF)
def update_order_status(
    order_id: str,
    payload: OrderStatusUpdateIn,
    db: Session = Depends(get_db),
) -> OrderOut:
    """Fait avancer une commande dans son cycle (confirmée → en préparation → expédiée → livrée)."""
    order = db.scalars(
        select(OrderModel)
        .options(selectinload(OrderModel.items))
        .where(OrderModel.id == order_id)
        .with_for_update()
    ).first()
    if order is None:
        raise OrderNotFoundError()
    if payload.status not in ORDER_TRANSITIONS.get(order.status, set()):
        raise OrderStatusTransitionConflictError(order.status, payload.status)

    if payload.status == "confirmed":
        _confirm_order(order, strict=True)
    elif payload.status == "cancelled":
        _restore_stock(order)
        order.status = "cancelled"
    else:
        order.status = payload.status
    db.commit()
    db.refresh(order)
    return OrderOut.model_validate(order)


# ─── Factures ───────────────────────────────────────────────────────

INVOICE_STAFF_ROLES = {Role.ADMIN, Role.COMMERCIAL, Role.MANAGER}
PAYMENT_METHOD_LABELS = {"stripe": "carte bancaire", "mvola": "MVola"}


def _assign_invoice_number(
    db: Session, order: OrderModel, now: datetime, timezone: ZoneInfo
) -> None:
    """Numéro séquentiel par année (FAC-2026-00001), attribué une seule fois et jamais réutilisé."""
    prefix = f"FAC-{now.astimezone(timezone).year}-"
    for _ in range(3):
        last = db.scalar(
            select(OrderModel.invoice_number)
            .where(OrderModel.invoice_number.like(f"{prefix}%"))
            .order_by(OrderModel.invoice_number.desc())
            .limit(1)
        )
        sequence = int(last.removeprefix(prefix)) + 1 if last else 1
        order.invoice_number = f"{prefix}{sequence:05d}"
        order.invoice_issued_at = now
        try:
            db.commit()
            return
        except IntegrityError:
            # Deux factures émises en même temps : on recalcule le numéro suivant.
            db.rollback()
            db.refresh(order)
            if order.invoice_number:
                return
    raise OrderConflictError()


@router.get(
    "/{order_id}/invoice",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "Facture PDF"}},
)
def download_invoice(
    order_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Facture PDF de la commande (le client pour ses commandes, l'équipe pour toutes)."""
    query = (
        select(OrderModel)
        .options(selectinload(OrderModel.items).selectinload(OrderItemModel.product))
        .where(OrderModel.id == order_id)
    )
    if user.role not in INVOICE_STAFF_ROLES:
        query = query.where(OrderModel.user_id == user.id)
    order = db.scalars(query).first()
    if order is None:
        raise OrderNotFoundError()
    if order.status == "cancelled":
        raise OrderCancelledConflictError()

    timezone = ZoneInfo(settings.app_timezone)
    if not order.invoice_number:
        _assign_invoice_number(db, order, datetime.now(UTC), timezone)

    issued_at = _as_aware(order.invoice_issued_at or datetime.now(UTC))
    is_paid = order.payment_status == "completed"
    invoice = InvoiceData(
        number=order.invoice_number or "",
        issued_at=issued_at.astimezone(timezone),
        order_reference=order.reference,
        order_date=_as_aware(order.created_at).astimezone(timezone),
        customer_name=order.customer_name,
        customer_email=order.customer_email,
        seller=InvoiceSeller(
            name=settings.invoice_seller_name,
            address=settings.invoice_seller_address,
            city=settings.invoice_seller_city,
            phone=settings.invoice_seller_phone,
            email=settings.invoice_seller_email,
            nif=settings.invoice_seller_nif,
            stat=settings.invoice_seller_stat,
            rcs=settings.invoice_seller_rcs,
            logo_path=Path(settings.invoice_logo_path)
            if settings.invoice_logo_path
            else DEFAULT_LOGO,
        ),
        lines=[
            InvoiceLine(
                designation=item.product_name,
                reference=item.product.code if item.product is not None else "—",
                quantity=item.quantity,
                unit_price=item.unit_price,
                total=item.line_total,
            )
            for item in order.items
        ],
        total_ttc=order.total_amount,
        vat_rate=settings.invoice_vat_rate,
        is_paid=is_paid,
        paid_at=_as_aware(order.paid_at).astimezone(timezone)
        if is_paid and order.paid_at
        else None,
        payment_method=PAYMENT_METHOD_LABELS.get(order.payment_provider or ""),
        payment_terms=settings.invoice_payment_terms,
    )
    filename = f"facture-{order.invoice_number}.pdf"
    return Response(
        content=render_invoice_pdf(invoice),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
        },
    )
