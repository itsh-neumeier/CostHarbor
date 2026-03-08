"""Shelly Pro 3EM CSV import adapter.

Supports two modes:
1. CSV upload: Parse exported CSV from the device's /emdata/0/data.csv endpoint
2. HTTP polling: Fetch CSV directly from the Shelly device via network (auto-sync)

Aggregates minute-level phase data into hourly normalized measurements.
"""

import logging
from datetime import UTC, datetime, timedelta
from io import StringIO

import httpx
import pandas as pd
from sqlalchemy.orm import Session

from app.sources.models import (
    EntityMapping,
    ImportedFile,
    ImportJob,
    NormalizedMeasurement,
    RawMeasurement,
    SourceConnection,
)

logger = logging.getLogger(__name__)


def import_shelly_csv(db: Session, job: ImportJob, source: SourceConnection) -> None:
    """Parse and import Shelly Pro 3EM data (from file upload or HTTP poll)."""
    meta = job.job_metadata_json or {}

    # Check if this is an auto-sync (HTTP poll) or file upload
    if meta.get("auto_sync") or meta.get("triggered_by") == "scheduler":
        content = _fetch_shelly_http(source)
    else:
        # Get the uploaded file
        imported_file = db.query(ImportedFile).filter(ImportedFile.import_job_id == job.id).first()
        if not imported_file:
            raise ValueError("Keine Datei fuer diesen Import-Job gefunden")
        with open(imported_file.stored_path, encoding="utf-8-sig") as f:
            content = f.read()

    if not content or not content.strip():
        job.status = "completed"
        job.records_imported = 0
        return

    df = _parse_shelly_csv(content)
    if df.empty:
        job.status = "completed"
        job.records_imported = 0
        return

    # Get entity mappings for this source
    mappings = (
        db.query(EntityMapping)
        .filter(
            EntityMapping.source_connection_id == source.id,
        )
        .all()
    )

    # Store raw data
    for _, row in df.iterrows():
        raw = RawMeasurement(
            import_job_id=job.id,
            source_connection_id=source.id,
            timestamp=row["timestamp"],
            value_raw=row["total_active_energy"],
            unit="Wh",
            metadata_json={
                "phase_a": row.get("a_act_energy", 0),
                "phase_b": row.get("b_act_energy", 0),
                "phase_c": row.get("c_act_energy", 0),
            },
        )
        db.add(raw)
        job.records_imported += 1

    # Aggregate to hourly and create normalized measurements
    hourly = _aggregate_hourly(df)
    for mapping in mappings:
        for _, row in hourly.iterrows():
            if mapping.entity_type == "grid_consumption":
                value = row.get("total_active_kwh", 0)
                mtype = "grid_consumption_kwh"
            elif mapping.entity_type == "grid_feedin":
                value = row.get("total_return_kwh", 0)
                mtype = "grid_feedin_kwh"
            else:
                continue

            if value <= 0:
                continue

            normalized = NormalizedMeasurement(
                unit_id=mapping.unit_id or 0,
                measurement_type=mtype,
                timestamp=row["hour_start"],
                value=value,
                measurement_unit="kWh",
                period_start=row["hour_start"],
                period_end=row["hour_start"] + timedelta(hours=1),
            )
            db.add(normalized)

    db.flush()
    logger.info("Shelly CSV import: %d raw records, hourly aggregated", job.records_imported)


def _parse_shelly_csv(content: str) -> pd.DataFrame:
    """Parse Shelly Pro 3EM CSV format.

    Expected columns vary, but typically include timestamp and per-phase energy values.
    Common patterns:
    - Timestamp (Unix epoch), a_act_energy, b_act_energy, c_act_energy, ...
    """
    try:
        df = pd.read_csv(StringIO(content))
    except Exception as e:
        logger.error("Failed to parse CSV: %s", e)
        return pd.DataFrame()

    if df.empty:
        return df

    # Normalize column names
    df.columns = [c.strip().lower() for c in df.columns]

    # Detect timestamp column
    ts_col = None
    for candidate in ["timestamp", "ts", "date_time", "time"]:
        if candidate in df.columns:
            ts_col = candidate
            break

    if ts_col is None and df.columns[0]:
        ts_col = df.columns[0]

    # Convert timestamps
    if ts_col:
        sample = df[ts_col].iloc[0]
        if isinstance(sample, (int, float)) and sample > 1e9:
            df["timestamp"] = pd.to_datetime(df[ts_col], unit="s", utc=True)
        else:
            df["timestamp"] = pd.to_datetime(df[ts_col], utc=True)

    # Compute total active energy from phases if available
    phase_cols = [c for c in df.columns if "act_energy" in c and "ret" not in c]
    if phase_cols:
        df["total_active_energy"] = df[phase_cols].sum(axis=1)
    elif "total_act" in df.columns:
        df["total_active_energy"] = df["total_act"]
    else:
        df["total_active_energy"] = 0

    # Return energy (exported)
    ret_cols = [c for c in df.columns if "ret" in c and "energy" in c]
    if ret_cols:
        df["total_return_energy"] = df[ret_cols].sum(axis=1)
    elif "total_act_ret" in df.columns:
        df["total_return_energy"] = df["total_act_ret"]
    else:
        df["total_return_energy"] = 0

    return df


def _aggregate_hourly(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate minute-level data to hourly deltas."""
    if "timestamp" not in df.columns or df.empty:
        return pd.DataFrame()

    df = df.sort_values("timestamp").copy()
    df["hour"] = df["timestamp"].dt.floor("h")

    # Calculate deltas (difference between max and min per hour for cumulative counters)
    grouped = (
        df.groupby("hour")
        .agg(
            total_active_start=("total_active_energy", "first"),
            total_active_end=("total_active_energy", "last"),
            total_return_start=("total_return_energy", "first"),
            total_return_end=("total_return_energy", "last"),
        )
        .reset_index()
    )

    grouped["total_active_kwh"] = (grouped["total_active_end"] - grouped["total_active_start"]) / 1000
    grouped["total_return_kwh"] = (grouped["total_return_end"] - grouped["total_return_start"]) / 1000
    grouped["hour_start"] = grouped["hour"]

    # Filter out negative deltas (counter resets)
    grouped.loc[grouped["total_active_kwh"] < 0, "total_active_kwh"] = 0
    grouped.loc[grouped["total_return_kwh"] < 0, "total_return_kwh"] = 0

    return grouped


def _fetch_shelly_http(source: SourceConnection) -> str:
    """Fetch CSV data directly from a Shelly Pro 3EM device via HTTP."""
    config = source.connection_config_json or {}
    device_ip = config.get("device_ip", "")

    if not device_ip:
        raise ValueError("device_ip fehlt in der Konfiguration")

    # Fetch last 24 hours of data
    now = datetime.now(UTC)
    start_ts = int((now - timedelta(hours=24)).timestamp())
    end_ts = int(now.timestamp())

    url = f"http://{device_ip}/emdata/0/data.csv?ts={start_ts}&end_ts={end_ts}"

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(url)
            resp.raise_for_status()
        return resp.text
    except httpx.ConnectError as exc:
        raise ValueError(f"Shelly-Geraet unter {device_ip} nicht erreichbar") from exc
    except httpx.TimeoutException as exc:
        raise ValueError(f"Timeout bei Verbindung zu Shelly unter {device_ip}") from exc
    except httpx.HTTPStatusError as exc:
        raise ValueError(f"Shelly HTTP-Fehler: {exc.response.status_code}") from exc
