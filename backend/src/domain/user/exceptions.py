"""Exceptions métier du domaine user.

Convention (voir shared/errors/handlers.py) : le suffixe du nom fixe le code HTTP.
  *NotFoundError        → 404
  *AlreadyExistsError   → 409
  *ConflictError        → 409
  *CredentialsError     → 401
  *TokenError           → 401
  *LockedError          → 429
  *DisabledError        → 403
  *ForbiddenError       → 403
  autre DomainError     → 400
"""

from src.domain.errors import DomainError


class UserNotFoundError(DomainError):
    def __init__(self, user_id: str) -> None:
        super().__init__(f"User '{user_id}' not found")


class UserAlreadyExistsError(DomainError):
    def __init__(self, email: str) -> None:
        super().__init__(f"A user with email '{email}' already exists")


class UserConflictError(DomainError):
    def __init__(self) -> None:
        super().__init__("Email or agent link conflicts with existing data")


class InvalidCredentialsError(DomainError):
    """Message volontairement unique : ne révèle ni l'existence du compte ni son état."""

    def __init__(self) -> None:
        super().__init__("Invalid email or password")


class InvalidGoogleCredentialsError(DomainError):
    def __init__(self) -> None:
        super().__init__("Invalid Google identity token")


class GoogleAuthUnavailableError(DomainError):
    def __init__(self) -> None:
        super().__init__("Google authentication is temporarily unavailable")


class InvalidTokenError(DomainError):
    def __init__(self) -> None:
        super().__init__("Invalid or expired token")


class AccountLockedError(DomainError):
    def __init__(self) -> None:
        super().__init__("Too many failed attempts, try again later")


class AccountDisabledError(DomainError):
    def __init__(self) -> None:
        super().__init__("This account is disabled")


class ForbiddenError(DomainError):
    def __init__(self, message: str = "You do not have permission to perform this action") -> None:
        super().__init__(message)


class IncorrectPasswordError(DomainError):
    def __init__(self) -> None:
        super().__init__("Current password is incorrect")


class PasswordReuseError(DomainError):
    def __init__(self) -> None:
        super().__init__("New password must be different from the current one")


class LastAdminError(DomainError):
    def __init__(self) -> None:
        super().__init__("At least one active administrator must remain")
