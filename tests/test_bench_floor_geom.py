"""Off-Max geometry tests for tools/apartment/furn_bench_floor.py.

pymxs is stubbed while the module is imported (and the previous entry put
back), so only the pure-Python generator runs; build_pine_floor is exercised
against a recording fake of the runtime and a fake bench_common. LEGACY is
checked against a verbatim copy of today's bench1_scene.build_pine_floor.
"""
import math
import os
import random
import sys
import types
from collections import Counter

import pytest

APT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "apartment")
if APT not in sys.path:
    sys.path.insert(0, APT)

_prev = sys.modules.get("pymxs")
sys.modules["pymxs"] = types.SimpleNamespace(runtime=types.SimpleNamespace())
try:
    import furn_bench_floor as fbf  # noqa: E402
finally:
    if _prev is None:
        sys.modules.pop("pymxs", None)
    else:
        sys.modules["pymxs"] = _prev

MAIN = (-20.0, 500.0, 0.0, 640.0, 23)          # bench1_scene.build_architecture's two floors
NEXT = (-420.0, -20.0, 300.0, 640.0, 41)
CASES = [MAIN, NEXT, (0.0, 333.3, 12.5, 517.7, 5), (3.0, 61.0, 0.0, 95.0, 2)]
TOL = 1e-9


# ------------------------------------------------------------ today's floor, verbatim
def _quad_today(faces, a, b, c, d, verts, out):
    """apartment_scene._quad, verbatim."""
    pa, pb, pc = verts[a], verts[b], verts[c]
    u = [pb[i] - pa[i] for i in range(3)]
    v = [pc[i] - pa[i] for i in range(3)]
    n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    if n[0] * out[0] + n[1] * out[1] + n[2] * out[2] >= 0.0:
        faces += [(a, b, c), (a, c, d)]
    else:
        faces += [(a, c, b), (a, d, c)]


def floor_today(x0, x1, y0, y1, seed):
    """The mesh of bench1_scene.build_pine_floor as of 2026-11-06, verbatim but
    for the Max calls: (verts, faces, ids, tvs)."""
    PINE_W = 21.0
    PINE_U_CM, PINE_V_CM = 60.0, 90.0
    PINE_TINTS = ((0.0, 0.0, 0.0), (2.0, -60.0, 0.0), (-2.0, -56.0, 1.0), (4.0, -64.0, -1.0), (0.0, -58.0, 0.5),
                  (3.0, -54.0, 1.5))
    rnd = random.Random(seed)
    c, g = 0.2, 0.1
    verts, tvs, faces, ids = [], [], [], []
    x = x0
    while x < x1 - 1e-6:
        xb = min(x + PINE_W, x1)
        y = y0
        L = rnd.uniform(40.0, 300.0)
        while y < y1 - 1e-6:
            yb = min(y + L, y1)
            u0 = rnd.uniform(0.0, 1.0)
            u1 = u0 + (xb - x) / PINE_U_CM
            v0 = rnd.uniform(0.0, 1.0)
            v1 = v0 + (yb - y) / PINE_V_CM
            if rnd.random() < 0.5:
                u0, u1, v0, v1 = u1, u0, v1, v0
            du = c / PINE_U_CM * (1.0 if u1 > u0 else -1.0)
            dv = c / PINE_V_CM * (1.0 if v1 > v0 else -1.0)
            X0, X1, Y0, Y1 = x + g, xb - g, y + g, yb - g
            base = len(verts)
            verts += [(X0 + c, Y0 + c, 0.0), (X1 - c, Y0 + c, 0.0), (X1 - c, Y1 - c, 0.0), (X0 + c, Y1 - c, 0.0),
                      (X0, Y0, -c), (X1, Y0, -c), (X1, Y1, -c), (X0, Y1, -c),
                      (X0, Y0, -2.2), (X1, Y0, -2.2), (X1, Y1, -2.2), (X0, Y1, -2.2)]
            uv_out = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
            tvs += [(u0 + du, v0 + dv), (u1 - du, v0 + dv), (u1 - du, v1 - dv), (u0 + du, v1 - dv)]
            tvs += uv_out + uv_out
            t, m, b = base, base + 4, base + 8
            n0 = len(faces)
            _quad_today(faces, t, t + 1, t + 2, t + 3, verts, (0, 0, 1))
            for i, out in ((0, (0, -1, 1)), (1, (1, 0, 1)), (2, (0, 1, 1)), (3, (-1, 0, 1))):
                i2 = (i + 1) % 4
                _quad_today(faces, t + i, t + i2, m + i2, m + i, verts, out)
                _quad_today(faces, m + i, m + i2, b + i2, b + i, verts, (out[0], out[1], 0))
            _quad_today(faces, b, b + 3, b + 2, b + 1, verts, (0, 0, -1))
            ids += [2 + rnd.randrange(len(PINE_TINTS) - 1)] * (len(faces) - n0)
            y = yb
            L = rnd.uniform(180.0, 420.0)
        x = xb
    return verts, faces, ids, tvs


