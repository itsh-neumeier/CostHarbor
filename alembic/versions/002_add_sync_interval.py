"""Add sync_interval_minutes to source_connections

Revision ID: 002
Revises: 001
Create Date: 2026-03-08

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "source_connections",
        sa.Column("sync_interval_minutes", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("source_connections", "sync_interval_minutes")
