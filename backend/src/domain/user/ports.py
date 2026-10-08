"""Ports : ce dont le domaine user a besoin côté sécurité. L'infrastructure les implémente."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


class PasswordHasher(ABC):
    @abstractmethod
    def hash(self, password: str) -> str: ...

    @abstractmethod
    def verify(self, password: str, password_hash: str) -> bool: ...

    @abstractmethod
    def needs_rehash(self, password_hash: str) -> bool: ...


@dataclass(frozen=True)
class AccessToken:
    value: str
    expires_in: int  # secondes


class AccessTokenService(ABC):
    @abstractmethod
    def create(self, user_id: str) -> AccessToken: ...

    @abstractmethod
    def decode(self, token: str) -> str:
        """Retourne l'id utilisateur ou lève InvalidTokenError."""


@dataclass(frozen=True)
class AuthPolicy:
    max_failed_attempts: int = 5
    lockout_minutes: int = 15
    refresh_ttl_days: int = 7
