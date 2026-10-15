"""Types for budget-aware product suggestions."""

from dataclasses import dataclass
from typing import Protocol

from src.domain.errors import DomainError


@dataclass(frozen=True)
class ShoppingMissionCandidate:
    id: str
    name: str
    description: str
    price: int
    category_name: str


@dataclass(frozen=True)
class ShoppingMissionSuggestion:
    product_id: str
    reason: str


@dataclass(frozen=True)
class ShoppingMissionAnalysis:
    summary: str
    suggestions: list[ShoppingMissionSuggestion]


class ShoppingMissionAnalyzer(Protocol):
    def recommend(
        self,
        mission: str,
        budget: int,
        candidates: list[ShoppingMissionCandidate],
    ) -> ShoppingMissionAnalysis: ...


class ShoppingMissionUnavailableError(DomainError):
    """Raised when the configured AI cannot produce a valid recommendation."""
