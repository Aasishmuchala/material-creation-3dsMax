"""Geometry tests for tools/apartment/bench2_arch.py - runs without 3ds Max.

pymxs is stubbed while the module is imported (and the previous entry put
back). Every mesh must be a closed, consistently wound solid facing outward,
free of NaN, at real-world size; every section a simple polygon whose visible
corners are all filleted. The build_* wrappers run against a fake runtime.
"""
import math
import os
import sys
import types
from collections import Counter

import pytest

APT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "apartment")
if APT not in sys.path:
    sys.path.insert(0, APT)
_saved_pymxs = sys.modules.get("pymxs")
sys.modules["pymxs"] = types.SimpleNamespace(runtime=types.SimpleNamespace())
try:
    import kit  # noqa: E402
    import furn_living  # noqa: E402
    import bench2_arch as B  # noqa: E402
finally:
    if _saved_pymxs is None:
        sys.modules.pop("pymxs", None)
    else:
        sys.modules["pymxs"] = _saved_pymxs

USED = {"paint_white", "metal_black", "emissive_warm", "copper_plaster", "metal_brass", "marble_floor"}


# ------------------------------------------------------------------ helpers
def assert_solid(md, name=""):
    assert md.v and md.f, "%s: empty mesh" % name
    for p in md.v:
        assert all(math.isfinite(c) for c in p), "%s: NaN / inf vertex %r" % (name, p)
    for f in md.f:
        assert len(f) >= 3 and len(set(f)) == len(f), "%s: degenerate face %r" % (name, f)
        assert all(0 <= i < len(md.v) for i in f)
    ec = Counter()
    for f in md.f:
        for i in range(len(f)):
            ec[(f[i], f[(i + 1) % len(f)])] += 1
    bad = [e for e, c in ec.items() if c != 1 or ec.get((e[1], e[0]), 0) != 1]
    assert not bad, "%s: %d open or inconsistent edges, e.g. %r" % (name, len(bad), bad[:3])
    assert B._volume(md) > 0.0, "%s: wound inside out" % name


