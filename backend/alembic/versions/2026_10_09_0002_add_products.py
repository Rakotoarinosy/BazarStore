"""Add products linked to one product category.

Revision ID: c4d8f7a912be
Revises: 6fc2b5931a40
Create Date: 2026-10-09 01:35:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4d8f7a912be"
down_revision: str | Sequence[str] | None = "6fc2b5931a40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column("image_url", sa.String(length=1000), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("category_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["category_id"], ["product_categories.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_products_code", "products", ["code"], unique=True)
    op.create_index("ix_products_name", "products", ["name"])
    op.create_index("ix_products_category_id", "products", ["category_id"])


def downgrade() -> None:
    op.drop_index("ix_products_category_id", table_name="products")
    op.drop_index("ix_products_name", table_name="products")
    op.drop_index("ix_products_code", table_name="products")
    op.drop_table("products")
