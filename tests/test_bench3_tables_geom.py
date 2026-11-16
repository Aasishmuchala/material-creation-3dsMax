"""Off-Max geometry tests for tools/apartment/furn_bench3_tables.py (the nesting green-onyx coffee
tables, the turned walnut side table and the brass tray side table of the benchmark-3 living room).

pymxs is stubbed while the module is imported (and the previous entry put back), so only the
pure-Python cage generators run; the build_* wrappers are exercised with furn_living._build /
kit.soften / kit.group / kit.place faked.
"""
import math
import os
import sys
import types

import pytest

APT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "apartment")
if APT not in sys.path:
    sys.path.insert(0, APT)

_prev = sys.modules.get("pymxs")
sys.modules["pymxs"] = types.SimpleNamespace(runtime=types.SimpleNamespace())
try:
    import kit  # noqa: E402
    import furn_living  # noqa: E402
    import furn_bench3_tables as fb3  # noqa: E402
finally:
    if _prev is None:
        sys.modules.pop("pymxs", None)
    else:
        sys.modules["pymxs"] = _prev

ALLOWED = {"onyx", "bronze", "wood_dark", "metal_brass"}
SEEDS = (0, 1, 2, 3)


# ------------------------------------------------------------------ helpers
def bounds(mds):
    if not isinstance(mds, (list, tuple)):
        mds = [mds]
    vs = [v for md in mds for v in md.v]
    return [(min(v[k] for v in vs), max(v[k] for v in vs)) for k in range(3)]


def volume(md):
    tot = 0.0
    for f in md.f:
        a = md.v[f[0]]
        for k in range(1, len(f) - 1):
            b, c = md.v[f[k]], md.v[f[k + 1]]
            tot += (a[0] * (b[1] * c[2] - b[2] * c[1]) + a[1] * (b[2] * c[0] - b[0] * c[2])
                    + a[2] * (b[0] * c[1] - b[1] * c[0]))
    return tot / 6.0


def check_mesh(md):
    """Non-empty, finite, valid faces; closed: every directed edge paired with its reverse
    exactly once; a positive enclosed volume (consistently outward faces)."""
    assert md.v and md.f
    assert all(math.isfinite(c) for v in md.v for c in v)
    nv = len(md.v)
    for f in md.f:
        assert len(f) >= 3 and len(set(f)) == len(f) and all(0 <= i < nv for i in f)
    count = {}
    for f in md.f:
        for i in range(len(f)):
            e = (f[i], f[(i + 1) % len(f)])
            count[e] = count.get(e, 0) + 1
    assert all(c == 1 for c in count.values()), "edge used twice in one direction"
    assert all((b, a) in count for (a, b) in count), "open edge"
    vol = volume(md)
    assert vol > 0.0, "faces point inwards"
    return vol


def own_uv(md):
    return (len(md.fuv) == len(md.f) and all(u is not None and len(u) == len(f) for u, f in zip(md.fuv, md.f))
            and all(math.isfinite(c) for u in md.fuv for t in u for c in t))


def check_parts(parts):
    assert parts
    for name, mat, md, tile, smooth in parts:
        assert mat in kit.MAT_KEYS and mat in ALLOWED, (name, mat)
        assert tile > 0 and smooth == 0
        check_mesh(md)
        assert own_uv(md), name


def part(parts, name):
    return [p for p in parts if p[0] == name][0][2]


def face_normal(md, f):
    n = [0.0, 0.0, 0.0]
    for i in range(len(f)):
        a, b = md.v[f[i]], md.v[f[(i + 1) % len(f)]]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    return n


def area2(pts):
    return 0.5 * sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                     for i in range(len(pts)))


def turns(pts):
    n = len(pts)
    out = []
    for i in range(n):
        a, p, c = pts[i - 1], pts[i], pts[(i + 1) % n]
        d1 = (p[0] - a[0], p[1] - a[1])
        d2 = (c[0] - p[0], c[1] - p[1])
        out.append(math.atan2(d1[0] * d2[1] - d1[1] * d2[0], d1[0] * d2[0] + d1[1] * d2[1]))
    return out


def curvature_radii(pts):
    n = len(pts)
    tr = turns(pts)
    out = []
    for i in range(n):
        a, p, c = pts[i - 1], pts[i], pts[(i + 1) % n]
        ds = 0.5 * (math.hypot(p[0] - a[0], p[1] - a[1]) + math.hypot(c[0] - p[0], c[1] - p[1]))
        out.append(ds / tr[i] if abs(tr[i]) > 1e-12 else float("inf"))
    return out


def seg_dist(px, py, ax, ay, bx, by):
    ex, ey = bx - ax, by - ay
    l2 = ex * ex + ey * ey
    t = max(0.0, min(1.0, ((px - ax) * ex + (py - ay) * ey) / l2)) if l2 > 0.0 else 0.0
    return math.hypot(px - ax - ex * t, py - ay - ey * t)


def bdist(pts, x, y):
    n = len(pts)
    return min(seg_dist(x, y, pts[i][0], pts[i][1], pts[(i + 1) % n][0], pts[(i + 1) % n][1]) for i in range(n))


def inside(pts, x, y):
    res = False
    j = len(pts) - 1
    for i in range(len(pts)):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > y) != (yj > y) and x < xi + (y - yi) * (xj - xi) / (yj - yi):
            res = not res
        j = i
    return res


