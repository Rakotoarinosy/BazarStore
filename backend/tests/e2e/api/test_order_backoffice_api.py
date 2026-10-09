import httpx
import pytest

pytestmark = pytest.mark.anyio

AUTH = "/api/v1/auth"


async def _customer_token(client: httpx.AsyncClient) -> str:
    credentials = {"email": "client@example.com", "name": "Client", "password": "Str0ng!Passw0rd"}
    await client.post(f"{AUTH}/register", json=credentials)
    login = await client.post(
        f"{AUTH}/login", json={"email": credentials["email"], "password": credentials["password"]}
    )
    return login.json()["access_token"]


async def test_customers_cannot_manage_orders(client: httpx.AsyncClient) -> None:
    headers = {"Authorization": f"Bearer {await _customer_token(client)}"}

    listing = await client.get("/api/v1/orders/manage", headers=headers)
    update = await client.patch(
        "/api/v1/orders/o-1/status", json={"status": "shipped"}, headers=headers
    )

    assert listing.status_code == 403
    assert update.status_code == 403


async def test_order_management_requires_authentication(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/orders/manage")).status_code == 401
