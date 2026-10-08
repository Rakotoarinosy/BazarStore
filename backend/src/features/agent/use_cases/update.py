"""Modification partielle d'un agent (nom, email, département, statut)."""

from dataclasses import replace

from src.domain.agent import Agent, AgentAlreadyExistsError, AgentRepository
from src.features.agent.schemas import UpdateAgentIn
from src.features.agent.use_cases.read import get_agent


def update_agent(agent_id: str, dto: UpdateAgentIn, repo: AgentRepository) -> Agent:
    agent = get_agent(agent_id, repo)
    changes = dto.model_dump(exclude_unset=True, exclude_none=True)

    new_email = changes.get("email")
    if new_email and new_email != agent.email and repo.get_by_email(new_email):
        raise AgentAlreadyExistsError(new_email)

    return repo.update(replace(agent, **changes))
