"""Fusion API -> dfm_engine.PartModel.

All Fusion lengths are centimetres; the engine uses millimetres (CM = 10).
Anything that cannot be measured is recorded in PartModel.unsupported, never guessed.

API usage status is tracked in docs/API_VERIFICATION.md. Every Fusion member used here was
checked against the Autodesk API reference (help.autodesk.com/cloudhelp/ENU/Fusion-360-API);
the *behavioural* assumptions (marked ASSUMPTION) still need a run in real Fusion.
"""
from __future__ import annotations
import math

import adsk.core
import adsk.fusion

from dfm_engine import Bend, Flange, GeometryRef, Hole, PartModel
from dfm_engine import geometry as g
from .log import get_logger

CM = 10.0
ANG_TOL = 1e-3
LEN_TOL_CM = 1e-3
log = get_logger()


class ExtractionError(Exception):
    """User-facing problem (message is shown in the palette)."""


def _pt(p):
    return (p.x, p.y, p.z)


def _vec(v):
    return (v.x, v.y, v.z)


def _token(entity):
    try:
        return entity.entityToken
    except Exception:
        return None


def _surface_type(face):
    try:
        return face.geometry.surfaceType
    except Exception:
        return None


def _curve_type(edge):
    try:
        return edge.geometry.curveType
    except Exception:
        return None


def _is_plane(face):
    return _surface_type(face) == adsk.core.SurfaceTypes.PlaneSurfaceType


def _is_cyl(face):
    return _surface_type(face) == adsk.core.SurfaceTypes.CylinderSurfaceType


def _is_circle(edge):
    return _curve_type(edge) == adsk.core.Curve3DTypes.Circle3DCurveType


def _is_line(edge):
    return _curve_type(edge) == adsk.core.Curve3DTypes.Line3DCurveType


def _edge_len(edge):
    return edge.length  # BRepEdge.length: centimetres


def _edge_points(edge, tol_cm=0.005):
    """Polyline for an edge (cm). CurveEvaluator3D.getStrokes(from, to, tolerance) -> (ok, [Point3D])."""
    ok, lo, hi = edge.evaluator.getParameterExtents()
    if ok:
        ok, pts = edge.evaluator.getStrokes(lo, hi, tol_cm)
        if ok and pts:
            return [_pt(p) for p in pts]
    return [_pt(edge.startVertex.geometry), _pt(edge.endVertex.geometry)]


def _other_face(edge, face):
    for f in edge.faces:
        if f.tempId != face.tempId:
            return f
    return None


# ---------------------------------------------------------------- body selection
def _all_solid_bodies(design):
    bodies = [b for b in design.rootComponent.bRepBodies if b.isSolid]
    for occ in design.rootComponent.allOccurrences:
        bodies.extend(b for b in occ.bRepBodies if b.isSolid)
    return bodies


def _select_body(app, design, warnings):
    bodies = _all_solid_bodies(design)
    log.info("bodies: %s", [(b.name, b.isSheetMetal, b.isVisible) for b in bodies])
    sel = app.userInterface.activeSelections
    for i in range(sel.count):
        b = adsk.fusion.BRepBody.cast(sel.item(i).entity)
        if b:
            if not b.isSheetMetal:
                raise ExtractionError(f"Selected body '{b.name}' is not a sheet metal body. Phase 1 supports native Fusion sheet metal only.")
            return b
    sm = [b for b in bodies if b.isSheetMetal and b.isVisible]
    if not sm:
        raise ExtractionError("No visible sheet metal body found. Phase 1 supports native Fusion sheet metal only "
                              "(a folded sheet metal body, created with the Sheet Metal tools).")
    if len(sm) > 1:
        warnings.append(f"{len(sm)} sheet metal bodies found; analysing the largest. Select a body to analyse a specific one.")
        sm.sort(key=lambda b: b.volume, reverse=True)
    return sm[0]


# ---------------------------------------------------------------- thickness
def _thickness_from_rule(comp):
    """Component.activeSheetMetalRule -> SheetMetalRule.thickness (SheetMetalRuleValue).value, cm. May be null."""
    rule = comp.activeSheetMetalRule
    if rule is None:
        return None
    v = rule.thickness.value
    return v * CM if v and v > 0 else None


def _thickness_from_geometry(body):
    """CROSS-CHECK/FALLBACK ONLY. Smallest distance between the largest planar face and another
    parallel planar face (orientation-agnostic: face-normal sign conventions are not relied on)."""
    planes = []
    for f in body.faces:
        if _is_plane(f):
            ok, n = f.evaluator.getNormalAtPoint(f.pointOnFace)
            if ok:
                planes.append((f.area, _pt(f.pointOnFace), g.unit(_vec(n))))
    planes.sort(key=lambda t: t[0], reverse=True)
    for _, p0, n0 in planes[:4]:
        ds = [abs(g.dot(g.sub(p1, p0), n0)) for _, p1, n1 in planes if abs(g.dot(n0, n1)) > 0.9999]
        ds = [d for d in ds if d > LEN_TOL_CM]
        if ds:
            return min(ds) * CM
    return None


