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
