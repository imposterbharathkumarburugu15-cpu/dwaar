"""Tests for Phase 9: Autonomous Regulatory Intelligence, Change Detection & Human Approval Workflow."""

import pytest
from pramana.intelligence.regulatory_monitor import (
    RegulatoryIntelligenceEngine,
    RegulatorySource,
)


def test_regulatory_source_registry():
    engine = RegulatoryIntelligenceEngine()
    sources = engine.get_sources()
    assert len(sources) >= 3

    # Add new approved gazette source
    new_src = RegulatorySource(
        id="delhi_higher_ed_gazette",
        authority="Govt of NCT Delhi",
        name="State Technical Education Gazette",
        official_url="https://delhi.gov.in/gazette",
        category="GAZETTE",
    )
    engine.register_source(new_src)
    assert len(engine.get_sources()) == len(sources) + 1


def test_regulatory_diff_detection_and_classification():
    engine = RegulatoryIntelligenceEngine()

    before = {
        "4.1": "Minimum land required for Engineering College in Urban area shall be 2.5 Acres.",
        "4.2": "Faculty to student ratio shall be 1:20.",
        "4.3": "Every institution shall maintain a physical library with 5000 books.",
    }

    after = {
        "4.1": "Minimum land required for Engineering College in Urban area shall be 3.0 Acres.",  # MODIFIED
        "4.2": "Faculty to student ratio shall be 1:15.",  # MODIFIED
        # 4.3 REPEALED
        "4.4": "Institution shall maintain high-speed digital library access with 100 Mbps.",  # ADDED
    }

    change_item = engine.detect_change(
        source_id="aicte_aph",
        instrument_title="Approval Process Handbook 2026-27 Amendments",
        clauses_before=before,
        clauses_after=after,
        effective_date="2026-04-01",
        gazette_ref="DL-(N)04/0007/2026-26",
    )

    assert change_item.status == "CHANGE_DETECTED"
    assert len(change_item.diffs) == 4

    types = {d.clause_id: d.change_type for d in change_item.diffs}
    assert types["4.1"] == "MODIFIED"
    assert types["4.2"] == "MODIFIED"
    assert types["4.3"] == "REPEALED"
    assert types["4.4"] == "ADDED"
    assert len(change_item.affected_rule_ids) > 0


def test_mandatory_human_approval_workflow():
    engine = RegulatoryIntelligenceEngine()

    item = engine.detect_change(
        source_id="aicte_aph",
        instrument_title="Test Amendment",
        clauses_before={"1.0": "Rule A"},
        clauses_after={"1.0": "Rule A Prime"},
        effective_date="2026-06-01",
    )
    assert item.status == "CHANGE_DETECTED"

    # Expert Review step
    item = engine.submit_expert_review(
        change_id=item.change_id,
        reviewer_name="Dr. S. Sharma (AICTE Bureau Advisor)",
        review_notes="Recommended for adoption; compliant with National Education Policy.",
        recommendation="APPROVE",
    )
    assert item.status == "EXPERT_REVIEW"
    assert item.expert_reviewer is not None

    # Final Administrative Approval & Rule Activation
    item = engine.admin_approve_and_activate(
        change_id=item.change_id,
        admin_name="Member Secretary, AICTE",
        new_ruleset_version="v2026.2.0",
    )
    assert item.status == "RULE_ACTIVATED"
    assert item.admin_approver == "Member Secretary, AICTE"
    assert item.created_rule_version == "v2026.2.0"

