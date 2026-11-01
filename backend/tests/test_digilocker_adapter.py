"""Tests for DigiLocker / NAD Provider Adapter."""

import pytest
from pramana.integrations.adapters.digilocker import DigiLockerAdapter


def test_parse_valid_digilocker_uri():
    adapter = DigiLockerAdapter()
    parsed = adapter.parse_digilocker_uri("in.gov.aicte-LOA-2025-001234")

    assert parsed["issuer"] == "in.gov.aicte"
    assert parsed["doc_type"] == "LOA"
    assert parsed["document_id"] == "2025-001234"


def test_parse_invalid_digilocker_uri():
    adapter = DigiLockerAdapter()
    with pytest.raises(ValueError):
        adapter.parse_digilocker_uri("invalid_uri_string")


def test_pull_issued_document_sandbox():
    adapter = DigiLockerAdapter()
    res = adapter.pull_issued_document("in.gov.aicte-LOA-2025-001234")

    assert res["source"] == "DIGILOCKER_SIMULATED_SANDBOX"
    assert res["is_simulation"] is True
    assert res["signature_valid"] is True
    assert "xml_payload" in res

    # Verify XML payload structure
    sig_check = adapter.verify_xml_signature(res["xml_payload"])
    assert sig_check["valid"] is True
    assert sig_check["signature_type"] == "XML_DSIG_SHA256"

