"""Lecture des agents : détail, liste filtrée et interventions."""

from src.domain.agent import Agent, AgentNotFoundError, AgentQuery, AgentRepository
from src.domain.citizen_request import CitizenRequest, CitizenRequestRepository


def get_agent(agent_id: str, repo: AgentRepository) -> Agent:
    agent = repo.get_by_id(agent_id)
    if agent is None:
        raise AgentNotFoundError(agent_id)

    return agent


def list_agents(query: AgentQuery, repo: AgentRepository) -> list[Agent]:
    return repo.search(query)


def list_agent_interventions(
    agent_id: str, agents: AgentRepository, requests: CitizenRequestRepository
) -> list[CitizenRequest]:
    get_agent(agent_id, agents)

    return requests.list_by_agent(agent_id)