def segments_cross(p1, p2, q1, q2):
    def o(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return (o(q1, q2, p1) * o(q1, q2, p2) < -1e-12) and (o(p1, p2, q1) * o(p1, p2, q2) < -1e-12)


def simple_polyline(pts, closed):
    n = len(pts)
    m = n if closed else n - 1
    for i in range(m):
        for j in range(i + 2, m):
            if closed and i == 0 and j == n - 1:
                continue
            if segments_cross(pts[i], pts[(i + 1) % n], pts[j], pts[(j + 1) % n]):
                return False
    return True


def centroid2(pts):
    a = cx = cy = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        c = x0 * y1 - x1 * y0
        a += c
        cx += (x0 + x1) * c
        cy += (y0 + y1) * c
    return (cx / (3.0 * a), cy / (3.0 * a))


def tri_margin(legs, c):
    a, b, d = legs
    s = 1.0 if (b[0] - a[0]) * (d[1] - a[1]) - (b[1] - a[1]) * (d[0] - a[0]) > 0.0 else -1.0
    return min(s * ((q[0] - p[0]) * (c[1] - p[1]) - (q[1] - p[1]) * (c[0] - p[0]))
               / math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in ((a, b), (b, d), (d, a)))


def overlap_fraction(lower, upper, step=1.5):
    """Share of the upper outline's area that lies over the lower outline (grid estimate)."""
    xs, ys = [p[0] for p in upper], [p[1] for p in upper]
    tot = ov = 0
    x = min(xs) + 0.5 * step
    while x < max(xs):
        y = min(ys) + 0.5 * step
        while y < max(ys):
            if inside(upper, x, y):
                tot += 1
                ov += inside(lower, x, y)
            y += step
        x += step
    return ov / float(tot)


def to_local(p, at):
    """Group-space (x, y) into a slab's own frame (at = (x, y, deg))."""
    c, s = math.cos(math.radians(at[2])), math.sin(math.radians(at[2]))
    dx, dy = p[0] - at[0], p[1] - at[1]
    return (dx * c + dy * s, -dx * s + dy * c)


def r_at(prof, z):
    """Largest radius of a section where it crosses height z."""
    best = None
    for (r0, z0), (r1, z1) in zip(prof, prof[1:]):
        if min(z0, z1) <= z <= max(z0, z1) and z0 != z1:
            r = r0 + (r1 - r0) * (z - z0) / (z1 - z0)
            best = r if best is None else max(best, r)
    assert best is not None, z
    return best


# ------------------------------------------------------------------ fixtures
@pytest.fixture(scope="module")
def layouts():
    return {s: fb3.onyx_tables_layout(s) for s in SEEDS}


@pytest.fixture(scope="module")
def onyx():
    return {s: fb3.onyx_tables_parts(s) for s in (0, 1)}


@pytest.fixture(scope="module")
def walnut():
    return fb3.walnut_side_table_parts()


@pytest.fixture(scope="module")
def brass():
    return fb3.brass_tray_table_parts()


# ------------------------------------------------------------------ material keys
def test_material_keys_declared():
    for key in ("onyx", "bronze"):
        assert key in kit.MAT_KEYS
    for key in ALLOWED:
        assert key in kit.MAT_KEYS


def test_every_part_uses_allowed_keys(onyx, walnut, brass):
    used = {p[1] for p in onyx[0] + walnut + brass}
    assert used == ALLOWED
    assert used <= set(kit.MAT_KEYS)


# ------------------------------------------------------------------ 2-D tools
def test_round_poly_fillets_and_supports():
    out = fb3._round_poly([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)], [0.0, 2.0, 0.0], step_deg=10.0)
    assert out[0] == (0.0, 0.0) and out[-1] == (10.0, 10.0)
    arc = [p for p in out if 8.0 - 1e-9 <= p[0] <= 10.0 and 0.0 <= p[1] <= 2.0 + 1e-9]
    assert len(arc) >= 9                                                              # 90 deg in 10 deg steps
    for x, y in arc:
        assert abs(math.hypot(x - 8.0, y - 2.0) - 2.0) < 1e-9                         # tangent 2 cm round
    s = fb3.SUPPORT
    assert any(abs(x - (8.0 - s)) < 1e-9 and abs(y) < 1e-12 for x, y in out)         # support points
    assert any(abs(x - 10.0) < 1e-12 and abs(y - (2.0 + s)) < 1e-9 for x, y in out)
    # a radius too big for its legs shrinks to fit (arcs meet mid-segment, no duplicate points)
    sq = fb3._round_poly([(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)], [0.0, 5.0, 5.0, 0.0])
    assert all(math.hypot(a[0] - b[0], a[1] - b[1]) > 1e-7 for a, b in zip(sq, sq[1:]))
    assert max(x for x, y in sq) <= 2.0 + 1e-9


def test_edge_profile():
    prof, kb, kt = fb3.edge_profile(27.5, 32.0, 1.5, 1.5)
    assert kb == 1 and kt == len(prof) - 2
    assert prof[0] == (1.5 + fb3.SUPPORT, 27.5) and prof[-1] == (1.5 + fb3.SUPPORT, 32.0)
    assert prof[kb] == pytest.approx((1.5, 27.5)) and prof[kt] == pytest.approx((1.5, 32.0))
    for d, z in prof[kb:kt + 1]:
        if 1e-9 < d < 1.5 - 1e-9:
            cz = 30.5 if z > 29.75 else 29.0
            assert abs(math.hypot(d - 1.5, z - cz) - 1.5) < 1e-9                       # 1.5 cm rounds
    band = [z for d, z in prof if abs(d) < 1e-12]
    assert abs(min(band) - 29.0) < 1e-9 and abs(max(band) - 30.5) < 1e-9
    with pytest.raises(ValueError):
        fb3.edge_profile(0.0, 2.0, 1.5, 1.5)


