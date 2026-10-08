import httpx
import pytest

pytestmark = pytest.mark.anyio


async def test_scalar_docs_use_docs_route_and_openapi_schema(
    client: httpx.AsyncClient,
) -> None:
    docs_response = await client.get("/docs")
    openapi_response = await client.get("/openapi.json")
    old_scalar_response = await client.get("/scalar")

    assert docs_response.status_code == 200
    assert "text/html" in docs_response.headers["content-type"]
    assert "/openapi.json" in docs_response.text
    assert openapi_response.status_code == 200
    schema = openapi_response.json()
    assert "/api/v1/requests" in schema["paths"]
    assert "/api/v1/requests/{request_id}" in schema["paths"]
    assert "/api/v1/dashboard" in schema["paths"]
    assert old_scalar_response.status_code == 404
