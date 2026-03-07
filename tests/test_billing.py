"""Tests for billing engine."""

from datetime import datetime, timezone

from app.billing.models import CalculationRun, CalculationLineItem, PricingRule
from app.core.models import Site, Unit, Tenant, RecurringCostItem
from app.sources.models import NormalizedMeasurement


def test_fixed_cost_allocation(db_session):
    """Test that fixed costs are allocated by area ratio."""
    site = Site(name="Billing Test Site", total_area_sqm=200)
    db_session.add(site)
    db_session.flush()

    unit = Unit(site_id=site.id, name="Unit 1", area_sqm=80)
    db_session.add(unit)
    db_session.flush()

    tenant = Tenant(unit_id=unit.id, name="Test Tenant")
    db_session.add(tenant)
    db_session.flush()

    cost = RecurringCostItem(
        site_id=site.id, name="Grundsteuer",
        amount_cents=10000, allocation_method="area",
    )
    db_session.add(cost)
    db_session.flush()

    from app.billing.engine import calculate_billing
    run = calculate_billing(db_session, site.id, unit.id, tenant.id, "2026-02")

    assert run is not None
    assert run.status == "draft"
    # 80/200 = 40% of 100 EUR = 40 EUR = 4000 cents
    fixed_items = [i for i in run.line_items if i.category == "fixed_cost"]
    assert len(fixed_items) == 1
    assert fixed_items[0].total_cents == 4000


def test_calculation_run_versioning(db_session):
    """Test that calculation runs store version info."""
    site = Site(name="Version Test", total_area_sqm=100)
    db_session.add(site)
    db_session.flush()

    unit = Unit(site_id=site.id, name="V-Unit", area_sqm=50)
    db_session.add(unit)
    db_session.flush()

    tenant = Tenant(unit_id=unit.id, name="V-Tenant")
    db_session.add(tenant)
    db_session.flush()

    from app.billing.engine import calculate_billing
    run = calculate_billing(db_session, site.id, unit.id, tenant.id, "2026-01")

    assert run.app_version != ""
    assert run.config_version != ""
    assert run.calculated_at is not None
