"""Audit log routes."""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.audit.models import AuditLog
from app.database import get_db

router = APIRouter(tags=["audit"])

ITEMS_PER_PAGE = 50


@router.get("/audit")
async def audit_list(
    request: Request,
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    total = db.query(AuditLog).count()
    entries = (
        db.query(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .offset((page - 1) * ITEMS_PER_PAGE)
        .limit(ITEMS_PER_PAGE)
        .all()
    )
    total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)

    return request.app.state.templates.TemplateResponse("audit/list.html", {
        "request": request, "user": user,
        "entries": entries, "page": page, "total_pages": total_pages,
        "active_page": "audit",
    })
