"""API d'intégration Odoo : réservée aux administrateurs, coupée par défaut, champs Odoo verrouillés."""

from collections.abc import Iterator
from contextlib import contextmanager

import httpx
import pytest
from sqlalchemy import Engine, update
from sqlalchemy.orm import Session

from src.domain.integration import OdooCatalogSource
from src.features.integration.router import get_catalog_opener
from src.infrastructure.config.settings import get_settings
from src.infrastructure.persistence.models import UserModel
from src.main import app
from tests.fakes_odoo import FakeOdooCatalog, odoo_product

pytestmark = pytest.mark.anyio

AUTH = "/api/v1/auth"
SYNC = "/api/v1/integration/odoo/catalog/sync"
PASSWORD = "Str0ng!Passw0rd"


async def _token(client: httpx.AsyncClient, engine: Engine, email: str, role: str) -> str:
    await client.post(
        f"{AUTH}/register", json={"email": email, "name": "Test", "password": PASSWORD}
    )
    with Session(engine) as db:
        db.execute(update(UserModel).where(UserModel.email == email).values(role=role))
        db.commit()
    login = await client.post(f"{AUTH}/login", json={"email": email, "password": PASSWORD})
    return str(login.json()["access_token"])


def _enable_odoo(odoo: FakeOdooCatalog) -> None:
    enabled = get_settings().model_copy(update={"odoo_sync_enabled": True})
    app.dependency_overrides[get_settings] = lambda: enabled

    @contextmanager
    def open_catalog(correlation_id: str) -> Iterator[OdooCatalogSource]:
        yield odoo

    app.dependency_overrides[get_catalog_opener] = lambda: open_catalog


async def test_sync_requires_an_administrator(client: httpx.AsyncClient, engine: Engine) -> None:
    customer = await _token(client, engine, "client@example.com", "customer")
    commercial = await _token(client, engine, "vente@example.com", "commercial")

    assert (await client.post(SYNC)).status_code == 401
    for token in (customer, commercial):
        headers = {"Authorization": f"Bearer {token}"}
        assert (await client.post(SYNC, headers=headers)).status_code == 403
        assert (
            await client.get("/api/v1/integration/odoo/runs", headers=headers)
        ).status_code == 403


async def test_sync_is_cut_when_disabled(client: httpx.AsyncClient, engine: Engine) -> None:
    headers = {
        "Authorization": f"Bearer {await _token(client, engine, 'admin@example.com', 'admin')}"
    }
    disabled = get_settings().model_copy(update={"odoo_sync_enabled": False})
    app.dependency_overrides[get_settings] = lambda: disabled

    def must_not_be_called() -> None:
        raise AssertionError("Odoo ne doit pas être contacté")

    app.dependency_overrides[get_catalog_opener] = must_not_be_called

    response = await client.post(SYNC, headers=headers)

    assert response.status_code == 503
    assert response.json()["error"] == "OdooSyncUnavailableError"


async def test_admin_sync_publishes_the_catalog_and_logs_the_run(
    client: httpx.AsyncClient, engine: Engine
) -> None:
    headers = {
        "Authorization": f"Bearer {await _token(client, engine, 'admin@example.com', 'admin')}"
    }
    _enable_odoo(FakeOdooCatalog([odoo_product(42, "BAZ-TECH-001", "Casque audio", price=700_000)]))

    response = await client.post(SYNC, headers=headers)
    catalog = await client.get("/api/v1/products")
    runs = await client.get("/api/v1/integration/odoo/runs", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["created_count"], body["trigger"]) == ("succeeded", 1, "api")
    product = catalog.json()[0]
    assert (product["code"], product["price"], product["odoo_product_id"]) == (
        "BAZ-TECH-001",
        700_000,
        42,
    )
    assert runs.json()[0]["correlation_id"] == body["correlation_id"]


async def test_odoo_managed_fields_are_locked_in_the_backoffice(
    client: httpx.AsyncClient, engine: Engine
) -> None:
    headers = {
        "Authorization": f"Bearer {await _token(client, engine, 'admin@example.com', 'admin')}"
    }
    _enable_odoo(FakeOdooCatalog([odoo_product(42, "BAZ-TECH-001", "Casque audio", price=700_000)]))
    await client.post(SYNC, headers=headers)
    product = (await client.get("/api/v1/products")).json()[0]
    url = f"/api/v1/products/{product['id']}"

    price_change = await client.patch(url, json={"price": 1}, headers=headers)
    unchanged_form = await client.patch(
        url,
        json={"price": 700_000, "name": "Casque audio", "description": "Nouveau texte"},
        headers=headers,
    )
    deletion = await client.delete(url, headers=headers)

    assert price_change.status_code == 409
    assert "price" in price_change.json()["detail"]
    assert unchanged_form.status_code == 200  # valeurs identiques + description : accepté
    assert unchanged_form.json()["description"] == "Nouveau texte"
    assert deletion.status_code == 409


async def test_single_product_id_must_be_positive(
    client: httpx.AsyncClient, engine: Engine
) -> None:
    headers = {
        "Authorization": f"Bearer {await _token(client, engine, 'admin@example.com', 'admin')}"
    }
    _enable_odoo(FakeOdooCatalog([]))

    response = await client.post("/api/v1/integration/odoo/products/0/sync", headers=headers)

    assert response.status_code == 422
