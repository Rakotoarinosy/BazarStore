"""Schémas HTTP des catégories du catalogue."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CategoryCreateIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=120)
    slug: str | None = Field(default=None, max_length=140)
    description: str = Field(default="", max_length=2000)
    image_key: str | None = Field(default=None, max_length=512)
    is_active: bool = True


class CategoryUpdateIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=2, max_length=120)
    slug: str | None = Field(default=None, max_length=140)
    description: str | None = Field(default=None, max_length=2000)
    image_key: str | None = Field(default=None, max_length=512)
    is_active: bool | None = None


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    description: str
    image_key: str | None
    image_url: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
