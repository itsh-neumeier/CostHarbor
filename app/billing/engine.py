"""Billing calculation engine.

Calculates monthly bills for a given unit/tenant based on:
- Normalized energy measurements (grid, PV, battery, feedin)
- Hourly market prices (aWATTar) or fixed pricing rules
- Water consumption with configurable split ratios
- Recurring fixed costs allocated by area
"""

import hashlib
import json
import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.billing.models import CalculationLineItem, CalculationRun, HourlyPrice, PricingRule
from app.core.models import RecurringCostItem, Site, Unit, WaterRule
from app.sources.models import NormalizedMeasurement
from app.version import VERSION

logger = logging.getLogger(__name__)


def calculate_billing(
    db: Session,
    site_id: int,
    unit_id: int,
    tenant_id: int,
    billing_month: str,
) -> CalculationRun:
    """Run a full billing calculation for a unit/tenant/month.

    Args:
        billing_month: Format "YYYY-MM"
    """
    site = db.get(Site, site_id)
    unit = db.get(Unit, unit_id)
    if not site or not unit:
        raise ValueError("Standort oder Einheit nicht gefunden")

    year, month = map(int, billing_month.split("-"))
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    period_start = datetime(year, month, 1, tzinfo=UTC)
    period_end = datetime(next_year, next_month, 1, tzinfo=UTC)

    # Load pricing rules for site
    rules = db.query(PricingRule).filter(PricingRule.site_id == site_id).all()
    rules_hash = hashlib.md5(
        json.dumps([r.parameters_json for r in rules], sort_keys=True, default=str).encode()
    ).hexdigest()[:8]

    # Create calculation run
    run = CalculationRun(
        site_id=site_id,
        unit_id=unit_id,
        tenant_id=tenant_id,
        billing_month=billing_month,
        status="draft",
        app_version=VERSION,
        config_version=str(site.config_version),
        rules_version=rules_hash,
        source_snapshot_version="",
        calculated_at=datetime.now(UTC),
    )
    db.add(run)
    db.flush()

    warnings: list[str] = []
    sort_order = 0

    # 1. Electricity - Grid consumption
    sort_order = _calc_grid(db, run, unit_id, period_start, period_end, rules, warnings, sort_order)

    # 2. PV self-consumption
    sort_order = _calc_pv(db, run, unit_id, period_start, period_end, rules, warnings, sort_order)

    # 3. Battery
    sort_order = _calc_battery(db, run, unit_id, period_start, period_end, rules, warnings, sort_order)

    # 4. Grid feedin (credit)
    sort_order = _calc_feedin(db, run, unit_id, period_start, period_end, rules, warnings, sort_order)

    # 5. Water
    sort_order = _calc_water(db, run, site_id, unit_id, period_start, period_end, warnings, sort_order)

    # 6. Fixed costs
    sort_order = _calc_fixed(db, run, site, unit, warnings, sort_order)

    # Sum up
    total = sum(item.total_cents for item in run.line_items)
    run.total_amount_cents = total
    run.warnings_json = warnings if warnings else None

    db.flush()
    logger.info("Calculation run %d: %d items, total %.2f EUR", run.id, len(run.line_items), total / 100)
    return run


def _get_measurements(db: Session, unit_id: int, mtype: str, start: datetime, end: datetime):
    return (
        db.query(NormalizedMeasurement)
        .filter(
            NormalizedMeasurement.unit_id == unit_id,
            NormalizedMeasurement.measurement_type == mtype,
            NormalizedMeasurement.period_start >= start,
            NormalizedMeasurement.period_end <= end,
        )
        .order_by(NormalizedMeasurement.period_start)
        .all()
    )


def _find_rule(rules: list[PricingRule], rule_type: str) -> PricingRule | None:
    for r in rules:
        if r.rule_type == rule_type:
            return r
    return None


def _add_line(db, run, category, description, quantity, qty_unit, price_cents, total_cents, sort_order, metadata=None):
    item = CalculationLineItem(
        calculation_run_id=run.id,
        category=category,
        description=description,
        quantity=round(quantity, 4),
        quantity_unit=qty_unit,
        unit_price_cents=round(price_cents, 4),
        total_cents=round(total_cents),
        sort_order=sort_order,
        metadata_json=metadata,
    )
    run.line_items.append(item)
    return item


