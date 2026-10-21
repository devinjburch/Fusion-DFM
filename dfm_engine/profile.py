"""Manufacturer profile loading and validation (JSON -> validated dict).

schema_version 1 (Phase 1) and 2 (Phase 2) are both accepted. v2 adds per-thickness specification
tables, spec-driven rules, rule strength (requirement/advisory), tolerances/notes and research status.
"""
from __future__ import annotations
import json
import os

BASE_MIN = ("min_mm", "min_ratio_to_thickness", "spec", "factor", "measure")
RULE_TYPES = {
    "thickness_range": ("min_mm", "max_mm"),
    "thickness_in_stock": (),
    "min_bend_radius": BASE_MIN,
    "bend_radius_match": ("spec", "factor", "tolerance_mm"),
    "min_flange_length": BASE_MIN,
    "min_hole_edge_distance": BASE_MIN,
    "min_hole_bend_distance": BASE_MIN,
    "min_hole_diameter": BASE_MIN,
    "max_bend_length": ("max_mm", "spec", "factor"),
    "max_part_dimensions": ("max_long_mm", "max_short_mm", "spec"),
    "min_part_dimensions": ("min_long_mm", "min_short_mm", "spec"),
}
SPEC_FIELDS = {
    "bend_radius_mm", "k_factor", "bend_deduction_mm", "die_width_mm", "min_flange_length_mm",
    "min_flange_flat_pattern_mm", "min_corner_relief_mm", "bend_relief_depth_mm", "max_bend_length_mm",
}
SPEC_PAIR_FIELDS = {"min_flat_size_mm", "max_flat_size_mm"}
MEASURES = {"apex", "tangent", "centerline"}
PROFILE_STATUS = {"verified", "partially_verified", "unverified", "demo"}
SEVERITIES = {"ERROR", "WARNING", "INFO"}
STRENGTHS = {"requirement", "advisory"}
RESEARCH_STATUS = {"verified", "partial", "blocked", "not_started"}
SCHEMA_VERSIONS = {1, 2}
DEFAULT_TOLERANCE_MM = 0.05
DEFAULT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "manufacturers")


class ProfileError(ValueError):
    pass


def _req(cond: bool, msg: str):
    if not cond:
        raise ProfileError(msg)


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _check_source(where: str, src, needed: bool):
    src = src or {}
    if needed:
        _req(isinstance(src, dict) and src.get("url", "").startswith("http") and src.get("date_verified"),
             f"{where}: needs source.url (http...) and source.date_verified")


def validate(p: dict) -> dict:
    _req(isinstance(p, dict), "profile must be an object")
    for k in ("schema_version", "manufacturer", "profile_status", "processes"):
        _req(k in p, f"missing '{k}'")
    _req(p["schema_version"] in SCHEMA_VERSIONS, f"unsupported schema_version {p['schema_version']!r}")
    _req(p["profile_status"] in PROFILE_STATUS, f"bad profile_status {p['profile_status']!r}")
    m = p["manufacturer"]
    _req(isinstance(m, dict) and m.get("id") and m.get("name"), "manufacturer needs id and name")
    demo = p["profile_status"] == "demo"
    v2 = p["schema_version"] >= 2
    if "research" in p:
        _req(p["research"].get("status") in RESEARCH_STATUS, "research.status invalid")
    _req(isinstance(p["processes"], list) and p["processes"], "processes must be a non-empty list")
    warnings = []
    seen_p = set()
    for proc in p["processes"]:
        pid = proc.get("id")
        _req(pid and pid not in seen_p, f"process id missing/duplicate: {pid!r}")
        seen_p.add(pid)
        tol = proc.get("thickness_match_tolerance_mm", DEFAULT_TOLERANCE_MM)
        _req(_num(tol) and 0 <= tol <= 1, f"{pid}: thickness_match_tolerance_mm must be 0..1")
        mat_ids, spec_fields_by_mat = set(), {}
        for mat in proc.get("materials", []):
            _req(mat.get("id") and mat.get("name"), f"{pid}: material needs id and name")
            _req(mat["id"] not in mat_ids, f"{pid}: duplicate material {mat['id']}")
            mat_ids.add(mat["id"])
            spec_fields_by_mat[mat["id"]] = _validate_specs(pid, mat, demo)
        for t in proc.get("tolerances", []):
            _req(t.get("id") and t.get("text"), f"{pid}: tolerance needs id and text")
            if not demo:
                _check_source(f"{pid}: tolerance {t.get('id')}", t.get("source"), True)
        for rs in proc.get("restrictions", []):
            _req(rs.get("id") and rs.get("text"), f"{pid}: restriction needs id and text")
            if not demo:
                _check_source(f"{pid}: restriction {rs.get('id')}", rs.get("source"), True)
        seen_r = set()
        for r in proc.get("rules", []):
            rid = r.get("id")
            _req(rid and rid not in seen_r, f"{pid}: rule id missing/duplicate: {rid!r}")
            seen_r.add(rid)
            _validate_rule(pid, r, mat_ids, spec_fields_by_mat, demo, v2)
        warnings += _scope_conflicts(pid, proc.get("rules", []), mat_ids)
    p["_warnings"] = warnings
    return p