def test_planar_uv_convention():
    # a direction at angle a in the map shows at a + deg on the piece; one repeat per tile cm
    u0, v0 = fb3.planar_uv(0.0, 0.0, 30.0, 100.0, 0.2, 0.7)
    assert (u0, v0) == pytest.approx((0.2, 0.7))
    u, v = fb3.planar_uv(100.0 * math.cos(math.radians(30.0)), 100.0 * math.sin(math.radians(30.0)), 30.0, 100.0,
                         0.2, 0.7)
    assert (u - u0, v - v0) == pytest.approx((1.0, 0.0))


# ------------------------------------------------------------------ pebble outlines
@pytest.mark.parametrize("which", ("lower", "upper"))
@pytest.mark.parametrize("seed", SEEDS)
def test_pebble_outline(which, seed):
    spec = fb3.SLABS[which]
    L, W = spec["length"], spec["width"]
    ol = fb3.pebble_outline(which, seed)
    n = len(ol)
    assert n == spec["n"]
    xs, ys = [p[0] for p in ol], [p[1] for p in ol]
    assert abs(min(xs) + 0.5 * L) < 1e-9 and abs(max(xs) - 0.5 * L) < 1e-9          # exactly length x width
    assert abs(min(ys) + 0.5 * W) < 1e-9 and abs(max(ys) - 0.5 * W) < 1e-9
    assert 0.72 < area2(ol) / (L * W) < 0.86                                          # counter-clockwise pebble
    assert max(abs(t) for t in turns(ol)) < math.radians(6.0)                         # smooth: no kinks
    radii = curvature_radii(ol)
    assert min(r for r in radii if r > 0.0) > 8.0                                     # no tight corners
    assert all(abs(r) > 100.0 for r in radii if r < 0.0)                              # only gentle hollows
    # not an ellipse: well off the ellipse of its own bounding box
    a, b = 0.5 * L, 0.5 * W
    dev = max(math.hypot(x - a * math.cos(math.atan2(y / b, x / a)), y - b * math.sin(math.atan2(y / b, x / a)))
              for x, y in ol)
    assert dev > 2.5
    # asymmetric left-right and front-back (the egg mostly end to end, its front flatter than its back)
    lr, fb = (6.0, 5.0) if which == "lower" else (3.5, 1.8)
    assert max(bdist(ol, -x, y) for x, y in ol[::3]) > lr
    assert max(bdist(ol, x, -y) for x, y in ol[::3]) > fb
    # the lower stone is broad at the left, the upper egg at the right
    left = [y for x, y in ol if x < -0.4 * L]
    right = [y for x, y in ol if x > 0.4 * L]
    if which == "lower":
        assert max(left) - min(left) > max(right) - min(right) + 5.0
    else:
        assert max(right) - min(right) > max(left) - min(left) + 3.0
    # simple polygon, star-shaped about its centroid (the cap fans need it)
    assert simple_polyline(ol, True)
    cx, cy = centroid2(ol)
    ang = [math.atan2(y - cy, x - cx) for x, y in ol]
    steps = [((ang[(i + 1) % n] - ang[i] + math.pi) % (2.0 * math.pi)) - math.pi for i in range(n)]
    assert all(s > 0.0 for s in steps) and abs(sum(steps) - 2.0 * math.pi) < 1e-9


def test_pebble_outline_seeds():
    assert fb3.pebble_outline("lower", 0) == fb3.pebble_outline("lower", 0)
    assert fb3.pebble_outline("lower", 0) != fb3.pebble_outline("lower", 1)
    assert fb3.pebble_outline("upper", 2) != fb3.pebble_outline("upper", 3)
    assert len(fb3.pebble_outline("upper", 0, n=96)) == 96


# ------------------------------------------------------------------ the two tiers
@pytest.mark.parametrize("seed", SEEDS)
def test_two_tiers(layouts, seed):
    L = layouts[seed]
    lo, up = L["lower"], L["upper"]
    assert lo["top"] == 32.0 and up["top"] == 39.0
    assert abs(lo["under"] - 27.5) < 1e-12 and abs(up["under"] - 34.5) < 1e-12        # 4.5 cm slabs
    assert up["under"] - lo["top"] == pytest.approx(2.5)                              # the upper clears the lower
    # the group origin is under the centre of the larger table's footprint
    xs, ys = [p[0] for p in lo["outline"]], [p[1] for p in lo["outline"]]
    assert abs(min(xs) + 60.0) < 1e-9 and abs(max(xs) - 60.0) < 1e-9
    assert abs(min(ys) + 31.0) < 1e-9 and abs(max(ys) - 31.0) < 1e-9
    # the upper overlaps the lower in plan, partly: its left end over the lower's back-right
    f = overlap_fraction(lo["outline"], up["outline"])
    assert 0.15 < f < 0.30, f
    assert not inside(lo["outline"], *up["centroid"])                                 # not stacked on it
    assert up["centroid"][0] > 30.0 and up["centroid"][1] > 15.0                      # right and behind
    # the upper outline is the local pebble turned and moved rigidly
    for p, q in zip(up["local"][::11], up["outline"][::11]):
        assert to_local(q, up["at"]) == pytest.approx(p, abs=1e-9)


