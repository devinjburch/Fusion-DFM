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


@dataclass
class Bend:
    inner_radius_mm: Optional[float] = None
    angle_deg: Optional[float] = None
    ref: Optional[GeometryRef] = None


@dataclass
class Flange:
    length_mm: float
    is_terminal: bool = True   # True only for a free flange (one bend on one side)
    ref: Optional[GeometryRef] = None


@dataclass
class PartModel:
    name: str
    thickness_mm: Optional[float] = None
    thickness_source: str = ""
    material_name: Optional[str] = None
    flat_dimensions_mm: Optional[tuple] = None    # flat-pattern (L, W); None if unavailable
    folded_dimensions_mm: Optional[tuple] = None  # axis-aligned bbox (X, Y, Z)
    holes: list = field(default_factory=list)
    bends: list = field(default_factory=list)
    flanges: list = field(default_factory=list)
    body_ref: Optional[GeometryRef] = None
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

    def to_dict(self) -> dict:
        d = asdict(self)
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

    def counts(self) -> dict:
        c = {s.value: 0 for s in Status}
        for r in self.results:
            c[r.status.value] += 1
        return c

    def to_dict(self) -> dict:
        return {"manufacturer_id": self.manufacturer_id, "manufacturer_name": self.manufacturer_name,
                "process_id": self.process_id, "material_id": self.material_id,
                "part_name": self.part_name, "overall": self.overall.value, "demo": self.demo,
                "counts": self.counts(), "notes": self.notes,
                "results": [r.to_dict() for r in self.results]}
