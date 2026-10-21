"""Tiny pure-Python vector helpers (no CAD dependency)."""
from __future__ import annotations
import math


def sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def norm(a): return math.sqrt(dot(a, a))
def cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def unit(a):
    n = norm(a)
    if n == 0:
        raise ValueError("zero-length vector")
    return (a[0] / n, a[1] / n, a[2] / n)


def point_segment_distance(p, a, b) -> float:
    ab = sub(b, a)
    L2 = dot(ab, ab)
    if L2 == 0:
        return norm(sub(p, a))
    t = max(0.0, min(1.0, dot(sub(p, a), ab) / L2))
    return norm(sub(p, (a[0] + t * ab[0], a[1] + t * ab[1], a[2] + t * ab[2])))


def point_polyline_distance(p, pts) -> float:
    if len(pts) == 1:
        return norm(sub(p, pts[0]))
    return min(point_segment_distance(p, pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def polyline_distance(a, b) -> float:
    """Minimum distance between two 3D polylines (vertex-to-segment both ways; exact for non-crossing polylines)."""
    best = float("inf")
    for p in a:
        best = min(best, point_polyline_distance(p, b))
    for p in b:
        best = min(best, point_polyline_distance(p, a))
    return best


def plane_basis(normal):
    """Two unit vectors spanning the plane with the given normal."""
    n = unit(normal)
    ref = (1.0, 0.0, 0.0) if abs(n[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = unit(cross(n, ref))
    v = cross(n, u)
    return u, v


def to_2d(p, origin, u, v):
    d = sub(p, origin)
    return (dot(d, u), dot(d, v))
