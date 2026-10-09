import httpx
import pytest

pytestmark = pytest.mark.anyio


async def test_api_responses_carry_security_headers(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["x-xss-protection"] == "0"
    assert response.headers["content-security-policy"].startswith("default-src 'none'")
    # HSTS uniquement en production (HTTPS).
    assert "strict-transport-security" not in response.headers


async def test_docs_page_allows_scalar_assets(client: httpx.AsyncClient) -> None:
    response = await client.get("/docs")

    assert "https://cdn.jsdelivr.net" in response.headers["content-security-policy"]
    assert response.headers["x-frame-options"] == "DENY"
