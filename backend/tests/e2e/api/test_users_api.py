import httpx
import pytest

pytestmark = pytest.mark.anyio

USERS = "/api/v1/users"


async def test_health(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_user_crud_flow(client: httpx.AsyncClient) -> None:
    # POST
    response = await client.post(USERS, json={"email": "ada@example.com", "name": "Ada"})
    assert response.status_code == 201
    user = response.json()
    assert user["email"] == "ada@example.com"
    assert set(user) == {"id", "email", "name", "created_at"}

    # GET (détail + liste)
    response = await client.get(f"{USERS}/{user['id']}")
    assert response.status_code == 200
    assert response.json() == user

    response = await client.get(USERS)
    assert response.json() == [user]

    # PUT
    response = await client.put(f"{USERS}/{user['id']}", json={"name": "Ada Lovelace"})
    assert response.status_code == 200
    assert response.json() == {**user, "name": "Ada Lovelace"}

    # DELETE
    response = await client.delete(f"{USERS}/{user['id']}")
    assert response.status_code == 204

    response = await client.get(f"{USERS}/{user['id']}")
    assert response.status_code == 404


async def test_duplicate_email_returns_409(client: httpx.AsyncClient) -> None:
    payload = {"email": "ada@example.com", "name": "Ada"}
    await client.post(USERS, json=payload)

    response = await client.post(USERS, json=payload)

    assert response.status_code == 409
    assert response.json()["error"] == "UserAlreadyExistsError"


async def test_unknown_user_returns_404(client: httpx.AsyncClient) -> None:
    response = await client.get(f"{USERS}/missing")

    assert response.status_code == 404
    assert response.json()["error"] == "UserNotFoundError"


async def test_invalid_email_returns_422(client: httpx.AsyncClient) -> None:
    response = await client.post(USERS, json={"email": "not-an-email", "name": "Ada"})

    assert response.status_code == 422
