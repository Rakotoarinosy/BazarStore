"""Add configurable storefront and category images.

Revision ID: d5b7a9c1e204
Revises: b8e61a43d57c
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d5b7a9c1e204"
down_revision: str | Sequence[str] | None = "b8e61a43d57c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("product_categories", sa.Column("image_key", sa.String(length=512), nullable=True))
    op.create_table(
        "storefront_settings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("hero_main_image_key", sa.String(length=512), nullable=True),
        sa.Column("hero_secondary_image_key", sa.String(length=512), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("storefront_settings")
    op.drop_column("product_categories", "image_key")
