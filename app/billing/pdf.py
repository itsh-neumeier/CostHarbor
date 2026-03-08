"""PDF invoice generation using WeasyPrint.

Generates a German-language PDF invoice from a CalculationRun.
Supports both the new Nebenkostenabrechnung categories (energie,
netznutzung, umlagen, sonderpositionen) and the legacy categories.
When vat_summary_json is present, a VAT breakdown is rendered.
"""

import logging
from datetime import datetime

from app.billing.models import CalculationLineItem, CalculationRun
from app.core.models import Site, Tenant, Unit
from app.version import VERSION

logger = logging.getLogger(__name__)

CATEGORY_LABELS = {
    # New Nebenkostenabrechnung categories
    "energie": "Energie",
    "netznutzung": "Netznutzung",
    "umlagen": "Umlagen, Abgaben & Steuern",
    "sonderpositionen": "Sonderpositionen",
    # Legacy categories
    "electricity_grid": "Strom (Netz)",
    "electricity_pv": "Strom (PV-Eigenverbrauch)",
    "electricity_battery": "Strom (Batterie)",
    "electricity_feedin": "Einspeisung (Gutschrift)",
    # Shared
    "water": "Wasser",
    "fixed_cost": "Nebenkosten",
}

# Render order for categories
CATEGORY_ORDER = [
    "energie",
    "netznutzung",
    "umlagen",
    "sonderpositionen",
    "electricity_grid",
    "electricity_pv",
    "electricity_battery",
    "electricity_feedin",
    "water",
    "fixed_cost",
]

MONTH_NAMES = {
    1: "Januar",
    2: "Februar",
    3: "M\u00e4rz",
    4: "April",
    5: "Mai",
    6: "Juni",
    7: "Juli",
    8: "August",
    9: "September",
    10: "Oktober",
    11: "November",
    12: "Dezember",
}


def generate_pdf(
    run: CalculationRun,
    site: Site | None,
    unit: Unit | None,
    tenant: Tenant | None,
    line_items: list[CalculationLineItem],
) -> bytes:
    """Generate a PDF invoice and return the bytes."""
    year, month = map(int, run.billing_month.split("-"))
    month_name = MONTH_NAMES.get(month, str(month))

    # Group items by category, preserving defined order
    categories: dict[str, dict] = {}
    for item in sorted(line_items, key=lambda x: x.sort_order):
        cat = item.category
        if cat not in categories:
            categories[cat] = {
                "label": CATEGORY_LABELS.get(cat, cat),
                "items": [],
                "subtotal": 0,
            }
        categories[cat]["items"].append(item)
        categories[cat]["subtotal"] += item.total_cents

    # Sort categories according to CATEGORY_ORDER
    ordered_cats = []
    for key in CATEGORY_ORDER:
        if key in categories:
            ordered_cats.append((key, categories[key]))
    # Append any unknown categories at the end
    for key, val in categories.items():
        if key not in CATEGORY_ORDER:
            ordered_cats.append((key, val))

    html = _build_html(run, site, unit, tenant, ordered_cats, month_name, year)

    try:
        from weasyprint import HTML

        return HTML(string=html).write_pdf()
    except ImportError:
        logger.warning("WeasyPrint not installed - returning HTML as fallback")
        return html.encode("utf-8")


def _fmt_eur(cents: int | float) -> str:
    """Format cents as EUR string with German formatting."""
    val = cents / 100
    if val < 0:
        return f"-{abs(val):,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{val:,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_price(cents: float) -> str:
    """Format a per-unit price in Ct with 4 decimals, or EUR for large values."""
    if abs(cents) >= 100:
        return f"{cents / 100:,.4f} EUR".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{cents:,.4f} Ct".replace(",", "X").replace(".", ",").replace("X", ".")


