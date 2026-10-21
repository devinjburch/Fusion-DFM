"""Minimal duck-typed stand-in for the parts of adsk used by fusion_addin (enum values match the
official API: SurfaceTypes Plane=0 Cylinder=1; Curve3DTypes Line3D=0 Arc3D=1 Circle3D=2).
It validates OUR logic only - it cannot prove Fusion behaves like this."""
import math
import sys
import types


class P:
    def __init__(self, x, y, z): self.x, self.y, self.z = x, y, z


def _mod(name, **kw):
    m = types.ModuleType(name); m.__dict__.update(kw); return m


class SurfaceTypes: PlaneSurfaceType = 0; CylinderSurfaceType = 1
class Curve3DTypes: Line3DCurveType = 0; Arc3DCurveType = 1; Circle3DCurveType = 2


class Geo:
    def __init__(self, **kw): self.__dict__.update(kw)


class Edge:
    def __init__(self, kind, a=None, b=None, center=None, radius=None, axis=None, ang=(0, math.pi / 2), pts=None):
        self.kind, self.a, self.b = kind, a, b
        self.faces = []
        if kind == "line":
            self.geometry = Geo(curveType=0)
            self.startVertex = Geo(geometry=P(*a)); self.endVertex = Geo(geometry=P(*b))
            self.length = math.dist(a, b)
            self._pts = [P(*a), P(*b)]
        elif kind == "arc":
            self.geometry = Geo(curveType=1, startAngle=ang[0], endAngle=ang[1], radius=radius if radius is not None else 0.3)
            self.startVertex = Geo(geometry=P(*a)); self.endVertex = Geo(geometry=P(*b))
            self.length = 0.3
            self._pts = [P(*q) for q in pts] if pts else [P(*a), P(*b)]
        elif kind == "spline":
            self.geometry = Geo(curveType=9)
            self.startVertex = Geo(geometry=P(*a)); self.endVertex = Geo(geometry=P(*b))
            self.length = 1.0
            self._pts = [P(*q) for q in pts]
        else:  # circle
            self.geometry = Geo(curveType=2, center=P(*center), radius=radius)
            self.startVertex = self.endVertex = Geo(geometry=P(center[0] + radius, center[1], center[2]))
            self.length = 2 * math.pi * radius
            self._pts = [P(center[0] + radius * math.cos(i * math.pi / 8), center[1] + radius * math.sin(i * math.pi / 8), center[2]) for i in range(17)]
        self.evaluator = Geo(getParameterExtents=lambda: (True, 0.0, 1.0), getStrokes=lambda f, t, tol: (True, self._pts))


class Loop:
    def __init__(self, is_outer, edges):
        self.isOuter, self.edges = is_outer, edges
        self.coEdges = [Geo(edge=e) for e in edges]


class Face:
    _n = 0

    @property
    def loops(self):
        """Fake topology: circle edges on a planar face are inner loops; everything else is the outer loop."""
        if self.geometry.surfaceType == 0:
            inner = [Loop(False, [e]) for e in self.edges if e.kind == "circle"]
            outer = [e for e in self.edges if e.kind != "circle"]
            return ([Loop(True, outer)] if outer else []) + inner + list(getattr(self, "extra_loops", []))
        return [Loop(True, list(self.edges))]

    def __init__(self, geometry, normal=None, point=(0, 0, 0), area=1.0):
        Face._n += 1
        self.tempId, self.geometry, self.area = Face._n, geometry, area
        self.edges, self.entityToken = [], f"tok{Face._n}"
        self.pointOnFace = P(*point)
        self.evaluator = Geo(getNormalAtPoint=lambda p: (True, P(*normal)))

    def link(self, *edges):
        for e in edges:
            self.edges.append(e); e.faces.append(self)


def plane(normal, point, area):
    return Face(Geo(surfaceType=0), normal, point, area)


def cyl(radius, axis, origin):
    return Face(Geo(surfaceType=1, radius=radius, axis=P(*axis), origin=P(*origin)), (0, 0, 1), origin, 1.0)


class Collection(list):
    @property
    def count(self): return len(self)
    def item(self, i): return self[i]


