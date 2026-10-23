"""Evaluate a PartModel against a validated manufacturer profile.

Principles: missing/uncertain information never yields PASS; only enabled, verified rules yield PASS/FAIL;
advisory rules never FAIL (they yield NEEDS_REVIEW at INFO severity); conflicting manufacturer values
yield NEEDS_REVIEW unless the outcome is the same under every candidate.
"""
from __future__ import annotations
from typing import Optional
from .corrections import Correction
from .models import PartModel, Report, RuleResult, Severity, Status
from .profile import DEFAULT_TOLERANCE_MM
from .units import fmt_len, MM_PER_IN

EPS = 1e-3  # mm; tolerance for float noise from CAD kernels

CATEGORY = {
    "thickness_range": "thickness", "thickness_in_stock": "thickness",
    "min_bend_radius": "bend_radius", "bend_radius_match": "bend_radius",
    "min_flange_length": "flange_length", "min_hole_diameter": "hole_diameter",
    "min_hole_edge_distance": "hole_edge_distance", "min_hole_bend_distance": "hole_bend_distance",
    "max_part_dimensions": "max_part_size", "min_part_dimensions": "min_part_size", "max_bend_length": "max_bend_length",
}
CORE_CATEGORIES = ["thickness", "bend_radius", "flange_length", "hole_diameter",
                   "hole_edge_distance", "hole_bend_distance", "max_part_size"]
CATEGORY_LABEL = {"thickness": "material thickness", "bend_radius": "bend radius", "flange_length": "flange length",
                  "hole_diameter": "hole/cutout size", "hole_edge_distance": "hole-to-edge distance",
                  "hole_bend_distance": "hole-to-bend distance", "max_part_size": "maximum part size"}


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


def find_thickness_row(material: Optional[dict], t_mm: Optional[float], tol: float):
    """-> (row | None, status) with status 'match' | 'none' | 'ambiguous' | 'no_table'."""
    if material is None or not material.get("thickness_specs"):
        return None, "no_table"
    if t_mm is None:
        return None, "none"
    hits = [r for r in material["thickness_specs"] if abs(r["thickness_mm"] - t_mm) <= tol + 1e-9]
    if len(hits) == 1:
        return hits[0], "match"
    return (None, "ambiguous") if hits else (None, "none")


def evaluate(part: PartModel, profile: dict, process_id: str,
             material_id: Optional[str] = None) -> Report:
    process = next((p for p in profile["processes"] if p["id"] == process_id), None)
    if process is None:
        raise KeyError(f"process {process_id!r} not in profile {profile['manufacturer']['id']}")
    notes = []
    if material_id is None:
        material_id = match_material(process, part.material_name)
        if material_id is None:
            notes.append("Material not recognised for this manufacturer; material-specific rules need review.")
    ctx = _Ctx(part, profile, process, material_id)
    results = []
    for rule in process.get("rules", []):
        results.extend(ctx.run(rule))
    gaps = _coverage_gaps(process, material_id, profile['profile_status'] == 'demo')
    row, st = find_thickness_row(ctx.material, part.thickness_mm, ctx.tol)
    match_note = ""
    if st == "match":
        match_note = f"matched listed stock thickness {row['thickness_mm']:.3f} mm"
    elif st in ("none", "ambiguous") and ctx.material and ctx.material.get("thickness_specs"):
        match_note = "no unique listed stock thickness within tolerance"
    return Report(profile["manufacturer"]["id"], profile["manufacturer"]["name"], process_id,
                  material_id, part.name, _overall(results), results,
                  demo=profile["profile_status"] == "demo", notes=notes, coverage_gaps=gaps,
                  material_name=ctx.material["name"] if ctx.material else None,
                  thickness_mm=part.thickness_mm, thickness_match=match_note)


def _overall(results) -> Status:
    s = {r.status for r in results}
    if Status.FAIL in s:
        return Status.FAIL
    if Status.NEEDS_REVIEW in s:
        return Status.NEEDS_REVIEW
    if Status.WARNING in s:
        return Status.WARNING          # passes, but with warnings that must be shown
    return Status.PASS if Status.PASS in s else Status.NEEDS_REVIEW


