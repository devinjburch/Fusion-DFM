"""Fusion API -> dfm_engine.PartModel.

All Fusion lengths are centimetres; the engine uses millimetres (CM = 10).
Anything that cannot be measured is recorded in PartModel.unsupported, never guessed.
NOTE: written against the documented Fusion API but NOT executed against a live Fusion
install in the authoring environment; see docs/LIMITATIONS.md ("Needs live verification").
"""
from __future__ import annotations
import math

import adsk.core
import adsk.fusion

from dfm_engine import Bend, Flange, GeometryRef, Hole, PartModel
from dfm_engine import geometry as g

CM = 10.0
ANG_TOL = 1e-3
LEN_TOL_CM = 1e-3


class ExtractionError(Exception):
    pass


def _pt(p):  # Point3D -> tuple (cm)
    return (p.x, p.y, p.z)


def _vec(v):
    return (v.x, v.y, v.z)


def _token(entity) -> str | None:
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


def _edge_points(edge, tol_cm=0.005):
    """Polyline approximation of an edge (cm)."""
    ev = edge.evaluator
    ok, lo, hi = ev.getParameterExtents()
    if ok:
        ok, pts = ev.getStrokes(lo, hi, tol_cm)
        if ok and pts:
            return [_pt(p) for p in pts]
    return [_pt(edge.startVertex.geometry), _pt(edge.endVertex.geometry)]


# ---------------------------------------------------------------- body selection
def _candidate_bodies(design):
    bodies = []
    root = design.rootComponent
    for b in root.bRepBodies:
        if b.isSolid and b.isVisible:
            bodies.append(b)
    for occ in root.allOccurrences:
        for b in occ.bRepBodies:
            if b.isSolid and b.isVisible:
                bodies.append(b)
    return bodies


def _select_body(app, design, warnings):
    sel = app.userInterface.activeSelections
    for i in range(sel.count):
        e = adsk.fusion.BRepBody.cast(sel.item(i).entity)
        if e:
            return e
    bodies = _candidate_bodies(design)
    if not bodies:
        raise ExtractionError("No visible solid bodies found. Open a sheet metal design.")
    sm = [b for b in bodies if getattr(b, "isSheetMetal", False) is True]
    pool = sm or bodies
    if len(pool) > 1:
        warnings.append(f"{len(pool)} bodies found; analysing the largest. Select a body to analyse a specific one.")
        pool = sorted(pool, key=lambda b: b.volume, reverse=True)
    return pool[0]


# ---------------------------------------------------------------- thickness
def _thickness_from_rule(body, design):
    """Try the active sheet metal rule. Attribute names are probed, not assumed."""
    comp = body.parentComponent
    for holder in (comp, design):
        rule = getattr(holder, "activeSheetMetalRule", None)
        if rule is not None:
            thick = getattr(rule, "thickness", None)
            val = getattr(thick, "value", None)
            if isinstance(val, (int, float)) and val > 0:
                return val * CM, "sheet_metal_rule"
    return None


def _thickness_from_geometry(body):
    """Smallest distance from the largest planar face to a parallel, opposed planar face."""
    planes = []
    for f in body.faces:
        if _surface_type(f) == adsk.core.SurfaceTypes.PlaneSurfaceType:
            ok, n = f.evaluator.getNormalAtPoint(f.pointOnFace)
            if ok:
                planes.append((f.area, _pt(f.pointOnFace), g.unit(_vec(n))))
    if len(planes) < 2:
        return None
    planes.sort(key=lambda t: t[0], reverse=True)
    best = None
    for _, p0, n0 in planes[:4]:
        for _, p1, n1 in planes:
            if g.dot(n0, n1) < -0.9999:
                d = abs(g.dot(g.sub(p1, p0), n0))
                if d > LEN_TOL_CM and (best is None or d < best):
                    best = d
        if best is not None:
            break
    return (best * CM, "derived_from_geometry") if best else None


# ---------------------------------------------------------------- features
def _is_circle(edge):
    return _curve_type(edge) == adsk.core.Curve3DTypes.Circle3DCurveType


def _is_line(edge):
    return _curve_type(edge) == adsk.core.Curve3DTypes.Line3DCurveType


