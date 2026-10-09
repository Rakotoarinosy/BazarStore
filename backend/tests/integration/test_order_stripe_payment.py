import hashlib
import hmac
import json
import time
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from src.domain.user import User
from src.features.order.router import (
    OrderNotPayableConflictError,
    get_stripe_payment_status,
    start_stripe_payment,
)
from src.infrastructure.config.settings import Settings
from src.infrastructure.external.stripe_payments import (
    CheckoutLine,
    InvalidStripeWebhookError,
    StripeCheckout,
    StripePayments,
    StripeSessionState,
)
from src.infrastructure.persistence.models import OrderItemModel, OrderModel, UserModel

SETTINGS = Settings(public_frontend_url="http://localhost:4300")


class FakeStripe:
    def __init__(self) -> None:
        self.paid = False
        self.expired = False
        self.calls: list[dict[str, object]] = []

    def create_checkout(self, **kwargs: object) -> StripeCheckout:
        self.calls.append(kwargs)
        return StripeCheckout(
            url="https://checkout.stripe.com/c/pay/cs_test_1", session_id="cs_test_1"
        )

    def get_session_state(self, session_id: str) -> StripeSessionState:
        assert session_id == "cs_test_1"
        return StripeSessionState(order_id="order-1", paid=self.paid, expired=self.expired)


@pytest.fixture
def customer(db_session: Session) -> User:
    db_session.add(UserModel(id="customer-1", email="customer@example.com", name="Customer"))
    db_session.add(
        OrderModel(
            id="order-1",
            reference="CMD-STRIPE1",
            user_id="customer-1",
            customer_name="Customer",
            customer_email="customer@example.com",
            status="pending",
            total_amount=1_328_000,
            items=[
                OrderItemModel(
                    product_name="Casque audio", unit_price=700_000, quantity=1, line_total=700_000
                ),
                OrderItemModel(
                    product_name="Baskets", unit_price=314_000, quantity=2, line_total=628_000
                ),
            ],
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


def test_stripe_checkout_then_confirmation(db_session: Session, customer: User) -> None:
    stripe = FakeStripe()

    started = start_stripe_payment("order-1", db_session, customer, stripe, SETTINGS)  # type: ignore[arg-type]
    assert started.checkout_url.startswith("https://checkout.stripe.com/")
    assert started.order.payment_provider == "stripe"
    call = stripe.calls[0]
    assert call["order_id"] == "order-1"
    assert call["success_url"] == "http://localhost:4300/my-orders?order=order-1&payment=success"
    assert sorted(call["lines"], key=lambda line: line.name) == [  # type: ignore[arg-type]
        CheckoutLine(name="Baskets", unit_price_ar=314_000, quantity=2),
        CheckoutLine(name="Casque audio", unit_price_ar=700_000, quantity=1),
    ]

    assert get_stripe_payment_status("order-1", db_session, customer, stripe).status == "pending"  # type: ignore[arg-type]

    stripe.paid = True
    paid = get_stripe_payment_status("order-1", db_session, customer, stripe)  # type: ignore[arg-type]
    assert paid.status == "confirmed"
    assert paid.payment_status == "completed"

    with pytest.raises(OrderNotPayableConflictError):
        start_stripe_payment("order-1", db_session, customer, stripe, SETTINGS)  # type: ignore[arg-type]


def test_expired_session_marks_payment_failed(db_session: Session, customer: User) -> None:
    stripe = FakeStripe()
    start_stripe_payment("order-1", db_session, customer, stripe, SETTINGS)  # type: ignore[arg-type]

    stripe.expired = True
    failed = get_stripe_payment_status("order-1", db_session, customer, stripe)  # type: ignore[arg-type]
    assert failed.payment_status == "failed"
    assert failed.status == "pending"


@pytest.mark.parametrize(
    ("currency", "amount_ar", "expected"),
    [("mga", 1_328_000, 1_328_000), ("eur", 1_328_000, 26_560), ("eur", 2_500, 50)],
)
def test_amount_conversion(currency: str, amount_ar: int, expected: int) -> None:
    payments = StripePayments(Settings(stripe_secret_key="sk_test_x", stripe_currency=currency))
    assert payments.to_stripe_amount(amount_ar) == expected


def _signed(payload: bytes, secret: str) -> str:
    timestamp = int(time.time())
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256)
    return f"t={timestamp},v1={digest.hexdigest()}"


def test_webhook_signature_is_verified_with_the_real_stripe_library() -> None:
    payments = StripePayments(
        Settings(stripe_secret_key="sk_test_x", stripe_webhook_secret="whsec_test")
    )
    event = {
        "id": "evt_1",
        "object": "event",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_1",
                "object": "checkout.session",
                "payment_status": "paid",
                "status": "complete",
                "metadata": {"order_id": "order-1"},
            }
        },
    }
    payload = json.dumps(event).encode()

    session_id, state = payments.parse_webhook(payload, _signed(payload, "whsec_test"))  # type: ignore[misc]
    assert session_id == "cs_test_1"
    assert state == StripeSessionState(order_id="order-1", paid=True, expired=False)

    with pytest.raises(InvalidStripeWebhookError):
        payments.parse_webhook(payload, _signed(payload, "whsec_attaquant"))
