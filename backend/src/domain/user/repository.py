"""Interfaces des repositories user : le domaine décrit ce dont il a besoin, l'infrastructure l'implémente."""

from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.user.entities import RefreshToken, Role, User


class UserRepository(ABC):
    @abstractmethod
    def get_by_id(self, user_id: str) -> User | None: ...

    @abstractmethod
    def get_by_email(self, email: str) -> User | None: ...

    @abstractmethod
    def count_active_by_role(self, role: Role) -> int: ...

    @abstractmethod
    def add(self, user: User) -> User: ...

    @abstractmethod
    def update(self, user: User) -> User: ...

    @abstractmethod
    def delete(self, user_id: str) -> None: ...

    # Déclaré en dernier : le nom `list` masque le builtin dans le corps de la classe.
    @abstractmethod
    def list(self) -> list[User]: ...


class RefreshTokenRepository(ABC):
    @abstractmethod
    def add(self, token: RefreshToken) -> RefreshToken: ...

    @abstractmethod
    def get_by_hash(self, token_hash: str) -> RefreshToken | None: ...

    @abstractmethod
    def revoke(self, token_id: str, now: datetime) -> bool:
        """Révoque un token. Retourne False s'il était déjà révoqué (course / réutilisation)."""

    @abstractmethod
    def revoke_family(self, family_id: str, now: datetime) -> None: ...

    @abstractmethod
    def revoke_all_for_user(self, user_id: str, now: datetime) -> None: ...

    @abstractmethod
    def delete_expired(self, now: datetime) -> None: ...
