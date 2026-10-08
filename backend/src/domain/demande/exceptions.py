"""Exceptions métier du domaine demande.

Convention (voir shared/errors/handlers.py) : le suffixe du nom fixe le code HTTP.
  *NotFoundError      → 404
  *AlreadyExistsError → 409
  autre DomainError   → 400
"""

from src.domain.errors import DomainError


class DemandeNotFoundError(DomainError):
    def __init__(self, demande_id: str) -> None:
        super().__init__(f"Demande '{demande_id}' not found")


class InvalidStatusTransitionError(DomainError):
    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"Cannot move a demande from '{current}' to '{target}'")


class CitizenRequiredError(DomainError):
    def __init__(self) -> None:
        super().__init__("citizen_id is required when creating a demande on behalf of a citizen")
