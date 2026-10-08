"""Paramètres de recherche d'une liste de demandes (filtres, tri, pagination)."""

from dataclasses import dataclass
from enum import StrEnum

from src.domain.demande.entities import Category, Priority, Status


class SortField(StrEnum):
    CREATED_AT = "created_at"
    TITLE = "title"
    PRIORITY = "priority"
    STATUS = "status"
    CATEGORY = "category"


@dataclass(frozen=True)
class DemandeQuery:
    search: str | None = None
    status: Status | None = None
    category: Category | None = None
    priority: Priority | None = None
    agent_id: str | None = None
    citizen_id: str | None = None
    sort_by: SortField = SortField.CREATED_AT
    descending: bool = True
    page: int = 1
    page_size: int = 20
