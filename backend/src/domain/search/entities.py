"""Recherche globale (T+10h)."""

from dataclasses import dataclass
from enum import StrEnum


class SearchKind(StrEnum):
    DEMANDE = "demande"
    CITOYEN = "citoyen"
    AGENT = "agent"
    INTERVENTION = "intervention"


@dataclass(frozen=True, slots=True)
class SearchScope:
    """Périmètre imposé par le rôle : un citoyen ou un agent ne voit que ses demandes."""

    citizen_id: str | None = None
    agent_id: str | None = None
    directory: bool = False  # peut chercher parmi les citoyens et les agents


@dataclass(frozen=True, slots=True)
class SearchHit:
    kind: SearchKind
    id: str
    title: str
    subtitle: str
    demande_id: str | None = None
    agent_id: str | None = None
