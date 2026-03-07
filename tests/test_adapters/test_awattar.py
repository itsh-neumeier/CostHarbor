"""Tests for aWATTar adapter."""


def test_awattar_url_selection():
    """Test that correct URL is selected by country code."""
    from app.sources.adapters.awattar import AWATTAR_URLS

    assert "de" in AWATTAR_URLS
    assert "at" in AWATTAR_URLS
    assert "api.awattar.de" in AWATTAR_URLS["de"]
    assert "api.awattar.at" in AWATTAR_URLS["at"]
