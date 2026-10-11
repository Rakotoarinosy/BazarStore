"""Client JSON-2 Odoo : authentification, délais, nouvelles tentatives, pagination (sans réseau)."""

import json
from collections.abc import Callable

import httpx
import pytest

from src.infrastructure.config.settings import Settings
from src.infrastructure.external import odoo_client
from src.infrastructure.external.odoo_client import (
    OdooCatalogClient,
    OdooClient,
    OdooSyncUnavailableError,
    OdooUnavailableError,
)

Handler = Callable[[httpx.Request], httpx.Response]


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "odoo_url": "https://odoo.test/",
        "odoo_db": "bazarstore_odoo",
        "odoo_api_key": "test-api-key",
        "odoo_max_retries": 2,
        "odoo_retry_backoff_seconds": 1.0,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def make_client(handler: Handler, sleeps: list[float], **overrides: object) -> OdooClient:
    return OdooClient(
        settings(**overrides),
        correlation_id="corr-1",
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
    )


def test_call_sends_api_key_database_and_correlation_id() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[{"id": 1}])

    result = make_client(handler, []).call("product.product", "search_read", limit=5)

    request = seen[0]
    assert result == [{"id": 1}]
    assert request.method == "POST"
    assert str(request.url) == "https://odoo.test/json/2/product.product/search_read"
    assert request.headers["Authorization"] == "bearer test-api-key"
    assert request.headers["X-Odoo-Database"] == "bazarstore_odoo"
    assert request.headers["X-Correlation-ID"] == "corr-1"
    assert json.loads(request.content) == {"limit": 5}


def test_transient_failures_are_retried_with_exponential_backoff() -> None:
    attempts: list[int] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) == 1:
            raise httpx.ReadTimeout("slow", request=request)
        if len(attempts) == 2:
            return httpx.Response(503)
        return httpx.Response(200, json=True)

    assert make_client(handler, sleeps).call("res.partner", "check_access_rights") is True
    assert len(attempts) == 3
    assert sleeps == [1.0, 2.0]


def test_gives_up_after_max_retries() -> None:
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(OdooUnavailableError, match="3 tentative"):
        make_client(handler, sleeps).call("product.product", "search_read")
    assert sleeps == [1.0, 2.0]


@pytest.mark.parametrize(
    ("status", "body", "message"),
    [
        (401, {"name": "werkzeug.exceptions.Unauthorized"}, "ODOO_API_KEY"),
        (403, {}, "refusé l'accès"),
        (422, {"message": "Invalid field 'free_qty'"}, "Invalid field 'free_qty'"),
        (404, {"message": "the model 'x' does not exist"}, "HTTP 404"),
    ],
)
def test_client_errors_are_not_retried(status: int, body: object, message: str) -> None:
    calls: list[int] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(status, json=body)

    with pytest.raises(OdooUnavailableError, match=message):
        make_client(handler, sleeps).call("product.product", "search_read")
    assert calls == [1]
    assert sleeps == []


def test_api_key_is_never_part_of_error_messages() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={})

    with pytest.raises(OdooUnavailableError) as error:
        make_client(handler, []).call("product.product", "search_read")
    assert "test-api-key" not in error.value.message


@pytest.mark.parametrize("missing", ["odoo_url", "odoo_db", "odoo_api_key"])
def test_incomplete_configuration_is_refused(missing: str) -> None:
    with pytest.raises(OdooSyncUnavailableError):
        OdooClient(settings(**{missing: None}), correlation_id="corr-1")


def test_catalog_pages_until_a_short_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(odoo_client, "PAGE_SIZE", 2)
    bodies: list[dict[str, object]] = []
    rows = [{"id": 1}, {"id": 2}, {"id": 3}]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        return httpx.Response(200, json=rows[body["offset"] : body["offset"] + body["limit"]])

    client = make_client(handler, [], odoo_warehouse_id=3)
    pages = list(
        OdooCatalogClient(client, settings(odoo_warehouse_id=3)).product_pages(linked_ids=[9])
    )

    assert pages == [[{"id": 1}, {"id": 2}], [{"id": 3}]]
    assert [body["offset"] for body in bodies] == [0, 2]
    first = bodies[0]
    # Produits déjà liés lus même archivés, pour pouvoir les retirer de la vente.
    assert first["context"] == {"active_test": False, "lang": "fr_FR", "warehouse_id": 3}
    assert ["id", "in", [9]] in first["domain"]  # type: ignore[operator]
    assert "free_qty" in first["fields"]  # type: ignore[operator]


def test_single_product_resync_filters_on_its_id() -> None:
    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=[])

    client = make_client(handler, [])
    pages = list(OdooCatalogClient(client, settings()).product_pages(linked_ids=[], only_ids=[42]))

    assert pages == []
    assert bodies[0]["domain"] == [["id", "in", [42]]]


def test_unexpected_payload_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"not": "a list"})

    client = make_client(handler, [])
    with pytest.raises(OdooUnavailableError, match="inattendue"):
        list(OdooCatalogClient(client, settings()).product_pages(linked_ids=[]))
