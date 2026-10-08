"""Endpoints HTTP du domaine demande, protégés par authentification et par rôle.

Matrice :
  CITIZEN  → crée ses demandes, voit les siennes, modifie/supprime les siennes tant qu'elles sont « nouveau »
  AGENT    → voit les demandes qui lui sont attribuées et peut les résoudre
  MANAGER  → tout sur les demandes, dont accepter / rejeter / attribuer
  ADMIN    → tout

ATTENTION à l'ordre : les routes fixes (/map) doivent être déclarées AVANT /{demande_id}.
"""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi import status as http_status
from sqlalchemy.orm import Session

from src.domain.agent import AgentRepository
from src.domain.demande import (
    AgentDirectory,
    Category,
    Demande,
    DemandeQuery,
    DemandeRepository,
    Priority,
    SortField,
    Status,
)
from src.domain.demande.analytics import DemandeAnalytics, MapPoint
from src.domain.demande.events import DemandeEvent, DemandeEventRepository
from src.domain.pagination import Page
from src.domain.user import ForbiddenError, Role, User, UserRepository
from src.features.demande.schemas import (
    AssignDemandeIn,
    CreateDemandeIn,
    DemandeOut,
    DemandePageOut,
    EventOut,
    MapPointOut,
    UpdateDemandeIn,
)
from src.features.demande.use_cases import (
    accept_demande,
    assign_demande,
    create_demande,
    delete_demande,
    get_demande,
    list_demandes,
    reject_demande,
    resolve_demande,
    update_demande,
)
from src.features.demande.use_cases.insights import list_map_points
from src.features.demande.use_cases.timeline import list_demande_events
from src.infrastructure.persistence.agent_directory import SqlAlchemyAgentDirectory
from src.infrastructure.persistence.agent_repository import SqlAlchemyAgentRepository
from src.infrastructure.persistence.database import get_db
from src.infrastructure.persistence.demande_analytics import SqlAlchemyDemandeAnalytics
from src.infrastructure.persistence.demande_event_repository import (
    SqlAlchemyDemandeEventRepository,
)
from src.infrastructure.persistence.demande_repository import SqlAlchemyDemandeRepository
from src.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from src.infrastructure.security.deps import get_current_user, require_roles

router = APIRouter(prefix="/demandes", tags=["demandes"])

STAFF = {Role.ADMIN, Role.MANAGER, Role.COMMERCIAL}
# Champs qu'un citoyen n'a jamais le droit de modifier lui-même.
CITIZEN_PROTECTED_FIELDS = {"status", "priority", "agent_id", "scheduled_at", "citizen_id"}


def get_demande_repo(db: Session = Depends(get_db)) -> DemandeRepository:
    return SqlAlchemyDemandeRepository(db)


def get_user_repo(db: Session = Depends(get_db)) -> UserRepository:
    return SqlAlchemyUserRepository(db)


def get_agent_directory(db: Session = Depends(get_db)) -> AgentDirectory:
    return SqlAlchemyAgentDirectory(db)


def get_agent_repo(db: Session = Depends(get_db)) -> AgentRepository:
    return SqlAlchemyAgentRepository(db)


def get_event_repo(db: Session = Depends(get_db)) -> DemandeEventRepository:
    return SqlAlchemyDemandeEventRepository(db)


def get_analytics(db: Session = Depends(get_db)) -> DemandeAnalytics:
    return SqlAlchemyDemandeAnalytics(db)


# ─── Contrôles d'accès ──────────────────────────────────────────────


def _apply_scope(
    user: User, citizen_id: str | None, agent_id: str | None
) -> tuple[str | None, str | None]:
    """Filtrage imposé côté serveur : les paramètres du client sont écrasés pour CITIZEN / AGENT."""
    if user.role is Role.CITIZEN:
        return user.id, agent_id
    if user.role is Role.AGENT:
        if user.agent_id is None:
            raise ForbiddenError("This account is not linked to an agent profile")
        return citizen_id, user.agent_id

    return citizen_id, agent_id


def _can_view(user: User, demande: Demande) -> bool:
    if user.role in STAFF:
        return True
    if user.role is Role.CITIZEN:
        return demande.citizen_id == user.id
    if user.role is Role.AGENT:
        return user.agent_id is not None and demande.agent_id == user.agent_id
    return False


def _ensure_can_view(user: User, demande: Demande) -> None:
    if not _can_view(user, demande):
        raise ForbiddenError()


def _ensure_citizen_can_edit(user: User, demande: Demande) -> None:
    if demande.citizen_id != user.id:
        raise ForbiddenError()
    if demande.status != Status.NOUVEAU:
        raise ForbiddenError("Only new requests can be modified or deleted by their author")


# ─── Création / lecture ─────────────────────────────────────────────


@router.post("", response_model=DemandeOut, status_code=http_status.HTTP_201_CREATED)
def create_demande_endpoint(
    payload: CreateDemandeIn,
    user: User = Depends(require_roles(Role.CITIZEN, Role.MANAGER)),
    repo: DemandeRepository = Depends(get_demande_repo),
    users: UserRepository = Depends(get_user_repo),
    events: DemandeEventRepository = Depends(get_event_repo),
) -> Demande:
    if user.role is Role.CITIZEN:
        # Un citoyen crée en son nom et ne fixe pas la priorité (évaluée par le service).
        payload = payload.model_copy(update={"citizen_id": user.id, "priority": Priority.MOYENNE})

    return create_demande(payload, repo, users, events, user)


