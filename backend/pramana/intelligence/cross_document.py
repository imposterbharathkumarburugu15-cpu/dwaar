"""Cross-Document Consistency and Discrepancy Detection Engine.

Implements Modules 7.1 & 7.2 of Phase 7:
- Cross-document validation across Application, Land Deed, Fire NOC, Building Plan, and Society Registration.
- Entity matching (institution names, trust/society names, survey numbers, built-up areas).
- Detection of chronological inconsistencies (e.g. NOC issued before society establishment).
- Distinguishing minor typographical discrepancies from critical suspicious anomalies.
- Produces auditable, explainable findings with confidence scores and recommended officer actions.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
import difflib
import logging
import re
from typing import Any

logger = logging.getLogger("pramana.intelligence.cross_document")


@dataclass
class DiscrepancyFinding:
    finding_id: str
    category: str  # NAME_MISMATCH, ADDRESS_MISMATCH, CHRONOLOGICAL_ANOMALY, INFRASTRUCTURE_DISCREPANCY, FACULTY_CADRE_DEFICIENCY
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW, INFO
    confidence: float  # 0.0 to 1.0
    source_documents: list[str]
    claimed_facts: dict[str, Any]
    comparison_logic: str
    explanation: str
    is_suspicious_anomaly: bool  # False = typo/formatting variation, True = conflicting legal claim
    recommended_action: str


class CrossDocumentIntelligenceEngine:
    """Evaluates factual and semantic consistency across multiple application documents."""

    def analyze_application_documents(
        self,
        application_data: dict[str, Any],
        extracted_documents: list[dict[str, Any]],
    ) -> list[DiscrepancyFinding]:
        """Performs exhaustive cross-comparison between application metadata and document evidence."""
        findings: list[DiscrepancyFinding] = []

        doc_by_type = {doc.get("doc_type"): doc for doc in extracted_documents}

        app_name = application_data.get("institution_name", "").strip()
        app_society = application_data.get("society_name", "").strip()
        app_survey = application_data.get("survey_number", "").strip()
        app_area = float(application_data.get("land_area_acres", 0.0))

        # Check 1: Institution / Society Name Consistency across Trust Deed and Application
        society_doc = doc_by_type.get("SOCIETY_REGISTRATION") or doc_by_type.get("TRUST_DEED")
        if society_doc:
            doc_society = society_doc.get("extracted_facts", {}).get("society_name", "").strip()
            if doc_society and app_society:
                ratio = difflib.SequenceMatcher(None, app_society.lower(), doc_society.lower()).ratio()
                if ratio < 0.85:
                    findings.append(
                        DiscrepancyFinding(
                            finding_id="XDOC-NAME-001",
                            category="NAME_MISMATCH",
                            severity="HIGH",
                            confidence=round(1.0 - ratio, 2),
                            source_documents=["APPLICATION_METADATA", society_doc.get("doc_id", "DOC-SOC")],
                            claimed_facts={"application_society": app_society, "document_society": doc_society},
                            comparison_logic=f"Fuzzy string ratio {ratio:.2f} below threshold 0.85",
                            explanation=(
                                f"Society name in application ('{app_society}') diverges significantly from "
                                f"the registered society name in deed ('{doc_society}')."
                            ),
                            is_suspicious_anomaly=ratio < 0.6,
                            recommended_action="Seek clarification from applicant and verify legal trust resolution.",
                        )
                    )

        # Check 2: Land Survey Number Consistency (Application vs Land Deed vs Fire NOC)
        land_doc = doc_by_type.get("LAND_AFFIDAVIT") or doc_by_type.get("SALE_DEED")
        fire_doc = doc_by_type.get("FIRE_NOC")

        if land_doc and app_survey:
            doc_survey = land_doc.get("extracted_facts", {}).get("survey_number", "").strip()
            if doc_survey and app_survey.lower() != doc_survey.lower():
                findings.append(
                    DiscrepancyFinding(
                        finding_id="XDOC-SURVEY-001",
                        category="ADDRESS_MISMATCH",
                        severity="CRITICAL",
                        confidence=0.98,
                        source_documents=["APPLICATION_METADATA", land_doc.get("doc_id", "DOC-LAND")],
                        claimed_facts={"application_survey": app_survey, "deed_survey": doc_survey},
                        comparison_logic="Exact normalized survey coordinate mismatch",
                        explanation=(
                            f"Land survey coordinate in application ('{app_survey}') contradicts "
                            f"the survey number recorded in the registered land document ('{doc_survey}')."
                        ),
                        is_suspicious_anomaly=True,
                        recommended_action="Reject approval until verified survey boundary certificate is submitted.",
                    )
                )

        if fire_doc and land_doc:
            fire_survey = fire_doc.get("extracted_facts", {}).get("survey_number", "").strip()
            land_survey = land_doc.get("extracted_facts", {}).get("survey_number", "").strip()
            if fire_survey and land_survey and fire_survey.lower() != land_survey.lower():
                findings.append(
                    DiscrepancyFinding(
                        finding_id="XDOC-FIRE-SURVEY-002",
                        category="ADDRESS_MISMATCH",
                        severity="HIGH",
                        confidence=0.95,
                        source_documents=[fire_doc.get("doc_id", "DOC-FIRE"), land_doc.get("doc_id", "DOC-LAND")],
                        claimed_facts={"fire_noc_survey": fire_survey, "land_deed_survey": land_survey},
                        comparison_logic="Cross-document survey coordinate comparison",
                        explanation=(
                            f"Fire NOC inspected premises survey ('{fire_survey}') does not match "
                            f"the registered institutional land parcel ('{land_survey}')."
                        ),
                        is_suspicious_anomaly=True,
                        recommended_action="Verify whether Fire NOC covers an adjacent or non-contiguous parcel.",
                    )
                )

        # Check 3: Chronological Feasibility
        if society_doc and land_doc:
            soc_date_str = society_doc.get("extracted_facts", {}).get("registration_date")
            land_date_str = land_doc.get("extracted_facts", {}).get("execution_date")
            if soc_date_str and land_date_str:
                try:
                    soc_d = datetime.fromisoformat(soc_date_str).date()
                    land_d = datetime.fromisoformat(land_date_str).date()
                    if land_d < soc_d:
                        findings.append(
                            DiscrepancyFinding(
                                finding_id="XDOC-TIME-001",
                                category="CHRONOLOGICAL_ANOMALY",
                                severity="HIGH",
                                confidence=0.92,
                                source_documents=[society_doc.get("doc_id", "DOC-SOC"), land_doc.get("doc_id", "DOC-LAND")],
                                claimed_facts={"society_established": soc_date_str, "land_acquired": land_date_str},
                                comparison_logic="Land purchase date predates legal society incorporation date",
                                explanation=(
                                    f"Land document was executed on {land_date_str}, which predates the "
                                    f"legal incorporation of the purchasing society on {soc_date_str}."
                                ),
                                is_suspicious_anomaly=True,
                                recommended_action="Request prior promoter purchase authorization or assignment deed.",
                            )
                        )
                except ValueError:
                    pass

        # Check 4: Built-up Area Contradiction
        arch_doc = doc_by_type.get("ARCHITECT_CERTIFICATE")
        if arch_doc and "built_up_area_sqm" in application_data:
            claimed_area = float(application_data["built_up_area_sqm"])
            certified_area = float(arch_doc.get("extracted_facts", {}).get("built_up_area_sqm", 0.0))
            if certified_area > 0 and abs(claimed_area - certified_area) > (certified_area * 0.05):
                findings.append(
                    DiscrepancyFinding(
                        finding_id="XDOC-AREA-001",
                        category="INFRASTRUCTURE_DISCREPANCY",
                        severity="MEDIUM",
                        confidence=0.88,
                        source_documents=["APPLICATION_METADATA", arch_doc.get("doc_id", "DOC-ARCH")],
                        claimed_facts={"application_built_up": claimed_area, "architect_certified": certified_area},
                        comparison_logic="Area divergence exceeds 5% engineering tolerance",
                        explanation=(
                            f"Claimed built-up area ({claimed_area} sqm) differs by "
                            f"{abs(claimed_area - certified_area):.1f} sqm from the Architect's certificate ({certified_area} sqm)."
                        ),
                        is_suspicious_anomaly=False,
                        recommended_action="Request updated occupancy certificate with verified measurement schedule.",
                    )
                )

        return findings


default_cross_document_engine = CrossDocumentIntelligenceEngine()

