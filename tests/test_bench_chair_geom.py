"""Geometry tests for tools/apartment/furn_bench_chair.py (the leather lounge chair on a
flat-bar satin-steel frame). Pure Python: pymxs is stubbed, nothing touches 3ds Max."""
import math
import os
import sys
import types
from collections import Counter

import pytest

APT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "apartment")
sys.modules.setdefault("pymxs", types.SimpleNamespace(runtime=types.SimpleNamespace()))
if APT not in sys.path:
    sys.path.insert(0, APT)

import furn_bench_chair as fbc  # noqa: E402
import furn_living as fl  # noqa: E402
import kit  # noqa: E402

NAMES = ("Frame", "Glides", "SeatStraps", "SeatCushion", "BackCushion")


# ----------------------------------------------------------------- helpers
def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _bbox(md):
    return [(min(v[k] for v in md.v), max(v[k] for v in md.v)) for k in range(3)]


def _newell(pts):
    n = [0.0, 0.0, 0.0]
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    return n


def _tri_normal(a, b, c):
    u, v = _sub(b, a), _sub(c, a)
    n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    ln = math.sqrt(_dot(n, n))
    return (n[0] / ln, n[1] / ln, n[2] / ln) if ln > 1e-15 else (0.0, 0.0, 0.0)


def _signed_volume(md):
    vol = 0.0
    for f in md.f:
        p0 = md.v[f[0]]
        for k in range(1, len(f) - 1):
            a, b = md.v[f[k]], md.v[f[k + 1]]
            vol += (p0[0] * (a[1] * b[2] - a[2] * b[1]) - p0[1] * (a[0] * b[2] - a[2] * b[0])
                    + p0[2] * (a[0] * b[1] - a[1] * b[0])) / 6.0
    return vol


