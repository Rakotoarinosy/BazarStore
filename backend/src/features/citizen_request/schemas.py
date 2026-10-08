"""Schémas HTTP des demandes citoyennes et du dashboard."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.agent import AgentStatus
from src.domain.citizen_request import RequestCategory, RequestPriority, RequestStatus


class CreateCitizenRequestIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=10_000)
    category: RequestCategory
    priority: RequestPriority = RequestPriority.NORMAL
    status: RequestStatus = RequestStatus.NEW
    citizen_id: str = Field(min_length=1, max_length=36)
    location: str = Field(min_length=1, max_length=500)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    assigned_agent_id: str | None = Field(default=None, min_length=1, max_length=36)


class UpdateCitizenRequestIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1, max_length=10_000)
    category: RequestCategory | None = None
    priority: RequestPriority | None = None
    status: RequestStatus | None = None
    citizen_id: str | None = Field(default=None, min_length=1, max_length=36)
    location: str | None = Field(default=None, min_length=1, max_length=500)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    assigned_agent_id: str | None = Field(default=None, min_length=1, max_length=36)

    @model_validator(mode="before")
    @classmethod
    def reject_null_required_fields(cls, value: object) -> object:
        if isinstance(value, dict):
            required_fields = {
                "title",
                "description",
                "category",
                "priority",
                "status",
                "citizen_id",
                "location",
            }
            for field in required_fields.intersection(value):
                if value[field] is None:
                    raise ValueError(f"{field} cannot be null")

        return value


class CitizenRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: str
    category: RequestCategory
    priority: RequestPriority
    status: RequestStatus
    citizen_id: str
    created_at: datetime
    location: str
    latitude: float | None
    longitude: float | None
    assigned_agent_id: str | None
    resolved_at: datetime | None


class CitizenRequestPageOut(BaseModel):
    items: list[CitizenRequestOut]
    total: int
    page: int
    page_size: int
    total_pages: int


class DashboardCategoryCountOut(BaseModel):
    category: RequestCategory
    count: int


class DashboardDailyCountOut(BaseModel):
    date: date
    count: int


class DashboardOut(BaseModel):
    open_requests: int
    in_progress_requests: int
    resolved_requests: int
    today_interventions: int
    category_distribution: list[DashboardCategoryCountOut]
    requests_last_7_days: list[DashboardDailyCountOut]


class RecommendedAgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    department: str
    status: AgentStatus
    interventions: int


class RequestAnalysisOut(BaseModel):
    """Suggestion de l'IA : à valider par un humain avant d'être appliquée à la demande."""

    category: RequestCategory
    priority: RequestPriority
    summary: str
    reason: str
    recommended_agent: RecommendedAgentOut | None
