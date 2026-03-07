"""Document routes."""

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.documents.models import Document

router = APIRouter(tags=["documents"])


@router.get("/documents")
async def documents_list(request: Request, db: Session = Depends(get_db)):
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    docs = db.query(Document).order_by(Document.created_at.desc()).limit(100).all()
    return request.app.state.templates.TemplateResponse(
        "documents/list.html",
        {
            "request": request,
            "user": user,
            "documents": docs,
            "active_page": "documents",
        },
    )


@router.get("/documents/{doc_id}/download")
async def document_download(request: Request, doc_id: int, db: Session = Depends(get_db)):
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    doc = db.get(Document, doc_id)
    if not doc or not Path(doc.stored_path).exists():
        return RedirectResponse(url="/documents", status_code=303)
    return FileResponse(doc.stored_path, filename=doc.filename, media_type="application/pdf")
