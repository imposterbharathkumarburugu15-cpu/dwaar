"""Regulatory Intelligence 2.0: Multi-version ruleset catalog and version diffing.

Allows regulatory officers to inspect version history, compare rule changes across
academic years (APH 2024-27, APH 2025-26, APH 2027-28 Draft), and evaluate historical
applications under the contemporaneous legal framework.
"""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..crypto import sha256_hex
from .engine import Ruleset, load_ruleset


@dataclass
class RuleDiff:
    rule_id: str
    title: str
    change_type: str  # 'added', 'removed', 'modified', 'unchanged'
    old_value: dict[str, Any] | None = None
    new_value: dict[str, Any] | None = None
    details: list[str] = field(default_factory=list)


def list_available_rulesets() -> list[dict[str, Any]]:
    """Lists all versioned rulesets available in the rulesets directory."""
    d = get_settings().rulesets_dir
    yaml_files = sorted(p for p in d.glob("*.yaml") if p.name not in ("regulatory_basis.yaml",))
    
    rulesets = []
    for p in yaml_files:
        try:
            rs = load_ruleset(p)
            rulesets.append({
                "id": rs.id,
                "title": rs.title,
                "version": rs.version,
                "sha256": rs.sha256,
                "rule_count": len(rs.rules),
                "filename": p.name,
                "path": str(p),
                "is_active": (p.name == "aicte-aph-2024-27.yaml"),
                "provenance": "AICTE Approval Process Handbook (Synthetic Demo Edition)",
            })
        except Exception:
            continue
    return rulesets


def get_ruleset_by_version(version_or_id: str) -> Ruleset:
    """Retrieves a specific ruleset by version or ID."""
    d = get_settings().rulesets_dir
    yaml_files = sorted(p for p in d.glob("*.yaml") if p.name not in ("regulatory_basis.yaml",))
    
    for p in yaml_files:
        try:
            rs = load_ruleset(p)
            if rs.id == version_or_id or rs.version == version_or_id or p.name == version_or_id:
                return rs
        except Exception:
            continue
            
    # Fallback to active ruleset
    from .engine import active_ruleset
    return active_ruleset()


def compare_rulesets(v1: str, v2: str) -> dict[str, Any]:
    """Compares two ruleset versions and produces a structured change summary."""
    rs1 = get_ruleset_by_version(v1)
    rs2 = get_ruleset_by_version(v2)
    
    rules1 = {r["id"]: r for r in rs1.rules}
    rules2 = {r["id"]: r for r in rs2.rules}
    
    diffs: list[dict[str, Any]] = []
    
    # Check removed and modified
    for rid, r1 in rules1.items():
        if rid not in rules2:
            diffs.append({
                "rule_id": rid,
                "title": r1.get("title", rid),
                "change_type": "removed",
                "details": [f"Rule {rid} was removed in {rs2.version}."],
                "old": r1,
                "new": None,
            })
        else:
            r2 = rules2[rid]
            changes = []
            if r1.get("check") != r2.get("check"):
                changes.append("Check condition expression changed.")
            if r1.get("severity") != r2.get("severity"):
                changes.append(f"Severity changed: {r1.get('severity')} -> {r2.get('severity')}.")
            if r1.get("applies_to") != r2.get("applies_to"):
                changes.append("Applicability criteria updated.")
            if r1.get("source") != r2.get("source"):
                changes.append("Statutory source clause citation modified.")
                
            if changes:
                diffs.append({
                    "rule_id": rid,
                    "title": r2.get("title", rid),
                    "change_type": "modified",
                    "details": changes,
                    "old": r1,
                    "new": r2,
                })
            else:
                diffs.append({
                    "rule_id": rid,
                    "title": r1.get("title", rid),
                    "change_type": "unchanged",
                    "details": [],
                    "old": r1,
                    "new": r2,
                })
                
    # Check added rules
    for rid, r2 in rules2.items():
        if rid not in rules1:
            diffs.append({
                "rule_id": rid,
                "title": r2.get("title", rid),
                "change_type": "added",
                "details": [f"New rule {rid} introduced in {rs2.version}."],
                "old": None,
                "new": r2,
            })
            
    # Norms comparison (FSR, bandwidth, land)
    norms_diff = {}
    all_norm_keys = set(rs1.norms.keys()) | set(rs2.norms.keys())
    for k in all_norm_keys:
        val1 = rs1.norms.get(k)
        val2 = rs2.norms.get(k)
        if val1 != val2:
            norms_diff[k] = {"version_1": val1, "version_2": val2}
            
    added_count = sum(1 for d in diffs if d["change_type"] == "added")
    removed_count = sum(1 for d in diffs if d["change_type"] == "removed")
    modified_count = sum(1 for d in diffs if d["change_type"] == "modified")
    unchanged_count = sum(1 for d in diffs if d["change_type"] == "unchanged")
    
    return {
        "ruleset_1": {"id": rs1.id, "version": rs1.version, "title": rs1.title},
        "ruleset_2": {"id": rs2.id, "version": rs2.version, "title": rs2.title},
        "summary": {
            "total_rules_v1": len(rs1.rules),
            "total_rules_v2": len(rs2.rules),
            "added": added_count,
            "removed": removed_count,
            "modified": modified_count,
            "unchanged": unchanged_count,
        },
        "norms_diff": norms_diff,
        "diffs": diffs,
    }

