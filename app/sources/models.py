"""Data source models: connections, entity mappings, imports, measurements."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

# Use JSON for cross-DB compatibility; JSONB on PostgreSQL via with_variant
JsonType = JSON().with_variant(JSONB, "postgresql")
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SourceConnection(Base):
    __tablename__ = "source_connections"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(
        Enum("homeassistant", "shelly", "vrm_imap", "vrm_upload", "awattar", name="source_type_enum"),
        nullable=False,
    )
    connection_config_json: Mapped[dict] = mapped_column(JsonType, default=dict)
    is_active: Mapped[bool] = mapped_column(default=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_interval_minutes: Mapped[int] = mapped_column(Integer, default=0)
    config_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    entity_mappings: Mapped[list["EntityMapping"]] = relationship(
        back_populates="source_connection", cascade="all, delete-orphan"
    )
    import_jobs: Mapped[list["ImportJob"]] = relationship(
        back_populates="source_connection", cascade="all, delete-orphan"
    )


class EntityMapping(Base):
    __tablename__ = "entity_mappings"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_connection_id: Mapped[int] = mapped_column(
        ForeignKey("source_connections.id", ondelete="CASCADE"), nullable=False
    )
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id", ondelete="SET NULL"), nullable=True)
    entity_id: Mapped[str] = mapped_column(String(500), nullable=False)
    entity_type: Mapped[str] = mapped_column(
        Enum(
            "grid_consumption",
            "grid_feedin",
            "battery_charge",
            "battery_discharge",
            "pv_production",
            "water",
            name="entity_type_enum",
        ),
        nullable=False,
    )
    measurement_unit: Mapped[str] = mapped_column(String(20), default="kWh")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    source_connection: Mapped["SourceConnection"] = relationship(back_populates="entity_mappings")


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_connection_id: Mapped[int] = mapped_column(
        ForeignKey("source_connections.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        Enum("pending", "running", "completed", "failed", "partial", name="import_status_enum"),
        default="pending",
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    records_imported: Mapped[int] = mapped_column(Integer, default=0)
    records_failed: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_metadata_json: Mapped[dict] = mapped_column(JsonType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source_connection: Mapped["SourceConnection"] = relationship(back_populates="import_jobs")
    imported_files: Mapped[list["ImportedFile"]] = relationship(
        back_populates="import_job", cascade="all, delete-orphan"
    )


class ImportedFile(Base):
    __tablename__ = "imported_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    import_job_id: Mapped[int] = mapped_column(ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    file_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_email_subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_email_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    import_job: Mapped["ImportJob"] = relationship(back_populates="imported_files")


class RawMeasurement(Base):
    __tablename__ = "raw_measurements"

    id: Mapped[int] = mapped_column(primary_key=True)
    import_job_id: Mapped[int] = mapped_column(ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=False)
    source_connection_id: Mapped[int] = mapped_column(
        ForeignKey("source_connections.id", ondelete="CASCADE"), nullable=False
    )
    entity_mapping_id: Mapped[int | None] = mapped_column(
        ForeignKey("entity_mappings.id", ondelete="SET NULL"), nullable=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value_raw: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), default="kWh")
    metadata_json: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NormalizedMeasurement(Base):
    __tablename__ = "normalized_measurements"

    id: Mapped[int] = mapped_column(primary_key=True)
    raw_measurement_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_measurements.id", ondelete="SET NULL"), nullable=True
    )
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"), nullable=False)
    measurement_type: Mapped[str] = mapped_column(
        Enum(
            "grid_consumption_kwh",
            "grid_feedin_kwh",
            "battery_charge_kwh",
            "battery_discharge_kwh",
            "pv_production_kwh",
            "water_m3",
            name="measurement_type_enum",
        ),
        nullable=False,
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    measurement_unit: Mapped[str] = mapped_column(String(20), default="kWh")
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
