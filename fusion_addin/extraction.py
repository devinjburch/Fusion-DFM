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
from dfm_engine.features import EdgeDesc, LoopDesc, classify_loop, dedupe_sheet_sides, to_cutout
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
    try:
        v = rule.thickness.value
    except RuntimeError as e:
        # Seen live while the flat pattern environment was active: "InternalValidationError : xlDesign".
        log.warning("sheet metal rule thickness not readable (%s); falling back to geometry", e)
        return None
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


def _outer_boundary(planar):
    """Edges of the face's OUTER loop(s) (BRepFace.loops, BRepLoop.isOuter, BRepLoop.edges)."""
    out = []
    for loop in planar.loops:
        if loop.isOuter:
            out.extend(loop.edges)
    return out


def _bend_zone_mm(bend_info, bend_face, t_mm):
    """Upper bound of tangent line -> bend centerline: (R_inner + t) * angle / 2 (K-factor <= 1). None if unknown."""
    info = bend_info.get(bend_face.tempId)
    if not info or info[0] is None or info[1] is None:
        return None
    return (info[0] + t_mm) * math.radians(info[1]) / 2


def _boundary_distances(planar, own_edge_ids, center_pts, bend_face_ids, bend_info, t_mm, radius_cm=0.0):
    """Distances (cm) from a feature to the sheet's outer edges and to adjacent bend tangent lines.
    Returns (dist_edge_cm | None, dist_bend_cm | None, has_bend, zone_mm | None)."""
    edge_d = bend_d = None
    zone = None
    has_bend = False
    for e in _outer_boundary(planar):
        other = _other_face(e, planar)
        d = g.polyline_distance(center_pts, _edge_points(e)) - radius_cm
        if other is not None and other.tempId in bend_face_ids:
            has_bend = True
            if bend_d is None or d < bend_d:
                bend_d, zone = d, _bend_zone_mm(bend_info, other, t_mm)
        else:
            edge_d = d if edge_d is None else min(edge_d, d)
    return edge_d, bend_d, has_bend, zone


def _hole_distances(hole_face, circle_edge, radius_cm, bend_face_ids, bend_info, t_mm):
    """(center_mm, dist_to_edge_mm, dist_to_bend_mm, has_adjacent_bend, bend_zone_max_mm) on one sheet face.
    Edge distance is to the sheet's OUTER boundary (other cutouts/holes are not counted)."""
    planar = _other_face(circle_edge, hole_face)
    if planar is None or not _is_plane(planar):
        return None
    center = _pt(circle_edge.geometry.center)
    ed, bd, hb, zone = _boundary_distances(planar, set(), [center], bend_face_ids, bend_info, t_mm, radius_cm)
    mm = lambda v: None if v is None else v * CM
    return tuple(c * CM for c in center), mm(ed), mm(bd), hb, zone


# ---------------------------------------------------------------- cutouts (slots, rectangles, irregular)
def _wall_height_mm(edge, face, normal):
    """Extent of the face on the other side of `edge`, measured along the sheet-face normal (cm -> mm)."""
    other = _other_face(edge, face)
    if other is None:
        return None
    base = _pt(edge.startVertex.geometry)
    hs = []
    for e in other.edges:
        for p in _edge_points(e):
            hs.append(abs(g.dot(g.sub(p, base), normal)))
    return max(hs) * CM if hs else None


def _edge_desc(edge, face, normal):
    ct = _curve_type(edge)
    pts = [tuple(c * CM for c in p) for p in _edge_points(edge)]
    wall = _wall_height_mm(edge, face, normal)
    if ct == adsk.core.Curve3DTypes.Line3DCurveType:
        return EdgeDesc("line", [pts[0], pts[-1]], wall_height_mm=wall)
    if ct == adsk.core.Curve3DTypes.Arc3DCurveType:
        a = edge.geometry
        return EdgeDesc("arc", pts, radius_mm=a.radius * CM, sweep_deg=math.degrees(abs(a.endAngle - a.startAngle)), wall_height_mm=wall)
    if ct == adsk.core.Curve3DTypes.Circle3DCurveType:
        return EdgeDesc("circle", pts, radius_mm=edge.geometry.radius * CM, wall_height_mm=wall)
    return EdgeDesc("other", pts, wall_height_mm=wall)


