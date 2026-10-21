"""Problem extraction and (non-AI) correction generation. A future LLM generator implements CorrectionGenerator."""
from __future__ import annotations
from typing import Protocol, Optional
from dfm_engine.models import Report, Status
from dfm_engine.units import fmt_len
from .models import (AffectedFeature, ManufacturingProblem, ParameterChange, SuggestedCorrection, ValidationRequirement,
                     DesignConstraint)

# Correction.parameter (engine) -> CAD-facing parameter name
PARAM_MAP = {"flange_length": "flange_length", "flange_length (from apex)": "flange_length", "inner_bend_radius": "inner_bend_radius",
             "feature_min_dimension": "feature_min_dimension", "distance_to_edge": "feature_position",
             "distance_to_bend": "feature_position", "distance_to_bend_centerline": "feature_position",
             "sheet_thickness": "sheet_thickness", "flat_size": "flat_size", "bend_length": "bend_length"}


def problems_from_report(report: Report) -> list:
    """Actionable problems = confirmed FAILs of enabled, verified REQUIREMENT rules (never advisory/unverified)."""
    out = []
    for r in report.results:
        if r.status != Status.FAIL or r.strength != "requirement":
            continue
        ref = r.geometry_ref
        kind = ref.kind if ref else "body"
        out.append(ManufacturingProblem(
            rule_id=r.rule_id, manufacturer_id=report.manufacturer_id, status="FAIL", severity=r.severity.value,
            explanation=r.explanation, feature=AffectedFeature(kind, ref.token if ref else None, ref.label if ref else ""),
            measured_mm=r.measured if isinstance(r.measured, (int, float)) else None, required_mm=r.required_mm,
            source_url=r.source_url, strength=r.strength))
    return out


class CorrectionGenerator(Protocol):
    def generate(self, problem: ManufacturingProblem, report: Report, constraints: list) -> list: ...


class RuleBasedGenerator:
    """Deterministic generator: converts the engine's structured Corrections into SuggestedCorrections."""

    def generate(self, problem, report, constraints):
        result = next((r for r in report.results if r.rule_id == problem.rule_id and r.status == Status.FAIL
                       and (r.geometry_ref.token if r.geometry_ref else None) == problem.feature.ref_token), None)
        if result is None:
            return []
        out = []
        for c in result.corrections:
            if c.proposed_mm is None:
                continue
            target = AffectedFeature(problem.feature.kind, problem.feature.ref_token, problem.feature.label)
            changes = [ParameterChange(target, PARAM_MAP.get(c.parameter, c.parameter), c.current_mm, c.proposed_mm)]
            sc = SuggestedCorrection(
                problem.problem_id, c.summary(), c.explanation, changes, c.confidence, list(c.side_effects),
                [ValidationRequirement("reanalyze", "Re-run the manufacturability analysis after the change"),
                 ValidationRequirement("problem_resolved", f"Rule {problem.rule_id} must pass for this feature"),
                 ValidationRequirement("no_new_failures", "The change must not introduce new FAIL results"),
                 ValidationRequirement("constraints_hold", "All design constraints must still hold")])
            sc.violated_constraints = [v for con in constraints for ch in changes if (v := con.violated_by(ch))]
            out.append(sc)
        # least invasive first: smallest absolute change
        out.sort(key=lambda s: abs(s.changes[0].delta_mm or 0))
        return out
