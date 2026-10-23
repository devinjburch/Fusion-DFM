"""PCBWay / Xometry profiles built from the owner-supplied research snapshot: behaviour on real parts."""
import os
import pytest
from dfm_engine import PartModel, Hole, Bend, Flange, GeometryRef, Status, load_profile, evaluate
from dfm_engine.profile import DEFAULT_DIR

IN = 25.4
PCB = load_profile(os.path.join(DEFAULT_DIR, "pcbway.json"))
XOM = load_profile(os.path.join(DEFAULT_DIR, "xometry.json"))
P = "sheet_metal_bending"
T = 0.119 * IN


def part(**kw):
    d = dict(name="p", thickness_mm=T, material_name="Steel", flat_dimensions_mm=(192.5, 50.8),
             bends=[Bend(1.6, 90, 50, GeometryRef("bend", "b1", "Bend 1"))],
             flanges=[Flange(length_mm=12.0, length_apex_mm=16.0, bend_angle_deg=90, ref=GeometryRef("flange", "f1", "Flange 1"))],
             holes=[Hole(6.0, dist_to_edge_mm=10.0, dist_to_bend_mm=12.0, has_adjacent_bend=True, bend_zone_max_mm=5.0,
                         ref=GeometryRef("hole", "h1", "Hole 1"))])
    d.update(kw)
    return PartModel(**d)


def by(rep, rid):
    return {r.rule_id: r for r in rep.results}[rid]


def test_generic_fusion_steel_name_matches_pcbway_steel_family_but_not_stainless():
    assert evaluate(part(material_name="Steel"), PCB, P).material_id == "steel"
    assert evaluate(part(material_name="Stainless Steel 304"), PCB, P).material_id == "stainless_steel"
    assert evaluate(part(material_name="Aluminum 6061"), PCB, P).material_id == "aluminum"
    assert evaluate(part(material_name="Unobtainium"), PCB, P).material_id is None


def test_xometry_thickness_multiple_rules_use_the_part_thickness_and_are_warnings():
    rep = evaluate(part(), XOM, P)
    br = by(rep, "xom.min_bend_radius")       # 1x thickness = 3.02 mm; part radius 1.6 mm
    assert br.status == Status.WARNING and br.confirmed and br.provisional and br.consequence == "warning"
    assert br.required_mm == pytest.approx(T) and "Bend" in br.title
    he = by(rep, "xom.hole_edge")             # 2x thickness = 6.05 mm; hole is 10 mm from the edge
    assert he.status == Status.PASS and "provisional data" in he.explanation
    assert by(rep, "xom.hole_edge").source_url == "https://www.xometry.com/capabilities/sheet-metal-fabrication/"
    close = evaluate(part(holes=[Hole(6.0, dist_to_edge_mm=3.0, has_adjacent_bend=False, ref=GeometryRef("hole", "h1", "Hole 1"))]), XOM, P)
    r = by(close, "xom.hole_edge")
    assert r.status == Status.WARNING and r.title == "Hole 1: too close to edge" and r.corrections[0].kind == "move_feature"
    assert close.counts()["FAIL"] == 0 and close.overall == Status.WARNING


def test_xometry_typical_limits_need_review_not_fail():
    thick = evaluate(part(thickness_mm=8.0), XOM, P)
    r = by(thick, "xom.thickness_typical")
    assert r.status == Status.NEEDS_REVIEW and "confirm with the manufacturer" in r.explanation and thick.counts()["FAIL"] == 0
    big = by(evaluate(part(flat_dimensions_mm=(4000, 1000)), XOM, P), "xom.max_blank")      # > 120 x 60 in
    assert big.status == Status.NEEDS_REVIEW
    assert by(evaluate(part(flat_dimensions_mm=(3000, 1500)), XOM, P), "xom.max_blank").status == Status.PASS   # 118 x 59 in


def test_xometry_skips_ambiguous_datum_rule_and_never_automates_hole_to_hole():
    rep = evaluate(part(), XOM, P)
    assert by(rep, "xom.bend_to_hole").status == Status.SKIPPED
    assert "xom.hole_to_hole" not in {r.rule_id for r in rep.results}


def test_pcbway_flange_bend_clearance_and_stock_limits():
    rep = evaluate(part(), PCB, P)
    fl = by(rep, "pcb.min_flange")            # 4x t = 12.09 mm, measured from the tangent line (conservative): flange is 12.0
    assert fl.status == Status.WARNING and fl.required_mm == pytest.approx(4 * T) and "tangent" in fl.rationale + fl.notes
    fb = by(rep, "pcb.feature_to_bend")       # 2x t = 6.05 mm; hole 12 mm from tangent -> pass
    assert fb.status == Status.PASS
    close = by(evaluate(part(holes=[Hole(6, dist_to_edge_mm=20, dist_to_bend_mm=1.0, has_adjacent_bend=True, bend_zone_max_mm=2.0,
                                          ref=GeometryRef("hole", "h1", "Hole 1"))]), PCB, P), "pcb.feature_to_bend")
    assert close.status == Status.WARNING and close.title == "Hole 1: too close to bend"
    # steel stock 1500 x 3000 minus 5 mm margins; rotation allowed (long/short compared separately)
    ok = by(evaluate(part(flat_dimensions_mm=(1400, 2900)), PCB, P), "pcb.stock.steel")
    assert ok.status == Status.PASS
    over = by(evaluate(part(flat_dimensions_mm=(1495, 2995)), PCB, P), "pcb.stock.steel")
    assert over.status == Status.NEEDS_REVIEW and "raw" in over.notes.lower()
    # aluminum has a smaller sheet: the same flat part needs review there but not on steel
    big = part(flat_dimensions_mm=(1400, 2600))
    assert by(evaluate(big, PCB, P), "pcb.stock.steel").status == Status.PASS
    assert by(evaluate(PartModel(**{**big.__dict__, "material_name": "Aluminum 6061"}), PCB, P), "pcb.stock.aluminum").status == Status.NEEDS_REVIEW
    assert "pcb.stock.aluminum" not in {r.rule_id for r in evaluate(big, PCB, P).results}      # scoped to its material family


def test_pcbway_no_universal_bend_radius_is_applied():
    rep = evaluate(part(bends=[Bend(0.1, 90, 50)]), PCB, P)       # absurdly small radius
    assert by(rep, "pcb.min_bend_radius").status == Status.SKIPPED and rep.counts()["FAIL"] == 0


def test_provisional_results_never_fail_and_never_make_the_part_compatible():
    for prof in (PCB, XOM):
        rep = evaluate(part(thickness_mm=30, flat_dimensions_mm=(9000, 9000)), prof, P)
        assert rep.counts()["FAIL"] == 0
        assert {"thickness", "bend_radius", "hole_diameter", "max_part_size"} <= set(rep.coverage_gaps)
        assert all(r.provisional for r in rep.results if r.status != Status.SKIPPED)


def test_pcbway_cnc_routing_process_uses_review_consequence():
    rep = evaluate(part(flat_dimensions_mm=(1500, 800), holes=[Hole(0.1, dist_to_edge_mm=10, has_adjacent_bend=False)]), PCB, "cnc_routing")
    assert by(rep, "pcb.route.max_part").status == Status.NEEDS_REVIEW
    assert by(rep, "pcb.route.min_hole").status == Status.NEEDS_REVIEW and rep.counts()["FAIL"] == 0
