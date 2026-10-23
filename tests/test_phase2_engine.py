"""Phase 2 engine behaviour on the schema-v2 SendCutSend profile (real published values)."""
import os
import pytest
from dfm_engine import PartModel, Hole, Bend, Flange, GeometryRef, Status, load_profile, evaluate
from dfm_engine.models import Cutout
from dfm_engine.profile import DEFAULT_DIR

SCS = load_profile(os.path.join(DEFAULT_DIR, "sendcutsend.json"))
P = "sheet_metal_bending"
IN = 25.4


def mild(t_in=0.119, **kw):
    d = dict(name="p", thickness_mm=t_in * IN, material_name="Mild Steel", flat_dimensions_mm=(300, 100),
             bends=[Bend(inner_radius_mm=0.063 * IN, angle_deg=90, length_mm=100)],
             flanges=[Flange(length_mm=20, length_apex_mm=1.0 * IN, bend_angle_deg=90)],
             holes=[Hole(diameter_mm=6, dist_to_edge_mm=20, dist_to_bend_mm=30, has_adjacent_bend=True, bend_zone_max_mm=6)])
    d.update(kw)
    return PartModel(**d)


def by(rep, rid):
    return [r for r in rep.results if r.rule_id == rid]


def test_stock_thickness_pass_and_match_note():
    rep = evaluate(mild(), SCS, P)
    assert by(rep, "scs.thickness_in_stock")[0].status == Status.PASS
    assert "listed stock thickness" in rep.thickness_match
    assert rep.material_id == "mild_steel"


def test_thickness_matching_tolerance_boundary():
    # .119 in = 3.0226 mm; +0.05 mm still matches, +0.06 mm does not
    near = evaluate(mild(thickness_mm=0.119 * IN + 0.05), SCS, P)
    far = evaluate(mild(thickness_mm=0.119 * IN + 0.06), SCS, P)
    assert by(near, "scs.thickness_in_stock")[0].status == Status.PASS
    assert by(far, "scs.thickness_in_stock")[0].status == Status.NEEDS_REVIEW   # unlisted, not a FAIL
    # per-thickness spec rules cannot run without a listed thickness
    assert by(far, "scs.min_flange_length")[0].status == Status.NEEDS_REVIEW


def test_na_row_is_confirmed_fail_with_correction():
    rep = evaluate(mild(thickness_mm=0.313 * IN), SCS, P)   # mild steel .313 listed N/A for bending
    r = by(rep, "scs.thickness_in_stock")[0]
    assert r.status == Status.FAIL and r.corrections and r.corrections[0].kind == "change_thickness"


def test_out_of_range_thickness_fails_range_rule():
    rep = evaluate(mild(thickness_mm=1.0 * IN), SCS, P)
    assert by(rep, "scs.thickness.mild_steel")[0].status == Status.FAIL


def test_bend_radius_fixed_match_and_mismatch():
    ok = evaluate(mild(), SCS, P)
    assert by(ok, "scs.bend_radius_fixed")[0].status == Status.PASS
    bad = evaluate(mild(bends=[Bend(inner_radius_mm=0.2 * IN, angle_deg=90, length_mm=100)]), SCS, P)
    r = by(bad, "scs.bend_radius_fixed")[0]
    assert r.status == Status.FAIL and r.severity.value == "WARNING"
    c = r.corrections[0]
    assert c.kind == "set_bend_radius" and c.proposed_mm == pytest.approx(0.063 * IN, abs=1e-3) and c.confidence == "exact"
    assert "does not offer custom bend radii" in r.explanation


def test_conflicting_published_radius_gives_needs_review():
    # 5052 .080 in: spec table .038 in vs min/max table .045 in (recorded as a conflict)
    t = 0.080 * IN
    for radius_in, expect in ((0.038, Status.NEEDS_REVIEW), (0.045, Status.NEEDS_REVIEW), (0.100, Status.FAIL)):
        rep = evaluate(mild(thickness_mm=t, material_name="5052 Aluminum",
                            bends=[Bend(inner_radius_mm=radius_in * IN, angle_deg=90, length_mm=100)]), SCS, P)
        assert by(rep, "scs.bend_radius_fixed")[0].status == expect, radius_in