# ------------------------------------------------------------------ slabs
@pytest.mark.parametrize("seed", (0, 1))
def test_onyx_slabs(onyx, layouts, seed):
    parts = onyx[seed]
    check_parts(parts)
    L = layouts[seed]
    for which, tag in (("lower", "Lower"), ("upper", "Upper")):
        s = L[which]
        md = part(parts, "OnyxTables_%sTop" % tag)
        (x0, x1), (y0, y1), (z0, z1) = bounds(md)
        assert abs(z0 - s["under"]) < 1e-9 and abs(z1 - s["top"]) < 1e-9
        loc = [to_local(v, s["at"]) for v in md.v]
        spec = fb3.SLABS[which]
        lx = [p[0] for p in loc]
        ly = [p[1] for p in loc]
        assert abs(max(lx) - min(lx) - spec["length"]) < 1e-9 and abs(max(ly) - min(ly) - spec["width"]) < 1e-9
        # cap fans: every top / underside face flat and facing straight up / down
        ups = downs = 0
        for f in md.f:
            zs = [md.v[i][2] for i in f]
            nrm = face_normal(md, f)
            if all(abs(z - s["top"]) < 1e-9 for z in zs):
                assert nrm[2] > 0.0 and abs(nrm[0]) + abs(nrm[1]) < 1e-9 * max(1.0, nrm[2])
                ups += 1
            if all(abs(z - s["under"]) < 1e-9 for z in zs):
                assert nrm[2] < 0.0
                downs += 1
        assert ups >= spec["n"] and downs >= spec["n"]
        # rounded 1.5 cm: nothing at the sharp corner, the flat top stops 1.5 cm in from the edge
        ol = s["outline"]
        for x, y in ol[::12]:
            near = min(math.sqrt((v[0] - x) ** 2 + (v[1] - y) ** 2 + (v[2] - s["top"]) ** 2) for v in md.v)
            assert near > 0.4
        flat = [v for v in md.v if abs(v[2] - s["top"]) < 1e-9]
        assert min(bdist(ol, v[0], v[1]) for v in flat[::5]) > 1.49
        # the band: vertical 1.5 cm between the rounds, at the outline itself
        band = [v for v in md.v if s["under"] + 1.5 + 0.01 < v[2] < s["top"] - 1.5 - 0.01]
        assert band and max(bdist(ol, v[0], v[1]) for v in band) < 1e-6


@pytest.mark.parametrize("seed", (0, 1))
def test_onyx_uvs(onyx, layouts, seed):
    parts = onyx[seed]
    L = layouts[seed]
    windows = []
    for which, tag in (("lower", "Lower"), ("upper", "Upper")):
        s = L[which]
        md = part(parts, "OnyxTables_%sTop" % tag)
        deg, u0, v0 = fb3.onyx_slab_uv(which, seed)
        # the onyx bands cross the slab: the map's axes run 20-45 deg off its length
        assert 20.0 <= abs(deg) <= 45.0
        assert abs(deg - fb3.BAND_DEG[which]) <= 5.0 + 1e-12
        # planar on the top at 100 cm per repeat, in the slab's own frame
        us = []
        for f, uv in zip(md.f, md.fuv):
            if all(abs(md.v[i][2] - s["top"]) < 1e-9 for i in f):
                for i, (u, v) in zip(f, uv):
                    eu, ev = fb3.planar_uv(*to_local(md.v[i], s["at"]), deg, 100.0, u0, v0)
                    assert abs(u - eu) < 1e-9 and abs(v - ev) < 1e-9
                    us.append(u)
        # ... so U spans the flat top's extent along the turned map's U axis, at 100 cm a repeat
        c, sn = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        proj = [x * c + y * sn for x, y in s["local"]]
        expect = (max(proj) - min(proj) - 2.0 * (fb3.ONYX_R + fb3.SUPPORT)) / 100.0
        assert expect > 0.6 and abs(max(us) - min(us) - expect) < 0.01
        windows.append((u0, v0))
        # the edge: no UV seam on the top arris, true scale down the round and the band
        N = fb3.SLABS[which]["n"]
        prof, kb, kt = fb3.edge_profile(s["under"], s["top"], fb3.ONYX_R, fb3.ONYX_R)
        seen = {}
        for f, uv in zip(md.f, md.fuv):
            for i, t in zip(f, uv):
                if i < N * len(prof):
                    seen.setdefault(i, set()).add((round(t[0], 9), round(t[1], 9)))
        for i in range(0, N, 16):
            assert len(seen[kt * N + i]) == 1
        for k in range(kb + 1, kt - 1):
            for i in range(0, N, 24):
                ua, ub = seen[k * N + i], seen[(k + 1) * N + i]
                if len(ua) != 1 or len(ub) != 1:
                    continue
                ua, ub = list(ua)[0], list(ub)[0]
                seg = math.hypot(prof[k + 1][0] - prof[k][0], prof[k + 1][1] - prof[k][1])
                assert abs(math.hypot(ub[0] - ua[0], ub[1] - ua[1]) * 100.0 - seg) < 1e-6
    # each slab its own window of the stone
    assert math.hypot(windows[0][0] - windows[1][0], windows[0][1] - windows[1][1]) > 0.15


def test_onyx_uv_seeds_vary():
    vals = [fb3.onyx_slab_uv("lower", s) for s in range(6)]
    assert len({round(v[1], 3) for v in vals}) == 6 and len({round(v[2], 3) for v in vals}) == 6
    assert max(v[1] for v in vals) - min(v[1] for v in vals) > 0.1
    assert max(v[2] for v in vals) - min(v[2] for v in vals) > 0.1
    assert fb3.onyx_slab_uv("upper", 3) == fb3.onyx_slab_uv("upper", 3)


