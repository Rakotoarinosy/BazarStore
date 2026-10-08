"""Faux repository agent en mémoire pour tester les use cases sans base de données."""

from src.domain.agent import Agent, AgentQuery, AgentRepository


class FakeAgentRepository(AgentRepository):
    def __init__(self) -> None:
        self.items: dict[str, Agent] = {}

    def get_by_id(self, agent_id: str) -> Agent | None:
        return self.items.get(agent_id)

    def get_by_email(self, email: str) -> Agent | None:
        return next((a for a in self.items.values() if a.email == email), None)

    def search(self, query: AgentQuery) -> list[Agent]:
        return [
            a
            for a in self.items.values()
            if (query.department is None or a.department == query.department)
            and (query.status is None or a.status == query.status)
            and (query.is_active is None or a.is_active == query.is_active)
        ]

    def add(self, agent: Agent) -> Agent:
        self.items[agent.id] = agent
        return agent

    def update(self, agent: Agent) -> Agent:
        self.items[agent.id] = agent
        return agent
