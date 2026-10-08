"""Analyse d'une demande par IA : le domaine décrit le besoin, l'infrastructure choisit le modèle."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.domain.agent import Agent
from src.domain.citizen_request.entities import CitizenRequest, RequestCategory, RequestPriority


@dataclass(frozen=True)
class RequestAnalysis:
    category: RequestCategory
    priority: RequestPriority
    summary: str
    # Toujours l'id d'un des agents candidats, ou None si aucun ne convient.
    recommended_agent_id: str | None
    reason: str


class RequestAnalyzer(ABC):
    @abstractmethod
    def analyze(self, request: CitizenRequest, candidates: list[Agent]) -> RequestAnalysis:
        """Lève AnalysisUnavailableError si le service d'IA ne répond pas ou répond mal."""