def test_flange_min_uses_apex_and_90_degree_scope():
    # mild .119 in: min formed flange .466 in (11.84 mm) measured from the apex
    short = evaluate(mild(flanges=[Flange(length_mm=5, length_apex_mm=0.30 * IN, bend_angle_deg=90)]), SCS, P)
    r = by(short, "scs.min_flange_length")[0]
    assert r.status == Status.FAIL and r.required_mm == pytest.approx(0.466 * IN, abs=1e-3)
    assert r.corrections[0].delta_mm == pytest.approx((0.466 - 0.30) * IN, abs=1e-3)
    assert "0.466 in" in r.explanation and "Lengthen the flange by at least" in r.recommendation
    exact = evaluate(mild(flanges=[Flange(length_mm=5, length_apex_mm=0.466 * IN, bend_angle_deg=90)]), SCS, P)
    assert by(exact, "scs.min_flange_length")[0].status == Status.PASS          # boundary
    other = evaluate(mild(flanges=[Flange(length_mm=5, length_apex_mm=0.1 * IN, bend_angle_deg=60)]), SCS, P)
    assert by(other, "scs.min_flange_length")[0].status == Status.NEEDS_REVIEW  # unpublished angle
    noapex = evaluate(mild(flanges=[Flange(length_mm=5, bend_angle_deg=90)]), SCS, P)
    assert by(noapex, "scs.min_flange_length")[0].status == Status.NEEDS_REVIEW


def test_feature_to_bend_centerline_outcomes_are_non_blocking_warnings():
    die_half = 0.630 * IN / 2          # mild .119 -> die .630 in -> 8.0 mm
    mk = lambda d, zone: mild(holes=[Hole(diameter_mm=6, dist_to_edge_mm=30, dist_to_bend_mm=d, has_adjacent_bend=True, bend_zone_max_mm=zone,
                                          ref=GeometryRef("hole", "h4", "Hole 4"))])
    ok = by(evaluate(mk(die_half, 6), SCS, P), "scs.feature_to_bend")[0]
    assert ok.status == Status.PASS
    warn = by(evaluate(mk(1.0, 3.0), SCS, P), "scs.feature_to_bend")[0]       # max centerline dist 4.0 < 8.0: confirmed
    assert warn.status == Status.WARNING and warn.confirmed and warn.severity.value == "WARNING" and warn.consequence == "warning"
    assert warn.corrections[0].kind == "move_feature" and warn.title == "Hole 4: too close to bend"
    unsure = by(evaluate(mk(5.0, 6.0), SCS, P), "scs.feature_to_bend")[0]     # between 5 and 11: cannot be ruled out
    assert unsure.status == Status.WARNING and not unsure.confirmed and "centerline" in unsure.explanation
    assert unsure.title == "Hole 4: may be too close to bend" and unsure.explanation.startswith("Not confirmed")
    unknown_zone = by(evaluate(mk(5.0, None), SCS, P), "scs.feature_to_bend")[0]
    assert unknown_zone.status == Status.WARNING and not unknown_zone.confirmed


def test_feature_to_bend_can_be_made_blocking_again():
    import copy
    prof = copy.deepcopy(SCS)
    for r in prof["processes"][0]["rules"]:
        if r["id"] == "scs.feature_to_bend":
            r["consequence"] = "blocking"
    mk = lambda d, zone: mild(holes=[Hole(diameter_mm=6, dist_to_edge_mm=30, dist_to_bend_mm=d, has_adjacent_bend=True, bend_zone_max_mm=zone)])
    assert by(evaluate(mk(1.0, 3.0), prof, P), "scs.feature_to_bend")[0].status == Status.FAIL
    assert by(evaluate(mk(5.0, 6.0), prof, P), "scs.feature_to_bend")[0].status == Status.NEEDS_REVIEW


def test_warning_does_not_block_but_prevents_unconditional_verdict():
    from dfm_engine.compare import compare, CONDITIONAL
    p = mild(holes=[Hole(diameter_mm=6, dist_to_edge_mm=30, dist_to_bend_mm=1.0, has_adjacent_bend=True, bend_zone_max_mm=3.0)])
    rep = evaluate(p, SCS, P)
    assert rep.overall == Status.WARNING and rep.counts()["WARNING"] == 1 and rep.counts()["FAIL"] == 0
    e = compare(p, [SCS]).entries[0]
    assert e.verdict == CONDITIONAL and e.failures == 0 and e.unresolved == 0 and e.warnings == 1
    assert e.warning_items[0]["rule_id"] == "scs.feature_to_bend" and e.warning_items[0]["confirmed"] is True
    assert e.to_dict()["warnings"] == 1 and "warnings" in e.to_dict()["verdict_text"]


