import math
from dfm_engine import geometry as g


def test_segment_distance():
    assert g.point_segment_distance((0, 1, 0), (-1, 0, 0), (1, 0, 0)) == 1
    assert math.isclose(g.point_segment_distance((3, 0, 0), (-1, 0, 0), (1, 0, 0)), 2)  # clamps to end
    assert g.point_segment_distance((1, 1, 1), (0, 0, 0), (0, 0, 0)) == math.sqrt(3)


def test_polyline_and_vectors():
    pl = [(0, 0, 0), (10, 0, 0), (10, 10, 0)]
    assert g.point_polyline_distance((5, 2, 0), pl) == 2
    assert g.point_polyline_distance((9, 5, 0), pl) == 1
    assert g.cross((1, 0, 0), (0, 1, 0)) == (0, 0, 1)
    assert g.unit((0, 0, 5)) == (0, 0, 1)
