"""Billing calculation engine.

Calculates monthly bills for a given unit/tenant based on:
- BillingParameters (Nebenkostenabrechnung): detailed German utility billing
  with categories Energie, Netznutzung, Umlagen, Sonderpositionen
- Normalized energy measurements (grid, PV, battery, feedin)
- Hourly market prices (aWATTar) or fixed pricing rules (legacy fallback)
- Water consumption with configurable split ratios
- Recurring fixed costs allocated by area/equal/fixed

When BillingParameters exist for a site, the detailed Nebenkostenabrechnung
calculation is used.  Otherwise, the legacy PricingRule-based engine runs
for backward compatibility.
"""

import hashlib
import json
import logging
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.billing.models import CalculationLineItem, CalculationRun, HourlyPrice, PricingRule
from app.billing.parameters import BillingParameters
from app.core.models import RecurringCostItem, Site, Unit, WaterRule
from app.sources.models import NormalizedMeasurement
from app.version import VERSION

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

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

    # Resolve BillingParameters for this site & billing period
    params = _get_billing_params(db, site_id, billing_month)

    # Load pricing rules (still used for feedin + legacy fallback)
    rules = db.query(PricingRule).filter(PricingRule.site_id == site_id).all()
    rules_hash = _make_rules_hash(rules, params)

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

    # --- Electricity ---
    if params:
        sort_order = _calc_with_params(
            db, run, params, unit_id, period_start, period_end, rules, warnings, sort_order,
        )
    else:
        sort_order = _calc_legacy(
            db, run, unit_id, period_start, period_end, rules, warnings, sort_order,
        )

    # --- Water ---
    sort_order = _calc_water(db, run, site.id, unit_id, period_start, period_end, warnings, sort_order)

    # --- Recurring fixed costs ---
    sort_order = _calc_fixed(db, run, site, unit, warnings, sort_order)

    # --- Totals ---
    netto_cents = sum(item.total_cents for item in run.line_items)

    if params:
        vat_summary = _calc_vat_summary(run.line_items, params.vat_rate_pct)
        run.vat_summary_json = vat_summary
        brutto_cents = vat_summary["total_brutto_cents"]
    else:
        brutto_cents = netto_cents

    run.total_amount_cents = brutto_cents
    run.warnings_json = warnings if warnings else None

    db.flush()
    logger.info(
        "Calculation run %d: %d items, netto %.2f EUR, brutto %.2f EUR",
        run.id, len(run.line_items), netto_cents / 100, brutto_cents / 100,
    )
    return run


# ---------------------------------------------------------------------------
# BillingParameters lookup
# ---------------------------------------------------------------------------

def _get_billing_params(db: Session, site_id: int, billing_month: str) -> BillingParameters | None:
    """Find BillingParameters valid for the given billing month."""
    year, month = map(int, billing_month.split("-"))
    ref_date = date(year, month, 1)
    return (
        db.query(BillingParameters)
        .filter(
            BillingParameters.site_id == site_id,
            BillingParameters.valid_from <= ref_date,
            (BillingParameters.valid_to.is_(None)) | (BillingParameters.valid_to >= ref_date),
        )
        .order_by(BillingParameters.valid_from.desc())
        .first()
    )


# ---------------------------------------------------------------------------
# Nebenkostenabrechnung calculation (BillingParameters)
# ---------------------------------------------------------------------------