# ------------------------------------------------------------------ legs
def test_leg_profile():
    prof = fb3.leg_profile(27.5)
    assert prof[0] == (0.0, 0.0) and prof[-1][0] == 0.0 and abs(prof[-1][1] - 27.6) < 1e-12   # 1 mm into the slab
    assert all(r >= 0.0 for r, z in prof)
    assert all(r > 0.0 for r, z in prof[1:-1])                                         # poles only at the ends
    assert simple_polyline(prof, False)
    assert all(math.hypot(a[0] - b[0], a[1] - b[1]) > 1e-7 for a, b in zip(prof, prof[1:]))
    # the glide stands flat on the floor, 5.2 cm across
    assert abs(max(r for r, z in prof if abs(z) < 1e-12) - (fb3.PAD_R - 0.2)) < 1e-9
    assert abs(max(r for r, z in prof if z < fb3.PAD_H) - fb3.PAD_R) < 1e-9
    # the ball: a sphere of BALL_R round (0, BALL_Z), wider than the 3.5 cm shaft, held by the cup
    ball = [(r, z) for r, z in prof if abs(math.hypot(r, z - fb3.BALL_Z) - fb3.BALL_R) < 1e-9]
    assert len(ball) >= 8 and max(r for r, z in ball) > fb3.LEG_R + 0.3
    assert max(z for r, z in ball) > fb3.BALL_Z + 1.5 and min(z for r, z in ball) < fb3.CUP_TOP
    assert fb3.CUP_TOP < fb3.BALL_Z                                    # the cup holds it below its equator
    rim = [r for r, z in prof if abs(z - fb3.CUP_TOP) < 1e-9]
    assert min(rim) > math.sqrt(fb3.BALL_R ** 2 - (fb3.CUP_TOP - fb3.BALL_Z) ** 2)    # a hair gap at the rim
    # the neck narrower than the shaft, the shaft 3.5 cm round, the flange 6.8 cm under the slab
    neck = r_at(prof, fb3.BALL_Z + fb3.BALL_R * math.sin(math.acos(fb3.NECK_R / fb3.BALL_R)) + 0.2)
    assert neck < fb3.LEG_R - 0.5
    for z in (8.0, 15.0, 25.0):
        assert abs(r_at(prof, z) - fb3.LEG_R) < 1e-9
    assert abs(max(r for r, z in prof) - fb3.FLANGE_R) < 1e-9
    assert all(z > 27.5 - fb3.FLANGE_T - 0.4 for r, z in prof if r > fb3.LEG_R + 0.4 and z > 10.0)
    with pytest.raises(ValueError):
        fb3.leg_profile(10.0)


@pytest.mark.parametrize("seed", SEEDS)
def test_leg_layout(layouts, seed):
    L = layouts[seed]
    lo, up = L["lower"], L["upper"]
    for s, inset, lim in ((lo, fb3.LEG_INSET["lower"], 0.55), (up, fb3.LEG_INSET["upper"], 0.35)):
        legs, ol = s["legs"], s["outline"]
        assert len(legs) == 3
        for x, y in legs:
            assert inside(ol, x, y) and bdist(ol, x, y) >= inset - 0.3 - 1e-9          # under the slab, inset
            assert bdist(ol, x, y) - fb3.FLANGE_R > fb3.ONYX_R + 0.5     # the flange on the flat underside
        for i in range(3):
            for j in range(i + 1, 3):
                assert math.hypot(legs[i][0] - legs[j][0], legs[i][1] - legs[j][1]) >= fb3.LEG_MIN_SEP - 1e-9
        # it stands: the slab's centroid deep inside the legs' triangle, hard to tip
        m = tri_margin(legs, centroid2(ol))
        assert m >= 8.0 - 1e-9 and abs(m - s["margin"]) < 1e-9
        assert fb3.tip_ratio(legs, ol) > lim
        # ordered counter-clockwise round the centroid from the front
        c = centroid2(ol)
        keys = [(math.atan2(y - c[1], x - c[0]) + 0.5 * math.pi) % (2.0 * math.pi) for x, y in legs]
        assert keys == sorted(keys)
    # the upper table's legs pass outside the lower slab with an air gap
    for x, y in up["legs"]:
        assert not inside(lo["outline"], x, y)
        assert bdist(lo["outline"], x, y) - fb3.LEG_R >= fb3.LEG_CLEAR - 1e-9
    # and are well clear of the lower table's legs (their glides too)
    for p in up["legs"]:
        for q in lo["legs"]:
            assert math.hypot(p[0] - q[0], p[1] - q[1]) > 2.0 * fb3.PAD_R + 5.0


def test_leg_layout_errors():
    ol = fb3.pebble_outline("upper", 0)
    with pytest.raises(ValueError):
        fb3.leg_layout(ol, 7.5, avoid=ol, clear=1.0)                                    # nowhere to stand
    legs, margin = fb3.leg_layout(ol, 7.5)
    assert margin >= 8.0 and len(legs) == 3


