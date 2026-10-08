"""Use cases du domaine des demandes citoyennes."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from src.domain.agent import (
    Agent,
    AgentInactiveError,
    AgentNotFoundError,
    AgentQuery,
    AgentRepository,
)
from src.domain.citizen_request import (
    CitizenRequest,
    CitizenRequestNotFoundError,
    CitizenRequestRepository,
    DashboardCategoryCount,
    DashboardDailyCount,
    DashboardSummary,
    RequestAnalysis,
    RequestAnalyzer,
    RequestCategory,
    RequestPriority,
    RequestSortBy,
    RequestStatus,
    SortOrder,
)
from src.domain.user import UserNotFoundError, UserRepository
from src.features.citizen_request.schemas import (
    CreateCitizenRequestIn,
    UpdateCitizenRequestIn,
)


def create_citizen_request(
    dto: CreateCitizenRequestIn,
    repo: CitizenRequestRepository,
    users: UserRepository,
    agents: AgentRepository,
) -> CitizenRequest:
    _ensure_user_exists(dto.citizen_id, users)
    if dto.assigned_agent_id is not None:
        _ensure_agent_assignable(dto.assigned_agent_id, agents)

    now = datetime.now(UTC)
    request = CitizenRequest(
        id=str(uuid.uuid4()),
        title=dto.title,
        description=dto.description,
        category=dto.category,
        priority=dto.priority,
        status=dto.status,
        citizen_id=dto.citizen_id,
        created_at=now,
        location=dto.location,
        latitude=dto.latitude,
        longitude=dto.longitude,
        assigned_agent_id=dto.assigned_agent_id,
        resolved_at=now if dto.status is RequestStatus.RESOLVED else None,
    )

    return repo.add(request)


def list_citizen_requests(
    repo: CitizenRequestRepository,
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
    return repo.list_page(
        page=page,
        page_size=page_size,
        search=search,
        category=category,
        priority=priority,
        status=status,
        sort_by=sort_by,
        sort_order=sort_order,
    )


def get_citizen_request(request_id: str, repo: CitizenRequestRepository) -> CitizenRequest:
    request = repo.get_by_id(request_id)
    if request is None:
        raise CitizenRequestNotFoundError(request_id)

    return request


def update_citizen_request(
    request_id: str,
    dto: UpdateCitizenRequestIn,
    repo: CitizenRequestRepository,
    users: UserRepository,
    agents: AgentRepository,
) -> CitizenRequest:
    request = get_citizen_request(request_id, repo)
    changes = dto.model_dump(exclude_unset=True)

    citizen_id = changes.get("citizen_id")
    if citizen_id is not None:
        _ensure_user_exists(citizen_id, users)

    # Seule une nouvelle attribution est vérifiée : on peut toujours modifier une demande
    # dont l'agent a été désactivé depuis.
    assigned_agent_id = changes.get("assigned_agent_id")
    if assigned_agent_id is not None and assigned_agent_id != request.assigned_agent_id:
        _ensure_agent_assignable(assigned_agent_id, agents)

    new_status = changes.get("status", request.status)
    now = datetime.now(UTC)
    if new_status is RequestStatus.RESOLVED and request.status is not RequestStatus.RESOLVED:
        changes["resolved_at"] = now
    elif new_status is not RequestStatus.RESOLVED and request.status is RequestStatus.RESOLVED:
        changes["resolved_at"] = None

    return repo.update(replace(request, **changes))


def delete_citizen_request(request_id: str, repo: CitizenRequestRepository) -> None:
    get_citizen_request(request_id, repo)
    repo.delete(request_id)


def analyze_citizen_request(
    request_id: str,
    repo: CitizenRequestRepository,
    agents: AgentRepository,
    analyzer: RequestAnalyzer,
) -> tuple[RequestAnalysis, Agent | None]:
    """Suggestion de l'IA (catégorie, priorité, résumé, agent). Rien n'est modifié en base."""
    request = get_citizen_request(request_id, repo)
    candidates = agents.search(AgentQuery(is_active=True))

    analysis = analyzer.analyze(request, candidates)

    # Le modèle peut halluciner un identifiant : seul un agent actif réellement proposé est retenu.
    agent = next((a for a in candidates if a.id == analysis.recommended_agent_id), None)
    if agent is None and analysis.recommended_agent_id is not None:
        analysis = replace(analysis, recommended_agent_id=None)

    return analysis, agent


def get_dashboard_summary(
    repo: CitizenRequestRepository, now: datetime | None = None
) -> DashboardSummary:
    current_time = now or datetime.now(UTC)
    today_start = current_time.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    trend_start = today_start - timedelta(days=6)

    aggregates = repo.dashboard_aggregates(
        trend_start=trend_start,
        trend_end=today_end,
        today_start=today_start,
        today_end=today_end,
    )
    categories = [
        DashboardCategoryCount(
            category=category,
            count=aggregates.by_category.get(category, 0),
        )
        for category in RequestCategory
    ]
    daily_counts = [
        DashboardDailyCount(
            date=day,
            count=aggregates.by_day.get(day, 0),
        )
        for day in (trend_start.date() + timedelta(days=offset) for offset in range(7))
    ]

    return DashboardSummary(
        open_requests=(
            aggregates.by_status.get(RequestStatus.NEW, 0)
            + aggregates.by_status.get(RequestStatus.PENDING, 0)
        ),
        in_progress_requests=aggregates.by_status.get(RequestStatus.IN_PROGRESS, 0),
        resolved_requests=aggregates.by_status.get(RequestStatus.RESOLVED, 0),
        today_interventions=aggregates.resolved_today,
        category_distribution=categories,
        requests_last_7_days=daily_counts,
    )


def _ensure_user_exists(user_id: str, users: UserRepository) -> None:
    if users.get_by_id(user_id) is None:
        raise UserNotFoundError(user_id)


def _ensure_agent_assignable(agent_id: str, agents: AgentRepository) -> None:
    agent = agents.get_by_id(agent_id)
    if agent is None:
        raise AgentNotFoundError(agent_id)
    if not agent.is_active:
        raise AgentInactiveError(agent_id)
