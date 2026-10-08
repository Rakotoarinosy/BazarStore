"""Journal d'événements d'une demande : source unique pour la timeline, les notifications et le mode incident.

Chaque action métier sur une demande écrit un événement (voir features/demande/use_cases/recording.py).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    PRIORITY_CHANGED = "priority_changed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ASSIGNED = "assigned"
    RESOLVED = "resolved"
    # Réservés pour l'étape « interventions » (démarrage / fin d'intervention).
    INTERVENTION_STARTED = "intervention_started"
    INTERVENTION_FINISHED = "intervention_finished"


@dataclass
class DemandeEvent:
    id: str
    demande_id: str
    type: EventType
    created_at: datetime
    # Instantané du nom au moment de l'action : l'historique reste lisible si l'utilisateur est renommé.
    actor_id: str | None = None
    actor_name: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


class DemandeEventRepository(ABC):
    @abstractmethod
    def add(self, event: DemandeEvent) -> DemandeEvent: ...

    @abstractmethod
    def list_for_demande(self, demande_id: str) -> list[DemandeEvent]:
        """Événements d'une demande, du plus ancien au plus récent."""
