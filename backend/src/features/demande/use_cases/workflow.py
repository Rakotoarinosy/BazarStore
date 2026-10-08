"""Cycle de vie d'une demande : accepter, refuser, résoudre, attribuer à un agent.

Les transitions de statut autorisées sont définies dans domain/demande/rules.py.
Chaque action écrit un événement dans le journal (timeline, notifications).
"""

from dataclasses import replace
from datetime import UTC, datetime

from src.domain.demande import (
    AgentDirectory,
    AgentNotFoundError,
    Demande,
    DemandeRepository,
    Status,
    ensure_transition,
)
from src.domain.demande.events import DemandeEventRepository, EventType
from src.domain.user import User
from src.features.demande.schemas import AssignDemandeIn
from src.features.demande.use_cases.read import get_demande
from src.features.demande.use_cases.recording import record_event

_EVENT_BY_TARGET = {
    Status.EN_COURS: EventType.ACCEPTED,
    Status.REJETE: EventType.REJECTED,
    Status.RESOLU: EventType.RESOLVED,
}


def accept_demande(
    demande_id: str, repo: DemandeRepository, events: DemandeEventRepository, actor: User
) -> Demande:
    return _move_to(demande_id, Status.EN_COURS, repo, events, actor)


def reject_demande(
    demande_id: str, repo: DemandeRepository, events: DemandeEventRepository, actor: User
) -> Demande:
    return _move_to(demande_id, Status.REJETE, repo, events, actor)


def resolve_demande(
    demande_id: str, repo: DemandeRepository, events: DemandeEventRepository, actor: User
) -> Demande:
    return _move_to(demande_id, Status.RESOLU, repo, events, actor)


def assign_demande(
    demande_id: str,
    dto: AssignDemandeIn,
    repo: DemandeRepository,
    agents: AgentDirectory,
    events: DemandeEventRepository,
    actor: User,
) -> Demande:
    """Attribue la demande à un agent pour une date donnée ; elle passe (ou reste) « en cours »."""
    demande = get_demande(demande_id, repo)

    # Réattribuer une demande déjà en cours est permis ; les états finaux sont refusés.
    if demande.status != Status.EN_COURS:
        ensure_transition(demande.status, Status.EN_COURS)
    if not agents.exists(dto.agent_id):
        raise AgentNotFoundError(dto.agent_id)

    scheduled_at = _as_utc(dto.scheduled_at)
    updated = repo.update(
        replace(
            demande,
            status=Status.EN_COURS,
            agent_id=dto.agent_id,
            scheduled_at=scheduled_at,
            updated_at=datetime.now(UTC),
        )
    )
    record_event(
        events,
        demande_id,
        EventType.ASSIGNED,
        actor,
        {
            "agent_id": dto.agent_id,
            "previous_agent_id": demande.agent_id,
            "scheduled_at": scheduled_at.isoformat(),
            "from": demande.status.value,
            "to": Status.EN_COURS.value,
        },
    )

    return updated


def _move_to(
    demande_id: str,
    target: Status,
    repo: DemandeRepository,
    events: DemandeEventRepository,
    actor: User,
) -> Demande:
    demande = get_demande(demande_id, repo)
    ensure_transition(demande.status, target)

    updated = repo.update(replace(demande, status=target, updated_at=datetime.now(UTC)))
    record_event(
        events,
        demande_id,
        _EVENT_BY_TARGET[target],
        actor,
        {"from": demande.status.value, "to": target.value},
    )

    return updated


def _as_utc(value: datetime) -> datetime:
    # Une date sans fuseau (ex. envoyée par un sélecteur de date) est considérée comme UTC.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
