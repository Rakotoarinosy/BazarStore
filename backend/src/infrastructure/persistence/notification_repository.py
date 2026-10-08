"""Notifications (T+4h) dérivées du journal d'événements des demandes.

Pas de table de notifications à alimenter : une notification est un événement (demande_events)
ou un retard (calculé), filtré selon le rôle du destinataire. Seul l'état « lu » est stocké
(table notification_reads : une ligne par utilisateur et par notification).
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.domain.demande.entities import Status
from src.domain.demande.events import EventType
from src.domain.demande.priority import NEW_MAX_AGE, WAITING_MAX_AGE, as_utc, late_since
from src.domain.notification import Notification
from src.domain.user import Role, User
from src.infrastructure.persistence.models import (
    DemandeEventModel,
    DemandeModel,
    NotificationReadModel,
)

EVENT_WINDOW = timedelta(days=14)
MAX_ITEMS = 200

# Noms de EventType notifiés selon le destinataire (ignorés s'ils n'existent pas dans l'enum).
_AUDIENCE_EVENTS = {
    "staff": ("CREATED", "ASSIGNED", "RESOLVED"),
    "citizen": ("ACCEPTED", "REJECTED", "ASSIGNED", "RESOLVED"),
    "agent": ("ASSIGNED",),
}
_TITLES = {
    "CREATED": "Nouvelle demande #{ref}",
    "ACCEPTED": "Demande #{ref} acceptée",
    "REJECTED": "Demande #{ref} rejetée",
    "ASSIGNED": "Demande #{ref} assignée",
    "RESOLVED": "Demande #{ref} résolue",
}
_LATE_TITLE = "Demande #{ref} en retard"


def _audience(user: User) -> str:
    if user.role in (Role.ADMIN, Role.MANAGER, Role.COMMERCIAL):
        return "staff"

    return "agent" if user.role is Role.AGENT else "citizen"


def _ref(demande_id: str) -> str:
    return demande_id[:8]


class SqlAlchemyNotificationRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_for(
        self, user: User, *, unread_only: bool, limit: int
    ) -> tuple[list[Notification], int]:
        if user.role is Role.AGENT and user.agent_id is None:
            return [], 0

        now = datetime.now(UTC)
        items = self._event_notifications(user, now) + self._late_notifications(user, now)
        items.sort(key=lambda item: item.created_at, reverse=True)
        items = items[:MAX_ITEMS]

        read_keys = self._read_keys(user.id, [item.key for item in items])
        items = [replace(item, is_read=item.key in read_keys) for item in items]
        unread_count = sum(1 for item in items if not item.is_read)
        if unread_only:
            items = [item for item in items if not item.is_read]

        return items[:limit], unread_count

    def mark_read(self, user_id: str, key: str) -> None:
        if self._db.get(NotificationReadModel, (user_id, key)) is not None:
            return
        self._db.add(NotificationReadModel(user_id=user_id, key=key))
        try:
            self._db.commit()
        except IntegrityError:  # marquée en parallèle : le résultat est le même
            self._db.rollback()

    def mark_all_read(self, user: User) -> int:
        unread, _ = self.list_for(user, unread_only=True, limit=MAX_ITEMS)
        for item in unread:
            self._db.add(NotificationReadModel(user_id=user.id, key=item.key))
        self._db.commit()

        return len(unread)

    # ─── sources ────────────────────────────────────────────────────

    def _event_notifications(self, user: User, now: datetime) -> list[Notification]:
        names_by_value = {
            EventType[name].value: name
            for name in _AUDIENCE_EVENTS[_audience(user)]
            if name in EventType.__members__
        }
        if not names_by_value:
            return []

        stmt = (
            select(
                DemandeEventModel.id,
                DemandeEventModel.type,
                DemandeEventModel.demande_id,
                DemandeEventModel.created_at,
                DemandeModel.title,
            )
            .join(DemandeModel, DemandeModel.id == DemandeEventModel.demande_id)
            .where(
                DemandeEventModel.type.in_(list(names_by_value)),
                DemandeEventModel.created_at >= now - EVENT_WINDOW,
                # On ne notifie pas quelqu'un de ses propres actions.
                or_(DemandeEventModel.actor_id.is_(None), DemandeEventModel.actor_id != user.id),
            )
            .order_by(DemandeEventModel.created_at.desc())
            .limit(MAX_ITEMS)
        )
        stmt = self._scoped(user, stmt)

        return [
            Notification(
                key=str(event_id),
                kind=names_by_value[event_type].lower(),
                title=_TITLES[names_by_value[event_type]].format(ref=_ref(demande_id)),
                message=title,
                demande_id=demande_id,
                created_at=as_utc(created_at),
            )
            for event_id, event_type, demande_id, created_at, title in self._db.execute(stmt)
        ]

    def _late_notifications(self, user: User, now: datetime) -> list[Notification]:
        overdue = or_(
            and_(
                DemandeModel.status == Status.NOUVEAU.value,
                DemandeModel.created_at <= now - NEW_MAX_AGE,
            ),
            and_(
                DemandeModel.status == Status.EN_COURS.value,
                DemandeModel.scheduled_at.is_not(None),
                DemandeModel.scheduled_at <= now,
            ),
            and_(
                DemandeModel.status == Status.EN_ATTENTE.value,
                DemandeModel.updated_at <= now - WAITING_MAX_AGE,
            ),
        )
        stmt = self._scoped(user, select(DemandeModel).where(overdue).limit(MAX_ITEMS))

        notifications = []
        for row in self._db.scalars(stmt).all():
            since = late_since(
                Status(row.status),
                created_at=row.created_at,
                scheduled_at=row.scheduled_at,
                updated_at=row.updated_at,
            )
            if since is None:
                continue
            notifications.append(
                Notification(
                    key=f"late:{row.id}",
                    kind="late",
                    title=_LATE_TITLE.format(ref=_ref(row.id)),
                    message=row.title,
                    demande_id=row.id,
                    created_at=since,
                )
            )

        return notifications

    # ─── utilitaires ────────────────────────────────────────────────

    @staticmethod
    def _scoped(user: User, stmt):
        if user.role is Role.CITIZEN:
            return stmt.where(DemandeModel.citizen_id == user.id)
        if user.role is Role.AGENT:
            return stmt.where(DemandeModel.agent_id == user.agent_id)

        return stmt

    def _read_keys(self, user_id: str, keys: list[str]) -> set[str]:
        if not keys:
            return set()
        stmt = select(NotificationReadModel.key).where(
            NotificationReadModel.user_id == user_id, NotificationReadModel.key.in_(keys)
        )

        return set(self._db.scalars(stmt).all())