def _calc_with_params(db, run, params, unit_id, start, end, rules, warnings, so):
    """Full Nebenkostenabrechnung using BillingParameters."""

    # ── Messwerte laden ──
    grid_ms = _get_measurements(db, unit_id, "grid_consumption_kwh", start, end)
    pv_ms = _get_measurements(db, unit_id, "pv_production_kwh", start, end)
    feedin_ms = _get_measurements(db, unit_id, "grid_feedin_kwh", start, end)

    grid_kwh = sum(m.value for m in grid_ms)
    pv_kwh = sum(m.value for m in pv_ms)
    feedin_kwh = sum(m.value for m in feedin_ms)

    # PV-Eigenverbrauch = Erzeugung - Einspeisung
    pv_self_kwh = max(0.0, pv_kwh - feedin_kwh) if pv_kwh > 0 else 0.0
    total_kwh = grid_kwh + pv_self_kwh

    if not grid_ms and not pv_ms:
        warnings.append("Keine Verbrauchsdaten fuer diesen Zeitraum")

    # ── 1. ENERGIE ──────────────────────────────────────────────
    if grid_kwh > 0:
        so += 1
        cost_ct = grid_kwh * params.energy_price_ct_kwh
        _add_line(db, run, "energie", "Strombezug Netz",
                  grid_kwh, "kWh", params.energy_price_ct_kwh, round(cost_ct), so)

    if pv_self_kwh > 0:
        pv_price_ct = round(params.energy_price_ct_kwh * params.pv_price_factor, 4)
        so += 1
        cost_ct = pv_self_kwh * pv_price_ct
        _add_line(db, run, "energie",
                  f"PV-Eigenverbrauch ({params.pv_price_factor * 100:.0f}% Rabatt)",
                  pv_self_kwh, "kWh", pv_price_ct, round(cost_ct), so,
                  {"pv_price_factor": params.pv_price_factor})

    if params.energy_base_fee_eur_month > 0:
        so += 1
        fee_ct = round(params.energy_base_fee_eur_month * 100)
        _add_line(db, run, "energie", "Grundgebuehr Energie",
                  1, "Monat", fee_ct, fee_ct, so)

    # Einspeiseverguetung (Gutschrift via PricingRule)
    if feedin_kwh > 0:
        feedin_rule = _find_rule(rules, "feedin")
        if feedin_rule:
            fp = (feedin_rule.parameters_json or {}).get("price_cents_kwh", 0)
            if fp:
                so += 1
                _add_line(db, run, "energie", "Einspeiseverguetung (Gutschrift)",
                          feedin_kwh, "kWh", -fp, round(-(feedin_kwh * fp)), so)

    # ── 2. NETZNUTZUNG ─────────────────────────────────────────
    if grid_kwh > 0 and params.grid_fee_ct_kwh > 0:
        so += 1
        cost_ct = grid_kwh * params.grid_fee_ct_kwh
        _add_line(db, run, "netznutzung", "Netzentgelt (arbeitsbezogen)",
                  grid_kwh, "kWh", params.grid_fee_ct_kwh, round(cost_ct), so)

    if params.grid_fee_base_eur_year > 0:
        so += 1
        monthly_ct = round(params.grid_fee_base_eur_year * 100 / 12, 2)
        _add_line(db, run, "netznutzung", "Netzentgelt (Grundpreis)",
                  1, "Monat", monthly_ct, round(monthly_ct), so)

    # ── 3. UMLAGEN, ABGABEN, STEUERN ──────────────────────────
    # Applied to grid consumption (Netzstrom).  PV-Eigenverbrauch
    # is typically exempt from most UAS in Mieterstrom models.
    uas_items = [
        ("Konzessionsabgabe", params.uas_konzessionsabgabe),
        ("Umlage abschaltbare Lasten", params.uas_abschaltbare_lasten),
        ("KWK-Umlage", params.uas_kwk_umlage),
        ("Offshore-Netzumlage", params.uas_offshore),
        ("Stromsteuer", params.uas_stromsteuer),
        ("\u00a719 StromNEV-Umlage", params.uas_stromnev),
    ]

    for name, rate_ct in uas_items:
        if rate_ct > 0 and grid_kwh > 0:
            so += 1
            cost_ct = grid_kwh * rate_ct
            _add_line(db, run, "umlagen", name,
                      grid_kwh, "kWh", rate_ct, round(cost_ct), so)

    # ── 4. SONDERPOSITIONEN ────────────────────────────────────
    if params.invest_levy_base_ct > 0 and params.invest_levy_factor > 0 and total_kwh > 0:
        levy_ct = round(params.invest_levy_base_ct * params.invest_levy_factor, 4)
        so += 1
        cost_ct = total_kwh * levy_ct
        _add_line(db, run, "sonderpositionen", "Investitionsumlage",
                  total_kwh, "kWh", levy_ct, round(cost_ct), so,
                  {"base_ct": params.invest_levy_base_ct,
                   "factor": params.invest_levy_factor})

    if params.invest_levy_pv_factor > 0 and pv_self_kwh > 0:
        pv_levy_ct = round(params.invest_levy_base_ct * params.invest_levy_pv_factor, 4)
        so += 1
        cost_ct = pv_self_kwh * pv_levy_ct
        _add_line(db, run, "sonderpositionen", "PV-Investitionsumlage",
                  pv_self_kwh, "kWh", pv_levy_ct, round(cost_ct), so,
                  {"base_ct": params.invest_levy_base_ct,
                   "pv_factor": params.invest_levy_pv_factor})

    return so


# ---------------------------------------------------------------------------
# Legacy PricingRule-based calculation
# ---------------------------------------------------------------------------

