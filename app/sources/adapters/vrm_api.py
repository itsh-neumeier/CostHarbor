"""Victron VRM API adapter - direct data import via REST API.

Fetches energy statistics from the VRM Portal API v2 using access tokens.
No email/IMAP needed - data is pulled directly.

Required config:
    {"access_token": "...", "installation_id": 12345}

API docs: https://vrm-api-docs.victronenergy.com/
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

VRM_API_BASE = "https://vrmapi.victronenergy.com/v2"

# VRM attribute codes mapped to our measurement types
VRM_ATTRIBUTE_MAP = {
    "Gc": "grid_consumption_kwh",  # Grid to consumers (kWh)
    "Pg": "grid_feedin_kwh",  # PV to grid / grid feed-in (kWh)
    "Pc": "pv_production_kwh",  # PV to consumers (kWh)
    "Pb": "battery_charge_kwh",  # PV to battery (kWh)
    "Gb": "battery_discharge_kwh",  # Battery to consumers (kWh)
}

# Reverse: our entity_type to VRM attribute code
ENTITY_TYPE_TO_VRM = {
    "grid_consumption": "Gc",
    "grid_feedin": "Pg",
    "pv_production": "Pc",
    "battery_charge": "Pb",
    "battery_discharge": "Gb",
}


def import_vrm_api(db: Session, job: ImportJob, source: SourceConnection) -> None:
    """Fetch energy stats from VRM API and create normalized measurements."""
    config = source.connection_config_json or {}
    access_token = config.get("access_token", "")
    installation_id = config.get("installation_id", "")

    if not access_token or not installation_id:
        raise ValueError("access_token und installation_id sind erforderlich")

    # Determine time range
    meta = job.job_metadata_json or {}
    if "start_date" in meta:
        start_dt = datetime.fromisoformat(meta["start_date"]).replace(tzinfo=UTC)
    else:
        start_dt = (datetime.now(UTC) - timedelta(days=31)).replace(hour=0, minute=0, second=0, microsecond=0)

    if "end_date" in meta:
        end_dt = datetime.fromisoformat(meta["end_date"]).replace(tzinfo=UTC)
    else:
        end_dt = datetime.now(UTC)

    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())

    # Get entity mappings to know which data to fetch
    mappings = db.query(EntityMapping).filter(EntityMapping.source_connection_id == source.id).all()

    # Determine which VRM attribute codes we need
    attr_codes = set()
    for mapping in mappings:
        vrm_code = ENTITY_TYPE_TO_VRM.get(mapping.entity_type)
        if vrm_code:
            attr_codes.add(vrm_code)

    if not attr_codes:
        # Default: fetch all known attributes
        attr_codes = set(VRM_ATTRIBUTE_MAP.keys())

    headers = {
        "X-Authorization": f"Token {access_token}",
        "Content-Type": "application/json",
    }

    # Fetch stats from VRM API
    params = {
        "start": start_ts,
        "end": end_ts,
        "interval": "hours",
        "type": "custom",
    }
    params["attributeCodes[]"] = list(attr_codes)

    url = f"{VRM_API_BASE}/installations/{installation_id}/stats"

    try:
        with httpx.Client(timeout=60) as client:
            resp = client.get(url, headers=headers, params=params)
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            raise ValueError("VRM API: Token ungueltig oder abgelaufen") from exc
        if exc.response.status_code == 404:
            raise ValueError(f"VRM API: Installation {installation_id} nicht gefunden") from exc
        raise ValueError(f"VRM API Fehler: HTTP {exc.response.status_code}") from exc
    except httpx.ConnectError as exc:
        raise ValueError("VRM API nicht erreichbar") from exc

    data = resp.json()
    records = data.get("records", {})
    totals = data.get("totals", {})

    if not records:
        logger.info("Keine VRM-Daten fuer den Zeitraum")
        job.status = "completed"
        return

    # Process each attribute code's time series
    for attr_code, measurement_type in VRM_ATTRIBUTE_MAP.items():
        ts_data = records.get(attr_code, [])
        if not ts_data:
            continue

        # Find matching entity mapping for unit assignment
        target_unit_id = 0
        for mapping in mappings:
            if ENTITY_TYPE_TO_VRM.get(mapping.entity_type) == attr_code:
                target_unit_id = mapping.unit_id or 0
                break

        for entry in ts_data:
            if len(entry) < 2:
                continue

            ts_ms = entry[0]  # Unix timestamp in milliseconds
            value = entry[1]  # kWh value

            if value is None or value == 0:
                continue

            ts = datetime.fromtimestamp(ts_ms / 1000, tz=UTC)
            hour_start = ts.replace(minute=0, second=0, microsecond=0)

            # Store raw measurement
            raw = RawMeasurement(
                import_job_id=job.id,
                source_connection_id=source.id,
                timestamp=ts,
                value_raw=float(value),
                unit="kWh",
                metadata_json={"vrm_attr": attr_code},
            )
            db.add(raw)
            job.records_imported += 1

            # Store normalized measurement
            if target_unit_id > 0 and float(value) > 0:
                normalized = NormalizedMeasurement(
                    unit_id=target_unit_id,
                    measurement_type=measurement_type,
                    timestamp=ts,
                    value=float(value),
                    measurement_unit="kWh",
                    period_start=hour_start,
                    period_end=hour_start + timedelta(hours=1),
                )
                db.add(normalized)

    # Log totals
    total_info = {k: v for k, v in totals.items() if k in VRM_ATTRIBUTE_MAP}
    logger.info(
        "VRM API import: %d records, totals: %s",
        job.records_imported,
        total_info,
    )
    db.flush()
