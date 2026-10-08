"""Entités métier du domaine demande. Python pur : aucune dépendance à un framework."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Category(StrEnum):
    ECLAIRAGE_PUBLIC = "eclairage_public"
    VOIRIE = "voirie"
    EAU = "eau"
    DECHETS = "dechets"
    SECURITE = "securite"
    ESPACES_VERTS = "espaces_verts"
    AUTRE = "autre"


class Priority(StrEnum):
    # L'ordre de déclaration sert au tri par priorité (du moins au plus urgent).
    FAIBLE = "faible"
    MOYENNE = "moyenne"
    HAUTE = "haute"
    CRITIQUE = "critique"


class Status(StrEnum):
    NOUVEAU = "nouveau"
    EN_COURS = "en_cours"
    EN_ATTENTE = "en_attente"
    RESOLU = "resolu"
    REJETE = "rejete"


@dataclass
class Demande:
    id: str
    title: str
    description: str
    category: Category
    priority: Priority
    status: Status
    citizen_id: str
    created_at: datetime
    updated_at: datetime
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    agent_id: str | None = None
    scheduled_at: datetime | None = None