def _calc_legacy(db, run, unit_id, start, end, rules, warnings, so):
    """Legacy calculation using PricingRules (backward compatibility)."""
    so = _calc_grid(db, run, unit_id, start, end, rules, warnings, so)
    so = _calc_pv(db, run, unit_id, start, end, rules, warnings, so)
    so = _calc_battery(db, run, unit_id, start, end, rules, warnings, so)
    so = _calc_feedin(db, run, unit_id, start, end, rules, warnings, so)
    return so


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
            db, run, "electricity_grid", "Netzbezug (dynamisch)",
            total_kwh, "kWh", avg_price, total_cost, so,
            {"pricing": "dynamic", "markup_cents": markup},
        )

    elif rule and rule.rule_type == "grid_fixed":
        params = rule.parameters_json or {}
        price = params.get("price_cents_kwh", 30)
        total_kwh = sum(m.value for m in measurements)
        so += 1
        _add_line(db, run, "electricity_grid", "Netzbezug (Festpreis)",
                  total_kwh, "kWh", price, total_kwh * price, so)
    else:
        total_kwh = sum(m.value for m in measurements)
        warnings.append(f"Keine Preisregel fuer Netzbezug ({total_kwh:.1f} kWh)")

    # Base fee
    if rule:
        bf = (rule.parameters_json or {}).get("base_fee_cents", 0)
        if bf:
            so += 1
            _add_line(db, run, "electricity_grid", "Grundgebuehr Strom",
                      1, "Monat", bf, bf, so)
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
        _add_line(db, run, "electricity_pv", "PV-Eigenverbrauch",
                  total, "kWh", price, total * price, so)
    return so


def _calc_battery(db, run, unit_id, start, end, rules, warnings, so):
    rule = _find_rule(rules, "battery")
    if not rule:
        return so
    price = (rule.parameters_json or {}).get("price_cents_kwh", 0)
    for mtype, desc in [
        ("battery_discharge_kwh", "Batterie-Entladung"),
        ("battery_charge_kwh", "Batterie-Ladung"),
    ]:
        ms = _get_measurements(db, unit_id, mtype, start, end)
        total = sum(m.value for m in ms)
        if total > 0 and price:
            so += 1
            _add_line(db, run, "electricity_battery", desc,
                      total, "kWh", price, total * price, so)
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
            db, run, "electricity_feedin", "Netzeinspeisung (Gutschrift)",
            total, "kWh", -price, -(total * price), so,
        )
    return so


# ---------------------------------------------------------------------------
# Water & fixed costs (shared by both modes)
# ---------------------------------------------------------------------------

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
        _add_line(db, run, "water",
                  f"Wasserverbrauch ({ratio * 100:.0f}%)",
                  unit_m3, "m\u00b3", price, unit_m3 * price, so)
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
            db, run, "fixed_cost",
            f"{ci.name} ({ratio * 100:.1f}%)",
            1, "Monat", allocated, allocated, so,
            {"method": ci.allocation_method, "ratio": ratio},
        )
    return so


# ---------------------------------------------------------------------------
# VAT calculation
# ---------------------------------------------------------------------------

def _calc_vat_summary(line_items: list[CalculationLineItem], vat_rate_pct: float) -> dict:
    """Calculate VAT grouped by category.

    Returns a dict stored in CalculationRun.vat_summary_json with the schema::

        {
            "categories": {
                "energie": {"netto_cents": ..., "vat_cents": ..., "brutto_cents": ...},
                ...
            },
            "total_netto_cents": ...,
            "total_vat_cents": ...,
            "total_brutto_cents": ...,
            "vat_rate_pct": ...
        }
    """
    by_cat: dict[str, dict] = {}
    for item in line_items:
        cat = item.category
        if cat not in by_cat:
            by_cat[cat] = {"netto_cents": 0, "vat_cents": 0, "brutto_cents": 0}
        by_cat[cat]["netto_cents"] += item.total_cents

    total_netto = 0
    total_vat = 0
    for vals in by_cat.values():
        vat = round(vals["netto_cents"] * vat_rate_pct / 100)
        vals["vat_cents"] = vat
        vals["brutto_cents"] = vals["netto_cents"] + vat
        vals["vat_rate_pct"] = vat_rate_pct
        total_netto += vals["netto_cents"]
        total_vat += vat

    return {
        "categories": by_cat,
        "total_netto_cents": total_netto,
        "total_vat_cents": total_vat,
        "total_brutto_cents": total_netto + total_vat,
        "vat_rate_pct": vat_rate_pct,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _add_line(db, run, category, description, quantity, qty_unit,
              price_cents, total_cents, sort_order, metadata=None):
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


def _make_rules_hash(rules: list[PricingRule], params: BillingParameters | None) -> str:
    """Create a reproducible hash of all pricing config."""
    data = json.dumps(
        [r.parameters_json for r in rules], sort_keys=True, default=str,
    ).encode()
    h = hashlib.md5(data).hexdigest()[:8]

    if params:
        pdata = json.dumps({
            "id": params.id,
            "energy_price_ct_kwh": params.energy_price_ct_kwh,
            "grid_fee_ct_kwh": params.grid_fee_ct_kwh,
            "vat_rate_pct": params.vat_rate_pct,
            "tenant_share": params.tenant_share,
            "updated_at": str(params.updated_at),
        }, sort_keys=True).encode()
        h = f"{h}_{hashlib.md5(pdata).hexdigest()[:8]}"

    return h
