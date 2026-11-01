"""Regulatory Intelligence 2.0: What-If Regulatory Simulation Engine.

Enables regulatory policymakers, AICTE administrators, and scrutiny officers to
simulate proposed handbook amendments (e.g. tightening FSR from 1:20 to 1:15,
increasing minimum bandwidth, or mandating green buffer zones) across institutional
applications and forecast sector-wide compliance impacts before notifications are gazetted.
"""

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Application, Document, Institution
from ..pipeline.facts_builder import build_facts
from .engine import RuleResult, active_ruleset, evaluate, load_ruleset
from .versioning import get_ruleset_by_version


@dataclass
class SimulationImpact:
    application_id: str
    institution_name: str
    aicte_id: str
    state: str
    category: str
    baseline_findings_count: int
    simulated_findings_count: int
    baseline_compliance_score: float
    simulated_compliance_score: float
    status_change: str  # 'unaffected', 'new_deficiency', 'improved'
    new_violations: list[dict[str, Any]] = field(default_factory=list)
    resolved_violations: list[dict[str, Any]] = field(default_factory=list)


def calculate_compliance_score(results: list[RuleResult]) -> float:
    """Calculates a normalized 0-100 compliance score from rule evaluation results."""
    evaluated = [r for r in results if r.outcome not in ("not_applicable", "error")]
    if not evaluated:
        return 100.0
    
    weights = {
        "critical": 25.0,
        "high": 15.0,
        "medium": 8.0,
        "low": 3.0,
        "info": 0.0,
    }
    
    total_penalty = 0.0
    for r in evaluated:
        if r.outcome == "fail":
            sev = r.rule.get("severity", "medium").lower()
            total_penalty += weights.get(sev, 10.0)
            
    # Asymptotic decay score
    score = max(0.0, 100.0 - total_penalty)
    return round(score, 1)


def run_simulation(
    db: Session,
    target_ruleset_version: str | None = None,
    parameter_overrides: dict[str, Any] | None = None,
    application_id: str | None = None,
) -> dict[str, Any]:
    """Simulates regulatory rule changes over applications in the system.
    
    Args:
        db: SQLAlchemy session
        target_ruleset_version: Version ID to evaluate against (defaults to active)
        parameter_overrides: Dict of modified norms/thresholds, e.g.
            {"norms": {"faculty_student_ratio": {"UG_ET": 15}}, "bandwidth_multiplier": 1.5}
        application_id: Optional single application filter; if omitted, runs on all apps.
    """
    overrides = parameter_overrides or {}
    
    # 1. Load baseline ruleset and simulated ruleset
    baseline_rs = active_ruleset()
    sim_rs = deepcopy(get_ruleset_by_version(target_ruleset_version)) if target_ruleset_version else deepcopy(baseline_rs)
    
    # 2. Apply parameter overrides to simulated ruleset
    if "norms" in overrides:
        for k, v in overrides["norms"].items():
            if isinstance(v, dict) and isinstance(sim_rs.norms.get(k), dict):
                sim_rs.norms[k].update(v)
            else:
                sim_rs.norms[k] = v
                
    # Threshold overrides on specific rules
    if "rule_thresholds" in overrides:
        # e.g. {"R-LAND-MIN-ACRE": 5.0}
        for r in sim_rs.rules:
            rid = r.get("id")
            if rid in overrides["rule_thresholds"]:
                # Custom injection into rule when supported
                r["simulated_threshold"] = overrides["rule_thresholds"][rid]

    # 3. Fetch applications
    q = select(Application).join(Institution)
    if application_id:
        q = q.where(Application.id == application_id)
    apps = list(db.scalars(q).all())
    
    impacts: list[dict[str, Any]] = []
    total_baseline_score = 0.0
    total_simulated_score = 0.0
    new_deficiency_count = 0
    improved_count = 0
    unaffected_count = 0
    
    as_of = date.today()
    
    for app in apps:
        docs = list(db.scalars(
            select(Document).where(Document.application_id == app.id, Document.superseded.is_(False))
        ).all())
        facts = build_facts(db, app, docs, baseline_rs)
        
        # Baseline evaluation
        base_results = evaluate(baseline_rs, facts, category=app.category, as_of=as_of)
        base_fails = {r.rule["id"]: r for r in base_results if r.outcome == "fail"}
        base_score = calculate_compliance_score(base_results)
        
        # Simulated evaluation
        sim_results = evaluate(sim_rs, facts, category=app.category, as_of=as_of)
        sim_fails = {r.rule["id"]: r for r in sim_results if r.outcome == "fail"}
        sim_score = calculate_compliance_score(sim_results)
        
        total_baseline_score += base_score
        total_simulated_score += sim_score
        
        # Compare violations
        new_vids = set(sim_fails.keys()) - set(base_fails.keys())
        resolved_vids = set(base_fails.keys()) - set(sim_fails.keys())
        
        if new_vids:
            status_change = "new_deficiency"
            new_deficiency_count += 1
        elif resolved_vids:
            status_change = "improved"
            improved_count += 1
        else:
            status_change = "unaffected"
            unaffected_count += 1
            
        impacts.append({
            "application_id": app.id,
            "institution_name": app.institution.name,
            "aicte_id": app.institution.aicte_id,
            "state": app.institution.state,
            "category": app.category,
            "baseline_findings_count": len(base_fails),
            "simulated_findings_count": len(sim_fails),
            "baseline_compliance_score": base_score,
            "simulated_compliance_score": sim_score,
            "score_delta": round(sim_score - base_score, 1),
            "status_change": status_change,
            "new_violations": [
                {
                    "rule_id": vid,
                    "title": sim_fails[vid].rule.get("title", vid),
                    "severity": sim_fails[vid].rule.get("severity", "medium"),
                    "message": sim_fails[vid].message,
                    "clause": sim_fails[vid].rule.get("source", {}).get("clause", "N/A"),
                }
                for vid in new_vids
            ],
            "resolved_violations": [
                {
                    "rule_id": vid,
                    "title": base_fails[vid].rule.get("title", vid),
                    "severity": base_fails[vid].rule.get("severity", "medium"),
                }
                for vid in resolved_vids
            ],
        })
        
    n_apps = len(apps) or 1
    mean_baseline = round(total_baseline_score / n_apps, 1)
    mean_simulated = round(total_simulated_score / n_apps, 1)
    
    return {
        "simulation_id": f"SIM-{date.today().isoformat()}-{hash(str(overrides)) & 0xFFFF:04X}",
        "as_of": as_of.isoformat(),
        "baseline_ruleset": {"id": baseline_rs.id, "version": baseline_rs.version},
        "target_ruleset": {"id": sim_rs.id, "version": sim_rs.version},
        "parameter_overrides": overrides,
        "summary": {
            "total_applications_evaluated": len(apps),
            "mean_baseline_compliance_score": mean_baseline,
            "mean_simulated_compliance_score": mean_simulated,
            "net_score_delta": round(mean_simulated - mean_baseline, 1),
            "new_deficiencies": new_deficiency_count,
            "improved_applications": improved_count,
            "unaffected_applications": unaffected_count,
            "sector_impact_severity": "high" if new_deficiency_count > len(apps) * 0.3 else "moderate" if new_deficiency_count > 0 else "low",
        },
        "applications": impacts,
    }
