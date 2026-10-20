"""Evaluate a PartModel against a validated manufacturer profile."""
from __future__ import annotations
from typing import Optional
from .models import PartModel, Report, RuleResult, Severity, Status

EPS = 1e-3  # mm; tolerance for float noise from CAD kernels


def match_material(profile_process: dict, material_name: Optional[str]) -> Optional[str]:
    """Best alias match (longest alias wins). Returns None rather than guessing."""
    if not material_name:
        return None
    name = material_name.casefold()
    best, best_len = None, 0
    for mat in profile_process.get("materials", []):
        for alias in [mat["name"], *mat.get("aliases", [])]:
            a = alias.casefold()
            if a and a in name and len(a) > best_len:
                best, best_len = mat["id"], len(a)
    return best


def evaluate(part: PartModel, profile: dict, process_id: str,
             material_id: Optional[str] = None) -> Report:
    process = next((p for p in profile["processes"] if p["id"] == process_id), None)
    if process is None:
        raise KeyError(f"process {process_id!r} not in profile {profile['manufacturer']['id']}")
    notes = []
    if material_id is None:
        material_id = match_material(process, part.material_name)
        if material_id is None:
            notes.append("Material not recognised for this manufacturer; material-specific "
                         "rules need review.")
    ctx = _Ctx(part, profile, process, material_id)
    results = []
    for rule in process.get("rules", []):
        results.extend(ctx.run(rule))
    return Report(profile["manufacturer"]["id"], profile["manufacturer"]["name"], process_id,
                  material_id, part.name, _overall(results), results,
                  demo=profile["profile_status"] == "demo", notes=notes)


def _overall(results) -> Status:
    s = {r.status for r in results}
    if Status.FAIL in s:
        return Status.FAIL
    if Status.NEEDS_REVIEW in s:
        return Status.NEEDS_REVIEW
    return Status.PASS if Status.PASS in s else Status.NEEDS_REVIEW


