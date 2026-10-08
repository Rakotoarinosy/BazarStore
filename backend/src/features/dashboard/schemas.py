"""Schémas Pydantic du dashboard."""

from datetime import date

from pydantic import BaseModel, ConfigDict


class DailyCountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    day: date
    created: int
    resolved: int


class DashboardStatsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total: int
    open: int
    in_progress: int
    resolved: int
    rejected: int
    resolution_rate: float
    interventions_today: int
    by_status: dict[str, int]
    by_category: dict[str, int]
    by_priority: dict[str, int]
    daily: list[DailyCountOut]
