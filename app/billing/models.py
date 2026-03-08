"""Billing models: pricing rules, hourly prices, calculation runs, line items."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

# Use JSON for cross-DB compatibility; JSONB on PostgreSQL via with_variant
JsonType = JSON().with_variant(JSONB, "postgresql")
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class HourlyPrice(Base):
    __tablename__ = "hourly_prices"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(50), default="awattar")
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, unique=True)
    price_eur_mwh: Mapped[float] = mapped_column(Float, nullable=False)
    price_eur_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    region: Mapped[str] = mapped_column(String(10), default="DE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PricingRule(Base):
    __tablename__ = "pricing_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    rule_type: Mapped[str] = mapped_column(
        Enum("grid_dynamic", "grid_fixed", "pv_self", "battery", "feedin", name="pricing_rule_type_enum"),
        nullable=False,
    )
    parameters_json: Mapped[dict] = mapped_column(JsonType, default=dict)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    config_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CalculationRun(Base):
    __tablename__ = "calculation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    billing_month: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    status: Mapped[str] = mapped_column(
        Enum("draft", "final", "archived", name="calc_status_enum"),
        default="draft",
    )
    app_version: Mapped[str] = mapped_column(String(20), nullable=False)
    config_version: Mapped[str] = mapped_column(String(50), default="")
    rules_version: Mapped[str] = mapped_column(String(50), default="")
    source_snapshot_version: Mapped[str] = mapped_column(String(200), default="")
    total_amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    warnings_json: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    errors_json: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    vat_summary_json: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    line_items: Mapped[list["CalculationLineItem"]] = relationship(
        back_populates="calculation_run", cascade="all, delete-orphan"
    )


class CalculationLineItem(Base):
    __tablename__ = "calculation_line_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    calculation_run_id: Mapped[int] = mapped_column(
        ForeignKey("calculation_runs.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(
        Enum(
            "electricity_grid",
            "electricity_pv",
            "electricity_battery",
            "electricity_feedin",
            "water",
            "fixed_cost",
            "energie",
            "netznutzung",
            "umlagen",
            "sonderpositionen",
            name="line_item_category_enum",
        ),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, default=0)
    quantity_unit: Mapped[str] = mapped_column(String(20), default="kWh")
    unit_price_cents: Mapped[float] = mapped_column(Float, default=0)
    total_cents: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    calculation_run: Mapped["CalculationRun"] = relationship(back_populates="line_items")
