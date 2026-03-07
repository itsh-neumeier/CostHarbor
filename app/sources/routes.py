"""Routes for data sources, entity mappings, and file imports."""

import hashlib
import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import require_auth
from app.audit.models import AuditLog
from app.config import settings
from app.core.models import Site, Unit
from app.database import get_db
from app.sources.models import EntityMapping, ImportJob, ImportedFile, SourceConnection

router = APIRouter(tags=["sources"])


def _audit(db: Session, user: dict, action: str, entity_type: str, entity_id: int | None, request: Request, **kw):
    db.add(AuditLog(
        user_id=user["id"], action=action, entity_type=entity_type,
        entity_id=entity_id, ip_address=request.client.host if request.client else None, **kw,
    ))


# ---- Source Connections ----

@router.get("/sources")
async def sources_list(request: Request, db: Session = Depends(get_db)):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    sources = db.query(SourceConnection).order_by(SourceConnection.name).all()
    return request.app.state.templates.TemplateResponse("sources/list.html", {
        "request": request, "user": user, "sources": sources, "active_page": "sources",
    })


@router.get("/sources/new")
async def source_new(request: Request, db: Session = Depends(get_db)):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    sites = db.query(Site).order_by(Site.name).all()
    return request.app.state.templates.TemplateResponse("sources/form.html", {
        "request": request, "user": user, "source": None, "sites": sites, "active_page": "sources",
    })


@router.post("/sources/new")
async def source_create(
    request: Request,
    site_id: int = Form(...),
    name: str = Form(...),
    source_type: str = Form(...),
    connection_config_json: str = Form("{}"),
    db: Session = Depends(get_db),
):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    config = json.loads(connection_config_json)
    source = SourceConnection(
        site_id=site_id, name=name, source_type=source_type,
        connection_config_json=config,
    )
    db.add(source)
    db.flush()
    _audit(db, user, "create", "source_connection", source.id, request)
    db.commit()
    return RedirectResponse(url="/sources", status_code=303)


@router.get("/sources/{source_id}/edit")
async def source_edit(request: Request, source_id: int, db: Session = Depends(get_db)):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    source = db.get(SourceConnection, source_id)
    sites = db.query(Site).order_by(Site.name).all()
    return request.app.state.templates.TemplateResponse("sources/form.html", {
        "request": request, "user": user, "source": source, "sites": sites, "active_page": "sources",
    })


@router.post("/sources/{source_id}/edit")
async def source_update(
    request: Request, source_id: int,
    site_id: int = Form(...),
    name: str = Form(...),
    source_type: str = Form(...),
    connection_config_json: str = Form("{}"),
    db: Session = Depends(get_db),
):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    source = db.get(SourceConnection, source_id)
    old = {"name": source.name, "source_type": source.source_type}
    source.site_id = site_id
    source.name = name
    source.source_type = source_type
    source.connection_config_json = json.loads(connection_config_json)
    source.config_version += 1
    _audit(db, user, "update", "source_connection", source.id, request, old_values_json=old)
    db.commit()
    return RedirectResponse(url="/sources", status_code=303)


@router.post("/sources/{source_id}/delete")
async def source_delete(request: Request, source_id: int, db: Session = Depends(get_db)):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    source = db.get(SourceConnection, source_id)
    _audit(db, user, "delete", "source_connection", source.id, request, old_values_json={"name": source.name})
    db.delete(source)
    db.commit()
    return RedirectResponse(url="/sources", status_code=303)


# ---- Entity Mappings ----

@router.get("/sources/mappings")
async def mappings_list(request: Request, db: Session = Depends(get_db)):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    mappings = db.query(EntityMapping).order_by(EntityMapping.id).all()
    sources = db.query(SourceConnection).order_by(SourceConnection.name).all()
    units = db.query(Unit).order_by(Unit.name).all()
    return request.app.state.templates.TemplateResponse("sources/mappings.html", {
        "request": request, "user": user, "mappings": mappings,
        "sources": sources, "units": units, "active_page": "mappings",
    })


