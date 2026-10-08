"""Use cases d'authentification. Ne dépendent que du domaine : ni HTTP, ni SQL.

Refresh tokens : opaques, stockés hachés (SHA-256), rotatifs (un usage), groupés en « familles ».
La réutilisation d'un token déjà consommé révoque toute la famille (détection de vol).
"""

import hashlib
import logging
import secrets
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from src.domain.user import (
    AccessToken,
    AccessTokenService,
    AccountLockedError,
    AuthPolicy,
    GoogleIdentity,
    IncorrectPasswordError,
    InvalidCredentialsError,
    InvalidGoogleCredentialsError,
    InvalidTokenError,
    PasswordHasher,
    PasswordReuseError,
    RefreshToken,
    RefreshTokenRepository,
    Role,
    User,
    UserAlreadyExistsError,
    UserRepository,
)
from src.features.auth.schemas import ChangePasswordIn, LoginIn, RegisterIn

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthSession:
    user: User
    access_token: AccessToken
    refresh_token: str  # valeur brute : à poser dans le cookie, jamais stockée en clair


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _issue_session(
    user: User,
    family_id: str,
    refresh_repo: RefreshTokenRepository,
    tokens: AccessTokenService,
    policy: AuthPolicy,
    now: datetime,
) -> AuthSession:
    raw = secrets.token_urlsafe(48)
    refresh_repo.add(
        RefreshToken(
            id=str(uuid.uuid4()),
            user_id=user.id,
            family_id=family_id,
            token_hash=_hash_token(raw),
            expires_at=now + timedelta(days=policy.refresh_ttl_days),
            created_at=now,
        )
    )

    return AuthSession(user=user, access_token=tokens.create(user.id), refresh_token=raw)


def register(dto: RegisterIn, users: UserRepository, hasher: PasswordHasher) -> User:
    if users.get_by_email(dto.email):
        raise UserAlreadyExistsError(dto.email)

    user = User(
        id=str(uuid.uuid4()),
        email=dto.email,
        name=dto.name,
        created_at=datetime.now(UTC),
        password_hash=hasher.hash(dto.password),
        role=Role.CUSTOMER,
    )

    return users.add(user)


def login(
    dto: LoginIn,
    users: UserRepository,
    refresh_repo: RefreshTokenRepository,
    hasher: PasswordHasher,
    tokens: AccessTokenService,
    policy: AuthPolicy,
) -> AuthSession:
    now = datetime.now(UTC)
    user = users.get_by_email(dto.email)

    if user is None:
        hasher.hash(dto.password)  # égalise le temps de réponse (anti-énumération de comptes)
        raise InvalidCredentialsError()

    if user.is_locked(now):
        raise AccountLockedError()

    if not hasher.verify(dto.password, user.password_hash):
        attempts = user.failed_login_attempts + 1
        lock = attempts >= policy.max_failed_attempts
        users.update(
            replace(
                user,
                failed_login_attempts=0 if lock else attempts,
                locked_until=now + timedelta(minutes=policy.lockout_minutes) if lock else None,
            )
        )
        raise InvalidCredentialsError()

    # Compte désactivé : même erreur qu'un mauvais mot de passe, après vérification du mot de passe.
    if not user.is_active:
        raise InvalidCredentialsError()

    changes: dict[str, object] = {}
    if user.failed_login_attempts or user.locked_until:
        changes.update(failed_login_attempts=0, locked_until=None)
    if hasher.needs_rehash(user.password_hash):
        changes["password_hash"] = hasher.hash(dto.password)
    if changes:
        user = users.update(replace(user, **changes))

    refresh_repo.delete_expired(now)

    return _issue_session(user, str(uuid.uuid4()), refresh_repo, tokens, policy, now)


def login_with_google(
    identity: GoogleIdentity,
    users: UserRepository,
    refresh_repo: RefreshTokenRepository,
    hasher: PasswordHasher,
    tokens: AccessTokenService,
    policy: AuthPolicy,
) -> AuthSession:
    now = datetime.now(UTC)
    user = users.get_by_email(identity.email)

    if user is None:
        user = users.add(
            User(
                id=str(uuid.uuid4()),
                email=identity.email,
                name=identity.name or identity.email.partition("@")[0],
                created_at=now,
                password_hash=hasher.hash(secrets.token_urlsafe(48)),
                role=Role.CUSTOMER,
                google_subject=identity.subject,
            )
        )
    elif not user.is_active:
        logger.warning("Google login rejected: matched account is inactive")
        raise InvalidGoogleCredentialsError()
    elif user.google_subject is not None and user.google_subject != identity.subject:
        logger.warning("Google login rejected: account is linked to a different Google identity")
        raise InvalidGoogleCredentialsError()
    elif user.google_subject is None:
        user = users.update(replace(user, google_subject=identity.subject))

    refresh_repo.delete_expired(now)

    return _issue_session(user, str(uuid.uuid4()), refresh_repo, tokens, policy, now)


def refresh(
    raw_token: str | None,
    users: UserRepository,
    refresh_repo: RefreshTokenRepository,
    tokens: AccessTokenService,
    policy: AuthPolicy,
) -> AuthSession:
    if not raw_token:
        raise InvalidTokenError()

    now = datetime.now(UTC)
    stored = refresh_repo.get_by_hash(_hash_token(raw_token))
    if stored is None:
        raise InvalidTokenError()

    if stored.revoked_at is not None:
        # Token déjà consommé : vol probable → on coupe toute la session.
        refresh_repo.revoke_family(stored.family_id, now)
        raise InvalidTokenError()

    if stored.expires_at <= now:
        raise InvalidTokenError()

    if not refresh_repo.revoke(stored.id, now):  # course : un autre appel l'a consommé avant
        refresh_repo.revoke_family(stored.family_id, now)
        raise InvalidTokenError()

    user = users.get_by_id(stored.user_id)
    if user is None or not user.is_active:
        refresh_repo.revoke_family(stored.family_id, now)
        raise InvalidTokenError()

    return _issue_session(user, stored.family_id, refresh_repo, tokens, policy, now)


def logout(raw_token: str | None, refresh_repo: RefreshTokenRepository) -> None:
    """Idempotent : ne lève jamais d'erreur si le token est absent ou inconnu."""
    if not raw_token:
        return

    stored = refresh_repo.get_by_hash(_hash_token(raw_token))
    if stored:
        refresh_repo.revoke_family(stored.family_id, datetime.now(UTC))


def logout_all(user: User, refresh_repo: RefreshTokenRepository) -> None:
    refresh_repo.revoke_all_for_user(user.id, datetime.now(UTC))


def change_password(
    user: User,
    dto: ChangePasswordIn,
    users: UserRepository,
    refresh_repo: RefreshTokenRepository,
    hasher: PasswordHasher,
    tokens: AccessTokenService,
    policy: AuthPolicy,
) -> AuthSession:
    if not hasher.verify(dto.current_password, user.password_hash):
        raise IncorrectPasswordError()
    if dto.new_password == dto.current_password:
        raise PasswordReuseError()

    now = datetime.now(UTC)
    user = users.update(replace(user, password_hash=hasher.hash(dto.new_password)))
    refresh_repo.revoke_all_for_user(user.id, now)  # déconnecte tous les autres appareils

    return _issue_session(user, str(uuid.uuid4()), refresh_repo, tokens, policy, now)
