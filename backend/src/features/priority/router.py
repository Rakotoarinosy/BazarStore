"""File priorisée des demandes (T+8h).

  GET   /priorities/queue             demandes triées par score décroissant (critiques en premier)
  POST  /priorities/recompute         recalcul manuel (MANAGER)
  PATCH /priorities/{id}/inputs       urgence / citoyens concernés (MANAGER, ou auteur tant que « nouveau »)

Le score dépend de l'ancienneté : la file est recalculée à chaque lecture (refresh=true).
"""

from fastapi import APIRouter, Depends, Query
from fastapi import status as http_status
from sqlalchemy.orm import Session

from src.domain.demande import DemandeRepository, Status
from src.domain.demande.priority import PriorityRepository
from src.domain.user import ForbiddenError, Role, User
from src.features.demande.use_cases import get_demande
from src.features.priority.schemas import (
    PriorityInputsIn,
    PriorityItemOut,
    PriorityPageOut,
    RecomputeOut,
)
from src.infrastructure.persistence.database import get_db
from src.infrastructure.persistence.demande_priority import SqlAlchemyPriorityRepository
from src.infrastructure.persistence.demande_repository import SqlAlchemyDemandeRepository
from src.infrastructure.security.deps import get_current_user, require_roles

router = APIRouter(prefix="/priorities", tags=["priorities"])


def get_priority_repo(db: Session = Depends(get_db)) -> PriorityRepository:
    return SqlAlchemyPriorityRepository(db)


def get_demande_repo(db: Session = Depends(get_db)) -> DemandeRepository:
    return SqlAlchemyDemandeRepository(db)


def _scope(user: User) -> tuple[str | None, str | None]:
    """(citizen_id, agent_id) imposés par le rôle, comme pour GET /demandes."""
    if user.role is Role.CITIZEN:
        return user.id, None
    if user.role is Role.AGENT:
        if user.agent_id is None:
            raise ForbiddenError("This account is not linked to an agent profile")
        return None, user.agent_id

    return None, None


@router.get("/queue", response_model=PriorityPageOut)
def priority_queue_endpoint(
    status: Status | None = None,
    include_closed: bool = False,
    refresh: bool = True,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    repo: PriorityRepository = Depends(get_priority_repo),
) -> PriorityPageOut:
    if refresh:
        repo.refresh_scores()
    citizen_id, agent_id = _scope(user)
    items, total = repo.ranked(
        citizen_id=citizen_id,
        agent_id=agent_id,
        status=status,
        include_closed=include_closed,
        page=page,
        page_size=page_size,
    )

    return PriorityPageOut(
        items=[PriorityItemOut.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/recompute", response_model=RecomputeOut)
def recompute_endpoint(
    _: User = Depends(require_roles(Role.MANAGER)),
    repo: PriorityRepository = Depends(get_priority_repo),
) -> RecomputeOut:
    return RecomputeOut(level_changes=repo.refresh_scores())


@router.patch("/{demande_id}/inputs", response_model=PriorityItemOut)
def update_inputs_endpoint(
    demande_id: str,
    payload: PriorityInputsIn,
    user: User = Depends(require_roles(Role.CITIZEN, Role.MANAGER)),
    demandes: DemandeRepository = Depends(get_demande_repo),
    repo: PriorityRepository = Depends(get_priority_repo),
) -> PriorityItemOut:
    demande = get_demande(demande_id, demandes)
    if user.role is Role.CITIZEN and (
        demande.citizen_id != user.id or demande.status != Status.NOUVEAU
    ):
        raise ForbiddenError("Only the author can edit a new request")

    repo.update_inputs(
        demande_id,
        urgency=payload.urgency,
        affected_citizens=payload.affected_citizens,
        actor_id=user.id,
        actor_name=user.name,
    )
    item = repo.get_item(demande_id)

    return PriorityItemOut.model_validate(item)