# short, rule-specific headings: (confirmed violation, could not be confirmed, ok)
PHRASES = {
    "thickness_range": ("thickness outside supported range", "thickness not confirmed as supported", "thickness supported"),
    "thickness_in_stock": ("not a stocked thickness", "not confirmed as a stocked thickness", "stocked thickness"),
    "min_bend_radius": ("bend radius too small", "bend radius not confirmed", "bend radius ok"),
    "bend_radius_match": ("bend radius differs from the fixed radius", "bend radius not confirmed", "bend radius matches"),
    "min_flange_length": ("flange too short", "flange length not confirmed", "flange length ok"),
    "min_hole_edge_distance": ("too close to edge", "may be too close to edge", "edge distance ok"),
    "min_hole_bend_distance": ("too close to bend", "may be too close to bend", "bend distance ok"),
    "min_hole_diameter": ("too small", "size not confirmed", "size ok"),
    "max_bend_length": ("bend too long", "bend length not confirmed", "bend length ok"),
    "max_part_dimensions": ("flat part too large", "flat size not confirmed", "flat size ok"),
    "min_part_dimensions": ("flat part too small", "flat size not confirmed", "flat size ok"),
}
DEFAULT_LABEL = {"thickness_range": "Sheet thickness", "thickness_in_stock": "Sheet thickness",
                 "max_part_dimensions": "Flat size", "min_part_dimensions": "Flat size"}


def make_title(r: RuleResult, original: Status) -> str:
    if r.status == Status.SKIPPED:
        return f"{r.rule_id}: not checked"
    label = (r.geometry_ref.label if r.geometry_ref and r.geometry_ref.label else "") or r.feature_label \
        or DEFAULT_LABEL.get(r.rule_type, "Part")
    bad, maybe, ok = PHRASES.get(r.rule_type, ("requirement not met", "could not be checked", "ok"))
    phrase = ok if r.status == Status.PASS else (bad if original == Status.FAIL else maybe)
    return f"{label}: {phrase}"


def _coverage_gaps(process, material_id, demo):
    """Core rule categories for which no enabled, verified (or demo) rule applies to the material."""
    required = process.get("coverage_required", CORE_CATEGORIES)
    covered = set()
    for r in process.get("rules", []):
        if not r["enabled"] or not (r["verified"] or demo):
            continue
        mats = (r.get("applies_to") or {}).get("materials")
        if mats and material_id is not None and material_id not in mats:
            continue
        covered.add(CATEGORY.get(r["type"]))
    return [c for c in required if c not in covered]


