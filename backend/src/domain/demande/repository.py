"""Interface du repository demande : le domaine décrit ce dont il a besoin, l'infrastructure l'implémente."""

from abc import ABC, abstractmethod

from src.domain.demande.entities import Demande
from src.domain.demande.queries import DemandeQuery
from src.domain.pagination import Page


class DemandeRepository(ABC):
    @abstractmethod
    def get_by_id(self, demande_id: str) -> Demande | None: ...

    @abstractmethod
    def search(self, query: DemandeQuery) -> Page[Demande]: ...

    @abstractmethod
    def add(self, demande: Demande) -> Demande: ...

    @abstractmethod
    def update(self, demande: Demande) -> Demande: ...

    @abstractmethod
    def delete(self, demande_id: str) -> None: ...
