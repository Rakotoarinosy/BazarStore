"""Schémas HTTP de supervision de l'intégration Odoo."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SyncRejectionOut(BaseModel):
    odoo_id: int | str | None
    reason: str


class SyncRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    correlation_id: str
    kind: str
    trigger: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    created_count: int
    updated_count: int
    unchanged_count: int
    deactivated_count: int
    rejected_count: int
    rejections: list[SyncRejectionOut]
    error_message: str | None
