import httpx
import pytest

pytestmark = pytest.mark.anyio

AGENTS = "/api/v1/agents"
REQUESTS = "/api/v1/requests"
USERS = "/api/v1/users"


def _agent(**overrides: object) -> dict:
    return {"name": "Jean Rakoto", "email": "jean@mairie.mg", "department": "Voirie", **overrides}


async def test_agent_crud_flow(client: httpx.AsyncClient) -> None:
    # POST
    response = await client.post(AGENTS, json=_agent())
    assert response.status_code == 201
    agent = response.json()
    assert agent["status"] == "available"
    assert agent["is_active"] is True
    assert agent["interventions"] == 0
    assert set(agent) == {
        "id", "name", "email", "department", "status", "is_active", "interventions", "created_at",
    }

    # GET (détail + liste)
    assert (await client.get(f"{AGENTS}/{agent['id']}")).json() == agent
    assert (await client.get(AGENTS)).json() == [agent]

    # PATCH
    response = await client.patch(
        f"{AGENTS}/{agent['id']}", json={"status": "in_intervention", "department": "Eau"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "in_intervention"
    assert response.json()["department"] == "Eau"
    assert response.json()["name"] == "Jean Rakoto"

    # Désactiver puis réactiver
    response = await client.post(f"{AGENTS}/{agent['id']}/deactivate")
    assert response.json()["is_active"] is False
    assert response.json()["status"] == "offline"

    response = await client.post(f"{AGENTS}/{agent['id']}/activate")
    assert response.json()["is_active"] is True


async def test_list_filters(client: httpx.AsyncClient) -> None:
    await client.post(AGENTS, json=_agent())
    sarah = (await client.post(AGENTS, json=_agent(name="Sarah Andry", email="s@mairie.mg", department="Eau"))).json()
    await client.post(AGENTS, json=_agent(name="Marc Rabe", email="m@mairie.mg", department="Éclairage"))
    await client.post(f"{AGENTS}/{sarah['id']}/deactivate")

    by_department = await client.get(AGENTS, params={"department": "eau"})
    assert [a["name"] for a in by_department.json()] == ["Sarah Andry"]

    active = await client.get(AGENTS, params={"is_active": True})
    assert [a["name"] for a in active.json()] == ["Jean Rakoto", "Marc Rabe"]

    by_search = await client.get(AGENTS, params={"search": "marc"})
    assert [a["name"] for a in by_search.json()] == ["Marc Rabe"]


async def test_duplicate_email_returns_409(client: httpx.AsyncClient) -> None:
    await client.post(AGENTS, json=_agent())

    response = await client.post(AGENTS, json=_agent(name="Autre"))

    assert response.status_code == 409
    assert response.json()["error"] == "AgentAlreadyExistsError"


async def test_unknown_agent_returns_404(client: httpx.AsyncClient) -> None:
    response = await client.get(f"{AGENTS}/missing")

    assert response.status_code == 404
    assert response.json()["error"] == "AgentNotFoundError"


async def test_invalid_email_returns_422(client: httpx.AsyncClient) -> None:
    response = await client.post(AGENTS, json=_agent(email="not-an-email"))

    assert response.status_code == 422


async def test_interventions_follow_assigned_citizen_requests(client: httpx.AsyncClient) -> None:
    agent = (await client.post(AGENTS, json=_agent())).json()
    other = (await client.post(AGENTS, json=_agent(name="Sarah Andry", email="s@mairie.mg"))).json()
    citizen = (await client.post(USERS, json={"email": "rina@example.com", "name": "Rina"})).json()
    for title, agent_id in (("Nid de poule", agent["id"]), ("Lampadaire", agent["id"]), ("Fuite", other["id"])):
        response = await client.post(
            REQUESTS,
            json={
                "title": title,
                "description": "x",
                "category": "Voirie",
                "citizen_id": citizen["id"],
                "location": "Analakely",
                "assigned_agent_id": agent_id,
            },
        )
        assert response.status_code == 201

    assert (await client.get(f"{AGENTS}/{agent['id']}")).json()["interventions"] == 2
    assert [a["interventions"] for a in (await client.get(AGENTS)).json()] == [2, 1]

    # « Voir ses interventions » : les demandes attribuées, les plus récentes d'abord.
    interventions = await client.get(f"{AGENTS}/{agent['id']}/interventions")
    assert interventions.status_code == 200
    assert [r["title"] for r in interventions.json()] == ["Lampadaire", "Nid de poule"]


async def test_interventions_of_unknown_agent_returns_404(client: httpx.AsyncClient) -> None:
    response = await client.get(f"{AGENTS}/missing/interventions")

    assert response.status_code == 404
