"""Additional routes for VRM IMAP mailbox testing and polling."""

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.audit.models import AuditLog
from app.database import get_db
from app.sources.models import ImportJob, SourceConnection

router = APIRouter(tags=["vrm_imap"])
logger = logging.getLogger(__name__)


@router.post("/sources/{source_id}/test-imap")
async def test_imap_connection(request: Request, source_id: int, db: Session = Depends(get_db)):
    """Test IMAP connection for a VRM source."""
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    source = db.get(SourceConnection, source_id)
    if not source or source.source_type != "vrm_imap":
        return RedirectResponse(url="/sources", status_code=303)

    import imaplib

    config = source.connection_config_json or {}
    host = config.get("host", "")
    port = int(config.get("port", 993))
    use_tls = config.get("tls", True)
    username = config.get("username", "")
    password = config.get("password", "")

    try:
        if use_tls:
            conn = imaplib.IMAP4_SSL(host, port)
        else:
            conn = imaplib.IMAP4(host, port)
        conn.login(username, password)
        conn.logout()
        result = "Verbindung erfolgreich!"
    except Exception as e:
        result = f"Verbindungsfehler: {e}"

    # Return to sources page with result (simplified - just redirect)
    logger.info("IMAP test for source %d: %s", source_id, result)
    return RedirectResponse(url="/sources", status_code=303)


@router.post("/sources/{source_id}/fetch-imap")
async def fetch_imap_emails(request: Request, source_id: int, db: Session = Depends(get_db)):
    """Trigger IMAP email fetch for a VRM source."""
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    source = db.get(SourceConnection, source_id)
    if not source or source.source_type != "vrm_imap":
        return RedirectResponse(url="/sources", status_code=303)

    job = ImportJob(source_connection_id=source.id, status="pending")
    db.add(job)
    db.flush()

    db.add(
        AuditLog(
            user_id=user["id"],
            action="imap_fetch",
            entity_type="import_job",
            entity_id=job.id,
            ip_address=request.client.host if request.client else None,
        )
    )

    try:
        from datetime import datetime

        from app.sources.adapters.vrm_imap import fetch_vrm_emails

        job.status = "running"
        job.started_at = datetime.now()
        db.commit()

        fetch_vrm_emails(db, job, source)

        job.status = "completed"
        job.completed_at = datetime.now()
        db.commit()
    except Exception as e:
        logger.exception("IMAP fetch failed")
        job.status = "failed"
        job.error_message = str(e)[:2000]
        db.commit()

    return RedirectResponse(url="/imports", status_code=303)