# ------------------------------------------------------------------ helpers
def rows_of(fm):
    rows = {}
    for bd in fm.boards:
        rows.setdefault(bd.row, []).append(bd)
    return [rows[k] for k in sorted(rows)]


def faces_of(fm, bd):
    a, n = bd.faces
    return fm.faces[a:a + n]


def verts_of(fm, bd):
    a, n = bd.verts
    return range(a, a + n)


def normal(fm, f):
    a, b, c = (fm.verts[i] for i in f)
    u = [b[k] - a[k] for k in range(3)]
    v = [c[k] - a[k] for k in range(3)]
    n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    ln = math.sqrt(sum(x * x for x in n))
    return tuple(x / ln for x in n)


def top_stations(fm, bd):
    """[(x, z)] across a board's top, -X to +X: its up-facing faces' vertices,
    two per station (the -Y and +Y ends), which must agree in z."""
    top = {i for f in faces_of(fm, bd) if normal(fm, f)[2] > 0.99 for i in f}
    by_x = {}
    for i in top:
        x, y, z = fm.verts[i]
        by_x.setdefault(round(x, 6), []).append(z)
    out = []
    for x in sorted(by_x):
        zs = by_x[x]
        assert len(zs) == 2 and abs(zs[0] - zs[1]) < 1e-12
        out.append((x, zs[0]))
    return out


def in_range(v, lo, hi):
    return lo - TOL <= v <= hi + TOL


# ------------------------------------------------------------ today's floor kept
@pytest.mark.parametrize("case", [MAIN, NEXT, (0.0, 333.3, 12.5, 517.7, 5)])
def test_legacy_is_todays_floor(case):
    fm = fbf.pine_floor_mesh(*case, **fbf.LEGACY)
    verts, faces, ids, tvs = floor_today(*case)
    assert fm.verts == verts and fm.faces == faces
    assert fm.ids == ids and fm.tvs == tvs
    assert set(fm.smooth) == {0} and len(fm.smooth) == len(faces)


def test_variation_keeps_todays_draws():
    """Board lengths, photo windows and IDs come from today's stream in today's
    order: the first board of the main floor is today's but for its width."""
    new, old = fbf.pine_floor_mesh(*MAIN).boards[0], fbf.pine_floor_mesh(*MAIN, **fbf.LEGACY).boards[0]
    assert new.cell[2:] == old.cell[2:] and new.uv[2:] == old.uv[2:] and new.mat == old.mat
    assert min(new.uv[:2]) == min(old.uv[:2])


def test_deterministic_and_seeded():
    a, b = fbf.pine_floor_mesh(*MAIN), fbf.pine_floor_mesh(*MAIN)
    assert a == b
    assert fbf.pine_floor_mesh(*(MAIN[:4] + (24,))).verts != a.verts


# ------------------------------------------------------------ layout
@pytest.mark.parametrize("case", CASES)
def test_boards_tile_the_rectangle(case):
    x0, x1, y0, y1, seed = case
    fm = fbf.pine_floor_mesh(*case)
    rows = rows_of(fm)
    assert rows[0][0].cell[0] == x0 and abs(rows[-1][0].cell[1] - x1) < TOL
    for ra, rb in zip(rows, rows[1:]):
        assert ra[0].cell[1] == rb[0].cell[0]
    for r in rows:
        assert len({bd.cell[:2] for bd in r}) == 1                       # one width per row
        assert r[0].cell[2] == y0 and abs(r[-1].cell[3] - y1) < TOL
        assert all(a.cell[3] == b.cell[2] for a, b in zip(r, r[1:]))    # end to end
    area = sum((bd.cell[1] - bd.cell[0]) * (bd.cell[3] - bd.cell[2]) for bd in fm.boards)
    assert area == pytest.approx((x1 - x0) * (y1 - y0), rel=1e-12)


