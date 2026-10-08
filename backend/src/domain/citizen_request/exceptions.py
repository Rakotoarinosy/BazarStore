"""Exceptions métier du domaine des demandes citoyennes."""

from src.domain.errors import DomainError


class CitizenRequestNotFoundError(DomainError):
    def __init__(self, request_id: str) -> None:
        super().__init__(f"Citizen request '{request_id}' not found")


class AnalysisUnavailableError(DomainError):  # → 503
    def __init__(self, reason: str = "AI analysis is temporarily unavailable") -> None:
        super().__init__(reason)
