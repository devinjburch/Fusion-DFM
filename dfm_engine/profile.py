"""Manufacturer profile loading and validation (JSON -> validated dict)."""
from __future__ import annotations
import json
import os

RULE_TYPES = {
    "thickness_range": ("min_mm", "max_mm"),
    "min_bend_radius": ("min_mm", "min_ratio_to_thickness"),
    "min_flange_length": ("min_mm", "min_ratio_to_thickness"),
    "min_hole_edge_distance": ("min_mm", "min_ratio_to_thickness"),
    "min_hole_bend_distance": ("min_mm", "min_ratio_to_thickness"),
    "min_hole_diameter": ("min_mm", "min_ratio_to_thickness"),
    "max_part_dimensions": ("max_long_mm", "max_short_mm"),
}
PROFILE_STATUS = {"verified", "partially_verified", "unverified", "demo"}
SEVERITIES = {"ERROR", "WARNING", "INFO"}
DEFAULT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "manufacturers")


class ProfileError(ValueError):
    pass


def _req(cond: bool, msg: str):
    if not cond:
        raise ProfileError(msg)


def validate(p: dict) -> dict:
    _req(isinstance(p, dict), "profile must be an object")
    for k in ("schema_version", "manufacturer", "profile_status", "processes"):
        _req(k in p, f"missing '{k}'")
    _req(p["profile_status"] in PROFILE_STATUS, f"bad profile_status {p['profile_status']!r}")
    m = p["manufacturer"]
    _req(isinstance(m, dict) and m.get("id") and m.get("name"), "manufacturer needs id and name")
    demo = p["profile_status"] == "demo"
    _req(isinstance(p["processes"], list) and p["processes"], "processes must be a non-empty list")
    seen_p = set()
    for proc in p["processes"]:
        pid = proc.get("id")
        _req(pid and pid not in seen_p, f"process id missing/duplicate: {pid!r}")
        seen_p.add(pid)
        mats = proc.get("materials", [])
        mat_ids = set()
        for mat in mats:
            _req(mat.get("id") and mat.get("name"), f"{pid}: material needs id and name")
            _req(mat["id"] not in mat_ids, f"{pid}: duplicate material {mat['id']}")
            mat_ids.add(mat["id"])
        seen_r = set()
        for r in proc.get("rules", []):
            rid = r.get("id")
            _req(rid and rid not in seen_r, f"{pid}: rule id missing/duplicate: {rid!r}")
            seen_r.add(rid)
            _validate_rule(pid, r, mat_ids, demo)
    return p


def _validate_rule(pid: str, r: dict, mat_ids: set, demo: bool):
    rid = r["id"]
    t = r.get("type")
    _req(t in RULE_TYPES, f"{rid}: unknown rule type {t!r}")
    _req(isinstance(r.get("enabled"), bool) and isinstance(r.get("verified"), bool),
         f"{rid}: 'enabled' and 'verified' must be booleans")
    _req(r.get("severity", "ERROR") in SEVERITIES, f"{rid}: bad severity")
    params = r.get("parameters") or {}
    for k, v in params.items():
        _req(k in RULE_TYPES[t], f"{rid}: parameter {k!r} not valid for {t}")
        _req(isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0,
             f"{rid}: parameter {k!r} must be a non-negative number")
    for m in (r.get("applies_to") or {}).get("materials", []):
        _req(m in mat_ids, f"{rid}: applies_to unknown material {m!r}")
    if r["enabled"]:
        _req(params, f"{rid}: enabled rule has no parameters")
        if t == "thickness_range":
            _req("min_mm" in params and "max_mm" in params, f"{rid}: needs min_mm and max_mm")
        if not demo:
            _req(r["verified"], f"{rid}: enabled rule in a non-demo profile must be verified")
            src = r.get("source") or {}
            _req(src.get("url") and src.get("date_verified"),
                 f"{rid}: verified rule needs source.url and source.date_verified")


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
