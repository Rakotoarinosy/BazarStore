"""Paiement par carte via la passerelle ecommerce_monitoring (client HTTP simulé)."""

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.orm import Session

from src.domain.user import User
from src.features.order.router import (
    OrderNotPayableConflictError,
    get_card_payment_status,
    start_card_payment,
)
from src.infrastructure.config.settings import Settings
from src.infrastructure.external.payment_gateway import (
    CheckoutLine,
    InvalidGatewayWebhookError,
    PaymentGateway,
    PaymentGatewayUnavailableError,
    verify_signature,
)
from src.infrastructure.persistence.models import OrderItemModel, OrderModel, UserModel

SECRET = "whsec_gateway_test"
SETTINGS = Settings(
    public_frontend_url="http://localhost:4300",
    payment_gateway_url="http://gateway.test",
    payment_gateway_api_key="api-key",
    payment_gateway_webhook_secret=SECRET,
)


class FakeGatewayApi:
    """Rejoue l'API /v1/payment-intents de la passerelle."""

    def __init__(self) -> None:
        self.status = "pending"
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.headers["authorization"] == "Bearer api-key"
        body = {
            "id": "pi_1",
            "merchant_reference": "order-1",
            "amount": 1_328_000,
            "currency": "MGA",
            "status": self.status,
            "checkout_url": "http://gateway.test/v1/simulator/checkout/pi_1",
        }
        return httpx.Response(201 if request.method == "POST" else 200, json=body)


@pytest.fixture
def api() -> FakeGatewayApi:
    return FakeGatewayApi()


@pytest.fixture
def gateway(api: FakeGatewayApi) -> PaymentGateway:
    return PaymentGateway(SETTINGS, transport=httpx.MockTransport(api))


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


def test_card_checkout_then_confirmation(
    db_session: Session, customer: User, api: FakeGatewayApi, gateway: PaymentGateway
) -> None:
    started = start_card_payment("order-1", db_session, customer, gateway, SETTINGS)
    assert started.checkout_url == "http://gateway.test/v1/simulator/checkout/pi_1"
    assert started.order.payment_provider == "card"

    sent = json.loads(api.requests[0].content)
    assert api.requests[0].url == "http://gateway.test/v1/payment-intents"
    assert sent["amount"] == 1_328_000
    assert sent["currency"] == "MGA"
    assert (sent["customer_name"], sent["order_reference"]) == ("Customer", "CMD-CARD1")
    assert sent["success_url"] == "http://localhost:4300/my-orders?order=order-1&payment=success"
    assert sorted(line["name"] for line in sent["lines"]) == ["Baskets", "Casque audio"]

    assert get_card_payment_status("order-1", db_session, customer, gateway).status == "pending"

    api.status = "success"
    paid = get_card_payment_status("order-1", db_session, customer, gateway)
    assert paid.status == "confirmed"
    assert paid.payment_status == "completed"

    with pytest.raises(OrderNotPayableConflictError):
        start_card_payment("order-1", db_session, customer, gateway, SETTINGS)


def test_declined_payment_marks_order_failed(
    db_session: Session, customer: User, api: FakeGatewayApi, gateway: PaymentGateway
) -> None:
    start_card_payment("order-1", db_session, customer, gateway, SETTINGS)
    api.status = "failed"
    failed = get_card_payment_status("order-1", db_session, customer, gateway)
    assert failed.payment_status == "failed"
    assert failed.status == "pending"


def test_gateway_outage_is_a_clean_domain_error(db_session: Session, customer: User) -> None:
    down = PaymentGateway(SETTINGS, transport=httpx.MockTransport(lambda _: httpx.Response(502)))
    with pytest.raises(PaymentGatewayUnavailableError):
        down.create_checkout(
            order_id="order-1",
            reference="CMD-CARD1",
            amount_ar=1,
            customer_name="C",
            customer_email="c@example.com",
            lines=[CheckoutLine(name="x", unit_price_ar=1, quantity=1)],
            success_url="http://a",
            cancel_url="http://b",
        )


def _signed(payload: bytes, secret: str = SECRET, timestamp: int | None = None) -> str:
    timestamp = int(time.time()) if timestamp is None else timestamp
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256)
    return f"t={timestamp},v1={digest.hexdigest()}"


def test_webhook_signature_is_verified(gateway: PaymentGateway) -> None:
    payload = json.dumps(
        {
            "type": "payment_intent.succeeded",
            "data": {"id": "pi_1", "merchant_reference": "order-1", "status": "success"},
        }
    ).encode()

    state = gateway.parse_webhook(payload, _signed(payload))
    assert (state.intent_id, state.order_id, state.paid) == ("pi_1", "order-1", True)

    with pytest.raises(InvalidGatewayWebhookError):
        gateway.parse_webhook(payload, _signed(payload, "whsec_attaquant"))
    with pytest.raises(InvalidGatewayWebhookError):
        gateway.parse_webhook(payload + b" ", _signed(payload))


def test_stale_signature_is_rejected_against_replay() -> None:
    payload = b"{}"
    assert not verify_signature(payload, _signed(payload, timestamp=int(time.time()) - 3600), SECRET)
    assert not verify_signature(payload, None, SECRET)
    assert not verify_signature(payload, "garbage", SECRET)