@router.get("", response_model=DemandePageOut)
def list_demandes_endpoint(
    search: str | None = Query(default=None, max_length=100),
    status: Status | None = None,
    category: Category | None = None,
    priority: Priority | None = None,
    agent_id: str | None = None,
    citizen_id: str | None = None,
    sort_by: SortField = SortField.CREATED_AT,
    order: Literal["asc", "desc"] = "desc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    repo: DemandeRepository = Depends(get_demande_repo),
) -> Page[Demande]:
    citizen_id, agent_id = _apply_scope(user, citizen_id, agent_id)

    query = DemandeQuery(
        search=search,
        status=status,
        category=category,
        priority=priority,
        agent_id=agent_id,
        citizen_id=citizen_id,
        sort_by=sort_by,
        descending=order == "desc",
        page=page,
        page_size=page_size,
    )

    return list_demandes(query, repo)


@router.get("/map", response_model=list[MapPointOut])
def map_demandes_endpoint(
    status: Status | None = None,
    category: Category | None = None,
    priority: Priority | None = None,
    agent_id: str | None = None,
    include_closed: bool = False,
    limit: int = Query(default=1000, ge=1, le=2000),
    user: User = Depends(get_current_user),
    analytics: DemandeAnalytics = Depends(get_analytics),
) -> list[MapPoint]:
    """Demandes géolocalisées pour la carte (par défaut : uniquement les non clôturées)."""
    citizen_id, agent_id = _apply_scope(user, None, agent_id)
    query = DemandeQuery(
        status=status, category=category, priority=priority, agent_id=agent_id, citizen_id=citizen_id
    )

    return list_map_points(query, analytics, active_only=not include_closed, limit=limit)


@router.get("/{demande_id}", response_model=DemandeOut)
def get_demande_endpoint(
    demande_id: str,
    user: User = Depends(get_current_user),
    repo: DemandeRepository = Depends(get_demande_repo),
) -> Demande:
    demande = get_demande(demande_id, repo)
    _ensure_can_view(user, demande)

    return demande


@router.get("/{demande_id}/events", response_model=list[EventOut])
def list_demande_events_endpoint(
    demande_id: str,
    user: User = Depends(get_current_user),
    repo: DemandeRepository = Depends(get_demande_repo),
    events: DemandeEventRepository = Depends(get_event_repo),
    agents: AgentRepository = Depends(get_agent_repo),
) -> list[DemandeEvent]:
    """Historique complet (timeline) d'une demande, du plus ancien au plus récent."""
    _ensure_can_view(user, get_demande(demande_id, repo))

    return list_demande_events(demande_id, events, agents)


# ─── Modification / suppression ─────────────────────────────────────


@router.patch("/{demande_id}", response_model=DemandeOut)
def update_demande_endpoint(
    demande_id: str,
    payload: UpdateDemandeIn,
    user: User = Depends(require_roles(Role.CITIZEN, Role.MANAGER)),
    repo: DemandeRepository = Depends(get_demande_repo),
    events: DemandeEventRepository = Depends(get_event_repo),
) -> Demande:
    if user.role is Role.CITIZEN:
        _ensure_citizen_can_edit(user, get_demande(demande_id, repo))
        if CITIZEN_PROTECTED_FIELDS & payload.model_dump(exclude_unset=True).keys():
            raise ForbiddenError("You cannot modify status, priority or assignment")

    return update_demande(demande_id, payload, repo, events, user)


@router.delete("/{demande_id}", status_code=http_status.HTTP_204_NO_CONTENT)
def delete_demande_endpoint(
    demande_id: str,
    user: User = Depends(require_roles(Role.CITIZEN, Role.MANAGER)),
    repo: DemandeRepository = Depends(get_demande_repo),
) -> None:
    if user.role is Role.CITIZEN:
        _ensure_citizen_can_edit(user, get_demande(demande_id, repo))

    delete_demande(demande_id, repo)


# ─── Workflow ───────────────────────────────────────────────────────


@router.post("/{demande_id}/accept", response_model=DemandeOut)
def accept_demande_endpoint(
    demande_id: str,
    user: User = Depends(require_roles(Role.MANAGER)),
    repo: DemandeRepository = Depends(get_demande_repo),
    events: DemandeEventRepository = Depends(get_event_repo),
) -> Demande:
    return accept_demande(demande_id, repo, events, user)


@router.post(
    "/{demande_id}/reject",
    response_model=DemandeOut,
    dependencies=[Depends(require_roles(Role.MANAGER))],
)
def reject_demande_endpoint(
    demande_id: str,
    user: User = Depends(require_roles(Role.MANAGER)),
    repo: DemandeRepository = Depends(get_demande_repo),
    events: DemandeEventRepository = Depends(get_event_repo),
) -> Demande:
    return reject_demande(demande_id, repo, events, user)


@router.post("/{demande_id}/resolve", response_model=DemandeOut)
def resolve_demande_endpoint(
    demande_id: str,
    user: User = Depends(require_roles(Role.AGENT, Role.MANAGER)),
    repo: DemandeRepository = Depends(get_demande_repo),
    events: DemandeEventRepository = Depends(get_event_repo),
) -> Demande:
    if user.role is Role.AGENT:
        # Un agent ne résout que les demandes qui lui sont attribuées.
        _ensure_can_view(user, get_demande(demande_id, repo))

    return resolve_demande(demande_id, repo, events, user)


@router.post(
    "/{demande_id}/assign",
    response_model=DemandeOut,
    dependencies=[Depends(require_roles(Role.MANAGER))],
)
def assign_demande_endpoint(
    demande_id: str,
    payload: AssignDemandeIn,
    user: User = Depends(require_roles(Role.MANAGER)),
    repo: DemandeRepository = Depends(get_demande_repo),
    agents: AgentDirectory = Depends(get_agent_directory),
    events: DemandeEventRepository = Depends(get_event_repo),
) -> Demande:
    return assign_demande(demande_id, payload, repo, agents, events, user)
