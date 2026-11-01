"""Tests for API Setu Provider Adapter."""

import pytest
from pramana.integrations.adapters.apisetu import APISetuAdapter


def test_apisetu_land_record_simulation():
    adapter = APISetuAdapter()
    res = adapter.verify_land_record(survey_number="SN-778/B", state="Maharashtra", district="Pune")

    assert res["source"] == "API_SETU_SIMULATED_SANDBOX"
    assert res["is_simulation"] is True
    assert res["survey_number"] == "SN-778/B"
    assert res["title_status"] == "CLEAR_AND_UNENCUMBERED"
    assert res["digital_sign_valid"] is True
    assert "query_hash" in res


def test_apisetu_fire_noc_verification():
    adapter = APISetuAdapter()
    res = adapter.verify_fire_noc(noc_number="NOC-2024-9912", institution_name="Pramana Tech")

    assert res["is_simulation"] is True
    assert res["noc_number"] == "NOC-2024-9912"
    assert res["status"] == "VALID"
    assert res["fire_equipment_certified"] is True


def test_apisetu_society_registration():
    adapter = APISetuAdapter()
    res = adapter.verify_society_registration(registration_number="SOC-MAH-2010-01", state="Maharashtra")

    assert res["is_simulation"] is True
    assert res["society_name"] == "Vidya Bharti Educational Society"
    assert res["status"] == "ACTIVE"

