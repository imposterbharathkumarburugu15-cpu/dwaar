"""Advanced Document Intelligence: Cross-Document Contradiction & Completeness Engine.

Cross-checks extracted claims across different supporting documents within an
application (and between declared portal values and submitted documents) to detect
contradictions, discrepancy discrepancies, temporal anomalies, and missing filings.
Every comparison retains full provenance (source document, page number, bounding box).
"""

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Application, Document, ExtractedField
from ..rules.engine import Ruleset, active_ruleset


@dataclass
class ContradictionItem:
    code: str
    field_name: str
    severity: str  # 'critical', 'high', 'medium', 'low'
    summary: str
    explanation: str
    doc1_id: str
    doc1_type: str
    doc1_filename: str
    doc1_value: Any
    doc1_provenance: dict[str, Any]
    doc2_id: str
    doc2_type: str
    doc2_filename: str
    doc2_value: Any
    doc2_provenance: dict[str, Any]
    discrepancy_delta: float | None = None


def _clean_str(val: Any) -> str:
    if val is None:
        return ""
    return re.sub(r"\s+", " ", str(val).strip().upper())


def _to_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        cleaned = re.sub(r"[^\d.]", "", str(val))
        return float(cleaned) if cleaned else None
    except (ValueError, TypeError):
        return None


def analyze_document_completeness(app: Application, docs: list[Document], rs: Ruleset | None = None) -> dict[str, Any]:
    """Analyzes document completeness against statutory checklist requirements."""
    rs = rs or active_ruleset()
    checklist = rs.checklists.get(app.category, {})
    required_types = checklist.get("required", [])
    optional_types = checklist.get("optional", [])
    
    uploaded_active = [d for d in docs if not d.superseded]
    uploaded_by_type: dict[str, list[Document]] = {}
    for d in uploaded_active:
        uploaded_by_type.setdefault(d.declared_type, []).append(d)
        
    required_status = []
    missing_required = []
    for doc_type in required_types:
        type_meta = rs.doc_types.get(doc_type, {})
        has_doc = doc_type in uploaded_by_type
        if not has_doc:
            missing_required.append(doc_type)
        required_status.append({
            "doc_type": doc_type,
            "label": type_meta.get("label", doc_type),
            "mandatory": True,
            "uploaded": has_doc,
            "document_id": uploaded_by_type[doc_type][0].id if has_doc else None,
            "filename": uploaded_by_type[doc_type][0].original_filename if has_doc else None,
            "fields_extracted": len(uploaded_by_type[doc_type][0].fields) if has_doc else 0,
        })
        
    optional_status = []
    for doc_type in optional_types:
        type_meta = rs.doc_types.get(doc_type, {})
        has_doc = doc_type in uploaded_by_type
        optional_status.append({
            "doc_type": doc_type,
            "label": type_meta.get("label", doc_type),
            "mandatory": False,
            "uploaded": has_doc,
            "document_id": uploaded_by_type[doc_type][0].id if has_doc else None,
            "filename": uploaded_by_type[doc_type][0].original_filename if has_doc else None,
            "fields_extracted": len(uploaded_by_type[doc_type][0].fields) if has_doc else 0,
        })
        
    total_required = len(required_types) or 1
    fulfilled_required = total_required - len(missing_required)
    completeness_score = round((fulfilled_required / total_required) * 100.0, 1)
    
    return {
        "category": app.category,
        "completeness_score": completeness_score,
        "total_required": len(required_types),
        "fulfilled_required": fulfilled_required,
        "missing_required": missing_required,
        "required_documents": required_status,
        "optional_documents": optional_status,
        "is_complete": len(missing_required) == 0,
    }


