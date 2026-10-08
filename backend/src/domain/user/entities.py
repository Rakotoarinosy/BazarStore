"""Entités métier du domaine user. Python pur : aucune dépendance à un framework."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    COMMERCIAL = "commercial"
    # Ancien nom conservé pour que les comptes existants gardent leurs accès.
    MANAGER = "manager"
    AGENT = "agent"
    CUSTOMER = "customer"
    CITIZEN = "citizen"  # Legacy value retained for accounts in the historical database.


@dataclass
class User:
    id: str
    email: str
    name: str
    created_at: datetime
    password_hash: str
    role: Role = Role.CUSTOMER
    is_active: bool = True
    # Pour un utilisateur AGENT : lien vers sa fiche agent (« Mes interventions »).
    agent_id: str | None = None
    google_subject: str | None = None
    failed_login_attempts: int = 0
    locked_until: datetime | None = None

    def is_locked(self, now: datetime) -> bool:
        return self.locked_until is not None and self.locked_until > now


@dataclass(frozen=True)
class GoogleIdentity:
    subject: str
    email: str
    name: str


@dataclass
class RefreshToken:
    """Refresh token stocké sous forme de hash. Une « famille » = une session de connexion."""

    id: str
    user_id: str
    family_id: str
    token_hash: str
    expires_at: datetime
    created_at: datetime
    revoked_at: datetime | None = None
