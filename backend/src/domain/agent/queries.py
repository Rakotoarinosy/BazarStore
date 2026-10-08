"""Paramètres de recherche d'une liste d'agents."""

from dataclasses import dataclass

from src.domain.agent.entities import AgentStatus


@dataclass(frozen=True)
class AgentQuery:
    search: str | None = None
    department: str | None = None
    status: AgentStatus | None = None
    is_active: bool | None = None  # None = actifs et désactivés
