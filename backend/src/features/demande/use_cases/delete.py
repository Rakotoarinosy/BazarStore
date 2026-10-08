"""Suppression d'une demande."""

from src.domain.demande import DemandeRepository
from src.features.demande.use_cases.read import get_demande


def delete_demande(demande_id: str, repo: DemandeRepository) -> None:
    get_demande(demande_id, repo)
    repo.delete(demande_id)
