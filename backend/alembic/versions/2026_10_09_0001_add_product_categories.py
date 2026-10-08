"""Add product categories for the BazarStore catalogue.

Revision ID: 6fc2b5931a40
Revises: 91b6c2e7a4d3
Create Date: 2026-10-09 01:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6fc2b5931a40"
down_revision: str | Sequence[str] | None = "91b6c2e7a4d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_categories",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=140), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_product_categories_slug", "product_categories", ["slug"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_product_categories_slug", table_name="product_categories")
    op.drop_table("product_categories")
