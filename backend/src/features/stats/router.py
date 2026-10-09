"""Dashboard backoffice : indicateurs calculés sur les vraies commandes, clients et produits.

Les bornes « aujourd'hui » et « ce mois-ci » suivent le fuseau de la boutique (APP_TIMEZONE).
"""

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from src.domain.user import Role
from src.features.order.events import OPEN_ORDER_STATUSES
from src.features.stats.schemas import (
    ActivityItem,
    BestSeller,
    CustomersKpi,
    DashboardOut,
    MonthlyRevenue,
    OrdersKpi,
    ProductsKpi,
    RecentOrder,
    RevenueKpi,
)
from src.infrastructure.config import Settings, get_settings
from src.infrastructure.persistence.database import get_db
from src.infrastructure.persistence.models import (
    OrderItemModel,
    OrderModel,
    ProductModel,
    UserModel,
)
from src.infrastructure.security.deps import require_roles

router = APIRouter(
    prefix="/stats",
    tags=["stats"],
    dependencies=[Depends(require_roles(Role.COMMERCIAL))],  # ADMIN toujours autorisé
)

# Commandes comptées comme des ventes (ni en attente, ni annulées).
SOLD_STATUSES = ("confirmed", "processing", "shipped", "completed")
LOW_STOCK_THRESHOLD = 5  # même seuil que l'étiquette « Stock faible » des produits
MONTHS = 6
RECENT_ORDERS = 6
BEST_SELLERS = 5
ACTIVITY_ITEMS = 8


def _utc(value: datetime) -> datetime:
    # SQLite renvoie des dates naïves (PostgreSQL des dates avec fuseau) : tout en UTC.
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _local_midnight(day: date, timezone: ZoneInfo) -> datetime:
    return datetime.combine(day, time.min, tzinfo=timezone).astimezone(UTC)


