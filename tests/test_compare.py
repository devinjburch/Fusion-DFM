import os
import pytest
from dfm_engine import PartModel, Hole, Bend, Flange, load_profile, list_profiles
from dfm_engine.compare import compare, Target, COMPATIBLE, CONDITIONAL, NEEDS_REVIEW, INCOMPATIBLE
from dfm_engine.profile import DEFAULT_DIR

IN = 25.4
PROFILES, _ = list_profiles()
FULL = load_profile(os.path.join(os.path.dirname(__file__), "fixtures", "full_coverage.json"))


def mild(**kw):
    d = dict(name="p", thickness_mm=0.119 * IN, material_name="Mild Steel", flat_dimensions_mm=(300, 100),
             bends=[Bend(inner_radius_mm=0.063 * IN, angle_deg=90, length_mm=100)],
             flanges=[Flange(length_mm=20, length_apex_mm=1.0 * IN, bend_angle_deg=90)],
             holes=[Hole(diameter_mm=6, dist_to_edge_mm=20, dist_to_bend_mm=30, has_adjacent_bend=True, bend_zone_max_mm=6)])
    d.update(kw)
    return PartModel(**d)


def entry(c, mid):
    return next(e for e in c.entries if e.manufacturer_id == mid)


def test_unverified_manufacturers_never_get_a_compatible_verdict():
    c = compare(mild(), PROFILES)
    for mid in ("pcbway", "xometry"):
        e = entry(c, mid)
        assert e.verdict == NEEDS_REVIEW and e.passed == 0 and e.failures == 0
        assert "No verified check" in e.summary


def test_sendcutsend_conditional_when_coverage_gap_remains():
    e = entry(compare(mild(), PROFILES), "sendcutsend")
    assert e.failures == 0 and e.unresolved == 0
    assert e.verdict == CONDITIONAL and "hole_edge_distance" in e.coverage_gaps


def test_incompatible_lists_reasons_and_corrections():
    p = mild(flanges=[Flange(length_mm=5, length_apex_mm=0.2 * IN, bend_angle_deg=90)])
    e = entry(compare(p, PROFILES), "sendcutsend")
    assert e.verdict == INCOMPATIBLE and e.failures == 1
    assert "flange" in e.reasons[0]["explanation"].lower() and e.corrections[0]["kind"] == "increase_flange_length"


def test_missing_information_blocks_unconditional_verdict():
    p = mild(flat_dimensions_mm=None, unsupported={"flat_dimensions": "no flat pattern"})
    e = entry(compare(p, [FULL]), "full")
    assert e.verdict == NEEDS_REVIEW and e.unresolved >= 1


def test_fully_covered_profile_can_be_compatible_and_ranking_orders_verdicts():
    c = compare(mild(), PROFILES + [FULL])
    assert entry(c, "full").verdict == COMPATIBLE
    ranked = [e.manufacturer_id for e in c.ranked()]
    assert ranked.index("full") < ranked.index("sendcutsend") < ranked.index("pcbway")
    assert "demo" not in ranked                      # demo excluded from ranking by default
    assert "demo" in [e.manufacturer_id for e in c.ranked(include_demo=True)]


def test_multiple_parts_aggregate_and_one_failure_fails_the_manufacturer():
    good, bad = mild(name="good"), mild(name="bad", flat_dimensions_mm=(5000, 5000))
    e = entry(compare([good, bad], PROFILES + [FULL]), "full")
    assert e.verdict == INCOMPATIBLE and {r["part"] for r in e.reasons} == {"bad"}
    assert len(e.reports) == 2


def test_targets_select_process_and_material():
    c = compare(mild(material_name=None), PROFILES, [Target("sendcutsend", "sheet_metal_bending", "mild_steel")])
    assert len(c.entries) == 1 and c.entries[0].reports[0].material_id == "mild_steel"
    with pytest.raises(KeyError):
        compare(mild(), PROFILES, [Target("nobody")])


def test_to_dict_is_json_serialisable():
    import json
    json.dumps(compare(mild(), PROFILES).to_dict())
