"""Implémentation SQLAlchemy de AgentRepository. Le mapping Model ↔ Entity reste privé à ce fichier."""

from datetime import UTC

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from src.domain.agent import Agent, AgentQuery, AgentRepository, AgentStatus
from src.infrastructure.persistence.models import AgentModel, CitizenRequestModel


class SqlAlchemyAgentRepository(AgentRepository):
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, agent_id: str) -> Agent | None:
        model = self.db.get(AgentModel, agent_id)

        return self._to_entities([model])[0] if model else None

    def get_by_email(self, email: str) -> Agent | None:
        model = self.db.scalar(select(AgentModel).where(AgentModel.email == email))

        return self._to_entities([model])[0] if model else None

    def search(self, query: AgentQuery) -> list[Agent]:
        statement = select(AgentModel).order_by(AgentModel.name, AgentModel.id)

        if query.search:
            pattern = f"%{_escape_like(query.search.strip())}%"
            statement = statement.where(
                or_(
                    AgentModel.name.ilike(pattern, escape="\\"),
                    AgentModel.email.ilike(pattern, escape="\\"),
                )
            )
        if query.department:
            statement = statement.where(
                func.lower(AgentModel.department) == query.department.strip().lower()
            )
        if query.status:
            statement = statement.where(AgentModel.status == query.status.value)
        if query.is_active is not None:
            statement = statement.where(AgentModel.is_active == query.is_active)

        return self._to_entities(list(self.db.scalars(statement)))

    def add(self, agent: Agent) -> Agent:
        model = self._to_model(agent)
        self.db.add(model)
        self.db.commit()

        return self._to_entities([model])[0]

    def update(self, agent: Agent) -> Agent:
        model = self.db.merge(self._to_model(agent))
        self.db.commit()

        return self._to_entities([model])[0]

    # ─── Interventions (demandes citoyennes attribuées) ─────────────

    def _count_interventions(self, agent_ids: list[str]) -> dict[str, int]:
        if not agent_ids:
            return {}
        rows = self.db.execute(
            select(CitizenRequestModel.assigned_agent_id, func.count())
            .where(CitizenRequestModel.assigned_agent_id.in_(agent_ids))
            .group_by(CitizenRequestModel.assigned_agent_id)
        )

        return {agent_id: count for agent_id, count in rows}

    # ─── Mapping ────────────────────────────────────────────────────

    def _to_entities(self, models: list[AgentModel]) -> list[Agent]:
        counts = self._count_interventions([model.id for model in models])

        return [self._to_entity(model, counts.get(model.id, 0)) for model in models]

    def _to_entity(self, model: AgentModel, interventions: int) -> Agent:
        return Agent(
            id=model.id,
            email=model.email,
            name=model.name,
            department=model.department,
            # SQLite ne conserve pas le fuseau : on garantit un datetime UTC « aware » partout.
            created_at=model.created_at.replace(tzinfo=model.created_at.tzinfo or UTC),
            status=AgentStatus(model.status),
            is_active=model.is_active,
            interventions=interventions,
        )

    def _to_model(self, agent: Agent) -> AgentModel:
        return AgentModel(
            id=agent.id,
            email=agent.email,
            name=agent.name,
            department=agent.department,
            status=agent.status.value,
            is_active=agent.is_active,
            created_at=agent.created_at,
        )


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
