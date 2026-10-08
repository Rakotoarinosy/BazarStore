"""Endpoints HTTP des demandes citoyennes et du dashboard."""

from functools import lru_cache

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from src.domain.agent import Agent, AgentRepository
from src.domain.citizen_request import (
    AnalysisUnavailableError,
    CitizenRequest,
    CitizenRequestRepository,
    RequestAnalysis,
    RequestAnalyzer,
    RequestCategory,
    RequestPriority,
    RequestSortBy,
    RequestStatus,
    SortOrder,
)
from src.domain.user import Role, UserRepository
from src.features.citizen_request.schemas import (
    CitizenRequestOut,
    CitizenRequestPageOut,
    CreateCitizenRequestIn,
    DashboardOut,
    RecommendedAgentOut,
    RequestAnalysisOut,
    UpdateCitizenRequestIn,
)
from src.features.citizen_request.use_cases import (
    analyze_citizen_request,
    create_citizen_request,
    delete_citizen_request,
    get_citizen_request,
    get_dashboard_summary,
    list_citizen_requests,
    update_citizen_request,
)
from src.infrastructure.config import get_settings
from src.infrastructure.external.gemini_analyzer import GeminiRequestAnalyzer
from src.infrastructure.persistence.agent_repository import SqlAlchemyAgentRepository
from src.infrastructure.persistence.citizen_request_repository import (
    SqlAlchemyCitizenRequestRepository,
)
from src.infrastructure.persistence.database import get_db
from src.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from src.infrastructure.security.deps import require_roles

request_router = APIRouter(prefix="/requests", tags=["citizen requests"])
dashboard_router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def get_request_repo(db: Session = Depends(get_db)) -> CitizenRequestRepository:
    return SqlAlchemyCitizenRequestRepository(db)


def get_users_repo(db: Session = Depends(get_db)) -> UserRepository:
    return SqlAlchemyUserRepository(db)


def get_agents_repo(db: Session = Depends(get_db)) -> AgentRepository:
    return SqlAlchemyAgentRepository(db)


@lru_cache
def _gemini_analyzer(api_key: str, model: str) -> RequestAnalyzer:
    return GeminiRequestAnalyzer(api_key, model)


def get_request_analyzer() -> RequestAnalyzer:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise AnalysisUnavailableError("AI analysis is not configured (GEMINI_API_KEY is missing)")

    return _gemini_analyzer(settings.gemini_api_key, settings.gemini_model)


@request_router.post(
    "",
    response_model=CitizenRequestOut,
    status_code=status.HTTP_201_CREATED,
)
def create_request_endpoint(
    payload: CreateCitizenRequestIn,
    repo: CitizenRequestRepository = Depends(get_request_repo),
    users: UserRepository = Depends(get_users_repo),
    agents: AgentRepository = Depends(get_agents_repo),
) -> CitizenRequest:
    return create_citizen_request(payload, repo, users, agents)


@request_router.get("", response_model=CitizenRequestPageOut)
def list_requests_endpoint(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, min_length=1, max_length=200),
    category: RequestCategory | None = None,
    priority: RequestPriority | None = None,
    request_status: RequestStatus | None = Query(default=None, alias="status"),
    sort_by: RequestSortBy = RequestSortBy.CREATED_AT,
    sort_order: SortOrder = SortOrder.DESC,
    repo: CitizenRequestRepository = Depends(get_request_repo),
) -> CitizenRequestPageOut:
    items, total = list_citizen_requests(
        repo,
        page=page,
        page_size=page_size,
        search=search,
        category=category,
        priority=priority,
        status=request_status,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    return CitizenRequestPageOut(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@request_router.get("/{request_id}", response_model=CitizenRequestOut)
def get_request_endpoint(
    request_id: str,
    repo: CitizenRequestRepository = Depends(get_request_repo),
) -> CitizenRequest:
    return get_citizen_request(request_id, repo)


@request_router.post(
    "/{request_id}/analyze",
    response_model=RequestAnalysisOut,
    dependencies=[Depends(require_roles(Role.MANAGER))],
)
def analyze_request_endpoint(
    request_id: str,
    repo: CitizenRequestRepository = Depends(get_request_repo),
    agents: AgentRepository = Depends(get_agents_repo),
    analyzer: RequestAnalyzer = Depends(get_request_analyzer),
) -> RequestAnalysisOut:
    analysis, agent = analyze_citizen_request(request_id, repo, agents, analyzer)

    return _analysis_out(analysis, agent)


@request_router.put("/{request_id}", response_model=CitizenRequestOut)
def update_request_endpoint(
    request_id: str,
    payload: UpdateCitizenRequestIn,
    repo: CitizenRequestRepository = Depends(get_request_repo),
    users: UserRepository = Depends(get_users_repo),
    agents: AgentRepository = Depends(get_agents_repo),
) -> CitizenRequest:
    return update_citizen_request(request_id, payload, repo, users, agents)


@request_router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_request_endpoint(
    request_id: str,
    repo: CitizenRequestRepository = Depends(get_request_repo),
) -> None:
    delete_citizen_request(request_id, repo)


@dashboard_router.get("", response_model=DashboardOut)
def get_dashboard_endpoint(
    repo: CitizenRequestRepository = Depends(get_request_repo),
) -> DashboardOut:
    return get_dashboard_summary(repo)


def _analysis_out(analysis: RequestAnalysis, agent: Agent | None) -> RequestAnalysisOut:
    return RequestAnalysisOut(
        category=analysis.category,
        priority=analysis.priority,
        summary=analysis.summary,
        reason=analysis.reason,
        recommended_agent=RecommendedAgentOut.model_validate(agent) if agent else None,
    )