@pytest.mark.parametrize("case", CASES)
def test_no_overlaps_and_gaps_in_range(case):
    fm = fbf.pine_floor_mesh(*case)
    lo, hi = fbf.HALF_GAP
    for bd in fm.boards:
        cx0, cx1, cy0, cy1 = bd.cell
        X0, X1, Y0, Y1 = bd.box
        for setback in (X0 - cx0, cx1 - X1, Y0 - cy0, cy1 - Y1):        # every edge back from its seam
            assert in_range(setback, lo, hi)
        for i in verts_of(fm, bd):                                       # the mesh keeps to the footprint
            x, y, z = fm.verts[i]
            assert in_range(x, X0, X1) and in_range(y, Y0, Y1)
    boxes = [bd.box for bd in fm.boards]
    for i, a in enumerate(boxes):
        for bx in boxes[i + 1:]:
            assert a[1] <= bx[0] or bx[1] <= a[0] or a[3] <= bx[2] or bx[3] <= a[2]
    rows = rows_of(fm)
    ends = [b.box[2] - a.box[3] for r in rows for a, b in zip(r, r[1:])]
    sides = [b.box[0] - a.box[1] for ra, rb in zip(rows, rows[1:]) for a in ra for b in rb
             if a.cell[2] < b.cell[3] and b.cell[2] < a.cell[3]]
    assert all(in_range(gp, 2.0 * lo, 2.0 * hi) for gp in ends + sides)  # 1-4 mm
    if len(sides) > 20:
        assert max(sides) - min(sides) > 0.15                            # not one gap everywhere


@pytest.mark.parametrize("case", CASES[:3])
def test_row_widths(case):
    rows = rows_of(fbf.pine_floor_mesh(*case))
    ws = [r[0].cell[1] - r[0].cell[0] for r in rows]
    lo, hi = fbf.WIDTHS
    assert all(in_range(w, lo, hi) for w in ws[:-2])                     # the last two may be ripped
    assert all(in_range(w, fbf.MIN_RIP, hi) for w in ws)
    assert max(ws[:-2]) - min(ws[:-2]) > 4.0


class _Draws(object):
    def __init__(self, values):
        self.values = list(values)

    def uniform(self, a, b):
        return self.values.pop(0)


def test_ripped_pieces_are_never_stubs():
    seams = lambda span, draws, wd=(17.0, 25.0): fbf._row_seams(0.0, span, wd, _Draws(draws), 8.0)
    assert seams(64.0, [20.0] * 4) == [0.0, 20.0, 40.0, 64.0]           # a 4 cm stub joins its row
    assert seams(64.0, [20.0] * 4, (17.0, 20.0)) == [0.0, 20.0, 40.0, 52.0, 64.0]   # too wide: two
    assert seams(75.0, [20.0] * 4) == [0.0, 20.0, 40.0, 60.0, 75.0]     # 15 cm is no stub
    assert seams(5.0, [20.0]) == [0.0, 5.0]
    for seed in range(12):
        fm = fbf.pine_floor_mesh(0.0, 130.0, 0.0, 517.0, seed)
        assert all(bd.cell[3] - bd.cell[2] >= fbf.MIN_RIP for bd in fm.boards)
        assert all(bd.cell[1] - bd.cell[0] >= fbf.MIN_RIP for bd in fm.boards)
    with pytest.raises(ValueError):
        fbf.pine_floor_mesh(0.0, 0.0, 0.0, 100.0, 1)


