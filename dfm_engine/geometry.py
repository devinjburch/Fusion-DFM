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
