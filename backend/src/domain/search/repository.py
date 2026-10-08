from typing import Protocol

from src.domain.search.entities import SearchHit, SearchScope


class SearchRepository(Protocol):
    def search(self, query: str, scope: SearchScope, *, limit_per_kind: int) -> list[SearchHit]: ...