# ------------------------------------------------------------ the board tops
@pytest.mark.parametrize("case", CASES)
def test_tops_cupped_lifted_and_rolled(case):
    fm = fbf.pine_floor_mesh(*case)
    n = fbf.STRIPS
    for bd in fm.boards:
        st = top_stations(fm, bd)
        assert len(st) == n + 1
        zs = [z for x, z in st]
        assert all(abs(z) <= 0.15 for z in zs)                           # +- 1.5 mm
        cup = 0.5 * (zs[0] + zs[-1]) - zs[n // 2]
        assert in_range(cup, *fbf.CUP) and cup == pytest.approx(bd.cup, abs=TOL)
        roll = math.degrees(math.atan((zs[-1] - zs[0]) / (st[-1][0] - st[0][0])))
        assert abs(roll) <= fbf.TILT + TOL and roll == pytest.approx(bd.tilt, abs=1e-7)
        lift = zs[n // 2] + cup / 3.0
        assert abs(lift) <= fbf.LIFT + TOL and lift == pytest.approx(bd.lift, abs=TOL)
        for k in range(1, n):                                            # concave across the width
            chord = zs[0] + (zs[-1] - zs[0]) * (st[k][0] - st[0][0]) / (st[-1][0] - st[0][0])
            assert zs[k] < chord
    assert max(v[2] for v in fm.verts) <= 0.15 and min(v[2] for v in fm.verts) == -fbf.DEPTH
    if len(fm.boards) > 20:                                              # every board its own
        for key in ("lift", "tilt"):
            vals = [getattr(bd, key) for bd in fm.boards]
            assert min(vals) < 0.0 < max(vals)
        cups = [bd.cup for bd in fm.boards]
        assert max(cups) - min(cups) > 0.02


@pytest.mark.parametrize("case", CASES)
def test_each_board_is_a_closed_solid(case):
    fm = fbf.pine_floor_mesh(*case)
    for bd in fm.boards:
        fs = faces_of(fm, bd)
        vs = set(verts_of(fm, bd))
        assert all(i in vs for f in fs for i in f) and all(len(set(f)) == 3 for f in fs)
        count = Counter((f[i], f[(i + 1) % 3]) for f in fs for i in range(3))
        assert all(c == 1 for c in count.values()), "edge used twice in one direction"
        assert all((b, a) in count for (a, b) in count), "open edge"
        vol = 0.0
        for f in fs:
            p0, p1, p2 = (fm.verts[i] for i in f)
            vol += (p0[0] * (p1[1] * p2[2] - p1[2] * p2[1]) - p0[1] * (p1[0] * p2[2] - p1[2] * p2[0])
                    + p0[2] * (p1[0] * p2[1] - p1[1] * p2[0])) / 6.0
        X0, X1, Y0, Y1 = bd.box
        assert vol == pytest.approx((X1 - X0) * (Y1 - Y0) * fbf.DEPTH, rel=0.03)    # outward, full depth


def test_strips_and_smoothing():
    fm = fbf.pine_floor_mesh(*MAIN)
    n = fbf.STRIPS
    for bd in fm.boards:
        a, nf = bd.faces
        assert nf == 2 * (6 * n + 4)
        assert fm.smooth[a:a + nf] == [1] * (2 * n) + [0] * (nf - 2 * n)   # the top shades as one curve
        assert all(normal(fm, f)[2] > 0.99 for f in fm.faces[a:a + 2 * n])
    old = fbf.pine_floor_mesh(*MAIN, **fbf.LEGACY)
    assert set(old.smooth) == {0} and all(bd.faces[1] == 20 and bd.verts[1] == 12 for bd in old.boards)


# ------------------------------------------------------------ photo windows, IDs
@pytest.mark.parametrize("case", CASES)
def test_uvs_in_each_boards_window(case):
    fm = fbf.pine_floor_mesh(*case)
    assert len(fm.tvs) == len(fm.verts)
    turned = set()
    for bd in fm.boards:
        u0, u1, v0, v1 = bd.uv
        cx0, cx1, cy0, cy1 = bd.cell
        assert abs(u1 - u0) == pytest.approx((cx1 - cx0) / fbf.PINE_U_CM)
        assert abs(v1 - v0) == pytest.approx((cy1 - cy0) / fbf.PINE_V_CM)
        assert 0.0 <= min(u0, u1) <= 1.0 and 0.0 <= min(v0, v1) <= 1.0
        for i in verts_of(fm, bd):
            u, v = fm.tvs[i]
            assert in_range(u, min(u0, u1), max(u0, u1)) and in_range(v, min(v0, v1), max(v0, v1))
        # the photo runs with the board at its own scale (today's eased-edge inset aside)
        top = sorted({i for f in faces_of(fm, bd)[:2 * fbf.STRIPS] for i in f}, key=lambda i: fm.verts[i])
        a, z = top[0], top[-1]
        su = (fm.tvs[z][0] - fm.tvs[a][0]) / (fm.verts[z][0] - fm.verts[a][0]) * fbf.PINE_U_CM
        sv = (fm.tvs[z][1] - fm.tvs[a][1]) / (fm.verts[z][1] - fm.verts[a][1]) * fbf.PINE_V_CM
        assert abs(su) == pytest.approx(1.0, abs=0.06) and abs(sv) == pytest.approx(1.0, abs=0.06)
        assert (su < 0) == (u1 < u0) and (sv < 0) == (v1 < v0)
        turned.add(u1 < u0)
    if len(fm.boards) > 10:
        assert turned == {True, False}


@pytest.mark.parametrize("case", CASES)
def test_material_ids(case):
    fm = fbf.pine_floor_mesh(*case)
    assert len(fm.ids) == len(fm.faces) == len(fm.smooth)
    assert set(fm.ids) <= {2, 3, 4, 5, 6}
    for bd in fm.boards:
        a, nf = bd.faces
        assert set(fm.ids[a:a + nf]) == {bd.mat}                         # one tint per board
    if len(fm.boards) > 30:
        assert set(fm.ids) == {2, 3, 4, 5, 6}


# ---------------------------------------------------------------- wrapper
class _Node(object):
    def __init__(self, name):
        self.name = name


class _FakeRT(object):
    def __init__(self):
        self.scripts = []

    def execute(self, s):
        self.scripts.append(s)
        return _Node(s.split('name:"', 1)[1].split('"', 1)[0])


def _array(script, key):
    """Items of the MAXScript array literal after `key`."""
    body = script.split(key, 1)[1].split(")", 1)[0]
    return [p.strip("[]") for p in body.split("],[")] if body.startswith("[") else body.split(",")


def test_build_pine_floor(monkeypatch):
    fake, calls = _FakeRT(), []
    bench = types.SimpleNamespace(
        A=types.SimpleNamespace(finish=lambda node, key, tile=100.0, maptype=4: calls.append(
            ("finish", node, key, tile, maptype)) or node),
        box=lambda *a: calls.append(("box",) + a))
    monkeypatch.setattr(fbf, "rt", fake)
    monkeypatch.setitem(sys.modules, "bench_common", bench)
    node = fbf.build_pine_floor("main", *MAIN)
    assert node.name == "FloorPine_main"
    assert calls == [("finish", node, "planks_pine", None, None),
                     ("box", "Subfloor_main", -20.0, 500.0, 0.0, 640.0, -2.6, -2.2, "subfloor", 100.0)]
    fm, s = fbf.pine_floor_mesh(*MAIN), fake.scripts[0]
    verts = _array(s, "vertices:#(")
    assert len(verts) == len(fm.verts) and len(_array(s, "tverts:#(")) == len(fm.tvs)
    assert [float(c) for c in verts[7].split(",")] == pytest.approx(fm.verts[7], abs=1e-4)
    assert _array(s, "faces:#(")[0] == "%d,%d,%d" % tuple(i + 1 for i in fm.faces[0])
    assert [int(i) for i in _array(s, "pfi = #(")] == fm.ids
    assert [int(i) for i in _array(s, "pfs = #(")] == fm.smooth
    assert "setFaceSmoothGroup pfm f pfs[f]" in s and "setFaceMatID pfm f pfi[f]" in s
    # the variation keywords pass through: today's floor
    old = fbf.build_pine_floor("next", *NEXT, **fbf.LEGACY)
    assert old.name == "FloorPine_next" and calls[-1][1] == "Subfloor_next"
    s = fake.scripts[1]
    assert set(_array(s, "pfs = #(")) == {"0"}
    assert len(_array(s, "vertices:#(")) == 12 * len(fbf.pine_floor_mesh(*NEXT, **fbf.LEGACY).boards)
