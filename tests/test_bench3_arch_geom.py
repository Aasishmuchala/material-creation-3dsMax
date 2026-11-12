"""Geometry tests for tools/apartment/bench3_arch.py - runs without 3ds Max.

pymxs is stubbed while the module is imported (and the previous entry put back). Every mesh
must be a closed, consistently wound solid whose every shell faces outward, free of NaN, at
real-world size; every section a simple polygon whose visible corners are all filleted; own-UV
parts carry UVs on every face. The build_* wrappers run against a fake runtime.
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
    import bench3_arch as B  # noqa: E402
finally:
    if _saved_pymxs is None:
        sys.modules.pop("pymxs", None)
    else:
        sys.modules["pymxs"] = _saved_pymxs

USED = {"oak_slat", "metal_black", "stone_floor", "paint_white", "metal_steel"}


# ------------------------------------------------------------------ helpers
def _find(parent, i):
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


def _labels(md):
    parent = list(range(len(md.v)))
    for f in md.f:
        r = _find(parent, f[0])
        for i in f[1:]:
            parent[_find(parent, i)] = r
    return [_find(parent, i) for i in range(len(md.v))]


def components(md):
    lab = _labels(md)
    return len({lab[i] for f in md.f for i in f})


def shell_volumes(md):
    """Signed volume of every connected shell (> 0: wound outward)."""
    lab, vol = _labels(md), {}
    for f in md.f:
        a = md.v[f[0]]
        for k in range(1, len(f) - 1):
            b, c = md.v[f[k]], md.v[f[k + 1]]
            t = (a[0] * (b[1] * c[2] - b[2] * c[1]) + a[1] * (b[2] * c[0] - b[0] * c[2])
                 + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
            vol[lab[f[0]]] = vol.get(lab[f[0]], 0.0) + t
    return list(vol.values())


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
    vols = shell_volumes(md)
    assert min(vols) > 0.0, "%s: a shell is wound inside out" % name
    assert B._volume(md) > 0.0


def own_uv(md):
    return (len(md.fuv) == len(md.f) and all(uv is not None and len(uv) == len(f) for f, uv in zip(md.f, md.fuv))
            and all(math.isfinite(c) for uv in md.fuv for t in uv for c in t))


def check_parts(parts):
    assert parts
    for name, key, md, tile, smooth in parts:
        assert key in kit.MAT_KEYS and key in USED, (name, key)
        assert (tile is None or tile > 0) and smooth == 0
        assert_solid(md, name)
        if tile is None:
            assert own_uv(md), "%s: a face without UVs" % name
    return {p[0]: p for p in parts}


def bbox(md):
    return B._bbox(md)


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
    """Simple closed polygon, no duplicate points, every vertex turning more than 25 degrees
    buried (hidden(p)): no razor-sharp visible edge."""
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


def box_dist(p, lo, hi):
    return math.sqrt(sum(max(lo[k] - p[k], 0.0, p[k] - hi[k]) ** 2 for k in range(3)))


# ------------------------------------------------------------------ keys
def test_material_keys_declared():
    assert "oak_slat" in kit.MAT_KEYS and "stone_floor" in kit.MAT_KEYS
    assert USED <= set(kit.MAT_KEYS)


# ------------------------------------------------------------------ eased box
def test_eased_box():
    calls = []
    md = B._eased_box_md(0.0, 9.0, -2.4, 0.0, 0.0, 50.0, 0.1, lambda a, s, p: calls.append((a, s)) or (p[0], p[2]))
    assert_solid(md, "eased box")
    assert components(md) == 1 and len(md.f) == 6 * 7 * 7 and own_uv(md)
    assert {c for c in calls} == {(a, s) for a in range(3) for s in (-1, 1)}
    (x0, y0, z0), (x1, y1, z1) = bbox(md)
    assert (x0, x1, y0, y1, z0, z1) == pytest.approx((0.0, 9.0, -2.4, 0.0, 0.0, 50.0))
    lo, hi = (0.1, -2.3, 0.1), (8.9, -0.1, 49.9)
    assert all(box_dist(p, lo, hi) == pytest.approx(0.1, abs=1e-9) for p in md.v)      # exact 1 mm rounds
    face = [p for p in md.v if abs(p[1] + 2.4) < 1e-9]                                    # the flat front
    assert len(face) == 16                                                               # 4 x 4: with supports
    assert min(p[0] for p in face) == pytest.approx(0.1) and max(p[2] for p in face) == pytest.approx(49.9)
    xs = sorted({round(p[0], 9) for p in face})
    assert xs == pytest.approx([0.1, 0.1 + B.SUPPORT, 8.9 - B.SUPPORT, 8.9])
    vol = B._volume(md)
    assert 9.0 * 2.4 * 50.0 * 0.99 < vol < 9.0 * 2.4 * 50.0
    with pytest.raises(ValueError):
        B._eased_box_md(0.0, 0.2, 0.0, 1.0, 0.0, 1.0, 0.1)


# ------------------------------------------------------------------ slat layout
LAYOUTS = [(300.0, 0), (287.3, 0), (95.0, 0), (30.0, 0), (412.0, 6), (250.0, 3), (180.0, 4), (500.0, 8),
           (61.5, 1), (333.3, 5)]


@pytest.mark.parametrize("W,N", LAYOUTS)
def test_slat_layout(W, N):
    boards = B.slat_layout(W, N)
    assert boards[0][0] == pytest.approx(-W / 2) and boards[-1][1] == pytest.approx(W / 2)
    for (a0, a1, ka), (b0, b1, kb) in zip(boards, boards[1:]):
        assert b0 - a1 == pytest.approx(B.GROOVE_W)                                   # 1.5 cm grooves
    for (a0, a1, ka), (b0, b1, kb) in zip(boards, reversed(boards)):
        assert (a0, a1) == pytest.approx((-b1, -b0)) and ka == kb                       # symmetric
    std = {"slat": B.SLAT_W, "pilaster": B.PIL_W}
    for x0, x1, k in boards[1:-1]:
        assert x1 - x0 == pytest.approx(std[k])                                         # full boards
    for x0, x1, k in (boards[0], boards[-1]):
        assert B.END_MIN - 1e-9 <= x1 - x0 < std[k] + B.GROOVE_W + B.END_MIN            # ripped / widened ends
    kinds = [k for _a, _b, k in boards]
    if N == 0:
        assert set(kinds) == {"slat"}
    else:
        pil = [i for i, k in enumerate(kinds) if k == "pilaster"]
        assert pil
        assert all(j - i - 1 == N for i, j in zip(pil, pil[1:]))                        # N slats per bay
        assert pil[0] <= N and len(kinds) - 1 - pil[-1] <= N


def test_slat_layout_choice_and_errors():
    # 30 cm: three full slats (a slat on the centre line); 40.5: four, a groove on it
    assert [b[1] - b[0] for b in B.slat_layout(30.0)] == pytest.approx([9.0, 9.0, 9.0])
    assert [b[1] - b[0] for b in B.slat_layout(40.5)] == pytest.approx([9.0] * 4)
    assert B.slat_layout(40.5)[1][1] == pytest.approx(-0.75)
    lay = B.slat_layout(61.5, 1)                                                          # widened pilasters
    assert [k for a, b, k in lay] == ["pilaster", "slat", "pilaster"]
    with pytest.raises(ValueError):
        B.slat_layout(20.0)
    with pytest.raises(ValueError):
        B.slat_layout(300.0, -1)
    with pytest.raises(ValueError):
        B.slat_layout(300.0, 4, pilaster_w=5.0)


def test_board_windows():
    w = B.board_windows(60, 4)
    assert len(w) == 60 and w == B.board_windows(60, 4) and w != B.board_windows(60, 5)
    assert B.window_sep(60) == B.WIN_SEP and B.window_sep(400) == pytest.approx(0.025)
    for i in range(60):
        assert 0.0 <= w[i][0] < 1.0 and 0.0 <= w[i][1] < 1.0 and abs(w[i][2]) == 1.0 and abs(w[i][3]) == 1.0
        for j in range(i):
            du, dv = abs(w[i][0] - w[j][0]), abs(w[i][1] - w[j][1])
            assert math.hypot(min(du, 1.0 - du), min(dv, 1.0 - dv)) >= B.WIN_SEP - 1e-12
    long_run = B.board_windows(180, 1)
    sep = B.window_sep(180)
    for i in range(180):
        for j in range(i):
            du, dv = abs(long_run[i][0] - long_run[j][0]), abs(long_run[i][1] - long_run[j][1])
            assert math.hypot(min(du, 1.0 - du), min(dv, 1.0 - dv)) >= sep - 1e-12
    assert {f for _u, _v, f, _g in w} == {-1.0, 1.0} and {g for _u, _v, _f, g in w} == {-1.0, 1.0}


# ------------------------------------------------------------------ slat panel
@pytest.mark.parametrize("W,H,N,seed", [(300.0, 280.0, 0, 0), (412.0, 290.0, 6, 1), (95.0, 250.0, 0, 2),
                                        (180.0, 265.0, 4, 3)])
def test_slat_panel(W, H, N, seed):
    parts = check_parts(B.slat_panel_parts(W, H, seed, N))
    boards = B.slat_layout(W, N)
    slats = [b for b in boards if b[2] == "slat"]
    pils = [b for b in boards if b[2] == "pilaster"]
    assert set(parts) == {"SlatPanel_Boards", "SlatPanel_Backing"} | ({"SlatPanel_Pilasters"} if pils else set())
    wood = [parts["SlatPanel_Boards"][2]] + ([parts["SlatPanel_Pilasters"][2]] if pils else [])
    assert components(wood[0]) == len(slats) and (not pils or components(wood[1]) == len(pils))
    assert all(parts[n][1] == "oak_slat" and parts[n][3] is None for n in parts if n != "SlatPanel_Backing")
    assert parts["SlatPanel_Backing"][1] == "metal_black"
    lo = [min(bbox(m)[0][k] for m in wood) for k in range(3)]
    hi = [max(bbox(m)[1][k] for m in wood) for k in range(3)]
    assert lo + hi == pytest.approx([-W / 2, -B.SLAT_T, 0.0, W / 2, 0.0, H])          # stands on the floor
    (bx0, by0, bz0), (bx1, by1, bz1) = bbox(parts["SlatPanel_Backing"][2])
    assert (bx0, bx1, by0, by1, bz0, bz1) == pytest.approx((-W / 2 + 0.3, W / 2 - 0.3, -1.4, 0.1, -0.1, H + 0.1))
    assert by0 - (-B.SLAT_T) == pytest.approx(B.GROOVE_D)                                # 1 cm deep grooves
    assert boards[0][0] < bx0 < boards[0][1] and boards[-1][0] < bx1 < boards[-1][1]   # hidden at the ends
    for x0, x1, kind in boards:
        assert x1 - x0 >= B.END_MIN - 1e-9

    def board_of(x):
        hit = [b for b in boards if b[0] - 1e-6 <= x <= b[1] + 1e-6]
        assert len(hit) == 1, x
        return hit[0]

    wins = B.board_windows(len(boards), seed)
    for md in wood:
        for p in md.v:                                                                   # every edge eased 1 mm
            x0, x1, k = board_of(p[0])
            assert box_dist(p, (x0 + 0.1, -2.3, 0.1), (x1 - 0.1, -0.1, H - 0.1)) == pytest.approx(0.1, abs=1e-9)
        # own UVs: the grain runs up V, each board shows its own window
        nfront = 0
        for f, uv in zip(md.f, md.fuv):
            pts = [md.v[i] for i in f]
            if not all(abs(p[1] + B.SLAT_T) < 1e-9 for p in pts):
                continue
            nfront += 1
            x0, x1, k = board_of(sum(p[0] for p in pts) / len(pts))
            u0, v0, fu, fv = wins[boards.index((x0, x1, k))]
            xc = 0.5 * (x0 + x1)
            for p, t in zip(pts, uv):
                assert t[0] == pytest.approx(u0 + fu * (p[0] - xc) / B.OAK_TILE, abs=1e-9)
                assert t[1] == pytest.approx(v0 + fv * p[2] / B.OAK_TILE, abs=1e-9)
        assert nfront >= 9 * (components(md))                                           # 3 x 3 flat quads each
        # the groove walls carry the grain up V as well
        for f, uv in zip(md.f, md.fuv):
            pts = [md.v[i] for i in f]
            if len({round(p[0], 9) for p in pts}) == 1 and max(p[2] for p in pts) - min(p[2] for p in pts) > 50.0:
                dz = pts[1][2] - pts[0][2] or pts[2][2] - pts[1][2]
                dv = uv[1][1] - uv[0][1] or uv[2][1] - uv[1][1]
                assert abs(dv) == pytest.approx(abs(dz) / B.OAK_TILE, rel=1e-9)
    starts = {(round(u, 9), round(v, 9)) for u, v, _a, _b in wins}
    assert len(starts) == len(boards)                                                   # no two boards match


def test_slat_panel_options():
    p = check_parts(B.slat_panel_parts(240.0, 250.0, 0, 0, to_ceiling=False))
    (x0, y0, z0), (x1, y1, z1) = bbox(p["SlatPanel_Backing"][2])
    assert z0 == pytest.approx(-0.1) and z1 == pytest.approx(249.95)                     # stops under the tops
    q = check_parts(B.slat_panel_parts(240.0, 250.0, 0, 0, tile=200.0))
    a, b = p["SlatPanel_Boards"][2], q["SlatPanel_Boards"][2]
    assert a.v == b.v and a.fuv != b.fuv
    assert B.slat_panel_parts(240.0, 250.0, 7)[0][2].fuv != B.slat_panel_parts(240.0, 250.0, 8)[0][2].fuv
    with pytest.raises(ValueError):
        B.slat_panel_parts(300.0, 10.0)
    with pytest.raises(ValueError):
        B.slat_panel_parts(20.0, 280.0)
    with pytest.raises(ValueError):
        B.slat_panel_parts(300.0, 280.0, tile=5.0)


# ------------------------------------------------------------------ limestone floor
def test_setout():
    assert B._setout(0.0, 400.0, 90.0) == pytest.approx([65.0, 155.0, 245.0, 335.0])
    assert B._setout(0.0, 540.0, 90.0) == pytest.approx([90.0, 180.0, 270.0, 360.0, 450.0])
    assert B._setout(0.0, 60.0, 90.0) == []
    assert B._setout(0.0, 100.0, 90.0) == pytest.approx([50.0])
    for L in (91.0, 133.0, 260.0, 455.0, 611.7, 640.0):
        j = B._setout(-30.0, L - 30.0, 90.0)
        assert j[0] - (-30.0) == pytest.approx((L - 30.0) - j[-1])                    # equal cuts both ends
        assert j[0] + 30.0 >= 45.0 - 1e-9                                               # never under half a tile


FLOORS = [((-250.0, -200.0, 250.0, 200.0), 0), ((0.0, 0.0, 640.0, 455.0), 3), ((10.0, -40.0, 95.0, 300.0), 5)]


@pytest.mark.parametrize("rect,seed", FLOORS)
def test_limestone_floor(rect, seed):
    parts = check_parts(B.limestone_floor_parts(rect, seed))
    name, key, tiles, tile, sm = parts["LimestoneFloor_Tiles"]
    assert key == "stone_floor" and tile is None
    assert parts["LimestoneFloor_Subfloor"][1] == "metal_black"
    cells = B.limestone_layout(rect, seed)
    assert components(tiles) == len(cells) and len(tiles.f) == 26 * len(cells)
    x0, y0, x1, y1 = rect
    (bx0, by0, bz0), (bx1, by1, bz1) = bbox(tiles)
    assert (bx0, by0, bx1, by1) == pytest.approx((x0 + 0.1, y0 + 0.1, x1 - 0.1, y1 - 0.1))
    assert bz0 == pytest.approx(-2.0) and -0.032 - 1e-9 <= bz1 <= 0.0
    (sx0, sy0, sz0), (sx1, sy1, sz1) = bbox(parts["LimestoneFloor_Subfloor"][2])
    assert (sx0, sy0, sx1, sy1) == pytest.approx((x0, y0, x1, y1)) and sz1 == pytest.approx(B.SUB_TOP)
    # cells tile the room exactly; full tiles 90 x 90, cuts never under half a tile, equal at both walls
    assert sum((c["x1"] - c["x0"]) * (c["y1"] - c["y0"]) for c in cells) == pytest.approx((x1 - x0) * (y1 - y0))
    cols = sorted({(c["x0"], c["x1"]) for c in cells})
    rows = sorted({(c["y0"], c["y1"]) for c in cells})
    for spans, lo, hi in ((cols, x0, x1), (rows, y0, y1)):
        widths = [b - a for a, b in spans]
        assert all(w <= 90.0 + 1e-9 for w in widths)
        assert all(w == pytest.approx(90.0) for w in widths[1:-1])
        assert widths[0] == pytest.approx(widths[-1])
        assert min(widths) >= min(45.0, hi - lo) - 1e-9
    # the 2 mm joints are open: no tile vertex within 1 mm of a joint line
    jx = {a for a, b in cols if a > x0 + 1e-6}
    jy = {a for a, b in rows if a > y0 + 1e-6}
    for v in tiles.v:
        assert all(abs(v[0] - j) >= 0.1 - 1e-9 for j in jx) and all(abs(v[1] - j) >= 0.1 - 1e-9 for j in jy)
    # every tile its own window of the 180 cm repeat: a full tile is 0.5 x 0.5 (less joint and ease)
    assert len({(round(c["u0"], 9), round(c["v0"], 9)) for c in cells}) == len(cells)
    inset = 0.1 + B.LS_EASE + B.SUPPORT
    for i, c in enumerate(cells):
        f, uv = tiles.f[26 * i], tiles.fuv[26 * i]
        assert all(math.isclose(tiles.v[j][0], v, abs_tol=1e-9) for j, v in
                   zip(f, (c["x0"] + inset, c["x1"] - inset, c["x1"] - inset, c["x0"] + inset)))
        su = max(t[0] for t in uv) - min(t[0] for t in uv)
        sv = max(t[1] for t in uv) - min(t[1] for t in uv)
        wx, wy = (c["x1"] - c["x0"] - 2 * inset) / 180.0, (c["y1"] - c["y0"] - 2 * inset) / 180.0
        assert (su, sv) == pytest.approx((wy, wx) if c["sym"] & 1 else (wx, wy), abs=1e-9)
        if c["x1"] - c["x0"] > 89.0 and c["y1"] - c["y0"] > 89.0:
            assert su == pytest.approx((90.0 - 2 * inset) / 180.0)


def test_limestone_lippage_and_errors():
    rect = (0.0, 0.0, 485.0, 362.0)
    tiles = B.limestone_floor_parts(rect, 1)[0][2]
    tops = [tiles.v[i] for k in range(0, len(tiles.f), 26) for i in tiles.f[k]]
    assert all(-0.032 - 1e-9 <= v[2] <= 1e-9 for v in tops)                            # sub-millimetre lippage
    assert len({round(v[2], 6) for v in tops}) > 10
    flat = B.limestone_floor_parts(rect, 1, lippage=0.0)[0][2]
    assert all(abs(flat.v[i][2]) < 1e-12 for k in range(0, len(flat.f), 26) for i in flat.f[k])
    assert B.limestone_layout(rect, 1) == B.limestone_layout(rect, 1)
    assert [c["u0"] for c in B.limestone_layout(rect, 1)] != [c["u0"] for c in B.limestone_layout(rect, 2)]
    assert len({c["sym"] for c in B.limestone_layout((0.0, 0.0, 900.0, 900.0), 0)}) == 8
    with pytest.raises(ValueError):
        B.limestone_floor_parts(rect, gap=3.0)
    with pytest.raises(ValueError):
        B.limestone_layout(rect, tile=10.0)


# ------------------------------------------------------------------ flush skirting
def test_flush_skirting_section():
    prof = B.flush_skirting_profile()
    assert_section(prof, lambda p: p[1] <= 1e-6 or p[1] >= B.FS_TOP - 1e-6 or p[0] <= -B.FS_BACK + 1e-6, "skirting")
    us, zs = [p[0] for p in prof], [p[1] for p in prof]
    assert (min(us), max(us), min(zs), max(zs)) == pytest.approx((-1.2, 0.0, -B.FS_FOOT, 7.2))
    assert B.FS_FOOT < -B.SUB_TOP                                                         # clear of the subfloor
    assert B.FS_TOP == pytest.approx(7.2) and B.FS_BACK == pytest.approx(1.2)
    face = [z for u, z in prof if abs(u) < 1e-9]
    assert max(z for z in face if z < 6.5) == pytest.approx(6.0 - 0.1)                   # 6 cm face, 1 mm arris
    assert max(u for u, z in prof if 6.049 < z < 6.951) == pytest.approx(-1.0)        # 1 x 1 cm shadow line
    with pytest.raises(ValueError):
        B.flush_skirting_profile(2.0)


def test_flush_skirting_ring():
    rect = (-250.0, -200.0, 250.0, 200.0)
    md = B.flush_skirting_md(rect)
    assert_solid(md, "skirting")
    assert components(md) == 1
    (x0, y0, z0), (x1, y1, z1) = bbox(md)
    assert (x0, y0, x1, y1, z0, z1) == pytest.approx((-251.2, -201.2, 251.2, 201.2, -B.FS_FOOT, 7.2))
    inside = lambda v: min(v[0] + 250.0, 250.0 - v[0], v[1] + 200.0, 200.0 - v[1])
    assert max(inside(v) for v in md.v) == pytest.approx(0.0, abs=1e-6)                  # flush: nothing proud
    assert max(inside(v) for v in md.v if 6.049 < v[2] < 6.951) == pytest.approx(-1.0)  # the shadow line


def test_flush_skirting_openings():
    rect = (0.0, 0.0, 600.0, 450.0)
    md = B.flush_skirting_md(rect, [("s", 120.0, 230.0), ("n", 200.0, 360.0)])
    assert_solid(md, "skirting runs")
    assert components(md) == 2
    for x, y, z in md.v:
        if y < 3.0:
            assert not 120.0 + 1e-6 < x < 230.0 - 1e-6
        if y > 447.0:
            assert not 200.0 + 1e-6 < x < 360.0 - 1e-6
    assert B.flush_skirting_md(rect, [("s", 0, 600), ("e", 0, 450), ("n", 0, 600), ("w", 0, 450)]).v == []
    p = check_parts(B.flush_skirting_parts(rect, height=8.0, gap=1.5, recess=1.5))
    assert p["FlushSkirting"][1] == "paint_white"
    (x0, y0, z0), (x1, y1, z1) = bbox(p["FlushSkirting"][2])
    assert z1 == pytest.approx(9.7) and x0 == pytest.approx(-1.7)


# ------------------------------------------------------------------ slot diffuser
def test_fin_section():
    sec = B.fin_section()
    assert_section(sec, lambda p: False, "fin")
    area = 0.5 * sum(sec[i][0] * sec[(i + 1) % len(sec)][1] - sec[(i + 1) % len(sec)][0] * sec[i][1]
                     for i in range(len(sec)))
    assert area > 0.0 and area == pytest.approx(1.8 * 0.08, rel=0.08)                   # 0.8 mm blade
    low = min(sec, key=lambda p: p[1])
    high = max(sec, key=lambda p: p[1])
    assert low[0] < 0.0 < high[0]                                                         # lower edge to -Y


@pytest.mark.parametrize("L,W", [(140.0, 9.0), (240.0, 12.0), (60.0, 7.5)])
def test_slot_diffuser(L, W):
    p = check_parts(B.slot_diffuser_parts(L, W))
    assert set(p) == {"SlotDiffuser_Frame", "SlotDiffuser_Fins", "SlotDiffuser_Plenum"}
    assert p["SlotDiffuser_Frame"][1] == "metal_steel" and p["SlotDiffuser_Fins"][1] == "metal_steel"
    assert p["SlotDiffuser_Plenum"][1] == "metal_black"
    frame, fins, plenum = (p[n][2] for n in ("SlotDiffuser_Frame", "SlotDiffuser_Fins", "SlotDiffuser_Plenum"))
    assert components(frame) == 2 and components(fins) == 2 and components(plenum) == 2
    (x0, y0, z0), (x1, y1, z1) = bbox(frame)
    assert (x0, x1, y0, y1, z0, z1) == pytest.approx((-L / 2, L / 2, -W / 2, W / 2, -0.25, 2.0))
    allv = frame.v + fins.v + plenum.v
    assert min(v[2] for v in allv) == pytest.approx(-0.25)                                # hangs 2.5 mm
    face = [v for v in frame.v if abs(v[2] + 0.25) < 1e-9]
    assert max(abs(v[0]) for v in face) == pytest.approx(L / 2 - 0.1)                    # 1 mm outer arris
    assert max(abs(v[1]) for v in face) == pytest.approx(W / 2 - 0.1)
    a, b = L / 2 - 1.5, W / 2 - 1.5
    clear = (0.5 + 1e-6, b - 0.12 - 1e-6)
    for v in frame.v:                                                                     # the slots are open
        assert not (clear[0] < abs(v[1]) < clear[1] and abs(v[0]) < a - 0.12 - 1e-6)
    # one blade per slot, inside it, 5 mm above the face, leaning to throw to the front
    lab = _labels(fins)
    blades = {}
    for i, v in enumerate(fins.v):
        blades.setdefault(lab[i], []).append(v)
    assert sorted(min(v[1] for v in bl) > 0.0 for bl in blades.values()) == [False, True]   # one each side
    for bl in blades.values():
        assert len({v[1] > 0.0 for v in bl}) == 1
        assert all(clear[0] < abs(v[1]) < clear[1] for v in bl)
        assert min(v[2] for v in bl) == pytest.approx(-0.25 + B.DF_FIN_LIFT)
        assert max(v[2] for v in bl) < B.DF_THROAT
        assert max(abs(v[0]) for v in bl) == pytest.approx(a - 0.12 + 0.05)              # into the end webs
        low, high = min(bl, key=lambda v: v[2]), max(bl, key=lambda v: v[2])
        assert low[1] < high[1]
    (px0, py0, pz0), (px1, py1, pz1) = bbox(plenum)
    assert pz0 == pytest.approx(0.05) and pz1 == pytest.approx(B.DF_PLENUM + 0.05)
    hx0, hx1, hy0, hy1 = B.slot_diffuser_hole(L, W)
    assert hx0 < px0 - 0.15 and px1 + 0.15 < hx1 and hy0 < py0 - 0.15 and py1 + 0.15 < hy1
    assert -L / 2 + 1.0 < hx0 and hx1 < L / 2 - 1.0 and -W / 2 + 1.0 < hy0 and hy1 < W / 2 - 1.0
    assert (hx1 - hx0, hy1 - hy0) == pytest.approx((L - 2.2, W - 2.2))


def test_slot_diffuser_errors():
    with pytest.raises(ValueError):
        B.slot_diffuser_parts(20.0)
    with pytest.raises(ValueError):
        B.slot_diffuser_parts(140.0, 5.0)
    with pytest.raises(KeyError):
        B.slot_diffuser_parts(140.0, 9.0, "no_such_key")
    white = B.slot_diffuser_parts(140.0, 9.0, "paint_white")
    assert [k for n, k, md, t, s in white] == ["paint_white", "metal_steel", "metal_black"]
    assert B.diffuser_frame_profile()
    assert_section(B.diffuser_frame_profile(), lambda p: p[1] >= B.EPS - 1e-6, "diffuser frame")


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
    groups = [B.build_slat_panel(300.0, 280.0, 1, 6), B.build_limestone_floor(rect),
              B.build_flush_skirting(rect, [("s", 100.0, 200.0)]), B.build_slot_diffuser()]
    assert [g.name for g in groups] == ["SlatPanel", "LimestoneFloor", "FlushSkirting", "SlotDiffuser"]
    keys = {n.name: (k, t, m) for n, k, t, m in kit.PARTS}
    assert len(kit.PARTS) == 3 + 2 + 1 + 3
    own = {"SlatPanel_Boards", "SlatPanel_Pilasters", "LimestoneFloor_Tiles"}
    assert keys["SlatPanel_Boards"] == ("oak_slat", None, None)                          # own UVs kept
    assert keys["SlatPanel_Pilasters"] == ("oak_slat", None, None)
    assert keys["LimestoneFloor_Tiles"] == ("stone_floor", None, None)
    assert all(t > 0 and m == 4 for name, (k, t, m) in keys.items() if name not in own)
    assert {k for k, t, m in keys.values()} == USED
    assert all(n.parent is not None for n, k, t, m in kit.PARTS)
    assert len(fake.mods) == len(kit.PARTS)
    assert all(m.autoSmooth is True and m.threshold == 40.0 for n, m in fake.mods)
    assert all("convertToPoly" in s for s in fake.scripts)
    for s in fake.scripts:
        name = s.split('name:"', 1)[1].split('"', 1)[0]
        assert ("setTVert" in s) == (name in own), name
    B.preview()
