"""Multi-manufacturer comparison. Never returns an unconditional verdict when information is missing."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from .engine import evaluate, CATEGORY_LABEL
from .models import PartModel, Report, Status

COMPATIBLE = "COMPATIBLE"
CONDITIONAL = "CONDITIONALLY_COMPATIBLE"
NEEDS_REVIEW = "NEEDS_REVIEW"
INCOMPATIBLE = "INCOMPATIBLE"
_ORDER = {COMPATIBLE: 0, CONDITIONAL: 1, NEEDS_REVIEW: 2, INCOMPATIBLE: 3}
VERDICT_TEXT = {
    COMPATIBLE: "All required checks ran and passed.",
    CONDITIONAL: "No failures, but some requirement categories have no verified data, so full compatibility is not confirmed.",
    NEEDS_REVIEW: "Some checks could not be resolved; compatibility cannot be confirmed or ruled out.",
    INCOMPATIBLE: "At least one verified requirement is not met.",
}


@dataclass
class Target:
    manufacturer_id: str
    process_id: Optional[str] = None     # default: first process in the profile
    material_id: Optional[str] = None    # default: auto-detect from the part's material


@dataclass
class ManufacturerVerdict:
    manufacturer_id: str
    manufacturer_name: str
    process_id: str
    verdict: str
    failures: int
    unresolved: int
    passed: int
    not_checked: int
    coverage_gaps: list
    reasons: list                  # confirmed failures: dicts
    unresolved_items: list         # dicts
    corrections: list              # Correction dicts for the failures
    reports: list                  # Report per part
    demo: bool = False
    profile_status: str = ""
    summary: str = ""
    research_status: str = ""
    research_notes: str = ""

    def to_dict(self):
        return {"manufacturer_id": self.manufacturer_id, "manufacturer_name": self.manufacturer_name,
                "process_id": self.process_id, "verdict": self.verdict, "verdict_text": VERDICT_TEXT[self.verdict],
                "failures": self.failures, "unresolved": self.unresolved, "passed": self.passed,
                "not_checked": self.not_checked, "coverage_gaps": self.coverage_gaps,
                "coverage_gap_labels": [CATEGORY_LABEL.get(c, c) for c in self.coverage_gaps],
                "reasons": self.reasons, "unresolved_items": self.unresolved_items, "corrections": self.corrections,
                "reports": [r.to_dict() for r in self.reports], "demo": self.demo,
                "profile_status": self.profile_status, "summary": self.summary,
                "research_status": self.research_status, "research_notes": self.research_notes}


@dataclass
class Comparison:
    part_names: list
    entries: list = field(default_factory=list)

    def ranked(self, include_demo=False):
        es = [e for e in self.entries if include_demo or not e.demo]
        return sorted(es, key=lambda e: (_ORDER[e.verdict], e.failures, e.unresolved))

    def to_dict(self):
        return {"parts": self.part_names, "entries": [e.to_dict() for e in self.ranked(include_demo=True)]}


def _verdict(reports, demo):
    fails = sum(r.counts()["FAIL"] for r in reports)
    unresolved = sum(r.counts()["NEEDS_REVIEW"] for r in reports)
    passed = sum(r.counts()["PASS"] for r in reports)
    gaps = sorted({g for r in reports for g in r.coverage_gaps})
    if fails:
        return INCOMPATIBLE, ""
    if unresolved:
        return NEEDS_REVIEW, ""
    if not passed:
        return NEEDS_REVIEW, "No verified check could be performed (no verified rules apply)."
    if gaps:
        return CONDITIONAL, ""
    return COMPATIBLE, ""


def compare(parts, profiles: list, targets: Optional[list] = None) -> Comparison:
    """parts: PartModel or list of PartModel. targets: optional Target list (default: every profile, first process)."""
    parts = [parts] if isinstance(parts, PartModel) else list(parts)
    by_id = {p["manufacturer"]["id"]: p for p in profiles}
    targets = targets or [Target(p["manufacturer"]["id"]) for p in profiles]
    comp = Comparison([p.name for p in parts])
    for t in targets:
        prof = by_id.get(t.manufacturer_id)
        if prof is None:
            raise KeyError(f"unknown manufacturer {t.manufacturer_id!r}")
        pid = t.process_id or prof["processes"][0]["id"]
        reports = [evaluate(p, prof, pid, t.material_id) for p in parts]
        demo = prof["profile_status"] == "demo"
        verdict, extra = _verdict(reports, demo)
        reasons, unresolved_items, corrections = [], [], []
        for part, rep in zip(parts, reports):
            for r in rep.results:
                item = {"part": part.name, "rule_id": r.rule_id, "explanation": r.explanation,
                        "recommendation": r.recommendation, "token": r.geometry_ref.token if r.geometry_ref else None,
                        "source_url": r.source_url, "strength": r.strength}
                if r.status == Status.FAIL:
                    reasons.append(item)
                    corrections += [dict(c.to_dict(), part=part.name) for c in r.corrections]
                elif r.status == Status.NEEDS_REVIEW:
                    unresolved_items.append(item)
        counts = [r.counts() for r in reports]
        entry = ManufacturerVerdict(
            manufacturer_id=t.manufacturer_id, manufacturer_name=prof["manufacturer"]["name"], process_id=pid,
            verdict=verdict, failures=sum(c["FAIL"] for c in counts), unresolved=sum(c["NEEDS_REVIEW"] for c in counts),
            passed=sum(c["PASS"] for c in counts), not_checked=sum(c["SKIPPED"] for c in counts),
            coverage_gaps=sorted({g for r in reports for g in r.coverage_gaps}), reasons=reasons,
            unresolved_items=unresolved_items, corrections=corrections, reports=reports, demo=demo,
            profile_status=prof["profile_status"], summary=extra or VERDICT_TEXT[verdict],
            research_status=(prof.get("research") or {}).get("status", ""), research_notes=(prof.get("research") or {}).get("notes", ""))
        comp.entries.append(entry)
    return comp
