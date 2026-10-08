"""Recherche globale dans le header (T+10h).

  GET /search?q=éclairage&limit=5   → résultats mélangés, avec un champ « kind » pour les regrouper.

Périmètre selon le rôle : ADMIN / MANAGER cherchent partout ; un CITIZEN ou un AGENT ne trouve
que ses propres demandes (et interventions), jamais les autres citoyens ni l'annuaire des agents.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.domain.search import SearchRepository, SearchScope
from src.domain.user import ForbiddenError, Role, User
from src.features.search.schemas import SearchHitOut, SearchOut
from src.infrastructure.persistence.database import get_db
from src.infrastructure.persistence.search_repository import SqlAlchemySearchRepository
from src.infrastructure.security.deps import get_current_user

router = APIRouter(prefix="/search", tags=["search"])


def get_search_repo(db: Session = Depends(get_db)) -> SearchRepository:
    return SqlAlchemySearchRepository(db)


def _scope_for(user: User) -> SearchScope:
    if user.role is Role.CITIZEN:
        return SearchScope(citizen_id=user.id)
    if user.role is Role.AGENT:
        if user.agent_id is None:
            raise ForbiddenError("This account is not linked to an agent profile")
        return SearchScope(agent_id=user.agent_id)

    return SearchScope(directory=True)


@router.get("", response_model=SearchOut)
def search_endpoint(
    q: str = Query(min_length=2, max_length=100),
    limit: int = Query(default=5, ge=1, le=20, description="Résultats maximum par catégorie"),
    user: User = Depends(get_current_user),
    repo: SearchRepository = Depends(get_search_repo),
) -> SearchOut:
    hits = repo.search(q, _scope_for(user), limit_per_kind=limit)

    return SearchOut(
        query=q,
        total=len(hits),
        items=[SearchHitOut.model_validate(hit) for hit in hits],
    )
