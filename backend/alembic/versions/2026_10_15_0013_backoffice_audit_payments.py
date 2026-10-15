"""Add back-office audit trail and persistent payment attempts."""

from collections.abc import Sequence
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "c92f14a61d80"
down_revision: str | Sequence[str] | None = "8e2d4b6f1c37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backoffice_audit_logs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=True),
        sa.Column("actor_name", sa.String(255), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=True),
        sa.Column("details", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("actor_id", "action", "entity_type", "entity_id", "created_at"):
        op.create_index(f"ix_backoffice_audit_logs_{column}", "backoffice_audit_logs", [column])

    op.create_table(
        "payment_attempts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("order_id", sa.String(36), nullable=False),
        sa.Column("order_reference", sa.String(24), nullable=False),
        sa.Column("provider", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("provider_reference", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("order_id", "order_reference", "status", "created_at"):
        op.create_index(f"ix_payment_attempts_{column}", "payment_attempts", [column])

    connection = op.get_bind()
    orders = sa.table(
        "orders",
        sa.column("id", sa.String), sa.column("reference", sa.String),
        sa.column("payment_provider", sa.String), sa.column("payment_status", sa.String),
        sa.column("total_amount", sa.Integer), sa.column("payment_correlation_id", sa.String),
        sa.column("payment_requested_at", sa.DateTime(timezone=True)),
        sa.column("paid_at", sa.DateTime(timezone=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    attempts = sa.table(
        "payment_attempts",
        sa.column("id", sa.String), sa.column("order_id", sa.String),
        sa.column("order_reference", sa.String), sa.column("provider", sa.String),
        sa.column("status", sa.String), sa.column("amount", sa.Integer),
        sa.column("provider_reference", sa.String), sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    for order in connection.execute(sa.select(orders).where(orders.c.payment_status.is_not(None))):
        connection.execute(attempts.insert().values(
            id=str(uuid.uuid4()), order_id=order.id, order_reference=order.reference,
            provider=order.payment_provider or "unknown", status=order.payment_status,
            amount=order.total_amount, provider_reference=order.payment_correlation_id,
            created_at=order.payment_requested_at or order.paid_at or order.created_at,
            updated_at=order.paid_at,
        ))


def downgrade() -> None:
    for column in ("order_id", "order_reference", "status", "created_at"):
        op.drop_index(f"ix_payment_attempts_{column}", table_name="payment_attempts")
    op.drop_table("payment_attempts")
    for column in ("actor_id", "action", "entity_type", "entity_id", "created_at"):
        op.drop_index(f"ix_backoffice_audit_logs_{column}", table_name="backoffice_audit_logs")
    op.drop_table("backoffice_audit_logs")
