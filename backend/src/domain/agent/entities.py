"""Entités métier du domaine agent. Python pur : aucune dépendance à un framework."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class AgentStatus(StrEnum):
    AVAILABLE = "available"
    IN_INTERVENTION = "in_intervention"
    UNAVAILABLE = "unavailable"
    OFFLINE = "offline"


@dataclass
class Agent:
    id: str
    email: str
    name: str
    department: str
    created_at: datetime
    status: AgentStatus = AgentStatus.AVAILABLE
    is_active: bool = True
    # Calculé à la lecture (nombre de demandes attribuées à l'agent), jamais stocké.
    interventions: int = 0
