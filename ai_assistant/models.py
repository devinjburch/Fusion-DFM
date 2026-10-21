"""Structured, JSON-serialisable data models for the future AI redesign workflow."""
from __future__ import annotations
import datetime as _dt
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


def _id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _now():
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


class State(str, Enum):
    DETECTED = "DETECTED"
    EXPLAINED = "EXPLAINED"
    PROPOSED = "PROPOSED"                 # >= 1 candidate correction generated
    AWAITING_APPROVAL = "AWAITING_APPROVAL"   # one correction shown to the user
    APPROVED = "APPROVED"
    APPLIED = "APPLIED"
    REANALYZED = "REANALYZED"
    ACCEPTED = "ACCEPTED"
    UNDONE = "UNDONE"
    REJECTED = "REJECTED"


@dataclass
class AffectedFeature:
    kind: str                              # "flange" | "bend" | "hole" | "cutout" | "body"
    ref_token: Optional[str] = None        # Fusion entityToken (opaque)
    label: str = ""
    cad_parameter: Optional[str] = None    # name of the driving CAD parameter/dimension, if known
    owner_feature: Optional[str] = None    # timeline feature that owns it (sketch, flange, hole...), if known

    def to_dict(self): return asdict(self)

    @staticmethod
    def from_dict(d): return AffectedFeature(**d)


@dataclass
class ParameterChange:
    target: AffectedFeature
    parameter: str                         # e.g. "flange_length", "inner_bend_radius", "feature_min_dimension"
    from_value_mm: Optional[float]
    to_value_mm: float
    units: str = "mm"

    @property
    def delta_mm(self):
        return None if self.from_value_mm is None else self.to_value_mm - self.from_value_mm

    def inverse(self) -> "ParameterChange":
        if self.from_value_mm is None:
            raise ValueError("cannot invert a change with unknown original value")
        return ParameterChange(self.target, self.parameter, self.to_value_mm, self.from_value_mm, self.units)

    def to_dict(self):
        d = asdict(self); d["delta_mm"] = self.delta_mm; return d

    @staticmethod
    def from_dict(d):
        d = dict(d); d.pop("delta_mm", None); d["target"] = AffectedFeature.from_dict(d["target"])
        return ParameterChange(**d)


@dataclass
class DesignConstraint:
    kind: str                              # "locked_parameter" | "max_change_mm" | "keep_material" | "keep_thickness" | "custom"
    description: str
    target: Optional[AffectedFeature] = None
    parameter: Optional[str] = None
    value_mm: Optional[float] = None
    source: str = "user"                   # "user" | "system"
    constraint_id: str = field(default_factory=lambda: _id("con"))

    def violated_by(self, change: ParameterChange) -> Optional[str]:
        same = (self.target is None or self.target.ref_token == change.target.ref_token) and \
               (self.parameter is None or self.parameter == change.parameter)
        if self.kind == "locked_parameter" and same:
            return f"{change.parameter} is locked: {self.description}"
        if self.kind == "max_change_mm" and same and self.value_mm is not None and change.delta_mm is not None \
                and abs(change.delta_mm) > self.value_mm + 1e-9:
            return f"change of {abs(change.delta_mm):.2f} mm exceeds the allowed {self.value_mm:.2f} mm: {self.description}"
        if self.kind in ("keep_thickness", "keep_material") and change.parameter in ("sheet_thickness", "material"):
            return f"{change.parameter} must not change: {self.description}"
        return None

    def to_dict(self): return asdict(self)

    @staticmethod
    def from_dict(d):
        d = dict(d)
        if d.get("target"): d["target"] = AffectedFeature.from_dict(d["target"])
        return DesignConstraint(**d)


@dataclass
class ValidationRequirement:
    kind: str                              # "reanalyze" | "problem_resolved" | "no_new_failures" | "constraints_hold" | "flat_pattern_regenerates"
    description: str = ""
    params: dict = field(default_factory=dict)

    def to_dict(self): return asdict(self)


@dataclass
class ManufacturingProblem:
    rule_id: str
    manufacturer_id: str
    status: str                            # always "FAIL" for actionable problems
    severity: str
    explanation: str
    feature: AffectedFeature
    measured_mm: Optional[float] = None
    required_mm: Optional[float] = None
    source_url: str = ""
    strength: str = "requirement"
    problem_id: str = field(default_factory=lambda: _id("prob"))

    def to_dict(self):
        d = asdict(self); return d

    @staticmethod
    def from_dict(d):
        d = dict(d); d["feature"] = AffectedFeature.from_dict(d["feature"]); return ManufacturingProblem(**d)


@dataclass
class SuggestedCorrection:
    problem_id: str
    title: str
    rationale: str
    changes: list                          # list[ParameterChange]
    confidence: str = "minimum"            # "exact" | "minimum" | "heuristic"
    side_effects: list = field(default_factory=list)
    validations: list = field(default_factory=list)       # list[ValidationRequirement]
    violated_constraints: list = field(default_factory=list)   # strings; non-empty => cannot be applied
    correction_id: str = field(default_factory=lambda: _id("fix"))
    status: str = "proposed"               # proposed | approved | rejected | applied | rolled_back

    @property
    def applicable(self): return not self.violated_constraints

    def to_dict(self):
        d = asdict(self); d["changes"] = [c.to_dict() for c in self.changes]; d["applicable"] = self.applicable; return d

    @staticmethod
    def from_dict(d):
        d = dict(d); d.pop("applicable", None)
        d["changes"] = [ParameterChange.from_dict(c) for c in d["changes"]]
        d["validations"] = [ValidationRequirement(**v) for v in d.get("validations", [])]
        return SuggestedCorrection(**d)


@dataclass
class ApprovalRecord:
    correction_id: str
    approved_by: str                       # user identity as supplied by the host UI
    approved_at: str = field(default_factory=_now)
    shown_summary: str = ""                # exact text the user saw when approving

    def to_dict(self): return asdict(self)


@dataclass
class UndoOperation:
    correction_id: str
    inverse_changes: list                  # list[ParameterChange] restoring the original values
    strategy: str = "parameter_restore"    # "parameter_restore" | "timeline_rollback" | "document_version"
    snapshot_ref: Optional[str] = None     # e.g. timeline marker / document version id (adapter specific)
    created_at: str = field(default_factory=_now)
    executed: bool = False
    op_id: str = field(default_factory=lambda: _id("undo"))

    def to_dict(self):
        d = asdict(self); d["inverse_changes"] = [c.to_dict() for c in self.inverse_changes]; return d


@dataclass
class RollbackPlan:
    operations: list                       # UndoOperation, newest first
    def to_dict(self): return {"operations": [o.to_dict() for o in self.operations]}
