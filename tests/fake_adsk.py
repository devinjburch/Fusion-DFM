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
    def __init__(self, kind, a=None, b=None, center=None, radius=None, axis=None, ang=(0, math.pi / 2)):
        self.kind, self.a, self.b = kind, a, b
        self.faces = []
        if kind == "line":
            self.geometry = Geo(curveType=0)
            self.startVertex = Geo(geometry=P(*a)); self.endVertex = Geo(geometry=P(*b))
            self.length = math.dist(a, b)
            self._pts = [P(*a), P(*b)]
        elif kind == "arc":
            self.geometry = Geo(curveType=1, startAngle=ang[0], endAngle=ang[1])
            self.startVertex = Geo(geometry=P(*a)); self.endVertex = Geo(geometry=P(*b))
            self.length = 0.3
            self._pts = [P(*a), P(*b)]
        else:  # circle
            self.geometry = Geo(curveType=2, center=P(*center), radius=radius)
            self.startVertex = self.endVertex = Geo(geometry=P(center[0] + radius, center[1], center[2]))
            self.length = 2 * math.pi * radius
            self._pts = [P(center[0] + radius * math.cos(i * math.pi / 8), center[1] + radius * math.sin(i * math.pi / 8), center[2]) for i in range(17)]
        self.evaluator = Geo(getParameterExtents=lambda: (True, 0.0, 1.0), getStrokes=lambda f, t, tol: (True, self._pts))


class Face:
    _n = 0

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
               faces=faces, boundingBox=Geo(minPoint=P(0, 0, 0), maxPoint=P(5.4, 4, 3.4)))
    return body, faces


def install(body, selected=None):
    """Put fake adsk into sys.modules; return a fake app whose active design holds `body`."""
    class Design:
        @staticmethod
        def cast(x): return x if isinstance(x, Design) else None
    d = Design()
    d.rootComponent = Geo(bRepBodies=Collection([body]), allOccurrences=Collection(), name="Root")
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