def build_l_bracket(rule_thickness_cm=0.2, with_rule=True, with_flat=False):
    """Folded L bracket, cm. Thickness 0.2, inner bend R0.2, flange B 3 cm tall, one Ø0.5 hole at (2,2)."""
    t, ri, ro, W = 0.2, 0.2, 0.4, 4.0
    a_top = plane((0, 0, 1), (1, 1, 0.2), 20); a_bot = plane((0, 0, -1), (1, 1, 0), 20)
    b_in = plane((-1, 0, 0), (5.2, 1, 2), 12); b_out = plane((1, 0, 0), (5.4, 1, 2), 12)
    side = plane((0, 1, 0), (0, 0, 0.1), 1)
    c_in = cyl(ri, (0, 1, 0), (5.0, 0, 0.4)); c_out = cyl(ro, (0, 1, 0), (5.0, 0, 0.4))
    hole = cyl(0.25, (0, 0, 1), (2, 2, 0))
    E = Edge
    tan_in_a = E("line", (5.0, 0, 0.2), (5.0, W, 0.2)); tan_in_b = E("line", (5.2, 0, 0.4), (5.2, W, 0.4))
    tan_out_a = E("line", (5.0, 0, 0.0), (5.0, W, 0.0)); tan_out_b = E("line", (5.4, 0, 0.4), (5.4, W, 0.4))
    a_top.link(E("line", (0, 0, .2), (0, W, .2)), E("line", (0, 0, .2), (5, 0, .2)), E("line", (0, W, .2), (5, W, .2)), tan_in_a)
    a_bot.link(E("line", (0, 0, 0), (0, W, 0)), E("line", (0, 0, 0), (5, 0, 0)), E("line", (0, W, 0), (5, W, 0)), tan_out_a)
    for e in a_top.edges[:3] + a_bot.edges[:3]: side.link(*[]) or e.faces.append(side)
    b_in.link(tan_in_b, E("line", (5.2, 0, .4), (5.2, 0, 3.4)), E("line", (5.2, W, .4), (5.2, W, 3.4)), E("line", (5.2, 0, 3.4), (5.2, W, 3.4)))
    b_out.link(tan_out_b, E("line", (5.4, 0, .4), (5.4, 0, 3.4)), E("line", (5.4, W, .4), (5.4, W, 3.4)), E("line", (5.4, 0, 3.4), (5.4, W, 3.4)))
    for e in b_in.edges[1:] + b_out.edges[1:]: e.faces.append(side)
    c_in.link(tan_in_a, tan_in_b, E("arc", (5, 0, .2), (5.2, 0, .4)), E("arc", (5, W, .2), (5.2, W, .4)))
    c_out.link(tan_out_a, tan_out_b, E("arc", (5, 0, 0), (5.4, 0, .4)), E("arc", (5, W, 0), (5.4, W, .4)))
    for f in (c_in, c_out):
        for e in f.edges[2:]: e.faces.append(side)
    ct, cb = E("circle", center=(2, 2, 0.2), radius=0.25), E("circle", center=(2, 2, 0.0), radius=0.25)
    a_top.link(ct); a_bot.link(cb); hole.link(ct, cb)
    faces = [a_top, a_bot, b_in, b_out, side, c_in, c_out, hole]
    comp = Geo(activeSheetMetalRule=Geo(name="Steel", thickness=Geo(value=rule_thickness_cm, expression="2 mm")) if with_rule else None,
               flatPattern=Geo(flatBody=Geo(boundingBox=Geo(minPoint=P(0, 0, 0), maxPoint=P(10.2, 4, 0.2)))) if with_flat else None,
               material=None)
    body = Geo(name="Bracket", isSheetMetal=True, isSolid=True, isVisible=True, volume=10.0,
               material=Geo(name="Steel, Mild"), parentComponent=comp, entityToken="bodytok",
               faces=faces, boundingBox=Geo(minPoint=P(0, 0, 0), maxPoint=P(5.4, 4, 3.4)), nativeObject=None, assemblyContext=None)
    return body, faces


