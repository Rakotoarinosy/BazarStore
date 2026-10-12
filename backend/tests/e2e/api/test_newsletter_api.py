from collections.abc import Iterator
from datetime import UTC, datetime

import httpx
import pytest

from src.domain.user import Role, User
from src.infrastructure.security.deps import get_current_user
from src.main import app

pytestmark = pytest.mark.anyio

SUBSCRIPTIONS = "/api/v1/newsletter/subscriptions"


def _user(role: Role) -> User:
    return User(
        id=f"{role.value}-id",
        email=f"{role.value}@test.mg",
        name=role.value,
        created_at=datetime.now(UTC),
        password_hash="",
        role=role,
    )


@pytest.fixture
def as_commercial() -> Iterator[None]:
    app.dependency_overrides[get_current_user] = lambda: _user(Role.COMMERCIAL)
    yield
    app.dependency_overrides.pop(get_current_user, None)


async def test_subscribe_normalizes_and_deduplicates_email(
    client: httpx.AsyncClient, as_commercial: None
) -> None:
    first = await client.post(SUBSCRIPTIONS, json={"email": "Jane.Doe@Example.com"})
    again = await client.post(SUBSCRIPTIONS, json={"email": "jane.doe@example.com"})

    # Même réponse pour une adresse déjà inscrite : la liste n'est pas révélée.
    assert first.status_code == again.status_code == 201
    assert first.json() == again.json()

    listing = (await client.get(SUBSCRIPTIONS)).json()
    assert listing["total"] == 1
    assert [s["email"] for s in listing["subscribers"]] == ["jane.doe@example.com"]


async def test_subscribe_rejects_invalid_email(client: httpx.AsyncClient) -> None:
    response = await client.post(SUBSCRIPTIONS, json={"email": "pas-une-adresse"})

    assert response.status_code == 422


async def test_subscriber_list_is_reserved_to_backoffice(client: httpx.AsyncClient) -> None:
    assert (await client.get(SUBSCRIPTIONS)).status_code == 401

    app.dependency_overrides[get_current_user] = lambda: _user(Role.CUSTOMER)
    try:
        assert (await client.get(SUBSCRIPTIONS)).status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


async def test_search_filters_subscribers(client: httpx.AsyncClient, as_commercial: None) -> None:
    for email in ("alice@example.com", "bob@example.com"):
        await client.post(SUBSCRIPTIONS, json={"email": email})

    listing = (await client.get(SUBSCRIPTIONS, params={"search": "ALICE"})).json()

    assert listing["total"] == 1
    assert listing["subscribers"][0]["email"] == "alice@example.com"


async def test_export_is_excel_friendly_csv_with_unsubscribe_links(
    client: httpx.AsyncClient, as_commercial: None
) -> None:
    await client.post(SUBSCRIPTIONS, json={"email": "alice@example.com"})

    response = await client.get(f"{SUBSCRIPTIONS}/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment;" in response.headers["content-disposition"]
    lines = response.content.decode("utf-8-sig").splitlines()
    assert lines[0] == "email;date_inscription;lien_desinscription"
    email, _, link = lines[1].split(";")
    assert email == "alice@example.com"
    assert "/newsletter/unsubscribe?token=" in link


async def test_unsubscribe_link_deactivates_subscription(
    client: httpx.AsyncClient, as_commercial: None
) -> None:
    await client.post(SUBSCRIPTIONS, json={"email": "alice@example.com"})
    export = (await client.get(f"{SUBSCRIPTIONS}/export")).content.decode("utf-8-sig")
    token = export.splitlines()[1].rsplit("token=", 1)[1]

    first = await client.post("/api/v1/newsletter/unsubscribe", json={"token": token})
    again = await client.post("/api/v1/newsletter/unsubscribe", json={"token": token})

    assert first.status_code == again.status_code == 200
    assert (await client.get(SUBSCRIPTIONS)).json()["total"] == 0

    # Une nouvelle inscription réactive l'adresse.
    await client.post(SUBSCRIPTIONS, json={"email": "alice@example.com"})
    assert (await client.get(SUBSCRIPTIONS)).json()["total"] == 1


async def test_unsubscribe_rejects_unknown_token(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/v1/newsletter/unsubscribe", json={"token": "inconnu"})

    assert response.status_code == 404


async def test_backoffice_can_remove_a_subscriber(
    client: httpx.AsyncClient, as_commercial: None
) -> None:
    await client.post(SUBSCRIPTIONS, json={"email": "alice@example.com"})
    subscriber_id = (await client.get(SUBSCRIPTIONS)).json()["subscribers"][0]["id"]

    assert (await client.delete(f"{SUBSCRIPTIONS}/{subscriber_id}")).status_code == 204
    assert (await client.get(SUBSCRIPTIONS)).json()["total"] == 0
    assert (await client.delete(f"{SUBSCRIPTIONS}/inconnu")).status_code == 404


async def test_export_and_removal_are_reserved_to_backoffice(client: httpx.AsyncClient) -> None:
    assert (await client.get(f"{SUBSCRIPTIONS}/export")).status_code == 401
    assert (await client.delete(f"{SUBSCRIPTIONS}/any-id")).status_code == 401


def test_csv_cells_cannot_be_read_as_spreadsheet_formulas() -> None:
    from src.features.newsletter.router import _csv_cell

    assert _csv_cell("=HYPERLINK(1)@example.com") == "'=HYPERLINK(1)@example.com"
    assert _csv_cell("alice@example.com") == "alice@example.com"
