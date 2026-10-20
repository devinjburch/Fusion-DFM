"""Pure-Python message payload builders for the palette (no adsk import; unit-testable)."""
from __future__ import annotations
from dfm_engine import evaluate, list_profiles


def profiles_payload(directory=None):
    profiles, errors = list_profiles(directory) if directory else list_profiles()
    out = []
    for p in profiles:
        out.append({"id": p["manufacturer"]["id"], "name": p["manufacturer"]["name"],
                    "status": p["profile_status"], "description": p.get("description", ""),
                    "processes": [{"id": pr["id"], "name": pr.get("name", pr["id"]),
                                   "materials": [{"id": m["id"], "name": m["name"]} for m in pr.get("materials", [])]}
                                  for pr in p["processes"]]})
    return {"profiles": out, "errors": errors}


def part_summary(part, warnings):
    r = lambda v: None if v is None else round(v, 3)
    return {"name": part.name, "material": part.material_name, "thickness_mm": r(part.thickness_mm),
            "thickness_source": part.thickness_source,
            "flat_dimensions_mm": None if part.flat_dimensions_mm is None else [r(x) for x in part.flat_dimensions_mm],
            "folded_dimensions_mm": None if part.folded_dimensions_mm is None else [r(x) for x in part.folded_dimensions_mm],
            "counts": {"holes": len(part.holes), "bends": len(part.bends), "flanges": len(part.flanges)},
            "unsupported": part.unsupported, "warnings": warnings}


def results_payload(part, warnings, request, directory=None):
    profiles, _ = list_profiles(directory) if directory else list_profiles()
    prof = next((p for p in profiles if p["manufacturer"]["id"] == request.get("manufacturer_id")), None)
    if prof is None:
        raise ValueError("Unknown manufacturer")
    rep = evaluate(part, prof, request["process_id"], request.get("material_id") or None)
    d = rep.to_dict()
    for r in d["results"]:  # flatten refs for JSON/JS
        ref = r.pop("geometry_ref")
        r["token"] = ref["token"] if ref else None
        r["ref_label"] = ref["label"] if ref else ""
    d["part"] = part_summary(part, warnings)
    return d
