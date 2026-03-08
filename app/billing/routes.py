"""Billing routes: calculations, preview, PDF generation, parameters CRUD."""

import logging
from datetime import date, datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.audit.models import AuditLog
from app.billing.models import CalculationRun
from app.billing.parameters import BillingParameters
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


# ---------------------------------------------------------------------------
# BillingParameters CRUD
# ---------------------------------------------------------------------------

_PARAM_FIELDS = [
    "energy_price_ct_kwh",
    "energy_base_fee_eur_month",
    "pv_price_factor",
    "grid_fee_base_eur_year",
    "grid_fee_ct_kwh",
    "uas_konzessionsabgabe",
    "uas_abschaltbare_lasten",
    "uas_kwk_umlage",
    "uas_offshore",
    "uas_stromsteuer",
    "uas_stromnev",
    "invest_levy_base_ct",
    "invest_levy_factor",
    "invest_levy_pv_factor",
    "tenant_share",
    "vat_rate_pct",
]


@router.get("/billing/parameters")
async def parameters_list(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_auth(request)
    if redirect:
        return redirect
    params = (
        db.query(BillingParameters)
        .order_by(BillingParameters.valid_from.desc())
        .all()
    )
    params_list = []
    for p in params:
        site = db.get(Site, p.site_id)
        params_list.append({"param": p, "site_name": site.name if site else "?"})
    return request.app.state.templates.TemplateResponse(
        "billing/parameters.html",
        {
            "request": request,
            "user": user,
            "params_list": params_list,
            "active_page": "billing",
        },
    )


@router.get("/billing/parameters/new")
async def parameters_new_form(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_auth(request)
    if redirect:
        return redirect
    sites = db.query(Site).order_by(Site.name).all()
    return request.app.state.templates.TemplateResponse(
        "billing/parameters_form.html",
        {
            "request": request,
            "user": user,
            "param": None,
            "sites": sites,
            "active_page": "billing",
        },
    )


@router.post("/billing/parameters/new")
async def parameters_create(
    request: Request,
    site_id: int = Form(...),
    valid_from: str = Form(...),
    valid_to: str = Form(None),
    db: Session = Depends(get_db),
):
    user, redirect = _require_auth(request)
    if redirect:
        return redirect

    form = await request.form()
    param = BillingParameters(
        site_id=site_id,
        valid_from=date.fromisoformat(valid_from),
        valid_to=date.fromisoformat(valid_to) if valid_to else None,
    )
    for field in _PARAM_FIELDS:
        val = form.get(field)
        if val is not None and val != "":
            setattr(param, field, float(val))

    db.add(param)
    db.add(
        AuditLog(
            user_id=user["id"],
            action="create",
            entity_type="billing_parameters",
            entity_id=0,
            new_values_json={f: getattr(param, f) for f in _PARAM_FIELDS},
            ip_address=request.client.host if request.client else None,
        )
    )
    db.commit()
    return RedirectResponse(url="/billing/parameters", status_code=303)


@router.get("/billing/parameters/{param_id}/edit")
async def parameters_edit_form(request: Request, param_id: int, db: Session = Depends(get_db)):
    user, redirect = _require_auth(request)
    if redirect:
        return redirect
    param = db.get(BillingParameters, param_id)
    if not param:
        return RedirectResponse(url="/billing/parameters", status_code=303)
    sites = db.query(Site).order_by(Site.name).all()
    return request.app.state.templates.TemplateResponse(
        "billing/parameters_form.html",
        {
            "request": request,
            "user": user,
            "param": param,
            "sites": sites,
            "active_page": "billing",
        },
    )


@router.post("/billing/parameters/{param_id}/edit")
async def parameters_update(
    request: Request,
    param_id: int,
    site_id: int = Form(...),
    valid_from: str = Form(...),
    valid_to: str = Form(None),
    db: Session = Depends(get_db),
):
    user, redirect = _require_auth(request)
    if redirect:
        return redirect

    param = db.get(BillingParameters, param_id)
    if not param:
        return RedirectResponse(url="/billing/parameters", status_code=303)

    form = await request.form()
    old_values = {f: getattr(param, f) for f in _PARAM_FIELDS}

    param.site_id = site_id
    param.valid_from = date.fromisoformat(valid_from)
    param.valid_to = date.fromisoformat(valid_to) if valid_to else None

    for field in _PARAM_FIELDS:
        val = form.get(field)
        if val is not None and val != "":
            setattr(param, field, float(val))

    db.add(
        AuditLog(
            user_id=user["id"],
            action="update",
            entity_type="billing_parameters",
            entity_id=param.id,
            old_values_json=old_values,
            new_values_json={f: getattr(param, f) for f in _PARAM_FIELDS},
            ip_address=request.client.host if request.client else None,
        )
    )
    db.commit()
    return RedirectResponse(url="/billing/parameters", status_code=303)


@router.post("/billing/parameters/{param_id}/delete")
async def parameters_delete(request: Request, param_id: int, db: Session = Depends(get_db)):
    user, redirect = _require_auth(request)
    if redirect:
        return redirect
    param = db.get(BillingParameters, param_id)
    if param:
        db.add(
            AuditLog(
                user_id=user["id"],
                action="delete",
                entity_type="billing_parameters",
                entity_id=param.id,
                old_values_json={f: getattr(param, f) for f in _PARAM_FIELDS},
                ip_address=request.client.host if request.client else None,
            )
        )
        db.delete(param)
        db.commit()
    return RedirectResponse(url="/billing/parameters", status_code=303)