def detect_cross_document_contradictions(app: Application, docs: list[Document]) -> list[dict[str, Any]]:
    """Compares fields across all uploaded documents to discover mutually conflicting claims."""
    active_docs = [d for d in docs if not d.superseded]
    contradictions: list[dict[str, Any]] = []
    
    # Map documents to extracted fields dict
    doc_fields: dict[str, dict[str, ExtractedField]] = {}
    for d in active_docs:
        doc_fields[d.id] = {f.name: f for f in d.fields}
        
    doc_lookup = {d.id: d for d in active_docs}
    
    # 1. Compare Area figures (built-up area or land area across Affidavit 2, Land documents, Architect certs)
    area_fields = ("land_area_acres", "built_up_area_sqm", "carpet_area_sqm", "land_area", "built_up_area")
    for fld_name in area_fields:
        occurrences = []
        for d in active_docs:
            f = doc_fields[d.id].get(fld_name)
            if f and f.value:
                num = _to_float(f.value)
                if num is not None:
                    occurrences.append((d, f, num))
                    
        for i in range(len(occurrences)):
            for j in range(i + 1, len(occurrences)):
                d1, f1, v1 = occurrences[i]
                d2, f2, v2 = occurrences[j]
                # If difference exceeds 5% or 10 units, flag contradiction
                delta = abs(v1 - v2)
                max_val = max(abs(v1), abs(v2)) or 1.0
                rel_diff = delta / max_val
                if rel_diff > 0.05 and delta > 2.0:
                    contradictions.append({
                        "code": "XDOC-CONTRADICTION-AREA",
                        "field_name": fld_name,
                        "severity": "critical" if rel_diff > 0.2 else "high",
                        "title": f"Area discrepancy between {d1.declared_type} and {d2.declared_type}",
                        "explanation": (
                            f"{d1.original_filename} states {fld_name} as {v1}, whereas "
                            f"{d2.original_filename} claims {v2} (variance of {delta:.1f}, {rel_diff*100:.1f}%)."
                        ),
                        "doc1": {
                            "document_id": d1.id,
                            "doc_type": d1.declared_type,
                            "filename": d1.original_filename,
                            "value": v1,
                            "page": f1.page,
                            "bbox": f1.bbox,
                            "confidence": f1.confidence,
                        },
                        "doc2": {
                            "document_id": d2.id,
                            "doc_type": d2.declared_type,
                            "filename": d2.original_filename,
                            "value": v2,
                            "page": f2.page,
                            "bbox": f2.bbox,
                            "confidence": f2.confidence,
                        },
                        "delta": delta,
                        "percentage_variance": round(rel_diff * 100, 1),
                    })

    # 2. Compare Institution Name / Trust Name across documents
    name_fields = ("institution_name", "trust_name", "society_name", "deponent_name")
    for fld_name in name_fields:
        occurrences = []
        for d in active_docs:
            f = doc_fields[d.id].get(fld_name)
            if f and f.value:
                clean = _clean_str(f.value)
                if len(clean) > 5:
                    occurrences.append((d, f, clean))
                    
        for i in range(len(occurrences)):
            for j in range(i + 1, len(occurrences)):
                d1, f1, s1 = occurrences[i]
                d2, f2, s2 = occurrences[j]
                # Compare similarity (token set comparison or length mismatch)
                t1 = set(re.findall(r"\w+", s1))
                t2 = set(re.findall(r"\w+", s2))
                jaccard = len(t1 & t2) / (len(t1 | t2) or 1)
                if jaccard < 0.6:
                    contradictions.append({
                        "code": "XDOC-CONTRADICTION-NAME",
                        "field_name": fld_name,
                        "severity": "high",
                        "title": f"Conflicting {fld_name.replace('_', ' ').title()} in {d1.declared_type} and {d2.declared_type}",
                        "explanation": (
                            f"{d1.original_filename} states '{f1.value}', while {d2.original_filename} "
                            f"certifies '{f2.value}'. The two names differ substantially."
                        ),
                        "doc1": {
                            "document_id": d1.id,
                            "doc_type": d1.declared_type,
                            "filename": d1.original_filename,
                            "value": f1.value,
                            "page": f1.page,
                            "bbox": f1.bbox,
                            "confidence": f1.confidence,
                        },
                        "doc2": {
                            "document_id": d2.id,
                            "doc_type": d2.declared_type,
                            "filename": d2.original_filename,
                            "value": f2.value,
                            "page": f2.page,
                            "bbox": f2.bbox,
                            "confidence": f2.confidence,
                        },
                        "jaccard_similarity": round(jaccard, 2),
                    })

    # 3. Check for Anachronistic / Temporal Inversion (e.g. Sworn Date precedes Registration/Issuance date)
    date_pairs = [
        ("affidavit_2", "sworn_date", "fire_noc", "valid_upto"),
        ("affidavit_2", "sworn_date", "building_plan", "approval_date"),
    ]
    for type1, fld1, type2, fld2 in date_pairs:
        d1_list = [d for d in active_docs if d.declared_type == type1]
        d2_list = [d for d in active_docs if d.declared_type == type2]
        if d1_list and d2_list:
            d1, d2 = d1_list[0], d2_list[0]
            field1 = doc_fields[d1.id].get(fld1)
            field2 = doc_fields[d2.id].get(fld2)
            if field1 and field2 and field1.value and field2.value:
                try:
                    dt1 = date.fromisoformat(field1.value[:10])
                    dt2 = date.fromisoformat(field2.value[:10])
                    # If certificate had already expired prior to affidavit affirmation
                    if fld2 == "valid_upto" and dt2 < dt1:
                        contradictions.append({
                            "code": "XDOC-TEMPORAL-EXPIRED-AT-AFFIRMATION",
                            "field_name": "validity_timeline",
                            "severity": "critical",
                            "title": f"{type2} expired prior to {type1} affirmation",
                            "explanation": (
                                f"{d2.original_filename} expired on {dt2.isoformat()}, yet "
                                f"{d1.original_filename} was affirmed on {dt1.isoformat()} claiming compliance."
                            ),
                            "doc1": {
                                "document_id": d1.id,
                                "doc_type": d1.declared_type,
                                "filename": d1.original_filename,
                                "value": dt1.isoformat(),
                                "page": field1.page,
                                "bbox": field1.bbox,
                            },
                            "doc2": {
                                "document_id": d2.id,
                                "doc_type": d2.declared_type,
                                "filename": d2.original_filename,
                                "value": dt2.isoformat(),
                                "page": field2.page,
                                "bbox": field2.bbox,
                            },
                        })
                except (ValueError, TypeError):
                    pass

    return contradictions


def run_cross_document_intelligence(db: Session, app_id: str) -> dict[str, Any]:
    """Top-level execution endpoint for cross-document intelligence on an application."""
    app = db.get(Application, app_id)
    if not app:
        raise ValueError(f"Application {app_id} not found")
        
    docs = list(db.scalars(
        select(Document).where(Document.application_id == app_id).order_by(Document.uploaded_at)
    ).all())
    
    completeness = analyze_document_completeness(app, docs)
    contradictions = detect_cross_document_contradictions(app, docs)
    
    return {
        "application_id": app.id,
        "category": app.category,
        "academic_year": app.academic_year,
        "completeness": completeness,
        "contradictions_count": len(contradictions),
        "contradictions": contradictions,
        "has_critical_contradiction": any(c.get("severity") == "critical" for c in contradictions),
        "summary": (
            f"Completeness is {completeness['completeness_score']}%. "
            f"Identified {len(contradictions)} cross-document discrepancies across {len(docs)} documents."
        ),
    }