def _components(md):
    parent = list(range(len(md.v)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for f in md.f:
        r0 = find(f[0])
        for k in f[1:]:
            rk = find(k)
            if rk != r0:
                parent[rk] = r0
    return len({find(i) for f in md.f for i in f})


def _lean_from_vertical(md):
    """Angle (deg) of the major axis of the mesh's YZ projection from vertical."""
    ys = [v[1] for v in md.v]
    zs = [v[2] for v in md.v]
    my, mz = sum(ys) / len(ys), sum(zs) / len(zs)
    syy = sum((y - my) ** 2 for y in ys)
    szz = sum((z - mz) ** 2 for z in zs)
    syz = sum((y - my) * (z - mz) for y, z in zip(ys, zs))
    return math.degrees(0.5 * math.atan2(2.0 * syz, szz - syy))


# ----------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def layout():
    return fbc.lounge_chair_layout()


@pytest.fixture(scope="module")
def parts():
    return {p.name.split("_", 1)[1]: p for p in fbc.lounge_chair_parts()}


@pytest.fixture(scope="module")
def plain():
    return {p.name.split("_", 1)[1]: p for p in fbc.lounge_chair_parts(creases=False)}


# ----------------------------------------------------------------- inventory / mesh hygiene
def test_parts_and_material_keys(parts):
    assert set(parts) == set(NAMES)
    mats = {k: p.mat for k, p in parts.items()}
    assert mats == {"Frame": "metal_steel", "Glides": "rubber", "SeatStraps": "leather",
                    "SeatCushion": "leather", "BackCushion": "leather"}
    for p in parts.values():
        assert p.mat in kit.MAT_KEYS
        assert p.mode in ("uv", "box", "soft")
        assert p.tile and p.tile > 0
    for key in ("SeatCushion", "BackCushion"):
        ax = parts[key].axes
        for i in range(3):                                 # orthonormal node frames
            for j in range(3):
                assert abs(_dot(ax[i], ax[j]) - (1.0 if i == j else 0.0)) < 1e-9


def test_meshes_nonempty_finite_and_valid(parts):
    for name, p in parts.items():
        md = p.md
        assert len(md.v) > 100 and len(md.f) > 100, name
        assert all(math.isfinite(c) for v in md.v for c in v), name
        nv = len(md.v)
        for f in md.f:
            assert len(f) >= 3 and len(set(f)) == len(f), name
            assert all(0 <= i < nv for i in f), name
        assert len(md.fuv) == len(md.f), name
        for uv in md.fuv:
            if uv is not None:
                assert all(math.isfinite(c) for t in uv for c in t), name


def test_meshes_closed_and_consistently_wound(parts):
    """Every directed edge appears exactly once and its reverse exists: watertight,
    no T-junctions or open seams, and all faces wound the same way."""
    for name, p in parts.items():
        edges = Counter()
        for f in p.md.f:
            for i in range(len(f)):
                edges[(f[i], f[(i + 1) % len(f)])] += 1
        assert all(c == 1 for c in edges.values()), name
        assert all((b, a) in edges for (a, b) in edges), name


def test_normals_face_outwards_and_volumes_are_real(parts):
    vols = {k: _signed_volume(p.md) for k, p in parts.items()}
    assert 2600.0 < vols["Frame"] < 3400.0                 # ~4 m of 4 x 1 cm bar
    assert 15.0 < vols["Glides"] < 30.0
    assert 350.0 < vols["SeatStraps"] < 650.0
    assert 44000.0 < vols["SeatCushion"] < 54000.0         # ~61 x 66 x 12 cm, crowned 2.8
    assert 21000.0 < vols["BackCushion"] < 29000.0         # ~60 x 39 x 10.5 cm


def test_ngons_fan_cleanly(parts):
    """_build fan-triangulates every polygon from its first vertex: each fan triangle
    must have real area and face the same way as the polygon (caps star-shaped from
    vertex 0, no collinear slivers whose normals would be noise)."""
    for name, p in parts.items():
        V = p.md.v
        for f in p.md.f:
            if len(f) <= 4:
                continue
            n = _newell([V[i] for i in f])
            ln = math.sqrt(_dot(n, n))
            for k in range(1, len(f) - 1):
                a, b, c = V[f[0]], V[f[k]], V[f[k + 1]]
                u, v = _sub(b, a), _sub(c, a)
                cr = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
                assert _dot(cr, n) / ln > 1e-7, name            # twice the area, along the normal


def test_face_budget(parts):
    total = sum(len(p.md.f) for p in parts.values())
    assert total < 60000


# ----------------------------------------------------------------- real-world dimensions
def test_overall_footprint(parts):
    allv = [v for p in parts.values() for v in p.md.v]
    xs, ys, zs = [v[0] for v in allv], [v[1] for v in allv], [v[2] for v in allv]
    assert -35.05 <= min(xs) <= -34.9 and 34.9 <= max(xs) <= 35.05          # W 70
    assert -39.05 <= min(ys) <= -38.9 and 38.85 <= max(ys) <= 39.2          # D 78 (the back cushion's crown 1 mm proud)
    assert abs(min(zs)) < 1e-6                                              # on the floor
    assert 71.4 <= max(zs) <= 72.6                                          # H 72
    # front faces -Y: the seat cushion's front is near y = -39, the back cushion at +Y
    seat, back = _bbox(parts["SeatCushion"].md), _bbox(parts["BackCushion"].md)
    assert seat[1][0] < -38.0 and back[1][0] > 15.0


def test_only_glides_touch_the_floor(parts, layout):
    fr, gl = _bbox(parts["Frame"].md), _bbox(parts["Glides"].md)
    assert abs(fr[2][0] - layout["glide"]) < 1e-6           # runner bottoms 3 mm up
    assert gl[2][0] == pytest.approx(0.0, abs=1e-9) and gl[2][1] < 0.4
    for v in parts["Glides"].md.v:                          # under the runners
        assert layout["xi"] <= abs(v[0]) <= layout["xo"]
        assert layout["runner"][0] - 0.01 <= v[1] <= layout["runner"][1] + 0.01


def test_side_frame_is_a_4_by_1_flat_bar(layout):
    xc = layout["xc"]
    md = fbc._side_frame_md(layout, xc)
    xs = [v[0] for v in md.v]
    assert min(xs) >= xc - 2.0 - 1e-6 and max(xs) <= xc + 2.0 + 1e-6
    assert max(xs) - min(xs) == pytest.approx(4.0, abs=1e-6)
    V = md.v
    # arm: top at arm_h, 1 cm thick (support ring next to the front-top bend)
    y_ring = layout["yf"] + 5.0 + 0.05
    ring = [v for v in V if abs(v[1] - y_ring) < 1e-6]
    assert ring
    assert min(v[2] for v in ring) == pytest.approx(55.0, abs=1e-6)
    assert max(v[2] for v in ring) == pytest.approx(56.0, abs=1e-6)
    assert max(v[2] for v in V if v[1] < 30.0) == pytest.approx(56.0, abs=1e-6)
    # front leg: 1 cm deep, its front face on the chair's front plane
    leg = [v for v in V if 6.84 < v[2] < 50.46 and v[1] < -37.5]
    assert leg
    assert min(v[1] for v in leg) == pytest.approx(-39.0, abs=1e-6)
    assert max(v[1] for v in leg) == pytest.approx(-38.0, abs=1e-6)
    # runner bottom 3 mm above the floor, post top reaches ~6.5 cm under the cushion top
    assert min(v[2] for v in V) == pytest.approx(layout["glide"], abs=1e-6)
    assert 65.0 < max(v[2] for v in V) < 66.0


def test_frame_edges_and_bends_are_rounded(layout):
    """No razor edges: every section vertex lies inside the 4 x 1 cm rectangle with
    2 mm corner radii (and some lie on those arcs); the bends keep real radii."""
    xc, r = layout["xc"], layout["edge_r"]
    md = fbc._side_frame_md(layout, xc)
    y_ring = layout["yf"] + 5.0 + 0.05
    ring = [v for v in md.v if abs(v[1] - y_ring) < 1e-6]
    on_arc = 0
    for v in ring:
        a, b = abs(v[0] - xc), abs(v[2] - 55.5)
        if a > 2.0 - r and b > 0.5 - r:
            d = math.hypot(a - (2.0 - r), b - (0.5 - r))
            assert d <= r + 1e-6
            on_arc += abs(d - r) < 1e-6
    assert on_arc >= 8
    # the outer face of the front foot bend stays >= 2 cm off the sharp corner
    corner = (-39.0, layout["glide"])
    assert min(math.hypot(v[1] - corner[0], v[2] - corner[1]) for v in md.v) > 2.0
    # the eased post top: nothing pokes out of the bar's rounded end
    top = max(md.v, key=lambda v: v[2])
    assert top[2] < layout["post_top"] + 0.25


def test_cross_bars_join_the_side_frames(parts, layout):
    xi = layout["xi"]
    for key in ("front_rail", "rear_rail", "lumbar_rail", "top_rail"):
        wdir = (0.0, 0.0, 1.0) if key == "front_rail" else layout["u"]
        md = fbc._rail_md(layout, layout[key], wdir)
        xs = [v[0] for v in md.v]
        assert min(xs) == pytest.approx(-(xi + 0.3), abs=1e-6)     # 3 mm into each side frame
        assert max(xs) == pytest.approx(xi + 0.3, abs=1e-6)
        assert _components(md) == 5                                # bar + 4 fillet welds
    # the rails on the posts lie in the post plane (flush with the posts' faces)
    nf, pc = layout["nf"], layout["pc"]
    for key in ("rear_rail", "lumbar_rail", "top_rail"):
        assert abs(_dot(_sub(layout[key], pc), nf)) < 1e-9


def test_seat_height_thickness_and_support(parts, layout):
    seat = parts["SeatCushion"]
    front = [v[2] for v in seat.md.v if v[1] < -28.0]
    assert 37.0 <= max(front) <= 39.0                                  # seat height ~38
    O, ax = seat.origin, seat.axes
    lz = [_dot(_sub(v, O), ax[2]) for v in seat.md.v]
    assert -0.01 <= min(lz) <= 0.02                                    # bottom on the support plane
    assert 13.5 <= max(lz) - min(lz) <= 15.2                           # 12 cm cushion + 2.8 cm crown
    z_sp = layout["z_sp"]
    assert max(v[2] - z_sp(v[1]) for v in parts["SeatStraps"].md.v) <= 0.0
    assert layout["front_rail"][2] + 2.0 <= z_sp(layout["yf"] + 0.5)
    seat_tilt = math.degrees(math.atan2(-ax[1][2], ax[1][1]))
    assert seat_tilt == pytest.approx(layout["seat_tilt"], abs=1e-9)


def test_back_cushion_leans_at_100_degrees(parts, layout):
    lean = _lean_from_vertical(parts["BackCushion"].md)
    seat_back = 90.0 + lean - layout["seat_tilt"]
    assert seat_back == pytest.approx(100.0, abs=1.5)
    ax = parts["BackCushion"].axes
    frame_angle = math.degrees(math.acos(_dot((0.0, -math.cos(layout["tilt"]), math.sin(layout["tilt"])), ax[1])))
    assert frame_angle == pytest.approx(100.0, abs=1e-6)


def test_cushions_clear_of_the_frame(parts, layout):
    xi = layout["xi"]
    for key in ("SeatCushion", "BackCushion"):
        assert max(abs(v[0]) for v in parts[key].md.v) <= xi - 0.2, key
    nf, pc = layout["nf"], layout["pc"]
    seat_d = [_dot(_sub(v, pc), nf) - 0.5 * layout["bar_t"] for v in parts["SeatCushion"].md.v]
    assert min(seat_d) >= 0.1                                          # in front of posts and rails
    # the arms pass beside the back cushion, never through it
    back = parts["BackCushion"].md
    assert all(abs(v[0]) < xi for v in back.v if 54.0 < v[2] < 57.0)


def test_back_cushion_rests_on_the_rails(parts, layout):
    nf, pc, u = layout["nf"], layout["pc"], layout["u"]
    back = parts["BackCushion"].md
    for key in ("lumbar_rail", "top_rail"):
        c = layout[key]
        band = [_dot(_sub(v, pc), nf) - 0.5 * layout["bar_t"] for v in back.v if abs(_dot(_sub(v, c), u)) < 1.9]
        assert band, key
        assert -0.05 <= min(band) <= 0.3, key                          # touching, not through


def test_back_cushion_sits_on_the_seat(parts):
    seat, back = parts["SeatCushion"], parts["BackCushion"]
    O, ax = seat.origin, seat.axes
    grid = fl._Grid2(0, 1, 1.0).add([v for v in seat.md.v if _dot(_sub(v, O), ax[2]) > 6.0])
    gaps = []
    for v in back.md.v:
        pts = grid.near(v[0], v[1], 0.6)
        if pts:
            gaps.append(v[2] - max(p[2] for p in pts))
    assert len(gaps) > 500
    assert min(gaps) >= -0.25                                          # pressed in a little at most
    assert min(gaps) <= 0.1                                            # but touching: no floating


def test_top_seam_is_pulled_in_and_welts_are_present(parts, plain):
    seat = parts["SeatCushion"]
    O, ax, T = seat.origin, seat.axes, 10.0
    loc = [(v[0], _dot(_sub(v, O), ax[1]), _dot(_sub(v, O), ax[2])) for v in seat.md.v]
    mid = [p for p in loc if abs(p[1]) < 3.0]
    seam = max(abs(p[0]) for p in mid if T - 0.8 < p[2] < T - 0.2)
    belly = max(abs(p[0]) for p in mid if 4.0 < p[2] < 6.0)
    assert 0.3 < belly - seam < 1.5                                    # sides pulled in under the crown
    assert _components(seat.md) == 3                                   # body + top and bottom welts
    assert _components(parts["BackCushion"].md) == 3


def test_leather_has_creases_but_no_folds(parts, plain):
    for key in ("SeatCushion", "BackCushion"):
        a, b = plain[key].md, parts[key].md
        assert len(a.v) == len(b.v) and a.f == b.f
        moved = max(math.dist(p, q) for p, q in zip(a.v, b.v))
        assert 0.15 < moved < 0.6, key                                 # soft 2-4 mm creases
        for f in b.f:
            na = _tri_normal(a.v[f[0]], a.v[f[1]], a.v[f[2]])
            nb = _tri_normal(b.v[f[0]], b.v[f[1]], b.v[f[2]])
            assert _dot(na, nb) > 0.8, key                             # nothing folds over


def test_parameters_drive_the_geometry():
    ps = {p.name.split("_", 1)[1]: p for p in fbc.lounge_chair_parts(width=80.0, depth=84.0, height=78.0,
                                                                     seat_h=40.0, arm_h=58.0,
                                                                     back_angle=106.0, straps=0, seed=3)}
    assert "SeatStraps" not in ps
    allv = [v for p in ps.values() for v in p.md.v]
    assert max(v[0] for v in allv) == pytest.approx(40.0, abs=0.05)
    fr = _bbox(ps["Frame"].md)
    assert fr[1][0] == pytest.approx(-42.0, abs=0.05) and fr[1][1] == pytest.approx(42.0, abs=0.05)
    assert min(v[1] for v in allv) >= -42.05
    assert max(v[1] for v in allv) <= 44.0          # a steeper back leans its cushion top past the post
    assert max(v[2] for v in allv) == pytest.approx(78.0, abs=0.6)
    assert max(v[2] for v in ps["Frame"].md.v if v[1] < 30.0) == pytest.approx(58.0, abs=1e-6)
    lean = _lean_from_vertical(ps["BackCushion"].md)
    assert 90.0 + lean - 4.0 == pytest.approx(106.0, abs=1.5)


def test_deterministic():
    a = fbc.lounge_chair_parts(seed=5)
    b = fbc.lounge_chair_parts(seed=5)
    for pa, pb in zip(a, b):
        assert pa.md.v == pb.md.v and pa.md.f == pb.md.f


# ----------------------------------------------------------------- the Max-facing wrapper
class _FakeNode(object):
    def __init__(self, name):
        self.name = name


def test_build_wrapper_registers_every_part(monkeypatch):
    built = []

    def fake_build(md, name, uv_tile=None):
        built.append((name, uv_tile, len(md.v)))
        return _FakeNode(name)

    monkeypatch.setattr(fl, "_build", fake_build)
    monkeypatch.setattr(fl, "rt", types.SimpleNamespace(Matrix3=lambda *a: a, Point3=lambda *a: a))
    monkeypatch.setattr(kit, "soften", lambda node, *a, **k: node)
    monkeypatch.setattr(kit, "group", lambda name, nodes: types.SimpleNamespace(name=name, nodes=nodes))
    start = len(kit.PARTS)
    try:
        g = fbc.build_lounge_chair()
        reg = kit.PARTS[start:]
    finally:
        del kit.PARTS[start:]
    assert g.name == "LoungeChair" and len(g.nodes) == 5
    assert [n.name for n in g.nodes] == ["LoungeChair_" + k for k in NAMES]
    keys = {n.name: (k, t, m) for n, k, t, m in reg}
    assert keys["LoungeChair_Frame"] == ("metal_steel", None, None)          # own UVs
    assert keys["LoungeChair_SeatCushion"] == ("leather", None, None)
    assert keys["LoungeChair_BackCushion"] == ("leather", None, None)
    assert keys["LoungeChair_Glides"] == ("rubber", fbc.RUBBER, 4)            # box-mapped
    assert {name: tile for name, tile, _ in built}["LoungeChair_Frame"] == fbc.STEEL
    assert all(k in kit.MAT_KEYS for k, _t, _m in keys.values())