def test_a_failure_elsewhere_still_makes_it_incompatible_with_the_warning_listed():
    from dfm_engine.compare import compare, INCOMPATIBLE
    p = mild(holes=[Hole(diameter_mm=6, dist_to_edge_mm=30, dist_to_bend_mm=1.0, has_adjacent_bend=True, bend_zone_max_mm=3.0)],
             flanges=[Flange(length_mm=5, length_apex_mm=0.2 * IN, bend_angle_deg=90)])
    e = compare(p, [SCS]).entries[0]
    assert e.verdict == INCOMPATIBLE and e.failures == 1 and e.warnings == 1


def test_titles_name_the_problem_by_rule():
    h = Hole(diameter_mm=0.5, dist_to_edge_mm=1.0, dist_to_bend_mm=30, has_adjacent_bend=False, ref=GeometryRef("hole", "h2", "Hole 2"))
    rep = evaluate(mild(holes=[h], flanges=[Flange(length_mm=5, length_apex_mm=0.2 * IN, bend_angle_deg=90, ref=GeometryRef("flange", "f1", "Flange 1"))],
                        bends=[Bend(0.2 * IN, 90, 100, GeometryRef("bend", "b1", "Bend 1"))]), SCS, P)
    t = {r.rule_id: r.title for r in rep.results}
    assert t["scs.min_hole_diameter"] == "Hole 2: too small"
    assert t["scs.min_flange_length"] == "Flange 1: flange too short"
    assert t["scs.bend_radius_fixed"] == "Bend 1: bend radius differs from the fixed radius"
    assert t["scs.thickness_in_stock"] == "Sheet thickness: stocked thickness"
    assert t["scs.min_hole_edge_distance"] == "scs.min_hole_edge_distance: not checked"      # skipped rule


def test_cutouts_checked_and_uncertain_ones_need_review():
    cut_ok = Cutout("slot", min_dimension_mm=6, dist_to_edge_mm=20, dist_to_bend_mm=30, has_adjacent_bend=True, bend_zone_max_mm=5)
    cut_small = Cutout("rect", min_dimension_mm=0.5, dist_to_edge_mm=20, has_adjacent_bend=False)
    cut_unsure = Cutout("irregular", min_dimension_mm=None, certain=False, uncertainty_reason="loop has spline edges")
    rep = evaluate(mild(holes=[], cutouts=[cut_ok, cut_small, cut_unsure]), SCS, P)
    dia = by(rep, "scs.min_hole_diameter")
    assert [r.status for r in dia] == [Status.PASS, Status.FAIL, Status.NEEDS_REVIEW]   # 50% of 3.02 mm = 1.51 mm
    assert "uncertain" in dia[2].explanation


def test_flat_size_limits_and_min_size():
    big = evaluate(mild(flat_dimensions_mm=(1200, 700)), SCS, P)    # max 30x44 in = 1117.6 x 762
    assert by(big, "scs.max_flat_size")[0].status == Status.FAIL
    tiny = evaluate(mild(flat_dimensions_mm=(20, 5)), SCS, P)       # min .375 x 1.5 in
    assert by(tiny, "scs.min_flat_size")[0].status == Status.FAIL
    fine = evaluate(mild(), SCS, P)
    assert by(fine, "scs.max_flat_size")[0].status == Status.PASS and by(fine, "scs.min_flat_size")[0].status == Status.PASS
    nofp = evaluate(mild(flat_dimensions_mm=None, unsupported={"flat_dimensions": "no flat pattern"}), SCS, P)
    assert by(nofp, "scs.max_flat_size")[0].status == Status.NEEDS_REVIEW


def test_max_bend_length():
    rep = evaluate(mild(bends=[Bend(inner_radius_mm=0.063 * IN, angle_deg=90, length_mm=45 * IN)]), SCS, P)
    assert by(rep, "scs.max_bend_length")[0].status == Status.FAIL


def test_coverage_gap_reported_for_unverified_rules():
    rep = evaluate(mild(), SCS, P)
    assert "hole_edge_distance" in rep.coverage_gaps
    assert by(rep, "scs.min_hole_edge_distance")[0].status == Status.SKIPPED


def test_advisory_rules_never_fail():
    import copy
    prof = copy.deepcopy(SCS)
    for r in prof["processes"][0]["rules"]:
        if r["id"] == "scs.min_flange_length":
            r["strength"] = "advisory"
    rep = evaluate(mild(flanges=[Flange(length_mm=5, length_apex_mm=0.1 * IN, bend_angle_deg=90)]), prof, P)
    r = by(rep, "scs.min_flange_length")[0]
    assert r.status == Status.WARNING and r.severity.value == "INFO" and r.strength == "advisory"   # measured miss: low-severity warning
    assert r.explanation.startswith("Advisory guidance")


