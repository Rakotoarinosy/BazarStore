"""Use cases du dashboard. Ne dépendent que du domaine."""

from datetime import UTC, datetime, tzinfo

from src.domain.demande.analytics import DashboardStats, DemandeAnalytics

DEFAULT_DAYS = 7


def get_dashboard_stats(
    analytics: DemandeAnalytics, tz: tzinfo, days: int = DEFAULT_DAYS
) -> DashboardStats:
    return analytics.dashboard_stats(datetime.now(UTC), tz, days)
