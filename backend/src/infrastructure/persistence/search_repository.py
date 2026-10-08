"""Recherche globale (T+10h) : demandes, citoyens, agents, interventions.

Une « intervention » est une demande attribuée à un agent avec une date planifiée.
La recherche est insensible à la casse et tolère l'absence d'accents (« eclairage » trouve
« Éclairage ») ; les jokers LIKE saisis par l'utilisateur sont échappés.
"""

import unicodedata

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from src.domain.search import SearchHit, SearchKind, SearchScope
from src.domain.user import Role
from src.infrastructure.persistence.models import (
    AgentModel,
    CitizenRequestModel,
    DemandeModel,
    UserModel,
)

_ESCAPE = "\\"
_MIN_REF_LENGTH = 4


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)

    return decomposed.encode("ascii", "ignore").decode().lower()


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _patterns(query: str) -> list[str]:
    base = query.strip()
    folded = _fold(base)
    # SQLite ne compare sans casse que l'ASCII (« é » ≠ « É ») : on ajoute les variantes courantes.
    # Sur PostgreSQL, ILIKE gère déjà tout cela.
    variants = {
        base,
        base.lower(),
        base.capitalize(),
        base.title(),
        folded,
        folded.replace(" ", "_"),  # « eclairage public » → slug de catégorie
    }

    return [f"%{_escape(variant)}%" for variant in variants if variant]


def _matches(columns: list, patterns: list[str]):
    return or_(*(column.ilike(pattern, escape=_ESCAPE) for column in columns for pattern in patterns))


def _ref(demande_id: str) -> str:
    return demande_id[:8]


class SqlAlchemySearchRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def search(self, query: str, scope: SearchScope, *, limit_per_kind: int) -> list[SearchHit]:
        patterns = _patterns(query)
        if not patterns:
            return []

        hits = self._demandes(query, patterns, scope, limit_per_kind)
        if scope.directory:
            hits += self._citizens(patterns, limit_per_kind)
            hits += self._agents(patterns, limit_per_kind)
        hits += self._interventions(patterns, scope, limit_per_kind)

        return hits

    def _demandes(
        self, query: str, patterns: list[str], scope: SearchScope, limit: int
    ) -> list[SearchHit]:
        model = CitizenRequestModel
        condition = _matches([model.title, model.description, model.location, model.category], patterns)
        ref = query.strip().lstrip("#")
        if len(ref) >= _MIN_REF_LENGTH:  # « #ab12cd34 » : recherche par début d'identifiant
            condition = or_(condition, model.id.ilike(f"{_escape(ref)}%", escape=_ESCAPE))

        stmt = self._scope_requests(select(model).where(condition), scope)
        rows = self._db.scalars(stmt.order_by(model.created_at.desc()).limit(limit)).all()

        return [
            SearchHit(
                kind=SearchKind.DEMANDE,
                id=row.id,
                title=f"#{_ref(row.id)} {row.title}",
                subtitle=f"{row.category} · {row.status}",
                demande_id=row.id,
                agent_id=row.assigned_agent_id,
            )
            for row in rows
        ]

    def _citizens(self, patterns: list[str], limit: int) -> list[SearchHit]:
        stmt = (
            select(UserModel)
            .where(
                UserModel.role == Role.CITIZEN.value,
                _matches([UserModel.name, UserModel.email], patterns),
            )
            .order_by(UserModel.name)
            .limit(limit)
        )

        return [
            SearchHit(kind=SearchKind.CITOYEN, id=row.id, title=row.name, subtitle=row.email)
            for row in self._db.scalars(stmt).all()
        ]

    def _agents(self, patterns: list[str], limit: int) -> list[SearchHit]:
        stmt = (
            select(AgentModel)
            .where(_matches([AgentModel.name, AgentModel.email, AgentModel.department], patterns))
            .order_by(AgentModel.name)
            .limit(limit)
        )

        return [
            SearchHit(
                kind=SearchKind.AGENT,
                id=row.id,
                title=row.name,
                subtitle=f"{row.department} · {row.status}",
                agent_id=row.id,
            )
            for row in self._db.scalars(stmt).all()
        ]

    def _interventions(
        self, patterns: list[str], scope: SearchScope, limit: int
    ) -> list[SearchHit]:
        # Reste sur la table legacy : seule `demandes` possède `scheduled_at`.
        stmt = (
            select(DemandeModel, AgentModel.name)
            .join(AgentModel, AgentModel.id == DemandeModel.agent_id)
            .where(
                DemandeModel.scheduled_at.is_not(None),
                _matches(
                    [
                        DemandeModel.title,
                        DemandeModel.description,
                        AgentModel.name,
                        AgentModel.department,
                    ],
                    patterns,
                ),
            )
        )
        stmt = self._scope_demandes(stmt, scope).order_by(DemandeModel.scheduled_at.desc()).limit(limit)

        return [
            SearchHit(
                kind=SearchKind.INTERVENTION,
                id=row.id,
                title=f"Intervention #{_ref(row.id)} — {row.title}",
                subtitle=f"{agent_name} · {row.scheduled_at:%d/%m/%Y %H:%M}",
                demande_id=row.id,
                agent_id=row.agent_id,
            )
            for row, agent_name in self._db.execute(stmt).all()
        ]

    @staticmethod
    def _scope_requests(stmt, scope: SearchScope):
        if scope.citizen_id is not None:
            stmt = stmt.where(CitizenRequestModel.citizen_id == scope.citizen_id)
        if scope.agent_id is not None:
            stmt = stmt.where(CitizenRequestModel.assigned_agent_id == scope.agent_id)

        return stmt

    @staticmethod
    def _scope_demandes(stmt, scope: SearchScope):
        if scope.citizen_id is not None:
            stmt = stmt.where(DemandeModel.citizen_id == scope.citizen_id)
        if scope.agent_id is not None:
            stmt = stmt.where(DemandeModel.agent_id == scope.agent_id)

        return stmt