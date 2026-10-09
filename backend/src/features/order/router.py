"""Création et consultation des commandes liées à l'utilisateur connecté."""

import logging
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from src.domain.errors import DomainError
from src.domain.user import Role, User
from src.features.order.schemas import (
    CardCheckoutOut,
    MvolaCallbackIn,
    MvolaPaymentIn,
    OrderCreateIn,
    OrderOut,
)
from src.infrastructure.config import Settings, get_settings
from src.infrastructure.documents.invoice_pdf import (
    DEFAULT_LOGO,
    InvoiceData,
    InvoiceLine,
    InvoiceSeller,
    render_invoice_pdf,
)
from src.infrastructure.external.card_payment_gateway import (
    CardPaymentGateway,
    get_card_payment_gateway,
)
from src.infrastructure.external.mvola_client import MvolaClient, get_mvola_client
from src.infrastructure.persistence.database import get_db
from src.infrastructure.persistence.models import (
    OrderItemModel,
    OrderModel,
    ProductCategoryModel,
    ProductModel,
)
from src.infrastructure.security.deps import get_current_user

router = APIRouter(prefix="/orders", tags=["orders"])
logger = logging.getLogger(__name__)

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
    order_outputs = [OrderOut.model_validate(order) for order in orders]
    for order_model, order_output in zip(orders, order_outputs, strict=True):
        products_by_id = {
            item.product_id: item.product
            for item in order_model.items
            if item.product_id is not None and item.product is not None
        }
        for item_output in order_output.items:
            product = products_by_id.get(item_output.product_id)
            if item_output.product_image_url is None and product is not None:
                item_output.product_image_url = (
                    f"/api/v1/products/images/{product.image_key}"
                    if product.image_key
                    else product.image_url
                )
    return order_outputs


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


def _refresh_mvola_status(order: OrderModel, mvola: MvolaClient) -> None:
    """Relit le statut chez MVola et l'applique à la commande (sans commit)."""
    if order.payment_status != "pending" or not order.payment_correlation_id:
        return

    result = mvola.get_status(order.payment_correlation_id)
    if result.status == "completed":
        order.payment_status = "completed"
        order.payment_reference = result.transaction_reference
        order.paid_at = datetime.now(UTC)
        order.status = "confirmed"
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


def _refresh_card_status(order: OrderModel, gateway: CardPaymentGateway) -> None:
    """Confirme la commande si l'API Stripe externe a enregistré son paiement (sans commit)."""
    if order.payment_provider != "card" or order.payment_status != "pending":
        return
    if gateway.is_paid(reference=order.reference, amount_ar=order.total_amount):
        order.payment_status = "completed"
        order.paid_at = datetime.now(UTC)
        order.status = "confirmed"


@router.post(
    "/{order_id}/payments/card", response_model=CardCheckoutOut, dependencies=PAYMENTS_GUARD
)
def start_card_payment(
    order_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    gateway: CardPaymentGateway = Depends(get_card_payment_gateway),
) -> CardCheckoutOut:
    """Crée une session Stripe Checkout ; le frontend redirige le client vers `checkout_url`."""
    order = _get_user_order(db, order_id, user)
    _refresh_card_status(order, gateway)
    if order.status != "pending" or order.payment_status == "completed":
        db.commit()
        raise OrderNotPayableConflictError()

    checkout = gateway.create_checkout(reference=order.reference, amount_ar=order.total_amount)
    order.payment_provider = "card"
    order.payment_status = "pending"
    order.payment_phone = None
    order.payment_correlation_id = checkout.session_id
    order.payment_reference = None
    order.payment_requested_at = datetime.now(UTC)
    db.commit()
    db.refresh(order)
    return CardCheckoutOut(checkout_url=checkout.checkout_url, order=OrderOut.model_validate(order))


@router.get("/{order_id}/payments/card", response_model=OrderOut, dependencies=PAYMENTS_GUARD)
def get_card_payment_status(
    order_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    gateway: CardPaymentGateway = Depends(get_card_payment_gateway),
) -> OrderOut:
    """Statut du paiement par carte (interrogé au retour de Stripe)."""
    order = _get_user_order(db, order_id, user)
    _refresh_card_status(order, gateway)
    db.commit()
    db.refresh(order)
    return OrderOut.model_validate(order)


# ─── Factures ───────────────────────────────────────────────────────

INVOICE_STAFF_ROLES = {Role.ADMIN, Role.COMMERCIAL, Role.MANAGER}
PAYMENT_METHOD_LABELS = {"card": "carte bancaire", "mvola": "MVola"}


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