def _validate_specs(pid, mat, demo):
    fields = set()
    seen = set()
    for row in mat.get("thickness_specs", []):
        where = f"{pid}/{mat['id']}"
        t = row.get("thickness_mm")
        _req(_num(t) and t > 0, f"{where}: thickness_mm must be > 0")
        _req(round(t, 4) not in seen, f"{where}: duplicate thickness {t}")
        seen.add(round(t, 4))
        _req(isinstance(row.get("bendable", True), bool), f"{where}/{t}: bendable must be boolean")
        if not demo:
            _check_source(f"{where}/{t}", row.get("source"), True)
        for name, v in (row.get("values") or {}).items():
            _req(name in SPEC_FIELDS or name in SPEC_PAIR_FIELDS, f"{where}/{t}: unknown spec field {name!r}")
            if name in SPEC_PAIR_FIELDS:
                _req(isinstance(v, list) and len(v) == 2 and all(_num(x) and x > 0 for x in v),
                     f"{where}/{t}: {name} must be [a, b] positive numbers")
            else:
                _req(_num(v) and v >= 0, f"{where}/{t}: {name} must be a non-negative number")
            fields.add(name)
        for name, cands in (row.get("conflicts") or {}).items():
            _req(name in (row.get("values") or {}) and name in SPEC_FIELDS, f"{where}/{t}: conflict on unlisted field {name!r}")
            _req(isinstance(cands, list) and len(cands) >= 2 and all(_num(c.get("value")) for c in cands),
                 f"{where}/{t}: conflicts.{name} needs >= 2 candidates with numeric values")
            for c in cands:
                if not demo:
                    _check_source(f"{where}/{t} conflict {name}", c.get("source"), True)
    return fields