@pytest.mark.parametrize("seed", (0, 1))
def test_onyx_legs(onyx, layouts, seed):
    parts = onyx[seed]
    L = layouts[seed]
    names = [p[0] for p in parts]
    assert names == (["OnyxTables_LowerTop"] + ["OnyxTables_LowerLeg%d" % k for k in range(3)]
                     + ["OnyxTables_UpperTop"] + ["OnyxTables_UpperLeg%d" % k for k in range(3)])
    for which, tag in (("lower", "Lower"), ("upper", "Upper")):
        s = L[which]
        slab = part(parts, "OnyxTables_%sTop" % tag)
        for k, (x, y) in enumerate(s["legs"]):
            md = part(parts, "OnyxTables_%sLeg%d" % (tag, k))
            (bx0, bx1), (by0, by1), (bz0, bz1) = bounds(md)
            assert abs(bz0) < 1e-12 and abs(bz1 - (s["under"] + fb3.SINK)) < 1e-9   # floor to 1 mm into the slab
            assert abs(0.5 * (bx0 + bx1) - x) < 0.02 and abs(0.5 * (by0 + by1) - y) < 0.02
            assert bx1 - bx0 <= 2.0 * fb3.FLANGE_R + 1e-9
            # 3.5 cm round all the way up the shaft (rings only where it starts and stops)
            mid = [(v[2], math.hypot(v[0] - x, v[1] - y)) for v in md.v if 6.3 < v[2] < s["under"] - 0.9]
            assert max(abs(r - fb3.LEG_R) for z, r in mid) < 1e-9
            zs = [z for z, r in mid]
            assert min(zs) < 7.0 and max(zs) > s["under"] - 1.0
            # what touches the floor is the glide (nothing else at z = 0)
            foot = [math.hypot(v[0] - x, v[1] - y) for v in md.v if abs(v[2]) < 1e-12]
            assert foot and max(foot) <= fb3.PAD_R
            # UVs: V climbs the leg, U runs round it at true scale (bronze, 30 cm per repeat)
            us = [t[0] for uv in md.fuv for t in uv]
            assert 2.0 * math.pi * fb3.FLANGE_R / fb3.BRONZE_TILE == pytest.approx(max(us))
            # the flange sits on the slab's flat underside (1 mm into it)
            top = [v for v in md.v if v[2] > s["under"]]
            assert top and all(bdist(s["outline"], v[0], v[1]) > fb3.ONYX_R for v in top)
        assert bounds(slab)[2][0] == pytest.approx(s["under"])
    # nothing of the lower table reaches up to the upper slab
    lo_top = max(bounds(p[2])[2][1] for p in parts if p[0].startswith("OnyxTables_Lower"))
    assert lo_top == pytest.approx(32.0) and lo_top < L["upper"]["under"] - 2.0


def test_onyx_totals(onyx):
    parts = onyx[0]
    (x0, x1), (y0, y1), (z0, z1) = fb3.footprint(parts)
    assert abs(x0 + 60.0) < 1e-9 and 90.0 < x1 < 100.0
    assert abs(y0 + 31.0) < 1e-9 and 50.0 < y1 < 60.0
    assert abs(z0) < 1e-12 and abs(z1 - 39.0) < 1e-9
    assert {p[1] for p in parts} == {"onyx", "bronze"}
    assert sum(len(p[2].f) for p in parts) < 80000


def test_onyx_deterministic_and_varied(onyx):
    again = fb3.onyx_tables_parts(0)
    assert [p[2].v for p in again] == [p[2].v for p in onyx[0]]
    assert [p[2].fuv for p in again] == [p[2].fuv for p in onyx[0]]
    assert part(onyx[0], "OnyxTables_LowerTop").v != part(onyx[1], "OnyxTables_LowerTop").v
    assert part(onyx[0], "OnyxTables_UpperTop").fuv != part(onyx[1], "OnyxTables_UpperTop").fuv


# ------------------------------------------------------------------ walnut side table
def test_walnut_side_table(walnut):
    check_parts(walnut)
    assert [p[0] for p in walnut] == ["WalnutSideTable_Top", "WalnutSideTable_Column", "WalnutSideTable_Foot"]
    assert {p[1] for p in walnut} == {"wood_dark"}
    (x0, x1), (y0, y1), (z0, z1) = bounds([p[2] for p in walnut])
    assert x0 == pytest.approx(-27.5) and x1 == pytest.approx(27.5) and y0 == pytest.approx(-27.5)
    assert abs(z0) < 1e-12 and abs(z1 - 50.0) < 1e-9                                   # 50 high, 55 across
    top, col, foot = (p[2] for p in walnut)
    tb = bounds(top)
    assert tb[2] == pytest.approx((47.0, 50.0))                                         # 3 cm top
    rt = [math.hypot(v[0], v[1]) for v in top.v]
    assert max(rt) == pytest.approx(27.5, abs=1e-9)
    flat = [math.hypot(v[0], v[1]) for v in top.v if abs(v[2] - 50.0) < 1e-12]
    assert max(flat) < 27.5 - 1.19                                                      # 1.2 cm round over the edge
    under = [math.hypot(v[0], v[1]) for v in top.v if abs(v[2] - 47.0) < 1e-12]
    assert max(under) < 27.5 - 0.89
    fb_ = bounds(foot)
    assert fb_[0] == pytest.approx((-20.0, 20.0)) and fb_[2] == pytest.approx((0.0, fb3.WT_LAND_Z))   # 40 cm foot
    contact = [math.hypot(v[0], v[1]) for v in foot.v if abs(v[2]) < 1e-12]
    assert min(contact) > 16.5 and max(contact) < 20.0 - 0.44                           # stands on its bearing ring
    edge = [v[2] for v in foot.v if math.hypot(v[0], v[1]) > 19.99]
    assert 1.5 < max(edge) < fb3.WT_FOOT_EDGE                                           # a soft, rounded edge
    cb = bounds(col)
    assert abs(cb[2][0] - (fb3.WT_LAND_Z - fb3.SINK)) < 1e-9 and abs(cb[2][1] - (47.0 + fb3.SINK)) < 1e-9
    low = [math.hypot(v[0], v[1]) for v in col.v if v[2] < fb3.WT_LAND_Z + 0.2]
    assert max(low) < fb3.WT_LAND_R                                                     # on the foot's flat landing
    land = [v for v in foot.v if abs(v[2] - fb3.WT_LAND_Z) < 1e-12]
    assert max(math.hypot(v[0], v[1]) for v in land) == pytest.approx(fb3.WT_LAND_R)