def _find_cutouts(body, t_mm, bend_face_ids, bend_info, warnings):
    """Non-circular inner loops of planar sheet faces -> Cutout list (via dfm_engine.features, which is CAD-free).
    Circular loops are holes (found via cylinders); non-through loops are ignored, with a log line."""
    items = []
    for f in body.faces:
        if not _is_plane(f):
            continue
        inner = [lp for lp in f.loops if not lp.isOuter]
        if not inner:
            continue
        ok, n = f.evaluator.getNormalAtPoint(f.pointOnFace)
        if not ok:
            continue
        normal = g.unit(_vec(n))
        for lp in inner:
            try:
                edges = [ce.edge for ce in lp.coEdges]
                desc = LoopDesc([_edge_desc(e, f, normal) for e in edges], normal, GeometryRef("cutout", _token(f), "Cutout"))
                lc = classify_loop(desc, t_mm)
            except Exception:
                log.exception("loop classification failed on face %s", getattr(f, "tempId", "?"))
                continue
            if lc.kind in ("circle", "ignored"):
                if lc.kind == "ignored":
                    log.info("ignored inner loop on face %s: %s", f.tempId, lc.reason)
                continue
            dist = {}
            try:
                pts_cm = [tuple(c / CM for c in p) for e in desc.edges for p in e.points]
                ed, bd, hb, zone = _boundary_distances(f, set(), pts_cm, bend_face_ids, bend_info, t_mm)
                dist = dict(dist_to_edge_mm=None if ed is None else ed * CM, dist_to_bend_mm=None if bd is None else bd * CM,
                            has_adjacent_bend=hb, bend_zone_max_mm=zone)
            except Exception:
                log.exception("cutout distance measurement failed")
            cut = to_cutout(lc, desc, **dist)
            items.append((lc.centroid_mm, normal, cut))
    kept = dedupe_sheet_sides(items, t_mm)
    cuts = [c for _, _, c in kept]
    for i, c in enumerate(cuts, 1):
        c.ref = GeometryRef("cutout", c.ref.token if c.ref else None, f"{c.cutout_kind.capitalize()} cutout {i}")
    return cuts


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