def _validate_rule(pid, r, mat_ids, spec_fields_by_mat, demo, v2):
    rid = r["id"]
    t = r.get("type")
    _req(t in RULE_TYPES, f"{rid}: unknown rule type {t!r}")
    _req(isinstance(r.get("enabled"), bool) and isinstance(r.get("verified"), bool),
         f"{rid}: 'enabled' and 'verified' must be booleans")
    _req(r.get("severity", "ERROR") in SEVERITIES, f"{rid}: bad severity")
    _req(r.get("strength", "requirement") in STRENGTHS, f"{rid}: bad strength")
    params = r.get("parameters") or {}
    for k, v in params.items():
        _req(k in RULE_TYPES[t], f"{rid}: parameter {k!r} not valid for {t}")
        if k == "spec":
            _req(v in SPEC_FIELDS or v in SPEC_PAIR_FIELDS, f"{rid}: unknown spec {v!r}")
        elif k == "measure":
            _req(v in MEASURES, f"{rid}: bad measure {v!r}")
        else:
            _req(_num(v) and v >= 0, f"{rid}: parameter {k!r} must be a non-negative number")
    ap = r.get("applies_to") or {}
    for m in ap.get("materials", []):
        _req(m in mat_ids, f"{rid}: applies_to unknown material {m!r}")
    ba = ap.get("bend_angle_deg")
    if ba is not None:
        _req(isinstance(ba, dict) and _num(ba.get("min", 0)) and _num(ba.get("max", 180)) and ba.get("min", 0) <= ba.get("max", 180),
             f"{rid}: applies_to.bend_angle_deg needs min<=max")
    for fk in ap.get("feature_kinds", []):
        _req(fk in ("hole", "slot", "rect", "irregular", "unknown"), f"{rid}: bad feature kind {fk!r}")
    if not r["enabled"]:
        if v2:
            _req(r.get("limitations"), f"{rid}: a disabled rule must say why in 'limitations'")
        return
    if t != "thickness_in_stock":
        _req(params, f"{rid}: enabled rule has no parameters")
    if t == "thickness_range":
        _req("min_mm" in params and "max_mm" in params, f"{rid}: needs min_mm and max_mm")
    if "spec" in params:
        mats = ap.get("materials") or list(mat_ids)
        _req(any(params["spec"] in spec_fields_by_mat.get(m, ()) for m in mats),
             f"{rid}: spec {params['spec']!r} is not defined for any applicable material")
    if t == "thickness_in_stock":
        mats = ap.get("materials") or list(mat_ids)
        _req(any(spec_fields_by_mat.get(m) is not None and m in spec_fields_by_mat for m in mats) and mats,
             f"{rid}: needs materials")
    if not demo:
        _req(r["verified"], f"{rid}: enabled rule in a non-demo profile must be verified")
        _check_source(rid, r.get("source"), True)


def _scope_conflicts(pid, rules, mat_ids):
    """Warn when two enabled requirement rules of one type overlap in material scope and differ in value."""
    out = []
    by_type = {}
    for r in rules:
        if r.get("enabled") and r.get("strength", "requirement") == "requirement":
            by_type.setdefault(r["type"], []).append(r)
    for t, rs in by_type.items():
        for i, a in enumerate(rs):
            for b in rs[i + 1:]:
                ma = set((a.get("applies_to") or {}).get("materials") or mat_ids)
                mb = set((b.get("applies_to") or {}).get("materials") or mat_ids)
                if ma & mb and (a.get("parameters") != b.get("parameters")) and \
                        _ranges_overlap((a.get("applies_to") or {}).get("thickness_mm"), (b.get("applies_to") or {}).get("thickness_mm")):
                    out.append(f"{pid}: rules {a['id']} and {b['id']} ({t}) overlap in scope with different parameters")
    return out


def _ranges_overlap(a, b):
    if not a or not b:
        return True
    return a.get("min", 0) <= b.get("max", float("inf")) and b.get("min", 0) <= a.get("max", float("inf"))


def load_profile_dict(d: dict) -> dict:
    return validate(d)


def load_profile(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        try:
            d = json.load(f)
        except json.JSONDecodeError as e:
            raise ProfileError(f"{path}: invalid JSON: {e}") from e
    try:
        return validate(d)
    except ProfileError as e:
        raise ProfileError(f"{os.path.basename(path)}: {e}") from e


def list_profiles(directory: str = DEFAULT_DIR):
    """Return (profiles, errors). One broken file never hides the others."""
    profiles, errors = [], []
    for fn in sorted(os.listdir(directory)):
        if fn.endswith(".json"):
            try:
                profiles.append(load_profile(os.path.join(directory, fn)))
            except (ProfileError, OSError) as e:
                errors.append(str(e))
    return profiles, errors
