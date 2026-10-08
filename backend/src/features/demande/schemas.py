"""Schémas Pydantic du domaine demande : entrées (In) validées par l'API, sorties (Out) renvoyées au client."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.domain.demande import Category, Priority, Status
from src.domain.demande.events import EventType


class CreateDemandeIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    category: Category
    priority: Priority = Priority.MOYENNE
    # Ignoré pour un CITIZEN (forcé à son propre id) ; obligatoire pour un MANAGER/ADMIN qui crée pour un citoyen.
    citizen_id: str | None = Field(default=None, min_length=1, max_length=36)
    address: str | None = Field(default=None, max_length=500)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class UpdateDemandeIn(BaseModel):
    """Mise à jour partielle : seuls les champs fournis sont modifiés. Le statut passe par les actions dédiées."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1)
    category: Category | None = None
    priority: Priority | None = None
    address: str | None = Field(default=None, max_length=500)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class AssignDemandeIn(BaseModel):
    agent_id: str = Field(min_length=1, max_length=36)
    scheduled_at: datetime


class DemandeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: str
    category: Category
    priority: Priority
    status: Status
    citizen_id: str
    created_at: datetime
    updated_at: datetime
    address: str | None
    latitude: float | None
    longitude: float | None
    agent_id: str | None
    scheduled_at: datetime | None


class DemandePageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[DemandeOut]
    total: int
    page: int
    page_size: int
    pages: int


class EventOut(BaseModel):
    """Entrée de timeline. Pour `assigned`, le payload contient aussi `agent_name`."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    type: EventType
    actor_id: str | None
    actor_name: str | None
    payload: dict[str, Any]
    created_at: datetime


class MapPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    category: Category
    priority: Priority
    status: Status
    latitude: float
    longitude: float
    address: str | None
    agent_id: str | None
    agent_name: str | None
    created_at: datetime
