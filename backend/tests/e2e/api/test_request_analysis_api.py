from collections.abc import Iterator
from datetime import UTC, datetime

import httpx
import pytest

from src.domain.agent import Agent
from src.domain.citizen_request import (
    AnalysisUnavailableError,
    CitizenRequest,
    RequestAnalysis,
    RequestAnalyzer,
    RequestCategory,
    RequestPriority,
)
from src.domain.user import Role, User
from src.features.citizen_request.router import get_request_analyzer
from src.infrastructure.security.deps import get_current_user
from src.main import app

pytestmark = pytest.mark.anyio

REQUESTS = "/api/v1/requests"


class FakeAnalyzer(RequestAnalyzer):
    """Recommande l'agent dont le département correspond, ou l'id imposé par le test."""

    def __init__(self) -> None:
        self.forced_agent_id: str | None = None
        self.fail = False
        self.seen_candidates: list[Agent] = []

    def analyze(self, request: CitizenRequest, candidates: list[Agent]) -> RequestAnalysis:
        if self.fail:
            raise AnalysisUnavailableError()
        self.seen_candidates = candidates
        match = next((a for a in candidates if a.department == "Éclairage public"), None)

        return RequestAnalysis(
            category=RequestCategory.PUBLIC_LIGHTING,
            priority=RequestPriority.HIGH,
            summary="Panne généralisée de l'éclairage dans la rue.",
            recommended_agent_id=self.forced_agent_id or (match.id if match else None),
            reason="Plusieurs foyers touchés depuis plus de 12 heures.",
        )


def _user(role: Role) -> User:
    return User(
        id=f"{role.value}-id",
        email=f"{role.value}@test.mg",
        name=role.value,
        created_at=datetime.now(UTC),
        password_hash="",
        role=role,
    )


@pytest.fixture
def analyzer() -> Iterator[FakeAnalyzer]:
    fake = FakeAnalyzer()
    app.dependency_overrides[get_request_analyzer] = lambda: fake
    # ADMIN : passe tous les contrôles de rôle (création d'utilisateurs et d'agents comprise).
    app.dependency_overrides[get_current_user] = lambda: _user(Role.ADMIN)
    yield fake
    app.dependency_overrides.pop(get_request_analyzer, None)
    app.dependency_overrides.pop(get_current_user, None)


async def _request_with_agents(client: httpx.AsyncClient) -> tuple[str, dict, dict]:
    citizen = (
        await client.post(
            "/api/v1/users",
            json={"email": "c@test.mg", "name": "Rina", "password": "Motdepasse123"},
        )
    ).json()
    marc = (
        await client.post(
            "/api/v1/agents",
            json={"name": "Marc Rabe", "email": "marc@test.mg", "department": "Éclairage public"},
        )
    ).json()
    off = (
        await client.post(
            "/api/v1/agents",
            json={"name": "Hery", "email": "hery@test.mg", "department": "Éclairage public"},
        )
    ).json()
    await client.post(f"/api/v1/agents/{off['id']}/deactivate")
    request = (
        await client.post(
            REQUESTS,
            json={
                "title": "Rue dans le noir",
                "description": "Depuis hier soir, toute notre rue est plongée dans le noir.",
                "category": "Autre",
                "citizen_id": citizen["id"],
                "location": "Isoraka",
            },
        )
    ).json()

    return request["id"], marc, off


async def test_analyze_returns_suggestion_without_modifying_request(
    client: httpx.AsyncClient, analyzer: FakeAnalyzer
) -> None:
    request_id, marc, off = await _request_with_agents(client)

    response = await client.post(f"{REQUESTS}/{request_id}/analyze")

    assert response.status_code == 200
    body = response.json()
    assert body["category"] == "Éclairage public"
    assert body["priority"] == "Haute"
    assert body["summary"] and body["reason"]
    assert body["recommended_agent"]["id"] == marc["id"]
    assert body["recommended_agent"]["name"] == "Marc Rabe"
    # Seuls les agents actifs sont proposés à l'IA.
    assert [a.id for a in analyzer.seen_candidates] == [marc["id"]]
    # Simple suggestion : la demande n'est pas modifiée.
    assert (await client.get(f"{REQUESTS}/{request_id}")).json()["category"] == "Autre"


async def test_hallucinated_agent_id_is_dropped(
    client: httpx.AsyncClient, analyzer: FakeAnalyzer
) -> None:
    request_id, _, off = await _request_with_agents(client)

    for invented_id in ("agent-inexistant", off["id"]):
        analyzer.forced_agent_id = invented_id
        body = (await client.post(f"{REQUESTS}/{request_id}/analyze")).json()
        assert body["recommended_agent"] is None


async def test_ai_failure_returns_503(client: httpx.AsyncClient, analyzer: FakeAnalyzer) -> None:
    request_id, _, _ = await _request_with_agents(client)
    analyzer.fail = True

    response = await client.post(f"{REQUESTS}/{request_id}/analyze")

    assert response.status_code == 503
    assert response.json()["error"] == "AnalysisUnavailableError"


async def test_unknown_request_returns_404(
    client: httpx.AsyncClient, analyzer: FakeAnalyzer
) -> None:
    assert (await client.post(f"{REQUESTS}/absent/analyze")).status_code == 404


async def test_citizen_cannot_analyze(client: httpx.AsyncClient, analyzer: FakeAnalyzer) -> None:
    app.dependency_overrides[get_current_user] = lambda: _user(Role.CITIZEN)

    assert (await client.post(f"{REQUESTS}/x/analyze")).status_code == 403


async def test_missing_api_key_returns_503(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.infrastructure.config import get_settings

    monkeypatch.setattr(get_settings(), "gemini_api_key", None)
    app.dependency_overrides[get_current_user] = lambda: _user(Role.ADMIN)
    try:
        response = await client.post(f"{REQUESTS}/x/analyze")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]
