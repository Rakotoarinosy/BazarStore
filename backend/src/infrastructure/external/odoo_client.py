"""Client de l'API externe JSON-2 d'Odoo 19 (`POST /json/2/<modèle>/<méthode>`).

- Authentification : clé API d'un utilisateur Odoo dédié (`Authorization: bearer …`), base
  choisie par l'en-tête `X-Odoo-Database`. La clé n'est jamais journalisée.
- Délai maximal par appel (ODOO_TIMEOUT_SECONDS) : un Odoo lent ne bloque pas BazarStore.
- Erreurs temporaires (délai, connexion, 429, 5xx) : nouvelles tentatives espacées
  (backoff exponentiel), au plus ODOO_MAX_RETRIES. Les autres erreurs (clé refusée, requête
  invalide) échouent tout de suite : les rejouer ne changerait rien.
- Chaque appel porte l'identifiant de corrélation de la synchronisation (`X-Correlation-ID`),
  repris dans les journaux BazarStore et dans `integration_sync_runs`.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from types import TracebackType

import httpx

from src.domain.errors import DomainError
from src.domain.integration import OdooCatalogSource
from src.infrastructure.config import Settings

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_BACKOFF_SECONDS = 30.0
PAGE_SIZE = 200

# Champs lus sur product.product (voir src.domain.integration.parse_odoo_product).
# `free_qty` (stock libre, hors réservations) nécessite le module Inventaire (`stock`).
ODOO_PRODUCT_FIELDS = [
    "id",
    "default_code",
    "display_name",
    "description_sale",
    "lst_price",
    "free_qty",
    "active",
    "sale_ok",
    "type",
    "categ_id",
]


class OdooSyncUnavailableError(DomainError):
    def __init__(self) -> None:
        super().__init__("L'intégration Odoo est désactivée ou incomplètement configurée.")


class OdooUnavailableError(DomainError):
    """Odoo injoignable, trop lent, ou appel refusé : la synchronisation est interrompue."""


class OdooClient:
    def __init__(
        self,
        settings: Settings,
        *,
        correlation_id: str,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not (settings.odoo_url and settings.odoo_db and settings.odoo_api_key):
            raise OdooSyncUnavailableError()
        self.correlation_id = correlation_id
        self._max_retries = max(settings.odoo_max_retries, 0)
        self._backoff = settings.odoo_retry_backoff_seconds
        self._sleep = sleep
        self._http = httpx.Client(
            base_url=settings.odoo_url.rstrip("/"),
            timeout=settings.odoo_timeout_seconds,
            transport=transport,
            headers={
                "Authorization": f"bearer {settings.odoo_api_key}",
                "X-Odoo-Database": settings.odoo_db,
                "X-Correlation-ID": correlation_id,
                "User-Agent": "BazarStore-Integration/1.0",
            },
        )

    def __enter__(self) -> OdooClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._http.close()

    def call(self, model: str, method: str, **params: object) -> object:
        """Appelle `model.method(**params)` ; `ids` et `context` sont des paramètres nommés."""
        path = f"/json/2/{model}/{method}"
        attempt = 0
        while True:
            started = time.monotonic()
            try:
                response = self._http.post(path, json=params)
            except httpx.TransportError as exc:  # délai dépassé, connexion refusée…
                failure = type(exc).__name__
            else:
                if response.status_code < 400:
                    return self._json(response, path)
                if response.status_code not in RETRYABLE_STATUS:
                    raise OdooUnavailableError(self._describe(response, path))
                failure = f"HTTP {response.status_code}"

            logger.warning(
                "Odoo call %s failed (%s) after %.0f ms, attempt %d/%d [correlation_id=%s]",
                path,
                failure,
                (time.monotonic() - started) * 1000,
                attempt + 1,
                self._max_retries + 1,
                self.correlation_id,
            )
            if attempt >= self._max_retries:
                raise OdooUnavailableError(
                    f"Odoo est injoignable ou trop lent ({failure}) "
                    f"après {attempt + 1} tentative(s)."
                )
            self._sleep(min(self._backoff * 2**attempt, MAX_BACKOFF_SECONDS))
            attempt += 1

    @staticmethod
    def _json(response: httpx.Response, path: str) -> object:
        try:
            return response.json()
        except ValueError as exc:
            raise OdooUnavailableError(f"Réponse illisible d'Odoo pour {path}.") from exc

    @staticmethod
    def _describe(response: httpx.Response, path: str) -> str:
        if response.status_code in {401, 403}:
            return (
                f"Odoo a refusé l'accès (HTTP {response.status_code}) : "
                "vérifiez ODOO_API_KEY, ODOO_DB et les droits de l'utilisateur d'intégration."
            )
        try:
            body = response.json()
            message = body.get("message") if isinstance(body, dict) else None
        except ValueError:
            message = None
        detail = f" : {str(message)[:200]}" if message else ""
        return f"Odoo a rejeté l'appel {path} (HTTP {response.status_code}){detail}"


class OdooCatalogClient(OdooCatalogSource):
    """Lecture paginée de `product.product` (archivés compris pour les produits déjà liés)."""

    def __init__(self, client: OdooClient, settings: Settings) -> None:
        self._client = client
        self._context: dict[str, object] = {"active_test": False, "lang": settings.odoo_lang}
        if settings.odoo_warehouse_id:
            # free_qty calculé sur cet entrepôt uniquement.
            self._context["warehouse_id"] = settings.odoo_warehouse_id

    def product_pages(
        self, *, linked_ids: Sequence[int], only_ids: Sequence[int] | None = None
    ) -> Iterator[list[Mapping[str, object]]]:
        if only_ids is not None:
            domain: list[object] = [["id", "in", list(only_ids)]]
        else:
            domain = [
                "|",
                ["id", "in", list(linked_ids)],
                "&",
                "&",
                ["active", "=", True],
                ["sale_ok", "=", True],
                ["type", "=", "consu"],
            ]
        offset = 0
        while True:
            page = self._client.call(
                "product.product",
                "search_read",
                domain=domain,
                fields=ODOO_PRODUCT_FIELDS,
                offset=offset,
                limit=PAGE_SIZE,
                order="id",
                context=self._context,
            )
            if not isinstance(page, list) or not all(isinstance(row, dict) for row in page):
                raise OdooUnavailableError("Réponse inattendue d'Odoo pour product.product.")
            if page:
                yield page
            if len(page) < PAGE_SIZE:
                return
            offset += PAGE_SIZE


@contextmanager
def open_odoo_catalog(settings: Settings, correlation_id: str) -> Iterator[OdooCatalogSource]:
    """Source catalogue Odoo pour une synchronisation ; la connexion HTTP est fermée à la fin."""
    with OdooClient(settings, correlation_id=correlation_id) as client:
        yield OdooCatalogClient(client, settings)