# ---------------------------------------------------------------- body extraction
def _extract_body(app, design, body, warnings, component_path="", instance_count=1):
    comp = body.parentComponent
    unsupported = {}
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
                     body_ref=GeometryRef("body", _token(body), body.name), unsupported=unsupported,
                     component_path=component_path, instance_count=instance_count)

    t_rule = _thickness_from_rule(comp)
    t_geo = _thickness_from_geometry(body)
    log.info("[%s] thickness: rule=%s mm, geometry=%s mm", body.name, t_rule, t_geo)
    if t_rule is not None:
        part.thickness_mm, part.thickness_source = t_rule, "sheet_metal_rule"
        if t_geo is not None and abs(t_geo - t_rule) > 0.02 * t_rule:
            warnings.append(f"{body.name}: rule thickness {t_rule:.3f} mm differs from geometry-derived {t_geo:.3f} mm; using the rule value.")
    elif t_geo is not None:
        part.thickness_mm, part.thickness_source = t_geo, "derived_from_geometry"
        why = "No active sheet metal rule" if comp.activeSheetMetalRule is None else "Sheet metal rule thickness not readable"
        warnings.append(f"{body.name}: {why}; thickness derived from geometry.")
    else:
        unsupported["thickness"] = "No readable sheet metal rule and no opposed parallel faces found."
        for k in ("holes", "bends", "flanges", "hole_edge_distance", "hole_bend_distance"):
            unsupported[k] = "requires sheet thickness"
        part.flat_dimensions_mm = _flat_dimensions(comp, unsupported)
        return part
    t_mm = part.thickness_mm
    t_cm = t_mm / CM
    _log_face_census(body, t_cm)

    bends_raw = _find_bends(body, t_cm)
    groups = _group_bends(bends_raw)
    bend_face_ids = {b[0].tempId for b in bends_raw}
    bend_info = {}                       # bend face tempId -> (inner radius mm | None, angle deg | None)
    inner_faces = {}
    bend_angle = {}
    bend_radius = {}
    for i, grp in enumerate(groups, 1):
        if len(grp) >= 2:
            inner, r_mm = min(grp, key=lambda b: b[2]), min(b[2] for b in grp) * CM
        else:
            inner, r_mm = grp[0], None
            warnings.append(f"{body.name}: bend {i}: only one cylindrical surface found; radius not reported.")
        ang = _arc_angle_deg(inner[0])
        length = max(_edge_len(e) for e in inner[1]) * CM
        for b in grp:
            bend_info[b[0].tempId] = (r_mm, ang)
        bend_angle[i], bend_radius[i] = ang, r_mm
        part.bends.append(Bend(inner_radius_mm=r_mm, angle_deg=ang, length_mm=length,
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
        bends_here = {i for _, i in tang}
        length = _flange_length_mm(pf, tang[0][0])
        apex = ang = None
        if len(bends_here) == 1:
            i = next(iter(bends_here))
            ang, r = bend_angle[i], bend_radius[i]
            if ang is not None and r is not None and 0 < ang < 170:
                apex = length + (r + t_mm) * math.tan(math.radians(ang) / 2)   # outer-face apex to flange edge
        part.flanges.append(Flange(length_mm=length, is_terminal=len(bends_here) == 1,
                                   ref=GeometryRef("flange", _token(pf), f"Flange {n}"),
                                   length_apex_mm=apex, bend_angle_deg=ang))

    for n, (hf, circles, r_cm) in enumerate(_find_holes(body, t_cm), 1):
        try:
            res = _hole_distances(hf, circles[0], r_cm, bend_face_ids, bend_info, t_mm)
        except Exception:
            log.exception("hole %d distance measurement failed", n)
            res = None
        pos, de, db, hb, zone = res if res else (None, None, None, None, None)
        part.holes.append(Hole(diameter_mm=2 * r_cm * CM, position_mm=pos, dist_to_edge_mm=de,
                               dist_to_bend_mm=db, has_adjacent_bend=hb if res else None, bend_zone_max_mm=zone,
                               ref=GeometryRef("hole", _token(hf), f"Hole {n}")))

    try:
        part.cutouts = _find_cutouts(body, t_mm, bend_face_ids, bend_info, warnings)
    except Exception:
        log.exception("cutout extraction failed")
        unsupported["slots_and_cutouts"] = "cutout extraction failed (see log); non-circular cutouts are not checked."
    part.flat_dimensions_mm = _flat_dimensions(comp, unsupported)
    log.info("[%s] extracted: thickness=%s (%s) material=%s bends=%d flanges=%d holes=%d cutouts=%d flat=%s unsupported=%s",
             body.name, part.thickness_mm, part.thickness_source, mat, len(part.bends), len(part.flanges),
             len(part.holes), len(part.cutouts), part.flat_dimensions_mm, list(unsupported))
    return part


def extract_part(app):
    """Phase 1 entry point: ONE part (selected sheet metal body, else the largest). Returns (PartModel, warnings)."""
    design = adsk.fusion.Design.cast(app.activeProduct)
    if design is None:
        raise ExtractionError("No active Fusion design. Open a design (Design workspace) first.")
    warnings = []
    body = _select_body(app, design, warnings)
    return _extract_body(app, design, body, warnings), warnings


# ---------------------------------------------------------------- multi-body / assemblies
def _sheet_metal_bodies(design):
    """All visible sheet metal bodies in the root component and in occurrences (any depth).
    Returns (list of (body, occurrence_path, instance_count), skipped_non_sheet_metal).
    Instances of one component share a native body: they are analysed once with instance_count."""
    found = {}
    order = []
    skipped = 0

    def consider(body, path):
        nonlocal skipped
        if not body.isSolid or not body.isVisible:
            return
        if not body.isSheetMetal:
            skipped += 1
            return
        native = body.nativeObject or body       # BRepBody.nativeObject: null when already native
        key = _token(native) or str(id(native))
        if key in found:
            found[key][2] += 1
        else:
            found[key] = [body, path, 1]
            order.append(key)

    for b in design.rootComponent.bRepBodies:
        consider(b, "")
    for occ in design.rootComponent.allOccurrences:
        if not occ.isVisible:
            continue
        for b in occ.bRepBodies:
            consider(b, occ.fullPathName)
    return [tuple(found[k]) for k in order], skipped


def extract_all(app):
    """Phase 2 entry point: every visible sheet metal body. Returns (list[PartModel], warnings)."""
    design = adsk.fusion.Design.cast(app.activeProduct)
    if design is None:
        raise ExtractionError("No active Fusion design. Open a design (Design workspace) first.")
    warnings = []
    sel = app.userInterface.activeSelections
    selected = []
    for i in range(sel.count):
        b = adsk.fusion.BRepBody.cast(sel.item(i).entity)
        if b is not None:
            if not b.isSheetMetal:
                warnings.append(f"Selected body '{b.name}' is not sheet metal and was skipped.")
            else:
                selected.append(b)
    if selected:
        bodies = [(b, b.assemblyContext.fullPathName if b.assemblyContext else "", 1) for b in selected]
        skipped = 0
    else:
        bodies, skipped = _sheet_metal_bodies(design)
    if not bodies:
        raise ExtractionError("No visible sheet metal body found. Phase 1/2 support native Fusion sheet metal only "
                              "(a folded sheet metal body, created with the Sheet Metal tools).")
    if skipped:
        warnings.append(f"{skipped} visible non-sheet-metal body(ies) were skipped.")
    names = [b.name for b, _, _ in bodies]
    parts = []
    for body, path, count in bodies:
        part = _extract_body(app, design, body, warnings, path, count)
        if names.count(body.name) > 1 or path:
            part.name = f"{body.parentComponent.name} / {body.name}"
        parts.append(part)
    log.info("extract_all: %d part(s): %s", len(parts), [p.name for p in parts])
    return parts, warnings