def _other_face(edge, face):
    for f in edge.faces:
        if f.tempId != face.tempId:
            return f
    return None


def _find_holes(body, t_cm):
    """Through holes = cylindrical faces bounded only by two coaxial full circles, t apart."""
    holes = []
    for f in body.faces:
        if _surface_type(f) != adsk.core.SurfaceTypes.CylinderSurfaceType:
            continue
        edges = list(f.edges)
        if len(edges) != 2 or not all(_is_circle(e) for e in edges):
            continue
        c0, c1 = edges[0].geometry, edges[1].geometry
        sep = g.norm(g.sub(_pt(c0.center), _pt(c1.center)))
        if abs(sep - t_cm) > 0.02 * t_cm:
            continue  # blind/counterbore/other; not a simple through hole
        holes.append((f, edges, c0.radius))
    return holes


def _find_bends(body, t_cm):
    """Cylindrical faces with axial straight edges longer than the thickness (slot ends excluded)."""
    bends = []
    for f in body.faces:
        if _surface_type(f) != adsk.core.SurfaceTypes.CylinderSurfaceType:
            continue
        cyl = f.geometry
        axis = g.unit(_vec(cyl.axis))
        lines = []
        for e in f.edges:
            if _is_line(e):
                a, b = _pt(e.startVertex.geometry), _pt(e.endVertex.geometry)
                d = g.sub(b, a)
                if g.norm(d) > 1.05 * t_cm and abs(abs(g.dot(g.unit(d), axis)) - 1) < ANG_TOL:
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
    for e in face.edges:
        if _curve_type(e) == adsk.core.Curve3DTypes.Arc3DCurveType:
            try:
                a = e.geometry
                return math.degrees(abs(a.endAngle - a.startAngle))
            except Exception:
                return None
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


def _hole_distances(hole_face, hole_edges, radius_cm, bend_face_ids):
    """Return (center_mm, dist_to_edge_mm, dist_to_bend_mm, has_adjacent_bend)."""
    circle = hole_edges[0]
    planar = _other_face(circle, hole_face)
    if planar is None or _surface_type(planar) != adsk.core.SurfaceTypes.PlaneSurfaceType:
        return None
    center = _pt(circle.geometry.center)
    edge_d, bend_d, has_bend = None, None, False
    for e in planar.edges:
        if _is_circle(e):
            continue  # other holes: hole-to-hole spacing is not checked
        other = _other_face(e, planar)
        pts = _edge_points(e)
        d = g.point_polyline_distance(center, pts) - radius_cm
        if other is not None and other.tempId in bend_face_ids:
            has_bend = True
            bend_d = d if bend_d is None else min(bend_d, d)
        else:
            edge_d = d if edge_d is None else min(edge_d, d)
    return (tuple(c * CM for c in center),
            None if edge_d is None else edge_d * CM,
            None if bend_d is None else bend_d * CM, has_bend)


# ---------------------------------------------------------------- flat pattern
def _flat_dimensions(comp, unsupported):
    try:
        fp = getattr(comp, "flatPattern", None)
    except Exception:
        fp = None
    if fp is None:
        unsupported["flat_dimensions"] = "No flat pattern in this design. Create one in the sheet metal environment."
        return None
    body = getattr(fp, "flatBody", None)
    if body is None:
        bodies = getattr(fp, "flatBodies", None)
        body = bodies.item(0) if bodies and bodies.count else None
    if body is None:
        unsupported["flat_dimensions"] = "Flat pattern exists but its body is not exposed by this API version."
        return None
    bb = body.boundingBox
    dims = sorted([abs(bb.maxPoint.x - bb.minPoint.x), abs(bb.maxPoint.y - bb.minPoint.y),
                   abs(bb.maxPoint.z - bb.minPoint.z)], reverse=True)
    return (dims[0] * CM, dims[1] * CM)  # axis-aligned; may overestimate a rotated pattern


