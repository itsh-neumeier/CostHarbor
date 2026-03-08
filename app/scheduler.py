"""APScheduler setup for background sync jobs.

Manages automatic data imports from configured sources:
- Home Assistant: hourly fetch of energy/water measurements
- aWATTar: daily price import (14:30 CET, after day-ahead publication)
- VRM IMAP: periodic mailbox polling
"""

import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="Europe/Berlin")

# Default sync intervals per source type (in minutes)
DEFAULT_SYNC_INTERVALS = {
    "homeassistant": 60,  # hourly
    "awattar": 1440,  # daily (managed via cron, not interval)
    "vrm_imap": 360,  # every 6 hours
    "vrm_api": 60,  # hourly (direct API pull)
    "shelly": 60,  # hourly (HTTP poll from device)
    "vrm_upload": 0,  # manual only (file upload)
}


def _run_source_sync(source_id: int) -> None:
    """Execute a sync job for a specific source connection."""
    from app.database import SessionLocal
    from app.sources.adapters import run_import
    from app.sources.models import ImportJob, SourceConnection

    db = SessionLocal()
    try:
        source = db.get(SourceConnection, source_id)
        if not source or not source.is_active:
            logger.info("Source %d inactive or missing, skipping sync", source_id)
            return

        # Create an import job for automated sync
        job = ImportJob(
            source_connection_id=source.id,
            status="pending",
            job_metadata_json={"triggered_by": "scheduler", "auto_sync": True},
        )
        db.add(job)
        db.flush()

        run_import(db, job, source)
        logger.info(
            "Auto-sync completed for source '%s': %d imported, %d failed",
            source.name,
            job.records_imported,
            job.records_failed,
        )
    except Exception:
        logger.exception("Auto-sync failed for source %d", source_id)
    finally:
        db.close()


def _run_awattar_sync(source_id: int) -> None:
    """Fetch tomorrow's aWATTar prices (day-ahead publication)."""
    from app.database import SessionLocal
    from app.sources.adapters import run_import
    from app.sources.models import ImportJob, SourceConnection

    db = SessionLocal()
    try:
        source = db.get(SourceConnection, source_id)
        if not source or not source.is_active:
            return

        # Fetch prices for today and tomorrow
        now = datetime.now(UTC)
        start_ms = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
        end_ms = int((now + timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)

        job = ImportJob(
            source_connection_id=source.id,
            status="pending",
            job_metadata_json={
                "triggered_by": "scheduler",
                "auto_sync": True,
                "start_ms": start_ms,
                "end_ms": end_ms,
            },
        )
        db.add(job)
        db.flush()

        run_import(db, job, source)
        logger.info("aWATTar auto-sync completed: %d prices imported", job.records_imported)
    except Exception:
        logger.exception("aWATTar auto-sync failed for source %d", source_id)
    finally:
        db.close()


def register_source_jobs() -> None:
    """Load all active sources from DB and register scheduler jobs."""
    from app.database import SessionLocal
    from app.sources.models import SourceConnection

    # Remove all existing auto-sync jobs
    for existing_job in scheduler.get_jobs():
        if existing_job.id.startswith("sync_"):
            existing_job.remove()

    db = SessionLocal()
    try:
        sources = db.query(SourceConnection).filter(SourceConnection.is_active.is_(True)).all()

        for source in sources:
            interval = source.sync_interval_minutes
            if interval <= 0:
                continue  # manual only

            job_id = f"sync_{source.id}"

            if source.source_type == "awattar":
                # aWATTar: daily cron at 14:30 CET (day-ahead prices published ~13:00)
                scheduler.add_job(
                    _run_awattar_sync,
                    "cron",
                    hour=14,
                    minute=30,
                    args=[source.id],
                    id=job_id,
                    replace_existing=True,
                    misfire_grace_time=3600,
                )
                logger.info("Registered daily aWATTar sync for source '%s' at 14:30", source.name)
            else:
                # Interval-based sync
                scheduler.add_job(
                    _run_source_sync,
                    "interval",
                    minutes=interval,
                    args=[source.id],
                    id=job_id,
                    replace_existing=True,
                    misfire_grace_time=600,
                    next_run_time=datetime.now() + timedelta(minutes=2),  # first run in 2 min
                )
                logger.info(
                    "Registered %d-min sync for source '%s' (%s)",
                    interval,
                    source.name,
                    source.source_type,
                )

    finally:
        db.close()


def start_scheduler() -> None:
    """Start the background scheduler and register jobs from DB."""
    if not scheduler.running:
        scheduler.start()
        register_source_jobs()
        logger.info("Background scheduler started with %d jobs", len(scheduler.get_jobs()))


def stop_scheduler() -> None:
    """Shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped")