def _shift_month(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def _paid() -> list:
    return [OrderModel.payment_status == "completed", OrderModel.status != "cancelled"]


def _revenue_between(db: Session, start: datetime, end: datetime | None = None) -> int:
    query = select(func.coalesce(func.sum(OrderModel.total_amount), 0)).where(
        *_paid(), OrderModel.paid_at >= start
    )
    if end is not None:
        query = query.where(OrderModel.paid_at < end)
    return int(db.scalar(query) or 0)


def _activity_kind(order: OrderModel) -> str:
    if order.status == "confirmed" and order.payment_status == "completed":
        return "paid"
    return "new" if order.status == "pending" else order.status


def _product_image(product: ProductModel | None) -> str | None:
    if product is None:
        return None
    return (
        f"/api/v1/products/images/{product.image_key}" if product.image_key else product.image_url
    )


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> DashboardOut:
    timezone = ZoneInfo(settings.app_timezone)
    today = datetime.now(timezone).date()
    today_start = _local_midnight(today, timezone)
    month_start = _local_midnight(today.replace(day=1), timezone)
    last_month_start = _local_midnight(_shift_month(today, -1), timezone)
    window_start_day = _shift_month(today, -(MONTHS - 1))
    window_start = _local_midnight(window_start_day, timezone)

    def count(*where: object) -> int:
        return int(db.scalar(select(func.count()).select_from(OrderModel).where(*where)) or 0)

    orders = OrdersKpi(
        total=count(),
        today=count(OrderModel.created_at >= today_start),
        open=count(OrderModel.status.in_(OPEN_ORDER_STATUSES)),
    )
    revenue = RevenueKpi(
        total=int(
            db.scalar(select(func.coalesce(func.sum(OrderModel.total_amount), 0)).where(*_paid()))
            or 0
        ),
        this_month=_revenue_between(db, month_start),
        last_month=_revenue_between(db, last_month_start, month_start),
    )
    customers = CustomersKpi(
        total=int(
            db.scalar(
                select(func.count())
                .select_from(UserModel)
                .where(UserModel.role == Role.CUSTOMER.value)
            )
            or 0
        ),
        new_this_month=int(
            db.scalar(
                select(func.count())
                .select_from(UserModel)
                .where(UserModel.role == Role.CUSTOMER.value, UserModel.created_at >= month_start)
            )
            or 0
        ),
    )
    active_products = (
        select(func.count()).select_from(ProductModel).where(ProductModel.is_active.is_(True))
    )
    products = ProductsKpi(
        active=int(db.scalar(active_products) or 0),
        out_of_stock=int(db.scalar(active_products.where(ProductModel.quantity == 0)) or 0),
        low_stock=int(
            db.scalar(active_products.where(ProductModel.quantity.between(1, LOW_STOCK_THRESHOLD)))
            or 0
        ),
    )

    # ─── Dernières commandes ───
    latest = db.scalars(
        select(OrderModel)
        .options(selectinload(OrderModel.items).selectinload(OrderItemModel.product))
        .order_by(OrderModel.created_at.desc())
        .limit(RECENT_ORDERS)
    ).all()
    recent_orders = [
        RecentOrder(
            id=order.id,
            reference=order.reference,
            customer_name=order.customer_name,
            total_amount=order.total_amount,
            status=order.status,
            payment_status=order.payment_status,
            created_at=order.created_at,
            image_url=next(
                (item.product_image_url or _product_image(item.product) for item in order.items),
                None,
            ),
            item_count=sum(item.quantity for item in order.items),
        )
        for order in latest
    ]

    # ─── Chiffre d'affaires mensuel (6 derniers mois, fuseau de la boutique) ───
    months = [_shift_month(window_start_day, offset).strftime("%Y-%m") for offset in range(MONTHS)]
    by_month = {month: MonthlyRevenue(month=month, revenue=0, orders=0) for month in months}
    for paid_at, amount in db.execute(
        select(OrderModel.paid_at, OrderModel.total_amount).where(
            *_paid(), OrderModel.paid_at >= window_start
        )
    ):
        bucket = by_month.get(_utc(paid_at).astimezone(timezone).strftime("%Y-%m"))
        if bucket:
            bucket.revenue += amount
    for (created_at,) in db.execute(
        select(OrderModel.created_at).where(
            OrderModel.status != "cancelled", OrderModel.created_at >= window_start
        )
    ):
        bucket = by_month.get(_utc(created_at).astimezone(timezone).strftime("%Y-%m"))
        if bucket:
            bucket.orders += 1

    # ─── Meilleures ventes (articles des commandes confirmées et suivantes) ───
    sold = (
        select(
            OrderItemModel.product_id,
            OrderItemModel.product_name,
            func.sum(OrderItemModel.quantity).label("quantity"),
            func.sum(OrderItemModel.line_total).label("revenue"),
        )
        .join(OrderModel, OrderItemModel.order_id == OrderModel.id)
        .where(OrderModel.status.in_(SOLD_STATUSES))
        .group_by(OrderItemModel.product_id, OrderItemModel.product_name)
        .order_by(func.sum(OrderItemModel.quantity).desc())
    )
    rows = db.execute(sold).all()
    total_sold = sum(row.quantity for row in rows) or 1
    top = rows[:BEST_SELLERS]
    product_ids = [row.product_id for row in top if row.product_id]
    catalog = {
        product.id: product
        for product in db.scalars(
            select(ProductModel)
            .options(selectinload(ProductModel.category))
            .where(ProductModel.id.in_(product_ids))
        )
    }
    best_sellers = [
        BestSeller(
            product_id=row.product_id,
            name=row.product_name,
            image_url=_product_image(catalog.get(row.product_id or "")),
            category=(
                product.category.name if (product := catalog.get(row.product_id or "")) else None
            ),
            quantity=int(row.quantity),
            revenue=int(row.revenue),
            share=round(100 * row.quantity / total_sold, 1),
        )
        for row in top
    ]

    # ─── Activité récente ───
    stamp = func.coalesce(OrderModel.updated_at, OrderModel.created_at)
    activity = [
        ActivityItem(
            order_id=order.id,
            reference=order.reference,
            kind=_activity_kind(order),
            customer_name=order.customer_name,
            amount=order.total_amount,
            at=order.updated_at or order.created_at,
        )
        for order in db.scalars(select(OrderModel).order_by(stamp.desc()).limit(ACTIVITY_ITEMS))
    ]

    return DashboardOut(
        orders=orders,
        revenue=revenue,
        customers=customers,
        products=products,
        recent_orders=recent_orders,
        monthly_revenue=list(by_month.values()),
        best_sellers=best_sellers,
        activity=activity,
    )
