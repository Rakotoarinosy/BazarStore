"""Désactivation et réactivation d'un agent (on ne supprime jamais un agent : ses interventions restent)."""

from dataclasses import replace

from src.domain.agent import Agent, AgentRepository, AgentStatus
from src.features.agent.use_cases.read import get_agent


def deactivate_agent(agent_id: str, repo: AgentRepository) -> Agent:
    agent = get_agent(agent_id, repo)

    return repo.update(replace(agent, is_active=False, status=AgentStatus.OFFLINE))


def activate_agent(agent_id: str, repo: AgentRepository) -> Agent:
    agent = get_agent(agent_id, repo)

    return repo.update(replace(agent, is_active=True, status=AgentStatus.AVAILABLE))