# ---------------------------------------------------------------- features
def _find_holes(body, t_cm):
    """Through holes: a cylindrical face with exactly two full-circle edges, coaxial and t apart.
    A straight seam edge of length ~t is tolerated (ASSUMPTION: Fusion may or may not expose one)."""
    holes = []
    for f in body.faces:
        if not _is_cyl(f):
            continue
        edges = list(f.edges)
        circles = [e for e in edges if _is_circle(e)]
        others = [e for e in edges if not _is_circle(e)]
        if len(circles) != 2:
            continue
        if any(not _is_line(e) or abs(_edge_len(e) - t_cm) > 0.02 * t_cm for e in others):
            continue
        c0, c1 = circles[0].geometry, circles[1].geometry
        if abs(g.norm(g.sub(_pt(c0.center), _pt(c1.center))) - t_cm) > 0.02 * t_cm:
            continue
        holes.append((f, circles, c0.radius))
    return holes


def _find_bends(body, t_cm):
    """Cylindrical faces with >=2 straight axial edges longer than the thickness (slot ends excluded)."""
    bends = []
    for f in body.faces:
        if not _is_cyl(f):
            continue
        cyl = f.geometry
        axis = g.unit(_vec(cyl.axis))
        lines = []
        for e in f.edges:
            if _is_line(e) and _edge_len(e) > 1.05 * t_cm:
                d = g.sub(_pt(e.endVertex.geometry), _pt(e.startVertex.geometry))
                if abs(abs(g.dot(g.unit(d), axis)) - 1) < ANG_TOL:
                    lines.append(e)
        if len(lines) >= 2:
            bends.append((f, lines, cyl.radius, _pt(cyl.origin), axis))
    return bends


def _group_bends(bends):
    """Group coaxial bend faces (inner + outer surface of one bend)."""
    groups = []
    for b in bends:
        for grp in groups:
            _, _, _, o, ax = grp[0]
            if abs(abs(g.dot(ax, b[4])) - 1) < ANG_TOL:
                off = g.sub(b[3], o)
                perp = g.sub(off, tuple(g.dot(off, ax) * c for c in ax))
                if g.norm(perp) < LEN_TOL_CM:
                    grp.append(b)
                    break
        else:
            groups.append([b])
    return groups


def _arc_angle_deg(face):
    """Sweep of the first Arc3D edge (Arc3D.startAngle/endAngle are radians)."""
    for e in face.edges:
        if _curve_type(e) == adsk.core.Curve3DTypes.Arc3DCurveType:
            a = e.geometry
            return math.degrees(abs(a.endAngle - a.startAngle))
    return None


def _flange_length_mm(planar, tangent_edge):
    pts = _edge_points(tangent_edge)
    a, b = pts[0], pts[-1]
    d = g.unit(g.sub(b, a))
    ok, n = planar.evaluator.getNormalAtPoint(planar.pointOnFace)
    u = g.unit(g.cross(g.unit(_vec(n)), d))
    far = 0.0
    for e in planar.edges:
        for p in _edge_points(e):
            far = max(far, abs(g.dot(g.sub(p, a), u)))
    return far * CM


def _hole_distances(hole_face, circle_edge, radius_cm, bend_face_ids):
    """(center_mm, dist_to_edge_mm, dist_to_bend_mm, has_adjacent_bend) measured on one sheet face."""
    planar = _other_face(circle_edge, hole_face)
    if planar is None or not _is_plane(planar):
        return None
    center = _pt(circle_edge.geometry.center)
    edge_d = bend_d = None
    has_bend = False
    for e in planar.edges:
        other = _other_face(e, planar)
        if _is_circle(e) and other is not None and _is_cyl(other):
            continue  # a hole boundary (this or another hole); hole-to-hole spacing is not checked
        d = g.point_polyline_distance(center, _edge_points(e)) - radius_cm
        if other is not None and other.tempId in bend_face_ids:
            has_bend = True
            bend_d = d if bend_d is None else min(bend_d, d)
        else:
            edge_d = d if edge_d is None else min(edge_d, d)
    mm = lambda v: None if v is None else v * CM
    return tuple(c * CM for c in center), mm(edge_d), mm(bend_d), has_bend


def _flat_dimensions(comp, unsupported):
    """Component.flatPattern (null if none) -> FlatPattern.flatBody -> BRepBody.boundingBox."""
    fp = comp.flatPattern
    if fp is None:
        unsupported["flat_dimensions"] = "No flat pattern in this design. Create one (Sheet Metal > Create Flat Pattern)."
        return None
    body = fp.flatBody
    if body is None:
        unsupported["flat_dimensions"] = "Flat pattern exists but exposes no flat body."
        return None
    bb = body.boundingBox
    dims = sorted([abs(bb.maxPoint.x - bb.minPoint.x), abs(bb.maxPoint.y - bb.minPoint.y),
                   abs(bb.maxPoint.z - bb.minPoint.z)], reverse=True)
    return (dims[0] * CM, dims[1] * CM)  # axis-aligned box; may overestimate a rotated pattern


