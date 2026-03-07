"""Tests for core models."""

from app.core.models import Site, Tenant, Unit


def test_site_creation(db_session):
    site = Site(name="Test Site", address="123 Main St", city="Berlin", postal_code="10115", total_area_sqm=200)
    db_session.add(site)
    db_session.flush()
    assert site.id is not None
    assert site.name == "Test Site"
    assert site.config_version == 1


def test_unit_creation(db_session):
    site = Site(name="Site for Unit", total_area_sqm=100)
    db_session.add(site)
    db_session.flush()

    unit = Unit(site_id=site.id, name="Unit A", area_sqm=50)
    db_session.add(unit)
    db_session.flush()
    assert unit.id is not None
    assert unit.site_id == site.id


def test_tenant_creation(db_session):
    site = Site(name="Site for Tenant", total_area_sqm=100)
    db_session.add(site)
    db_session.flush()

    unit = Unit(site_id=site.id, name="Unit B", area_sqm=50)
    db_session.add(unit)
    db_session.flush()

    tenant = Tenant(unit_id=unit.id, name="Max Mustermann", email="max@example.com")
    db_session.add(tenant)
    db_session.flush()
    assert tenant.id is not None
    assert tenant.is_active is True
