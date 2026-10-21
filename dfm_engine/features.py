"""Classify cutouts (inner loops of a sheet face) from neutral descriptors. No CAD dependency.

Conservative by design: a loop is only called a slot or rectangle when its edges prove it. Everything else
is 'irregular' with certain=False, so size rules return NEEDS_REVIEW instead of guessing a narrowest width.
Non-through loops (pockets, cosmetic splits) and tiny loops are reported as ignored, with the reason.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional
from . import geometry as g
from .models import Cutout, GeometryRef

REL = 0.02      # relative tolerance for dimension equality
ANG = 2.0       # degrees
MIN_AREA_MM2 = 0.01


@dataclass
class EdgeDesc:
    kind: str                       # "line" | "arc" | "circle" | "other"
    points: list                    # 3D polyline (mm), >= 2 points
    radius_mm: Optional[float] = None
    sweep_deg: Optional[float] = None
    wall_height_mm: Optional[float] = None   # extent of the adjoining face normal to the sheet face; None unknown


@dataclass
class LoopDesc:
    edges: list
    normal: tuple                   # normal of the sheet face (any sign)
    ref: Optional[GeometryRef] = None


@dataclass
class LoopClass:
    kind: str                       # "circle" | "slot" | "rect" | "irregular" | "ignored"
    min_dimension_mm: Optional[float] = None
    length_mm: Optional[float] = None
    centroid_mm: Optional[tuple] = None
    certain: bool = True
    reason: str = ""
    through: Optional[bool] = None


def _poly(loop):
    pts = []
    for e in loop.edges:
        pts.extend(e.points)
    return pts


def _area2d(pts2):
    s = 0.0
    for i in range(len(pts2)):
        x1, y1 = pts2[i]
        x2, y2 = pts2[(i + 1) % len(pts2)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def _close(a, b, rel=REL, absol=1e-6):
    return abs(a - b) <= max(abs(a), abs(b)) * rel + absol


def _dir2(e, u, v, o):
    a, b = g.to_2d(e.points[0], o, u, v), g.to_2d(e.points[-1], o, u, v)
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy)
    return (dx / n, dy / n, n) if n else (0, 0, 0)


def classify_loop(loop: LoopDesc, thickness_mm: Optional[float]) -> LoopClass:
    if not loop.edges:
        return LoopClass("ignored", reason="empty loop")
    pts = _poly(loop)
    u, v = g.plane_basis(loop.normal)
    o = pts[0]
    p2 = [g.to_2d(p, o, u, v) for p in pts]
    cx = tuple(sum(p[i] for p in pts) / len(pts) for i in range(3))
    area = _area2d(p2)
    # --- through-cut test -------------------------------------------------
    walls = [e.wall_height_mm for e in loop.edges]
    through = None
    if thickness_mm and all(w is not None for w in walls):
        through = all(abs(w - thickness_mm) <= 0.03 * thickness_mm + 0.01 for w in walls)
    if through is False:
        return LoopClass("ignored", centroid_mm=cx, through=False,
                         reason="not a through-cut (adjoining walls are not sheet-thickness tall): pocket, emboss or cosmetic split")
    if area < MIN_AREA_MM2 and len(loop.edges) > 1:
        return LoopClass("ignored", centroid_mm=cx, through=through, reason="loop area is negligible")
    uncertain_through = "" if through else " (through-cut not confirmed)"
    kinds = [e.kind for e in loop.edges]
    lines = [e for e in loop.edges if e.kind == "line"]
    arcs = [e for e in loop.edges if e.kind == "arc"]

    if kinds == ["circle"]:
        return LoopClass("circle", 2 * loop.edges[0].radius_mm, 2 * loop.edges[0].radius_mm, cx, through is not False and through is True,
                         "" if through else "through-cut not confirmed", through)

    if "other" in kinds:
        return LoopClass("irregular", None, None, cx, False, "outline contains non-line/arc edges (spline/ellipse); narrowest width not computed", through)

    # --- slot: 2 equal parallel lines + 2 half-circle arcs ------------------------------
    if len(lines) == 2 and len(arcs) == 2 and len(loop.edges) == 4:
        d0, d1 = _dir2(lines[0], u, v, o), _dir2(lines[1], u, v, o)
        parallel = abs(d0[0] * d1[1] - d0[1] * d1[0]) < math.sin(math.radians(ANG))
        a_pt = g.to_2d(lines[1].points[0], o, u, v)
        b_pt = g.to_2d(lines[0].points[0], o, u, v)
        sep = abs((a_pt[0] - b_pt[0]) * d0[1] - (a_pt[1] - b_pt[1]) * d0[0])
        r = arcs[0].radius_mm
        if (parallel and _close(d0[2], d1[2]) and all(a.sweep_deg and abs(a.sweep_deg - 180) <= ANG * 2 for a in arcs)
                and all(_close(a.radius_mm, r) for a in arcs) and _close(2 * r, sep)):
            return LoopClass("slot", 2 * r, d0[2] + 2 * r, cx, through is True, "" if through else "through-cut not confirmed", through)

    # --- rectangle (optionally with corner radii): 4 lines forming two perpendicular parallel pairs ----
    if len(lines) == 4 and len(arcs) in (0, 4) and len(loop.edges) == 4 + len(arcs):
        ds = [_dir2(e, u, v, o) for e in lines]
        def par(a, b):
            return abs(a[0] * b[1] - a[1] * b[0]) < math.sin(math.radians(ANG))
        def perp(a, b):
            return abs(a[0] * b[0] + a[1] * b[1]) < math.sin(math.radians(ANG))
        pairs = [(i, j) for i in range(4) for j in range(i + 1, 4) if par(ds[i], ds[j])]
        if len(pairs) == 2 and perp(ds[pairs[0][0]], ds[pairs[1][0]]):
            w = _extent(p2, ds[pairs[0][0]])
            h = _extent(p2, ds[pairs[1][0]])
            ok_arcs = all(a.sweep_deg and abs(a.sweep_deg - 90) <= ANG * 2 for a in arcs)
            if ok_arcs:
                return LoopClass("rect", min(w, h), max(w, h), cx, through is True, "" if through else "through-cut not confirmed", through)

    return LoopClass("irregular", None, None, cx, False,
                     "irregular outline; narrowest width is not computed, so size rules cannot be confirmed", through)


def _extent(p2, d):
    s = [x * d[0] + y * d[1] for x, y in p2]
    return max(s) - min(s)


def to_cutout(lc: LoopClass, loop: LoopDesc, **dist) -> Optional[Cutout]:
    """LoopClass -> engine Cutout (None for circles/ignored: circles are holes, ignored are not manufacturing features)."""
    if lc.kind in ("circle", "ignored"):
        return None
    return Cutout(cutout_kind=lc.kind, min_dimension_mm=lc.min_dimension_mm, length_mm=lc.length_mm,
                  position_mm=lc.centroid_mm, certain=lc.certain and lc.min_dimension_mm is not None,
                  uncertainty_reason=lc.reason, ref=loop.ref, **dist)


def dedupe_sheet_sides(items, thickness_mm, tol_mm=0.05):
    """Each through-cut appears once per sheet face (top and bottom). Keep one per physical feature.

    items: list of (centroid_xyz_mm, normal, payload). Two items are the same feature when their centroids differ
    only along the sheet normal by ~0 or ~thickness (within tol), in the in-plane coordinates they coincide.
    """
    kept = []
    for c, n, payload in items:
        un = g.unit(n)
        dup = False
        for kc, kn, _ in kept:
            if abs(abs(g.dot(un, g.unit(kn))) - 1) > 1e-3:
                continue
            d = g.sub(c, kc)
            along = g.dot(d, un)
            perp = g.norm(g.sub(d, tuple(along * x for x in un)))
            if perp <= tol_mm and (abs(along) <= tol_mm or (thickness_mm and abs(abs(along) - thickness_mm) <= max(tol_mm, 0.03 * thickness_mm))):
                dup = True
                break
        if not dup:
            kept.append((c, n, payload))
    return kept
