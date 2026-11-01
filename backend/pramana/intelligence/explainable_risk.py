"""Explainable Multi-Dimensional Risk Intelligence Engine.

Implements Module 7.3 of Phase 7:
- Decomposes institutional application risk into 6 orthogonal dimensions.
- Produces overall 0-100 risk score and categorical classification (LOW, MODERATE, ELEVATED, HIGH, CRITICAL).
- Delivers itemized contributing factors with direct links to supporting evidence.
- Preserves absolute human decision authority (decision-support only, never auto-rejects).
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class RiskDimension:
    name: str
    score: float  # 0.0 (safest) to 100.0 (highest risk)
    weight: float
    description: str
    contributing_factors: list[str] = field(default_factory=list)


@dataclass
class ExplainableRiskReport:
    application_id: str
    overall_risk_score: float
    risk_category: str  # LOW, MODERATE, ELEVATED, HIGH, CRITICAL
    confidence: float
    dimensions: dict[str, RiskDimension]
    key_contributing_factors: list[dict[str, Any]]
    supporting_evidence: list[str]
    human_review_recommendation: str
    disclaimer: str = (
        "AI risk intelligence is an assistive decision-support aid only. "
        "Regulatory decisions must be made exclusively by authorized regulatory officers."
    )
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class ExplainableRiskEngine:
    """Calculates granular, transparent, and explainable multi-dimensional risk scores."""

    DIMENSION_WEIGHTS = {
        "document_authenticity": 0.25,
        "institutional_identity": 0.15,
        "regulatory_compliance": 0.25,
        "data_consistency": 0.15,
        "historical_evidence": 0.10,
        "external_verification": 0.10,
    }

    def assess_application_risk(
        self,
        application_id: str,
        document_authenticity_findings: list[dict[str, Any]] | None = None,
        compliance_findings: list[dict[str, Any]] | None = None,
        cross_document_findings: list[Any] | None = None,
        external_verification_results: list[dict[str, Any]] | None = None,
        historical_infractions: int = 0,
    ) -> ExplainableRiskReport:
        doc_findings = document_authenticity_findings or []
        comp_findings = compliance_findings or []
        xdoc_findings = cross_document_findings or []
        ext_results = external_verification_results or []

        # 1. Document Authenticity Risk (0 - 100)
        doc_score = 0.0
        doc_factors = []
        for df in doc_findings:
            if df.get("is_tampered"):
                doc_score += 85.0
                doc_factors.append(f"Cryptographic hash or signature tampering detected in {df.get('doc_id')}")
            if df.get("reused_image"):
                doc_score += 50.0
                doc_factors.append(f"Image perceptual hash match indicating duplicate/reused photo in {df.get('doc_id')}")
        doc_score = min(100.0, doc_score)

        # 2. Institutional Identity Risk (0 - 100)
        ident_score = 0.0
        ident_factors = []
        for xf in xdoc_findings:
            cat = getattr(xf, "category", "") or (xf.get("category") if isinstance(xf, dict) else "")
            if cat == "NAME_MISMATCH":
                ident_score += 65.0
                ident_factors.append("Institutional/Society legal name divergence between application and trust deed")
        ident_score = min(100.0, ident_score)

        # 3. Regulatory Compliance Risk (0 - 100)
        comp_score = 0.0
        comp_factors = []
        for cf in comp_findings:
            sev = cf.get("severity", "medium").lower()
            if sev == "critical":
                comp_score += 75.0
                comp_factors.append(f"Critical compliance breach: {cf.get('title', 'Mandatory rule failed')}")
            elif sev == "high":
                comp_score += 40.0
                comp_factors.append(f"High-severity compliance deficiency: {cf.get('title')}")
            elif sev == "medium":
                comp_score += 20.0
        comp_score = min(100.0, comp_score)

        # 4. Data Consistency Risk (0 - 100)
        consist_score = 0.0
        consist_factors = []
        for xf in xdoc_findings:
            cat = getattr(xf, "category", "") or (xf.get("category") if isinstance(xf, dict) else "")
            sev = getattr(xf, "severity", "") or (xf.get("severity") if isinstance(xf, dict) else "")
            if cat in ("ADDRESS_MISMATCH", "CHRONOLOGICAL_ANOMALY"):
                val = 80.0 if sev == "CRITICAL" else 45.0
                consist_score += val
                expl = getattr(xf, "explanation", "") or (xf.get("explanation") if isinstance(xf, dict) else "")
                consist_factors.append(expl)
        consist_score = min(100.0, consist_score)

        # 5. Historical Evidence Risk (0 - 100)
        hist_score = min(100.0, historical_infractions * 25.0)
        hist_factors = [f"{historical_infractions} prior regulatory infractions on record"] if historical_infractions else []

        # 6. External Verification Risk (0 - 100)
        ext_score = 0.0
        ext_factors = []
        for er in ext_results:
            verdict = er.get("verdict", "")
            if verdict == "DOCUMENT_MISMATCH":
                ext_score += 50.0
                ext_factors.append(f"Official government registry returned mismatch for {er.get('provider_id')}")
            elif verdict == "SIGNATURE_INVALID":
                ext_score += 60.0
                ext_factors.append(f"Digital signature on government document failed verification")
        ext_score = min(100.0, ext_score)

        # Assemble Dimensions
        dimensions = {
            "document_authenticity": RiskDimension(
                name="Document Authenticity",
                score=round(doc_score, 1),
                weight=self.DIMENSION_WEIGHTS["document_authenticity"],
                description="Forensic integrity, signature validity, and image originality",
                contributing_factors=doc_factors,
            ),
            "institutional_identity": RiskDimension(
                name="Institutional Identity",
                score=round(ident_score, 1),
                weight=self.DIMENSION_WEIGHTS["institutional_identity"],
                description="Entity legal registration, society trust alignment, and promoter verification",
                contributing_factors=ident_factors,
            ),
            "regulatory_compliance": RiskDimension(
                name="Regulatory Compliance",
                score=round(comp_score, 1),
                weight=self.DIMENSION_WEIGHTS["regulatory_compliance"],
                description="Fulfillment of AICTE norms (land area, built-up space, cadre ratio, labs)",
                contributing_factors=comp_factors,
            ),
            "data_consistency": RiskDimension(
                name="Data Consistency",
                score=round(consist_score, 1),
                weight=self.DIMENSION_WEIGHTS["data_consistency"],
                description="Cross-document agreement across affidavits, NOCs, and municipal records",
                contributing_factors=consist_factors,
            ),
            "historical_evidence": RiskDimension(
                name="Historical Evidence",
                score=round(hist_score, 1),
                weight=self.DIMENSION_WEIGHTS["historical_evidence"],
                description="Past institutional inspection findings, show-cause notices, and compliance track record",
                contributing_factors=hist_factors,
            ),
            "external_verification": RiskDimension(
                name="External Verification",
                score=round(ext_score, 1),
                weight=self.DIMENSION_WEIGHTS["external_verification"],
                description="Direct authoritative API validation from API Setu, DigiLocker, and state portals",
                contributing_factors=ext_factors,
            ),
        }

        # Weighted aggregate score
        overall = sum(dim.score * dim.weight for dim in dimensions.values())
        overall = round(max(0.0, min(100.0, overall)), 1)

        # Category mapping
        if overall <= 25.0:
            category = "LOW"
            action = "Application exhibits high documentary integrity. Standard expedited verification recommended."
        elif overall <= 50.0:
            category = "MODERATE"
            action = "Minor factual variations detected. Standard desk scrutiny with clarification request recommended."
        elif overall <= 70.0:
            category = "ELEVATED"
            action = "Substantial discrepancies identified. Mandatory cross-document verification and officer audit required."
        elif overall <= 85.0:
            category = "HIGH"
            action = "Severe compliance or authenticity concerns. In-person regulatory field inspection strongly recommended."
        else:
            category = "CRITICAL"
            action = "Evidence of document tampering or major conflicting legal claims. Escalate immediately to Scrutiny Committee."

        # Compile top contributing factors
        all_factors = []
        for dim_key, dim in dimensions.items():
            for factor in dim.contributing_factors:
                all_factors.append({
                    "dimension": dim.name,
                    "dimension_score": dim.score,
                    "factor": factor,
                })

        # Supporting evidence references
        evidence_refs = []
        for df in doc_findings:
            if df.get("doc_id"):
                evidence_refs.append(str(df["doc_id"]))
        for xf in xdoc_findings:
            docs = getattr(xf, "source_documents", []) or (xf.get("source_documents", []) if isinstance(xf, dict) else [])
            evidence_refs.extend(docs)

        return ExplainableRiskReport(
            application_id=application_id,
            overall_risk_score=overall,
            risk_category=category,
            confidence=0.94,
            dimensions=dimensions,
            key_contributing_factors=all_factors,
            supporting_evidence=list(dict.fromkeys(evidence_refs)),
            human_review_recommendation=action,
        )


default_risk_engine = ExplainableRiskEngine()
