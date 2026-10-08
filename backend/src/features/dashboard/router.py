"""Endpoints HTTP du dashboard : réservés aux MANAGER (et ADMIN)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.domain.demande.analytics import DashboardStats, DemandeAnalytics
from src.domain.user import Role
from src.features.dashboard.schemas import DashboardStatsOut
from src.features.dashboard.use_cases import DEFAULT_DAYS, get_dashboard_stats
from src.infrastructure.config.settings import Settings, get_settings
from src.infrastructure.persistence.database import get_db
from src.infrastructure.persistence.demande_analytics import SqlAlchemyDemandeAnalytics
from src.infrastructure.security.deps import require_roles
from src.shared.timezone import resolve_timezone

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_roles(Role.MANAGER))],
)


def get_analytics(db: Session = Depends(get_db)) -> DemandeAnalytics:
    return SqlAlchemyDemandeAnalytics(db)


@router.get("/stats", response_model=DashboardStatsOut)
def dashboard_stats_endpoint(
    days: int = Query(default=DEFAULT_DAYS, ge=1, le=31),
    analytics: DemandeAnalytics = Depends(get_analytics),
    settings: Settings = Depends(get_settings),
) -> DashboardStats:
    return get_dashboard_stats(analytics, resolve_timezone(settings.app_timezone), days)
