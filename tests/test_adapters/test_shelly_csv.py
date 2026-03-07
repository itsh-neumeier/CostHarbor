"""Tests for Shelly CSV parser."""

from app.sources.adapters.shelly_csv import _aggregate_hourly, _parse_shelly_csv


def test_parse_empty_csv():
    df = _parse_shelly_csv("")
    assert df.empty


def test_parse_basic_csv():
    csv_data = """timestamp,a_act_energy,b_act_energy,c_act_energy,a_act_ret_energy
1709251200,1000,2000,3000,50
1709251260,1100,2100,3100,50
1709251320,1200,2200,3200,50
"""
    df = _parse_shelly_csv(csv_data)
    assert not df.empty
    assert "timestamp" in df.columns
    assert "total_active_energy" in df.columns
    assert len(df) == 3
    # Total should be sum of phases: 1000+2000+3000=6000 for first row
    assert df.iloc[0]["total_active_energy"] == 6000


def test_aggregate_hourly():
    csv_data = """timestamp,a_act_energy,b_act_energy,c_act_energy
1709251200,1000,0,0
1709251260,1100,0,0
1709254800,2000,0,0
1709254860,2200,0,0
"""
    df = _parse_shelly_csv(csv_data)
    hourly = _aggregate_hourly(df)
    assert not hourly.empty
    # Should have entries grouped by hour
    assert "total_active_kwh" in hourly.columns


def test_parse_csv_with_header_variations():
    csv_data = """ts,pha,phb,phc
1709251200,1000,2000,3000
"""
    # Should handle non-standard column names gracefully
    df = _parse_shelly_csv(csv_data)
    assert not df.empty
