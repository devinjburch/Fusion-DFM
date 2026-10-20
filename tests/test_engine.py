import os
from dfm_engine import (PartModel, Hole, Bend, Flange, GeometryRef, Status, load_profile, evaluate)
from dfm_engine.profile import DEFAULT_DIR

DEMO = load_profile(os.path.join(DEFAULT_DIR, "demo.json"))
SCS = load_profile(os.path.join(DEFAULT_DIR, "sendcutsend.json"))
PCBWAY = load_profile(os.path.join(DEFAULT_DIR, "pcbway.json"))
P = "sheet_metal_bending"


def good_part(**kw):
    d = dict(name="p", thickness_mm=1.5, material_name="Steel", flat_dimensions_mm=(300, 200),
             bends=[Bend(inner_radius_mm=2.0, angle_deg=90)], flanges=[Flange(length_mm=10)],
             holes=[Hole(diameter_mm=5, dist_to_edge_mm=10, dist_to_bend_mm=10, has_adjacent_bend=True)])
    d.update(kw)
    return PartModel(**d)


def by_rule(rep, rid):
    return [r for r in rep.results if r.rule_id == rid]


def test_all_pass():
    rep = evaluate(good_part(), DEMO, P)
    assert rep.overall == Status.PASS and rep.demo
    assert rep.counts()["FAIL"] == 0 and rep.counts()["NEEDS_REVIEW"] == 0


def test_thickness_fail_and_fields():
    rep = evaluate(good_part(thickness_mm=5.0), DEMO, P)
    r = by_rule(rep, "demo.thickness")[0]
    assert r.status == Status.FAIL and r.measured == 5.0 and r.required
    assert r.recommendation and r.explanation and r.manufacturer and r.severity.value == "ERROR"
    assert rep.overall == Status.FAIL


def test_bend_radius_fail_and_ref_kept():
    ref = GeometryRef("bend", "tok1", "Bend 1")
    rep = evaluate(good_part(bends=[Bend(inner_radius_mm=0.5, ref=ref)]), DEMO, P)
    r = by_rule(rep, "demo.bend_radius")[0]
    assert r.status == Status.FAIL and r.geometry_ref == ref and "1.50" in r.required


def test_boundary_value_passes():
    rep = evaluate(good_part(bends=[Bend(inner_radius_mm=1.5)]), DEMO, P)  # == 1.0 * t
    assert by_rule(rep, "demo.bend_radius")[0].status == Status.PASS


def test_flange_only_terminal_checked():
    rep = evaluate(good_part(flanges=[Flange(length_mm=1, is_terminal=False)]), DEMO, P)
    assert by_rule(rep, "demo.flange") == []
    rep = evaluate(good_part(flanges=[Flange(length_mm=1)]), DEMO, P)
    assert by_rule(rep, "demo.flange")[0].status == Status.FAIL


def test_hole_edge_and_bend_and_diameter():
    h = Hole(diameter_mm=0.5, dist_to_edge_mm=1.0, dist_to_bend_mm=1.0, has_adjacent_bend=True)
    rep = evaluate(good_part(holes=[h]), DEMO, P)
    assert by_rule(rep, "demo.hole_edge")[0].status == Status.FAIL
    assert by_rule(rep, "demo.hole_bend")[0].status == Status.FAIL
    assert by_rule(rep, "demo.hole_dia")[0].status == Status.FAIL
    assert by_rule(rep, "demo.hole_dia")[0].severity.value == "WARNING"


def test_hole_without_bend_not_checked_for_bend_distance():
    h = Hole(diameter_mm=5, dist_to_edge_mm=10, has_adjacent_bend=False)
    rep = evaluate(good_part(holes=[h]), DEMO, P)
    assert by_rule(rep, "demo.hole_bend") == []


def test_max_dimensions_orientation_independent():
    assert by_rule(evaluate(good_part(flat_dimensions_mm=(400, 1200)), DEMO, P), "demo.max_dims")[0].status == Status.FAIL
    assert by_rule(evaluate(good_part(flat_dimensions_mm=(900, 450)), DEMO, P), "demo.max_dims")[0].status == Status.PASS


