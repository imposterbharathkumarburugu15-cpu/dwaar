"""Tests for Phase 7: Advanced AI Intelligence & Explainable Regulatory Reasoning."""

import pytest
from pramana.intelligence.cross_document import CrossDocumentIntelligenceEngine
from pramana.intelligence.explainable_risk import ExplainableRiskEngine
from pramana.intelligence.regulatory_rag import RegulatoryRAGEngine
from pramana.rules.simulator import calculate_compliance_score, RuleResult


def test_cross_document_society_name_mismatch():
    engine = CrossDocumentIntelligenceEngine()
    app_data = {
        "institution_name": "Pramana Institute of Technology",
        "society_name": "Vidya Bharti Trust",
        "survey_number": "SN-402/A",
        "land_area_acres": 5.2,
    }
    extracted_docs = [
        {
            "doc_id": "DOC-SOC-01",
            "doc_type": "SOCIETY_REGISTRATION",
            "extracted_facts": {
                "society_name": "Completely Different Charitable Foundation",
                "registration_date": "2015-01-01",
            },
        }
    ]

    findings = engine.analyze_application_documents(app_data, extracted_docs)
    assert len(findings) >= 1
    f = next(x for x in findings if x.category == "NAME_MISMATCH")
    assert f.severity == "HIGH"
    assert f.is_suspicious_anomaly is True
    assert "DOC-SOC-01" in f.source_documents


def test_cross_document_conflicting_survey_numbers():
    engine = CrossDocumentIntelligenceEngine()
    app_data = {
        "institution_name": "Pramana Tech",
        "society_name": "Vidya Society",
        "survey_number": "SN-100/A",
    }
    extracted_docs = [
        {
            "doc_id": "DOC-LAND-01",
            "doc_type": "LAND_AFFIDAVIT",
            "extracted_facts": {"survey_number": "SN-999/Z"},  # Contradicts SN-100/A
        }
    ]

    findings = engine.analyze_application_documents(app_data, extracted_docs)
    survey_f = next(x for x in findings if x.category == "ADDRESS_MISMATCH")
    assert survey_f.severity == "CRITICAL"
    assert survey_f.is_suspicious_anomaly is True
    assert "SN-100/A" in str(survey_f.claimed_facts)
    assert "SN-999/Z" in str(survey_f.claimed_facts)


def test_explainable_risk_dimensions_and_human_authority():
    risk_engine = ExplainableRiskEngine()

    # Scenario: Clean application
    clean_report = risk_engine.assess_application_risk(
        application_id="APP-CLEAN-01",
        document_authenticity_findings=[],
        compliance_findings=[],
        cross_document_findings=[],
    )
    assert clean_report.overall_risk_score <= 25.0
    assert clean_report.risk_category == "LOW"
    assert len(clean_report.dimensions) == 6
    assert "decision-support" in clean_report.disclaimer.lower()

    # Scenario: Compromised application with tampering & mismatch
    bad_report = risk_engine.assess_application_risk(
        application_id="APP-RISKY-01",
        document_authenticity_findings=[{"doc_id": "DOC-1", "is_tampered": True}],
        compliance_findings=[{"title": "Fire NOC Missing", "severity": "critical"}],
        cross_document_findings=[{"category": "ADDRESS_MISMATCH", "severity": "CRITICAL", "source_documents": ["DOC-1"]}],
        historical_infractions=2,
    )
    assert bad_report.overall_risk_score > 50.0
    assert bad_report.risk_category in ("ELEVATED", "HIGH", "CRITICAL")
    assert len(bad_report.key_contributing_factors) >= 3
    assert "DOC-1" in bad_report.supporting_evidence


def test_regulatory_rag_grounded_citations():
    rag = RegulatoryRAGEngine()

    # Query matching indexed terms in regulatory basis
    res = rag.query_regulations("land requirements for engineering college")
    if res.status == "ANSWERED":
        assert len(res.citations) >= 1
        assert res.citations[0].verified is True
        assert res.citations[0].clause is not None
        assert res.confidence > 0.8
        assert res.hallucination_guarded is True


def test_regulatory_rag_hallucination_prevention_on_unsupported_claim():
    rag = RegulatoryRAGEngine()

    # Query with completely fabricated non-existent requirements
    res = rag.query_regulations("mandate for quantum computer teleportation in high school cafeterias")
    assert res.status == "INSUFFICIENT_REGULATORY_EVIDENCE"
    assert res.provisions_found == 0
    assert len(res.citations) == 0
    assert "PRAMANA will not invent" in res.summary


def test_what_if_compliance_score_calculation():
    # Test scoring with clean results
    r_pass = RuleResult(rule={"id": "R1", "severity": "critical"}, outcome="pass", message="Passes norm")
    score_clean = calculate_compliance_score([r_pass])
    assert score_clean == 100.0

    # Test scoring with critical failure
    r_fail = RuleResult(rule={"id": "R2", "severity": "critical"}, outcome="fail", message="Fails norm")
    score_fail = calculate_compliance_score([r_fail])
    assert score_fail < score_clean
    assert score_fail == 75.0  # 100 - 25
