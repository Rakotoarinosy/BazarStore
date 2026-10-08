"""Exceptions métier du domaine agent.

Convention (voir shared/errors/handlers.py) : le suffixe du nom fixe le code HTTP.
  *NotFoundError      → 404
  *AlreadyExistsError → 409
  autre DomainError   → 400
"""

from src.domain.errors import DomainError


class AgentNotFoundError(DomainError):
    def __init__(self, agent_id: str) -> None:
        super().__init__(f"Agent '{agent_id}' not found")


class AgentAlreadyExistsError(DomainError):
    def __init__(self, email: str) -> None:
        super().__init__(f"An agent with email '{email}' already exists")


class AgentInactiveError(DomainError):  # → 400
    def __init__(self, agent_id: str) -> None:
        super().__init__(f"Agent '{agent_id}' is deactivated and cannot be assigned")
