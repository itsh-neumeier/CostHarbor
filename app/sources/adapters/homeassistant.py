"""Home Assistant REST API adapter.

Fetches historical energy data via the HA REST API using Long-Lived Access Tokens.
Supports: grid consumption/feedin, PV production, battery charge/discharge, water.
"""

import logging
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from app.sources.models import (
    EntityMapping,
    ImportJob,
    NormalizedMeasurement,
    RawMeasurement,
    SourceConnection,
)

logger = logging.getLogger(__name__)

ENTITY_TYPE_TO_MEASUREMENT = {
    "grid_consumption": "grid_consumption_kwh",
    "grid_feedin": "grid_feedin_kwh",
    "pv_production": "pv_production_kwh",
    "battery_charge": "battery_charge_kwh",
    "battery_discharge": "battery_discharge_kwh",
    "water": "water_m3",
}


def import_homeassistant(db: Session, job: ImportJob, source: SourceConnection) -> None:
    """Fetch history data from Home Assistant and import measurements."""
    config = source.connection_config_json or {}
    base_url = config.get("base_url", "").rstrip("/")
    token = config.get("token", "")

    if not base_url or not token:
        raise ValueError("Home Assistant base_url and token are required")

    # Get entity mappings
    mappings = (
        db.query(EntityMapping)
        .filter(
            EntityMapping.source_connection_id == source.id,
        )
        .all()
    )

    if not mappings:
        raise ValueError("No entity mappings configured for this source")

    # Determine time range from job metadata or default to last 31 days
    meta = job.job_metadata_json or {}
    if "start_date" in meta:
        start_dt = datetime.fromisoformat(meta["start_date"]).replace(tzinfo=UTC)
    else:
        start_dt = (datetime.now(UTC) - timedelta(days=31)).replace(hour=0, minute=0, second=0, microsecond=0)

    if "end_date" in meta:
        end_dt = datetime.fromisoformat(meta["end_date"]).replace(tzinfo=UTC)
    else:
        end_dt = datetime.now(UTC)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    for mapping in mappings:
        try:
            _fetch_entity_history(db, job, source, mapping, base_url, headers, start_dt, end_dt)
        except Exception as e:
            logger.error("Failed to fetch entity %s: %s", mapping.entity_id, e)
            job.records_failed += 1

    logger.info("HA import completed: %d imported, %d failed", job.records_imported, job.records_failed)


def _fetch_entity_history(
    db: Session,
    job: ImportJob,
    source: SourceConnection,
    mapping: EntityMapping,
    base_url: str,
    headers: dict,
    start_dt: datetime,
    end_dt: datetime,
) -> None:
    """Fetch history for a single entity and store normalized measurements."""
    url = (
        f"{base_url}/api/history/period/{start_dt.isoformat()}"
        f"?end_time={end_dt.isoformat()}"
        f"&filter_entity_id={mapping.entity_id}"
        f"&minimal_response&no_attributes"
    )

    with httpx.Client(timeout=60) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()

    data = resp.json()
    if not data or not data[0]:
        logger.info("No history data for %s", mapping.entity_id)
        return

    states = data[0]
    measurement_type = ENTITY_TYPE_TO_MEASUREMENT.get(mapping.entity_type)
    if not measurement_type:
        return

    unit = "kWh" if "kwh" in measurement_type else "m3"

    # Process states - compute deltas for cumulative sensors
    prev_value = None
    for state in states:
        try:
            value = float(state["state"])
        except (ValueError, TypeError):
            continue

        ts = datetime.fromisoformat(state["last_changed"].replace("Z", "+00:00"))

        # Store raw
        raw = RawMeasurement(
            import_job_id=job.id,
            source_connection_id=source.id,
            entity_mapping_id=mapping.id,
            timestamp=ts,
            value_raw=value,
            unit=mapping.measurement_unit or unit,
        )
        db.add(raw)
        job.records_imported += 1

        if prev_value is not None:
            delta = value - prev_value
            if delta > 0:
                hour_start = ts.replace(minute=0, second=0, microsecond=0)
                normalized = NormalizedMeasurement(
                    unit_id=mapping.unit_id or 0,
                    measurement_type=measurement_type,
                    timestamp=ts,
                    value=delta,
                    measurement_unit=unit,
                    period_start=hour_start,
                    period_end=hour_start + timedelta(hours=1),
                )
                db.add(normalized)

        prev_value = value

    db.flush()
