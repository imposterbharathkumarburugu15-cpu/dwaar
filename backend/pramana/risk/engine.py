"""Institutional Risk Intelligence Engine: Multi-Factor Risk Assessment.

Computes explainable, deterministic risk scores for educational institutions based on
historical compliance records, document replacement frequency, cross-application
linkages, temporal submission velocity, and rectification round churn.

Categorizes institutions into five transparent risk tiers (Tier A through Tier E)
with fully explainable component breakdowns and citation of contributing evidence.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..consistency.cross import cross_checks
from ..models import Application, DeficiencyLetter, Document, Finding, Institution, RectificationRequest, ValidationRun
from ..rules.engine import active_ruleset


@dataclass
class RiskFactor:
    code: str
    category: str
    weight: float
    score_contribution: float
    severity: str
    title: str
    explanation: str
    evidence_references: list[dict[str, Any]] = field(default_factory=list)


def assess_institutional_risk(db: Session, institution_id: str) -> dict[str, Any]:
    """Evaluates the multi-dimensional risk profile for an institution."""
    inst = db.get(Institution, institution_id)
    if not inst:
        raise ValueError(f"Institution {institution_id} not found")
        
    apps = list(db.scalars(
        select(Application).where(Application.institution_id == institution_id)
        .order_by(Application.created_at.desc())
    ).all())
    app_ids = [a.id for a in apps]
    
    factors: list[RiskFactor] = []
    
    # 1. Recidivism: Historical Deficiency Count & Repeat Failures
    letters_count = 0
    if app_ids:
        letters_count = db.scalar(
            select(func.count(DeficiencyLetter.id)).where(DeficiencyLetter.application_id.in_(app_ids))
        ) or 0
        
    if letters_count >= 3:
        factors.append(RiskFactor(
            code="RISK-RECIDIVISM-CHRONIC",
            category="compliance_history",
            weight=25.0,
            score_contribution=25.0,
            severity="critical",
            title="Chronic Compliance Deficiencies",
            explanation=f"Institution has received {letters_count} formal deficiency letters across approval cycles.",
            evidence_references=[{"type": "deficiency_letters_count", "count": letters_count}],
        ))
    elif letters_count >= 1:
        factors.append(RiskFactor(
            code="RISK-RECIDIVISM-REPEAT",
            category="compliance_history",
            weight=10.0,
            score_contribution=10.0 * letters_count,
            severity="medium",
            title="Past Regulatory Deficiencies Recorded",
            explanation=f"Institution has {letters_count} past deficiency letter(s) on record.",
            evidence_references=[{"type": "deficiency_letters_count", "count": letters_count}],
        ))

    # 2. Document Replacement Anomaly & Churn
    superseded_docs = 0
    total_docs = 0
    if app_ids:
        superseded_docs = db.scalar(
            select(func.count(Document.id)).where(
                Document.application_id.in_(app_ids), Document.superseded.is_(True)
            )
        ) or 0
        total_docs = db.scalar(
            select(func.count(Document.id)).where(Document.application_id.in_(app_ids))
        ) or 1
        
    churn_rate = superseded_docs / (total_docs or 1)
    if superseded_docs >= 4 or churn_rate > 0.35:
        factors.append(RiskFactor(
            code="RISK-DOC-REPLACEMENT-ANOMALY",
            category="document_integrity",
            weight=20.0,
            score_contribution=20.0,
            severity="high",
            title="Abnormal Document Replacement Frequency",
            explanation=(
                f"High rate of superseded documents: {superseded_docs} documents replaced "
                f"({churn_rate*100:.1f}% of filings), indicating unstable or manipulated submissions."
            ),
            evidence_references=[{"superseded": superseded_docs, "total": total_docs}],
        ))
    elif superseded_docs >= 2:
        factors.append(RiskFactor(
            code="RISK-DOC-REPLACEMENT-MODERATE",
            category="document_integrity",
            weight=8.0,
            score_contribution=8.0,
            severity="low",
            title="Document Revisions Observed",
            explanation=f"{superseded_docs} documents superseded across submission rounds.",
            evidence_references=[{"superseded": superseded_docs}],
        ))

    # 3. Cross-Application Entity Overlaps (Shared Faculty / Reused Credentials)
    overlap_count = 0
    overlap_links = []
    rs = active_ruleset()
    ref_fields = {t: (s.get("verification") or {}).get("ref_field") for t, s in rs.doc_types.items()
                  if (s.get("verification") or {}).get("ref_field")}
    for app in apps:
        app_docs = list(db.scalars(
            select(Document).where(Document.application_id == app.id, Document.processing_status == "processed", Document.superseded.is_(False))
        ).all())
        links = cross_checks(db, app, app_docs, ref_fields)
        if links:
            overlap_count += len(links)
            for l in links:
                overlap_links.append({
                    "application_id": app.id,
                    "code": l.code,
                    "title": l.title,
                    "other_institution": l.other_institution,
                    "other_application": l.other_application,
                })
                
    if overlap_count > 0:
        critical_links = [l for l in overlap_links if "FACULTY" in l.get("code", "") or "SEAL" in l.get("code", "")]
        score_contrib = min(35.0, 15.0 + overlap_count * 5.0)
        factors.append(RiskFactor(
            code="RISK-CROSS-INSTITUTION-OVERLAP",
            category="entity_syndication",
            weight=35.0,
            score_contribution=score_contrib,
            severity="critical" if critical_links else "high",
            title="Cross-Institutional Evidence Collusion",
            explanation=(
                f"Detected {overlap_count} overlapping entity linkage(s) with external institutions, "
                f"including shared faculty roster entries or duplicated certificates."
            ),
            evidence_references=overlap_links[:10],
        ))

    # 4. Critical & High Forensic Findings
    critical_findings_count = 0
    high_findings_count = 0
    if app_ids:
        critical_findings_count = db.scalar(
            select(func.count(Finding.id)).where(
                Finding.application_id.in_(app_ids), Finding.severity == "critical"
            )
        ) or 0
        high_findings_count = db.scalar(
            select(func.count(Finding.id)).where(
                Finding.application_id.in_(app_ids), Finding.severity == "high"
            )
        ) or 0
        
    if critical_findings_count > 0:
        factors.append(RiskFactor(
            code="RISK-CRITICAL-FINDINGS-PRESENT",
            category="forensics",
            weight=30.0,
            score_contribution=min(30.0, critical_findings_count * 15.0),
            severity="critical",
            title="Critical Forensic & Verification Violations",
            explanation=f"{critical_findings_count} critical finding(s) detected (e.g. post-signature alteration, expired statutory NOC, forged credentials).",
            evidence_references=[{"critical_count": critical_findings_count, "high_count": high_findings_count}],
        ))
    elif high_findings_count >= 3:
        factors.append(RiskFactor(
            code="RISK-HIGH-FINDINGS-CLUSTER",
            category="forensics",
            weight=15.0,
            score_contribution=15.0,
            severity="high",
            title="Cluster of High-Severity Non-Compliances",
            explanation=f"{high_findings_count} high-severity findings flagged across applications.",
            evidence_references=[{"high_count": high_findings_count}],
        ))

    # 5. Rectification Round Churn
    max_round = max((a.round for a in apps), default=1)
    if max_round >= 3:
        factors.append(RiskFactor(
            code="RISK-RECTIFICATION-CHURN",
            category="procedural_velocity",
            weight=12.0,
            score_contribution=12.0,
            severity="medium",
            title="Prolonged Rectification Rounds Required",
            explanation=f"Application progressed through {max_round} rounds without clean statutory closure.",
            evidence_references=[{"round": max_round}],
        ))

    # Calculate Total Risk Score (0 - 100)
    raw_score = sum(f.score_contribution for f in factors)
    composite_score = min(100.0, round(raw_score, 1))
    
    # Assign Risk Tier
    if composite_score <= 15.0:
        tier = "Tier A"
        tier_label = "Low Risk (Compliant)"
        recommendation = "Eligible for fast-track automated clearance."
        action_required = "Standard automated sampling."
    elif composite_score <= 35.0:
        tier = "Tier B"
        tier_label = "Moderate Risk (Standard Review)"
        recommendation = "Standard officer scrutiny of submitted documents."
        action_required = "Verify declared values against registry extracts."
    elif composite_score <= 60.0:
        tier = "Tier C"
        tier_label = "Heightened Risk (Enhanced Scrutiny)"
        recommendation = "Requires multi-tier scrutiny and issuer re-verification."
        action_required = "Mandate live re-verification of time-bound NOCs."
    elif composite_score <= 80.0:
        tier = "Tier D"
        tier_label = "High Risk (Investigation Required)"
        recommendation = "Physical inspection committee and forensic review recommended."
        action_required = "Issue formal notice and conduct Surprise Physical Inspection."
    else:
        tier = "Tier E"
        tier_label = "Critical Risk (Immediate Regulatory Action)"
        recommendation = "Immediate referral to Executive Committee; freeze approval workflow."
        action_required = "Forward complete evidence pack to Regulation Bureau Vigilance Cell."

    return {
        "institution_id": inst.id,
        "aicte_id": inst.aicte_id,
        "name": inst.name,
        "state": inst.state,
        "district": inst.district,
        "established_year": inst.established_year,
        "composite_risk_score": composite_score,
        "risk_tier": tier,
        "risk_label": tier_label,
        "recommendation": recommendation,
        "recommended_action": action_required,
        "applications_evaluated": len(apps),
        "factors_count": len(factors),
        "factors": [
            {
                "code": f.code,
                "category": f.category,
                "severity": f.severity,
                "score_contribution": f.score_contribution,
                "title": f.title,
                "explanation": f.explanation,
                "evidence": f.evidence_references,
            }
            for f in factors
        ],
        "category_scores": {
            "compliance_history": round(sum(f.score_contribution for f in factors if f.category == "compliance_history"), 1),
            "document_integrity": round(sum(f.score_contribution for f in factors if f.category == "document_integrity"), 1),
            "entity_syndication": round(sum(f.score_contribution for f in factors if f.category == "entity_syndication"), 1),
            "forensics": round(sum(f.score_contribution for f in factors if f.category == "forensics"), 1),
            "procedural_velocity": round(sum(f.score_contribution for f in factors if f.category == "procedural_velocity"), 1),
        },
        "provenance": "Synthetic Demo Risk Intelligence Engine (Deterministic)",
    }


def compute_sector_risk_observatory(db: Session) -> dict[str, Any]:
    """Generates sector-wide risk intelligence aggregates across all institutions."""
    insts = list(db.scalars(select(Institution)).all())
    
    tier_distribution = {"Tier A": 0, "Tier B": 0, "Tier C": 0, "Tier D": 0, "Tier E": 0}
    scores = []
    high_risk_list = []
    
    for inst in insts:
        try:
            profile = assess_institutional_risk(db, inst.id)
            tier = profile["risk_tier"]
            tier_distribution[tier] = tier_distribution.get(tier, 0) + 1
            scores.append(profile["composite_risk_score"])
            
            if profile["composite_risk_score"] >= 40.0:
                high_risk_list.append({
                    "institution_id": inst.id,
                    "aicte_id": inst.aicte_id,
                    "name": inst.name,
                    "state": inst.state,
                    "risk_score": profile["composite_risk_score"],
                    "risk_tier": profile["risk_tier"],
                    "top_factor": profile["factors"][0]["title"] if profile["factors"] else "General Deficiencies",
                })
        except Exception:
            continue
            
    mean_score = round(sum(scores) / (len(scores) or 1), 1)
    high_risk_list.sort(key=lambda x: x["risk_score"], reverse=True)
    
    return {
        "total_institutions": len(insts),
        "mean_sector_risk_score": mean_score,
        "tier_distribution": tier_distribution,
        "high_risk_institutions": high_risk_list[:10],
        "as_of": datetime.now(UTC).isoformat(),
        "simulated": True,
        "label": "SYNTHETIC DEMO RISK OBSERVATORY",
    }
