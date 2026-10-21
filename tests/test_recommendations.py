"""Recommendation quality: values, units, affected geometry, rationale, source, and that corrections actually fix the problem."""
import copy
import os
import pytest
from dfm_engine import PartModel, Hole, Bend, Flange, GeometryRef, Status, evaluate, load_profile
from dfm_engine.models import Cutout
from dfm_engine.corrections import Correction
from dfm_engine.profile import DEFAULT_DIR

IN = 25.4
SCS = load_profile(os.path.join(DEFAULT_DIR, "sendcutsend.json"))
DEMO = load_profile(os.path.join(DEFAULT_DIR, "demo.json"))
P = "sheet_metal_bending"


def base(**kw):
    d = dict(name="Bracket", thickness_mm=0.119 * IN, material_name="Mild Steel", flat_dimensions_mm=(300, 100),
             bends=[Bend(0.063 * IN, 90, 100, GeometryRef("bend", "b1", "Bend 1"))],
             flanges=[Flange(length_mm=20, length_apex_mm=1.0 * IN, bend_angle_deg=90, ref=GeometryRef("flange", "f1", "Flange 1"))],
             holes=[Hole(6, dist_to_edge_mm=20, dist_to_bend_mm=30, has_adjacent_bend=True, bend_zone_max_mm=6, ref=GeometryRef("hole", "h1", "Hole 1"))])
    d.update(kw)
    return PartModel(**d)


def fails(rep, rid):
    return [r for r in rep.results if r.rule_id == rid and r.status == Status.FAIL]


def test_flange_message_matches_the_requested_style():
    # the user's own example: 0.30 in flange, 0.40 in required -> "increase by at least 0.10 in"
    prof = copy.deepcopy(DEMO)
    for r in prof["processes"][0]["rules"]:
        if r["id"] == "demo.flange":
            r["parameters"] = {"min_mm": 0.40 * IN}
    p = base(flanges=[Flange(length_mm=0.30 * IN, ref=GeometryRef("flange", "f1", "Flange 1"))])
    r = fails(evaluate(p, prof, P), "demo.flange")[0]
    assert "7.62 mm (0.300 in)" in r.explanation and "10.16 mm (0.400 in)" in r.explanation
    assert "at least 2.54 mm (0.100 in)" in r.recommendation
    assert r.geometry_ref.label == "Flange 1" and r.corrections[0].delta_mm == pytest.approx(0.10 * IN)


@pytest.mark.parametrize("make,rid,measure", [
    (lambda: base(flanges=[Flange(length_mm=5, length_apex_mm=0.2 * IN, bend_angle_deg=90, ref=GeometryRef("flange", "f1", "Flange 1"))]), "scs.min_flange_length", "flange"),
    (lambda: base(holes=[Hole(0.5, dist_to_edge_mm=20, has_adjacent_bend=False, ref=GeometryRef("hole", "h1", "Hole 1"))]), "scs.min_hole_diameter", "dia"),
    (lambda: base(holes=[Hole(6, dist_to_edge_mm=20, dist_to_bend_mm=1, has_adjacent_bend=True, bend_zone_max_mm=2, ref=GeometryRef("hole", "h1", "Hole 1"))]), "scs.feature_to_bend", "bend"),
    (lambda: base(bends=[Bend(0.2 * IN, 90, 100, GeometryRef("bend", "b1", "Bend 1"))]), "scs.bend_radius_fixed", "radius"),
])
def test_applying_the_correction_resolves_the_failure(make, rid, measure):
    part = make()
    rep = evaluate(part, SCS, P)
    r = fails(rep, rid)[0]
    c = r.corrections[0]
    assert isinstance(c, Correction) and c.requires_user_approval and c.proposed_mm is not None
    assert r.explanation and r.recommendation and r.source_url and r.date_verified and r.geometry_ref
    # apply the proposal to a copy of the part
    fixed = copy.deepcopy(part)
    if measure == "flange":
        fixed.flanges[0].length_apex_mm = c.proposed_mm
    elif measure == "dia":
        fixed.holes[0].diameter_mm = c.proposed_mm
    elif measure == "bend":
        fixed.holes[0].dist_to_bend_mm = c.proposed_mm - fixed.holes[0].bend_zone_max_mm   # proposal is a centerline distance
    elif measure == "radius":
        fixed.bends[0].inner_radius_mm = c.proposed_mm
    again = evaluate(fixed, SCS, P)
    assert not fails(again, rid), [x.explanation for x in again.results if x.rule_id == rid]
    # the minimum change: just below the proposal still fails (except exact-value rules)
    if c.confidence == "minimum":
        worse = copy.deepcopy(fixed)
        eps = 0.05
        if measure == "flange": worse.flanges[0].length_apex_mm = c.proposed_mm - eps
        elif measure == "dia": worse.holes[0].diameter_mm = c.proposed_mm - eps
        elif measure == "bend": worse.holes[0].dist_to_bend_mm -= eps
        assert fails(evaluate(worse, SCS, P), rid)


def test_every_failure_in_a_busy_part_carries_complete_information():
    part = base(thickness_mm=1.0 * IN, flat_dimensions_mm=(2000, 900),
                bends=[Bend(0.5 * IN, 90, 100, GeometryRef("bend", "b1", "Bend 1"))],
                flanges=[Flange(length_mm=1, length_apex_mm=2, bend_angle_deg=90, ref=GeometryRef("flange", "f1", "Flange 1"))],
                holes=[Hole(0.1, dist_to_edge_mm=0.5, dist_to_bend_mm=0.5, has_adjacent_bend=True, bend_zone_max_mm=1, ref=GeometryRef("hole", "h1", "Hole 1"))],
                cutouts=[Cutout("slot", min_dimension_mm=0.1, dist_to_edge_mm=1, ref=GeometryRef("cutout", "c1", "Slot 1"), has_adjacent_bend=False)])
    for prof in (SCS, DEMO):
        rep = evaluate(part, prof, P)
        for r in (x for x in rep.results if x.status == Status.FAIL):
            assert r.explanation and r.recommendation and r.manufacturer and r.rule_id
            assert r.geometry_ref is not None or r.rule_type in ("thickness_range", "max_part_dimensions", "min_part_dimensions")
            assert r.required_mm is not None or r.required
            if not r.demo:
                assert r.source_url and r.date_verified


def test_verified_requirement_vs_advisory_wording():
    prof = copy.deepcopy(SCS)
    for r in prof["processes"][0]["rules"]:
        if r["id"] == "scs.min_hole_diameter":
            r["strength"] = "advisory"
    part = base(holes=[Hole(0.5, dist_to_edge_mm=20, has_adjacent_bend=False, ref=GeometryRef("hole", "h1", "Hole 1"))])
    adv = [x for x in evaluate(part, prof, P).results if x.rule_id == "scs.min_hole_diameter"][0]
    req = [x for x in evaluate(part, SCS, P).results if x.rule_id == "scs.min_hole_diameter"][0]
    assert req.status == Status.FAIL and req.strength == "requirement"
    assert adv.status == Status.NEEDS_REVIEW and adv.strength == "advisory" and adv.explanation.startswith("Advisory guidance")


def test_correction_arithmetic_and_summary():
    c = Correction("increase_flange_length", "r", "flange_length", "increase", 7.62, 10.16, "x")
    assert c.delta_mm == pytest.approx(2.54) and "7.62 mm (0.300 in)" in c.summary() and "+2.54 mm (0.100 in)" in c.summary()
    assert Correction("k", "r", "p", "set", None, 1.0, "x").delta_mm is None