def _log_face_census(body, t_cm):
    counts = {}
    for f in body.faces:
        k = _surface_type(f)
        counts[k] = counts.get(k, 0) + 1
    log.info("face census (surfaceType -> count): %s", counts)
    n = 0
    for f in body.faces:
        if _is_cyl(f) and n < 40:
            n += 1
            kinds = [_curve_type(e) for e in f.edges]
            log.info("cyl face r=%.4fcm edges=%s", f.geometry.radius, kinds)
    log.info("thickness used for classification: %.4f cm", t_cm)


# ---------------------------------------------------------------- entry point
def extract_part(app):
    """Returns (PartModel, warnings). Raises ExtractionError for user-facing problems."""
    design = adsk.fusion.Design.cast(app.activeProduct)
    if design is None:
        raise ExtractionError("No active Fusion design. Open a design (Design workspace) first.")
    warnings, unsupported = [], {}
    body = _select_body(app, design, warnings)
    comp = body.parentComponent

    mat = None
    m = body.material or comp.material
    if m:
        mat = m.name
    else:
        unsupported["material"] = "No material assigned to the body or component."

    bb = body.boundingBox
    folded = (abs(bb.maxPoint.x - bb.minPoint.x) * CM, abs(bb.maxPoint.y - bb.minPoint.y) * CM,
              abs(bb.maxPoint.z - bb.minPoint.z) * CM)
    part = PartModel(name=body.name, material_name=mat, folded_dimensions_mm=folded,
                     body_ref=GeometryRef("body", _token(body), body.name), unsupported=unsupported)

    t_rule = _thickness_from_rule(comp)
    t_geo = _thickness_from_geometry(body)
    log.info("thickness: rule=%s mm, geometry=%s mm", t_rule, t_geo)
    if t_rule is not None:
        part.thickness_mm, part.thickness_source = t_rule, "sheet_metal_rule"
        if t_geo is not None and abs(t_geo - t_rule) > 0.02 * t_rule:
            warnings.append(f"Rule thickness {t_rule:.3f} mm differs from geometry-derived {t_geo:.3f} mm; using the rule value.")
    elif t_geo is not None:
        part.thickness_mm, part.thickness_source = t_geo, "derived_from_geometry"
        warnings.append("No active sheet metal rule; thickness derived from geometry.")
    else:
        unsupported["thickness"] = "No active sheet metal rule and no opposed parallel faces found."
        for k in ("holes", "bends", "flanges", "hole_edge_distance", "hole_bend_distance"):
            unsupported[k] = "requires sheet thickness"
        part.flat_dimensions_mm = _flat_dimensions(comp, unsupported)
        return part, warnings
    t_cm = part.thickness_mm / CM
    _log_face_census(body, t_cm)

    bends_raw = _find_bends(body, t_cm)
    groups = _group_bends(bends_raw)
    bend_face_ids = {b[0].tempId for b in bends_raw}
    inner_faces = {}
    for i, grp in enumerate(groups, 1):
        if len(grp) >= 2:
            inner, r_mm = min(grp, key=lambda b: b[2]), min(b[2] for b in grp) * CM
        else:
            inner, r_mm = grp[0], None
            warnings.append(f"Bend {i}: only one cylindrical surface found; radius not reported.")
        part.bends.append(Bend(inner_radius_mm=r_mm, angle_deg=_arc_angle_deg(inner[0]),
                               ref=GeometryRef("bend", _token(inner[0]), f"Bend {i}")))
        if r_mm is not None:
            inner_faces[inner[0].tempId] = (inner, i)

    flange_faces = {}
    for inner, i in inner_faces.values():
        for e in inner[1]:
            pf = _other_face(e, inner[0])
            if pf is not None and _is_plane(pf):
                flange_faces.setdefault(pf.tempId, [pf, []])[1].append((e, i))
    for n, (pf, tang) in enumerate(flange_faces.values(), 1):
        part.flanges.append(Flange(length_mm=_flange_length_mm(pf, tang[0][0]),
                                   is_terminal=len({i for _, i in tang}) == 1,
                                   ref=GeometryRef("flange", _token(pf), f"Flange {n}")))

    for n, (hf, circles, r_cm) in enumerate(_find_holes(body, t_cm), 1):
        try:
            res = _hole_distances(hf, circles[0], r_cm, bend_face_ids)
        except Exception:
            log.exception("hole %d distance measurement failed", n)
            res = None
        pos, de, db, hb = res if res else (None, None, None, None)
        part.holes.append(Hole(diameter_mm=2 * r_cm * CM, position_mm=pos, dist_to_edge_mm=de,
                               dist_to_bend_mm=db, has_adjacent_bend=hb if res else None,
                               ref=GeometryRef("hole", _token(hf), f"Hole {n}")))

    part.flat_dimensions_mm = _flat_dimensions(comp, unsupported)
    unsupported.setdefault("slots_and_cutouts",
                           "Only circular through holes are extracted; slots and non-circular cutouts are not checked.")
    log.info("extracted: thickness=%s (%s) material=%s bends=%d flanges=%d holes=%d flat=%s unsupported=%s",
             part.thickness_mm, part.thickness_source, mat, len(part.bends), len(part.flanges),
             len(part.holes), part.flat_dimensions_mm, list(unsupported))
    return part, warnings
