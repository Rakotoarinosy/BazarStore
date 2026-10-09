"""Résultat paginé générique, réutilisable par tous les domaines."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Page[T]:
    items: list[T]
    total: int
    page: int
    page_size: int

    @property
    def pages(self) -> int:
        return -(-self.total // self.page_size)
