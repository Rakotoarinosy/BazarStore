"""Track stock deduction and last update on orders (backoffice order management).

Revision ID: d7e1a4b9c225
Revises: c4d9e2f7a113
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7e1a4b9c225"
down_revision: str | Sequence[str] | None = "c4d9e2f7a113"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("orders") as batch:
        batch.add_column(
            sa.Column("stock_deducted", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch:
        batch.drop_column("updated_at")
        batch.drop_column("stock_deducted")
