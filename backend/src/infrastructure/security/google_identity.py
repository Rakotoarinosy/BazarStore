"""Validation des jetons d'identité Google à partir des clés publiques OIDC."""

import logging
from secrets import compare_digest

import httpx
import jwt
from jwt import PyJWKClient

from src.domain.user import (
    GoogleAuthUnavailableError,
    GoogleIdentity,
    InvalidGoogleCredentialsError,
)
from src.shared.validation import normalize_email

GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")
logger = logging.getLogger(__name__)


def verify_google_identity(
    credential: str, client_id: str, expected_nonce: str | None
) -> GoogleIdentity:
    """`expected_nonce=None` : flux serveur (code échangé avec le secret), sans nonce."""
    try:
        signing_key = PyJWKClient(GOOGLE_CERTS_URL, timeout=5).get_signing_key_from_jwt(credential)
    except jwt.PyJWKClientConnectionError as exc:
        raise GoogleAuthUnavailableError() from exc
    except jwt.PyJWTError as exc:
        logger.warning("Google ID token signature/key validation failed (%s)", type(exc).__name__)
        raise InvalidGoogleCredentialsError() from exc

    required_claims = ["exp", "iat", "sub", "iss", "aud", "email"]
    if expected_nonce is not None:
        required_claims.append("nonce")
    try:
        claims = jwt.decode(
            credential,
            signing_key.key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=GOOGLE_ISSUERS,
            options={"require": required_claims},
        )
    except jwt.PyJWTError as exc:
        logger.warning("Google ID token claims validation failed (%s)", type(exc).__name__)
        raise InvalidGoogleCredentialsError() from exc

    subject = claims.get("sub")
    email = claims.get("email")
    name = claims.get("name")
    if (
        not isinstance(subject, str)
        or not subject
        or not isinstance(email, str)
        or not email
        or claims.get("email_verified") is not True
    ):
        logger.warning("Google ID token rejected: required identity claims are invalid")
        raise InvalidGoogleCredentialsError()

    nonce = claims.get("nonce")
    if expected_nonce is not None and (
        not isinstance(nonce, str) or not compare_digest(nonce, expected_nonce)
    ):
        logger.warning("Google ID token rejected: nonce does not match the browser session")
        raise InvalidGoogleCredentialsError()

    return GoogleIdentity(
        subject=subject,
        email=normalize_email(email),
        name=name.strip() if isinstance(name, str) and name.strip() else "",
    )


def exchange_google_code(
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code_verifier: str | None = None,
) -> str:
    """Échange un code d'autorisation OAuth contre l'ID token Google (flux serveur)."""
    try:
        response = httpx.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                **({"code_verifier": code_verifier} if code_verifier else {}),
            },
            timeout=10,
        )
    except httpx.HTTPError as exc:
        raise GoogleAuthUnavailableError() from exc

    if response.status_code >= 500:
        raise GoogleAuthUnavailableError()
    id_token = response.json().get("id_token") if response.is_success else None
    if not isinstance(id_token, str) or not id_token:
        logger.warning("Google code exchange failed (HTTP %s)", response.status_code)
        raise InvalidGoogleCredentialsError()

    return id_token
