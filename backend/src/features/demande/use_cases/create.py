"""Envoi (création) d'une demande citoyenne."""

import uuid
from datetime import UTC, datetime

from src.domain.demande import Demande, DemandeRepository, Status
from src.domain.demande.events import DemandeEventRepository, EventType
from src.domain.demande.exceptions import CitizenRequiredError
from src.domain.user import User, UserNotFoundError, UserRepository
from src.features.demande.schemas import CreateDemandeIn
from src.features.demande.use_cases.recording import record_event


def create_demande(
    dto: CreateDemandeIn,
    repo: DemandeRepository,
    users: UserRepository,
    events: DemandeEventRepository,
    actor: User,
) -> Demande:
    if dto.citizen_id is None:
        raise CitizenRequiredError()
    if users.get_by_id(dto.citizen_id) is None:
        raise UserNotFoundError(dto.citizen_id)

    now = datetime.now(UTC)
    demande = Demande(
        id=str(uuid.uuid4()),
        title=dto.title,
        description=dto.description,
        category=dto.category,
        priority=dto.priority,
        status=Status.NOUVEAU,
        citizen_id=dto.citizen_id,
        created_at=now,
        updated_at=now,
        address=dto.address,
        latitude=dto.latitude,
        longitude=dto.longitude,
    )
    created = repo.add(demande)
    record_event(
        events,
        created.id,
        EventType.CREATED,
        actor,
        {
            "title": created.title,
            "category": created.category.value,
            "priority": created.priority.value,
        },
    )

    return created
