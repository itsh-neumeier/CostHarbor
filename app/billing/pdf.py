"""PDF invoice generation using WeasyPrint.

Generates a German-language PDF invoice from a CalculationRun.
"""

import logging
from datetime import datetime

from app.billing.models import CalculationLineItem, CalculationRun
from app.core.models import Site, Tenant, Unit
from app.version import VERSION

logger = logging.getLogger(__name__)

CATEGORY_LABELS = {
    "electricity_grid": "Strom (Netz)",
    "electricity_pv": "Strom (PV-Eigenverbrauch)",
    "electricity_battery": "Strom (Batterie)",
    "electricity_feedin": "Einspeisung (Gutschrift)",
    "water": "Wasser",
    "fixed_cost": "Nebenkosten",
}

MONTH_NAMES = {
    1: "Januar",
    2: "Februar",
    3: "Maerz",
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

    # Group items by category
    categories: dict[str, dict] = {}
    for item in sorted(line_items, key=lambda x: x.sort_order):
        cat = item.category
        if cat not in categories:
            categories[cat] = {"label": CATEGORY_LABELS.get(cat, cat), "items": [], "subtotal": 0}
        categories[cat]["items"].append(item)
        categories[cat]["subtotal"] += item.total_cents

    html = _build_html(run, site, unit, tenant, categories, month_name, year)

    try:
        from weasyprint import HTML

        return HTML(string=html).write_pdf()
    except ImportError:
        logger.warning("WeasyPrint not installed - returning HTML as fallback")
        return html.encode("utf-8")


def _build_html(run, site, unit, tenant, categories, month_name, year) -> str:
    tenant_name = tenant.name if tenant else "-"
    tenant_addr = tenant.address_line1 if tenant and tenant.address_line1 else ""
    tenant_city = f"{tenant.postal_code} {tenant.city}" if tenant else ""
    site_name = site.name if site else "-"
    unit_name = unit.name if unit else "-"
    calc_date = run.calculated_at.strftime("%d.%m.%Y %H:%M") if run.calculated_at else "-"

    cat_html = ""
    for cat_data in categories.values():
        cat_html += f"<h2>{cat_data['label']}</h2>\n<table>\n"
        cat_html += '<tr><th>Beschreibung</th><th class="r">Menge</th><th>Einheit</th><th class="r">Einzelpreis</th><th class="r">Summe</th></tr>\n'
        for it in cat_data["items"]:
            cat_html += (
                f"<tr><td>{it.description}</td>"
                f'<td class="r">{it.quantity:.2f}</td>'
                f"<td>{it.quantity_unit}</td>"
                f'<td class="r">{it.unit_price_cents / 100:.4f} EUR</td>'
                f'<td class="r">{it.total_cents / 100:.2f} EUR</td></tr>\n'
            )
        cat_html += (
            f'<tr class="sub"><td colspan="4">Zwischensumme {cat_data["label"]}</td>'
            f'<td class="r">{cat_data["subtotal"] / 100:.2f} EUR</td></tr></table>\n'
        )

    return f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<style>
@page {{ size: A4; margin: 2cm; }}
body {{ font-family: "DejaVu Sans", Arial, sans-serif; font-size: 10pt; color: #333; line-height: 1.4; }}
h1 {{ font-size: 18pt; color: #1a1a1a; margin-bottom: 4px; }}
h2 {{ font-size: 12pt; margin-top: 18px; border-bottom: 1px solid #ccc; padding-bottom: 2px; }}
.hdr {{ display: flex; justify-content: space-between; margin-bottom: 18px; }}
.hdr div {{ max-width: 48%; }}
.meta {{ font-size: 8pt; color: #888; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 6px; }}
th {{ background: #f5f5f5; text-align: left; padding: 5px 6px; font-size: 8.5pt; border-bottom: 2px solid #ccc; }}
td {{ padding: 4px 6px; border-bottom: 1px solid #eee; font-size: 9pt; }}
.r {{ text-align: right; }}
.sub td {{ font-weight: bold; border-top: 1px solid #999; background: #fafafa; }}
.total td {{ font-weight: bold; font-size: 11pt; border-top: 3px double #333; background: #f0f0f0; }}
.ft {{ margin-top: 25px; font-size: 7.5pt; color: #aaa; text-align: center; }}
</style></head><body>
<h1>Nebenkosten- und Verbrauchsabrechnung</h1>
<div class="hdr">
<div><strong>Empfaenger:</strong><br>{tenant_name}<br>{tenant_addr}<br>{tenant_city}</div>
<div style="text-align:right"><strong>Objekt:</strong> {site_name}<br><strong>Einheit:</strong> {unit_name}<br>
<strong>Monat:</strong> {month_name} {year}<br><strong>Datum:</strong> {datetime.now().strftime("%d.%m.%Y")}</div>
</div>
{cat_html}
<table><tr class="total"><td colspan="4">Gesamtsumme</td><td class="r">{run.total_amount_cents / 100:.2f} EUR</td></tr></table>
<div class="meta" style="margin-top:15px">Berechnung #{run.id} | App v{run.app_version} | Config v{run.config_version} | Regeln v{run.rules_version} | {calc_date}</div>
<div class="ft">Erstellt mit CostHarbor v{VERSION}</div>
</body></html>"""
