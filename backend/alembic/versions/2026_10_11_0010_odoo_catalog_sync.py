"""Odoo catalog sync: Odoo ids on products/categories and the integration sync journal.

Additive only: nullable columns and a new table, no existing data is modified.

Revision ID: e3a8c5d71f40
Revises: d7e1a4b9c225
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e3a8c5d71f40"
down_revision: str | Sequence[str] | None = "d7e1a4b9c225"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("product_categories") as batch:
        batch.add_column(sa.Column("odoo_category_id", sa.Integer(), nullable=True))
        batch.create_unique_constraint(
            "uq_product_categories_odoo_category_id", ["odoo_category_id"]
        )

    with op.batch_alter_table("products") as batch:
        batch.add_column(sa.Column("odoo_product_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("odoo_synced_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_unique_constraint("uq_products_odoo_product_id", ["odoo_product_id"])

    op.create_table(
        "integration_sync_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("correlation_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("unchanged_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("deactivated_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rejected_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rejections", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_integration_sync_runs_correlation_id",
        "integration_sync_runs",
        ["correlation_id"],
        unique=True,
    )
    op.create_index("ix_integration_sync_runs_kind", "integration_sync_runs", ["kind"])
    op.create_index("ix_integration_sync_runs_status", "integration_sync_runs", ["status"])
    op.create_index("ix_integration_sync_runs_started_at", "integration_sync_runs", ["started_at"])


def downgrade() -> None:
    op.drop_table("integration_sync_runs")
    with op.batch_alter_table("products") as batch:
        batch.drop_constraint("uq_products_odoo_product_id", type_="unique")
        batch.drop_column("odoo_synced_at")
        batch.drop_column("odoo_product_id")
    with op.batch_alter_table("product_categories") as batch:
        batch.drop_constraint("uq_product_categories_odoo_category_id", type_="unique")
        batch.drop_column("odoo_category_id")
