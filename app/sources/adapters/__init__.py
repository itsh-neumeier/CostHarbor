"""Data source adapters dispatch."""

import logging

from sqlalchemy.orm import Session

from app.sources.models import ImportJob, SourceConnection

logger = logging.getLogger(__name__)


def run_import(db: Session, job: ImportJob, source: SourceConnection) -> None:
    """Dispatch import to the correct adapter based on source type."""
    from datetime import datetime

    job.status = "running"
    job.started_at = datetime.now()
    db.commit()

    try:
        if source.source_type == "shelly":
            from app.sources.adapters.shelly_csv import import_shelly_csv

            import_shelly_csv(db, job, source)
        elif source.source_type in ("vrm_upload", "vrm_imap"):
            from app.sources.adapters.vrm_upload import import_vrm_csv

            import_vrm_csv(db, job, source)
        elif source.source_type == "homeassistant":
            from app.sources.adapters.homeassistant import import_homeassistant

            import_homeassistant(db, job, source)
        elif source.source_type == "awattar":
            from app.sources.adapters.awattar import import_awattar_prices

            import_awattar_prices(db, job, source)
        else:
            raise ValueError(f"Unknown source type: {source.source_type}")

        if job.status == "running":
            job.status = "completed"
        job.completed_at = datetime.now()
        source.last_sync_at = datetime.now()
        db.commit()

    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)[:2000]
        job.completed_at = datetime.now()
        db.commit()
        raise
