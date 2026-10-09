"""Number order invoices sequentially.

Revision ID: c4d9e2f7a113
Revises: b8c3d1e5f902
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4d9e2f7a113"
down_revision: str | Sequence[str] | None = "b8c3d1e5f902"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("orders") as batch:
        batch.add_column(sa.Column("invoice_number", sa.String(length=24), nullable=True))
        batch.add_column(sa.Column("invoice_issued_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_orders_invoice_number", "orders", ["invoice_number"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_orders_invoice_number", table_name="orders")
    with op.batch_alter_table("orders") as batch:
        batch.drop_column("invoice_issued_at")
        batch.drop_column("invoice_number")
