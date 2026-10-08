"""Modification partielle d'une demande (hors statut et agent, gérés par les actions du workflow)."""

from dataclasses import replace
from datetime import UTC, datetime

from src.domain.demande import Demande, DemandeRepository
from src.domain.demande.events import DemandeEventRepository, EventType
from src.domain.user import User
from src.features.demande.schemas import UpdateDemandeIn
from src.features.demande.use_cases.read import get_demande
from src.features.demande.use_cases.recording import record_event


def update_demande(
    demande_id: str,
    dto: UpdateDemandeIn,
    repo: DemandeRepository,
    events: DemandeEventRepository,
    actor: User,
) -> Demande:
    demande = get_demande(demande_id, repo)
    requested = dto.model_dump(exclude_unset=True, exclude_none=True)
    # Seuls les champs réellement modifiés comptent : pas d'événement ni de updated_at pour rien.
    changes = {key: value for key, value in requested.items() if getattr(demande, key) != value}
    if not changes:
        return demande

    updated = repo.update(replace(demande, **changes, updated_at=datetime.now(UTC)))

    if "priority" in changes:
        record_event(
            events,
            demande_id,
            EventType.PRIORITY_CHANGED,
            actor,
            {"from": demande.priority.value, "to": changes["priority"].value},
        )
    other_fields = sorted(key for key in changes if key != "priority")
    if other_fields:
        record_event(events, demande_id, EventType.UPDATED, actor, {"fields": other_fields})

    return updated
