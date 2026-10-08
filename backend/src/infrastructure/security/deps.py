"""Dépendances FastAPI de sécurité : utilisateur courant et contrôle des rôles.

Réutilisables dans tous les routers :
    user: User = Depends(get_current_user)
    dependencies=[Depends(require_roles(Role.MANAGER))]   # ADMIN est toujours autorisé
"""

from collections.abc import Callable
from functools import lru_cache

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from src.domain.user import (
    AccessTokenService,
    AuthPolicy,
    ForbiddenError,
    InvalidTokenError,
    PasswordHasher,
    RefreshTokenRepository,
    Role,
    User,
    UserRepository,
)
from src.infrastructure.config import get_settings
from src.infrastructure.persistence.database import get_db
from src.infrastructure.persistence.refresh_token_repository import (
    SqlAlchemyRefreshTokenRepository,
)
from src.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from src.infrastructure.security.password import Argon2PasswordHasher
from src.infrastructure.security.tokens import JwtAccessTokenService

bearer_scheme = HTTPBearer(auto_error=False)


def get_user_repo(db: Session = Depends(get_db)) -> UserRepository:
    return SqlAlchemyUserRepository(db)


def get_refresh_token_repo(db: Session = Depends(get_db)) -> RefreshTokenRepository:
    return SqlAlchemyRefreshTokenRepository(db)


@lru_cache
def get_password_hasher() -> PasswordHasher:
    return Argon2PasswordHasher()


@lru_cache
def get_token_service() -> AccessTokenService:
    settings = get_settings()

    return JwtAccessTokenService(settings.secret_key, settings.access_token_ttl_minutes)


def get_auth_policy() -> AuthPolicy:
    settings = get_settings()

    return AuthPolicy(
        max_failed_attempts=settings.max_failed_login_attempts,
        lockout_minutes=settings.lockout_minutes,
        refresh_ttl_days=settings.refresh_token_ttl_days,
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    users: UserRepository = Depends(get_user_repo),
    tokens: AccessTokenService = Depends(get_token_service),
) -> User:
    if credentials is None:
        raise InvalidTokenError()

    user = users.get_by_id(tokens.decode(credentials.credentials))
    # Rôle et statut sont relus en base à chaque requête : un changement de rôle par un admin
    # ou une désactivation prend effet immédiatement, sans attendre l'expiration du token.
    if user is None or not user.is_active:
        raise InvalidTokenError()

    return user


def require_roles(*roles: Role) -> Callable[..., User]:
    allowed_roles = set(roles)
    # Les anciens comptes MANAGER et les nouveaux comptes COMMERCIAL partagent
    # les mêmes droits de backoffice pendant la transition.
    if Role.MANAGER in allowed_roles or Role.COMMERCIAL in allowed_roles:
        allowed_roles.update((Role.MANAGER, Role.COMMERCIAL))
    allowed = frozenset(allowed_roles)

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role is not Role.ADMIN and user.role not in allowed:
            raise ForbiddenError()
        return user

    return dependency
