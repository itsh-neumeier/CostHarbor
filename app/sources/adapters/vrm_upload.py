"""VRM CSV upload adapter - parse manually uploaded VRM export CSVs.

Victron VRM exports are CSV files with kWh energy data, typically containing:
- Timestamp columns
- Various energy metrics (grid, PV, battery, etc.)
"""

import logging
from datetime import datetime, timedelta, timezone
from io import StringIO

import pandas as pd
from sqlalchemy.orm import Session

from app.sources.models import (
    EntityMapping, ImportJob, ImportedFile, NormalizedMeasurement,
    RawMeasurement, SourceConnection,
)

logger = logging.getLogger(__name__)


def import_vrm_csv(db: Session, job: ImportJob, source: SourceConnection) -> None:
    """Parse and import a VRM CSV file."""
    imported_file = db.query(ImportedFile).filter(ImportedFile.import_job_id == job.id).first()
    if not imported_file:
        raise ValueError("No file found for this import job")

    with open(imported_file.stored_path, "r", encoding="utf-8-sig") as f:
        content = f.read()

    df = _parse_vrm_csv(content)
    if df.empty:
        job.status = "completed"
        job.records_imported = 0
        return

    mappings = db.query(EntityMapping).filter(
        EntityMapping.source_connection_id == source.id,
    ).all()

    # Build column-to-mapping lookup
    col_map = _build_column_mapping(df.columns.tolist(), mappings)

    for _, row in df.iterrows():
        ts = row.get("timestamp")
        if pd.isna(ts):
            continue

        for col_name, mapping_info in col_map.items():
            value = row.get(col_name, 0)
            if pd.isna(value) or value == 0:
                continue

            mapping, mtype = mapping_info

            raw = RawMeasurement(
                import_job_id=job.id,
                source_connection_id=source.id,
                entity_mapping_id=mapping.id if mapping else None,
                timestamp=ts,
                value_raw=float(value),
                unit="kWh",
            )
            db.add(raw)

            if mapping and mapping.unit_id:
                hour_start = ts.replace(minute=0, second=0, microsecond=0)
                normalized = NormalizedMeasurement(
                    unit_id=mapping.unit_id,
                    measurement_type=mtype,
                    timestamp=ts,
                    value=float(value),
                    measurement_unit="kWh",
                    period_start=hour_start,
                    period_end=hour_start + timedelta(hours=1),
                )
                db.add(normalized)

            job.records_imported += 1

    db.flush()
    logger.info("VRM CSV import: %d records imported", job.records_imported)


def _parse_vrm_csv(content: str) -> pd.DataFrame:
    """Parse VRM export CSV. Handles various VRM export formats."""
    try:
        # VRM CSVs may have different separators
        for sep in [",", ";", "\t"]:
            try:
                df = pd.read_csv(StringIO(content), sep=sep)
                if len(df.columns) > 1:
                    break
            except Exception:
                continue
        else:
            return pd.DataFrame()
    except Exception as e:
        logger.error("Failed to parse VRM CSV: %s", e)
        return pd.DataFrame()

    if df.empty:
        return df

    df.columns = [c.strip() for c in df.columns]

    # Find timestamp column
    ts_col = None
    for candidate in df.columns:
        lower = candidate.lower()
        if lower in ("timestamp", "time", "date", "datetime", "date_time"):
            ts_col = candidate
            break

    if ts_col is None:
        ts_col = df.columns[0]

    # Parse timestamps
    try:
        sample = df[ts_col].iloc[0]
        if isinstance(sample, (int, float)) and sample > 1e9:
            df["timestamp"] = pd.to_datetime(df[ts_col], unit="s", utc=True)
        else:
            df["timestamp"] = pd.to_datetime(df[ts_col], utc=True)
    except Exception:
        df["timestamp"] = pd.to_datetime(df[ts_col], format="mixed", utc=True)

    return df


def _build_column_mapping(
    columns: list[str], mappings: list[EntityMapping],
) -> dict:
    """Map CSV columns to entity mappings by matching entity_id to column names."""
    col_map = {}
    type_map = {
        "grid_consumption": "grid_consumption_kwh",
        "grid_feedin": "grid_feedin_kwh",
        "pv_production": "pv_production_kwh",
        "battery_charge": "battery_charge_kwh",
        "battery_discharge": "battery_discharge_kwh",
        "water": "water_m3",
    }

    for mapping in mappings:
        entity_id = mapping.entity_id.lower()
        for col in columns:
            if col.lower() == entity_id or entity_id in col.lower():
                mtype = type_map.get(mapping.entity_type, "grid_consumption_kwh")
                col_map[col] = (mapping, mtype)
                break

    return col_map
