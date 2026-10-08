"""Lecture des demandes : détail et liste paginée (recherche, filtres, tri)."""

from src.domain.demande import Demande, DemandeNotFoundError, DemandeQuery, DemandeRepository
from src.domain.pagination import Page


def get_demande(demande_id: str, repo: DemandeRepository) -> Demande:
    demande = repo.get_by_id(demande_id)
    if demande is None:
        raise DemandeNotFoundError(demande_id)

    return demande


def list_demandes(query: DemandeQuery, repo: DemandeRepository) -> Page[Demande]:
    return repo.search(query)
