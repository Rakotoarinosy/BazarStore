"""HTTP schemas for shopping mission recommendations."""

from pydantic import BaseModel, ConfigDict, Field


class ShoppingMissionIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    mission: str = Field(min_length=5, max_length=500)
    budget: int = Field(ge=1, le=100_000_000)


class ShoppingMissionProductOut(BaseModel):
    id: str
    code: str
    name: str
    description: str
    price: int
    quantity: int
    inventory_status: str
    image_url: str | None
    category_id: str
    category_name: str
    is_active: bool


class ShoppingMissionRecommendationOut(BaseModel):
    product: ShoppingMissionProductOut
    reason: str


class ShoppingMissionOut(BaseModel):
    mission: str
    budget: int
    total_price: int
    summary: str
    recommendations: list[ShoppingMissionRecommendationOut] = Field(max_length=3)
