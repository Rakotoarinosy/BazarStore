"""Validation des jetons d'identité Google à partir des clés publiques OIDC."""

import logging
from secrets import compare_digest

import jwt
from jwt import PyJWKClient

from src.domain.user import (
    GoogleAuthUnavailableError,
    GoogleIdentity,
    InvalidGoogleCredentialsError,
)
from src.shared.validation import normalize_email

GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")
logger = logging.getLogger(__name__)


def verify_google_identity(credential: str, client_id: str, expected_nonce: str) -> GoogleIdentity:
    try:
        signing_key = PyJWKClient(GOOGLE_CERTS_URL, timeout=5).get_signing_key_from_jwt(credential)
    except jwt.PyJWKClientConnectionError as exc:
        raise GoogleAuthUnavailableError() from exc
    except jwt.PyJWTError as exc:
        logger.warning("Google ID token signature/key validation failed (%s)", type(exc).__name__)
        raise InvalidGoogleCredentialsError() from exc

    try:
        claims = jwt.decode(
            credential,
            signing_key.key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=GOOGLE_ISSUERS,
            options={"require": ["exp", "iat", "sub", "iss", "aud", "email", "nonce"]},
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
        or not isinstance(claims.get("nonce"), str)
    ):
        logger.warning("Google ID token rejected: required identity claims are invalid")
        raise InvalidGoogleCredentialsError()

    if not compare_digest(claims["nonce"], expected_nonce):
        logger.warning("Google ID token rejected: nonce does not match the browser session")
        raise InvalidGoogleCredentialsError()

    return GoogleIdentity(
        subject=subject,
        email=normalize_email(email),
        name=name.strip() if isinstance(name, str) and name.strip() else "",
    )
