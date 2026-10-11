"""Schémas des favoris anonymes et du rapport de popularité produit."""

from pydantic import BaseModel


class PopularProduct(BaseModel):
    product_id: str
    name: str
    category: str
    image_url: str | None
    visitors_total: int
    active_favorites: int
    recent_reactions: int


class PopularProductsOut(BaseModel):
    period_days: int
    products: list[PopularProduct]
