"""Annuaire d'agents SQL : dit aux demandes si un agent peut recevoir une attribution."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.demande import AgentDirectory
from src.infrastructure.persistence.models import AgentModel


class SqlAlchemyAgentDirectory(AgentDirectory):
    def __init__(self, db: Session) -> None:
        self.db = db

    def exists(self, agent_id: str) -> bool:
        # Un agent désactivé n'existe plus pour les attributions.
        is_active = self.db.scalar(select(AgentModel.is_active).where(AgentModel.id == agent_id))

        return bool(is_active)
