"""Schémas HTTP de création et consultation des commandes."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    items: list[OrderItemOut]
