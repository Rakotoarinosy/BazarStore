import httpx
import pytest

pytestmark = pytest.mark.anyio

REQUESTS = "/api/v1/requests"


async def test_citizen_request_crud_filters_and_dashboard(client: httpx.AsyncClient) -> None:
    citizen_response = await client.post(
        "/api/v1/users", json={"email": "citizen@example.com", "name": "Citoyen"}
    )
    agent_response = await client.post(
        "/api/v1/agents",
        json={"email": "agent@example.com", "name": "Agent", "department": "Voirie"},
    )
    citizen_id = citizen_response.json()["id"]
    agent_id = agent_response.json()["id"]

    resolved_response = await client.post(
        REQUESTS,
        json={
            "title": "Lampadaire en panne",
            "description": "Le lampadaire ne fonctionne plus.",
            "category": "Éclairage public",
            "priority": "Haute",
            "status": "Résolu",
            "citizen_id": citizen_id,
            "location": "Rue des Lilas",
            "assigned_agent_id": agent_id,
        },
    )
    open_response = await client.post(
        REQUESTS,
        json={
            "title": "Nid-de-poule",
            "description": "Un nid-de-poule dangereux.",
            "category": "Voirie",
            "citizen_id": citizen_id,
            "location": "Avenue Centrale",
        },
    )

    assert resolved_response.status_code == 201
    assert resolved_response.json()["resolved_at"] is not None
    assert open_response.status_code == 201
    resolved_id = resolved_response.json()["id"]
    open_id = open_response.json()["id"]

    page = await client.get(
        REQUESTS,
        params={
            "page": 1,
            "page_size": 1,
            "search": "nid-de-poule",
            "category": "Voirie",
            "sort_by": "title",
            "sort_order": "asc",
        },
    )
    assert page.status_code == 200
    assert page.json()["total"] == 1
    assert page.json()["total_pages"] == 1
    assert page.json()["items"][0]["id"] == open_id

    first_page = await client.get(
        REQUESTS,
        params={"page": 1, "page_size": 1, "sort_by": "title", "sort_order": "asc"},
    )
    second_page = await client.get(
        REQUESTS,
        params={"page": 2, "page_size": 1, "sort_by": "title", "sort_order": "asc"},
    )
    assert first_page.json()["total"] == 2
    assert first_page.json()["total_pages"] == 2
    assert first_page.json()["items"][0]["id"] == resolved_id
    assert second_page.json()["items"][0]["id"] == open_id

    detail = await client.get(f"{REQUESTS}/{resolved_id}")
    assert detail.status_code == 200
    assert detail.json()["citizen_id"] == citizen_id

    dashboard = await client.get("/api/v1/dashboard")
    dashboard_body = dashboard.json()
    assert dashboard.status_code == 200
    assert dashboard_body["open_requests"] == 1
    assert dashboard_body["resolved_requests"] == 1
    assert dashboard_body["today_interventions"] == 1
    assert len(dashboard_body["category_distribution"]) == 7
    assert len(dashboard_body["requests_last_7_days"]) == 7
    assert sum(item["count"] for item in dashboard_body["requests_last_7_days"]) == 2

    update = await client.put(
        f"{REQUESTS}/{open_id}",
        json={"status": "En cours", "assigned_agent_id": agent_id},
    )
    assert update.status_code == 200
    assert update.json()["status"] == "En cours"
    assert update.json()["assigned_agent_id"] == agent_id
    updated_dashboard = (await client.get("/api/v1/dashboard")).json()
    assert updated_dashboard["in_progress_requests"] == 1
    assert updated_dashboard["open_requests"] == 0

    deleted = await client.delete(f"{REQUESTS}/{open_id}")
    assert deleted.status_code == 204
    assert (await client.get(f"{REQUESTS}/{open_id}")).status_code == 404


async def test_request_creation_requires_existing_citizen(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        REQUESTS,
        json={
            "title": "Signalement",
            "description": "Description",
            "category": "Autre",
            "citizen_id": "absent",
            "location": "Centre-ville",
        },
    )

    assert response.status_code == 404


def _request(citizen_id: str, **overrides: object) -> dict:
    return {
        "title": "Signalement",
        "description": "Description",
        "category": "Autre",
        "citizen_id": citizen_id,
        "location": "Centre-ville",
        **overrides,
    }


async def test_request_assignment_requires_existing_active_agent(
    client: httpx.AsyncClient,
) -> None:
    citizen = (
        await client.post("/api/v1/users", json={"email": "c@example.com", "name": "Citoyen"})
    ).json()
    agent = (
        await client.post(
            "/api/v1/agents",
            json={"email": "a@example.com", "name": "Agent", "department": "Eau"},
        )
    ).json()

    unknown = await client.post(REQUESTS, json=_request(citizen["id"], assigned_agent_id="absent"))
    assert unknown.status_code == 404
    assert unknown.json()["error"] == "AgentNotFoundError"

    created = await client.post(REQUESTS, json=_request(citizen["id"], assigned_agent_id=agent["id"]))
    assert created.status_code == 201

    await client.post(f"/api/v1/agents/{agent['id']}/deactivate")

    refused = await client.post(REQUESTS, json=_request(citizen["id"], assigned_agent_id=agent["id"]))
    assert refused.status_code == 400
    assert refused.json()["error"] == "AgentInactiveError"

    # Une demande déjà attribuée à l'agent désactivé reste modifiable.
    edited = await client.put(f"{REQUESTS}/{created.json()['id']}", json={"status": "En cours"})
    assert edited.status_code == 200
    assert edited.json()["assigned_agent_id"] == agent["id"]


async def test_request_coordinates_are_optional_and_validated(client: httpx.AsyncClient) -> None:
    citizen = (
        await client.post("/api/v1/users", json={"email": "g@example.com", "name": "Citoyen"})
    ).json()

    without = await client.post(REQUESTS, json=_request(citizen["id"]))
    assert without.json()["latitude"] is None

    located = await client.post(
        REQUESTS, json=_request(citizen["id"], latitude=-18.9068, longitude=47.5244)
    )
    assert located.status_code == 201
    assert (located.json()["latitude"], located.json()["longitude"]) == (-18.9068, 47.5244)

    invalid = await client.post(REQUESTS, json=_request(citizen["id"], latitude=120))
    assert invalid.status_code == 422
