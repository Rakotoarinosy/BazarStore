"""Ajout d'un agent."""

import uuid
from datetime import UTC, datetime

from src.domain.agent import Agent, AgentAlreadyExistsError, AgentRepository
from src.features.agent.schemas import CreateAgentIn


def create_agent(dto: CreateAgentIn, repo: AgentRepository) -> Agent:
    if repo.get_by_email(dto.email):
        raise AgentAlreadyExistsError(dto.email)

    agent = Agent(
        id=str(uuid.uuid4()),
        email=dto.email,
        name=dto.name,
        department=dto.department,
        created_at=datetime.now(UTC),
        status=dto.status,
    )

    return repo.add(agent)
