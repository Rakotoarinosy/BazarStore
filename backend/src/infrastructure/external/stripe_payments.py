"""Paiement par carte via Stripe Checkout (repris du backend « E-commerce & Monitoring »).

Flux : session Checkout créée avec les lignes de la commande → le client paie sur la page Stripe
→ Stripe le renvoie sur « Mes commandes » → BazarStore relit la session (payment_status = paid).
Le webhook signé `checkout.session.completed` confirme aussi le paiement si le client ne revient pas.

L'ariary (MGA) est une devise « zero-decimal » chez Stripe : 1 328 000 Ar s'envoie tel quel.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import stripe

from src.domain.errors import DomainError
from src.infrastructure.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Devises sans centimes chez Stripe (montant envoyé en unités entières).
ZERO_DECIMAL_CURRENCIES = {
    "mga",
    "jpy",
    "krw",
    "xof",
    "xaf",
    "kmf",
    "bif",
    "djf",
    "gnf",
    "rwf",
    "ugx",
}
PAID_EVENTS = {"checkout.session.completed", "checkout.session.async_payment_succeeded"}


class StripeUnavailableError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "Le paiement par carte est indisponible pour le moment. Réessayez plus tard."
        )


class InvalidStripeWebhookError(DomainError):
    def __init__(self) -> None:
        super().__init__("Notification Stripe invalide.")


@dataclass(frozen=True)
class CheckoutLine:
    name: str
    unit_price_ar: int
    quantity: int


@dataclass(frozen=True)
class StripeCheckout:
    url: str
    session_id: str


@dataclass(frozen=True)
class StripeSessionState:
    order_id: str | None
    paid: bool
    expired: bool


class StripePayments:
    def __init__(self, settings: Settings) -> None:
        if not settings.stripe_secret_key:
            raise StripeUnavailableError()
        self._client = stripe.StripeClient(settings.stripe_secret_key)
        self._webhook_secret = settings.stripe_webhook_secret
        self._currency = settings.stripe_currency.lower()
        self._ar_per_unit = settings.stripe_ar_per_unit

    def to_stripe_amount(self, amount_ar: int) -> int:
        """Montant dans la plus petite unité de la devise Stripe."""
        if self._currency == "mga":
            return amount_ar
        converted = amount_ar / self._ar_per_unit  # ex. ariary → euros
        if self._currency in ZERO_DECIMAL_CURRENCIES:
            return round(converted)
        return round(converted * 100)  # centimes

    def create_checkout(
        self,
        *,
        order_id: str,
        reference: str,
        customer_email: str,
        lines: list[CheckoutLine],
        success_url: str,
        cancel_url: str,
    ) -> StripeCheckout:
        try:
            session = self._client.v1.checkout.sessions.create(
                params={
                    # Moyens de paiement (carte…) gérés dans le dashboard Stripe :
                    # l'API refuse désormais `payment_method_types`.
                    "mode": "payment",
                    "line_items": [
                        {
                            "price_data": {
                                "currency": self._currency,
                                "product_data": {"name": line.name[:250]},
                                "unit_amount": self.to_stripe_amount(line.unit_price_ar),
                            },
                            "quantity": line.quantity,
                        }
                        for line in lines
                    ],
                    "client_reference_id": order_id,
                    "customer_email": customer_email,
                    "metadata": {"order_id": order_id, "order_reference": reference},
                    "payment_intent_data": {
                        "description": f"Commande {reference}",
                        "metadata": {"order_id": order_id, "order_reference": reference},
                    },
                    "success_url": success_url,
                    "cancel_url": cancel_url,
                }
            )
        except stripe.StripeError as exc:
            logger.warning("Stripe checkout creation failed: %s", exc.user_message or exc)
            raise StripeUnavailableError() from exc

        if not session.url:
            raise StripeUnavailableError()
        return StripeCheckout(url=session.url, session_id=session.id)

    def get_session_state(self, session_id: str) -> StripeSessionState:
        try:
            session = self._client.v1.checkout.sessions.retrieve(session_id)
        except stripe.StripeError as exc:
            logger.warning("Stripe session lookup failed: %s", exc.user_message or exc)
            raise StripeUnavailableError() from exc
        return _session_state(session)

    def parse_webhook(
        self, payload: bytes, signature: str | None
    ) -> tuple[str, StripeSessionState] | None:
        """Vérifie la signature ; renvoie (session_id, état) pour un paiement Checkout réussi."""
        if not self._webhook_secret:
            raise StripeUnavailableError()
        try:
            event = self._client.construct_event(payload, signature, self._webhook_secret)
        except (ValueError, stripe.StripeError) as exc:
            logger.warning("Rejected Stripe webhook: %s", type(exc).__name__)
            raise InvalidStripeWebhookError() from exc

        if event.type not in PAID_EVENTS:
            return None
        session = event.data.object
        return session.id, _session_state(session)


def _session_state(session: stripe.checkout.Session) -> StripeSessionState:
    # Les objets Stripe (v16) ne se lisent plus comme des dict : on les convertit d'abord.
    data = session.to_dict()
    metadata = data.get("metadata") or {}
    return StripeSessionState(
        order_id=metadata.get("order_id") or data.get("client_reference_id"),
        paid=data.get("payment_status") == "paid",
        expired=data.get("status") == "expired",
    )


def get_stripe_payments() -> StripePayments:
    return StripePayments(get_settings())
