"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Users
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(100), unique=True, nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Sites
    op.create_table(
        "sites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("address", sa.String(500), default=""),
        sa.Column("city", sa.String(255), default=""),
        sa.Column("postal_code", sa.String(20), default=""),
        sa.Column("country", sa.String(100), default="DE"),
        sa.Column("total_area_sqm", sa.Numeric(10, 2), default=0),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("config_version", sa.Integer(), default=1),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Units
    op.create_table(
        "units",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("area_sqm", sa.Numeric(10, 2), default=0),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Tenants
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("unit_id", sa.Integer(), sa.ForeignKey("units.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("address_line1", sa.String(500), default=""),
        sa.Column("address_line2", sa.String(500), nullable=True),
        sa.Column("city", sa.String(255), default=""),
        sa.Column("postal_code", sa.String(20), default=""),
        sa.Column("move_in_date", sa.Date(), nullable=True),
        sa.Column("move_out_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Recurring Cost Items
    op.create_table(
        "recurring_cost_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), default="EUR"),
        sa.Column("frequency", sa.String(20), default="monthly"),
        sa.Column(
            "allocation_method", sa.Enum("area", "equal", "fixed", name="allocation_method_enum"), default="area"
        ),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Water Rules
    op.create_table(
        "water_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("split_ratio_json", JSONB, default={}),
        sa.Column("water_price_cents_m3", sa.Integer(), default=0),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Source Connections
    op.create_table(
        "source_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "source_type",
            sa.Enum("homeassistant", "shelly", "vrm_imap", "vrm_upload", "awattar", name="source_type_enum"),
            nullable=False,
        ),
        sa.Column("connection_config_json", JSONB, default={}),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("config_version", sa.Integer(), default=1),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Entity Mappings
    op.create_table(
        "entity_mappings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "source_connection_id",
            sa.Integer(),
            sa.ForeignKey("source_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("unit_id", sa.Integer(), sa.ForeignKey("units.id", ondelete="SET NULL"), nullable=True),
        sa.Column("entity_id", sa.String(500), nullable=False),
        sa.Column(
            "entity_type",
            sa.Enum(
                "grid_consumption",
                "grid_feedin",
                "battery_charge",
                "battery_discharge",
                "pv_production",
                "water",
                name="entity_type_enum",
            ),
            nullable=False,
        ),
        sa.Column("measurement_unit", sa.String(20), default="kWh"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Import Jobs
    op.create_table(
        "import_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "source_connection_id",
            sa.Integer(),
            sa.ForeignKey("source_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("pending", "running", "completed", "failed", "partial", name="import_status_enum"),
            default="pending",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("records_imported", sa.Integer(), default=0),
        sa.Column("records_failed", sa.Integer(), default=0),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("job_metadata_json", JSONB, default={}),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Imported Files
    op.create_table(
        "imported_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("import_job_id", sa.Integer(), sa.ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("stored_path", sa.String(1000), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), default=0),
        sa.Column("file_hash", sa.String(128), nullable=True),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("source_email_subject", sa.String(500), nullable=True),
        sa.Column("source_email_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Raw Measurements
    op.create_table(
        "raw_measurements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("import_job_id", sa.Integer(), sa.ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "source_connection_id",
            sa.Integer(),
            sa.ForeignKey("source_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "entity_mapping_id", sa.Integer(), sa.ForeignKey("entity_mappings.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value_raw", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(20), default="kWh"),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Normalized Measurements
    op.create_table(
        "normalized_measurements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "raw_measurement_id", sa.Integer(), sa.ForeignKey("raw_measurements.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("unit_id", sa.Integer(), sa.ForeignKey("units.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "measurement_type",
            sa.Enum(
                "grid_consumption_kwh",
                "grid_feedin_kwh",
                "battery_charge_kwh",
                "battery_discharge_kwh",
                "pv_production_kwh",
                "water_m3",
                name="measurement_type_enum",
            ),
            nullable=False,
        ),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("measurement_unit", sa.String(20), default="kWh"),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Hourly Prices
    op.create_table(
        "hourly_prices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(50), default="awattar"),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price_eur_mwh", sa.Float(), nullable=False),
        sa.Column("price_eur_kwh", sa.Float(), nullable=False),
        sa.Column("region", sa.String(10), default="DE"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_hourly_prices_timestamp", "hourly_prices", ["timestamp"])

    # Pricing Rules
    op.create_table(
        "pricing_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "rule_type",
            sa.Enum("grid_dynamic", "grid_fixed", "pv_self", "battery", "feedin", name="pricing_rule_type_enum"),
            nullable=False,
        ),
        sa.Column("parameters_json", JSONB, default={}),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("config_version", sa.Integer(), default=1),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Calculation Runs
    op.create_table(
        "calculation_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("unit_id", sa.Integer(), sa.ForeignKey("units.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("billing_month", sa.String(7), nullable=False),
        sa.Column("status", sa.Enum("draft", "final", "archived", name="calc_status_enum"), default="draft"),
        sa.Column("app_version", sa.String(20), nullable=False),
        sa.Column("config_version", sa.String(50), default=""),
        sa.Column("rules_version", sa.String(50), default=""),
        sa.Column("source_snapshot_version", sa.String(200), default=""),
        sa.Column("total_amount_cents", sa.Integer(), default=0),
        sa.Column("currency", sa.String(3), default="EUR"),
        sa.Column("warnings_json", JSONB, nullable=True),
        sa.Column("errors_json", JSONB, nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Calculation Line Items
    op.create_table(
        "calculation_line_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "calculation_run_id", sa.Integer(), sa.ForeignKey("calculation_runs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "category",
            sa.Enum(
                "electricity_grid",
                "electricity_pv",
                "electricity_battery",
                "electricity_feedin",
                "water",
                "fixed_cost",
                name="line_item_category_enum",
            ),
            nullable=False,
        ),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("quantity", sa.Float(), default=0),
        sa.Column("quantity_unit", sa.String(20), default="kWh"),
        sa.Column("unit_price_cents", sa.Float(), default=0),
        sa.Column("total_cents", sa.Integer(), default=0),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.Column("sort_order", sa.Integer(), default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Documents
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "calculation_run_id", sa.Integer(), sa.ForeignKey("calculation_runs.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("document_type", sa.Enum("invoice_pdf", "preview", name="document_type_enum"), default="invoice_pdf"),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("stored_path", sa.String(1000), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), default=0),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Audit Log
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("old_values_json", JSONB, nullable=True),
        sa.Column("new_values_json", JSONB, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("documents")
    op.drop_table("calculation_line_items")
    op.drop_table("calculation_runs")
    op.drop_table("pricing_rules")
    op.drop_index("ix_hourly_prices_timestamp")
    op.drop_table("hourly_prices")
    op.drop_table("normalized_measurements")
    op.drop_table("raw_measurements")
    op.drop_table("imported_files")
    op.drop_table("import_jobs")
    op.drop_table("entity_mappings")
    op.drop_table("source_connections")
    op.drop_table("water_rules")
    op.drop_table("recurring_cost_items")
    op.drop_table("tenants")
    op.drop_table("units")
    op.drop_table("sites")
    op.drop_table("users")

    # Drop enums
    for enum_name in [
        "allocation_method_enum",
        "source_type_enum",
        "entity_type_enum",
        "import_status_enum",
        "measurement_type_enum",
        "pricing_rule_type_enum",
        "calc_status_enum",
        "line_item_category_enum",
        "document_type_enum",
    ]:
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
