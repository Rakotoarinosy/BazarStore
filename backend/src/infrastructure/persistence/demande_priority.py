"""Priorisation automatique (T+8h) : recalcul des scores et file triée par score décroissant."""

from datetime import UTC, datetime

from sqlalchemy import and_, case, func, select, update
from sqlalchemy.orm import Session

from src.domain.demande.entities import Status
from src.domain.demande.events import EventType
from src.domain.demande.priority import (
    OPEN_STATUSES,
    PriorityItem,
    compute_score,
    is_late,
    level_for,
)
from src.infrastructure.persistence.models import DemandeEventModel, DemandeModel

_OPEN_VALUES = [status.value for status in OPEN_STATUSES]


class SqlAlchemyPriorityRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def refresh_scores(self, *, demande_id: str | None = None, now: datetime | None = None) -> int:
        now = now or datetime.now(UTC)
        stmt = select(DemandeModel).where(DemandeModel.status.in_(_OPEN_VALUES))
        if demande_id is not None:
            stmt = stmt.where(DemandeModel.id == demande_id)

        level_changes = 0
        for row in self._db.scalars(stmt).all():
            total = compute_score(
                urgency=row.urgency,
                affected_citizens=row.affected_citizens,
                created_at=row.created_at,
                category=row.category,
                now=now,
            ).total
            level = level_for(total).value
            if total == row.priority_score and level == row.priority:
                continue

            if level != row.priority:
                level_changes += 1
                self._db.add(
                    DemandeEventModel(
                        demande_id=row.id,
                        type=EventType.PRIORITY_CHANGED.value,
                        actor_id=None,
                        actor_name="Système",
                        payload={"from": row.priority, "to": level, "score": total, "auto": True},
                    )
                )
            # updated_at=lui-même : un recalcul automatique ne doit pas compter comme une modification.
            self._db.execute(
                update(DemandeModel)
                .where(DemandeModel.id == row.id)
                .values(priority=level, priority_score=total, updated_at=DemandeModel.updated_at)
                .execution_options(synchronize_session=False)
            )

        self._db.commit()

        return level_changes

    def update_inputs(
        self,
        demande_id: str,
        *,
        urgency: int | None,
        affected_citizens: int | None,
        actor_id: str,
        actor_name: str,
    ) -> None:
        values: dict[str, int] = {}
        if urgency is not None:
            values["urgency"] = urgency
        if affected_citizens is not None:
            values["affected_citizens"] = affected_citizens

        if values:
            self._db.execute(
                update(DemandeModel)
                .where(DemandeModel.id == demande_id)
                .values(**values)
                .execution_options(synchronize_session=False)
            )
            self._db.add(
                DemandeEventModel(
                    demande_id=demande_id,
                    type=EventType.UPDATED.value,
                    actor_id=actor_id,
                    actor_name=actor_name,
                    payload={"fields": sorted(values)},
                )
            )
            self._db.commit()

        self.refresh_scores(demande_id=demande_id)

    def get_item(self, demande_id: str) -> PriorityItem | None:
        self._db.expire_all()
        row = self._db.get(DemandeModel, demande_id)

        return self._to_item(row, datetime.now(UTC)) if row else None

    def ranked(
        self,
        *,
        citizen_id: str | None,
        agent_id: str | None,
        status: Status | None,
        include_closed: bool,
        page: int,
        page_size: int,
    ) -> tuple[list[PriorityItem], int]:
        conditions = []
        if citizen_id is not None:
            conditions.append(DemandeModel.citizen_id == citizen_id)
        if agent_id is not None:
            conditions.append(DemandeModel.agent_id == agent_id)
        if status is not None:
            conditions.append(DemandeModel.status == status.value)
        elif not include_closed:
            conditions.append(DemandeModel.status.in_(_OPEN_VALUES))
        where = and_(*conditions) if conditions else None

        count_stmt = select(func.count()).select_from(DemandeModel)
        rows_stmt = select(DemandeModel)
        if where is not None:
            count_stmt = count_stmt.where(where)
            rows_stmt = rows_stmt.where(where)

        open_first = case((DemandeModel.status.in_(_OPEN_VALUES), 0), else_=1)
        rows = self._db.scalars(
            rows_stmt.order_by(
                open_first, DemandeModel.priority_score.desc(), DemandeModel.created_at.asc()
            )
            .limit(page_size)
            .offset((page - 1) * page_size)
        ).all()
        now = datetime.now(UTC)

        return [self._to_item(row, now) for row in rows], self._db.scalar(count_stmt) or 0

    @staticmethod
    def _to_item(row: DemandeModel, now: datetime) -> PriorityItem:
        return PriorityItem(
            id=row.id,
            title=row.title,
            category=row.category,
            status=row.status,
            priority=row.priority,
            priority_score=row.priority_score,
            urgency=row.urgency,
            affected_citizens=row.affected_citizens,
            created_at=row.created_at,
            agent_id=row.agent_id,
            address=row.address,
            is_late=is_late(
                Status(row.status),
                created_at=row.created_at,
                scheduled_at=row.scheduled_at,
                updated_at=row.updated_at,
                now=now,
            ),
        )
