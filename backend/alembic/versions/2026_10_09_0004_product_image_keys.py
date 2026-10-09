"""Store MinIO object keys on products.

Revision ID: b8e61a43d57c
Revises: e71c45a9d302
Create Date: 2026-10-09 02:05:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8e61a43d57c"
down_revision: str | Sequence[str] | None = "e71c45a9d302"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("image_key", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "image_key")
