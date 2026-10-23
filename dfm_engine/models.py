"""Geometry-neutral data structures. All lengths are millimetres, angles degrees."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class Status(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    SKIPPED = "SKIPPED"  # rule disabled/unverified: NOT a pass, nothing was checked
    WARNING = "WARNING"  # non-blocking rule (consequence "warning"): violation confirmed or not ruled out; never a pass


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass(frozen=True)
class GeometryRef:
    """Opaque pointer back into the CAD model (e.g. a Fusion entityToken)."""
    kind: str                      # "hole" | "bend" | "flange" | "body"
    token: Optional[str] = None
    label: str = ""


@dataclass
class Hole:
    diameter_mm: float
    position_mm: Optional[tuple] = None          # (x, y, z) in model space
    dist_to_edge_mm: Optional[float] = None      # hole boundary -> nearest outer edge
    dist_to_bend_mm: Optional[float] = None      # hole boundary -> nearest bend tangent line
    has_adjacent_bend: Optional[bool] = None     # False: its face has no bend (rule N/A); None: unknown
    ref: Optional[GeometryRef] = None
    # upper bound of (tangent line -> bend centerline) on the adjacent bend, mm: (R_inner + t) * angle / 2
    bend_zone_max_mm: Optional[float] = None

    @property
    def kind(self) -> str:
        return "hole"

    @property
    def min_dimension_mm(self) -> float:
        return self.diameter_mm


@dataclass
class Cutout:
    """Non-circular opening (slot, rectangle, irregular) in a sheet face."""
    cutout_kind: str                              # "slot" | "rect" | "irregular" | "unknown"
    min_dimension_mm: Optional[float] = None      # slot width / smallest rectangle side / None if unknown
    length_mm: Optional[float] = None
    position_mm: Optional[tuple] = None
    dist_to_edge_mm: Optional[float] = None
    dist_to_bend_mm: Optional[float] = None
    has_adjacent_bend: Optional[bool] = None
    bend_zone_max_mm: Optional[float] = None
    certain: bool = True                          # False -> classification uncertain: rules give NEEDS_REVIEW
    uncertainty_reason: str = ""
    ref: Optional[GeometryRef] = None

    @property
    def kind(self) -> str:
        return self.cutout_kind


@dataclass
class Bend:
    inner_radius_mm: Optional[float] = None
    angle_deg: Optional[float] = None
    length_mm: Optional[float] = None
    ref: Optional[GeometryRef] = None


@dataclass
class Flange:
    length_mm: float                      # on the flange face, from the bend tangent line to the far edge
    is_terminal: bool = True              # True only for a free flange (one bend on one side)
    ref: Optional[GeometryRef] = None
    length_apex_mm: Optional[float] = None    # from the bend apex (virtual sharp of the outer faces); needs bend angle
    bend_angle_deg: Optional[float] = None


@dataclass
class PartModel:
    name: str
    thickness_mm: Optional[float] = None
    thickness_source: str = ""
    material_name: Optional[str] = None
    flat_dimensions_mm: Optional[tuple] = None    # flat-pattern (L, W); None if unavailable
    folded_dimensions_mm: Optional[tuple] = None  # axis-aligned bbox (X, Y, Z)
    holes: list = field(default_factory=list)
    cutouts: list = field(default_factory=list)
    bends: list = field(default_factory=list)
    flanges: list = field(default_factory=list)
    body_ref: Optional[GeometryRef] = None
    component_path: str = ""              # e.g. "Assembly1/Bracket:1" when part of an assembly
    instance_count: int = 1
    # feature name -> reason it could not be extracted. Never invent values.
    unsupported: dict = field(default_factory=dict)


@dataclass
class RuleResult:
    rule_id: str
    rule_type: str
    status: Status
    severity: Severity
    explanation: str
    recommendation: str = ""
    measured: Optional[float] = None
    required: Optional[str] = None
    unit: str = "mm"
    geometry_ref: Optional[GeometryRef] = None
    source_url: str = ""
    date_verified: str = ""
    manufacturer: str = ""
    demo: bool = False
    strength: str = "requirement"         # "requirement" (verified limit) | "advisory" (guidance only)
    rationale: str = ""                   # why the requirement exists, only where the source states it
    required_mm: Optional[float] = None   # numeric requirement (the string `required` is for display)
    notes: str = ""                       # source qualifications / exceptions
    corrections: list = field(default_factory=list)   # list[Correction]
    feature_kind: str = ""
    feature_label: str = ""               # e.g. "Hole #4" when the CAD reference has no label
    title: str = ""                       # short rule-specific heading, e.g. "Hole 4: too close to bend"
    consequence: str = "blocking"         # "blocking" | "warning" (from the rule)
    confirmed: bool = True                # False for a WARNING that could not be confirmed (unresolved check)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["corrections"] = [c.to_dict() if hasattr(c, "to_dict") else c for c in self.corrections]
        d["status"] = self.status.value
        d["severity"] = self.severity.value
        return d


@dataclass
class Report:
    manufacturer_id: str
    manufacturer_name: str
    process_id: str
    material_id: Optional[str]
    part_name: str
    overall: Status
    results: list
    demo: bool = False
    notes: list = field(default_factory=list)
    coverage_gaps: list = field(default_factory=list)   # rule categories with no verified, evaluated check
    material_name: Optional[str] = None
    thickness_mm: Optional[float] = None
    thickness_match: str = ""

    def counts(self) -> dict:
        c = {s.value: 0 for s in Status}
        for r in self.results:
            c[r.status.value] += 1
        return c

    def to_dict(self) -> dict:
        return {"manufacturer_id": self.manufacturer_id, "manufacturer_name": self.manufacturer_name,
                "process_id": self.process_id, "material_id": self.material_id,
                "part_name": self.part_name, "overall": self.overall.value, "demo": self.demo,
                "counts": self.counts(), "notes": self.notes, "coverage_gaps": self.coverage_gaps,
                "material_name": self.material_name, "thickness_mm": self.thickness_mm,
                "thickness_match": self.thickness_match,
                "results": [r.to_dict() for r in self.results]}
