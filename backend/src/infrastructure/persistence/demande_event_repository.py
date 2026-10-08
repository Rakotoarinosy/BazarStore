"""Implémentation SQLAlchemy de DemandeEventRepository."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.demande.events import DemandeEvent, DemandeEventRepository, EventType
from src.infrastructure.persistence.models import DemandeEventModel


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=value.tzinfo or UTC)


class SqlAlchemyDemandeEventRepository(DemandeEventRepository):
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, event: DemandeEvent) -> DemandeEvent:
        self.db.add(
            DemandeEventModel(
                id=event.id,
                demande_id=event.demande_id,
                type=event.type.value,
                actor_id=event.actor_id,
                actor_name=event.actor_name,
                payload=event.payload,
                created_at=event.created_at,
            )
        )
        self.db.commit()

        return event

    def list_for_demande(self, demande_id: str) -> list[DemandeEvent]:
        models = self.db.scalars(
            select(DemandeEventModel)
            .where(DemandeEventModel.demande_id == demande_id)
            .order_by(DemandeEventModel.created_at, DemandeEventModel.id)
        )

        return [
            DemandeEvent(
                id=m.id,
                demande_id=m.demande_id,
                type=EventType(m.type),
                created_at=_aware(m.created_at),
                actor_id=m.actor_id,
                actor_name=m.actor_name,
                payload=dict(m.payload or {}),
            )
            for m in models
        ]
