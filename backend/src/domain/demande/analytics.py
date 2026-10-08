"""Lectures agrégées (dashboard, carte). Modèles de lecture + port implémenté par l'infrastructure."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, tzinfo

from src.domain.demande.entities import Category, Priority, Status
from src.domain.demande.queries import DemandeQuery


@dataclass(frozen=True)
class MapPoint:
    id: str
    title: str
    category: Category
    priority: Priority
    status: Status
    latitude: float
    longitude: float
    created_at: datetime
    address: str | None = None
    agent_id: str | None = None
    agent_name: str | None = None


@dataclass(frozen=True)
class DailyCount:
    day: date
    created: int
    resolved: int


@dataclass(frozen=True)
class DashboardStats:
    total: int
    open: int  # non clôturées : nouveau + en cours + en attente
    in_progress: int
    resolved: int
    rejected: int
    resolution_rate: float  # % de demandes résolues sur le total (0 si aucune demande)
    interventions_today: int  # demandes attribuées à un agent et planifiées aujourd'hui
    by_status: dict[str, int]
    by_category: dict[str, int]
    by_priority: dict[str, int]
    daily: list[DailyCount]  # un élément par jour, du plus ancien à aujourd'hui


class DemandeAnalytics(ABC):
    @abstractmethod
    def dashboard_stats(self, now: datetime, tz: tzinfo, days: int) -> DashboardStats: ...

    @abstractmethod
    def map_points(self, query: DemandeQuery, *, active_only: bool, limit: int) -> list[MapPoint]:
        """Demandes géolocalisées. Si `query.status` est absent et `active_only`, exclut résolues/rejetées."""