def _calc_grid(db, run, unit_id, start, end, rules, warnings, so):
    measurements = _get_measurements(db, unit_id, "grid_consumption_kwh", start, end)
    if not measurements:
        warnings.append("Keine Netzbezugsdaten fuer diesen Zeitraum")
        return so

    rule = _find_rule(rules, "grid_dynamic") or _find_rule(rules, "grid_fixed")

    if rule and rule.rule_type == "grid_dynamic":
        params = rule.parameters_json or {}
        markup = params.get("markup_cents_kwh", 0)
        tax_pct = params.get("tax_pct", 0)
        fallback = params.get("fallback_price_cents_kwh", 30)

        total_kwh, total_cost = 0.0, 0.0
        for m in measurements:
            hp = db.query(HourlyPrice).filter(HourlyPrice.timestamp == m.period_start).first()
            base = (hp.price_eur_kwh * 100) if hp else fallback
            price = (base + markup) * (1 + tax_pct / 100) if tax_pct else base + markup
            total_kwh += m.value
            total_cost += m.value * price

        so += 1
        avg_price = total_cost / total_kwh if total_kwh else 0
        _add_line(
            db,
            run,
            "electricity_grid",
            "Netzbezug (dynamisch)",
            total_kwh,
            "kWh",
            avg_price,
            total_cost,
            so,
            {"pricing": "dynamic", "markup_cents": markup},
        )

    elif rule and rule.rule_type == "grid_fixed":
        params = rule.parameters_json or {}
        price = params.get("price_cents_kwh", 30)
        total_kwh = sum(m.value for m in measurements)
        so += 1
        _add_line(db, run, "electricity_grid", "Netzbezug (Festpreis)", total_kwh, "kWh", price, total_kwh * price, so)
    else:
        total_kwh = sum(m.value for m in measurements)
        warnings.append(f"Keine Preisregel fuer Netzbezug ({total_kwh:.1f} kWh)")

    # Base fee
    if rule:
        bf = (rule.parameters_json or {}).get("base_fee_cents", 0)
        if bf:
            so += 1
            _add_line(db, run, "electricity_grid", "Grundgebuehr Strom", 1, "Monat", bf, bf, so)
    return so


def _calc_pv(db, run, unit_id, start, end, rules, warnings, so):
    measurements = _get_measurements(db, unit_id, "pv_production_kwh", start, end)
    rule = _find_rule(rules, "pv_self")
    if not measurements or not rule:
        return so
    price = (rule.parameters_json or {}).get("price_cents_kwh", 0)
    total = sum(m.value for m in measurements)
    if total > 0 and price:
        so += 1
        _add_line(db, run, "electricity_pv", "PV-Eigenverbrauch", total, "kWh", price, total * price, so)
    return so


def _calc_battery(db, run, unit_id, start, end, rules, warnings, so):
    rule = _find_rule(rules, "battery")
    if not rule:
        return so
    price = (rule.parameters_json or {}).get("price_cents_kwh", 0)
    for mtype, desc in [("battery_discharge_kwh", "Batterie-Entladung"), ("battery_charge_kwh", "Batterie-Ladung")]:
        ms = _get_measurements(db, unit_id, mtype, start, end)
        total = sum(m.value for m in ms)
        if total > 0 and price:
            so += 1
            _add_line(db, run, "electricity_battery", desc, total, "kWh", price, total * price, so)
    return so


def _calc_feedin(db, run, unit_id, start, end, rules, warnings, so):
    measurements = _get_measurements(db, unit_id, "grid_feedin_kwh", start, end)
    rule = _find_rule(rules, "feedin")
    if not measurements or not rule:
        return so
    price = (rule.parameters_json or {}).get("price_cents_kwh", 0)
    total = sum(m.value for m in measurements)
    if total > 0 and price:
        so += 1
        _add_line(
            db, run, "electricity_feedin", "Netzeinspeisung (Gutschrift)", total, "kWh", -price, -(total * price), so
        )
    return so


def _calc_water(db, run, site_id, unit_id, start, end, warnings, so):
    all_water = _get_measurements(db, unit_id, "water_m3", start, end)
    if not all_water:
        return so

    water_rule = db.query(WaterRule).filter(WaterRule.site_id == site_id).first()
    if not water_rule:
        warnings.append("Keine Wasserregel konfiguriert")
        return so

    total_m3 = sum(m.value for m in all_water)
    split = water_rule.split_ratio_json or {}
    uid = str(unit_id)

    if uid in split:
        ratio = float(split[uid])
    elif not split:
        count = db.query(Unit).filter(Unit.site_id == site_id).count()
        ratio = 1.0 / max(count, 1)
    else:
        ratio = 0.5

    unit_m3 = total_m3 * ratio
    price = water_rule.water_price_cents_m3
    if unit_m3 > 0 and price:
        so += 1
        _add_line(db, run, "water", f"Wasserverbrauch ({ratio * 100:.0f}%)", unit_m3, "m3", price, unit_m3 * price, so)
    return so


def _calc_fixed(db, run, site, unit, warnings, so):
    items = db.query(RecurringCostItem).filter(RecurringCostItem.site_id == site.id).all()
    if not items:
        return so

    total_area = float(site.total_area_sqm) if site.total_area_sqm else 1
    unit_area = float(unit.area_sqm) if unit.area_sqm else 0

    for ci in items:
        if ci.allocation_method == "area":
            ratio = unit_area / total_area if total_area > 0 else 0
        elif ci.allocation_method == "equal":
            count = db.query(Unit).filter(Unit.site_id == site.id).count()
            ratio = 1.0 / max(count, 1)
        else:
            ratio = 1.0

        allocated = round(ci.amount_cents * ratio)
        so += 1
        _add_line(
            db,
            run,
            "fixed_cost",
            f"{ci.name} ({ratio * 100:.1f}%)",
            1,
            "Monat",
            allocated,
            allocated,
            so,
            {"method": ci.allocation_method, "ratio": ratio},
        )
    return so