def test_walnut_column_profile():
    prof = fb3.column_profile()
    assert prof[0][0] == 0.0 and prof[-1][0] == 0.0 and simple_polyline(prof, False)
    assert all(r > 0.0 for r, z in prof[1:-1])
    shaft = [r_at(prof, z) for z in (12.0, 20.0, 30.0, 38.0)]
    assert all(2.75 < r < 3.8 for r in shaft) and shaft == sorted(shaft, reverse=True)    # tapering up
    # two beads proud of the shaft under the capital; the capital flares to its flange
    c = fb3.COL
    beads = [r for r, z in prof if 38.0 < z < 43.0]
    assert max(beads) == pytest.approx(c["r1"] - c["bead_in"] + c["bead_r"], abs=1e-6)
    assert max(r for r, z in prof) == pytest.approx(c["cap_r"])
    assert max(r for r, z in prof if z < 6.0) == pytest.approx(c["base_r"])


def test_walnut_uvs(walnut):
    top, col, foot = (p[2] for p in walnut)
    # top and foot planar: the grain (V) runs along X, 70 cm per repeat
    for md, ztop in ((top, 50.0), (foot, None)):
        for f, uv in zip(md.f, md.fuv):
            if ztop is not None and not all(abs(md.v[i][2] - ztop) < 1e-12 for i in f):
                continue
            if ztop is None and not all(md.v[i][2] < 0.3 + 1e-12 and math.hypot(md.v[i][0], md.v[i][1]) < 16.0
                                        for i in f):
                continue
            for i, (u, v) in zip(f, uv):
                x, y = md.v[i][0], md.v[i][1]
                assert u == pytest.approx(0.5 - y / 70.0, abs=1e-9) and v == pytest.approx(0.5 + x / 70.0, abs=1e-9)
    # the column: cylindrical - U depends only on the angle round it (true scale on the shaft), V climbs
    for f, uv in zip(col.f, col.fuv):
        zs = [col.v[i][2] for i in f]
        if not all(10.0 < z < 35.0 for z in zs):
            continue
        for i, (u, v) in zip(f, uv):
            x, y = col.v[i][0], col.v[i][1]
            ang = (math.atan2(y, x) - 0.5 * math.pi) % (2.0 * math.pi)
            if ang > 2.0 * math.pi - 1e-6 or u > 2.0 * math.pi * fb3.WT_COL_R / 70.0 - 1e-9:
                continue                                                                 # the seam
            assert u == pytest.approx(ang * fb3.WT_COL_R / 70.0, abs=1e-9)
        lo = [t[1] for i, t in zip(f, uv) if col.v[i][2] == min(zs)]
        hi = [t[1] for i, t in zip(f, uv) if col.v[i][2] == max(zs)]
        assert min(hi) > max(lo)                                                         # V up the column
    assert len({round(math.atan2(v[1], v[0]), 6) for v in col.v if 20.0 < v[2] < 21.0}) == 48


# ------------------------------------------------------------------ brass tray table
def test_brass_tray_table(brass):
    check_parts(brass)
    assert [p[0] for p in brass] == ["BrassTrayTable_Base", "BrassTrayTable_Stem", "BrassTrayTable_Tray"]
    (x0, x1), (y0, y1), (z0, z1) = bounds([p[2] for p in brass])
    assert x0 == pytest.approx(-20.0) and x1 == pytest.approx(20.0) and y1 == pytest.approx(20.0)
    assert abs(z0) < 1e-12 and abs(z1 - 52.0) < 1e-6                                   # 52 high, 40 across
    base, stem, tray = (p[2] for p in brass)
    bb = bounds(base)
    assert bb[0] == pytest.approx((-15.0, 15.0)) and bb[2] == pytest.approx((0.0, fb3.BASE_HUB_Z))
    contact = [math.hypot(v[0], v[1]) for v in base.v if abs(v[2]) < 1e-12]
    assert min(contact) > 12.5 and max(contact) < 15.0 - 0.29                          # on its bearing ring
    # the stem: slim, 1 mm into the base hub and into the tray's floor
    sb = bounds(stem)
    assert abs(sb[2][0] - (fb3.BASE_HUB_Z - fb3.SINK)) < 1e-9 and abs(sb[2][1] - (49.8 + fb3.SINK)) < 1e-9
    mid = [(v[2], math.hypot(v[0], v[1])) for v in stem.v if 4.47 < v[2] < 47.33]     # rings where it starts / stops
    assert max(abs(r - fb3.STEM_R) for z, r in mid) < 1e-9 and 2.0 * fb3.STEM_R < 2.5
    assert min(z for z, r in mid) < 5.0 and max(z for z, r in mid) > 46.5
    # the tray: floor top at 50 (2 cm under the rim), 2 mm sheet, outside 40 cm at the bead
    tb = bounds(tray)
    assert tb[2][0] == pytest.approx(49.8) and tb[2][1] == pytest.approx(52.0, abs=1e-6)
    assert max(math.hypot(v[0], v[1]) for v in tray.v) == pytest.approx(20.0, abs=1e-6)
    floor_top = [v for v in tray.v if abs(v[2] - 50.0) < 1e-12]
    rf = max(math.hypot(v[0], v[1]) for v in floor_top)
    assert 18.4 < rf < 18.75                                                          # flat up to the 1 cm inside round


