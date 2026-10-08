"""Handlers d'exceptions globaux : traduisent les erreurs métier en réponses HTTP.

Le code HTTP est déduit du nom de l'exception, pour qu'un nouveau domaine n'ait rien à
enregistrer ici :
  *NotFoundError / *AlreadyExistsError / *ConflictError → 404 / 409 / 409
  *CredentialsError / *TokenError                       → 401
  *LockedError                                          → 429
  *DisabledError / *ForbiddenError                      → 403
  *UnavailableError (service externe, ex. IA)           → 503
  autre DomainError                                     → 400
Tout autre exception non gérée → 500 (détail loggé, jamais renvoyé au client).
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from src.domain.errors import DomainError

logger = logging.getLogger(__name__)

_STATUS_BY_SUFFIX = {
    "NotFoundError": status.HTTP_404_NOT_FOUND,
    "AlreadyExistsError": status.HTTP_409_CONFLICT,
    "ConflictError": status.HTTP_409_CONFLICT,
    "CredentialsError": status.HTTP_401_UNAUTHORIZED,
    "TokenError": status.HTTP_401_UNAUTHORIZED,
    "LockedError": status.HTTP_429_TOO_MANY_REQUESTS,
    "DisabledError": status.HTTP_403_FORBIDDEN,
    "ForbiddenError": status.HTTP_403_FORBIDDEN,
    "UnavailableError": status.HTTP_503_SERVICE_UNAVAILABLE,
}


def status_code_for(error: DomainError) -> int:
    name = type(error).__name__
    for suffix, code in _STATUS_BY_SUFFIX.items():
        if name.endswith(suffix):
            return code

    return status.HTTP_400_BAD_REQUEST


async def domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    code = status_code_for(exc)
    logger.info("domain error", extra={"error": type(exc).__name__, "path": request.url.path})
    headers = {"WWW-Authenticate": "Bearer"} if code == status.HTTP_401_UNAUTHORIZED else None

    return JSONResponse(
        status_code=code,
        content={"error": type(exc).__name__, "detail": exc.message},
        headers=headers,
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error", extra={"path": request.url.path})

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "InternalServerError", "detail": "An unexpected error occurred"},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, domain_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
