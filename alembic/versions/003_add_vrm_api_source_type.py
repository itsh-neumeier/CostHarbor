"""Add vrm_api to source_type_enum

Revision ID: 003
Revises: 002
Create Date: 2026-03-08

"""

from collections.abc import Sequence

from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # For PostgreSQL: alter the enum type to add the new value
    # For SQLite: enum types are stored as VARCHAR, so no DDL change needed.
    # We use execute() with a check to handle both cases.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE source_type_enum ADD VALUE IF NOT EXISTS 'vrm_api'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values easily.
    # This is intentionally a no-op; the unused value causes no harm.
    pass
