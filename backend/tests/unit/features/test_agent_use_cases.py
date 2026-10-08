import pytest

from src.domain.agent import AgentAlreadyExistsError, AgentNotFoundError, AgentQuery, AgentStatus
from src.features.agent.schemas import CreateAgentIn, UpdateAgentIn
from src.features.agent.use_cases import (
    activate_agent,
    create_agent,
    deactivate_agent,
    get_agent,
    list_agents,
    update_agent,
)
from tests.fakes_agent import FakeAgentRepository


@pytest.fixture
def repo() -> FakeAgentRepository:
    return FakeAgentRepository()


def _payload(**overrides) -> CreateAgentIn:
    data = {"name": "Jean Rakoto", "email": "jean@mairie.mg", "department": "Voirie"}
    return CreateAgentIn(**{**data, **overrides})


def test_create_defaults_to_available_and_active(repo):
    agent = create_agent(_payload(), repo)

    assert agent.status == AgentStatus.AVAILABLE
    assert agent.is_active is True
    assert agent.interventions == 0


def test_create_rejects_duplicate_email(repo):
    create_agent(_payload(), repo)

    with pytest.raises(AgentAlreadyExistsError):
        create_agent(_payload(name="Autre"), repo)


def test_get_fails_when_missing(repo):
    with pytest.raises(AgentNotFoundError):
        get_agent("nope", repo)


def test_update_changes_only_given_fields(repo):
    agent = create_agent(_payload(), repo)

    updated = update_agent(agent.id, UpdateAgentIn(status=AgentStatus.IN_INTERVENTION), repo)

    assert updated.status == AgentStatus.IN_INTERVENTION
    assert updated.name == "Jean Rakoto"
    assert updated.department == "Voirie"


def test_update_rejects_email_used_by_another_agent(repo):
    create_agent(_payload(), repo)
    other = create_agent(_payload(name="Sarah Andry", email="sarah@mairie.mg", department="Eau"), repo)

    with pytest.raises(AgentAlreadyExistsError):
        update_agent(other.id, UpdateAgentIn(email="jean@mairie.mg"), repo)


def test_update_allows_keeping_own_email(repo):
    agent = create_agent(_payload(), repo)

    updated = update_agent(agent.id, UpdateAgentIn(email="jean@mairie.mg", name="Jean R."), repo)

    assert updated.name == "Jean R."


def test_deactivate_then_activate(repo):
    agent = create_agent(_payload(), repo)

    off = deactivate_agent(agent.id, repo)
    assert (off.is_active, off.status) == (False, AgentStatus.OFFLINE)

    on = activate_agent(agent.id, repo)
    assert (on.is_active, on.status) == (True, AgentStatus.AVAILABLE)


def test_list_filters_by_department_and_activity(repo):
    jean = create_agent(_payload(), repo)
    create_agent(_payload(name="Sarah Andry", email="sarah@mairie.mg", department="Eau"), repo)
    deactivate_agent(jean.id, repo)

    assert [a.name for a in list_agents(AgentQuery(department="Eau"), repo)] == ["Sarah Andry"]
    assert [a.name for a in list_agents(AgentQuery(is_active=False), repo)] == ["Jean Rakoto"]
