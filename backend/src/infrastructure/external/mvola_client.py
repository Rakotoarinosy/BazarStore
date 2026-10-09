"""Client de l'API MVola Merchant Pay (paiement Mobile Money Telma).

Flux : token OAuth2 (client_credentials) → initiation d'un paiement marchand → le client valide
sur son téléphone → on lit le statut (polling) jusqu'à `completed` ou `failed`.
En sandbox (devapi.mvola.mg), seuls les numéros de test 0343500003 / 0343500004 sont acceptés.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import httpx

from src.domain.errors import DomainError
from src.infrastructure.config import Settings, get_settings

logger = logging.getLogger(__name__)

MERCHANT_PAY_PATH = "/mvola/mm/transactions/type/merchantpay/1.0.0/"


class MvolaUnavailableError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "MVola est indisponible ou a rencontré une erreur interne. Réessayez plus tard."
        )


class MvolaPaymentRejectedError(DomainError):
    def __init__(self) -> None:
        super().__init__("MVola a refusé la demande de paiement. Vérifiez le numéro et réessayez.")


@dataclass(frozen=True)
class MvolaInitiation:
    server_correlation_id: str
    status: str


@dataclass(frozen=True)
class MvolaStatus:
    status: str  # pending | completed | failed
    transaction_reference: str | None


class MvolaClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.mvola_consumer_key or not settings.mvola_consumer_secret:
            raise MvolaUnavailableError()
        self._settings = settings
        self._base_url = settings.mvola_base_url.rstrip("/")
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._lock = threading.Lock()

    def initiate_payment(
        self, *, amount: int, customer_msisdn: str, description: str, reference: str
    ) -> MvolaInitiation:
        merchant = self._settings.mvola_merchant_msisdn
        partner = self._settings.mvola_partner_name
        body = {
            "amount": str(amount),
            "currency": "Ar",
            "descriptionText": description[:50],
            "requestingOrganisationTransactionReference": reference,
            "requestDate": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "originalTransactionReference": reference,
            "debitParty": [{"key": "msisdn", "value": customer_msisdn}],
            "creditParty": [{"key": "msisdn", "value": merchant}],
            "metadata": [
                {"key": "partnerName", "value": partner},
                {"key": "fc", "value": "USD"},
                {"key": "amountFc", "value": "1"},
            ],
        }
        headers = self._headers()
        if self._settings.mvola_callback_url:
            headers["X-Callback-URL"] = self._settings.mvola_callback_url

        data = self._request("POST", MERCHANT_PAY_PATH, headers=headers, json=body)
        correlation_id = data.get("serverCorrelationId")
        if not isinstance(correlation_id, str) or not correlation_id:
            logger.warning("MVola initiation without serverCorrelationId: %s", data)
            raise MvolaPaymentRejectedError()

        return MvolaInitiation(
            server_correlation_id=correlation_id, status=str(data.get("status", "pending"))
        )

    def get_status(self, server_correlation_id: str) -> MvolaStatus:
        data = self._request(
            "GET", f"{MERCHANT_PAY_PATH}status/{server_correlation_id}", headers=self._headers()
        )
        reference = data.get("objectReference")

        return MvolaStatus(
            status=str(data.get("status", "pending")).lower(),
            transaction_reference=reference if isinstance(reference, str) and reference else None,
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token()}",
            "Version": "1.0",
            "X-CorrelationID": str(uuid4()),
            "UserLanguage": "FR",
            "UserAccountIdentifier": f"msisdn;{self._settings.mvola_merchant_msisdn}",
            "partnerName": self._settings.mvola_partner_name,
            "Cache-Control": "no-cache",
        }

    def _access_token(self) -> str:
        with self._lock:
            if self._token and time.monotonic() < self._token_expires_at:
                return self._token
            try:
                response = httpx.post(
                    f"{self._base_url}/token",
                    auth=(
                        self._settings.mvola_consumer_key or "",
                        self._settings.mvola_consumer_secret or "",
                    ),
                    data={"grant_type": "client_credentials", "scope": "EXT_INT_MVOLA_SCOPE"},
                    headers={"Cache-Control": "no-cache"},
                    timeout=15,
                )
            except httpx.HTTPError as exc:
                raise MvolaUnavailableError() from exc
            if not response.is_success:
                logger.warning("MVola token request failed (HTTP %s)", response.status_code)
                raise MvolaUnavailableError()

            payload = response.json()
            self._token = str(payload["access_token"])
            # Marge d'une minute pour ne jamais envoyer un token sur le point d'expirer.
            self._token_expires_at = time.monotonic() + max(
                int(payload.get("expires_in", 3600)) - 60, 30
            )
            return self._token

    def _request(self, method: str, path: str, **kwargs: object) -> dict[str, object]:
        try:
            response = httpx.request(method, f"{self._base_url}{path}", timeout=20, **kwargs)  # type: ignore[arg-type]
        except httpx.HTTPError as exc:
            raise MvolaUnavailableError() from exc

        if response.status_code >= 500:
            logger.warning(
                "MVola %s %s failed (HTTP %s): %s",
                method,
                path,
                response.status_code,
                response.text[:500],
            )
            raise MvolaUnavailableError()
        if not response.is_success:
            logger.warning(
                "MVola %s %s rejected (HTTP %s): %s",
                method,
                path,
                response.status_code,
                response.text[:500],
            )
            raise MvolaPaymentRejectedError()

        data = response.json()
        return data if isinstance(data, dict) else {}


_client: MvolaClient | None = None
_client_lock = threading.Lock()


def get_mvola_client() -> MvolaClient:
    """Instance partagée : le token OAuth est réutilisé entre les requêtes."""
    global _client
    with _client_lock:
        if _client is None:
            _client = MvolaClient(get_settings())
        return _client
