"""aWATTar adapter - import hourly dynamic electricity prices.

Fetches day-ahead market prices from the aWATTar API (Germany/Austria).
Prices are in EUR/MWh and converted to EUR/kWh for storage.
"""

import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session

from app.billing.models import HourlyPrice
from app.sources.models import ImportJob, SourceConnection

logger = logging.getLogger(__name__)

AWATTAR_URLS = {
    "de": "https://api.awattar.de/v1/marketdata",
    "at": "https://api.awattar.at/v1/marketdata",
}


def import_awattar_prices(db: Session, job: ImportJob, source: SourceConnection) -> None:
    """Fetch hourly prices from aWATTar API and store them."""
    config = source.connection_config_json or {}
    country = config.get("country", "de").lower()

    base_url = AWATTAR_URLS.get(country)
    if not base_url:
        raise ValueError(f"Unsupported country: {country}. Use 'de' or 'at'.")

    # Determine time range from job metadata
    meta = job.job_metadata_json or {}
    if "start_ms" in meta and "end_ms" in meta:
        start_ms = int(meta["start_ms"])
        end_ms = int(meta["end_ms"])
    elif "year" in meta and "month" in meta:
        year = int(meta["year"])
        month = int(meta["month"])
        start_dt = datetime(year, month, 1, tzinfo=UTC)
        if month == 12:
            end_dt = datetime(year + 1, 1, 1, tzinfo=UTC)
        else:
            end_dt = datetime(year, month + 1, 1, tzinfo=UTC)
        start_ms = int(start_dt.timestamp() * 1000)
        end_ms = int(end_dt.timestamp() * 1000)
    else:
        # Default: last 31 days
        now = datetime.now(UTC)
        end_ms = int(now.timestamp() * 1000)
        start_ms = end_ms - (31 * 24 * 60 * 60 * 1000)

    params = {"start": start_ms, "end": end_ms}

    with httpx.Client(timeout=30) as client:
        resp = client.get(base_url, params=params)
        resp.raise_for_status()

    data = resp.json()
    entries = data.get("data", [])

    if not entries:
        logger.info("No price data returned from aWATTar")
        job.status = "completed"
        return

    region = country.upper()
    imported = 0

    for entry in entries:
        ts_ms = entry.get("start_timestamp", 0)
        price_mwh = entry.get("marketprice", 0)

        ts = datetime.fromtimestamp(ts_ms / 1000, tz=UTC)
        price_kwh = price_mwh / 1000  # EUR/MWh -> EUR/kWh

        # Check for duplicate
        existing = (
            db.query(HourlyPrice)
            .filter(
                HourlyPrice.timestamp == ts,
                HourlyPrice.source == "awattar",
                HourlyPrice.region == region,
            )
            .first()
        )

        if existing:
            existing.price_eur_mwh = price_mwh
            existing.price_eur_kwh = price_kwh
        else:
            hp = HourlyPrice(
                source="awattar",
                timestamp=ts,
                price_eur_mwh=price_mwh,
                price_eur_kwh=price_kwh,
                region=region,
            )
            db.add(hp)

        imported += 1

    job.records_imported = imported
    db.flush()
    logger.info("aWATTar import: %d hourly prices for region %s", imported, region)
