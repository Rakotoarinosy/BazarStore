"""Enregistrement des événements d'une demande.

Point d'accroche unique : toute action métier passe par `record_event`. C'est ici que se brancheront
les notifications (T+4h) et la détection d'incident (T+22h), sans retoucher les use cases.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from src.domain.demande.events import DemandeEvent, DemandeEventRepository, EventType
from src.domain.user import User


def record_event(
    events: DemandeEventRepository,
    demande_id: str,
    type_: EventType,
    actor: User | None,
    payload: dict[str, Any] | None = None,
) -> DemandeEvent:
    """`payload` doit être sérialisable en JSON (str, nombres, bool, listes, dicts) : pas de datetime brut."""
    return events.add(
        DemandeEvent(
            id=str(uuid.uuid4()),
            demande_id=demande_id,
            type=type_,
            created_at=datetime.now(UTC),
            actor_id=actor.id if actor else None,
            actor_name=actor.name if actor else None,
            payload=payload or {},
        )
    )
