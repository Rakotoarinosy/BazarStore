"""Schémas HTTP du catalogue produits."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProductCreateIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=2, max_length=180)
    description: str = Field(default="", max_length=5000)
    price: int = Field(ge=0)
    quantity: int = Field(default=0, ge=0)
    image_url: str | None = Field(default=None, max_length=1000)
    image_key: str | None = Field(default=None, max_length=512)
    category_id: str = Field(min_length=1, max_length=36)
    is_active: bool = True


class ProductUpdateIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    code: str | None = Field(default=None, min_length=2, max_length=64)
    name: str | None = Field(default=None, min_length=2, max_length=180)
    description: str | None = Field(default=None, max_length=5000)
    price: int | None = Field(default=None, ge=0)
    quantity: int | None = Field(default=None, ge=0)
    image_url: str | None = Field(default=None, max_length=1000)
    image_key: str | None = Field(default=None, max_length=512)
    category_id: str | None = Field(default=None, min_length=1, max_length=36)
    is_active: bool | None = None


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    name: str
    description: str
    price: int
    quantity: int
    inventory_status: str
    image_url: str | None
    image_key: str | None
    category_id: str
    category_name: str
    is_active: bool
    # Renseigné si le produit est géré dans Odoo (champs maîtres non modifiables ici).
    odoo_product_id: int | None = None
    odoo_synced_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ProductImageUploadOut(BaseModel):
    image_key: str
    image_url: str