def build_plate(shapes, t=0.2, with_rule=True, wall_scale=1.0, name="Plate", comp_name="PlateComp"):
    """Flat 10 x 6 cm sheet. shapes: list of dicts {"edges": [("line",(x,y),(x,y)) | ("arc",(x,y),(x,y),r,sweep_deg) |
    ("spline",(x,y),(x,y),[pts])], "wall": fraction of t (default 1)} describing inner loops (x,y in cm)."""
    top = plane((0, 0, 1), (5, 3, t), 60); bot = plane((0, 0, -1), (5, 3, 0), 60)
    E = Edge
    side = plane((0, 1, 0), (0, 0, 0.1), 1)
    outer_t = [E("line", (0, 0, t), (10, 0, t)), E("line", (10, 0, t), (10, 6, t)), E("line", (10, 6, t), (0, 6, t)), E("line", (0, 6, t), (0, 0, t))]
    outer_b = [E("line", (0, 0, 0), (10, 0, 0)), E("line", (10, 0, 0), (10, 6, 0)), E("line", (10, 6, 0), (0, 6, 0)), E("line", (0, 6, 0), (0, 0, 0))]
    top.link(*outer_t); bot.link(*outer_b)
    for e in outer_t + outer_b: e.faces.append(side)
    top.extra_loops, bot.extra_loops = [], []
    faces = [top, bot, side]
    for sh in shapes:
        tl, bl = [], []
        wall_h = t * sh.get("wall", 1.0)
        zb = t - wall_h          # bottom of the wall: 0 for a through-cut, higher for a pocket
        for spec in sh["edges"]:
            def mk(z):
                if spec[0] == "line":
                    return E("line", (*spec[1], z), (*spec[2], z))
                if spec[0] == "arc":
                    return E("arc", (*spec[1], z), (*spec[2], z), radius=spec[3], ang=(0, math.radians(spec[4])))
                return E("spline", (*spec[1], z), (*spec[2], z), pts=[(x, y, z) for x, y in spec[3]])
            et, eb = mk(t), mk(zb)
            wall = plane((1, 0, 0), (spec[1][0], spec[1][1], t / 2), 0.5)
            ev1 = E("line", (*spec[1], zb), (*spec[1], t)); ev2 = E("line", (*spec[2], zb), (*spec[2], t))
            # wall edges: the real top/bottom edges plus verticals; wall_scale < 1 models a shallow pocket
            wall.edges = [et, eb, ev1, ev2]
            for e in (et, eb, ev1, ev2): e.faces.append(wall)
            et.faces.append(top)
            if wall_h >= t:
                eb.faces.append(bot)
            tl.append(et); bl.append(eb); faces.append(wall)
        top.extra_loops.append(Loop(False, tl))
        if wall_h >= t:
            bot.extra_loops.append(Loop(False, bl))
    comp = Geo(activeSheetMetalRule=Geo(name="Rule", thickness=Geo(value=t, expression="2 mm")) if with_rule else None,
               flatPattern=None, material=None, name=comp_name)
    body = Geo(name=name, isSheetMetal=True, isSolid=True, isVisible=True, volume=12.0, material=Geo(name="Steel"),
               parentComponent=comp, entityToken="plate-" + name, faces=faces,
               boundingBox=Geo(minPoint=P(0, 0, 0), maxPoint=P(10, 6, t)), nativeObject=None, assemblyContext=None)
    return body


def proxy_of(body, occ):
    """Body proxy as seen through an occurrence."""
    p = Geo(**body.__dict__)
    p.nativeObject, p.assemblyContext = body, occ
    return p


def install(body, selected=None, occurrences=None, extra_root=()):
    """Put fake adsk into sys.modules; return a fake app whose active design holds `body`."""
    class Design:
        @staticmethod
        def cast(x): return x if isinstance(x, Design) else None
    d = Design()
    d.rootComponent = Geo(bRepBodies=Collection([body, *extra_root]), allOccurrences=Collection(occurrences or []), name="Root")
    sel = Collection([Geo(entity=selected)] if selected else [])
    sel.clear = lambda: sel.__init__() or sel[:].clear()
    app = Geo(activeProduct=d, userInterface=Geo(activeSelections=sel), version="fake")
    core = _mod("adsk.core", SurfaceTypes=SurfaceTypes, Curve3DTypes=Curve3DTypes,
                HTMLEventHandler=object, CommandCreatedEventHandler=object,
                PaletteDockingStates=Geo(PaletteDockStateRight=4), Application=Geo(get=staticmethod(lambda: app)))
    fusion = _mod("adsk.fusion", Design=Design, BRepBody=Geo(cast=staticmethod(lambda x: x if hasattr(x, "isSheetMetal") else None)))
    root = _mod("adsk", core=core, fusion=fusion)
    for k, m in (("adsk", root), ("adsk.core", core), ("adsk.fusion", fusion)):
        sys.modules[k] = m
    for k in [k for k in sys.modules if k.startswith("fusion_addin")]:
        del sys.modules[k]
    return app
