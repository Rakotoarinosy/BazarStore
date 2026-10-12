"""Give each newsletter subscription an unguessable unsubscribe token."""

import secrets
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8e2d4b6f1c37"
down_revision: str | Sequence[str] | None = "3a9c5e71b0d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "newsletter_subscriptions",
        sa.Column("unsubscribe_token", sa.String(length=64), nullable=True),
    )
    connection = op.get_bind()
    subscriptions = sa.table(
        "newsletter_subscriptions",
        sa.column("id", sa.String),
        sa.column("unsubscribe_token", sa.String),
    )
    for (subscription_id,) in connection.execute(sa.select(subscriptions.c.id)):
        connection.execute(
            subscriptions.update()
            .where(subscriptions.c.id == subscription_id)
            .values(unsubscribe_token=secrets.token_urlsafe(32))
        )
    with op.batch_alter_table("newsletter_subscriptions") as batch:
        batch.alter_column("unsubscribe_token", existing_type=sa.String(length=64), nullable=False)
    op.create_index(
        "ix_newsletter_subscriptions_unsubscribe_token",
        "newsletter_subscriptions",
        ["unsubscribe_token"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_newsletter_subscriptions_unsubscribe_token", table_name="newsletter_subscriptions"
    )
    with op.batch_alter_table("newsletter_subscriptions") as batch:
        batch.drop_column("unsubscribe_token")
