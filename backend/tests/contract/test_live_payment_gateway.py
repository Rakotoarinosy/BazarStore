"""Contrat BazarStore ↔ passerelle ecommerce_monitoring, contre une passerelle réelle.

Ignoré sauf si PAYMENT_GATEWAY_E2E_URL est défini (CI, ou en local) :

    cd ../ecommerce_monitoring
    GATEWAY_PROVIDER=simulator docker compose -f docker-compose.gateway.yml up -d --build
    PAYMENT_GATEWAY_E2E_URL=http://localhost:8011 PAYMENT_GATEWAY_E2E_KEY=local-gateway-key \\
        uv run pytest -q tests/contract

La passerelle doit tourner en mode simulateur (la page Stripe ne se remplit pas en test) avec
la même clé API. En CI, aucune clé Stripe n'est présente : le simulateur est choisi d'office.
"""

import os
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.orm import Session

from src.domain.user import User
from src.features.order.router import get_card_payment_status, start_card_payment
from src.infrastructure.config.settings import Settings
from src.infrastructure.external.payment_gateway import PaymentGateway
from src.infrastructure.persistence.models import OrderItemModel, OrderModel, UserModel

GATEWAY_URL = os.getenv("PAYMENT_GATEWAY_E2E_URL")
pytestmark = pytest.mark.skipif(not GATEWAY_URL, reason="PAYMENT_GATEWAY_E2E_URL non défini")


@pytest.fixture
def setup(db_session: Session) -> tuple[User, PaymentGateway, Settings]:
    settings = Settings(
        public_frontend_url="http://localhost:4300",
        payment_gateway_url=GATEWAY_URL,
        payment_gateway_api_key=os.getenv("PAYMENT_GATEWAY_E2E_KEY", "local-gateway-key"),
    )
    db_session.add(UserModel(id="u-e2e", email="e2e@example.com", name="E2E"))
    order_id = f"e2e-{datetime.now(UTC).timestamp()}"
    db_session.add(OrderModel(
        id=order_id, reference="CMD-E2E", user_id="u-e2e", customer_name="E2E",
        customer_email="e2e@example.com", status="pending", total_amount=265_600,
        items=[OrderItemModel(product_name="Sac", unit_price=132_800, quantity=2,
                              line_total=265_600)],
    ))
    db_session.commit()
    user = User(id="u-e2e", email="e2e@example.com", name="E2E",
                created_at=datetime.now(UTC), password_hash="")
    return user, PaymentGateway(settings), settings


@pytest.mark.parametrize(("action", "order_status", "payment_status"), [
    ("pay", "confirmed", "completed"),
    ("decline", "pending", "failed"),
])
def test_order_paid_through_real_gateway(
    db_session: Session, setup: tuple[User, PaymentGateway, Settings],
    action: str, order_status: str, payment_status: str,
) -> None:
    user, gateway, settings = setup
    order_id = db_session.query(OrderModel).filter_by(user_id="u-e2e").one().id

    checkout = start_card_payment(order_id, db_session, user, gateway, settings)
    assert checkout.order.payment_status == "pending"

    # Le « client » valide sur la page du simulateur, qui le renvoie vers la boutique.
    page = httpx.get(checkout.checkout_url)
    assert "265 600 Ar" in page.text
    submitted = httpx.post(checkout.checkout_url, data={"action": action})
    assert submitted.status_code == 303
    assert submitted.headers["location"].startswith(f"http://localhost:4300/my-orders?order={order_id}")

    final = get_card_payment_status(order_id, db_session, user, gateway)
    assert (final.status, final.payment_status) == (order_status, payment_status)
