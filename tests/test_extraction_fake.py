import pytest
from . import fake_adsk as fa


def run(**kw):
    body, faces = fa.build_l_bracket(**kw)
    app = fa.install(body)
    from fusion_addin import extraction
    return extraction.extract_part(app), body


def test_l_bracket_features_in_mm():
    (part, warnings), _ = run(with_flat=True)
    assert part.thickness_mm == pytest.approx(2.0) and part.thickness_source == "sheet_metal_rule"
    assert part.material_name == "Steel, Mild"
    assert len(part.bends) == 1 and part.bends[0].inner_radius_mm == pytest.approx(2.0)
    assert part.bends[0].angle_deg == pytest.approx(90.0)
    # both faces next to the single bend are reported (base 50 mm, upright 30 mm), each terminal
    assert sorted(round(f.length_mm) for f in part.flanges) == [30, 50] and all(f.is_terminal for f in part.flanges)
    assert len(part.holes) == 1
    h = part.holes[0]
    assert h.diameter_mm == pytest.approx(5.0)
    assert h.dist_to_edge_mm == pytest.approx(17.5, abs=0.1)
    assert h.dist_to_bend_mm == pytest.approx(27.5, abs=0.1)
    assert h.has_adjacent_bend is True and h.ref.token
    assert part.flat_dimensions_mm == pytest.approx((102.0, 40.0))
    assert not warnings


def test_geometry_fallback_when_no_rule():
    (part, warnings), _ = run(with_rule=False)
    assert part.thickness_source == "derived_from_geometry" and part.thickness_mm == pytest.approx(2.0)
    assert any("No active sheet metal rule" in w for w in warnings)
    assert "flat_dimensions" in part.unsupported  # no flat pattern -> unsupported, not invented


def test_rule_geometry_mismatch_warns():
    (part, warnings), _ = run(rule_thickness_cm=0.3)
    assert part.thickness_mm == pytest.approx(3.0)
    assert any("differs" in w for w in warnings)


def test_non_sheet_metal_rejected():
    body, _ = fa.build_l_bracket()
    body.isSheetMetal = False
    app = fa.install(body)
    from fusion_addin import extraction
    with pytest.raises(extraction.ExtractionError, match="sheet metal"):
        extraction.extract_part(app)


def test_end_to_end_with_demo_profile_and_bridge():
    (part, warnings), _ = run(with_flat=True)
    from fusion_addin import bridge
    d = bridge.results_payload(part, warnings, {"manufacturer_id": "demo", "process_id": "sheet_metal_bending"})
    assert d["overall"] in ("PASS", "FAIL", "NEEDS_REVIEW")
    hole_edge = [r for r in d["results"] if r["rule_id"] == "demo.hole_edge"][0]
    assert hole_edge["status"] == "PASS" and hole_edge["token"]


def test_smoke_runner_with_fake_app():
    body, _ = fa.build_l_bracket(with_flat=True)
    app = fa.install(body)
    from fusion_addin import smoke
    res, report = smoke.run(app)
    st = {n: s for n, s, _ in res}
    assert st["active_design"] == "OK" and st["sheet_metal_body"] == "OK"
    assert st["thickness_rule"] == "OK" and st["extract_part"] == "OK" and st["evaluate_demo"] == "OK"
    assert st["extract_all_parts"] == "OK" and st["compare_all"] == "OK" and st["export_report"] == "OK"
    assert "checks without failure" in report


def test_smoke_runner_isolates_failures():
    from fusion_addin import smoke  # may use fake adsk from earlier tests
    res = smoke.run_checks([("a", lambda: "fine"), ("b", lambda: 1 / 0), ("c", lambda: ("WARN", "meh"))])
    assert [s for _, s, _ in res] == ["OK", "FAIL", "WARN"]


def test_unreadable_rule_thickness_falls_back_to_geometry():
    body, _ = fa.build_l_bracket()
    class Boom:
        @property
        def value(self): raise RuntimeError("2 : InternalValidationError : xlDesign")
    body.parentComponent.activeSheetMetalRule.thickness = Boom()
    app = fa.install(body)
    from fusion_addin import extraction, smoke
    part, warnings = extraction.extract_part(app)
    assert part.thickness_source == "derived_from_geometry" and part.thickness_mm == pytest.approx(2.0)
    assert any("derived from geometry" in w for w in warnings)
    st = {n: s for n, s, _ in smoke.run(app)[0]}
    assert st["thickness_rule"] == "WARN" and st["extract_part"] == "OK"


# ======================= Phase 2: apex/bend zone/cutouts/assemblies =======================
SLOT = {"edges": [("line", (2, 2.7), (4, 2.7)), ("arc", (4, 2.7), (4, 3.3), 0.3, 180), ("line", (4, 3.3), (2, 3.3)), ("arc", (2, 3.3), (2, 2.7), 0.3, 180)]}
RECT = {"edges": [("line", (1, 1), (2, 1)), ("line", (2, 1), (2, 1.4)), ("line", (2, 1.4), (1, 1.4)), ("line", (1, 1.4), (1, 1))]}
BLOB = {"edges": [("line", (6, 1), (8, 1)), ("spline", (8, 1), (6, 1), [(8, 1), (7, 1.8), (6, 1)])]}
POCKET = {"edges": [("line", (6, 4), (8, 4)), ("line", (8, 4), (8, 5)), ("line", (8, 5), (6, 5)), ("line", (6, 5), (6, 4))], "wall": 0.4}


