"""Persist storefront newsletter subscriptions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3a9c5e71b0d4"
down_revision: str | Sequence[str] | None = "f15a08c4d261"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "newsletter_subscriptions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("subscribed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("unsubscribed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_newsletter_subscriptions_email",
        "newsletter_subscriptions",
        ["email"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_newsletter_subscriptions_email", table_name="newsletter_subscriptions")
    op.drop_table("newsletter_subscriptions")
