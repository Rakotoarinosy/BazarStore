"""Client de l'API de paiement Stripe externe (projet « E-commerce & Monitoring API »).

Flux : POST /payments/checkout?user_id=<référence commande>&amount=<montant> → URL Stripe Checkout
→ le client paie sur Stripe → l'API externe enregistre le paiement (status « success »)
→ BazarStore le retrouve dans GET /payments/ grâce à la référence de commande.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from src.domain.errors import DomainError
from src.infrastructure.config import Settings, get_settings

logger = logging.getLogger(__name__)

PAID_STATUSES = {"success", "succeeded", "paid", "completed", "complete"}


class CardPaymentUnavailableError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "Le paiement par carte est indisponible pour le moment. Réessayez plus tard."
        )


@dataclass(frozen=True)
class CardCheckout:
    checkout_url: str
    session_id: str | None


class CardPaymentGateway:
    def __init__(self, settings: Settings) -> None:
        if not settings.card_payment_api_url:
            raise CardPaymentUnavailableError()
        self._base_url = settings.card_payment_api_url.rstrip("/")
        self._ar_per_unit = settings.card_payment_ar_per_unit

    def to_gateway_amount(self, amount_ar: int) -> float:
        """Convertit les ariary en devise de l'API Stripe (ex. EUR), arrondi au centime."""
        return max(round(amount_ar / self._ar_per_unit, 2), 0.5)

    def create_checkout(self, *, reference: str, amount_ar: int) -> CardCheckout:
        data = self._request(
            "POST",
            "/payments/checkout",
            params={"user_id": reference, "amount": self.to_gateway_amount(amount_ar)},
        )
        if not isinstance(data, dict):
            raise CardPaymentUnavailableError()
        # Format de réponse toléré : {"url"} / {"checkout_url"} / {"session_url"} (+ id de session).
        url = next(
            (
                data[key]
                for key in ("url", "checkout_url", "session_url")
                if isinstance(data.get(key), str)
            ),
            None,
        )
        if not url or not url.startswith("https://"):
            logger.warning("Card checkout response without a usable URL: %s", str(data)[:300])
            raise CardPaymentUnavailableError()
        session_id = next(
            (
                data[key]
                for key in ("session_id", "id", "sessionId")
                if isinstance(data.get(key), str)
            ),
            None,
        )
        return CardCheckout(checkout_url=url, session_id=session_id)

    def is_paid(self, *, reference: str, amount_ar: int) -> bool:
        """Cherche un paiement réussi pour cette référence de commande et ce montant."""
        payments = self._request("GET", "/payments/")
        if not isinstance(payments, list):
            raise CardPaymentUnavailableError()
        expected = self.to_gateway_amount(amount_ar)
        for payment in payments:
            if not isinstance(payment, dict) or payment.get("user_id") != reference:
                continue
            status = str(payment.get("status", "")).lower()
            amount = payment.get("amount")
            if (
                status in PAID_STATUSES
                and isinstance(amount, int | float)
                and abs(amount - expected) < 0.01
            ):
                return True
        return False

    def _request(self, method: str, path: str, **kwargs: object) -> object:
        try:
            response = httpx.request(method, f"{self._base_url}{path}", timeout=20, **kwargs)  # type: ignore[arg-type]
        except httpx.HTTPError as exc:
            raise CardPaymentUnavailableError() from exc
        if not response.is_success:
            logger.warning(
                "Card payment API %s %s failed (HTTP %s): %s",
                method,
                path,
                response.status_code,
                response.text[:300],
            )
            raise CardPaymentUnavailableError()
        return response.json()


def get_card_payment_gateway() -> CardPaymentGateway:
    return CardPaymentGateway(get_settings())