class _Ctx:
    def __init__(self, part, profile, process, material_id):
        self.part, self.profile, self.process, self.material_id = part, profile, process, material_id
        self.material = next((m for m in process.get("materials", []) if m["id"] == material_id), None)
        self.tol = process.get("thickness_match_tolerance_mm", DEFAULT_TOLERANCE_MM)
        self.mfr = profile["manufacturer"]["name"]
        self.rule = None

    # ------------------------------------------------------------ result construction
    def _mk(self, status, explanation, rec="", measured=None, required=None, ref=None,
            severity=None, required_mm=None, corrections=None, feature_kind="", label="") -> RuleResult:
        rule = self.rule
        src = rule.get("source") or {}
        if severity is None:
            severity = {Status.FAIL: Severity(rule.get("severity", "ERROR")),
                        Status.NEEDS_REVIEW: Severity.WARNING}.get(status, Severity.INFO)
        return RuleResult(
            rule_id=rule["id"], rule_type=rule["type"], status=status, severity=severity,
            explanation=explanation, recommendation=rec, measured=measured, required=required,
            geometry_ref=ref, source_url=src.get("url", ""), date_verified=src.get("date_verified", ""),
            manufacturer=self.mfr, demo=self.profile["profile_status"] == "demo",
            strength=rule.get("strength", "requirement"), rationale=rule.get("rationale", ""),
            required_mm=required_mm, notes=rule.get("notes", ""), corrections=corrections or [],
            feature_kind=feature_kind, feature_label=label)

    def _review(self, why, ref=None, kind=""):
        return self._mk(Status.NEEDS_REVIEW, f"Cannot evaluate: {why}",
                        "Check this requirement manually against the manufacturer's documentation.", ref=ref,
                        feature_kind=kind)

    # ------------------------------------------------------------ dispatch
    def run(self, rule):
        out = self._run(rule)
        for r in out:                      # every result gets a heading, including skipped / early-return ones
            if not r.title:
                r.title = make_title(r, r.status)
            r.consequence = rule.get("consequence", "blocking")
        return out

    def _run(self, rule):
        self.rule = rule
        if not rule["enabled"] or (not rule["verified"] and self.profile["profile_status"] != "demo"):
            why = rule.get("limitations") or "No verified manufacturer data for this rule."
            return [self._mk(Status.SKIPPED, f"Rule not checked: {why}", severity=Severity.INFO)]
        ap = rule.get("applies_to") or {}
        mats = ap.get("materials")
        if mats:
            if self.material_id is None:
                return [self._review("part material could not be matched to a manufacturer material.")]
            if self.material_id not in mats:
                return []
        t = self.part.thickness_mm
        tr = ap.get("thickness_mm")
        if tr:
            if t is None:
                return [self._review("sheet thickness unavailable, needed to select this rule.")]
            if t < tr.get("min", 0) - EPS or t > tr.get("max", float("inf")) + EPS:
                return []
        out = getattr(self, "_" + rule["type"])(rule, rule.get("parameters") or {})
        original = [r.status for r in out]
        out = [self._apply_strength(r) for r in out]
        if rule.get("consequence") == "warning" and rule.get("strength", "requirement") == "requirement":
            out = [self._apply_consequence(r) for r in out]
        for r, o in zip(out, original):
            r.consequence = rule.get("consequence", "blocking")
            r.title = make_title(r, o)
        return out

    @staticmethod
    def _apply_consequence(r):
        """Non-blocking rule: a confirmed violation OR an unresolved check becomes a WARNING (never a pass)."""
        if r.status in (Status.FAIL, Status.NEEDS_REVIEW):
            r.confirmed = r.status == Status.FAIL
            r.status, r.severity = Status.WARNING, Severity.WARNING
            if not r.confirmed:
                r.explanation = "Not confirmed (non-blocking rule): " + r.explanation
        return r

    def _apply_strength(self, r):
        if r.strength == "advisory" and r.status == Status.FAIL:
            r.status, r.severity = Status.NEEDS_REVIEW, Severity.INFO
            r.explanation = "Advisory guidance (not a hard requirement): " + r.explanation
        return r

    # ------------------------------------------------------------ requirement resolution
    def _spec_candidates(self, params):
        """-> (candidates | None, problem str | None). Values in mm; factor applied."""
        name = params["spec"]
        row, st = find_thickness_row(self.material, self.part.thickness_mm, self.tol)
        if self.part.thickness_mm is None:
            return None, "sheet thickness unavailable."
        if st == "no_table":
            return None, "no per-thickness specification table for this material."
        if st == "none":
            return None, (f"thickness {self.part.thickness_mm:.3f} mm is not a listed stock thickness "
                          f"(within {self.tol:g} mm) for {self.material['name']}.")
        if st == "ambiguous":
            return None, "thickness matches more than one listed stock thickness."
        conflicts = (row.get("conflicts") or {}).get(name)
        if conflicts:
            vals = [c["value"] for c in conflicts]
        else:
            v = (row.get("values") or {}).get(name)
            if v is None:
                return None, f"{name} is not published for {self.material['name']} {row['thickness_mm']:.3f} mm."
            vals = v if isinstance(v, list) else [v]
            if name.endswith("_size_mm"):
                return [vals], None          # a single [a, b] pair
        f = params.get("factor", 1.0)
        return [x * f for x in vals], None

    def _min_candidates(self, params):
        """Requirement candidates for min-style rules: list of mm (>=1) or (None, problem)."""
        if "spec" in params:
            return self._spec_candidates(params)
        vals = []
        if "min_mm" in params:
            vals.append(params["min_mm"])
        if "min_ratio_to_thickness" in params:
            if self.part.thickness_mm is None:
                return None, "sheet thickness unavailable, needed for a thickness-relative limit."
            vals.append(params["min_ratio_to_thickness"] * self.part.thickness_mm)
        return [max(vals)], None

    @staticmethod
    def _judge_min(measured, cands):
        hi, lo = max(cands), min(cands)
        if measured >= hi - EPS:
            return "PASS", hi
        if measured < lo - EPS:
            return "FAIL", hi
        return "REVIEW", hi

    def _req_text(self, cands, prefix=">="):
        if len(set(round(c, 4) for c in cands)) == 1:
            return f"{prefix} {cands[0]:.2f} mm"
        return f"{prefix} " + " or ".join(f"{c:.2f} mm" for c in sorted(set(round(c, 4) for c in cands))) + " (sources disagree)"

    def _scope(self):
        if self.material:
            t = self.part.thickness_mm
            return f" for {self.material['name']}" + (f" {t:.2f} mm" if t else "")
        return ""

    # ------------------------------------------------------------ min-style checks on a list of items
    def _min_items(self, params, items, getter, label, unsupported_key, fix_fmt, corr, unit_note=""):
        """items: list of (name, obj). getter(obj) -> measured mm or None."""
        if unsupported_key and unsupported_key in self.part.unsupported:
            return [self._review(f"{label} extraction unsupported: {self.part.unsupported[unsupported_key]}")]
        cands, err = self._min_candidates(params)
        if err:
            return [self._review(err)]
        out = []
        for name, it in items:
            v, ref = getter(it), getattr(it, "ref", None)
            kind = getattr(it, "kind", "")
            if getattr(it, "certain", True) is False:
                out.append(self._review(f"{name}: classification uncertain ({it.uncertainty_reason or 'unknown feature shape'}).", ref, kind))
                continue
            if v is None:
                out.append(self._review(f"{name} could not be measured.", ref, kind))
                continue
            verdict, req = self._judge_min(v, cands)
            req_txt = self._req_text(cands)
            if verdict == "PASS":
                out.append(self._mk(Status.PASS, f"{name} is {fmt_len(v)} (minimum {fmt_len(req)}){self._scope()}.",
                                    measured=v, required=req_txt, ref=ref, required_mm=req, feature_kind=kind, label=name))
            elif verdict == "REVIEW":
                out.append(self._mk(Status.NEEDS_REVIEW,
                                    f"{name} is {fmt_len(v)}; manufacturer sources disagree on the minimum ({req_txt}).",
                                    "Resolve the conflicting manufacturer values or meet the larger one.",
                                    measured=v, required=req_txt, ref=ref, required_mm=req, feature_kind=kind, label=name))
            else:
                delta = req - v
                c = corr(name, it, v, req)
                out.append(self._mk(Status.FAIL,
                                    f"{name} is {fmt_len(v)}; {self.mfr} requires at least {fmt_len(req)}{self._scope()}.",
                                    fix_fmt.format(req=fmt_len(req), delta=fmt_len(delta), name=name) + unit_note,
                                    measured=v, required=req_txt, ref=ref, required_mm=req,
                                    corrections=[c] if c else [], feature_kind=kind, label=name))
        return out

    # ------------------------------------------------------------ rule implementations
    def _thickness_range(self, rule, p):
        t = self.part.thickness_mm
        if t is None:
            return [self._review(self.part.unsupported.get("thickness", "sheet thickness could not be determined."))]
        req = f"{p['min_mm']:.3f}-{p['max_mm']:.3f} mm"
        if t < p["min_mm"] - EPS or t > p["max_mm"] + EPS:
            tgt = p["min_mm"] if t < p["min_mm"] else p["max_mm"]
            c = Correction("change_thickness", rule["id"], "sheet_thickness", "set", t, tgt,
                           f"Change the sheet metal rule thickness to {fmt_len(tgt)} (limit of the supported range) or choose another material/manufacturer.",
                           self.part.body_ref, "minimum",
                           side_effects=["changes bend allowance and flat pattern", "may change part strength/weight"])
            return [self._mk(Status.FAIL,
                             f"Sheet thickness {fmt_len(t)} is outside the supported range {req}{self._scope()}.",
                             "Change the sheet metal rule thickness to a supported value or choose another material/manufacturer.",
                             t, req, self.part.body_ref, required_mm=tgt, corrections=[c])]
        return [self._mk(Status.PASS, f"Sheet thickness {t:.3f} mm is within {req}.", measured=t, required=req,
                         ref=self.part.body_ref)]

    def _thickness_in_stock(self, rule, p):
        t = self.part.thickness_mm
        if t is None:
            return [self._review(self.part.unsupported.get("thickness", "sheet thickness could not be determined."))]
        if self.material is None:
            return [self._review("material not matched; stock thicknesses depend on material.")]
        row, st = find_thickness_row(self.material, t, self.tol)
        if st == "no_table":
            return [self._review("no stock-thickness table for this material.")]
        listed = sorted(r["thickness_mm"] for r in self.material["thickness_specs"] if r.get("bendable", True))
        if st == "ambiguous":
            return [self._review("thickness matches more than one listed stock thickness.", self.part.body_ref)]
        if st == "none":
            near = sorted(listed, key=lambda x: abs(x - t))[:2]
            c = Correction("change_thickness", rule["id"], "sheet_thickness", "set", t, near[0],
                           f"Use a listed stock thickness, e.g. {', '.join(fmt_len(x) for x in near)}.",
                           self.part.body_ref, "minimum", alternatives=near[1:],
                           side_effects=["changes bend allowance and flat pattern"]) if near else None
            return [self._mk(Status.NEEDS_REVIEW,
                             f"Thickness {fmt_len(t)} is not one of the listed stock thicknesses for {self.material['name']} "
                             f"(within {self.tol:g} mm). The published list may not be exhaustive.",
                             "Confirm availability with the manufacturer or switch to a listed thickness: "
                             + ", ".join(fmt_len(x) for x in listed) + ".",
                             measured=t, required="a listed stock thickness", ref=self.part.body_ref,
                             corrections=[c] if c else [])]
        if not row.get("bendable", True):
            near = [x for x in listed if x < t][-1:] or listed[:1]
            c = Correction("change_thickness", rule["id"], "sheet_thickness", "set", t, near[0] if near else None,
                           "Choose a thickness the manufacturer can bend.", self.part.body_ref, "minimum",
                           alternatives=listed, side_effects=["changes bend allowance and flat pattern"]) if near else None
            return [self._mk(Status.FAIL,
                             f"{self.material['name']} at {fmt_len(t)} is listed as not available for bending by {self.mfr}.",
                             "Use a thickness the manufacturer can bend: " + ", ".join(fmt_len(x) for x in listed) + ".",
                             t, "bendable thickness", self.part.body_ref, corrections=[c] if c else [])]
        return [self._mk(Status.PASS, f"{fmt_len(t)} matches listed stock thickness {fmt_len(row['thickness_mm'])} for {self.material['name']}.",
                         measured=t, required="a listed stock thickness", ref=self.part.body_ref)]

    def _min_bend_radius(self, rule, p):
        def corr(name, b, v, req):
            return Correction("set_bend_radius", rule["id"], "inner_bend_radius", "increase", v, req,
                              f"Increase the inner bend radius to at least {fmt_len(req)}.", b.ref, "minimum",
                              side_effects=["changes bend allowance and flat pattern"])
        return self._min_items(p, [(f"Bend #{i}", b) for i, b in enumerate(self.part.bends, 1)],
                               lambda b: b.inner_radius_mm, "Bend", "bends",
                               "Increase the inner bend radius by at least {delta} (to {req}).", corr)

    def _bend_radius_match(self, rule, p):
        if "bends" in self.part.unsupported:
            return [self._review(f"Bend extraction unsupported: {self.part.unsupported['bends']}")]
        cands, err = self._spec_candidates(p)
        if err:
            return [self._review(err)]
        tol = p.get("tolerance_mm", 0.01)
        out = []
        for i, b in enumerate(self.part.bends, 1):
            v = b.inner_radius_mm
            if v is None:
                out.append(self._review(f"Bend #{i} radius could not be measured.", b.ref))
                continue
            hits = [abs(v - c) <= tol + EPS for c in cands]
            req_txt = "= " + " or ".join(f"{c:.3f} mm" for c in sorted(set(round(c, 4) for c in cands)))
            if all(hits):
                out.append(self._mk(Status.PASS, f"Bend #{i} inner radius {fmt_len(v)} matches the manufacturer's fixed radius{self._scope()}.",
                                    measured=v, required=req_txt, ref=b.ref, required_mm=cands[0], label=f"Bend #{i}"))
            elif any(hits):
                out.append(self._mk(Status.NEEDS_REVIEW,
                                    f"Bend #{i} radius {fmt_len(v)} matches one of the manufacturer's conflicting published values ({req_txt}).",
                                    "Ask the manufacturer which radius applies.", measured=v, required=req_txt, ref=b.ref, label=f"Bend #{i}"))
            else:
                tgt = cands[0]
                alts = sorted(set(round(c, 4) for c in cands) - {round(tgt, 4)})
                c = Correction("set_bend_radius", rule["id"], "inner_bend_radius", "set", v, tgt,
                               f"Set the inner bend radius to {fmt_len(tgt)} (the manufacturer's fixed radius{self._scope()}).",
                               b.ref, "exact", alternatives=alts,
                               side_effects=["changes bend allowance, K-factor settings and flat pattern",
                                             "use the manufacturer's sheet metal rule (radius + K-factor) so flat lengths stay correct"])
                out.append(self._mk(Status.FAIL,
                                    f"Bend #{i} inner radius is {fmt_len(v)}; {self.mfr} forms a fixed radius of {fmt_len(tgt)}{self._scope()} and does not offer custom bend radii.",
                                    f"Model the bend with an inner radius of {fmt_len(tgt)} (change of {fmt_len(tgt - v)}); otherwise the formed part will not match your model.",
                                    measured=v, required=req_txt, ref=b.ref, required_mm=tgt, corrections=[c], label=f"Bend #{i}"))
        return out

    def _flange_items(self, rule):
        ap = rule.get("applies_to") or {}
        rng = ap.get("bend_angle_deg")
        items = []
        for i, f in enumerate(self.part.flanges, 1):
            if not f.is_terminal:
                continue
            items.append((f.ref.label if f.ref and f.ref.label else f"Flange #{i}", f))
        return items, rng

    def _min_flange_length(self, rule, p):
        measure = p.get("measure", "tangent")
        items, rng = self._flange_items(rule)
        if "flanges" in self.part.unsupported:
            return [self._review(f"Flange extraction unsupported: {self.part.unsupported['flanges']}")]
        out, usable = [], []
        for name, f in items:
            if rng:
                if f.bend_angle_deg is None:
                    out.append(self._review(f"{name}: bend angle unknown; requirement is published for {rng.get('min', 0):g}-{rng.get('max', 180):g} deg bends only.", f.ref))
                    continue
                if not (rng.get("min", 0) - 0.5 <= f.bend_angle_deg <= rng.get("max", 180) + 0.5):
                    out.append(self._review(f"{name}: bend angle {f.bend_angle_deg:.1f} deg is outside the published range "
                                            f"({rng.get('min', 0):g}-{rng.get('max', 180):g} deg); no verified requirement for this angle.", f.ref))
                    continue
            usable.append((name, f))

        def get(f):
            if measure == "apex":
                return f.length_apex_mm
            return f.length_mm

        def corr(name, f, v, req):
            return Correction("increase_flange_length", rule["id"], "flange_length" + (" (from apex)" if measure == "apex" else ""),
                              "increase", v, req,
                              f"Increase the flange length{' measured from the bend apex' if measure == 'apex' else ''} to at least {fmt_len(req)}.",
                              f.ref, "minimum",
                              side_effects=["changes flat-pattern length", "may interact with adjacent flanges/features"])
        meas_note = " (measured from the bend apex)" if measure == "apex" else ""
        res = self._min_items(p, usable, get, "Flange", None,
                              "Lengthen the flange by at least {delta} (to {req})" + meas_note + ".", corr)
        for r in res:
            if r.status == Status.NEEDS_REVIEW and "could not be measured" in r.explanation and measure == "apex":
                r.explanation += " (apex length needs the bend angle and radius)"
        return out + res

    def _feature_items(self, rule):
        kinds = (rule.get("applies_to") or {}).get("feature_kinds")
        lab = lambda f, default: f.ref.label if f.ref and f.ref.label else default      # prefer the CAD label (matches the UI)
        items = [(lab(h, f"Hole #{i}"), h) for i, h in enumerate(self.part.holes, 1)]
        items += [(lab(c, f"{c.cutout_kind.capitalize()} cutout #{i}"), c) for i, c in enumerate(self.part.cutouts, 1)]
        if kinds:
            items = [(n, f) for n, f in items if f.kind in kinds]
        return items

    def _min_hole_diameter(self, rule, p):
        def corr(name, f, v, req):
            return Correction("increase_feature_size", rule["id"], "feature_min_dimension", "increase", v, req,
                              f"Increase the smallest dimension of {name} to at least {fmt_len(req)}.", f.ref, "minimum",
                              side_effects=["changes the cut feature and may need spacing re-check"])
        return self._min_items(p, self._feature_items(rule), lambda f: f.min_dimension_mm, "Feature", "holes",
                               "Increase the smallest dimension of {name} by at least {delta} (to {req}).", corr)

    def _min_hole_edge_distance(self, rule, p):
        def corr(name, f, v, req):
            return Correction("move_feature", rule["id"], "distance_to_edge", "move_away", v, req,
                              f"Move {name} so its edge is at least {fmt_len(req)} from the nearest sheet edge.", f.ref, "minimum",
                              side_effects=["may conflict with other features or mating parts"])
        return self._min_items(p, self._feature_items(rule), lambda f: f.dist_to_edge_mm, "Feature",
                               "hole_edge_distance", "Move {name} at least {delta} further from the nearest edge (to {req}).", corr)

    def _min_hole_bend_distance(self, rule, p):
        measure = p.get("measure", "tangent")
        items = [(n, f) for n, f in self._feature_items(rule) if f.has_adjacent_bend is not False]
        if measure != "centerline":
            def corr(name, f, v, req):
                return Correction("move_feature", rule["id"], "distance_to_bend", "move_away", v, req,
                                  f"Move {name} so its edge is at least {fmt_len(req)} from the bend.", f.ref, "minimum",
                                  side_effects=["may conflict with other features"])
            return self._min_items(p, items, lambda f: f.dist_to_bend_mm, "Feature", "hole_bend_distance",
                                   "Move {name} at least {delta} further from the bend (to {req}).", corr)
        # requirement is measured to the bend CENTERLINE; we measure to the tangent line (a lower bound)
        # and bound the tangent->centerline offset from above by (R_inner + t) * angle / 2.
        if "hole_bend_distance" in self.part.unsupported:
            return [self._review(f"extraction unsupported: {self.part.unsupported['hole_bend_distance']}")]
        cands, err = self._min_candidates(p)
        if err:
            return [self._review(err)]
        lo_req, hi_req = min(cands), max(cands)
        out = []
        for name, f in items:
            ref, kind = f.ref, f.kind
            if getattr(f, "certain", True) is False:
                out.append(self._review(f"{name}: classification uncertain ({f.uncertainty_reason or 'unknown shape'}).", ref, kind))
                continue
            d, zone = f.dist_to_bend_mm, f.bend_zone_max_mm
            if d is None:
                out.append(self._review(f"{name} could not be measured to the bend.", ref, kind))
                continue
            req_txt = self._req_text(cands) + " from bend centerline"
            if d >= hi_req - EPS:
                out.append(self._mk(Status.PASS,
                                    f"{name} is at least {fmt_len(d)} from the bend tangent line, so its distance to the bend centerline is >= {fmt_len(hi_req)}{self._scope()}.",
                                    measured=d, required=req_txt, ref=ref, required_mm=hi_req, feature_kind=kind, label=name))
            elif zone is not None and d + zone < lo_req - EPS:
                short = hi_req - (d + zone)
                c = Correction("move_feature", rule["id"], "distance_to_bend_centerline", "move_away", d + zone, hi_req,
                               f"Move {name} at least {fmt_len(short)} further from the bend.", ref, "minimum",
                               side_effects=["may conflict with other features"])
                out.append(self._mk(Status.FAIL,
                                    f"{name} is at most {fmt_len(d + zone)} from the bend centerline; {self.mfr} requires at least {fmt_len(hi_req)}{self._scope()} (cut features closer than half the die width distort when bent).",
                                    f"Move {name} at least {fmt_len(short)} further from the bend.",
                                    measured=d + zone, required=req_txt, ref=ref, required_mm=hi_req, corrections=[c], feature_kind=kind, label=name))
            else:
                bound = "unknown" if zone is None else fmt_len(d + zone)
                out.append(self._mk(Status.NEEDS_REVIEW,
                                    f"{name}: distance to the bend tangent line is {fmt_len(d)}; the distance to the bend centerline (required >= {fmt_len(hi_req)}) lies between {fmt_len(d)} and {bound}, so compliance cannot be confirmed.",
                                    "Measure to the bend centerline on the flat pattern, or move the feature further from the bend.",
                                    measured=d, required=req_txt, ref=ref, required_mm=hi_req, feature_kind=kind, label=name))
        return out

    def _max_bend_length(self, rule, p):
        if "bends" in self.part.unsupported:
            return [self._review(f"Bend extraction unsupported: {self.part.unsupported['bends']}")]
        cands, err = self._spec_candidates(p) if "spec" in p else ([p["max_mm"]], None)
        if err:
            return [self._review(err)]
        out = []
        for i, b in enumerate(self.part.bends, 1):
            v = b.length_mm
            if v is None:
                out.append(self._review(f"Bend #{i} length could not be measured.", b.ref))
                continue
            lo, hi = min(cands), max(cands)
            req_txt = "<= " + " or ".join(f"{c:.1f} mm" for c in sorted(set(round(c, 2) for c in cands)))
            if v <= lo + EPS:
                out.append(self._mk(Status.PASS, f"Bend #{i} length {fmt_len(v)} is within the maximum {fmt_len(lo)}{self._scope()}.",
                                    measured=v, required=req_txt, ref=b.ref, required_mm=lo, label=f"Bend #{i}"))
            elif v > hi + EPS:
                c = Correction("resize_part", rule["id"], "bend_length", "decrease", v, lo,
                               f"Shorten bend #{i} to at most {fmt_len(lo)} or split it.", b.ref, "minimum")
                out.append(self._mk(Status.FAIL, f"Bend #{i} is {fmt_len(v)} long; {self.mfr} allows at most {fmt_len(lo)}{self._scope()}.",
                                    f"Shorten the bend by at least {fmt_len(v - lo)} or split the part.", measured=v, required=req_txt,
                                    ref=b.ref, required_mm=lo, corrections=[c], label=f"Bend #{i}"))
            else:
                out.append(self._mk(Status.NEEDS_REVIEW, f"Bend #{i} length {fmt_len(v)} lies between conflicting published maxima ({req_txt}).",
                                    "Ask the manufacturer which maximum applies.", measured=v, required=req_txt, ref=b.ref, label=f"Bend #{i}"))
        return out

    def _pair_candidates(self, p, kind):
        if "spec" in p:
            c, err = self._spec_candidates(p)
            return (c[0], err) if c else (None, err)
        if kind == "max":
            return [p.get("max_long_mm"), p.get("max_short_mm")], None
        return [p.get("min_long_mm"), p.get("min_short_mm")], None

    def _max_part_dimensions(self, rule, p):
        d = self.part.flat_dimensions_mm
        if d is None:
            return [self._review(self.part.unsupported.get("flat_dimensions", "flat pattern dimensions unavailable."), self.part.body_ref)]
        pair, err = self._pair_candidates(p, "max")
        if err:
            return [self._review(err, self.part.body_ref)]
        ml, ms = pair
        long_, short = sorted(d, reverse=True)[:2]
        bad = (ml is not None and long_ > ml + EPS) or (ms is not None and short > ms + EPS)
        req = f"<= {ml if ml is not None else '-'} x {ms if ms is not None else '-'} mm"
        if bad:
            c = Correction("resize_part", rule["id"], "flat_size", "decrease", long_, ml,
                           "Reduce the flat pattern size or split the part.", self.part.body_ref, "minimum")
            return [self._mk(Status.FAIL, f"Flat size {long_:.1f} x {short:.1f} mm exceeds the maximum {req}{self._scope()}.",
                             "Reduce the flat pattern size or split the part.", long_, req, self.part.body_ref,
                             required_mm=ml, corrections=[c])]
        return [self._mk(Status.PASS, f"Flat size {long_:.1f} x {short:.1f} mm is within {req}{self._scope()}.",
                         measured=long_, required=req, ref=self.part.body_ref, required_mm=ml)]

    def _min_part_dimensions(self, rule, p):
        d = self.part.flat_dimensions_mm
        if d is None:
            return [self._review(self.part.unsupported.get("flat_dimensions", "flat pattern dimensions unavailable."), self.part.body_ref)]
        pair, err = self._pair_candidates(p, "min")
        if err:
            return [self._review(err, self.part.body_ref)]
        a, b = pair  # published as (short, long)? treat as unordered: smaller is the short minimum
        ms, ml = sorted([x for x in (a, b) if x is not None])[:2] if a is not None and b is not None else (a, b)
        long_, short = sorted(d, reverse=True)[:2]
        bad = (ml is not None and long_ < ml - EPS) or (ms is not None and short < ms - EPS)
        req = f">= {ml:.1f} x {ms:.1f} mm"
        if bad:
            c = Correction("resize_part", rule["id"], "flat_size", "increase", short, ms,
                           "Increase the flat pattern size or combine with another part.", self.part.body_ref, "minimum")
            return [self._mk(Status.FAIL, f"Flat size {long_:.1f} x {short:.1f} mm is below the minimum {req}{self._scope()}.",
                             "Increase the part size above the manufacturer minimum.", short, req, self.part.body_ref,
                             required_mm=ms, corrections=[c])]
        return [self._mk(Status.PASS, f"Flat size {long_:.1f} x {short:.1f} mm meets the minimum {req}{self._scope()}.",
                         measured=short, required=req, ref=self.part.body_ref, required_mm=ms)]
