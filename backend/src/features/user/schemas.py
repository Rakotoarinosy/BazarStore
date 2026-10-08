"""Schémas Pydantic de la gestion des utilisateurs (réservée à l'ADMIN)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.domain.user import Role
from src.shared.validation import Email, Password


class CreateUserIn(BaseModel):
    email: Email
    name: str = Field(min_length=1, max_length=255)
    password: Password
    role: Role = Role.CUSTOMER
    agent_id: str | None = None


class UpdateUserIn(BaseModel):
    """Mise à jour partielle. `agent_id: null` explicite détache la fiche agent."""

    email: Email | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    role: Role | None = None
    is_active: bool | None = None
    agent_id: str | None = None
    password: Password | None = None  # réinitialisation par un admin


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    name: str
    role: Role
    is_active: bool
    agent_id: str | None
    created_at: datetime
