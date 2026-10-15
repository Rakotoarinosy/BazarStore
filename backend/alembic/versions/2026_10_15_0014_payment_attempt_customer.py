"""Keep the customer identity on each payment attempt."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d31a2b908e74"
down_revision: str | Sequence[str] | None = "c92f14a61d80"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("payment_attempts", sa.Column("customer_name", sa.String(length=255), nullable=True))
    op.add_column("payment_attempts", sa.Column("customer_email", sa.String(length=320), nullable=True))

    connection = op.get_bind()
    attempts = sa.table(
        "payment_attempts",
        sa.column("order_id", sa.String),
        sa.column("customer_name", sa.String),
        sa.column("customer_email", sa.String),
    )
    orders = sa.table(
        "orders",
        sa.column("id", sa.String),
        sa.column("customer_name", sa.String),
        sa.column("customer_email", sa.String),
    )
    connection.execute(
        attempts.update().values(
            customer_name=sa.select(orders.c.customer_name).where(orders.c.id == attempts.c.order_id).scalar_subquery(),
            customer_email=sa.select(orders.c.customer_email).where(orders.c.id == attempts.c.order_id).scalar_subquery(),
        )
    )
    connection.execute(
        attempts.update()
        .where(attempts.c.customer_name.is_(None))
        .values(customer_name="Client inconnu", customer_email="")
    )
    with op.batch_alter_table("payment_attempts") as batch:
        batch.alter_column("customer_name", existing_type=sa.String(length=255), nullable=False)
        batch.alter_column("customer_email", existing_type=sa.String(length=320), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("payment_attempts") as batch:
        batch.drop_column("customer_email")
        batch.drop_column("customer_name")