def _build_html(run, site, unit, tenant, ordered_cats, month_name, year) -> str:
    tenant_name = tenant.name if tenant else "-"
    tenant_addr = tenant.address_line1 if tenant and tenant.address_line1 else ""
    tenant_city = f"{tenant.postal_code} {tenant.city}" if tenant else ""
    site_name = site.name if site else "-"
    site_addr = site.address if site and site.address else ""
    unit_name = unit.name if unit else "-"
    calc_date = run.calculated_at.strftime("%d.%m.%Y %H:%M") if run.calculated_at else "-"
    vat = run.vat_summary_json

    # ── Category tables ──
    cat_html = ""
    for _cat_key, cat_data in ordered_cats:
        cat_html += f"<h2>{cat_data['label']}</h2>\n<table>\n"
        cat_html += (
            "<tr>"
            "<th>Beschreibung</th>"
            '<th class="r">Menge</th>'
            "<th>Einheit</th>"
            '<th class="r">Einzelpreis</th>'
            '<th class="r">Betrag</th>'
            "</tr>\n"
        )
        for it in cat_data["items"]:
            cat_html += (
                f"<tr><td>{it.description}</td>"
                f'<td class="r">{it.quantity:,.2f}</td>'
                f"<td>{it.quantity_unit}</td>"
                f'<td class="r">{_fmt_price(it.unit_price_cents)}</td>'
                f'<td class="r">{_fmt_eur(it.total_cents)}</td></tr>\n'
            )
        cat_html += (
            f'<tr class="sub"><td colspan="4">Zwischensumme {cat_data["label"]}</td>'
            f'<td class="r">{_fmt_eur(cat_data["subtotal"])}</td></tr></table>\n'
        )

    # ── VAT summary ──
    vat_html = ""
    if vat:
        netto = _fmt_eur(vat["total_netto_cents"])
        vat_amt = _fmt_eur(vat["total_vat_cents"])
        brutto = _fmt_eur(vat["total_brutto_cents"])
        rate = vat["vat_rate_pct"]
        vat_html = f"""
<table class="vat-summary">
<tr><td>Zwischensumme netto</td><td class="r">{netto}</td></tr>
<tr><td>zzgl. {rate:.1f}% MwSt.</td><td class="r">{vat_amt}</td></tr>
<tr class="total"><td><strong>Gesamtbetrag brutto</strong></td><td class="r"><strong>{brutto}</strong></td></tr>
</table>"""
    else:
        total = _fmt_eur(run.total_amount_cents)
        vat_html = f"""
<table class="vat-summary">
<tr class="total"><td><strong>Gesamtsumme</strong></td><td class="r"><strong>{total}</strong></td></tr>
</table>"""

    # ── Warnings ──
    warn_html = ""
    if run.warnings_json:
        warn_html = '<div class="warnings"><strong>Hinweise:</strong><ul>'
        for w in run.warnings_json:
            warn_html += f"<li>{w}</li>"
        warn_html += "</ul></div>"

    return f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<style>
@page {{ size: A4; margin: 2cm; }}
body {{ font-family: "DejaVu Sans", Arial, sans-serif; font-size: 10pt; color: #333; line-height: 1.4; }}
h1 {{ font-size: 16pt; color: #1a1a1a; margin-bottom: 2px; }}
.subtitle {{ font-size: 10pt; color: #666; margin-bottom: 16px; }}
h2 {{ font-size: 11pt; margin-top: 18px; border-bottom: 2px solid #2c5282; padding-bottom: 3px; color: #2c5282; }}
.hdr {{ display: flex; justify-content: space-between; margin-bottom: 18px; border: 1px solid #e0e0e0; padding: 12px; border-radius: 4px; }}
.hdr div {{ max-width: 48%; }}
.meta {{ font-size: 8pt; color: #888; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 6px; }}
th {{ background: #edf2f7; text-align: left; padding: 5px 6px; font-size: 8.5pt; border-bottom: 2px solid #cbd5e0; color: #2d3748; }}
td {{ padding: 4px 6px; border-bottom: 1px solid #eee; font-size: 9pt; }}
.r {{ text-align: right; }}
.sub td {{ font-weight: bold; border-top: 1px solid #999; background: #f7fafc; }}
.vat-summary {{ margin-top: 20px; width: 50%; margin-left: auto; }}
.vat-summary td {{ padding: 6px 8px; font-size: 10pt; }}
.vat-summary .total td {{ font-weight: bold; font-size: 12pt; border-top: 3px double #2c5282; background: #ebf8ff; color: #2c5282; }}
.warnings {{ margin-top: 15px; padding: 10px; background: #fffbeb; border: 1px solid #f6e05e; border-radius: 4px; font-size: 9pt; color: #744210; }}
.warnings ul {{ margin: 4px 0 0 16px; padding: 0; }}
.ft {{ margin-top: 25px; font-size: 7.5pt; color: #aaa; text-align: center; }}
</style></head><body>
<h1>Nebenkosten- und Verbrauchsabrechnung</h1>
<div class="subtitle">{month_name} {year}</div>

<div class="hdr">
<div><strong>Empf\u00e4nger:</strong><br>{tenant_name}<br>{tenant_addr}<br>{tenant_city}</div>
<div style="text-align:right"><strong>Objekt:</strong> {site_name}<br>{site_addr}<br>
<strong>Einheit:</strong> {unit_name}<br>
<strong>Datum:</strong> {datetime.now().strftime("%d.%m.%Y")}</div>
</div>

{cat_html}
{vat_html}
{warn_html}

<div class="meta" style="margin-top:15px">
Berechnung #{run.id} | App v{run.app_version} | Config v{run.config_version} | Regeln v{run.rules_version} | {calc_date}
</div>
<div class="ft">Erstellt mit CostHarbor v{VERSION}</div>
</body></html>"""
