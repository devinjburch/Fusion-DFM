"""Cutout classification on synthetic loop fixtures (no CAD)."""
import math
import pytest
from dfm_engine.features import EdgeDesc, LoopDesc, classify_loop, to_cutout, dedupe_sheet_sides

T = 2.0
N = (0, 0, 1)


def line(a, b, wall=T):
    return EdgeDesc("line", [(a[0], a[1], 0), (b[0], b[1], 0)], wall_height_mm=wall)


def arc(center, r, a0, a1, wall=T):
    pts = [(center[0] + r * math.cos(math.radians(a0 + (a1 - a0) * i / 8)), center[1] + r * math.sin(math.radians(a0 + (a1 - a0) * i / 8)), 0) for i in range(9)]
    return EdgeDesc("arc", pts, radius_mm=r, sweep_deg=abs(a1 - a0), wall_height_mm=wall)


def slot(L=20, W=6, wall=T):
    r = W / 2
    return LoopDesc([line((0, -r), (L, -r), wall), arc((L, 0), r, -90, 90, wall), line((L, r), (0, r), wall), arc((0, 0), r, 90, 270, wall)], N)


def rect(w=10, h=4, wall=T):
    return LoopDesc([line((0, 0), (w, 0), wall), line((w, 0), (w, h), wall), line((w, h), (0, h), wall), line((0, h), (0, 0), wall)], N)


def test_slot_classified_with_width_and_length():
    c = classify_loop(slot(), T)
    assert c.kind == "slot" and c.min_dimension_mm == pytest.approx(6) and c.length_mm == pytest.approx(26) and c.certain


def test_rectangle_and_rounded_rectangle():
    c = classify_loop(rect(), T)
    assert c.kind == "rect" and c.min_dimension_mm == pytest.approx(4) and c.length_mm == pytest.approx(10) and c.certain
    r = 1.0   # rounded corners: 4 lines shortened by r each end + 4 quarter arcs
    loop = LoopDesc([line((r, 0), (10 - r, 0)), arc((10 - r, r), r, -90, 0), line((10, r), (10, 4 - r)), arc((10 - r, 4 - r), r, 0, 90),
                     line((10 - r, 4), (r, 4)), arc((r, 4 - r), r, 90, 180), line((0, 4 - r), (0, r)), arc((r, r), r, 180, 270)], N)
    c = classify_loop(loop, T)
    assert c.kind == "rect" and c.min_dimension_mm == pytest.approx(4, abs=0.05)


def test_parallelogram_is_irregular_and_uncertain():
    loop = LoopDesc([line((0, 0), (10, 0)), line((10, 0), (13, 4)), line((13, 4), (3, 4)), line((3, 4), (0, 0))], N)
    c = classify_loop(loop, T)
    assert c.kind == "irregular" and c.certain is False and c.min_dimension_mm is None
    assert to_cutout(c, loop).certain is False


def test_spline_edge_is_irregular_uncertain():
    loop = LoopDesc([line((0, 0), (10, 0)), EdgeDesc("other", [(10, 0, 0), (5, 5, 0), (0, 0, 0)], wall_height_mm=T)], N)
    c = classify_loop(loop, T)
    assert c.kind == "irregular" and "spline" in c.reason and not c.certain


def test_asymmetric_slot_not_misclassified():
    loop = slot()
    loop.edges[1] = arc((20, 0), 3, -90, 90)
    loop.edges[3] = arc((0, 0), 2, 90, 270)       # unequal radii -> not a slot
    assert classify_loop(loop, T).kind == "irregular"


def test_circle_is_a_hole_not_a_cutout():
    loop = LoopDesc([EdgeDesc("circle", [(5, 0, 0), (0, 5, 0), (-5, 0, 0), (0, -5, 0), (5, 0, 0)], radius_mm=5, wall_height_mm=T)], N)
    c = classify_loop(loop, T)
    assert c.kind == "circle" and c.min_dimension_mm == pytest.approx(10) and to_cutout(c, loop) is None


def test_non_through_loop_is_ignored_not_a_manufacturing_feature():
    c = classify_loop(rect(wall=0.5), T)       # walls only 0.5 mm tall: pocket / emboss
    assert c.kind == "ignored" and c.through is False and "not a through-cut" in c.reason
    assert to_cutout(c, rect(wall=0.5)) is None


def test_unknown_wall_height_keeps_classification_but_not_certain():
    c = classify_loop(rect(wall=None), T)
    assert c.kind == "rect" and c.through is None and c.certain is False and "not confirmed" in c.reason


def test_negligible_loop_ignored():
    tiny = LoopDesc([line((0, 0), (0.05, 0)), line((0.05, 0), (0.05, 0.05)), line((0.05, 0.05), (0, 0.05)), line((0, 0.05), (0, 0))], N)
    assert classify_loop(tiny, T).kind == "ignored"


def test_dedupe_top_and_bottom_but_keep_separate_features():
    top = ((5, 5, 2.0), (0, 0, 1), "top")
    bottom = ((5, 5, 0.0), (0, 0, -1), "bottom")           # same cutout seen from the other face
    other = ((5, 5, 12.0), (0, 0, 1), "other leg")         # same in-plane position but a different sheet 12 mm away
    shifted = ((25, 5, 2.0), (0, 0, 1), "second")
    kept = dedupe_sheet_sides([top, bottom, other, shifted], T)
    assert [k[2] for k in kept] == ["top", "other leg", "second"]
