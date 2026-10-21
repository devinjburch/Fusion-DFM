"""Phase 1 behaviour must keep working unchanged."""
import json
import os
import pytest
from dfm_engine import (PartModel, Hole, Bend, Flange, GeometryRef, Status, Severity, load_profile, evaluate, list_profiles)
from dfm_engine.engine import match_material
from fusion_addin import bridge

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "phase1_sendcutsend.json")
PHASE1_RESULT_KEYS = {"rule_id", "rule_type", "status", "severity", "explanation", "recommendation", "measured", "required",
                      "unit", "geometry_ref", "source_url", "date_verified", "manufacturer", "demo"}
PHASE1_REPORT_KEYS = {"manufacturer_id", "manufacturer_name", "process_id", "material_id", "part_name", "overall", "demo", "counts", "notes", "results"}


def part():
    return PartModel("p", thickness_mm=1.5, material_name="Steel", flat_dimensions_mm=(300, 200),
                     bends=[Bend(inner_radius_mm=2.0, angle_deg=90)], flanges=[Flange(length_mm=10)],
                     holes=[Hole(diameter_mm=5, dist_to_edge_mm=10, dist_to_bend_mm=10, has_adjacent_bend=True)])


def test_phase1_models_construct_with_phase1_signatures():
    Hole(5.0); Hole(5.0, (1, 2, 3), 1.0, 2.0, True, GeometryRef("hole", "t", "Hole 1")); Bend(1.0, 90.0); Flange(5.0, True)
    PartModel("x", 1.5, "t", "Steel", (1, 2), (1, 2, 3))
    p = PartModel(name="x")
    assert p.cutouts == [] and p.instance_count == 1


def test_phase1_demo_profile_results_unchanged_in_shape_and_outcome():
    demo = next(p for p in list_profiles()[0] if p["manufacturer"]["id"] == "demo")
    rep = evaluate(part(), demo, "sheet_metal_bending")
    assert rep.overall == Status.PASS and rep.counts() == {"PASS": 7, "FAIL": 0, "NEEDS_REVIEW": 0, "SKIPPED": 0}
    d = rep.to_dict()
    assert PHASE1_REPORT_KEYS <= set(d) and PHASE1_RESULT_KEYS <= set(d["results"][0])
    assert d["results"][0]["status"] in ("PASS", "FAIL", "NEEDS_REVIEW", "SKIPPED")


def test_phase1_v1_profile_evaluates_with_original_semantics():
    scs = load_profile(FIX)
    rep = evaluate(PartModel("p", thickness_mm=2.0, material_name="Aluminum 5052-H32", flat_dimensions_mm=(300, 200)), scs, "sheet_metal_bending")
    by = {r.rule_id: r for r in rep.results}
    assert by["scs.thickness.aluminum_5052_h32"].status == Status.PASS
    assert by["scs.max_flat_size"].status == Status.PASS
    assert by["scs.min_bend_radius"].status == Status.SKIPPED and by["scs.min_flange_length"].status == Status.SKIPPED
    assert rep.material_id == "aluminum_5052_h32"
    bad = evaluate(PartModel("p", thickness_mm=0.5, material_name="Aluminum 5052", flat_dimensions_mm=(300, 200)), scs, "sheet_metal_bending")
    assert {r.rule_id: r for r in bad.results}["scs.thickness.aluminum_5052_h32"].status == Status.FAIL


def test_phase1_bridge_payload_shape():
    d = bridge.results_payload(part(), ["w"], {"manufacturer_id": "demo", "process_id": "sheet_metal_bending"})
    assert {"overall", "counts", "results", "notes", "part", "demo", "manufacturer_name"} <= set(d)
    assert {"name", "material", "thickness_mm", "unsupported", "warnings", "counts"} <= set(d["part"])
    r = d["results"][0]
    assert {"token", "ref_label", "status", "severity", "explanation", "recommendation"} <= set(r)
    json.dumps(d)
    assert bridge.profiles_payload()["profiles"][0].keys() >= {"id", "name", "status", "processes"}


def test_phase1_failure_modes_still_hold():
    demo = next(p for p in list_profiles()[0] if p["manufacturer"]["id"] == "demo")
    p = part(); p.thickness_mm = None; p.unsupported = {"thickness": "x"}
    rep = evaluate(p, demo, "sheet_metal_bending")
    assert rep.overall == Status.NEEDS_REVIEW and rep.counts()["PASS"] >= 0
    assert not any(r.status == Status.PASS and r.rule_type in ("min_bend_radius", "min_flange_length") for r in rep.results)


# ---- material matching behaviour (Fusion library names are NOT silently guessed) ----------------
SCS = None


@pytest.mark.parametrize("name,expected", [
    ("Mild Steel", "mild_steel"), ("mild steel (cold rolled)", "mild_steel"), ("Aluminum 5052-H32", "aluminum_5052_h32"),
    ("ALUMINIUM 5052", "aluminum_5052_h32"), ("Stainless Steel 304", "stainless_304"), ("304 Stainless", "stainless_304"),
    ("Brass", "brass"), ("Titanium Grade 2", "titanium_grade2"), ("G90 Galvanized Steel", "galvanized_g90"),
    # ambiguous generic library names must NOT match anything
    ("Steel", None), ("Aluminum 6061", None), ("Stainless Steel", None), ("Aluminum", None), ("", None), (None, None),
])
def test_material_matching(name, expected):
    proc = next(p for p in list_profiles()[0] if p["manufacturer"]["id"] == "sendcutsend")["processes"][0]
    assert match_material(proc, name) == expected
