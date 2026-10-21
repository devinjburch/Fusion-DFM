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