# ---- missing data is never PASS -------------------------------------------
def test_missing_thickness_needs_review():
    rep = evaluate(good_part(thickness_mm=None, unsupported={"thickness": "no sheet metal rule"}), DEMO, P)
    r = by_rule(rep, "demo.thickness")[0]
    assert r.status == Status.NEEDS_REVIEW and "no sheet metal rule" in r.explanation
    # ratio-based rules also cannot run
    assert by_rule(rep, "demo.bend_radius")[0].status == Status.NEEDS_REVIEW
    assert rep.overall == Status.NEEDS_REVIEW


def test_unsupported_feature_needs_review():
    rep = evaluate(good_part(unsupported={"flanges": "not extractable"}), DEMO, P)
    assert by_rule(rep, "demo.flange")[0].status == Status.NEEDS_REVIEW


def test_unmeasured_hole_needs_review():
    rep = evaluate(good_part(holes=[Hole(diameter_mm=5, dist_to_edge_mm=None)]), DEMO, P)
    assert by_rule(rep, "demo.hole_edge")[0].status == Status.NEEDS_REVIEW


def test_missing_flat_dims_needs_review():
    rep = evaluate(good_part(flat_dimensions_mm=None), DEMO, P)
    assert by_rule(rep, "demo.max_dims")[0].status == Status.NEEDS_REVIEW


def test_fail_outranks_needs_review():
    rep = evaluate(good_part(thickness_mm=None, bends=[Bend(inner_radius_mm=0.0)],
                             flat_dimensions_mm=(5000, 5000)), DEMO, P)
    assert rep.overall == Status.FAIL


# ---- manufacturer data availability ----------------------------------------
def test_unverified_profile_never_passes():
    rep = evaluate(good_part(), PCBWAY, "sheet_metal_fabrication")
    assert rep.counts()["PASS"] == 0 and rep.overall == Status.NEEDS_REVIEW
    assert all(r.status == Status.SKIPPED for r in rep.results)


def test_scs_material_matching_and_thickness():
    ok = evaluate(good_part(material_name="Aluminum 5052-H32", thickness_mm=2.0), SCS, P)
    assert ok.material_id == "aluminum_5052_h32"
    assert by_rule(ok, "scs.thickness.aluminum_5052_h32")[0].status == Status.PASS
    bad = evaluate(good_part(material_name="Aluminum 5052", thickness_mm=0.5), SCS, P)
    assert by_rule(bad, "scs.thickness.aluminum_5052_h32")[0].status == Status.FAIL
    # other materials' rules not applicable
    assert by_rule(bad, "scs.thickness.brass") == []


def test_scs_unknown_material_needs_review_not_pass():
    rep = evaluate(good_part(material_name="Unobtainium"), SCS, P)
    assert all(r.status == Status.NEEDS_REVIEW for r in rep.results if r.rule_id.startswith("scs.thickness"))
    assert rep.overall == Status.NEEDS_REVIEW and rep.notes


def test_scs_disabled_rules_reported_skipped():
    rep = evaluate(good_part(material_name="Mild Steel"), SCS, P)
    assert by_rule(rep, "scs.min_bend_radius")[0].status == Status.SKIPPED
    assert by_rule(rep, "scs.min_flange_length")[0].status == Status.SKIPPED


def test_scs_hole_ratio_and_size():
    rep = evaluate(good_part(material_name="Mild Steel", thickness_mm=3.0,
                             holes=[Hole(diameter_mm=1.0, dist_to_edge_mm=9)]), SCS, P)
    r = by_rule(rep, "scs.min_hole_diameter_laser")[0]
    assert r.status == Status.FAIL and "1.50" in r.required
    assert r.source_url and r.date_verified
    assert by_rule(rep, "scs.max_flat_size")[0].status == Status.PASS


def test_override_material():
    rep = evaluate(good_part(material_name=None), SCS, P, material_id="brass")
    assert rep.material_id == "brass"
