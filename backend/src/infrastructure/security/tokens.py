"""Access tokens JWT (HS256) de courte durée. Le rôle n'est PAS dans le token : il est relu en base."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt

from src.domain.user.exceptions import InvalidTokenError
from src.domain.user.ports import AccessToken, AccessTokenService

ALGORITHM = "HS256"
ISSUER = "bazarstore"


class JwtAccessTokenService(AccessTokenService):
    def __init__(self, secret_key: str, ttl_minutes: int) -> None:
        self._secret = secret_key
        self._ttl = timedelta(minutes=ttl_minutes)

    def create(self, user_id: str) -> AccessToken:
        now = datetime.now(UTC)
        payload = {
            "sub": user_id,
            "iss": ISSUER,
            "iat": now,
            "exp": now + self._ttl,
            "jti": str(uuid.uuid4()),
            "type": "access",
        }

        return AccessToken(
            value=jwt.encode(payload, self._secret, algorithm=ALGORITHM),
            expires_in=int(self._ttl.total_seconds()),
        )

    def decode(self, token: str) -> str:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[ALGORITHM],  # liste figée : pas d'attaque « alg: none »
                issuer=ISSUER,
                options={"require": ["exp", "iat", "sub", "iss"]},
            )
        except jwt.PyJWTError as exc:
            raise InvalidTokenError() from exc

        if payload.get("type") != "access" or not isinstance(payload["sub"], str):
            raise InvalidTokenError()

        return payload["sub"]
