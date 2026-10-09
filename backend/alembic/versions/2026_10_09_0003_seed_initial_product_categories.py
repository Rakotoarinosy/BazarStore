"""Seed six initial product categories.

Revision ID: e71c45a9d302
Revises: c4d8f7a912be
Create Date: 2026-10-09 01:45:00
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "e71c45a9d302"
down_revision: str | Sequence[str] | None = "c4d8f7a912be"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    categories = sa.table(
        "product_categories",
        sa.column("id", sa.String(length=36)),
        sa.column("name", sa.String(length=120)),
        sa.column("slug", sa.String(length=140)),
        sa.column("description", sa.Text()),
        sa.column("is_active", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    created_at = datetime(2026, 10, 9, tzinfo=UTC)
    op.bulk_insert(
        categories,
        [
            {
                "id": "7a1c82e4-9413-4d8c-9217-2f89a1f3c101",
                "name": "Mode & vêtements",
                "slug": "mode-vetements",
                "description": "Vêtements et articles de mode pour tous les jours.",
                "is_active": True,
                "created_at": created_at,
                "updated_at": created_at,
            },
            {
                "id": "7a1c82e4-9413-4d8c-9217-2f89a1f3c102",
                "name": "High-tech & électronique",
                "slug": "high-tech-electronique",
                "description": "Appareils électroniques, accessoires connectés et informatique.",
                "is_active": True,
                "created_at": created_at,
                "updated_at": created_at,
            },
            {
                "id": "7a1c82e4-9413-4d8c-9217-2f89a1f3c103",
                "name": "Accessoires",
                "slug": "accessoires",
                "description": "Accessoires de mode et objets utiles au quotidien.",
                "is_active": True,
                "created_at": created_at,
                "updated_at": created_at,
            },
            {
                "id": "7a1c82e4-9413-4d8c-9217-2f89a1f3c104",
                "name": "Sport & bien-être",
                "slug": "sport-bien-etre",
                "description": "Équipements et accessoires pour le sport et le bien-être.",
                "is_active": True,
                "created_at": created_at,
                "updated_at": created_at,
            },
            {
                "id": "7a1c82e4-9413-4d8c-9217-2f89a1f3c105",
                "name": "Maison & décoration",
                "slug": "maison-decoration",
                "description": "Objets pratiques et décoration pour la maison.",
                "is_active": True,
                "created_at": created_at,
                "updated_at": created_at,
            },
            {
                "id": "7a1c82e4-9413-4d8c-9217-2f89a1f3c106",
                "name": "Beauté & soins",
                "slug": "beaute-soins",
                "description": "Produits et accessoires de beauté et de soin personnel.",
                "is_active": True,
                "created_at": created_at,
                "updated_at": created_at,
            },
        ],
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM product_categories WHERE id IN "
        "('7a1c82e4-9413-4d8c-9217-2f89a1f3c101', "
        "'7a1c82e4-9413-4d8c-9217-2f89a1f3c102', "
        "'7a1c82e4-9413-4d8c-9217-2f89a1f3c103', "
        "'7a1c82e4-9413-4d8c-9217-2f89a1f3c104', "
        "'7a1c82e4-9413-4d8c-9217-2f89a1f3c105', "
        "'7a1c82e4-9413-4d8c-9217-2f89a1f3c106')"
    )
