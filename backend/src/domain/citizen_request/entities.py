"""Entités métier et valeurs du domaine des demandes citoyennes."""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class RequestCategory(StrEnum):
    PUBLIC_LIGHTING = "Éclairage public"
    ROADS = "Voirie"
    WATER = "Eau"
    WASTE = "Déchets"
    SAFETY = "Sécurité"
    GREEN_SPACES = "Espaces verts"
    OTHER = "Autre"


class RequestPriority(StrEnum):
    LOW = "Basse"
    NORMAL = "Normale"
    HIGH = "Haute"
    URGENT = "Urgente"


class RequestStatus(StrEnum):
    NEW = "Nouveau"
    IN_PROGRESS = "En cours"
    PENDING = "En attente"
    RESOLVED = "Résolu"
    REJECTED = "Rejeté"


class RequestSortBy(StrEnum):
    CREATED_AT = "created_at"
    TITLE = "title"
    CATEGORY = "category"
    PRIORITY = "priority"
    STATUS = "status"


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


@dataclass
class CitizenRequest:
    id: str
    title: str
    description: str
    category: RequestCategory
    priority: RequestPriority
    status: RequestStatus
    citizen_id: str
    created_at: datetime
    location: str
    assigned_agent_id: str | None = None
    resolved_at: datetime | None = None
    # Coordonnées GPS facultatives, pour placer la demande sur la carte du dashboard.
    latitude: float | None = None
    longitude: float | None = None


@dataclass(frozen=True)
class DashboardCategoryCount:
    category: RequestCategory
    count: int


@dataclass(frozen=True)
class DashboardDailyCount:
    date: date
    count: int


@dataclass(frozen=True)
class DashboardAggregates:
    by_status: dict[RequestStatus, int]
    by_category: dict[RequestCategory, int]
    resolved_today: int
    by_day: dict[date, int]


@dataclass(frozen=True)
class DashboardSummary:
    open_requests: int
    in_progress_requests: int
    resolved_requests: int
    today_interventions: int
    category_distribution: list[DashboardCategoryCount]
    requests_last_7_days: list[DashboardDailyCount]
