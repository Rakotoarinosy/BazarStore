"""Interface du repository agent : le domaine décrit ce dont il a besoin, l'infrastructure l'implémente."""

from abc import ABC, abstractmethod

from src.domain.agent.entities import Agent
from src.domain.agent.queries import AgentQuery


class AgentRepository(ABC):
    @abstractmethod
    def get_by_id(self, agent_id: str) -> Agent | None: ...

    @abstractmethod
    def get_by_email(self, email: str) -> Agent | None: ...

    @abstractmethod
    def search(self, query: AgentQuery) -> list[Agent]: ...

    @abstractmethod
    def add(self, agent: Agent) -> Agent: ...

    @abstractmethod
    def update(self, agent: Agent) -> Agent: ...
