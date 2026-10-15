"""Paiement par carte via la passerelle de paiement « ecommerce_monitoring ».

BazarStore ne détient plus de clé Stripe : il crée une intention de paiement (montant en MGA)
sur la passerelle, redirige le client vers `checkout_url` (Stripe Checkout en production,
simulateur en local et en CI), puis apprend le résultat de deux façons :
  - webhook signé HMAC-SHA256 (`X-Gateway-Signature: t=<unix>,v1=<hex>`) ;
  - relecture de l'intention (GET) au retour du client, si le webhook n'est pas arrivé.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass

import httpx

from src.domain.errors import DomainError
from src.infrastructure.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Une signature plus vieille que ça est refusée (rejeu d'un webhook intercepté).
SIGNATURE_TOLERANCE_SECONDS = 300


class PaymentGatewayUnavailableError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "Le paiement par carte est indisponible pour le moment. Réessayez plus tard."
        )


class InvalidGatewayWebhookError(DomainError):
    def __init__(self) -> None:
        super().__init__("Notification de paiement invalide.")


@dataclass(frozen=True)
class CheckoutLine:
    name: str
    unit_price_ar: int
    quantity: int


@dataclass(frozen=True)
class GatewayCheckout:
    url: str
    intent_id: str


@dataclass(frozen=True)
class GatewayIntentState:
    intent_id: str
    order_id: str
    status: str  # pending | success | failed | cancelled

    @property
    def paid(self) -> bool:
        return self.status == "success"

    @property
    def closed_unpaid(self) -> bool:
        return self.status in {"failed", "cancelled"}


def _state(data: dict[str, object]) -> GatewayIntentState:
    return GatewayIntentState(
        intent_id=str(data["id"]),
        order_id=str(data["merchant_reference"]),
        status=str(data["status"]),
    )


class PaymentGateway:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        if not settings.payment_gateway_url or not settings.payment_gateway_api_key:
            raise PaymentGatewayUnavailableError()
        self._webhook_secret = settings.payment_gateway_webhook_secret
        self._http = httpx.Client(
            base_url=settings.payment_gateway_url.rstrip("/") + "/v1",
            headers={"Authorization": f"Bearer {settings.payment_gateway_api_key}"},
            timeout=10.0,
            transport=transport,
        )

    def _request(self, method: str, path: str, **kwargs: object) -> dict[str, object]:
        try:
            response = self._http.request(method, path, **kwargs)  # type: ignore[arg-type]
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Payment gateway %s %s failed: %s", method, path, exc)
            raise PaymentGatewayUnavailableError() from exc
        return response.json()  # type: ignore[no-any-return]

    def create_checkout(
        self,
        *,
        order_id: str,
        reference: str,
        amount_ar: int,
        customer_name: str,
        customer_email: str,
        lines: list[CheckoutLine],
        success_url: str,
        cancel_url: str,
    ) -> GatewayCheckout:
        data = self._request(
            "POST",
            "/payment-intents",
            json={
                "merchant_reference": order_id,
                "amount": amount_ar,
                "currency": "MGA",
                "description": f"Commande {reference}",
                "order_reference": reference,
                "customer_name": customer_name,
                "customer_email": customer_email,
                "lines": [
                    {"name": line.name, "unit_amount": line.unit_price_ar, "quantity": line.quantity}
                    for line in lines
                ],
                "success_url": success_url,
                "cancel_url": cancel_url,
            },
        )
        return GatewayCheckout(url=str(data["checkout_url"]), intent_id=str(data["id"]))

    def get_intent_state(self, intent_id: str) -> GatewayIntentState:
        return _state(self._request("GET", f"/payment-intents/{intent_id}"))

    def parse_webhook(self, payload: bytes, signature: str | None) -> GatewayIntentState:
        """Vérifie la signature HMAC et la fraîcheur, puis renvoie l'état de l'intention."""
        if not self._webhook_secret:
            raise PaymentGatewayUnavailableError()
        if not verify_signature(payload, signature, self._webhook_secret):
            logger.warning("Rejected payment gateway webhook (bad signature)")
            raise InvalidGatewayWebhookError()
        try:
            return _state(json.loads(payload)["data"])
        except (ValueError, KeyError, TypeError) as exc:
            raise InvalidGatewayWebhookError() from exc


def verify_signature(payload: bytes, header: str | None, secret: str) -> bool:
    try:
        parts = dict(part.split("=", 1) for part in (header or "").split(","))
        timestamp = int(parts["t"])
        signature = parts["v1"]
    except (ValueError, KeyError):
        return False
    if abs(time.time() - timestamp) > SIGNATURE_TOLERANCE_SECONDS:
        return False
    expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256)
    return hmac.compare_digest(signature, expected.hexdigest())


def get_payment_gateway() -> PaymentGateway:
    return PaymentGateway(get_settings())
