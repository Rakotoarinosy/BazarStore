from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from src.domain.user import User
from src.features.order.router import (
    OrderNotPayableConflictError,
    get_card_payment_status,
    start_card_payment,
)
from src.infrastructure.config.settings import Settings
from src.infrastructure.external.card_payment_gateway import CardCheckout, CardPaymentGateway
from src.infrastructure.persistence.models import OrderModel, UserModel


class FakeGateway:
    def __init__(self) -> None:
        self.paid = False
        self.checkouts: list[tuple[str, int]] = []

    def create_checkout(self, *, reference: str, amount_ar: int) -> CardCheckout:
        self.checkouts.append((reference, amount_ar))
        return CardCheckout(
            checkout_url="https://checkout.stripe.com/c/pay/cs_test_1", session_id="cs_test_1"
        )

    def is_paid(self, *, reference: str, amount_ar: int) -> bool:
        return self.paid


@pytest.fixture
def customer(db_session: Session) -> User:
    db_session.add(UserModel(id="customer-1", email="customer@example.com", name="Customer"))
    db_session.add(
        OrderModel(
            id="order-1",
            reference="CMD-CARD1",
            user_id="customer-1",
            customer_name="Customer",
            customer_email="customer@example.com",
            status="pending",
            total_amount=25000,
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


def test_card_payment_redirects_then_confirms_order(db_session: Session, customer: User) -> None:
    gateway = FakeGateway()

    started = start_card_payment("order-1", db_session, customer, gateway)  # type: ignore[arg-type]
    assert started.checkout_url.startswith("https://checkout.stripe.com/")
    assert started.order.payment_provider == "card"
    assert started.order.payment_status == "pending"
    assert gateway.checkouts == [("CMD-CARD1", 25000)]

    still_pending = get_card_payment_status("order-1", db_session, customer, gateway)  # type: ignore[arg-type]
    assert still_pending.status == "pending"

    gateway.paid = True
    paid = get_card_payment_status("order-1", db_session, customer, gateway)  # type: ignore[arg-type]
    assert paid.status == "confirmed"
    assert paid.payment_status == "completed"

    with pytest.raises(OrderNotPayableConflictError):
        start_card_payment("order-1", db_session, customer, gateway)  # type: ignore[arg-type]


def test_gateway_matches_reference_and_converted_amount(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = CardPaymentGateway(Settings(card_payment_ar_per_unit=5000))
    assert gateway.to_gateway_amount(25000) == 5.0
    payments = [
        {"user_id": "CMD-OTHER", "amount": 5.0, "status": "success"},
        {"user_id": "CMD-CARD1", "amount": 4.0, "status": "success"},
    ]
    monkeypatch.setattr(gateway, "_request", lambda method, path, **_: payments)
    assert gateway.is_paid(reference="CMD-CARD1", amount_ar=25000) is False

    payments.append({"user_id": "CMD-CARD1", "amount": 5.0, "status": "success"})
    assert gateway.is_paid(reference="CMD-CARD1", amount_ar=25000) is True
