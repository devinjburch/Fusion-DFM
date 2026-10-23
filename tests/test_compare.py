import os
import pytest
from dfm_engine import PartModel, Hole, Bend, Flange, load_profile, list_profiles
from dfm_engine.compare import compare, Target, COMPATIBLE, CONDITIONAL, NEEDS_REVIEW, INCOMPATIBLE
from dfm_engine.profile import DEFAULT_DIR

IN = 25.4
PROFILES, _ = list_profiles()
FULL = load_profile(os.path.join(os.path.dirname(__file__), "fixtures", "full_coverage.json"))
STUB = load_profile(os.path.join(os.path.dirname(__file__), "fixtures", "phase1_pcbway_unverified.json"))   # no data at all
_RANK = {COMPATIBLE: 0, CONDITIONAL: 1, NEEDS_REVIEW: 2, INCOMPATIBLE: 3}


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
    e = entry(compare(mild(), [STUB]), "pcbway")
    assert e.verdict == NEEDS_REVIEW and e.passed == 0 and e.failures == 0
    assert "No verified check" in e.summary


def test_provisional_data_can_never_give_compatible_or_incompatible():
    for mat in ("Steel", "Mild Steel", "Aluminum 6061"):                         # generic Fusion names now match PCBWay families
        c = compare(mild(material_name=mat), PROFILES)
        for mid in ("pcbway", "xometry"):
            e = entry(c, mid)
            assert e.verdict in (CONDITIONAL, NEEDS_REVIEW) and e.failures == 0, (mat, mid, e.verdict)
            assert e.provisional and e.coverage_gaps                               # nothing is covered by provisional rules
    # even a hopeless part cannot be INCOMPATIBLE with a provisional manufacturer
    bad = mild(thickness_mm=40, flat_dimensions_mm=(9000, 9000), flanges=[Flange(length_mm=0.1, length_apex_mm=0.1, bend_angle_deg=90)])
    for mid in ("pcbway", "xometry"):
        assert entry(compare(bad, PROFILES), mid).verdict != INCOMPATIBLE


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
    assert ranked[0] == "full"
    assert [_RANK[e.verdict] for e in c.ranked()] == sorted(_RANK[e.verdict] for e in c.ranked())   # best verdict first
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


def test_material_override_resolves_generic_fusion_names():
    p = mild(material_name="Steel")                      # Fusion's generic library name: does not match
    auto = entry(compare(p, PROFILES), "sendcutsend")
    assert auto.reports[0].material_id is None and auto.unresolved >= 1
    chosen = entry(compare(p, PROFILES, [Target("sendcutsend", material_name="Mild Steel")]), "sendcutsend")
    assert chosen.reports[0].material_id == "mild_steel" and chosen.verdict in (CONDITIONAL, INCOMPATIBLE, COMPATIBLE)
    # the caller's part is not modified
    assert p.material_name == "Steel"


def test_bridge_compare_payload_material_name_and_list():
    from fusion_addin import bridge
    pl = bridge.compare_payload([mild(material_name="Steel")], [], {"material_name": "Mild Steel", "manufacturers": [{"id": "sendcutsend"}]})
    assert pl["comparison"]["entries"][0]["reports"][0]["material_id"] == "mild_steel"
    assert "Mild Steel" in bridge.profiles_payload()["material_names"]
