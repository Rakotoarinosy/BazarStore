"""Persist anonymous storefront favorites for product popularity reporting."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f15a08c4d261"
down_revision: str | Sequence[str] | None = "d7e1a4b9c225"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_reactions",
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("visitor_hash", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("first_reacted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_reacted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("product_id", "visitor_hash"),
    )
    op.create_index(
        "ix_product_reactions_last_reacted_at",
        "product_reactions",
        ["last_reacted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_product_reactions_last_reacted_at", table_name="product_reactions")
    op.drop_table("product_reactions")
