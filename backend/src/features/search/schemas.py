from pydantic import BaseModel, ConfigDict

from src.domain.search import SearchKind


class SearchHitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: SearchKind  # demande / citoyen / agent / intervention
    id: str
    title: str
    subtitle: str
    demande_id: str | None
    agent_id: str | None


class SearchOut(BaseModel):
    query: str
    total: int
    items: list[SearchHitOut]