class _Ctx:
    def __init__(self, part, profile, process, material_id):
        self.part, self.profile, self.process, self.material_id = part, profile, process, material_id

    # -- result construction -------------------------------------------------
    def _mk(self, rule, status, explanation, rec="", measured=None, required=None,
            ref=None, severity=None) -> RuleResult:
        src = rule.get("source") or {}
        if severity is None:
            severity = {Status.FAIL: Severity(rule.get("severity", "ERROR")),
                        Status.NEEDS_REVIEW: Severity.WARNING}.get(status, Severity.INFO)
        return RuleResult(
            rule_id=rule["id"], rule_type=rule["type"], status=status, severity=severity,
            explanation=explanation, recommendation=rec, measured=measured, required=required,
            geometry_ref=ref, source_url=src.get("url", ""), date_verified=src.get("date_verified", ""),
            manufacturer=self.profile["manufacturer"]["name"],
            demo=self.profile["profile_status"] == "demo")

    def _review(self, rule, why, ref=None):
        return self._mk(rule, Status.NEEDS_REVIEW, f"Cannot evaluate: {why}",
                        "Check this requirement manually against the manufacturer's documentation.",
                        ref=ref)

    # -- dispatch ------------------------------------------------------------
    def run(self, rule):
        if not rule["enabled"]:
            why = rule.get("limitations") or "No verified manufacturer data for this rule."
            return [self._mk(rule, Status.SKIPPED, f"Rule not checked: {why}", severity=Severity.INFO)]
        ap = rule.get("applies_to") or {}
        mats = ap.get("materials")
        if mats:
            if self.material_id is None:
                return [self._review(rule, "part material could not be matched to a manufacturer material.")]
            if self.material_id not in mats:
                return []  # not applicable to this material
        t = self.part.thickness_mm
        tr = ap.get("thickness_mm")
        if tr:
            if t is None:
                return [self._review(rule, "sheet thickness unavailable, needed to select this rule.")]
            if t < tr.get("min", 0) - EPS or t > tr.get("max", float("inf")) + EPS:
                return []
        return getattr(self, "_" + rule["type"])(rule, rule["parameters"])

    # -- helpers ---------------------------------------------------------------
    def _required(self, rule, params):
        """Return (required_mm, error). Uses the larger of absolute and ratio-based minimums."""
        vals = []
        if "min_mm" in params:
            vals.append(params["min_mm"])
        if "min_ratio_to_thickness" in params:
            if self.part.thickness_mm is None:
                return None, "sheet thickness unavailable, needed for a thickness-relative limit."
            vals.append(params["min_ratio_to_thickness"] * self.part.thickness_mm)
        return max(vals), None

    def _min_check(self, rule, params, items, attr, unsupported_key, label, rec):
        if unsupported_key in self.part.unsupported:
            return [self._review(rule, f"{label} extraction unsupported: {self.part.unsupported[unsupported_key]}")]
        req, err = self._required(rule, params)
        if err:
            return [self._review(rule, err)]
        out = []
        for i, it in enumerate(items, 1):
            v = getattr(it, attr)
            ref = getattr(it, "ref", None)
            if v is None:
                out.append(self._review(rule, f"{label} #{i} could not be measured.", ref))
            elif v < req - EPS:
                out.append(self._mk(rule, Status.FAIL,
                                    f"{label} #{i} is {v:.2f} mm; {self.profile['manufacturer']['name']} requires at least {req:.2f} mm.",
                                    rec.format(req=req), v, f">= {req:.2f} mm", ref))
            else:
                out.append(self._mk(rule, Status.PASS, f"{label} #{i} is {v:.2f} mm (minimum {req:.2f} mm).",
                                    measured=v, required=f">= {req:.2f} mm", ref=ref))
        return out

    # -- rule implementations ---------------------------------------------------
    def _thickness_range(self, rule, p):
        t = self.part.thickness_mm
        if t is None:
            why = self.part.unsupported.get("thickness", "sheet thickness could not be determined.")
            return [self._review(rule, why)]
        req = f"{p['min_mm']:.3f}-{p['max_mm']:.3f} mm"
        if t < p["min_mm"] - EPS or t > p["max_mm"] + EPS:
            return [self._mk(rule, Status.FAIL,
                             f"Sheet thickness {t:.3f} mm is outside the supported range {req}.",
                             "Change the sheet metal rule thickness to a supported value or choose another material/manufacturer.",
                             t, req, self.part.body_ref)]
        return [self._mk(rule, Status.PASS, f"Sheet thickness {t:.3f} mm is within {req}.",
                         measured=t, required=req, ref=self.part.body_ref)]

    def _min_bend_radius(self, rule, p):
        return self._min_check(rule, p, self.part.bends, "inner_radius_mm", "bends", "Bend",
                               "Increase the inner bend radius to at least {req:.2f} mm.")

    def _min_flange_length(self, rule, p):
        return self._min_check(rule, p, [f for f in self.part.flanges if f.is_terminal],
                               "length_mm", "flanges", "Flange",
                               "Lengthen the flange to at least {req:.2f} mm.")

    def _min_hole_edge_distance(self, rule, p):
        return self._min_check(rule, p, self.part.holes, "dist_to_edge_mm", "hole_edge_distance",
                               "Hole-to-edge distance of hole",
                               "Move the hole at least {req:.2f} mm from the nearest edge.")

    def _min_hole_bend_distance(self, rule, p):
        holes = [h for h in self.part.holes if h.has_adjacent_bend is not False]
        return self._min_check(rule, p, holes, "dist_to_bend_mm", "hole_bend_distance",
                               "Hole-to-bend distance of hole",
                               "Move the hole at least {req:.2f} mm from the bend line.")

    def _min_hole_diameter(self, rule, p):
        return self._min_check(rule, p, self.part.holes, "diameter_mm", "holes", "Diameter of hole",
                               "Increase the hole diameter to at least {req:.2f} mm.")

    def _max_part_dimensions(self, rule, p):
        d = self.part.flat_dimensions_mm
        if d is None:
            why = self.part.unsupported.get("flat_dimensions", "flat pattern dimensions unavailable.")
            return [self._review(rule, why, self.part.body_ref)]
        long_, short = sorted(d, reverse=True)[:2]
        bad = (("max_long_mm" in p and long_ > p["max_long_mm"] + EPS) or
               ("max_short_mm" in p and short > p["max_short_mm"] + EPS))
        req = f"<= {p.get('max_long_mm', '-')} x {p.get('max_short_mm', '-')} mm"
        if bad:
            return [self._mk(rule, Status.FAIL,
                             f"Flat size {long_:.1f} x {short:.1f} mm exceeds the maximum {req}.",
                             "Reduce the flat pattern size or split the part.", long_, req, self.part.body_ref)]
        return [self._mk(rule, Status.PASS, f"Flat size {long_:.1f} x {short:.1f} mm is within {req}.",
                         measured=long_, required=req, ref=self.part.body_ref)]
