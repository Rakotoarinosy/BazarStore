import hashlib
import hmac
import json
import time

import httpx
import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from src.infrastructure.config.settings import Settings, get_settings
from src.infrastructure.external.payment_gateway import PaymentGateway, get_payment_gateway
from src.infrastructure.persistence.models import OrderModel, UserModel
from src.main import app

pytestmark = pytest.mark.anyio

SECRET = "whsec_gateway_test"
SETTINGS = Settings(
    payments_enabled=True,
    payment_gateway_url="http://gateway.test",
    payment_gateway_api_key="api-key",
    payment_gateway_webhook_secret=SECRET,
)
URL = "/api/v1/orders/payments/gateway/webhook"


@pytest.fixture
def pending_card_order(engine: Engine) -> None:
    with Session(engine) as db:
        db.add(UserModel(id="u-1", email="c@example.com", name="C"))
        db.add(OrderModel(
            id="order-1", reference="CMD-WH1", user_id="u-1", customer_name="C",
            customer_email="c@example.com", status="pending", total_amount=35_000,
            payment_provider="card", payment_status="pending", payment_correlation_id="pi_1",
        ))
        db.commit()
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    app.dependency_overrides[get_payment_gateway] = lambda: PaymentGateway(SETTINGS)


def _event(status: str, intent_id: str = "pi_1") -> bytes:
    return json.dumps({
        "type": f"payment_intent.{status}",
        "data": {"id": intent_id, "merchant_reference": "order-1", "status": status},
    }).encode()


def _headers(body: bytes, secret: str = SECRET) -> dict[str, str]:
    t = int(time.time())
    digest = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return {"X-Gateway-Signature": f"t={t},v1={digest}", "Content-Type": "application/json"}


async def test_signed_success_webhook_confirms_order(
    client: httpx.AsyncClient, engine: Engine, pending_card_order: None
) -> None:
    body = _event("success")
    assert (await client.post(URL, content=body, headers=_headers(body))).status_code == 204
    with Session(engine) as db:
        order = db.get(OrderModel, "order-1")
        assert order is not None
        assert (order.status, order.payment_status) == ("confirmed", "completed")


async def test_forged_webhook_is_rejected(
    client: httpx.AsyncClient, engine: Engine, pending_card_order: None
) -> None:
    body = _event("success")
    response = await client.post(URL, content=body, headers=_headers(body, "whsec_attaquant"))
    assert response.status_code == 400
    with Session(engine) as db:
        assert db.get(OrderModel, "order-1").payment_status == "pending"  # type: ignore[union-attr]


async def test_webhook_for_superseded_intent_is_ignored(
    client: httpx.AsyncClient, engine: Engine, pending_card_order: None
) -> None:
    body = _event("success", intent_id="pi_old")
    assert (await client.post(URL, content=body, headers=_headers(body))).status_code == 204
    with Session(engine) as db:
        assert db.get(OrderModel, "order-1").payment_status == "pending"  # type: ignore[union-attr]