def test_unverified_enabled_rule_in_real_profile_is_not_evaluated():
    import copy
    prof = copy.deepcopy(SCS)
    for r in prof["processes"][0]["rules"]:
        if r["id"] == "scs.max_flat_size":
            r["verified"] = False        # bypass the loader on purpose: engine must still refuse
    rep = evaluate(mild(flat_dimensions_mm=(5000, 5000)), prof, P)
    assert by(rep, "scs.max_flat_size")[0].status == Status.SKIPPED


def test_recommendation_text_has_values_and_units():
    rep = evaluate(mild(holes=[Hole(diameter_mm=0.5, dist_to_edge_mm=20, dist_to_bend_mm=30, has_adjacent_bend=False)]), SCS, P)
    r = by(rep, "scs.min_hole_diameter")[0]
    assert r.status == Status.FAIL
    assert "mm" in r.explanation and "in)" in r.explanation and r.rationale and r.source_url and r.date_verified


# ---- round 6: unchecked non-blocking rules must not be shown as warnings --------------------
def test_unevaluable_non_blocking_rule_stays_needs_review_and_title_makes_no_claim():
    p = mild(material_name="Steel")                       # Fusion's generic name: no material match -> no spec table
    rep = evaluate(p, SCS, P)
    r = by(rep, "scs.feature_to_bend")[0]
    assert r.status == Status.NEEDS_REVIEW and not r.borderline and r.consequence == "warning"
    assert r.title == "Feature-to-bend distance: could not be checked" and "too close" not in r.title
    assert "Not confirmed (non-blocking rule)" not in r.explanation
    assert rep.counts()["WARNING"] == 0


def test_borderline_measurement_is_a_warning_but_unmeasured_is_not():
    mk = lambda d, zone: mild(holes=[Hole(diameter_mm=6, dist_to_edge_mm=30, dist_to_bend_mm=d, has_adjacent_bend=True, bend_zone_max_mm=zone,
                                          ref=GeometryRef("hole", "h1", "Hole 1"))])
    b = by(evaluate(mk(5.0, 6.0), SCS, P), "scs.feature_to_bend")[0]
    assert b.status == Status.WARNING and b.borderline and not b.confirmed and b.title == "Hole 1: may be too close to bend"
    unmeasured = by(evaluate(mk(None, 6.0), SCS, P), "scs.feature_to_bend")[0]       # hole could not be measured to the bend
    assert unmeasured.status == Status.NEEDS_REVIEW and unmeasured.title == "Hole 1: could not be checked"


def _with_rule(extra):
    import copy
    prof = copy.deepcopy(SCS)
    r = next(x for x in prof["processes"][0]["rules"] if x["id"] == "scs.max_flat_size")
    r.update(extra)
    return prof


def test_review_consequence_turns_a_confirmed_exceedance_into_needs_review():
    prof = _with_rule({"consequence": "review", "notes": "nominal limit; larger on request"})
    rep = evaluate(mild(flat_dimensions_mm=(1200, 700)), prof, P)
    r = by(rep, "scs.max_flat_size")[0]
    assert r.status == Status.NEEDS_REVIEW and r.explanation.startswith("Exceeds a published typical/nominal limit")
    assert r.title == "Flat size: flat part too large" and rep.counts()["FAIL"] == 0


def test_provisional_rule_pass_is_marked_and_never_counts_toward_coverage():
    prof = _with_rule({"provisional": True, "consequence": "review", "notes": "second-hand data",
                       "source": {"url": "https://x.test", "date_verified": "2026-10-23", "provenance": "supplied by owner"}})
    rep = evaluate(mild(), prof, P)
    r = by(rep, "scs.max_flat_size")[0]
    assert r.status == Status.PASS and r.provisional and "provisional data" in r.explanation
    assert "max_part_size" in rep.coverage_gaps            # a provisional rule does not cover its category


def test_validator_rules_for_provisional_and_review():
    import copy
    import pytest
    from dfm_engine import load_profile_dict, ProfileError
    prof = copy.deepcopy(SCS)
    rule = next(x for x in prof["processes"][0]["rules"] if x["id"] == "scs.max_flat_size")
    rule["provisional"] = True                              # no provenance, still blocking
    with pytest.raises(ProfileError, match="provenance"):
        load_profile_dict(prof)
    rule["source"]["provenance"] = "owner"
    with pytest.raises(ProfileError, match="must not be blocking"):
        load_profile_dict(prof)
    rule["consequence"] = "review"
    with pytest.raises(ProfileError, match="must justify"):
        load_profile_dict(prof)
    rule["notes"] = "nominal"
    load_profile_dict(prof)
