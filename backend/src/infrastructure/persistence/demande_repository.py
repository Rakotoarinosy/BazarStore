"""Implémentation SQLAlchemy de DemandeRepository. Le mapping Model ↔ Entity reste privé à ce fichier."""

from datetime import UTC, datetime

from sqlalchemy import ColumnElement, case, delete, func, or_, select
from sqlalchemy.orm import Session

from src.domain.demande import (
    Category,
    Demande,
    DemandeQuery,
    DemandeRepository,
    Priority,
    SortField,
    Status,
)
from src.domain.pagination import Page
from src.infrastructure.persistence.models import DemandeEventModel, DemandeModel

# Tri par priorité : on classe par rang (faible < moyenne < haute < critique), pas alphabétiquement.
_PRIORITY_RANK = case({p.value: i for i, p in enumerate(Priority)}, value=DemandeModel.priority)

_SORT_COLUMNS: dict[SortField, ColumnElement] = {
    SortField.CREATED_AT: DemandeModel.created_at,
    SortField.TITLE: DemandeModel.title,
    SortField.PRIORITY: _PRIORITY_RANK,
    SortField.STATUS: DemandeModel.status,
    SortField.CATEGORY: DemandeModel.category,
}


class SqlAlchemyDemandeRepository(DemandeRepository):
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, demande_id: str) -> Demande | None:
        model = self.db.get(DemandeModel, demande_id)

        return self._to_entity(model) if model else None

    def search(self, query: DemandeQuery) -> Page[Demande]:
        conditions = self._conditions(query)

        total = self.db.scalar(
            select(func.count()).select_from(DemandeModel).where(*conditions)
        )

        column = _SORT_COLUMNS[query.sort_by]
        direction = column.desc() if query.descending else column.asc()
        statement = (
            select(DemandeModel)
            .where(*conditions)
            .order_by(direction, DemandeModel.id)  # id : ordre stable entre deux pages
            .limit(query.page_size)
            .offset((query.page - 1) * query.page_size)
        )
        items = [self._to_entity(model) for model in self.db.scalars(statement)]

        return Page(items=items, total=total or 0, page=query.page, page_size=query.page_size)

    def add(self, demande: Demande) -> Demande:
        model = self._to_model(demande)
        self.db.add(model)
        self.db.commit()

        return self._to_entity(model)

    def update(self, demande: Demande) -> Demande:
        model = self.db.merge(self._to_model(demande))
        self.db.commit()

        return self._to_entity(model)

    def delete(self, demande_id: str) -> None:
        # Explicite : ne dépend pas de ON DELETE CASCADE (non appliqué par défaut sous SQLite).
        self.db.execute(delete(DemandeEventModel).where(DemandeEventModel.demande_id == demande_id))
        model = self.db.get(DemandeModel, demande_id)
        if model:
            self.db.delete(model)
        self.db.commit()

    # ─── Filtres ────────────────────────────────────────────────────

    def _conditions(self, query: DemandeQuery) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = []

        if query.search:
            pattern = f"%{_escape_like(query.search.strip())}%"
            conditions.append(
                or_(
                    DemandeModel.title.ilike(pattern, escape="\\"),
                    DemandeModel.description.ilike(pattern, escape="\\"),
                    DemandeModel.address.ilike(pattern, escape="\\"),
                )
            )
        if query.status:
            conditions.append(DemandeModel.status == query.status.value)
        if query.category:
            conditions.append(DemandeModel.category == query.category.value)
        if query.priority:
            conditions.append(DemandeModel.priority == query.priority.value)
        if query.agent_id:
            conditions.append(DemandeModel.agent_id == query.agent_id)
        if query.citizen_id:
            conditions.append(DemandeModel.citizen_id == query.citizen_id)

        return conditions

    # ─── Mapping ────────────────────────────────────────────────────

    def _to_entity(self, model: DemandeModel) -> Demande:
        return Demande(
            id=model.id,
            title=model.title,
            description=model.description,
            category=Category(model.category),
            priority=Priority(model.priority),
            status=Status(model.status),
            citizen_id=model.citizen_id,
            created_at=_aware(model.created_at),
            updated_at=_aware(model.updated_at),
            address=model.address,
            latitude=model.latitude,
            longitude=model.longitude,
            agent_id=model.agent_id,
            scheduled_at=_aware(model.scheduled_at) if model.scheduled_at else None,
        )

    def _to_model(self, demande: Demande) -> DemandeModel:
        return DemandeModel(
            id=demande.id,
            title=demande.title,
            description=demande.description,
            category=demande.category.value,
            priority=demande.priority.value,
            status=demande.status.value,
            citizen_id=demande.citizen_id,
            created_at=demande.created_at,
            updated_at=demande.updated_at,
            address=demande.address,
            latitude=demande.latitude,
            longitude=demande.longitude,
            agent_id=demande.agent_id,
            scheduled_at=demande.scheduled_at,
        )


def _aware(value: datetime) -> datetime:
    # SQLite ne conserve pas le fuseau : on garantit un datetime UTC « aware » partout.
    return value.replace(tzinfo=value.tzinfo or UTC)


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
