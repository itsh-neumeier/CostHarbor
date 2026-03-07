"""VRM IMAP adapter - fetch export emails and download CSV.

Connects to a configured IMAP mailbox, finds VRM export notification emails,
extracts the S3 download link, downloads the CSV, and stores it for import.
"""

import email
import imaplib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.sources.models import ImportJob, ImportedFile, SourceConnection

logger = logging.getLogger(__name__)

# Allowed download domains (SSRF protection)
ALLOWED_DOWNLOAD_DOMAINS = {
    "vrm-uploads.s3.eu-central-1.amazonaws.com",
    "vrm-uploads.s3.amazonaws.com",
}

# Default link extraction pattern
DEFAULT_LINK_PATTERN = r'https://vrm-uploads\.s3[\w.-]*\.amazonaws\.com/[^\s"\'<>]+'

MAX_DOWNLOAD_SIZE = 100 * 1024 * 1024  # 100 MB


def fetch_vrm_emails(db: Session, job: ImportJob, source: SourceConnection) -> None:
    """Connect to IMAP, find VRM export emails, download CSVs."""
    config = source.connection_config_json or {}

    host = config.get("host", "")
    port = int(config.get("port", 993))
    use_tls = config.get("tls", True)
    username = config.get("username", "")
    password = config.get("password", "")
    folder = config.get("folder", "INBOX")
    sender_filter = config.get("sender_filter", "no-reply@victronenergy.com")
    subject_filter = config.get("subject_filter", "Datenexport")
    unread_only = config.get("unread_only", True)
    link_pattern = config.get("extraction_regex", DEFAULT_LINK_PATTERN)

    if not all([host, username, password]):
        raise ValueError("IMAP host, username, and password are required")

    # Connect
    if use_tls:
        conn = imaplib.IMAP4_SSL(host, port)
    else:
        conn = imaplib.IMAP4(host, port)

    try:
        conn.login(username, password)
        conn.select(folder)

        # Build search criteria
        criteria: list[str] = []
        if sender_filter:
            criteria.append(f'FROM "{sender_filter}"')
        if subject_filter:
            criteria.append(f'SUBJECT "{subject_filter}"')
        if unread_only:
            criteria.append("UNSEEN")

        search_str = " ".join(criteria) if criteria else "ALL"
        status, msg_ids = conn.search(None, f"({search_str})")

        if status != "OK" or not msg_ids[0]:
            logger.info("No matching emails found")
            job.status = "completed"
            job.records_imported = 0
            return

        ids = msg_ids[0].split()
        logger.info("Found %d matching emails", len(ids))

        for msg_id in ids[-5:]:  # Process last 5 max
            _process_email(db, job, source, conn, msg_id, link_pattern)

    finally:
        try:
            conn.logout()
        except Exception:
            pass


def _process_email(
    db: Session, job: ImportJob, source: SourceConnection,
    conn: imaplib.IMAP4, msg_id: bytes, link_pattern: str,
) -> None:
    """Process a single VRM email: extract link, download CSV."""
    status, msg_data = conn.fetch(msg_id, "(RFC822)")
    if status != "OK":
        return

    raw_email = msg_data[0][1]
    msg = email.message_from_bytes(raw_email)

    subject = str(email.header.decode_header(msg["Subject"])[0][0] or "")
    if isinstance(subject, bytes):
        subject = subject.decode("utf-8", errors="replace")
    sender = msg.get("From", "")
    date_str = msg.get("Date", "")

    # Extract body text
    body = _get_email_body(msg)
    if not body:
        logger.warning("Empty email body for message")
        return

    # Find download link
    match = re.search(link_pattern, body)
    if not match:
        logger.warning("No download link found in email: %s", subject)
        return

    download_url = match.group(0)

    # Fix quoted-printable artifacts
    download_url = download_url.replace("=\n", "").replace("=3D", "=").replace("&amp;", "&")

    # SSRF validation
    parsed = urlparse(download_url)
    if parsed.hostname not in ALLOWED_DOWNLOAD_DOMAINS:
        logger.error("Blocked download from untrusted domain: %s", parsed.hostname)
        job.records_failed += 1
        return

    # Download file
    try:
        with httpx.Client(timeout=120, follow_redirects=True) as client:
            resp = client.get(download_url)
            resp.raise_for_status()

            if len(resp.content) > MAX_DOWNLOAD_SIZE:
                raise ValueError(f"File too large: {len(resp.content)} bytes")

            # Validate content type
            ct = resp.headers.get("content-type", "")
            if "csv" not in ct and "text" not in ct and "octet-stream" not in ct:
                raise ValueError(f"Unexpected content type: {ct}")

    except httpx.HTTPError as e:
        logger.error("Download failed: %s", e)
        job.records_failed += 1
        return

    # Save file
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Extract filename from URL or generate one
    url_path = parsed.path
    filename = url_path.split("/")[-1].split("?")[0] if "/" in url_path else "vrm_export.csv"
    stored_path = upload_dir / f"vrm_{job.id}_{filename}"
    stored_path.write_bytes(resp.content)

    imported_file = ImportedFile(
        import_job_id=job.id,
        original_filename=filename,
        stored_path=str(stored_path),
        file_size_bytes=len(resp.content),
        mime_type="text/csv",
        source_email_subject=subject[:500],
        source_email_date=_parse_email_date(date_str),
        source_url=download_url[:2000],  # Don't store full signed URL in logs
    )
    db.add(imported_file)
    db.flush()
    job.records_imported += 1
    logger.info("Downloaded VRM export: %s (%d bytes)", filename, len(resp.content))


def _get_email_body(msg: email.message.Message) -> str:
    """Extract text content from email (handles multipart)."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type in ("text/plain", "text/html"):
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    return ""


def _parse_email_date(date_str: str) -> datetime | None:
    """Parse email date header."""
    try:
        parsed = email.utils.parsedate_to_datetime(date_str)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None