@router.post("/sources/mappings/new")
async def mapping_create(
    request: Request,
    source_connection_id: int = Form(...),
    unit_id: int = Form(None),
    entity_id: str = Form(...),
    entity_type: str = Form(...),
    measurement_unit: str = Form("kWh"),
    db: Session = Depends(get_db),
):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    mapping = EntityMapping(
        source_connection_id=source_connection_id,
        unit_id=unit_id if unit_id else None,
        entity_id=entity_id,
        entity_type=entity_type,
        measurement_unit=measurement_unit,
    )
    db.add(mapping)
    db.flush()
    _audit(db, user, "create", "entity_mapping", mapping.id, request)
    db.commit()
    return RedirectResponse(url="/sources/mappings", status_code=303)


@router.post("/sources/mappings/{mapping_id}/delete")
async def mapping_delete(request: Request, mapping_id: int, db: Session = Depends(get_db)):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    mapping = db.get(EntityMapping, mapping_id)
    _audit(db, user, "delete", "entity_mapping", mapping.id, request,
           old_values_json={"entity_id": mapping.entity_id, "entity_type": mapping.entity_type})
    db.delete(mapping)
    db.commit()
    return RedirectResponse(url="/sources/mappings", status_code=303)


# ---- Imports ----

@router.get("/imports")
async def imports_list(request: Request, db: Session = Depends(get_db)):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    jobs = db.query(ImportJob).order_by(ImportJob.created_at.desc()).all()
    return request.app.state.templates.TemplateResponse("imports/list.html", {
        "request": request, "user": user, "jobs": jobs, "active_page": "imports",
    })


@router.get("/imports/upload")
async def import_upload_form(request: Request, db: Session = Depends(get_db)):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    sources = db.query(SourceConnection).order_by(SourceConnection.name).all()
    return request.app.state.templates.TemplateResponse("imports/upload.html", {
        "request": request, "user": user, "sources": sources,
        "max_size_mb": settings.max_upload_size_mb, "active_page": "imports",
    })


@router.post("/imports/upload")
async def import_upload(
    request: Request,
    source_connection_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user

    # Validate file type
    if not file.filename or not file.filename.lower().endswith(".csv"):
        return request.app.state.templates.TemplateResponse("imports/upload.html", {
            "request": request, "user": user,
            "sources": db.query(SourceConnection).order_by(SourceConnection.name).all(),
            "max_size_mb": settings.max_upload_size_mb,
            "error": "Nur CSV-Dateien sind erlaubt.",
            "active_page": "imports",
        })

    # Read file content
    content = await file.read()

    # Validate file size
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        return request.app.state.templates.TemplateResponse("imports/upload.html", {
            "request": request, "user": user,
            "sources": db.query(SourceConnection).order_by(SourceConnection.name).all(),
            "max_size_mb": settings.max_upload_size_mb,
            "error": f"Datei zu gross. Maximum: {settings.max_upload_size_mb} MB.",
            "active_page": "imports",
        })

    # Save file to upload directory
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_uuid = uuid.uuid4().hex
    stored_filename = f"{file_uuid}_{file.filename}"
    stored_path = upload_dir / stored_filename
    stored_path.write_bytes(content)

    # Compute file hash
    file_hash = hashlib.sha256(content).hexdigest()

    # Create ImportJob
    job = ImportJob(
        source_connection_id=source_connection_id,
        status="pending",
    )
    db.add(job)
    db.flush()

    # Create ImportedFile record
    imported_file = ImportedFile(
        import_job_id=job.id,
        original_filename=file.filename,
        stored_path=str(stored_path),
        file_size_bytes=len(content),
        file_hash=file_hash,
        mime_type="text/csv",
    )
    db.add(imported_file)

    _audit(db, user, "import", "import_job", job.id, request,
           new_values_json={"filename": file.filename, "size_bytes": len(content)})
    db.commit()

    return RedirectResponse(url="/imports", status_code=303)


# ---- Import Trigger ----

@router.post("/imports/{job_id}/run")
async def import_run(request: Request, job_id: int, db: Session = Depends(get_db)):
    """Trigger actual import processing for a pending job."""
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user

    job = db.get(ImportJob, job_id)
    if not job or job.status != "pending":
        return RedirectResponse(url="/imports", status_code=303)

    source = db.get(SourceConnection, job.source_connection_id)
    try:
        from app.sources.adapters import run_import
        run_import(db, job, source)
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Import failed for job %d", job_id)
        job.status = "failed"
        job.error_message = str(e)[:2000]
        db.commit()

    return RedirectResponse(url="/imports", status_code=303)
