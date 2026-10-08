"""Endpoints HTTP du domaine agent, protégés par rôle.

MANAGER (et ADMIN) : liste et gestion des agents. Un AGENT ne peut consulter que sa propre fiche
et ses propres interventions (ses demandes citoyennes) : GET /agents/{id}/interventions.
"""

from fastapi import APIRouter, Depends, Query
from fastapi import status as http_status
from sqlalchemy.orm import Session

from src.domain.agent import Agent, AgentQuery, AgentRepository, AgentStatus
from src.domain.citizen_request import CitizenRequest, CitizenRequestRepository
from src.domain.user import ForbiddenError, Role, User
from src.features.agent.schemas import AgentOut, CreateAgentIn, UpdateAgentIn
from src.features.agent.use_cases import (
    activate_agent,
    create_agent,
    deactivate_agent,
    get_agent,
    list_agent_interventions,
    list_agents,
    update_agent,
)
from src.features.citizen_request.schemas import CitizenRequestOut
from src.infrastructure.persistence.agent_repository import SqlAlchemyAgentRepository
from src.infrastructure.persistence.citizen_request_repository import (
    SqlAlchemyCitizenRequestRepository,
)
from src.infrastructure.persistence.database import get_db
from src.infrastructure.security.deps import require_roles

router = APIRouter(prefix="/agents", tags=["agents"])

manager_only = [Depends(require_roles(Role.MANAGER))]


def get_agent_repo(db: Session = Depends(get_db)) -> AgentRepository:
    return SqlAlchemyAgentRepository(db)


def get_request_repo(db: Session = Depends(get_db)) -> CitizenRequestRepository:
    return SqlAlchemyCitizenRequestRepository(db)


def _ensure_can_view_agent(user: User, agent_id: str) -> None:
    if user.role is Role.AGENT and user.agent_id != agent_id:
        raise ForbiddenError()


@router.post(
    "",
    response_model=AgentOut,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=manager_only,
)
def create_agent_endpoint(
    payload: CreateAgentIn, repo: AgentRepository = Depends(get_agent_repo)
) -> Agent:
    return create_agent(payload, repo)


@router.get("", response_model=list[AgentOut], dependencies=manager_only)
def list_agents_endpoint(
    search: str | None = Query(default=None, max_length=100),
    department: str | None = None,
    status: AgentStatus | None = None,
    is_active: bool | None = None,
    repo: AgentRepository = Depends(get_agent_repo),
) -> list[Agent]:
    query = AgentQuery(search=search, department=department, status=status, is_active=is_active)

    return list_agents(query, repo)


@router.get("/{agent_id}", response_model=AgentOut)
def get_agent_endpoint(
    agent_id: str,
    user: User = Depends(require_roles(Role.MANAGER, Role.AGENT)),
    repo: AgentRepository = Depends(get_agent_repo),
) -> Agent:
    _ensure_can_view_agent(user, agent_id)

    return get_agent(agent_id, repo)


@router.get("/{agent_id}/interventions", response_model=list[CitizenRequestOut])
def list_agent_interventions_endpoint(
    agent_id: str,
    user: User = Depends(require_roles(Role.MANAGER, Role.AGENT)),
    repo: AgentRepository = Depends(get_agent_repo),
    requests: CitizenRequestRepository = Depends(get_request_repo),
) -> list[CitizenRequest]:
    _ensure_can_view_agent(user, agent_id)

    return list_agent_interventions(agent_id, repo, requests)


@router.patch("/{agent_id}", response_model=AgentOut, dependencies=manager_only)
def update_agent_endpoint(
    agent_id: str, payload: UpdateAgentIn, repo: AgentRepository = Depends(get_agent_repo)
) -> Agent:
    return update_agent(agent_id, payload, repo)


@router.post("/{agent_id}/deactivate", response_model=AgentOut, dependencies=manager_only)
def deactivate_agent_endpoint(
    agent_id: str, repo: AgentRepository = Depends(get_agent_repo)
) -> Agent:
    return deactivate_agent(agent_id, repo)


@router.post("/{agent_id}/activate", response_model=AgentOut, dependencies=manager_only)
def activate_agent_endpoint(
    agent_id: str, repo: AgentRepository = Depends(get_agent_repo)
) -> Agent:
    return activate_agent(agent_id, repo)
