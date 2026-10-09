import httpx
import pytest

from src.infrastructure.config.settings import Settings, get_settings
from src.infrastructure.external.card_payment_gateway import get_card_payment_gateway
from src.infrastructure.external.mvola_client import get_mvola_client
from src.main import app

pytestmark = pytest.mark.anyio


def _must_not_be_called() -> None:
    raise AssertionError("Aucun service de paiement externe ne doit être contacté")


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/v1/orders/order-1/payments/card"),
        ("GET", "/api/v1/orders/order-1/payments/card"),
        ("POST", "/api/v1/orders/order-1/payments/mvola"),
        ("GET", "/api/v1/orders/order-1/payments/mvola"),
        ("PUT", "/api/v1/orders/payments/mvola/callback"),
    ],
)
async def test_payment_routes_are_cut_when_disabled(
    client: httpx.AsyncClient, method: str, path: str
) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(payments_enabled=False)
    app.dependency_overrides[get_card_payment_gateway] = _must_not_be_called
    app.dependency_overrides[get_mvola_client] = _must_not_be_called

    response = await client.request(method, path, json={})

    assert response.status_code == 503
    assert response.json()["error"] == "PaymentsUnavailableError"
