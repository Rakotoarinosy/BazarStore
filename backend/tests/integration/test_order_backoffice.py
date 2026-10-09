import pytest
from sqlalchemy.orm import Session

from src.features.order.router import (
    OrderStatusTransitionConflictError,
    OrderStockConflictError,
    _mark_stripe_paid,
    list_orders_for_staff,
    update_order_status,
)
from src.features.order.schemas import OrderStatusUpdateIn
from src.infrastructure.persistence.models import (
    OrderItemModel,
    OrderModel,
    ProductCategoryModel,
    ProductModel,
)


@pytest.fixture
def order(db_session: Session) -> OrderModel:
    category = ProductCategoryModel(id="cat-1", name="High-tech", slug="high-tech")
    product = ProductModel(
        id="p-1",
        code="BAZ-TECH-001",
        name="Casque audio",
        price=700_000,
        quantity=5,
        category=category,
    )
    order = OrderModel(
        id="o-1",
        reference="CMD-BO1",
        customer_name="Rakoto",
        customer_email="rakoto@example.com",
        status="pending",
        total_amount=1_400_000,
        items=[
            OrderItemModel(
                product=product,
                product_name="Casque audio",
                unit_price=700_000,
                quantity=2,
                line_total=1_400_000,
            )
        ],
    )
    db_session.add_all([category, product, order])
    db_session.commit()
    return order


def _set(db: Session, status: str) -> str:
    return update_order_status("o-1", OrderStatusUpdateIn(status=status), db).status  # type: ignore[arg-type]


def test_full_lifecycle_deducts_stock_once(db_session: Session, order: OrderModel) -> None:
    assert _set(db_session, "confirmed") == "confirmed"
    assert db_session.get(ProductModel, "p-1").quantity == 3
    assert _set(db_session, "processing") == "processing"
    assert _set(db_session, "shipped") == "shipped"
    assert _set(db_session, "completed") == "completed"
    assert db_session.get(ProductModel, "p-1").quantity == 3

    with pytest.raises(OrderStatusTransitionConflictError):
        _set(db_session, "cancelled")


def test_cancellation_restores_stock(db_session: Session, order: OrderModel) -> None:
    _set(db_session, "confirmed")
    _set(db_session, "processing")
    assert _set(db_session, "cancelled") == "cancelled"
    assert db_session.get(ProductModel, "p-1").quantity == 5
    assert db_session.get(OrderModel, "o-1").stock_deducted is False

    with pytest.raises(OrderStatusTransitionConflictError):
        _set(db_session, "confirmed")


def test_cannot_skip_steps(db_session: Session, order: OrderModel) -> None:
    with pytest.raises(OrderStatusTransitionConflictError):
        _set(db_session, "shipped")


def test_manual_confirmation_refuses_missing_stock(db_session: Session, order: OrderModel) -> None:
    db_session.get(ProductModel, "p-1").quantity = 1
    db_session.commit()

    with pytest.raises(OrderStockConflictError):
        _set(db_session, "confirmed")
    db_session.rollback()
    assert db_session.get(OrderModel, "o-1").status == "pending"


def test_paid_order_deducts_stock_even_when_short(db_session: Session, order: OrderModel) -> None:
    db_session.get(ProductModel, "p-1").quantity = 1
    _mark_stripe_paid(order)
    db_session.commit()

    assert order.status == "confirmed"
    assert db_session.get(ProductModel, "p-1").quantity == 0
    assert [o.reference for o in list_orders_for_staff(db_session)] == ["CMD-BO1"]