def test_tray_profile():
    prof = fb3.tray_profile()
    assert prof[0] == (0.0, 49.8) and prof[-1] == (0.0, 50.0)
    assert simple_polyline(prof, False)
    assert all(r > 0.0 for r, z in prof[1:-1])
    top = max(z for r, z in prof)
    assert abs(top - fb3.TRAY_H) < 1e-6 and abs(top - 50.0 - fb3.TRAY_LIP) < 1e-6        # a 2 cm lip
    assert abs(max(r for r, z in prof) - fb3.TRAY_R) < 1e-6
    # the sheet: the outer and inner wall 2 mm apart, the wall flared out
    i_top = max(range(len(prof)), key=lambda i: prof[i][1])
    outer, inner = prof[:i_top + 1], prof[i_top:]
    for z in (50.9, 51.1, 51.35):                                                     # the straight wall
        assert abs((r_at(outer, z) - r_at(inner, z)) * math.cos(math.radians(fb3.TRAY_FLARE)) - fb3.TRAY_T) < 1e-6
    assert r_at(outer, 51.35) > r_at(outer, 50.9)
    # the rolled bead: a round of TRAY_BEAD at the rim
    cz, cr = fb3.TRAY_H - fb3.TRAY_BEAD, fb3.TRAY_R - fb3.TRAY_BEAD
    bead = [p for p in prof if abs(math.hypot(p[0] - cr, p[1] - cz) - fb3.TRAY_BEAD) < 1e-9]
    assert len(bead) >= 20


def test_brass_uvs(brass):
    for name, mat, md, tile, sm in brass:
        assert tile == fb3.BRASS_TILE
        # spun: V is constant round every ring (the brushing runs round), U at true scale
        rings = 0
        for f, uv in zip(md.f, md.fuv):
            a, b = md.v[f[0]], md.v[f[1]]                      # a lathe quad's first edge runs round a ring
            r = math.hypot(a[0], a[1])
            if abs(a[2] - b[2]) > 1e-12 or abs(r - math.hypot(b[0], b[1])) > 1e-9 or r < 1.0:
                continue
            rings += 1
            assert uv[0][1] == pytest.approx(uv[1][1], abs=1e-12)
            d = math.hypot(a[0] - b[0], a[1] - b[1])
            chord_arc = 2.0 * r * math.asin(min(1.0, 0.5 * d / r))
            assert abs(uv[1][0] - uv[0][0]) * tile == pytest.approx(chord_arc, rel=1e-6)
        assert rings > 0.5 * len(md.f)


def test_lathe_seam_at_the_back():
    md = fb3._lathe_md([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)], 8, 5.0, -2.0, tile=10.0)
    check_mesh(md)
    assert own_uv(md)
    ring = [v for v in md.v if abs(v[2]) < 1e-12 and math.hypot(v[0] - 5.0, v[1] + 2.0) > 0.5]
    assert ring[0] == pytest.approx((5.0, -1.0, 0.0))                                  # the first (seam) vertex at +Y
    us = sorted({round(t[0], 9) for uv in md.fuv for t in uv})
    assert us[0] == 0.0 and us[-1] == pytest.approx(2.0 * math.pi / 10.0)


# ---------------------------------------------------------------- wrappers
class _Node(object):
    def __init__(self, name):
        self.name = name


def test_build_wrappers(monkeypatch):
    monkeypatch.setattr(furn_living, "_build", lambda md, name, uv_tile=None: _Node(name))
    monkeypatch.setattr(kit, "soften", lambda node, *a, **k: node)
    monkeypatch.setattr(kit, "group", lambda name, nodes: (name, list(nodes)))
    monkeypatch.setattr(kit, "place", lambda d, *a, **k: d)
    start = len(kit.PARTS)
    try:
        name, nodes = fb3.build_onyx_tables()
        assert name == "OnyxTables" and len(nodes) == 8
        reg = kit.PARTS[start:]
        assert [r[1] for r in reg] == ["onyx"] + ["bronze"] * 3 + ["onyx"] + ["bronze"] * 3
        assert all(r[2] is None and r[3] is None for r in reg)                          # own UVs, no box map
        mark = len(kit.PARTS)
        name, nodes = fb3.build_walnut_side_table()
        assert name == "WalnutSideTable" and [n.name for n in nodes] == [p[0] for p in fb3.walnut_side_table_parts()]
        assert [r[1:] for r in kit.PARTS[mark:]] == [("wood_dark", None, None)] * 3
        mark = len(kit.PARTS)
        name, nodes = fb3.build_brass_tray_table()
        assert name == "BrassTrayTable" and len(nodes) == 3
        assert [r[1:] for r in kit.PARTS[mark:]] == [("metal_brass", None, None)] * 3
        name, groups = fb3.preview()
        assert name == "Bench3Tables" and [g[0] for g in groups] == ["OnyxTables", "WalnutSideTable", "BrassTrayTable"]
        assert all(mat in ALLOWED and mat in kit.MAT_KEYS for _n, mat, _t, _m in kit.PARTS[start:])
    finally:
        del kit.PARTS[start:]
