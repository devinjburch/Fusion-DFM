"""Pure-Python message payload builders for the palette (no adsk import; unit-testable)."""
from __future__ import annotations
import os

from dfm_engine import evaluate, list_profiles
from dfm_engine.compare import Target, compare
from dfm_engine.reporting import build_context, write_reports


def profiles_payload(directory=None):
    profiles, errors = list_profiles(directory) if directory else list_profiles()
    out = []
    for p in profiles:
        out.append({"id": p["manufacturer"]["id"], "name": p["manufacturer"]["name"],
                    "status": p["profile_status"], "description": p.get("description", ""),
                    "processes": [{"id": pr["id"], "name": pr.get("name", pr["id"]),
                                   "materials": [{"id": m["id"], "name": m["name"]} for m in pr.get("materials", [])]}
                                  for pr in p["processes"]]})
    names = sorted({m["name"] for p in profiles if p["profile_status"] != "demo"
                    for pr in p["processes"] for m in pr.get("materials", [])})
    return {"profiles": out, "errors": errors, "material_names": names}


def _flatten_report(d):
    """Replace GeometryRef objects by plain token/label fields for JSON/JS."""
    for r in d["results"]:
        ref = r.pop("geometry_ref")
        r["token"] = ref["token"] if ref else None
        r["ref_label"] = ref["label"] if ref else ""
    return d


def compare_payload(parts, warnings, request, directory=None):
    """request: {"manufacturers": [{"id", "process_id"?, "material_id"?}, ...]} (default: every profile)."""
    profiles, _ = list_profiles(directory) if directory else list_profiles()
    wanted = request.get("manufacturers") or [{"id": p["manufacturer"]["id"]} for p in profiles]
    name = request.get("material_name") or None
    targets = [Target(w["id"], w.get("process_id") or None, w.get("material_id") or None, name) for w in wanted]
    comp = compare(parts, profiles, targets).to_dict()
    for e in comp["entries"]:
        for rep in e["reports"]:
            _flatten_report(rep)
    summaries = [part_summary(p, warnings) for p in parts]
    return {"comparison": comp, "parts": summaries}


def export_payload(parts, warnings, request, model_name="", document="", directory=None, out_dir=None):
    """Build the comparison and write HTML + CSV reports. Returns {paths}."""
    pl = compare_payload(parts, warnings, request, directory)
    ctx = build_context(pl["comparison"], pl["parts"], model_name, document)
    out_dir = out_dir or os.path.join(os.path.expanduser("~"), "FusionDFM", "reports")
    paths = write_reports(ctx, out_dir, model_name or (parts[0].name if parts else "report"))
    return {"paths": paths}


def part_summary(part, warnings):
    r = lambda v: None if v is None else round(v, 3)
    return {"name": part.name, "material": part.material_name, "thickness_mm": r(part.thickness_mm),
            "thickness_source": part.thickness_source,
            "flat_dimensions_mm": None if part.flat_dimensions_mm is None else [r(x) for x in part.flat_dimensions_mm],
            "folded_dimensions_mm": None if part.folded_dimensions_mm is None else [r(x) for x in part.folded_dimensions_mm],
            "counts": {"holes": len(part.holes), "cutouts": len(part.cutouts), "bends": len(part.bends), "flanges": len(part.flanges)},
            "component_path": part.component_path, "instance_count": part.instance_count,
            "unsupported": part.unsupported, "warnings": warnings}


def results_payload(part, warnings, request, directory=None):
    profiles, _ = list_profiles(directory) if directory else list_profiles()
    prof = next((p for p in profiles if p["manufacturer"]["id"] == request.get("manufacturer_id")), None)
    if prof is None:
        raise ValueError("Unknown manufacturer")
    rep = evaluate(part, prof, request["process_id"], request.get("material_id") or None)
    d = _flatten_report(rep.to_dict())
    d["part"] = part_summary(part, warnings)
    return d