# ---------------------------------------------------------------- entry point
def extract_part(app):
    """Returns (PartModel, warnings:list[str]). Raises ExtractionError for user-facing problems."""
    design = adsk.fusion.Design.cast(app.activeProduct)
    if design is None:
        raise ExtractionError("No active Fusion design. Open a design first.")
    warnings, unsupported = [], {}
    body = _select_body(app, design, warnings)
    comp = body.parentComponent
    if getattr(body, "isSheetMetal", None) is False:
        warnings.append("Body is not flagged as sheet metal; results may be unreliable.")
    elif getattr(body, "isSheetMetal", None) is None:
        warnings.append("Could not confirm the body is sheet metal (API property unavailable).")

    mat = None
    try:
        m = body.material or comp.material
        mat = m.name if m else None
    except Exception:
        pass
    if not mat:
        unsupported["material"] = "No material assigned to the body or component."

    bb = body.boundingBox
    folded = tuple(abs(c) * CM for c in (bb.maxPoint.x - bb.minPoint.x, bb.maxPoint.y - bb.minPoint.y,
                                         bb.maxPoint.z - bb.minPoint.z))
    part = PartModel(name=body.name, material_name=mat, folded_dimensions_mm=folded,
                     body_ref=GeometryRef("body", _token(body), body.name), unsupported=unsupported)

    th = _thickness_from_rule(body, design) or _thickness_from_geometry(body)
    if th is None:
        unsupported["thickness"] = "Thickness not available from a sheet metal rule or from opposed parallel faces."
        for k in ("holes", "bends", "flanges", "hole_edge_distance", "hole_bend_distance"):
            unsupported[k] = "requires sheet thickness"
        part.flat_dimensions_mm = _flat_dimensions(comp, unsupported)
        return part, warnings
    part.thickness_mm, part.thickness_source = th
    t_cm = part.thickness_mm / CM

    bends_raw = _find_bends(body, t_cm)
    groups = _group_bends(bends_raw)
    bend_face_ids = {b[0].tempId for b in bends_raw}
    inner_faces = {}
    for i, grp in enumerate(groups, 1):
        ref_t = None
        if len(grp) >= 2:
            inner = min(grp, key=lambda b: b[2])
            r_mm = inner[2] * CM
        else:
            inner, r_mm = grp[0], None  # cannot tell inner from outer with a single surface
            warnings.append(f"Bend {i}: only one cylindrical surface found; radius not reported.")
        ref_t = _token(inner[0])
        part.bends.append(Bend(inner_radius_mm=r_mm, angle_deg=_arc_angle_deg(inner[0]),
                               ref=GeometryRef("bend", ref_t, f"Bend {i}")))
        if r_mm is not None:
            inner_faces[inner[0].tempId] = (inner, i)

    # flanges: planar faces tangent to an inner bend surface
    flange_faces = {}
    for fid, (inner, i) in inner_faces.items():
        for e in inner[1]:
            pf = _other_face(e, inner[0])
            if pf is not None and _surface_type(pf) == adsk.core.SurfaceTypes.PlaneSurfaceType:
                flange_faces.setdefault(pf.tempId, [pf, []])[1].append((e, i))
    for n, (pf, tang) in enumerate(flange_faces.values(), 1):
        bend_ids = {i for _, i in tang}
        part.flanges.append(Flange(length_mm=_flange_length_mm(pf, tang[0][0]),
                                   is_terminal=len(bend_ids) == 1,
                                   ref=GeometryRef("flange", _token(pf), f"Flange {n}")))

    for n, (hf, hedges, r_cm) in enumerate(_find_holes(body, t_cm), 1):
        try:
            res = _hole_distances(hf, hedges, r_cm, bend_face_ids)
        except Exception:
            res = None
        pos, de, db, hb = res if res else (None, None, None, None)
        part.holes.append(Hole(diameter_mm=2 * r_cm * CM, position_mm=pos, dist_to_edge_mm=de,
                               dist_to_bend_mm=db, has_adjacent_bend=hb if res else None,
                               ref=GeometryRef("hole", _token(hf), f"Hole {n}")))

    part.flat_dimensions_mm = _flat_dimensions(comp, unsupported)
    unsupported.setdefault("slots_and_cutouts", "Only circular through holes are extracted; slots and non-circular cutouts are not checked.")
    return part, warnings
