from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.demande.priority import URGENCY_MAX, URGENCY_MIN


class PriorityInputsIn(BaseModel):
    urgency: int | None = Field(default=None, ge=URGENCY_MIN, le=URGENCY_MAX)
    affected_citizens: int | None = Field(default=None, ge=1, le=1_000_000)

    @model_validator(mode="after")
    def at_least_one(self) -> Self:
        if self.urgency is None and self.affected_citizens is None:
            raise ValueError("Provide urgency and/or affected_citizens")

        return self


class PriorityItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    category: str
    status: str
    priority: str  # CRITIQUE / HAUTE / MOYENNE / FAIBLE, calculé automatiquement
    priority_score: int
    urgency: int
    affected_citizens: int
    created_at: datetime
    agent_id: str | None
    address: str | None
    is_late: bool


class PriorityPageOut(BaseModel):
    items: list[PriorityItemOut]
    total: int
    page: int
    page_size: int


class RecomputeOut(BaseModel):
    level_changes: int
