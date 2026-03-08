"""Add billing_parameters table, new line item categories, and vat_summary_json

Revision ID: 004
Revises: 003
Create Date: 2026-03-08

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create billing_parameters table
    op.create_table(
        "billing_parameters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        # Energie
        sa.Column("energy_price_ct_kwh", sa.Float(), server_default="8.96"),
        sa.Column("energy_base_fee_eur_month", sa.Float(), server_default="3.85"),
        sa.Column("pv_price_factor", sa.Float(), server_default="0.80"),
        # Netznutzung
        sa.Column("grid_fee_base_eur_year", sa.Float(), server_default="95.55"),
        sa.Column("grid_fee_ct_kwh", sa.Float(), server_default="7.35"),
        # UAS (Ct/kWh)
        sa.Column("uas_konzessionsabgabe", sa.Float(), server_default="1.32"),
        sa.Column("uas_abschaltbare_lasten", sa.Float(), server_default="0.0"),
        sa.Column("uas_kwk_umlage", sa.Float(), server_default="0.28"),
        sa.Column("uas_offshore", sa.Float(), server_default="0.82"),
        sa.Column("uas_stromsteuer", sa.Float(), server_default="2.05"),
        sa.Column("uas_stromnev", sa.Float(), server_default="1.56"),
        # Sonderpositionen
        sa.Column("invest_levy_base_ct", sa.Float(), server_default="8.0"),
        sa.Column("invest_levy_factor", sa.Float(), server_default="0.75"),
        sa.Column("invest_levy_pv_factor", sa.Float(), server_default="0.015"),
        # Allgemein
        sa.Column("tenant_share", sa.Float(), server_default="0.5"),
        sa.Column("vat_rate_pct", sa.Float(), server_default="19.0"),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 2. Add new enum values to line_item_category_enum (PostgreSQL only)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE line_item_category_enum ADD VALUE IF NOT EXISTS 'energie'")
        op.execute("ALTER TYPE line_item_category_enum ADD VALUE IF NOT EXISTS 'netznutzung'")
        op.execute("ALTER TYPE line_item_category_enum ADD VALUE IF NOT EXISTS 'umlagen'")
        op.execute("ALTER TYPE line_item_category_enum ADD VALUE IF NOT EXISTS 'sonderpositionen'")

    # 3. Add vat_summary_json column to calculation_runs
    op.add_column(
        "calculation_runs",
        sa.Column("vat_summary_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("calculation_runs", "vat_summary_json")
    op.drop_table("billing_parameters")
    # PostgreSQL does not support removing enum values easily; left as no-op.
