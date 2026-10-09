"""Track Mobile Money (MVola) payments on orders.

Revision ID: b8c3d1e5f902
Revises: a6e2f9c1d804
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8c3d1e5f902"
down_revision: str | Sequence[str] | None = "a6e2f9c1d804"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("orders") as batch:
        batch.add_column(sa.Column("payment_provider", sa.String(length=24), nullable=True))
        batch.add_column(sa.Column("payment_status", sa.String(length=24), nullable=True))
        batch.add_column(sa.Column("payment_phone", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("payment_correlation_id", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("payment_reference", sa.String(length=100), nullable=True))
        batch.add_column(
            sa.Column("payment_requested_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_orders_payment_correlation_id", "orders", ["payment_correlation_id"])


def downgrade() -> None:
    op.drop_index("ix_orders_payment_correlation_id", table_name="orders")
    with op.batch_alter_table("orders") as batch:
        batch.drop_column("paid_at")
        batch.drop_column("payment_requested_at")
        batch.drop_column("payment_reference")
        batch.drop_column("payment_correlation_id")
        batch.drop_column("payment_phone")
        batch.drop_column("payment_status")
        batch.drop_column("payment_provider")
