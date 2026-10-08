"""Endpoints HTTP d'authentification.

Le refresh token voyage dans un cookie HttpOnly (illisible par JavaScript → résistant au XSS),
limité au chemin /api/v1/auth. L'access token est renvoyé dans le JSON et gardé en mémoire côté front.
"""

import logging
import secrets

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status

from src.domain.user import (
    AccessTokenService,
    AuthPolicy,
    InvalidGoogleCredentialsError,
    PasswordHasher,
    RefreshTokenRepository,
    User,
    UserRepository,
)
from src.features.auth.schemas import (
    ChangePasswordIn,
    GoogleLoginIn,
    LoginIn,
    ProfileOut,
    RegisterIn,
    TokenOut,
)
from src.features.auth.use_cases import (
    AuthSession,
    change_password,
    login,
    login_with_google,
    logout,
    logout_all,
    refresh,
    register,
)
from src.infrastructure.config.settings import Settings, get_settings
from src.infrastructure.security.deps import (
    get_auth_policy,
    get_current_user,
    get_password_hasher,
    get_refresh_token_repo,
    get_token_service,
    get_user_repo,
)
from src.infrastructure.security.google_identity import verify_google_identity

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"
GOOGLE_NONCE_COOKIE = "google_auth_nonce"
logger = logging.getLogger(__name__)


def _set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        max_age=settings.refresh_token_ttl_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path=REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path=REFRESH_COOKIE_PATH,
    )


def _set_google_nonce_cookie(response: Response, nonce: str, settings: Settings) -> None:
    response.set_cookie(
        key=GOOGLE_NONCE_COOKIE,
        value=nonce,
        max_age=300,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


def _clear_google_nonce_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=GOOGLE_NONCE_COOKIE,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


def _respond(session: AuthSession, response: Response, settings: Settings) -> TokenOut:
    _set_refresh_cookie(response, session.refresh_token, settings)
    response.headers["Cache-Control"] = "no-store"

    return TokenOut(
        access_token=session.access_token.value,
        expires_in=session.access_token.expires_in,
        user=ProfileOut.model_validate(session.user),
    )


@router.get("/google/nonce", response_model=dict[str, str])
def google_nonce_endpoint(
    response: Response,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    if not settings.google_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google authentication is not configured",
        )

    nonce = secrets.token_urlsafe(32)
    _set_google_nonce_cookie(response, nonce, settings)
    response.headers["Cache-Control"] = "no-store"

    return {"nonce": nonce}


@router.post("/register", response_model=ProfileOut, status_code=status.HTTP_201_CREATED)
def register_endpoint(
    payload: RegisterIn,
    users: UserRepository = Depends(get_user_repo),
    hasher: PasswordHasher = Depends(get_password_hasher),
) -> User:
    return register(payload, users, hasher)


@router.post("/login", response_model=TokenOut)
def login_endpoint(
    payload: LoginIn,
    response: Response,
    users: UserRepository = Depends(get_user_repo),
    refresh_repo: RefreshTokenRepository = Depends(get_refresh_token_repo),
    hasher: PasswordHasher = Depends(get_password_hasher),
    tokens: AccessTokenService = Depends(get_token_service),
    policy: AuthPolicy = Depends(get_auth_policy),
    settings: Settings = Depends(get_settings),
) -> TokenOut:
    session = login(payload, users, refresh_repo, hasher, tokens, policy)

    return _respond(session, response, settings)


@router.post("/google", response_model=TokenOut)
def google_login_endpoint(
    payload: GoogleLoginIn,
    response: Response,
    users: UserRepository = Depends(get_user_repo),
    refresh_repo: RefreshTokenRepository = Depends(get_refresh_token_repo),
    hasher: PasswordHasher = Depends(get_password_hasher),
    tokens: AccessTokenService = Depends(get_token_service),
    policy: AuthPolicy = Depends(get_auth_policy),
    settings: Settings = Depends(get_settings),
    google_nonce: str | None = Cookie(default=None, alias=GOOGLE_NONCE_COOKIE),
) -> TokenOut:
    if not settings.google_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google authentication is not configured",
        )
    if not google_nonce:
        logger.warning("Google login rejected: nonce cookie was not sent by the browser")
        raise InvalidGoogleCredentialsError()

    identity = verify_google_identity(payload.credential, settings.google_client_id, google_nonce)
    session = login_with_google(identity, users, refresh_repo, hasher, tokens, policy)
    _clear_google_nonce_cookie(response, settings)

    return _respond(session, response, settings)


@router.post("/refresh", response_model=TokenOut)
def refresh_endpoint(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
    users: UserRepository = Depends(get_user_repo),
    refresh_repo: RefreshTokenRepository = Depends(get_refresh_token_repo),
    tokens: AccessTokenService = Depends(get_token_service),
    policy: AuthPolicy = Depends(get_auth_policy),
    settings: Settings = Depends(get_settings),
) -> TokenOut:
    session = refresh(refresh_token, users, refresh_repo, tokens, policy)

    return _respond(session, response, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_endpoint(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
    refresh_repo: RefreshTokenRepository = Depends(get_refresh_token_repo),
    settings: Settings = Depends(get_settings),
) -> None:
    logout(refresh_token, refresh_repo)
    _clear_refresh_cookie(response, settings)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all_endpoint(
    response: Response,
    user: User = Depends(get_current_user),
    refresh_repo: RefreshTokenRepository = Depends(get_refresh_token_repo),
    settings: Settings = Depends(get_settings),
) -> None:
    logout_all(user, refresh_repo)
    _clear_refresh_cookie(response, settings)


@router.get("/me", response_model=ProfileOut)
def me_endpoint(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/change-password", response_model=TokenOut)
def change_password_endpoint(
    payload: ChangePasswordIn,
    response: Response,
    user: User = Depends(get_current_user),
    users: UserRepository = Depends(get_user_repo),
    refresh_repo: RefreshTokenRepository = Depends(get_refresh_token_repo),
    hasher: PasswordHasher = Depends(get_password_hasher),
    tokens: AccessTokenService = Depends(get_token_service),
    policy: AuthPolicy = Depends(get_auth_policy),
    settings: Settings = Depends(get_settings),
) -> TokenOut:
    session = change_password(user, payload, users, refresh_repo, hasher, tokens, policy)

    return _respond(session, response, settings)