def components(md):
    parent = list(range(len(md.v)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for f in md.f:
        r = find(f[0])
        for i in f[1:]:
            parent[find(i)] = r
    return len({find(i) for f in md.f for i in f})


def check_parts(parts):
    assert parts
    for name, key, md, tile, smooth in parts:
        assert key in kit.MAT_KEYS and key in USED, (name, key)
        assert (tile is None or tile > 0) and smooth == 0
        assert_solid(md, name)
    return {p[0]: p for p in parts}


def _turn(a, p, c):
    d1 = (p[0] - a[0], p[1] - a[1])
    d2 = (c[0] - p[0], c[1] - p[1])
    l1, l2 = math.hypot(*d1), math.hypot(*d2)
    return math.degrees(math.acos(max(-1.0, min(1.0, (d1[0] * d2[0] + d1[1] * d2[1]) / (l1 * l2)))))


def _crosses(p1, p2, q1, q2):
    def o(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return o(q1, q2, p1) * o(q1, q2, p2) < -1e-14 and o(p1, p2, q1) * o(p1, p2, q2) < -1e-14


def assert_section(prof, hidden, name=""):
    """Simple closed polygon, no duplicate points, every vertex turning more
    than 25 degrees buried (hidden(p)): no razor-sharp visible edge."""
    n = len(prof)
    assert n >= 4
    segs = [(prof[i], prof[(i + 1) % n]) for i in range(n)]
    for a, b in segs:
        assert math.hypot(b[0] - a[0], b[1] - a[1]) > 1e-6, "%s: duplicate point" % name
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            assert not _crosses(segs[i][0], segs[i][1], segs[j][0], segs[j][1]), "%s: self-crossing" % name
    for i in range(n):
        if _turn(prof[i - 1], prof[i], prof[(i + 1) % n]) > 25.0:
            assert hidden(prof[i]), "%s: sharp visible corner at %r" % (name, prof[i])


def bbox(md):
    return B._bbox(md)


# ------------------------------------------------------------------ keys
def test_material_keys_declared():
    assert "copper_plaster" in kit.MAT_KEYS and "marble_floor" in kit.MAT_KEYS
    assert USED <= set(kit.MAT_KEYS)


# ------------------------------------------------------------------ sections
A_NOTCH = 0.5 * B.BH_SLOT_W + B.BH_CHANNEL_T + B.BH_CLEAR


@pytest.mark.parametrize("name,prof,hidden", [
    ("bulkhead", B.bulkhead_profile(),
     lambda p: p[0] > 30.0 - 1e-6 or p[1] > -1e-6 or (abs(p[0]) <= A_NOTCH + 1e-6 and p[1] > -24.99)),
    ("channel", B.channel_profile(), lambda p: False),
    ("shadow", B.shadow_profile(), lambda p: p[1] <= 1e-6 or p[1] >= 8.15 - 1e-6 or p[0] <= -1.65 + 1e-6),
])
def test_sections_are_simple_and_filleted(name, prof, hidden):
    assert_section(prof, hidden, name)


def test_section_sizes():
    bh = B.bulkhead_profile(60.0, 25.0)
    ys, zs = [p[0] for p in bh], [p[1] for p in bh]
    assert (min(ys), max(ys)) == pytest.approx((-30.0, 30.1)) and (min(zs), max(zs)) == pytest.approx((-25.0, 0.1))
    ch = B.channel_profile(25.0)
    side = [abs(y) for y, z in ch if z < -20.2]
    assert min(side) == pytest.approx(3.0) and max(side) == pytest.approx(3.15)      # 6 cm clear, 1.5 mm walls
    assert max(z for y, z in ch if abs(y) < 3.0 - 1e-6) == pytest.approx(-20.0)       # 5 cm deep from the soffit
    sk = B.shadow_profile()
    assert min(p[0] for p in sk) == pytest.approx(-1.65) and max(p[0] for p in sk) == pytest.approx(0.0)
    assert (min(p[1] for p in sk), max(p[1] for p in sk)) == pytest.approx((-0.3, 8.15))
    web = [p for p in sk if 0.049 < p[1] < 7.951]
    assert max(p[0] for p in web) == pytest.approx(-1.5)                                # 1.5 cm deep reveal
    with pytest.raises(ValueError):
        B.shadow_profile(2.0, 1.5)
    with pytest.raises(ValueError):
        B.bulkhead_profile(60.0, 12.0)


# ------------------------------------------------------------------ bulkhead
def test_bulkhead_parts_and_size():
    p = check_parts(B.bulkhead_parts(420.0))
    assert set(p) == {"Bulkhead_Board", "Bulkhead_Track"}
    assert p["Bulkhead_Board"][1] == "paint_white" and p["Bulkhead_Track"][1] == "metal_black"
    board = p["Bulkhead_Board"][2]
    (x0, y0, z0), (x1, y1, z1) = bbox(board)
    assert (x0, x1, y0, y1, z0, z1) == pytest.approx((-210.1, 210.1, -30.0, 30.1, -25.0, 0.1))
    assert components(board) == 1 and components(p["Bulkhead_Track"][2]) == 1
    # shadow gap: nothing of the board in the 10 x 10 cm reveal under the ceiling
    assert not [v for v in board.v if v[1] < -20.11 and v[2] > -9.89]                 # (1 mm cove in its corner)
    assert [v for v in board.v if abs(v[1] + 20.0) < 1e-6 and abs(v[2] - 0.1) < 1e-6]
    # the fascia rises 15 cm from the soffit to the reveal ledge
    fascia = [v[2] for v in board.v if abs(v[1] + 30.0) < 1e-6]
    assert min(fascia) == pytest.approx(-25.0 + B.BH_ARRIS) and max(fascia) == pytest.approx(-10.0 - B.BH_ARRIS)
    # the slot is open: no board vertex below the channel top inside the slot
    assert not [v for v in board.v if abs(v[1]) < A_NOTCH - 1e-6 and v[2] < -25.0 + 5.17 - 1e-6]
    # the track channel sits in it, clear of the plaster
    (tx0, ty0, tz0), (tx1, ty1, tz1) = bbox(p["Bulkhead_Track"][2])
    assert (ty0, ty1) == pytest.approx((-3.15, 3.15)) and tz0 > -25.0 and tz1 < -25.0 + 5.17


def test_bulkhead_options():
    p = check_parts(B.bulkhead_parts(300.0, 50.0, 30.0, 8.0, 6.0, 6.0, 270.0, spots=(-100.0, 20.0), cove_led=True))
    (x0, y0, z0), (x1, y1, z1) = bbox(p["Bulkhead_Board"][2])
    assert (y0, y1, z0, z1) == pytest.approx((-25.0, 25.1, 240.0, 270.1))
    soffit, cz = 240.0, 270.0
    spots, lens = p["Bulkhead_Spots"][2], p["Bulkhead_SpotLens"][2]
    assert components(spots) == 4 and components(lens) == 2               # adapter + body each
    (sx0, sy0, sz0), (sx1, sy1, sz1) = bbox(spots)
    assert sz1 < soffit + 5.0 and soffit - 12.0 < sz0 < soffit - 8.0      # hangs ~10 cm under the soffit
    assert all(abs(v[1] - 6.0) <= 3.0 for v in spots.v if v[2] > soffit)    # fits the 6 cm slot
    for v in lens.v:                                                       # in the anti-glare recess
        assert math.hypot(min(abs(v[0] + 100.0), abs(v[0] - 20.0)), v[1] - 6.0) < B.SPOT_R - 0.3
        assert soffit - 10.0 < v[2] < soffit - 8.0
    (lx0, ly0, lz0), (lx1, ly1, lz1) = bbox(p["Bulkhead_CoveLED"][2])
    assert -25.0 < ly0 and ly1 < -25.0 + 6.0 and lz0 == pytest.approx(cz - 8.0)   # on the reveal ledge
    with pytest.raises(ValueError):
        B.bulkhead_parts(300.0, spots=(148.0,))
    with pytest.raises(ValueError):
        B.bulkhead_parts(20.0)
    with pytest.raises(ValueError):
        B.bulkhead_parts(300.0, slot_y=28.0)


# ------------------------------------------------------------------ feature wall
FW_CASES = [(320.0, 270.0, 0, False), (400.0, 280.0, 1, False), (240.0, 300.0, 2, True),
            (180.0, 260.0, 3, False), (500.0, 250.0, 5, True)]


@pytest.mark.parametrize("W,H,seed,flip", FW_CASES)
def test_feature_wall(W, H, seed, flip):
    parts = check_parts(B.feature_wall_parts(W, H, seed, flip=flip))
    name, key, md, tile, sm = parts["FeatureWall"]
    assert key == "copper_plaster" and tile == 200.0
    assert components(md) == 3                                             # two plaster fields + backing
    P = B.FW_PROUD
    (x0, y0, z0), (x1, y1, z1) = bbox(md)
    assert (x0, x1, y0, y1, z0, z1) == pytest.approx((-W / 2, W / 2, -P, 0.1, 0.0, H), abs=1e-6)
    face = [(v[0], v[2]) for v in md.v if abs(v[1] + P) < 1e-9]
    assert len(face) > 100
    # 1 cm arris on the panel edge the groove never reaches
    assert min(z for x, z in face) == pytest.approx(1.0, abs=1e-6)
    if flip:
        assert max(x for x, z in face) == pytest.approx(W / 2 - 1.0, abs=1e-6)
    else:
        assert min(x for x, z in face) == pytest.approx(-W / 2 + 1.0, abs=1e-6)
    # the groove: 2 cm wide at the face along its run, joint open edge to edge
    curve = B.groove_curve(W, H, seed, flip)
    inner = [p for p in curve[2:-2] if 15.0 < p[1] < H - 15.0 and abs(p[0]) < W / 2 - 15.0]
    assert len(inner) > 10
    for c in inner[::3]:
        assert min(math.hypot(x - c[0], z - c[1]) for x, z in face) == pytest.approx(1.0, abs=0.02)
    fields = [(v[0], v[2]) for v in md.v if v[1] < -P + B.FW_GROOVE_D - 1e-9]
    for x, z in fields[::4]:
        assert B._dist_polyline((x, z), curve) > 0.5 * B.FW_JOINT - 1e-4
    # groove floor 1.5 cm deep: the backing's face, shown in the joint
    assert [v for v in md.v if abs(v[1] - (-P + B.FW_GROOVE_D)) < 1e-9]


def test_groove_curve_shape():
    W, H = 360.0, 280.0
    for seed in range(6):
        c = B.groove_curve(W, H, seed)
        assert c[1][1] == pytest.approx(H) and c[-2][0] == pytest.approx(W / 2)      # top edge -> right side
        assert -W / 2 + 0.17 * W < c[1][0] < -W / 2 + 0.35 * W and 0.35 * H < c[-2][1] < 0.53 * H
        assert all(b[0] > a[0] and b[1] < a[1] for a, b in zip(c, c[1:]))          # always down and across
        turns = [(b[0] - a[0]) * (d[1] - b[1]) - (b[1] - a[1]) * (d[0] - b[0])
                 for a, b, d in zip(c[1:], c[2:], c[3:-1])]
        assert max(turns) > 1e-3 and min(turns) < -1e-3                             # an S: both bends
        steps = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(c[1:-2], c[2:-1])]
        assert max(steps) < 3.0
    a, b = B.groove_curve(W, H, 2), B.groove_curve(W, H, 2, flip=True)
    assert b == [(-x, z) for x, z in a] and B.groove_curve(W, H, 2) == a
    assert B.groove_curve(W, H, 0) != B.groove_curve(W, H, 1)
    with pytest.raises(ValueError):
        B.feature_wall_parts(50.0, 270.0)
    with pytest.raises(ValueError):
        B.feature_wall_parts(300.0, 270.0, proud=10.0)


def test_feature_wall_outlines():
    left, right, curve = B.feature_wall_outlines(320.0, 270.0, 0)
    for loop in (left, right):
        assert B._signed_area(loop) > 0.0                                            # counter-clockwise
        assert all(-160.0 - 1e-9 <= x <= 160.0 + 1e-9 and -1e-9 <= z <= 270.0 + 1e-9 for x, z in loop)
    # the small field holds the top-right corner region, the big one the rest
    assert B._signed_area(left) < B._signed_area(right)
    total = B._signed_area(left) + B._signed_area(right)
    assert total == pytest.approx(320.0 * 270.0, rel=0.01)


# ------------------------------------------------------------------ shadow skirting
def test_shadow_skirting_ring():
    rect = (-250.0, -200.0, 250.0, 200.0)
    md = B.shadow_skirting_md(rect)
    assert_solid(md, "reveal")
    assert components(md) == 1
    (x0, y0, z0), (x1, y1, z1) = bbox(md)
    assert (x0, y0, x1, y1, z0, z1) == pytest.approx((-251.65, -201.65, 251.65, 201.65, -0.3, 8.15))
    inside = lambda v: min(v[0] + 250.0, 250.0 - v[0], v[1] + 200.0, 200.0 - v[1])
    assert max(inside(v) for v in md.v) == pytest.approx(0.0, abs=1e-6)                  # nothing stands proud
    assert max(inside(v) for v in md.v if 0.049 < v[2] < 7.951) == pytest.approx(-1.5)  # the recessed web


def test_shadow_skirting_openings():
    rect = (0.0, 0.0, 600.0, 450.0)
    md = B.shadow_skirting_md(rect, [("s", 120.0, 230.0), ("n", 200.0, 360.0)])
    assert_solid(md, "reveal runs")
    assert components(md) == 2
    for x, y, z in md.v:
        if y < 3.0:
            assert not 120.0 + 1e-6 < x < 230.0 - 1e-6
        if y > 447.0:
            assert not 200.0 + 1e-6 < x < 360.0 - 1e-6
    assert B.shadow_skirting_md(rect, [("s", 0, 600), ("e", 0, 450), ("n", 0, 600), ("w", 0, 450)]).v == []
    p = check_parts(B.shadow_skirting_parts(rect, height=10.0, depth=2.0))
    (x0, y0, z0), (x1, y1, z1) = bbox(p["ShadowSkirting"][2])
    assert z1 == pytest.approx(10.15) and x0 == pytest.approx(-2.15)


# ------------------------------------------------------------------ switch plate
def test_switch_plate():
    p = check_parts(B.switch_parts())
    plate, rocker = p["SwitchPlate"][2], p["SwitchPlate_Rocker"][2]
    assert {q[1] for q in p.values()} == {"metal_brass"}
    (x0, y0, z0), (x1, y1, z1) = bbox(plate)
    assert (x0, x1, y0, y1, z0, z1) == pytest.approx((-4.3, 4.3, -0.6, 0.0, 100.7, 109.3))
    corner = min(math.hypot(abs(v[0]) - 4.3, abs(v[2] - 105.0) - 4.3) for v in plate.v)
    assert corner > 0.1                                                    # rounded corners
    assert min(math.hypot(v[1] + 0.6, abs(v[0]) - 4.3) for v in plate.v) > 0.03   # eased front edge
    (rx0, ry0, rz0), (rx1, ry1, rz1) = bbox(rocker)
    assert -4.3 < rx0 and rx1 < 4.3 and 100.7 < rz0 and rz1 < 109.3
    assert -0.6 < ry1 < 0.0 and ry0 < -0.95                                # sunk in the plate, ~5 mm proud
    top = min(v[1] for v in rocker.v if v[2] > 107.0)
    bot = min(v[1] for v in rocker.v if v[2] < 103.0)
    assert bot - top > 0.1                                                 # rocked: top edge out
    (x0, y0, z0), (x1, y1, z1) = bbox(B.switch_parts(120.0)[0][2])
    assert (z0, z1) == pytest.approx((115.7, 124.3))


# ------------------------------------------------------------------ marble floor
def tile_tops(md):
    """Top faces (the first face of each 14-face tile): [(face, uvs)]."""
    return [(md.f[i], md.fuv[i]) for i in range(0, len(md.f), 14)]


@pytest.mark.parametrize("rect,along", [((-250.0, -200.0, 250.0, 200.0), "x"), ((0.0, 0.0, 640.0, 455.0), "y")])
def test_marble_floor(rect, along):
    parts = check_parts(B.marble_floor_parts(rect, 3, along=along))
    name, key, tiles, tile, sm = parts["MarbleFloor_Tiles"]
    assert key == "marble_floor" and tile is None                          # own UVs
    assert parts["MarbleFloor_Subfloor"][1] == "metal_black"
    cells = B.floor_layout(rect, 3, along=along)
    assert components(tiles) == len(cells) and len(tiles.f) == 14 * len(cells)
    x0, y0, x1, y1 = rect
    (bx0, by0, bz0), (bx1, by1, bz1) = bbox(tiles)
    assert (bx0, by0, bx1, by1) == pytest.approx((x0 + 0.075, y0 + 0.075, x1 - 0.075, y1 - 0.075))
    assert bz0 == pytest.approx(-2.0) and -0.05 < bz1 <= 0.0
    (sx0, sy0, sz0), (sx1, sy1, sz1) = bbox(parts["MarbleFloor_Subfloor"][2])
    assert sz1 == pytest.approx(B.SUB_TOP) and sz1 < -1.0 and (sx0, sx1) == pytest.approx((x0, x1))
    # cells tile the room exactly; full tiles 120 x 60, nothing thinner than 6 cm
    assert sum((c["x1"] - c["x0"]) * (c["y1"] - c["y0"]) for c in cells) == pytest.approx((x1 - x0) * (y1 - y0))
    la = [(c["x1"] - c["x0"]) if along == "x" else (c["y1"] - c["y0"]) for c in cells]
    lb = [(c["y1"] - c["y0"]) if along == "x" else (c["x1"] - c["x0"]) for c in cells]
    assert min(la) >= 6.0 and min(lb) >= 6.0 and max(la) < 126.0 and max(lb) < 66.0
    assert sum(1 for a, b in zip(la, lb) if abs(a - 120.0) < 1e-6 and abs(b - 60.0) < 1e-6) >= len(cells) // 3
    # staggered by a third: joints of neighbouring rows 40 cm apart (mod 120)
    rows = {}
    for c in cells:
        rows.setdefault(c["row"], []).append(c["x0"] if along == "x" else c["y0"])
    lo = x0 if along == "x" else y0
    for r in range(len(rows) - 1):
        ja = [j for j in rows[r] if j > lo + 1e-6]
        jb = [j for j in rows[r + 1] if j > lo + 1e-6]
        if ja and jb:
            d = (jb[0] - ja[0]) % 120.0
            assert min(abs(d - 40.0), abs(d - 80.0)) < 1e-6
    # every tile its own UV window: distinct, 1 x 0.5 repeat for a full tile
    tops = tile_tops(tiles)
    assert all(uv is not None for f, uv in tops)
    starts = {(round(c["u0"], 6), round(c["v0"], 6)) for c in cells}
    assert len(starts) == len(cells)
    for (f, uv), c in zip(tops, cells):
        su = max(u for u, v in uv) - min(u for u, v in uv)
        sv = max(v for u, v in uv) - min(v for u, v in uv)
        a_len = (c["x1"] - c["x0"]) if along == "x" else (c["y1"] - c["y0"])
        b_len = (c["y1"] - c["y0"]) if along == "x" else (c["x1"] - c["x0"])
        assert su == pytest.approx((a_len - 0.15 - 0.2) / 120.0, abs=1e-4)
        assert sv == pytest.approx((b_len - 0.15 - 0.2) / 120.0, abs=1e-4)


def test_marble_floor_joints_and_lippage():
    rect = (0.0, 0.0, 485.0, 362.0)
    tiles = B.marble_floor_parts(rect, 1)[0][2]
    tops = [tiles.v[i] for f, uv in tile_tops(tiles) for i in f]
    assert all(-0.032 - 1e-9 <= v[2] <= 1e-9 for v in tops)                # sub-millimetre lippage
    assert len({round(v[2], 6) for v in tops}) > 10
    flat = B.marble_floor_parts(rect, 1, lippage=0.0)[0][2]
    assert all(abs(flat.v[i][2]) < 1e-12 for f, uv in tile_tops(flat) for i in f)
    # open 1.5 mm joints: no tile vertex within 0.075 cm of a cell joint
    cells = B.floor_layout(rect, 1)
    xs = {round(c["x0"], 6) for c in cells if c["x0"] > 1e-6}
    for v in tiles.v:
        assert all(abs(v[0] - j) >= 0.075 - 1e-9 for j in xs)
    # sliver-free: 485 cm leaves 5 cm (2.5 each end) - those joints are dropped
    assert min(c["x1"] - c["x0"] for c in cells) >= 6.0
    assert B.floor_layout(rect, 1) == B.floor_layout(rect, 1)
    assert [c["u0"] for c in B.floor_layout(rect, 1)] != [c["u0"] for c in B.floor_layout(rect, 2)]
    with pytest.raises(ValueError):
        B.marble_floor_parts(rect, gap=3.0)


# ------------------------------------------------------------------ Max wrappers
class _Node(object):
    def __init__(self, name=""):
        self.name, self.parent, self.pos = name, None, None


class _FakeRT(object):
    """Just enough pymxs for _build / kit.part / kit.group / kit.place / Smooth."""

    def __init__(self):
        self.scripts, self.mods = [], []

    def execute(self, s):
        self.scripts.append(s)
        return _Node(s.split('name:"', 1)[1].split('"', 1)[0])

    def Smooth(self):
        return types.SimpleNamespace()

    def addModifier(self, node, mod):
        self.mods.append((node, mod))

    def isProperty(self, obj, name):
        return True

    def Name(self, s):
        return s

    def Dummy(self):
        return _Node()

    def Point3(self, *a):
        return a

    def angleaxis(self, *a):
        return a

    def rotate(self, node, rot):
        pass


def test_build_wrappers(monkeypatch):
    fake = _FakeRT()
    for mod in (kit, furn_living, B):
        monkeypatch.setattr(mod, "rt", fake)
    monkeypatch.setattr(kit, "PARTS", [])
    rect = (0.0, 0.0, 500.0, 420.0)
    groups = [B.build_bulkhead(420.0, spots=(0.0,), cove_led=True), B.build_feature_wall(300.0, 270.0),
              B.build_shadow_skirting(rect, [("s", 100.0, 200.0)]), B.build_switch_plate(),
              B.build_marble_floor(rect)]
    assert [g.name for g in groups] == ["Bulkhead", "FeatureWall", "ShadowSkirting", "SwitchPlate", "MarbleFloor"]
    keys = {n.name: (k, t, m) for n, k, t, m in kit.PARTS}
    assert len(kit.PARTS) == 5 + 1 + 1 + 2 + 2
    assert keys["FeatureWall"] == ("copper_plaster", 200.0, 4)                  # one box map across the groove
    assert keys["MarbleFloor_Tiles"] == ("marble_floor", None, None)            # own UVs kept
    assert all(t > 0 and m == 4 for name, (k, t, m) in keys.items() if name != "MarbleFloor_Tiles")
    assert {k for k, t, m in keys.values()} <= USED
    assert all(n.parent is not None for n, k, t, m in kit.PARTS)
    assert len(fake.mods) == len(kit.PARTS)
    assert all(m.autoSmooth is True and m.threshold == 40.0 for n, m in fake.mods)
    assert all("convertToPoly" in s for s in fake.scripts)
    tiles_script = [s for s in fake.scripts if 'name:"MarbleFloor_Tiles"' in s][0]
    assert "setTVert" in tiles_script
    assert "setTVert" not in [s for s in fake.scripts if 'name:"FeatureWall"' in s][0]
    B.preview()
