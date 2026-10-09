"""Schémas HTTP de création et consultation des commandes."""

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Numéros MVola (Telma) : 034 / 038 suivis de 7 chiffres.
_MVOLA_MSISDN = re.compile(r"^03[48]\d{7}$")


class OrderItemCreateIn(BaseModel):
    product_id: str = Field(min_length=1, max_length=36)
    quantity: int = Field(ge=1, le=99)


class OrderCreateIn(BaseModel):
    items: list[OrderItemCreateIn] = Field(min_length=1, max_length=100)

    @field_validator("items")
    @classmethod
    def product_ids_must_be_unique(cls, items: list[OrderItemCreateIn]) -> list[OrderItemCreateIn]:
        product_ids = [item.product_id for item in items]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("Each product can only appear once in an order")
        return items


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    product_id: str | None
    product_name: str
    product_image_url: str | None
    unit_price: int
    quantity: int
    line_total: int


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    reference: str
    user_id: str | None
    customer_name: str
    customer_email: str
    status: str
    total_amount: int
    created_at: datetime
    payment_provider: str | None = None
    payment_status: str | None = None
    payment_phone: str | None = None
    payment_reference: str | None = None
    paid_at: datetime | None = None
    invoice_number: str | None = None
    items: list[OrderItemOut]


class MvolaPaymentIn(BaseModel):
    phone: str = Field(min_length=9, max_length=20, description="Numéro MVola, ex. 0343500003")

    @field_validator("phone")
    @classmethod
    def normalize_mvola_phone(cls, value: str) -> str:
        digits = re.sub(r"[\s.\-]", "", value)
        if digits.startswith("+261"):
            digits = "0" + digits[4:]
        elif digits.startswith("261"):
            digits = "0" + digits[3:]
        if not _MVOLA_MSISDN.match(digits):
            raise ValueError(
                "Numéro MVola invalide (format attendu : 034 ou 038 suivi de 7 chiffres)"
            )
        return digits


class MvolaCallbackIn(BaseModel):
    model_config = ConfigDict(extra="allow")

    serverCorrelationId: str = Field(min_length=1, max_length=100)  # noqa: N815 (nom imposé par MVola)


class StripeCheckoutOut(BaseModel):
    checkout_url: str
    order: OrderOut


class PaymentConfigOut(BaseModel):
    card_enabled: bool
