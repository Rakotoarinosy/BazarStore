from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from src.features.stats.router import _shift_month, dashboard
from src.infrastructure.config.settings import Settings
from src.infrastructure.persistence.models import (
    OrderItemModel,
    OrderModel,
    ProductCategoryModel,
    ProductModel,
    UserModel,
)

SETTINGS = Settings(app_timezone="Indian/Antananarivo")
NOW = datetime.now(UTC)
LAST_MONTH = datetime.combine(
    _shift_month(NOW.date(), -1), datetime.min.time(), tzinfo=UTC
) + timedelta(days=10)


def _order(
    order_id: str,
    product: ProductModel,
    quantity: int,
    *,
    status: str = "pending",
    paid_at: datetime | None = None,
    created_at: datetime = NOW,
) -> OrderModel:
    return OrderModel(
        id=order_id,
        reference=f"CMD-{order_id.upper()}",
        customer_name=f"Client {order_id}",
        customer_email="client@example.com",
        status=status,
        payment_status="completed" if paid_at else None,
        payment_provider="stripe" if paid_at else None,
        paid_at=paid_at,
        created_at=created_at,
        updated_at=created_at,
        total_amount=product.price * quantity,
        items=[
            OrderItemModel(
                product=product,
                product_name=product.name,
                unit_price=product.price,
                quantity=quantity,
                line_total=product.price * quantity,
            )
        ],
    )


@pytest.fixture
def shop(db_session: Session) -> None:
    category = ProductCategoryModel(id="cat", name="High-tech", slug="high-tech")
    casque = ProductModel(
        id="casque", code="TECH-1", name="Casque", price=100_000, quantity=8, category=category
    )
    montre = ProductModel(
        id="montre", code="TECH-2", name="Montre", price=50_000, quantity=3, category=category
    )
    epuise = ProductModel(
        id="epuise", code="TECH-3", name="Épuisé", price=10_000, quantity=0, category=category
    )
    db_session.add_all(
        [
            category,
            casque,
            montre,
            epuise,
            UserModel(id="c1", email="c1@example.com", name="C1"),  # rôle client par défaut
            UserModel(id="c2", email="c2@example.com", name="C2", created_at=LAST_MONTH),
            UserModel(id="admin", email="a@example.com", name="Admin", role="admin"),
            # Payée ce mois-ci : 2 casques.
            _order("paid", casque, 2, status="confirmed", paid_at=NOW),
            # Payée le mois dernier puis livrée : 3 montres.
            _order("old", montre, 3, status="completed", paid_at=LAST_MONTH, created_at=LAST_MONTH),
            # En attente, non payée : ne compte ni dans le CA ni dans les ventes.
            _order("wait", casque, 1),
            # Payée puis annulée : exclue du CA et des ventes.
            _order("cancel", montre, 1, status="cancelled", paid_at=NOW),
        ]
    )
    db_session.commit()


def test_dashboard_kpis(db_session: Session, shop: None) -> None:
    stats = dashboard(db_session, SETTINGS)

    assert (stats.orders.total, stats.orders.open) == (4, 2)
    assert stats.revenue.total == 200_000 + 150_000
    assert stats.revenue.this_month == 200_000
    assert stats.revenue.last_month == 150_000
    assert (stats.customers.total, stats.customers.new_this_month) == (2, 1)
    assert (stats.products.active, stats.products.out_of_stock, stats.products.low_stock) == (
        3,
        1,
        1,
    )


def test_dashboard_monthly_revenue_and_best_sellers(db_session: Session, shop: None) -> None:
    stats = dashboard(db_session, SETTINGS)

    assert len(stats.monthly_revenue) == 6
    current, previous = stats.monthly_revenue[-1], stats.monthly_revenue[-2]
    assert (current.revenue, current.orders) == (
        200_000,
        2,
    )  # « wait » compte comme commande, pas comme CA
    assert (previous.revenue, previous.orders) == (150_000, 1)

    assert [(seller.name, seller.quantity) for seller in stats.best_sellers] == [
        ("Montre", 3),
        ("Casque", 2),
    ]
    assert stats.best_sellers[0].share == 60.0
    assert stats.best_sellers[0].category == "High-tech"


def test_dashboard_recent_orders_and_activity(db_session: Session, shop: None) -> None:
    stats = dashboard(db_session, SETTINGS)

    assert stats.recent_orders[-1].reference == "CMD-OLD"
    assert {item.kind for item in stats.activity} == {"paid", "completed", "new", "cancelled"}


def test_dashboard_benchmark_compares_this_month_with_last_month(
    db_session: Session, shop: None
) -> None:
    axes = {axis.key: axis for axis in dashboard(db_session, SETTINGS).benchmark}

    assert [key for key in axes] == [
        "orders",
        "revenue",
        "basket",
        "items",
        "customers",
        "delivery",
    ]
    assert (axes["orders"].current, axes["orders"].previous) == (
        2,
        1,
    )  # « paid » + « wait » / « old »
    assert (axes["revenue"].current, axes["revenue"].previous) == (200_000, 150_000)
    assert (axes["basket"].current, axes["basket"].previous) == (200_000, 150_000)
    assert (axes["items"].current, axes["items"].previous) == (2, 3)
    assert (axes["customers"].current, axes["customers"].previous) == (1, 1)
    assert (axes["delivery"].current, axes["delivery"].previous) == (0, 100.0)
    assert axes["delivery"].unit == "percent"
