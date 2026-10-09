from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from src.domain.user import User
from src.features.order.router import (
    OrderNotPayableConflictError,
    OrderPaymentPendingConflictError,
    get_mvola_payment_status,
    start_mvola_payment,
)
from src.features.order.schemas import MvolaPaymentIn
from src.infrastructure.external.mvola_client import MvolaInitiation, MvolaStatus
from src.infrastructure.persistence.models import OrderModel, UserModel


class FakeMvola:
    def __init__(self) -> None:
        self.status = "pending"
        self.initiated: list[dict[str, object]] = []

    def initiate_payment(self, **kwargs: object) -> MvolaInitiation:
        self.initiated.append(kwargs)
        return MvolaInitiation(
            server_correlation_id=f"corr-{len(self.initiated)}", status="pending"
        )

    def get_status(self, server_correlation_id: str) -> MvolaStatus:
        reference = "TX-123" if self.status == "completed" else None
        return MvolaStatus(status=self.status, transaction_reference=reference)


@pytest.fixture
def customer(db_session: Session) -> User:
    db_session.add(UserModel(id="customer-1", email="customer@example.com", name="Customer"))
    db_session.add(
        OrderModel(
            id="order-1",
            reference="CMD-TEST1",
            user_id="customer-1",
            customer_name="Customer",
            customer_email="customer@example.com",
            status="pending",
            total_amount=15000,
        )
    )
    db_session.commit()
    return User(
        id="customer-1",
        email="customer@example.com",
        name="Customer",
        created_at=datetime.now(UTC),
        password_hash="",
    )


def test_mvola_payment_completes_order(db_session: Session, customer: User) -> None:
    mvola = FakeMvola()

    started = start_mvola_payment(
        "order-1", MvolaPaymentIn(phone="+261 34 35 000 03"), db_session, customer, mvola
    )  # type: ignore[arg-type]
    assert started.payment_status == "pending"
    assert started.payment_phone == "0343500003"
    assert mvola.initiated[0]["amount"] == 15000
    assert mvola.initiated[0]["customer_msisdn"] == "0343500003"

    with pytest.raises(OrderPaymentPendingConflictError):
        start_mvola_payment(
            "order-1", MvolaPaymentIn(phone="0343500003"), db_session, customer, mvola
        )  # type: ignore[arg-type]

    mvola.status = "completed"
    paid = get_mvola_payment_status("order-1", db_session, customer, mvola)  # type: ignore[arg-type]
    assert paid.status == "confirmed"
    assert paid.payment_status == "completed"
    assert paid.payment_reference == "TX-123"
    assert paid.paid_at is not None

    with pytest.raises(OrderNotPayableConflictError):
        start_mvola_payment(
            "order-1", MvolaPaymentIn(phone="0343500003"), db_session, customer, mvola
        )  # type: ignore[arg-type]


def test_failed_mvola_payment_can_be_retried(db_session: Session, customer: User) -> None:
    mvola = FakeMvola()
    start_mvola_payment("order-1", MvolaPaymentIn(phone="0343500003"), db_session, customer, mvola)  # type: ignore[arg-type]

    mvola.status = "failed"
    failed = get_mvola_payment_status("order-1", db_session, customer, mvola)  # type: ignore[arg-type]
    assert failed.payment_status == "failed"
    assert failed.status == "pending"

    mvola.status = "pending"
    retried = start_mvola_payment(
        "order-1", MvolaPaymentIn(phone="0343500003"), db_session, customer, mvola
    )  # type: ignore[arg-type]
    assert retried.payment_status == "pending"
    assert len(mvola.initiated) == 2


@pytest.mark.parametrize("phone", ["0321234567", "034123", "abc"])
def test_rejects_non_mvola_numbers(phone: str) -> None:
    with pytest.raises(ValidationError):
        MvolaPaymentIn(phone=phone)
