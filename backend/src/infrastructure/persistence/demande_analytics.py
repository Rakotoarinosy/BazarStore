"""Implémentation SQLAlchemy de DemandeAnalytics : agrégats du dashboard et points de carte."""

from collections import Counter
from datetime import UTC, datetime, timedelta, tzinfo
from enum import StrEnum

from sqlalchemy import ColumnElement, case, func, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from src.domain.demande.analytics import DailyCount, DashboardStats, DemandeAnalytics, MapPoint
from src.domain.demande.entities import Category, Priority, Status
from src.domain.demande.queries import DemandeQuery
from src.infrastructure.persistence.models import AgentModel, DemandeModel

_CLOSED = (Status.RESOLU.value, Status.REJETE.value)
_PRIORITY_RANK = case({p.value: i for i, p in enumerate(Priority)}, value=DemandeModel.priority)


def _aware(value: datetime) -> datetime:
    # SQLite ne conserve pas le fuseau : on garantit un datetime UTC « aware » partout.
    return value.replace(tzinfo=value.tzinfo or UTC)


class SqlAlchemyDemandeAnalytics(DemandeAnalytics):
    def __init__(self, db: Session) -> None:
        self.db = db

    # ─── Dashboard ──────────────────────────────────────────────────

    def dashboard_stats(self, now: datetime, tz: tzinfo, days: int) -> DashboardStats:
        by_status = self._count_by(DemandeModel.status, Status)
        by_category = self._count_by(DemandeModel.category, Category)
        by_priority = self._count_by(DemandeModel.priority, Priority)

        total = sum(by_status.values())
        resolved = by_status[Status.RESOLU.value]
        rejected = by_status[Status.REJETE.value]

        # « Aujourd'hui » et les jours du graphique suivent le fuseau de la municipalité, pas UTC.
        today_start_local = now.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        today_start = today_start_local.astimezone(UTC)
        tomorrow_start = (today_start_local + timedelta(days=1)).astimezone(UTC)

        interventions_today = self.db.scalar(
            select(func.count())
            .select_from(DemandeModel)
            .where(
                DemandeModel.agent_id.is_not(None),
                DemandeModel.scheduled_at >= today_start,
                DemandeModel.scheduled_at < tomorrow_start,
            )
        )

        return DashboardStats(
            total=total,
            open=total - resolved - rejected,
            in_progress=by_status[Status.EN_COURS.value],
            resolved=resolved,
            rejected=rejected,
            resolution_rate=round(resolved * 100 / total, 1) if total else 0.0,
            interventions_today=interventions_today or 0,
            by_status=by_status,
            by_category=by_category,
            by_priority=by_priority,
            daily=self._daily(today_start_local, tz, days),
        )

    def _count_by(self, column: InstrumentedAttribute[str], enum: type[StrEnum]) -> dict[str, int]:
        counts = {member.value: 0 for member in enum}  # zéros inclus : graphiques stables
        for value, count in self.db.execute(select(column, func.count()).group_by(column)):
            if value in counts:
                counts[value] = count

        return counts

    def _daily(self, today_start_local: datetime, tz: tzinfo, days: int) -> list[DailyCount]:
        first_day_local = today_start_local - timedelta(days=days - 1)
        window_start = first_day_local.astimezone(UTC)

        created = Counter(
            _aware(value).astimezone(tz).date()
            for value in self.db.scalars(
                select(DemandeModel.created_at).where(DemandeModel.created_at >= window_start)
            )
        )
        # Date de résolution approchée par la dernière modification d'une demande résolue (état final).
        resolved = Counter(
            _aware(value).astimezone(tz).date()
            for value in self.db.scalars(
                select(DemandeModel.updated_at).where(
                    DemandeModel.status == Status.RESOLU.value,
                    DemandeModel.updated_at >= window_start,
                )
            )
        )

        result = []
        for offset in range(days):
            day = (first_day_local + timedelta(days=offset)).date()
            result.append(DailyCount(day=day, created=created[day], resolved=resolved[day]))

        return result

    # ─── Carte ──────────────────────────────────────────────────────

    def map_points(self, query: DemandeQuery, *, active_only: bool, limit: int) -> list[MapPoint]:
        conditions: list[ColumnElement[bool]] = [
            DemandeModel.latitude.is_not(None),
            DemandeModel.longitude.is_not(None),
        ]
        if query.status:
            conditions.append(DemandeModel.status == query.status.value)
        elif active_only:
            conditions.append(DemandeModel.status.not_in(_CLOSED))
        if query.category:
            conditions.append(DemandeModel.category == query.category.value)
        if query.priority:
            conditions.append(DemandeModel.priority == query.priority.value)
        if query.agent_id:
            conditions.append(DemandeModel.agent_id == query.agent_id)
        if query.citizen_id:
            conditions.append(DemandeModel.citizen_id == query.citizen_id)

        statement = (
            select(
                DemandeModel.id,
                DemandeModel.title,
                DemandeModel.category,
                DemandeModel.priority,
                DemandeModel.status,
                DemandeModel.latitude,
                DemandeModel.longitude,
                DemandeModel.address,
                DemandeModel.created_at,
                DemandeModel.agent_id,
                AgentModel.name.label("agent_name"),
            )
            .join(AgentModel, DemandeModel.agent_id == AgentModel.id, isouter=True)
            .where(*conditions)
            # Si la limite tronque le résultat, on garde les plus urgentes puis les plus récentes.
            .order_by(_PRIORITY_RANK.desc(), DemandeModel.created_at.desc(), DemandeModel.id)
            .limit(limit)
        )

        return [
            MapPoint(
                id=row.id,
                title=row.title,
                category=Category(row.category),
                priority=Priority(row.priority),
                status=Status(row.status),
                latitude=row.latitude,
                longitude=row.longitude,
                created_at=_aware(row.created_at),
                address=row.address,
                agent_id=row.agent_id,
                agent_name=row.agent_name,
            )
            for row in self.db.execute(statement)
        ]
