"""Implémentation SQLAlchemy du repository de demandes citoyennes."""

from collections import defaultdict
from datetime import UTC, date, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from src.domain.citizen_request import (
    CitizenRequest,
    CitizenRequestRepository,
    DashboardAggregates,
    RequestCategory,
    RequestPriority,
    RequestSortBy,
    RequestStatus,
    SortOrder,
)
from src.infrastructure.persistence.models import CitizenRequestModel


class SqlAlchemyCitizenRequestRepository(CitizenRequestRepository):
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, request_id: str) -> CitizenRequest | None:
        model = self.db.get(CitizenRequestModel, request_id)

        return self._to_entity(model) if model else None

    def list_page(
        self,
        *,
        page: int,
        page_size: int,
        search: str | None,
        category: RequestCategory | None,
        priority: RequestPriority | None,
        status: RequestStatus | None,
        sort_by: RequestSortBy,
        sort_order: SortOrder,
    ) -> tuple[list[CitizenRequest], int]:
        filters = []
        if search is not None:
            search_pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    CitizenRequestModel.title.ilike(search_pattern),
                    CitizenRequestModel.description.ilike(search_pattern),
                    CitizenRequestModel.location.ilike(search_pattern),
                )
            )
        if category is not None:
            filters.append(CitizenRequestModel.category == category.value)
        if priority is not None:
            filters.append(CitizenRequestModel.priority == priority.value)
        if status is not None:
            filters.append(CitizenRequestModel.status == status.value)

        total = self.db.scalar(
            select(func.count()).select_from(CitizenRequestModel).where(*filters)
        )
        sort_column = getattr(CitizenRequestModel, sort_by.value)
        order_expression = sort_column.asc() if sort_order is SortOrder.ASC else sort_column.desc()
        models = self.db.scalars(
            select(CitizenRequestModel)
            .where(*filters)
            .order_by(order_expression, CitizenRequestModel.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()

        return [self._to_entity(model) for model in models], total or 0

    def list_by_agent(self, agent_id: str) -> list[CitizenRequest]:
        models = self.db.scalars(
            select(CitizenRequestModel)
            .where(CitizenRequestModel.assigned_agent_id == agent_id)
            .order_by(CitizenRequestModel.created_at.desc(), CitizenRequestModel.id.asc())
        )

        return [self._to_entity(model) for model in models]

    def add(self, request: CitizenRequest) -> CitizenRequest:
        model = self._to_model(request)
        self.db.add(model)
        self.db.commit()

        return self._to_entity(model)

    def update(self, request: CitizenRequest) -> CitizenRequest:
        model = self.db.merge(self._to_model(request))
        self.db.commit()

        return self._to_entity(model)

    def delete(self, request_id: str) -> None:
        model = self.db.get(CitizenRequestModel, request_id)
        if model is not None:
            self.db.delete(model)
            self.db.commit()

    def dashboard_aggregates(
        self,
        *,
        trend_start: datetime,
        trend_end: datetime,
        today_start: datetime,
        today_end: datetime,
    ) -> DashboardAggregates:
        status_rows = self.db.execute(
            select(CitizenRequestModel.status, func.count()).group_by(CitizenRequestModel.status)
        )
        by_status = {RequestStatus(value): count for value, count in status_rows}

        category_rows = self.db.execute(
            select(CitizenRequestModel.category, func.count()).group_by(
                CitizenRequestModel.category
            )
        )
        by_category = {RequestCategory(value): count for value, count in category_rows}

        resolved_today = self.db.scalar(
            select(func.count())
            .select_from(CitizenRequestModel)
            .where(
                CitizenRequestModel.status == RequestStatus.RESOLVED.value,
                CitizenRequestModel.resolved_at >= today_start,
                CitizenRequestModel.resolved_at < today_end,
            )
        )

        day_expression = func.date(CitizenRequestModel.created_at)
        daily_rows = self.db.execute(
            select(day_expression, func.count())
            .where(
                CitizenRequestModel.created_at >= trend_start,
                CitizenRequestModel.created_at < trend_end,
            )
            .group_by(day_expression)
        )
        by_day: dict[date, int] = defaultdict(int)
        for raw_day, count in daily_rows:
            day = date.fromisoformat(raw_day) if isinstance(raw_day, str) else raw_day
            by_day[day] = count

        return DashboardAggregates(
            by_status=by_status,
            by_category=by_category,
            resolved_today=resolved_today or 0,
            by_day=dict(by_day),
        )

    def _to_entity(self, model: CitizenRequestModel) -> CitizenRequest:
        return CitizenRequest(
            id=model.id,
            title=model.title,
            description=model.description,
            category=RequestCategory(model.category),
            priority=RequestPriority(model.priority),
            status=RequestStatus(model.status),
            citizen_id=model.citizen_id,
            created_at=self._as_utc(model.created_at),
            location=model.location,
            latitude=model.latitude,
            longitude=model.longitude,
            assigned_agent_id=model.assigned_agent_id,
            resolved_at=self._as_utc(model.resolved_at) if model.resolved_at else None,
        )

    def _to_model(self, request: CitizenRequest) -> CitizenRequestModel:
        return CitizenRequestModel(
            id=request.id,
            title=request.title,
            description=request.description,
            category=request.category.value,
            priority=request.priority.value,
            status=request.status.value,
            citizen_id=request.citizen_id,
            created_at=request.created_at,
            location=request.location,
            latitude=request.latitude,
            longitude=request.longitude,
            assigned_agent_id=request.assigned_agent_id,
            resolved_at=request.resolved_at,
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
