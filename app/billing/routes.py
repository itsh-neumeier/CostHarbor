"""Billing routes: calculations, preview, PDF generation."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.audit.models import AuditLog
from app.billing.models import CalculationRun
from app.core.models import Site, Tenant, Unit
from app.database import get_db

router = APIRouter(tags=["billing"])
logger = logging.getLogger(__name__)


def _require_auth(request: Request):
    user = request.session.get("user")
    if not user:
        return None, RedirectResponse(url="/login", status_code=303)
    return user, None


@router.get("/billing")
async def billing_list(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_auth(request)
    if redirect:
        return redirect
    runs = db.query(CalculationRun).order_by(CalculationRun.created_at.desc()).limit(100).all()
    # Enrich with unit/tenant names
    enriched = []
    for run in runs:
        unit = db.get(Unit, run.unit_id)
        tenant = db.get(Tenant, run.tenant_id)
        enriched.append(
            {
                "run": run,
                "unit_name": unit.name if unit else "?",
                "tenant_name": tenant.name if tenant else "?",
            }
        )
    return request.app.state.templates.TemplateResponse(
        "billing/list.html",
        {
            "request": request,
            "user": user,
            "runs": enriched,
            "active_page": "billing",
        },
    )


@router.get("/billing/new")
async def billing_new(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_auth(request)
    if redirect:
        return redirect
    sites = db.query(Site).order_by(Site.name).all()
    units = db.query(Unit).order_by(Unit.name).all()
    tenants = db.query(Tenant).filter(Tenant.is_active.is_(True)).order_by(Tenant.name).all()
    return request.app.state.templates.TemplateResponse(
        "billing/new.html",
        {
            "request": request,
            "user": user,
            "sites": sites,
            "units": units,
            "tenants": tenants,
            "active_page": "billing",
        },
    )


@router.post("/billing/calculate")
async def billing_calculate(
    request: Request,
    site_id: int = Form(...),
    unit_id: int = Form(...),
    tenant_id: int = Form(...),
    billing_month: str = Form(...),
    db: Session = Depends(get_db),
):
    user, redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.billing.engine import calculate_billing

    try:
        run = calculate_billing(db, site_id, unit_id, tenant_id, billing_month)
        db.add(
            AuditLog(
                user_id=user["id"],
                action="calculate",
                entity_type="calculation_run",
                entity_id=run.id,
                ip_address=request.client.host if request.client else None,
            )
        )
        db.commit()
        return RedirectResponse(url=f"/billing/{run.id}/preview", status_code=303)
    except Exception as e:
        logger.exception("Calculation failed")
        sites = db.query(Site).order_by(Site.name).all()
        units = db.query(Unit).order_by(Unit.name).all()
        tenants = db.query(Tenant).filter(Tenant.is_active.is_(True)).order_by(Tenant.name).all()
        return request.app.state.templates.TemplateResponse(
            "billing/new.html",
            {
                "request": request,
                "user": user,
                "sites": sites,
                "units": units,
                "tenants": tenants,
                "error": str(e),
                "active_page": "billing",
            },
        )


@router.get("/billing/{run_id}/preview")
async def billing_preview(request: Request, run_id: int, db: Session = Depends(get_db)):
    user, redirect = _require_auth(request)
    if redirect:
        return redirect
    run = db.get(CalculationRun, run_id)
    if not run:
        return RedirectResponse(url="/billing", status_code=303)
    unit = db.get(Unit, run.unit_id)
    tenant = db.get(Tenant, run.tenant_id)
    site = db.get(Site, run.site_id)
    return request.app.state.templates.TemplateResponse(
        "billing/preview.html",
        {
            "request": request,
            "user": user,
            "run": run,
            "unit": unit,
            "tenant": tenant,
            "site": site,
            "line_items": run.line_items,
            "active_page": "billing",
        },
    )


@router.post("/billing/{run_id}/finalize")
async def billing_finalize(request: Request, run_id: int, db: Session = Depends(get_db)):
    user, redirect = _require_auth(request)
    if redirect:
        return redirect
    run = db.get(CalculationRun, run_id)
    if run and run.status == "draft":
        run.status = "final"
        run.finalized_at = datetime.now()
        db.add(
            AuditLog(
                user_id=user["id"],
                action="finalize",
                entity_type="calculation_run",
                entity_id=run.id,
                ip_address=request.client.host if request.client else None,
            )
        )
        db.commit()
    return RedirectResponse(url="/billing", status_code=303)


@router.get("/billing/{run_id}/pdf")
async def billing_pdf(request: Request, run_id: int, db: Session = Depends(get_db)):
    user, redirect = _require_auth(request)
    if redirect:
        return redirect
    run = db.get(CalculationRun, run_id)
    if not run:
        return RedirectResponse(url="/billing", status_code=303)

    from app.billing.pdf import generate_pdf

    unit = db.get(Unit, run.unit_id)
    tenant = db.get(Tenant, run.tenant_id)
    site = db.get(Site, run.site_id)

    pdf_bytes = generate_pdf(run, site, unit, tenant, run.line_items)
    filename = f"Abrechnung_{run.billing_month}_{unit.name if unit else 'unknown'}.pdf"

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