def test_phase2_bend_length_apex_and_bend_zone():
    (part, _), _ = run(with_flat=True)
    assert part.bends[0].length_mm == pytest.approx(40.0)
    assert sorted(round(f.length_apex_mm, 2) for f in part.flanges) == [34.0, 54.0]      # L + (r + t) * tan(45 deg)
    assert all(f.bend_angle_deg == pytest.approx(90) for f in part.flanges)
    assert part.holes[0].bend_zone_max_mm == pytest.approx((2 + 2) * 3.14159265 / 4, abs=1e-3)   # (r+t) * angle / 2


def test_cutouts_classified_and_pocket_ignored():
    body = fa.build_plate([SLOT, RECT, BLOB, POCKET])
    app = fa.install(body)
    from fusion_addin import extraction
    part, warnings = extraction.extract_part(app)
    kinds = sorted(c.cutout_kind for c in part.cutouts)
    assert kinds == ["irregular", "rect", "slot"]                       # pocket ignored, bottom-face duplicates removed
    slot = next(c for c in part.cutouts if c.cutout_kind == "slot")
    rect = next(c for c in part.cutouts if c.cutout_kind == "rect")
    blob = next(c for c in part.cutouts if c.cutout_kind == "irregular")
    assert slot.min_dimension_mm == pytest.approx(6.0) and slot.length_mm == pytest.approx(26.0) and slot.certain
    assert rect.min_dimension_mm == pytest.approx(4.0) and rect.dist_to_edge_mm == pytest.approx(10.0, abs=0.1)
    assert slot.dist_to_edge_mm == pytest.approx(20.0, abs=0.1) and slot.has_adjacent_bend is False
    assert blob.certain is False and "spline" in blob.uncertainty_reason
    assert all(c.ref and c.ref.token for c in part.cutouts)
    assert "slots_and_cutouts" not in part.unsupported


def test_cutouts_flow_into_rules_and_highlight_tokens():
    from dfm_engine import Status, list_profiles, evaluate
    body = fa.build_plate([SLOT, RECT, BLOB])
    app = fa.install(body)
    from fusion_addin import extraction
    part, _ = extraction.extract_part(app)
    demo = next(p for p in list_profiles()[0] if p["manufacturer"]["id"] == "demo")
    rep = evaluate(part, demo, "sheet_metal_bending")
    dia = [r for r in rep.results if r.rule_id == "demo.hole_dia"]
    assert len(dia) == 3 and Status.NEEDS_REVIEW in {r.status for r in dia}          # the irregular one
    assert all(r.geometry_ref and r.geometry_ref.token for r in dia)


def test_extract_all_assembly_dedupes_instances_and_skips_other_bodies():
    bracket, _ = fa.build_l_bracket()
    bracket.parentComponent.name = "BracketComp"
    plate = fa.build_plate([SLOT], name="PlateBody", comp_name="PlateComp")
    hidden = fa.build_plate([RECT], name="Hidden"); hidden.isVisible = False
    solid = fa.build_plate([RECT], name="Block"); solid.isSheetMetal = False
    occ1 = fa.Geo(fullPathName="Sub:1+Plate:1", isVisible=True, bRepBodies=fa.Collection())
    occ2 = fa.Geo(fullPathName="Sub:1+Plate:2", isVisible=True, bRepBodies=fa.Collection())
    occ1.bRepBodies.append(fa.proxy_of(plate, occ1)); occ2.bRepBodies.append(fa.proxy_of(plate, occ2))
    occ3 = fa.Geo(fullPathName="Hid:1", isVisible=False, bRepBodies=fa.Collection([fa.proxy_of(hidden, None)]))
    occ4 = fa.Geo(fullPathName="Blk:1", isVisible=True, bRepBodies=fa.Collection([solid]))
    app = fa.install(bracket, occurrences=[occ1, occ2, occ3, occ4])
    from fusion_addin import extraction
    parts, warnings = extraction.extract_all(app)
    assert [p.name for p in parts] == ["Bracket", "PlateComp / PlateBody"]
    assert parts[0].instance_count == 1 and parts[1].instance_count == 2
    assert parts[1].component_path == "Sub:1+Plate:1"
    assert any("non-sheet-metal" in w for w in warnings)
    assert len(parts[1].cutouts) == 1


def test_extract_all_errors_clearly_without_sheet_metal():
    body, _ = fa.build_l_bracket(); body.isSheetMetal = False
    app = fa.install(body)
    from fusion_addin import extraction
    with pytest.raises(extraction.ExtractionError, match="No visible sheet metal body"):
        extraction.extract_all(app)
