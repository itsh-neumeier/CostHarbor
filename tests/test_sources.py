"""Tests for source models."""

from app.core.models import Site
from app.sources.models import SourceConnection, EntityMapping


def test_source_connection_creation(db_session):
    site = Site(name="Source Test Site", total_area_sqm=100)
    db_session.add(site)
    db_session.flush()

    source = SourceConnection(
        site_id=site.id, name="HA Connection",
        source_type="homeassistant",
        connection_config_json={"base_url": "http://localhost:8123", "token": "test"},
    )
    db_session.add(source)
    db_session.flush()

    assert source.id is not None
    assert source.source_type == "homeassistant"
    assert source.connection_config_json["base_url"] == "http://localhost:8123"


def test_vrm_imap_ssrf_protection():
    """Test that SSRF protection blocks untrusted domains."""
    from app.sources.adapters.vrm_imap import ALLOWED_DOWNLOAD_DOMAINS

    assert "vrm-uploads.s3.eu-central-1.amazonaws.com" in ALLOWED_DOWNLOAD_DOMAINS
    assert "evil.com" not in ALLOWED_DOWNLOAD_DOMAINS
