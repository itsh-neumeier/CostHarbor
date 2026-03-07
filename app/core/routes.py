"""Routes for sites, units, tenants, cost items, water rules, and pricing rules."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import require_auth
from app.audit.models import AuditLog
from app.billing.models import PricingRule
from app.core.models import RecurringCostItem, Site, Tenant, Unit, WaterRule
from app.database import get_db

router = APIRouter(tags=["core"])


def _audit(db: Session, user: dict, action: str, entity_type: str, entity_id: int | None, request: Request, **kw):
    db.add(AuditLog(
        user_id=user["id"], action=action, entity_type=entity_type,
        entity_id=entity_id, ip_address=request.client.host if request.client else None, **kw,
    ))


# ---- Sites ----

@router.get("/sites")
async def sites_list(request: Request, db: Session = Depends(get_db)):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    sites = db.query(Site).order_by(Site.name).all()
    return request.app.state.templates.TemplateResponse("sites/list.html", {
        "request": request, "user": user, "sites": sites, "active_page": "sites",
    })


@router.get("/sites/new")
async def site_new(request: Request):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    return request.app.state.templates.TemplateResponse("sites/form.html", {
        "request": request, "user": user, "site": None, "active_page": "sites",
    })


@router.post("/sites/new")
async def site_create(
    request: Request,
    name: str = Form(...), address: str = Form(""), city: str = Form(""),
    postal_code: str = Form(""), country: str = Form("DE"),
    total_area_sqm: float = Form(0), notes: str = Form(""),
    db: Session = Depends(get_db),
):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    site = Site(name=name, address=address, city=city, postal_code=postal_code,
                country=country, total_area_sqm=total_area_sqm, notes=notes or None)
    db.add(site)
    db.flush()
    _audit(db, user, "create", "site", site.id, request)
    db.commit()
    return RedirectResponse(url="/sites", status_code=303)


@router.get("/sites/{site_id}/edit")
async def site_edit(request: Request, site_id: int, db: Session = Depends(get_db)):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    site = db.get(Site, site_id)
    return request.app.state.templates.TemplateResponse("sites/form.html", {
        "request": request, "user": user, "site": site, "active_page": "sites",
    })


@router.post("/sites/{site_id}/edit")
async def site_update(
    request: Request, site_id: int,
    name: str = Form(...), address: str = Form(""), city: str = Form(""),
    postal_code: str = Form(""), country: str = Form("DE"),
    total_area_sqm: float = Form(0), notes: str = Form(""),
    db: Session = Depends(get_db),
):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    site = db.get(Site, site_id)
    old = {"name": site.name, "address": site.address, "total_area_sqm": float(site.total_area_sqm)}
    site.name = name
    site.address = address
    site.city = city
    site.postal_code = postal_code
    site.country = country
    site.total_area_sqm = total_area_sqm
    site.notes = notes or None
    site.config_version += 1
    _audit(db, user, "update", "site", site.id, request, old_values_json=old)
    db.commit()
    return RedirectResponse(url="/sites", status_code=303)


@router.post("/sites/{site_id}/delete")
async def site_delete(request: Request, site_id: int, db: Session = Depends(get_db)):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    site = db.get(Site, site_id)
    _audit(db, user, "delete", "site", site.id, request, old_values_json={"name": site.name})
    db.delete(site)
    db.commit()
    return RedirectResponse(url="/sites", status_code=303)


# ---- Units ----

@router.get("/units")
async def units_list(request: Request, db: Session = Depends(get_db)):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    units = db.query(Unit).order_by(Unit.name).all()
    return request.app.state.templates.TemplateResponse("units/list.html", {
        "request": request, "user": user, "units": units, "active_page": "units",
    })


@router.get("/units/new")
async def unit_new(request: Request, db: Session = Depends(get_db)):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    sites = db.query(Site).order_by(Site.name).all()
    return request.app.state.templates.TemplateResponse("units/form.html", {
        "request": request, "user": user, "unit": None, "sites": sites, "active_page": "units",
    })


@router.post("/units/new")
async def unit_create(
    request: Request, site_id: int = Form(...), name: str = Form(...),
    area_sqm: float = Form(0), description: str = Form(""),
    db: Session = Depends(get_db),
):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    unit = Unit(site_id=site_id, name=name, area_sqm=area_sqm, description=description or None)
    db.add(unit)
    db.flush()
    _audit(db, user, "create", "unit", unit.id, request)
    db.commit()
    return RedirectResponse(url="/units", status_code=303)


@router.get("/units/{unit_id}/edit")
async def unit_edit(request: Request, unit_id: int, db: Session = Depends(get_db)):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    unit = db.get(Unit, unit_id)
    sites = db.query(Site).order_by(Site.name).all()
    return request.app.state.templates.TemplateResponse("units/form.html", {
        "request": request, "user": user, "unit": unit, "sites": sites, "active_page": "units",
    })


@router.post("/units/{unit_id}/edit")
async def unit_update(
    request: Request, unit_id: int, site_id: int = Form(...),
    name: str = Form(...), area_sqm: float = Form(0), description: str = Form(""),
    db: Session = Depends(get_db),
):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    unit = db.get(Unit, unit_id)
    unit.site_id = site_id
    unit.name = name
    unit.area_sqm = area_sqm
    unit.description = description or None
    _audit(db, user, "update", "unit", unit.id, request)
    db.commit()
    return RedirectResponse(url="/units", status_code=303)


@router.post("/units/{unit_id}/delete")
async def unit_delete(request: Request, unit_id: int, db: Session = Depends(get_db)):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    unit = db.get(Unit, unit_id)
    _audit(db, user, "delete", "unit", unit.id, request)
    db.delete(unit)
    db.commit()
    return RedirectResponse(url="/units", status_code=303)


# ---- Tenants ----

@router.get("/tenants")
async def tenants_list(request: Request, db: Session = Depends(get_db)):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    tenants = db.query(Tenant).order_by(Tenant.name).all()
    return request.app.state.templates.TemplateResponse("tenants/list.html", {
        "request": request, "user": user, "tenants": tenants, "active_page": "tenants",
    })


@router.get("/tenants/new")
async def tenant_new(request: Request, db: Session = Depends(get_db)):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    units = db.query(Unit).order_by(Unit.name).all()
    return request.app.state.templates.TemplateResponse("tenants/form.html", {
        "request": request, "user": user, "tenant": None, "units": units, "active_page": "tenants",
    })


@router.post("/tenants/new")
async def tenant_create(
    request: Request, unit_id: int = Form(...), name: str = Form(...),
    email: str = Form(""), address_line1: str = Form(""), city: str = Form(""),
    postal_code: str = Form(""), move_in_date: str = Form(""),
    db: Session = Depends(get_db),
):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    from datetime import date as date_type
    mid = date_type.fromisoformat(move_in_date) if move_in_date else None
    tenant = Tenant(
        unit_id=unit_id, name=name, email=email or None,
        address_line1=address_line1, city=city, postal_code=postal_code,
        move_in_date=mid,
    )
    db.add(tenant)
    db.flush()
    _audit(db, user, "create", "tenant", tenant.id, request)
    db.commit()
    return RedirectResponse(url="/tenants", status_code=303)


@router.get("/tenants/{tenant_id}/edit")
async def tenant_edit(request: Request, tenant_id: int, db: Session = Depends(get_db)):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    tenant = db.get(Tenant, tenant_id)
    units = db.query(Unit).order_by(Unit.name).all()
    return request.app.state.templates.TemplateResponse("tenants/form.html", {
        "request": request, "user": user, "tenant": tenant, "units": units, "active_page": "tenants",
    })


@router.post("/tenants/{tenant_id}/edit")
async def tenant_update(
    request: Request, tenant_id: int,
    unit_id: int = Form(...), name: str = Form(...), email: str = Form(""),
    address_line1: str = Form(""), city: str = Form(""), postal_code: str = Form(""),
    move_in_date: str = Form(""), move_out_date: str = Form(""),
    is_active: bool = Form(True),
    db: Session = Depends(get_db),
):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    from datetime import date as date_type
    tenant = db.get(Tenant, tenant_id)
    tenant.unit_id = unit_id
    tenant.name = name
    tenant.email = email or None
    tenant.address_line1 = address_line1
    tenant.city = city
    tenant.postal_code = postal_code
    tenant.move_in_date = date_type.fromisoformat(move_in_date) if move_in_date else None
    tenant.move_out_date = date_type.fromisoformat(move_out_date) if move_out_date else None
    tenant.is_active = is_active
    _audit(db, user, "update", "tenant", tenant.id, request)
    db.commit()
    return RedirectResponse(url="/tenants", status_code=303)


@router.post("/tenants/{tenant_id}/delete")
async def tenant_delete(request: Request, tenant_id: int, db: Session = Depends(get_db)):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    tenant = db.get(Tenant, tenant_id)
    _audit(db, user, "delete", "tenant", tenant.id, request)
    db.delete(tenant)
    db.commit()
    return RedirectResponse(url="/tenants", status_code=303)


# ---- Recurring Cost Items ----

@router.get("/costs")
async def costs_list(request: Request, db: Session = Depends(get_db)):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    items = db.query(RecurringCostItem).order_by(RecurringCostItem.name).all()
    return request.app.state.templates.TemplateResponse("costs/list.html", {
        "request": request, "user": user, "items": items, "active_page": "costs",
    })


@router.get("/costs/new")
async def cost_new(request: Request, db: Session = Depends(get_db)):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    sites = db.query(Site).order_by(Site.name).all()
    return request.app.state.templates.TemplateResponse("costs/form.html", {
        "request": request, "user": user, "item": None, "sites": sites, "active_page": "costs",
    })


@router.post("/costs/new")
async def cost_create(
    request: Request, site_id: int = Form(...), name: str = Form(...),
    amount_cents: int = Form(...), allocation_method: str = Form("area"),
    db: Session = Depends(get_db),
):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    item = RecurringCostItem(site_id=site_id, name=name, amount_cents=amount_cents,
                              allocation_method=allocation_method)
    db.add(item)
    db.flush()
    _audit(db, user, "create", "recurring_cost_item", item.id, request)
    db.commit()
    return RedirectResponse(url="/costs", status_code=303)


@router.get("/costs/{item_id}/edit")
async def cost_edit(request: Request, item_id: int, db: Session = Depends(get_db)):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    item = db.get(RecurringCostItem, item_id)
    sites = db.query(Site).order_by(Site.name).all()
    return request.app.state.templates.TemplateResponse("costs/form.html", {
        "request": request, "user": user, "item": item, "sites": sites, "active_page": "costs",
    })


@router.post("/costs/{item_id}/edit")
async def cost_update(
    request: Request, item_id: int, site_id: int = Form(...),
    name: str = Form(...), amount_cents: int = Form(...),
    allocation_method: str = Form("area"),
    db: Session = Depends(get_db),
):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    item = db.get(RecurringCostItem, item_id)
    item.site_id = site_id
    item.name = name
    item.amount_cents = amount_cents
    item.allocation_method = allocation_method
    _audit(db, user, "update", "recurring_cost_item", item.id, request)
    db.commit()
    return RedirectResponse(url="/costs", status_code=303)


@router.post("/costs/{item_id}/delete")
async def cost_delete(request: Request, item_id: int, db: Session = Depends(get_db)):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    item = db.get(RecurringCostItem, item_id)
    _audit(db, user, "delete", "recurring_cost_item", item.id, request)
    db.delete(item)
    db.commit()
    return RedirectResponse(url="/costs", status_code=303)


# ---- Pricing Rules ----

@router.get("/billing/rules")
async def pricing_rules_list(request: Request, db: Session = Depends(get_db)):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    rules = db.query(PricingRule).order_by(PricingRule.name).all()
    sites = db.query(Site).order_by(Site.name).all()
    return request.app.state.templates.TemplateResponse("billing/rules.html", {
        "request": request, "user": user, "rules": rules, "sites": sites, "active_page": "billing",
    })


@router.post("/billing/rules/new")
async def pricing_rule_create(
    request: Request, site_id: int = Form(...), name: str = Form(...),
    rule_type: str = Form(...), parameters_json: str = Form("{}"),
    db: Session = Depends(get_db),
):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    import json
    params = json.loads(parameters_json)
    rule = PricingRule(site_id=site_id, name=name, rule_type=rule_type, parameters_json=params)
    db.add(rule)
    db.flush()
    _audit(db, user, "create", "pricing_rule", rule.id, request)
    db.commit()
    return RedirectResponse(url="/billing/rules", status_code=303)


@router.post("/billing/rules/{rule_id}/delete")
async def pricing_rule_delete(request: Request, rule_id: int, db: Session = Depends(get_db)):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    rule = db.get(PricingRule, rule_id)
    _audit(db, user, "delete", "pricing_rule", rule.id, request)
    db.delete(rule)
    db.commit()
    return RedirectResponse(url="/billing/rules", status_code=303)


# ---- Settings ----

@router.get("/settings")
async def settings_page(request: Request, db: Session = Depends(get_db)):
    user = require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    from app.version import VERSION
    return request.app.state.templates.TemplateResponse("settings/index.html", {
        "request": request, "user": user, "version": VERSION, "active_page": "settings",
    })
