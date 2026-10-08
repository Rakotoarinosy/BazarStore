"""Lectures pour la carte interactive."""

from src.domain.demande import DemandeQuery
from src.domain.demande.analytics import DemandeAnalytics, MapPoint


def list_map_points(
    query: DemandeQuery, analytics: DemandeAnalytics, *, active_only: bool, limit: int
) -> list[MapPoint]:
    return analytics.map_points(query, active_only=active_only, limit=limit)
