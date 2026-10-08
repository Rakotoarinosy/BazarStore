from unittest.mock import Mock

import httpx
import pytest
from sqlalchemy.orm import Session

from src.domain.user import GoogleIdentity, InvalidGoogleCredentialsError
from src.features.auth import router as auth_router
from src.infrastructure.config.settings import Settings, get_settings
from src.infrastructure.persistence.models import UserModel
from src.infrastructure.security.google_identity import verify_google_identity
from src.main import app

pytestmark = pytest.mark.anyio

AUTH = "/api/v1/auth"


async def test_register_login_refresh_and_logout(client: httpx.AsyncClient) -> None:
    credentials = {
        "email": "client@example.com",
        "name": "Client BazarStore",
        "password": "BazarStore2026!",
    }

    registered = await client.post(f"{AUTH}/register", json=credentials)

    assert registered.status_code == 201
    assert registered.json()["role"] == "customer"

    logged_in = await client.post(
        f"{AUTH}/login",
        json={"email": credentials["email"], "password": credentials["password"]},
    )

    assert logged_in.status_code == 200
    session = logged_in.json()
    assert session["user"]["email"] == credentials["email"]
    assert "refresh_token=" in logged_in.headers["set-cookie"]

    profile = await client.get(
        f"{AUTH}/me",
        headers={"Authorization": f"Bearer {session['access_token']}"},
    )
    assert profile.status_code == 200
    assert profile.json()["name"] == credentials["name"]

    refreshed = await client.post(f"{AUTH}/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"] != session["access_token"]

    logged_out = await client.post(f"{AUTH}/logout")
    assert logged_out.status_code == 204


async def test_duplicate_registration_and_invalid_login(client: httpx.AsyncClient) -> None:
    credentials = {
        "email": "client@example.com",
        "name": "Client BazarStore",
        "password": "BazarStore2026!",
    }
    await client.post(f"{AUTH}/register", json=credentials)

    duplicate = await client.post(f"{AUTH}/register", json=credentials)
    invalid_login = await client.post(
        f"{AUTH}/login",
        json={"email": credentials["email"], "password": "IncorrectPassword123"},
    )

    assert duplicate.status_code == 409
    assert invalid_login.status_code == 401


async def test_google_login_creates_customer_session(
    client: httpx.AsyncClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        environment="test",
        secret_key="test-google-auth-key-with-more-than-32-characters",
        google_client_id="BazarStore-web-client",
    )
    google_verifier = Mock(
        return_value=GoogleIdentity(
            subject="google-subject-1",
            email="google.customer@example.com",
            name="Google Customer",
        )
    )
    monkeypatch.setattr(auth_router, "verify_google_identity", google_verifier)
    nonce_response = await client.get(f"{AUTH}/google/nonce")
    assert nonce_response.status_code == 200
    nonce = nonce_response.json()["nonce"]

    response = await client.post(f"{AUTH}/google", json={"credential": "signed-id-token"})

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "google.customer@example.com"
    assert response.json()["user"]["role"] == "customer"
    assert "refresh_token=" in response.headers["set-cookie"]
    created_user = db_session.get(UserModel, response.json()["user"]["id"])
    assert created_user is not None
    assert created_user.google_subject == "google-subject-1"
    google_verifier.assert_called_once_with("signed-id-token", "BazarStore-web-client", nonce)
    assert client.cookies.get(auth_router.GOOGLE_NONCE_COOKIE) is None

    replay = await client.post(f"{AUTH}/google", json={"credential": "signed-id-token"})
    assert replay.status_code == 401
    assert google_verifier.call_count == 1


async def test_google_login_requires_client_configuration(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        environment="test",
        secret_key="test-google-auth-key-with-more-than-32-characters",
        google_client_id=None,
    )
    google_verifier = Mock(
        side_effect=AssertionError("Google verifier must not run when unconfigured")
    )
    monkeypatch.setattr(auth_router, "verify_google_identity", google_verifier)

    response = await client.post(f"{AUTH}/google", json={"credential": "signed-id-token"})

    assert response.status_code == 503
    google_verifier.assert_not_called()
    nonce_response = await client.get(f"{AUTH}/google/nonce")
    assert nonce_response.status_code == 503


async def test_google_verifier_rejects_malformed_identity_token() -> None:
    with pytest.raises(InvalidGoogleCredentialsError):
        verify_google_identity("not-a-signed-id-token", "BazarStore-web-client", "expected-nonce")


async def test_legacy_business_routes_are_not_mounted(client: httpx.AsyncClient) -> None:
    for path in ("/api/v1/agents", "/api/v1/demandes", "/api/v1/requests"):
        response = await client.get(path)
        assert response.status_code == 404
