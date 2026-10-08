"""Schémas Pydantic du domaine agent : entrées (In) validées par l'API, sortie (Out) renvoyée au client."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from src.domain.agent import AgentStatus


class CreateAgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    department: str = Field(min_length=1, max_length=100)
    status: AgentStatus = AgentStatus.AVAILABLE


class UpdateAgentIn(BaseModel):
    """Mise à jour partielle : seuls les champs fournis sont modifiés."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
    department: str | None = Field(default=None, min_length=1, max_length=100)
    status: AgentStatus | None = None


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    email: str
    department: str
    status: AgentStatus
    is_active: bool
    interventions: int
    created_at: datetime
