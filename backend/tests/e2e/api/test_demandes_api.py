import httpx
import pytest

pytestmark = pytest.mark.anyio

USERS = "/api/v1/users"
DEMANDES = "/api/v1/demandes"
AGENTS = "/api/v1/agents"


async def _create_citizen(client: httpx.AsyncClient) -> str:
    response = await client.post(USERS, json={"email": "rina@example.com", "name": "Rina"})

    return response.json()["id"]


async def _create_agent(client: httpx.AsyncClient) -> str:
    response = await client.post(
        AGENTS, json={"name": "Jean Rakoto", "email": "jean@mairie.mg", "department": "Voirie"}
    )

    return response.json()["id"]


def _payload(citizen_id: str, **overrides: object) -> dict:
    return {
        "title": "Lampadaire en panne",
        "description": "La rue est sans lumière depuis une semaine",
        "category": "eclairage_public",
        "citizen_id": citizen_id,
        "address": "Rue Rainandriamampandry, Antananarivo",
        **overrides,
    }


async def test_demande_crud_flow(client: httpx.AsyncClient) -> None:
    citizen_id = await _create_citizen(client)

    # POST
    response = await client.post(DEMANDES, json=_payload(citizen_id))
    assert response.status_code == 201
    demande = response.json()
    assert demande["status"] == "nouveau"
    assert demande["priority"] == "moyenne"
    assert demande["agent_id"] is None

    # GET (détail + liste paginée)
    response = await client.get(f"{DEMANDES}/{demande['id']}")
    assert response.status_code == 200
    assert response.json() == demande

    response = await client.get(DEMANDES)
    page = response.json()
    assert page["items"] == [demande]
    assert (page["total"], page["page"], page["pages"]) == (1, 1, 1)

    # PATCH
    response = await client.patch(
        f"{DEMANDES}/{demande['id']}", json={"title": "Lampadaire cassé", "priority": "haute"}
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Lampadaire cassé"
    assert response.json()["description"] == demande["description"]

    # DELETE
    response = await client.delete(f"{DEMANDES}/{demande['id']}")
    assert response.status_code == 204

    response = await client.get(f"{DEMANDES}/{demande['id']}")
    assert response.status_code == 404
    assert response.json()["error"] == "DemandeNotFoundError"


async def test_list_search_filter_sort_and_paginate(client: httpx.AsyncClient) -> None:
    citizen_id = await _create_citizen(client)
    for title, category, priority in [
        ("Nid de poule", "voirie", "urgente"),
        ("Fuite d'eau", "eau", "haute"),
        ("Déchets non collectés", "dechets", "basse"),
    ]:
        await client.post(
            DEMANDES, json=_payload(citizen_id, title=title, category=category, priority=priority)
        )

    by_category = await client.get(DEMANDES, params={"category": "eau"})
    assert [d["title"] for d in by_category.json()["items"]] == ["Fuite d'eau"]

    by_search = await client.get(DEMANDES, params={"search": "nid"})
    assert by_search.json()["total"] == 1

    by_priority = await client.get(DEMANDES, params={"sort_by": "priority", "order": "desc"})
    assert [d["priority"] for d in by_priority.json()["items"]] == ["urgente", "haute", "basse"]

    second_page = await client.get(DEMANDES, params={"page": 2, "page_size": 2})
    assert len(second_page.json()["items"]) == 1
    assert second_page.json()["pages"] == 2


async def test_accept_assign_resolve_workflow(client: httpx.AsyncClient) -> None:
    citizen_id = await _create_citizen(client)
    agent_id = await _create_agent(client)
    demande = (await client.post(DEMANDES, json=_payload(citizen_id))).json()
    url = f"{DEMANDES}/{demande['id']}"

    response = await client.post(
        f"{url}/assign", json={"agent_id": agent_id, "scheduled_at": "2026-10-05T09:00:00"}
    )
    assert response.status_code == 200
    assigned = response.json()
    assert assigned["status"] == "en_cours"
    assert assigned["agent_id"] == agent_id
    assert assigned["scheduled_at"].startswith("2026-10-05T09:00")

    response = await client.post(f"{url}/resolve")
    assert response.json()["status"] == "resolu"

    # Un état final ne peut plus évoluer.
    response = await client.post(f"{url}/accept")
    assert response.status_code == 400
    assert response.json()["error"] == "InvalidStatusTransitionError"


async def test_assign_unknown_or_inactive_agent_returns_404(client: httpx.AsyncClient) -> None:
    citizen_id = await _create_citizen(client)
    agent_id = await _create_agent(client)
    demande = (await client.post(DEMANDES, json=_payload(citizen_id))).json()
    url = f"{DEMANDES}/{demande['id']}/assign"
    body = {"scheduled_at": "2026-10-05T09:00:00"}

    response = await client.post(url, json={**body, "agent_id": "missing"})
    assert response.status_code == 404
    assert response.json()["error"] == "AgentNotFoundError"

    await client.post(f"{AGENTS}/{agent_id}/deactivate")
    response = await client.post(url, json={**body, "agent_id": agent_id})
    assert response.status_code == 404

    # La demande n'a pas bougé.
    assert (await client.get(f"{DEMANDES}/{demande['id']}")).json()["status"] == "nouveau"


async def test_reject_is_final(client: httpx.AsyncClient) -> None:
    citizen_id = await _create_citizen(client)
    demande = (await client.post(DEMANDES, json=_payload(citizen_id))).json()

    response = await client.post(f"{DEMANDES}/{demande['id']}/reject")
    assert response.json()["status"] == "rejete"

    response = await client.post(f"{DEMANDES}/{demande['id']}/accept")
    assert response.status_code == 400


async def test_unknown_citizen_returns_404(client: httpx.AsyncClient) -> None:
    response = await client.post(DEMANDES, json=_payload("missing"))

    assert response.status_code == 404
    assert response.json()["error"] == "UserNotFoundError"


async def test_invalid_category_returns_422(client: httpx.AsyncClient) -> None:
    citizen_id = await _create_citizen(client)

    response = await client.post(DEMANDES, json=_payload(citizen_id, category="inconnue"))

    assert response.status_code == 422
