"""Structured correction proposals. Pure data - nothing here modifies CAD.

A Correction describes *what parameter should change and by how much*. A future AI/automation layer
(ai_assistant/) may turn a Correction into a CAD operation after explicit user approval.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional
from .models import GeometryRef
from .units import fmt_len

KINDS = {"increase_flange_length", "set_bend_radius", "move_feature", "increase_feature_size",
         "change_thickness", "change_material", "resize_part", "reduce_bend_angle"}


@dataclass
class Correction:
    kind: str
    rule_id: str
    parameter: str                       # e.g. "flange_length", "inner_bend_radius"
    direction: str                       # "increase" | "decrease" | "set" | "move_away"
    current_mm: Optional[float]
    proposed_mm: Optional[float]
    explanation: str
    target: Optional[GeometryRef] = None
    confidence: str = "minimum"          # "exact" (manufacturer value) | "minimum" (smallest change that satisfies) | "heuristic"
    alternatives: list = field(default_factory=list)   # other proposed_mm values / descriptions
    side_effects: list = field(default_factory=list)
    requires_user_approval: bool = True  # always; never auto-applied

    @property
    def delta_mm(self) -> Optional[float]:
        if self.current_mm is None or self.proposed_mm is None:
            return None
        return self.proposed_mm - self.current_mm

    def summary(self) -> str:
        d = self.delta_mm
        change = f" ({'+' if d >= 0 else ''}{fmt_len(d)})" if d is not None else ""
        return f"{self.direction} {self.parameter} from {fmt_len(self.current_mm)} to {fmt_len(self.proposed_mm)}{change}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["delta_mm"] = self.delta_mm
        d["summary"] = self.summary()
        return d
