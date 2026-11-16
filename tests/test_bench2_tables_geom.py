"""Off-Max geometry tests for tools/apartment/furn_bench2_tables.py (the organic Nero Marquina
coffee table and its dressing for the benchmark-2 living room).

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
    import furn_bench2_tables as fbt  # noqa: E402
finally:
    if _prev is None:
        sys.modules.pop("pymxs", None)
    else:
        sys.modules["pymxs"] = _prev

ALLOWED = {"nero_marquina", "bronze", "microcement", "paper", "linen", "bedding", "glass_solid", "stem",
           "metal_brass"}
SEEDS = (0, 1, 2, 3)


# ------------------------------------------------------------------ helpers
def bounds(mds):
    if not isinstance(mds, (list, tuple)):
        mds = [mds]
    vs = [v for md in mds for v in md.v]
    return [(min(v[k] for v in vs), max(v[k] for v in vs)) for k in range(3)]


def check_mesh(md, closed=True):
    """Non-empty, finite, valid faces; closed meshes: every directed edge paired with its
    reverse exactly once and a positive enclosed volume (consistently outward faces)."""
    assert md.v and md.f
    assert all(math.isfinite(c) for v in md.v for c in v)
    nv = len(md.v)
    for f in md.f:
        assert len(f) >= 3 and len(set(f)) == len(f) and all(0 <= i < nv for i in f)
    if not closed:
        return None
    count = {}
    for f in md.f:
        for i in range(len(f)):
            e = (f[i], f[(i + 1) % len(f)])
            count[e] = count.get(e, 0) + 1
    assert all(c == 1 for c in count.values()), "edge used twice in one direction"
    assert all((b, a) in count for (a, b) in count), "open edge"
    vol = fbt._volume(md)
    assert vol > 0.0, "faces point inwards"
    return vol


def check_parts(parts):
    assert parts
    for name, mat, md, tile, smooth in parts:
        assert mat in kit.MAT_KEYS and mat in ALLOWED, (name, mat)
        assert tile > 0 and smooth in (0, 1, 2)
        check_mesh(md)


def own_uv(md):
    return len(md.fuv) == len(md.f) and all(u is not None and len(u) >= 3 for u in md.fuv)


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


def split_at_top(prof):
    i = max(range(len(prof)), key=lambda k: prof[k][1])
    return prof[:i + 1], prof[i:]


def r_at(chain, z):
    for (r0, z0), (r1, z1) in zip(chain, chain[1:]):
        if min(z0, z1) <= z <= max(z0, z1) and z0 != z1:
            return r0 + (r1 - r0) * (z - z0) / (z1 - z0)
    raise AssertionError("no crossing at z=%s" % z)


def chain_dist(p, chain):
    return min(fbt._seg_dist(p[0], p[1], a[0], a[1], b[0], b[1]) for a, b in zip(chain, chain[1:]))


def hull2(pts):
    pts = sorted(set((round(p[0], 9), round(p[1], 9)) for p in pts))
    if len(pts) < 3:
        return pts

    def cr(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cr(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cr(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def hull_margin(h, c):
    """Signed distance of c inside the counter-clockwise convex polygon h (> 0 inside)."""
    best = float("inf")
    for i in range(len(h)):
        a, b = h[i], h[(i + 1) % len(h)]
        ex, ey = b[0] - a[0], b[1] - a[1]
        best = min(best, (ex * (c[1] - a[1]) - ey * (c[0] - a[0])) / math.hypot(ex, ey))
    return best


def polys_apart(p, q):
    """Distance between two convex polygons (0 when they overlap)."""
    for poly in (p, q):
        for i in range(len(poly)):
            a, b = poly[i], poly[(i + 1) % len(poly)]
            nx, ny = b[1] - a[1], a[0] - b[0]
            pa = [nx * v[0] + ny * v[1] for v in p]
            qa = [nx * v[0] + ny * v[1] for v in q]
            if max(pa) < min(qa) or max(qa) < min(pa):
                break
        else:
            continue
        break
    else:
        return 0.0
    best = float("inf")
    for s, t in ((p, q), (q, p)):
        for v in s:
            for i in range(len(t)):
                a, b = t[i], t[(i + 1) % len(t)]
                best = min(best, fbt._seg_dist(v[0], v[1], a[0], a[1], b[0], b[1]))
    return best


def segments_cross(p1, p2, q1, q2):
    def o(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return (o(q1, q2, p1) * o(q1, q2, p2) < -1e-12) and (o(p1, p2, q1) * o(p1, p2, q2) < -1e-12)


# ------------------------------------------------------------------ fixtures
@pytest.fixture(scope="module")
def table():
    return fbt.coffee_table_parts(0)


@pytest.fixture(scope="module")
def dressings():
    return {s: fbt.table_dressing_parts(s) for s in SEEDS}


# ------------------------------------------------------------------ material keys
def test_material_keys_declared():
    for key in ("nero_marquina", "bronze", "microcement"):
        assert key in kit.MAT_KEYS
    for key in ALLOWED:
        assert key in kit.MAT_KEYS


# ------------------------------------------------------------------ pebble outline
@pytest.mark.parametrize("seed", SEEDS)
def test_pebble_outline(seed):
    ol = fbt.pebble_outline(seed)
    n = len(ol)
    assert n == 192
    xs, ys = [p[0] for p in ol], [p[1] for p in ol]
    assert abs(min(xs) + 75.0) < 1e-9 and abs(max(xs) - 75.0) < 1e-9
    assert abs(min(ys) + 37.5) < 1e-9 and abs(max(ys) - 37.5) < 1e-9
    area = fbt._area2(ol)
    assert 0.76 < area / (150.0 * 75.0) < 0.88                                      # counter-clockwise pebble
    turns = fbt._turns(ol)
    assert max(abs(t) for t in turns) < math.radians(6.0)                           # smooth: no kinks
    radii = fbt.curvature_radii(ol)
    assert min(r for r in radii if r > 0.0) > 12.0                                  # no tight corners
    assert all(abs(r) > 60.0 for r in radii if r < 0.0)                             # only gentle hollows
    # not an ellipse: well off the ellipse of its own bounding box
    dev = max(math.hypot(x - 75.0 * math.cos(math.atan2(y / 37.5, x / 75.0)),
                         y - 37.5 * math.sin(math.atan2(y / 37.5, x / 75.0))) for x, y in ol)
    assert dev > 4.0
    # asymmetric left-right and front-back
    assert max(fbt.boundary_distance(ol, -x, y) for x, y in ol[::3]) > 3.0
    assert max(fbt.boundary_distance(ol, x, -y) for x, y in ol[::3]) > 3.0
    # broad left end, narrower right end
    left = [y for x, y in ol if x < -55.0]
    right = [y for x, y in ol if x > 55.0]
    assert max(left) - min(left) > max(right) - min(right) + 5.0
    # simple polygon, star-shaped about its centroid (the cap fans need it)
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            assert not segments_cross(ol[i], ol[(i + 1) % n], ol[j], ol[(j + 1) % n])
    cx, cy = fbt._centroid2(ol)
    ang = [math.atan2(y - cy, x - cx) for x, y in ol]
    steps = [((ang[(i + 1) % n] - ang[i] + math.pi) % (2.0 * math.pi)) - math.pi for i in range(n)]
    assert all(s > 0.0 for s in steps) and abs(sum(steps) - 2.0 * math.pi) < 1e-9


def test_pebble_outline_other_size_and_seeds_differ():
    ol = fbt.pebble_outline(0, 120.0, 60.0)
    xs, ys = [p[0] for p in ol], [p[1] for p in ol]
    assert abs(max(xs) - min(xs) - 120.0) < 1e-9 and abs(max(ys) - min(ys) - 60.0) < 1e-9
    assert fbt.pebble_outline(0) == fbt.pebble_outline(0)
    assert fbt.pebble_outline(0) != fbt.pebble_outline(1)


# ------------------------------------------------------------------ slab
def test_slab_profile_rounds():
    prof = fbt.slab_profile(32.0, 36.0)
    assert prof[0] == (1.0 + fbt.SUPPORT, 32.0) and prof[-1] == (1.0 + fbt.SUPPORT, 36.0)
    for (d, z) in prof:
        assert 0.0 - 1e-12 <= d <= 1.0 + fbt.SUPPORT + 1e-12 and 32.0 <= z <= 36.0
    rounds = [(d, z) for d, z in prof if 1e-9 < d < 1.0 - 1e-9]
    assert len(rounds) >= 14
    for d, z in rounds:                                                              # 1 cm radius rounds
        cz = 35.0 if z > 34.0 else 33.0
        assert abs(math.hypot(d - 1.0, z - cz) - 1.0) < 1e-9
    band = [z for d, z in prof if abs(d) < 1e-9]
    assert abs(min(band) - 33.0) < 1e-9 and abs(max(band) - 35.0) < 1e-9


def test_slab_mesh(table):
    check_parts(table)
    top = part(table, "PebbleTable_Top")
    (x0, x1), (y0, y1), (z0, z1) = bounds(top)
    assert abs(x0 + 75.0) < 1e-9 and abs(x1 - 75.0) < 1e-9
    assert abs(y0 + 37.5) < 1e-9 and abs(y1 - 37.5) < 1e-9
    assert abs(z0 - 32.0) < 1e-9 and abs(z1 - 36.0) < 1e-9                           # 4 cm slab, top at 36
    ol = fbt.pebble_outline(0)
    # cap fans: every top / underside face flat and facing straight up / down
    for f in top.f:
        zs = [top.v[i][2] for i in f]
        n = face_normal(top, f)
        if all(abs(z - 36.0) < 1e-9 for z in zs):
            assert n[2] > 0.0 and abs(n[0]) + abs(n[1]) < 1e-9 * max(1.0, n[2])
        if all(abs(z - 32.0) < 1e-9 for z in zs):
            assert n[2] < 0.0
    # the rounded edge: nothing at the sharp corner (outline, z = 36)
    for x, y in ol[::12]:
        near = min(math.sqrt((v[0] - x) ** 2 + (v[1] - y) ** 2 + (v[2] - 36.0) ** 2) for v in top.v)
        assert near > 0.35
    # the flat top stops about 1 cm in from the edge
    flat = [v for v in top.v if abs(v[2] - 36.0) < 1e-9]
    assert min(fbt.boundary_distance(ol, v[0], v[1]) for v in flat[::7]) > 0.99


def test_slab_uvs(table):
    top = part(table, "PebbleTable_Top")
    assert own_uv(top)
    # the top and underside carry the planar marble projection (100 cm repeat, turned -25 deg)
    us = []
    for f, uv in zip(top.f, top.fuv):
        if all(abs(top.v[i][2] - 36.0) < 1e-9 for i in f):
            for i, (u, v) in zip(f, uv):
                eu, ev = fbt.marble_uv(top.v[i][0], top.v[i][1])
                assert abs(u - eu) < 1e-9 and abs(v - ev) < 1e-9
                us.append(u)
    assert max(us) - min(us) > 1.3                                                   # ~1.5 repeats across
    # the map's main veins (60 deg off U) cross the top at ~35 deg to its length
    a = fbt.marble_uv(math.cos(math.radians(35.0)), math.sin(math.radians(35.0)))
    b = fbt.marble_uv(0.0, 0.0)
    assert abs(math.degrees(math.atan2(a[1] - b[1], a[0] - b[0])) - 60.0) < 1e-6
    # the edge band: true scale across it, continuous over the top arris
    ol = fbt.pebble_outline(0)
    N, prof = len(ol), fbt.slab_profile(32.0, 36.0)
    K = len(prof)
    seen = {}
    for f, uv in zip(top.f, top.fuv):
        for i, t in zip(f, uv):
            if i < N * K:
                seen.setdefault(i, set()).add((round(t[0], 9), round(t[1], 9)))
    ktop = K - 2                                                                     # where the top round starts
    for i in range(0, N, 16):
        assert len(seen[ktop * N + i]) == 1                                          # no UV seam on the arris
    for k in range(1, K - 2):
        for i in range(0, N, 24):
            ua = list(seen[k * N + i])[0] if len(seen[k * N + i]) == 1 else None
            ub = list(seen[(k + 1) * N + i])[0] if len(seen[(k + 1) * N + i]) == 1 else None
            if ua is None or ub is None:
                continue
            seg = math.hypot(prof[k + 1][0] - prof[k][0], prof[k + 1][1] - prof[k][1])
            assert abs(math.hypot(ub[0] - ua[0], ub[1] - ua[1]) * 100.0 - seg) < 1e-6


# ------------------------------------------------------------------ pedestals
@pytest.mark.parametrize("seed,n_ped", [(0, 3), (1, 3), (2, 3), (3, 3), (0, 2), (1, 2)])
def test_pedestals(seed, n_ped):
    parts = fbt.coffee_table_parts(seed, n_pedestals=n_ped)
    check_parts(parts)
    peds = [p for p in parts if p[0].startswith("PebbleTable_Pedestal")]
    assert len(peds) == n_ped and {p[1] for p in peds} == {"bronze"}
    ol = fbt.pebble_outline(seed)
    lay = fbt.pedestal_layout(ol, seed, n_ped)
    cols = [p["column"] for p in lay]
    for (name, mat, md, tile, sm), p in zip(peds, lay):
        assert own_uv(md) and sm == 0
        (bx0, bx1), (by0, by1), (bz0, bz1) = bounds(md)
        assert abs(bz0) < 1e-9 and abs(bz1 - 32.1) < 1e-9                            # floor to 1 mm into the slab
        assert 20.0 <= 2.0 * p["a"] <= 30.0 and 20.0 <= 2.0 * p["b"] <= 30.0         # 20-30 cm across
        col = p["column"]
        clear = min(fbt.boundary_distance(ol, x, y) for x, y in col)
        assert abs(clear - fbt.PED_CLEAR) < 0.005                                    # column 2 cm inside the edge
        assert all(fbt.point_in_polygon(ol, x, y) for x, y in col)
        # the recessed plinth: what touches the floor is 1 cm in from the column face
        foot = [v for v in md.v if abs(v[2]) < 1e-9]
        assert foot and all(fbt.point_in_polygon(col, v[0], v[1]) for v in foot)
        assert min(fbt.boundary_distance(col, v[0], v[1]) for v in foot[::5]) > 0.99
        # soft column edges: nothing at the column's sharp top or bottom corners
        for x, y in col[::9]:
            for zc in (1.0, 32.1):
                assert min(math.sqrt((v[0] - x) ** 2 + (v[1] - y) ** 2 + (v[2] - zc) ** 2) for v in md.v) > 0.12
    for i in range(n_ped):
        for j in range(i + 1, n_ped):
            gap = min(math.hypot(a[0] - b[0], a[1] - b[1]) for a in cols[i][::2] for b in cols[j][::2])
            assert gap > 8.0
    # it stands: the slab's centroid well inside the pedestals' support hull
    h = hull2([q for c in cols for q in c])
    assert hull_margin(h, fbt._centroid2(ol)) > 8.0


def test_pedestal_profile_and_layout_errors():
    prof = fbt.pedestal_profile(32.1)
    assert prof[0][1] == 0.0 and abs(prof[-1][1] - 32.1) < 1e-12
    assert min(d for d, z in prof) > -1e-12                                          # nothing proud of the column face
    assert all(d >= 1.0 - 1e-9 for d, z in prof if z < 0.9)                          # plinth 1 cm in, 1 cm tall
    with pytest.raises(ValueError):
        fbt.pedestal_layout(fbt.pebble_outline(0), 0, 4)


# ------------------------------------------------------------------ whole table
def test_table_totals(table):
    (x0, x1), (y0, y1), (z0, z1) = bounds([p[2] for p in table])
    assert abs(x1 - x0 - 150.0) < 1e-9 and abs(y1 - y0 - 75.0) < 1e-9
    assert abs(z0) < 1e-9 and abs(z1 - 36.0) < 1e-9                                   # 36 cm overall
    assert [p[0] for p in table] == ["PebbleTable_Top"] + ["PebbleTable_Pedestal%d" % k for k in range(3)]
    assert {p[1] for p in table} == {"nero_marquina", "bronze"}
    assert all(own_uv(p[2]) for p in table)


def test_table_other_size():
    parts = fbt.coffee_table_parts(1, length=140.0, width=70.0, height=38.0, n_pedestals=2, vein_deg=10.0)
    check_parts(parts)
    (x0, x1), (y0, y1), (z0, z1) = bounds([p[2] for p in parts])
    assert abs(x1 - x0 - 140.0) < 1e-9 and abs(y1 - y0 - 70.0) < 1e-9 and abs(z1 - 38.0) < 1e-9
    with pytest.raises(ValueError):
        fbt.coffee_table_parts(0, thick=2.0)


# ------------------------------------------------------------------ books
@pytest.mark.parametrize("seed", (0, 1))
def test_book_pair(seed):
    parts, info = fbt.book_pair_layout(seed)
    check_parts(parts)
    assert len(parts) == 4 and all(own_uv(p[2]) for p in parts)                      # box UVs in each book's frame
    cases = [p for p in parts if p[0].endswith("_Case")]
    pages = [p for p in parts if p[0].endswith("_Pages")]
    assert [p[1] for p in cases] == ["linen", "paper"] and {p[1] for p in pages} == {"bedding"}
    b0, b1 = bounds(cases[0][2]), bounds(cases[1][2])
    assert abs(b0[2][0]) < 1e-9 and abs(b1[2][0] - b0[2][1]) < 1e-9                  # resting on each other
    assert abs(b1[2][1] - info["top_z"]) < 1e-9 and 5.2 < info["top_z"] < 6.3
    for H, W, T, cover, deg, dx, dy in info["books"]:
        assert 80.0 < deg < 100.0                                                    # spines to the front
    (x0, x1), (y0, y1), _z = bounds([p[2] for p in parts])
    assert 30.0 < x1 - x0 < 38.0 and 24.0 < y1 - y0 < 33.0


# ------------------------------------------------------------------ stone bowl
@pytest.mark.parametrize("seed", (0, 3))
def test_stone_bowl(seed):
    parts = fbt.stone_bowl_parts(seed)
    check_parts(parts)
    md = parts[0][2]
    (x0, x1), (y0, y1), (z0, z1) = bounds(md)
    assert abs(z0) < 1e-9 and 5.5 < z1 < 5.7
    assert 14.8 < x1 - x0 < 15.4 and 14.8 < y1 - y0 < 15.4
    foot = [math.hypot(v[0], v[1]) for v in md.v if abs(v[2]) < 1e-9]
    assert foot and 2.9 < min(foot) and max(foot) < 4.0                              # stands on its foot ring
    # per meridian (48 of them): the silhouette radius and the rim height
    rmax, ztop = {}, {}
    for v in md.v:
        r = math.hypot(v[0], v[1])
        if r < 1e-6:
            continue
        k = int(round(math.atan2(v[1], v[0]) / (2.0 * math.pi / 48.0))) % 48
        rmax[k] = max(rmax.get(k, 0.0), r)
        ztop[k] = max(ztop.get(k, 0.0), v[2])
    assert len(rmax) == 48
    assert 0.08 < max(rmax.values()) - min(rmax.values()) < 0.3                      # a little out of round
    assert 0.05 < max(ztop.values()) - min(ztop.values()) < 0.2                      # rim not quite level


def test_bowl_walls():
    outer, inner = split_at_top(fbt.bowl_profile())
    for r, z in inner:
        if 1.6 < z < 5.0:
            assert 0.6 < chain_dist((r, z), outer) < 1.3                             # 6-13 mm, thickening downwards
    floor = min(z for r, z in inner if r < 2.0)
    assert floor - 0.25 > 0.85                                                       # 9 mm+ base over the recess


# ------------------------------------------------------------------ bottle vase and branch
def test_bottle_walls():
    prof = fbt.bottle_profile()
    outer, inner = split_at_top(prof)
    for r, z in inner:
        if 1.8 < z < 16.0:
            assert 0.28 <= chain_dist((r, z), outer) <= 0.32                          # 3 mm glass
    assert min(r for r, z in inner if 13.2 < z < 16.9) >= fbt.BOTTLE_NECK_R - 1e-9
    under = max(z for r, z in outer if r < 1.0)
    floor = min(z for r, z in inner if r < 1.0)
    assert floor - under > 0.6                                                       # thick punted base
    assert abs(max(z for r, z in prof) - fbt.BOTTLE_LIP) < 1e-9
    assert abs(max(r for r, z in prof) - fbt.BOTTLE_R) < 1e-9


@pytest.mark.parametrize("seed", (0, 1, 2, 5))
def test_branch_in_the_bottle(seed):
    parts = fbt.bottle_vase_parts(seed)
    check_parts(parts)
    assert [p[1] for p in parts] == ["glass_solid", "stem"]
    gb = bounds(part(parts, "BottleVase_Glass"))
    assert abs(gb[2][0]) < 1e-9 and abs(gb[2][1] - fbt.BOTTLE_LIP) < 1e-9
    assert abs(gb[0][1] - fbt.BOTTLE_R) < 1e-6
    _outer, inner = split_at_top(fbt.bottle_profile())
    paths = fbt.branch_paths(seed)
    assert 5 <= len(paths) <= 9
    main, rad = paths[0]
    assert abs(rad[0] - 0.42) < 1e-9 and len(main) == len(rad)
    assert all(0.03 <= r <= 0.42 + 1e-9 for _p, rr in paths for r in rr)
    # clear of the glass all the way up through the neck (straight tube between path points)
    for a, b, r in zip(main, main[1:], rad):
        for k in range(11):
            p = tuple(a[q] + (b[q] - a[q]) * k / 10.0 for q in range(3))
            if 2.0 <= p[2] <= fbt.BOTTLE_LIP + 0.3:
                assert math.hypot(p[0], p[1]) + r < r_at(inner, min(p[2], fbt.BOTTLE_LIP - 1e-6)) - 0.1
    # the cut end stands on the inside of the base (0.5-1.5 mm above it, not floating)
    branch = part(parts, "BottleVase_Branch")
    zmin = min(v[2] for v in branch.v)
    assert fbt.BOTTLE_FLOOR + 0.0 < zmin < fbt.BOTTLE_FLOOR + 0.15
    low = [v for v in branch.v if v[2] < 2.0]
    assert all(math.hypot(v[0], v[1]) < 2.5 for v in low)
    # tall, leaning back-right, twigs leaving the stem above the lip
    top = max(main, key=lambda p: p[2])
    assert 48.0 < top[2] < 70.0
    tip = main[-1]
    assert tip[0] > 2.0 and tip[1] > 2.0 and math.hypot(tip[0], tip[1]) > 5.0
    for path, rr in paths[1:]:
        assert path[0][2] > 25.0 and rr[0] < 0.3
        i = min(range(len(main)), key=lambda k: sum((main[k][q] - path[0][q]) ** 2 for q in range(3)))
        if rr[0] > 0.1:                                                              # twigs start inside the stem
            assert rr[0] < rad[i] and math.sqrt(sum((main[i][q] - path[0][q]) ** 2 for q in range(3))) < 1e-9


# ------------------------------------------------------------------ ribbon sculpture
@pytest.mark.parametrize("seed", (0, 1, 2))
def test_ribbon(seed):
    parts = fbt.ribbon_parts(seed)
    check_parts(parts)
    md = parts[0][2]
    assert parts[0][1] == "metal_brass" and own_uv(md)
    (x0, x1), (y0, y1), (z0, z1) = bounds(md)
    assert 24.5 < x1 - x0 < 25.5 and y1 - y0 < 14.0 and 22.0 < z1 < 28.0             # about 25 across
    assert abs(z0) < 1e-6                                                            # standing on z = 0
    contact = [v for v in md.v if v[2] < 1e-6]
    cx = [v[0] for v in contact]
    cy = [v[1] for v in contact]
    assert max(cx) - min(cx) > 5.5 and max(cy) - min(cy) > 3.4                       # on its flat bottom run
    assert max(abs(c) for c in cx) < 5.0
    _md, info = fbt.ribbon_md(seed)
    cl, S = info["centreline"], info["length"]
    gx = sum(p[0] for p in cl) / len(cl)
    gy = sum(p[1] for p in cl) / len(cl)
    assert abs(gx) < 0.5 * (max(cx) - min(cx)) - 0.5 and abs(gy) < 0.5 * (max(cy) - min(cy)) - 0.3   # it stands
    psi = info["psi"]
    assert psi[0] == 0.0 and abs(psi[-1] - math.pi) < 1e-9                            # a half twist round the loop
    assert all(b >= a - 1e-12 for a, b in zip(psi, psi[1:]))
    sec = info["section"]
    h = len(sec) // 2
    assert all(abs(sec[j + h][0] + sec[j][0]) < 1e-12 and abs(sec[j + h][1] + sec[j][1]) < 1e-12 for j in range(h))
    # the band never runs into itself
    n = len(cl)
    for i in range(0, n, 4):
        for j in range(0, n, 4):
            ds = abs(i - j) * S / n
            if min(ds, S - ds) > 12.0:
                assert math.sqrt(sum((cl[i][q] - cl[j][q]) ** 2 for q in range(3))) > fbt.RIBBON_BAND + 1.0
    with pytest.raises(ValueError):
        fbt.ribbon_parts(0, mat="glass")
    assert fbt.ribbon_parts(0, mat="bronze")[0][1] == "bronze"


# ------------------------------------------------------------------ the dressing on the table
def test_dressing_fits_the_table(dressings):
    for s, parts in dressings.items():
        check_parts(parts)
        names = [p[0] for p in parts]
        assert names == ["BookPair_Book0_Case", "BookPair_Book0_Pages", "BookPair_Book1_Case", "BookPair_Book1_Pages",
                         "StoneBowl", "RibbonSculpture", "BottleVase_Glass", "BottleVase_Branch"]
        _parts, info = fbt.book_pair_layout(s)
        books = [p[2] for p in parts[:4]]
        bowl, ribbon = part(parts, "StoneBowl"), part(parts, "RibbonSculpture")
        glass, branch = part(parts, "BottleVase_Glass"), part(parts, "BottleVase_Branch")
        # everything rests on the top (z = 36), the bowl on the top book
        assert abs(bounds(books)[2][0] - 36.0) < 1e-9 and abs(bounds(ribbon)[2][0] - 36.0) < 1e-6
        assert abs(bounds(glass)[2][0] - 36.0) < 1e-9
        assert abs(bounds(bowl)[2][0] - (36.0 + info["top_z"])) < 1e-9
        # the bowl stands fully on the top book's board, clear of its hinge groove
        x, y, _z, deg = fbt.table_dressing_layout(s)["book_pair"]
        H, W, T, _c, bdeg, dx, dy = info["books"][-1]
        c, sn = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        cb, sb = math.cos(math.radians(bdeg)), math.sin(math.radians(bdeg))
        for v in bowl.v[::3]:
            px, py = v[0] - x, v[1] - y
            px, py = px * c + py * sn - dx, -px * sn + py * c - dy                   # into the pair's frame
            lx, ly = px * cb + py * sb, -px * sb + py * cb                           # into the top book's frame
            assert -0.5 * W + 2.0 < lx < 0.5 * W - 0.3 and abs(ly) < 0.5 * H - 0.3
        # props apart in plan
        hulls = {"books": hull2([v for md in books for v in md.v]), "ribbon": hull2(ribbon.v),
                 "vase": hull2(glass.v)}
        keys = sorted(hulls)
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                assert polys_apart(hulls[keys[i]], hulls[keys[j]]) > 3.0, (s, keys[i], keys[j])
        # the branch clear of the ribbon, the books and the bowl
        bb = bounds(branch)
        for other in (ribbon, bowl, books[2]):
            ob = bounds(other)
            assert any(bb[k][0] > ob[k][1] + 1.0 or ob[k][0] > bb[k][1] + 1.0 for k in range(3))
        # on every table outline (any seed), well inside the edge
        for ts in SEEDS:
            ol = fbt.pebble_outline(ts)
            for key, h in hulls.items():
                ring = list(h)
                ring += [((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5) for a, b in zip(h, h[1:] + h[:1])]
                for px, py in ring:
                    assert fbt.point_in_polygon(ol, px, py), (s, ts, key)
                    assert fbt.boundary_distance(ol, px, py) > 4.0, (s, ts, key)


def test_dressing_deterministic_and_varied(dressings):
    again = fbt.table_dressing_parts(2)
    assert [p[2].v for p in again] == [p[2].v for p in dressings[2]]
    assert part(dressings[0], "BottleVase_Branch").v != part(dressings[1], "BottleVase_Branch").v
    assert part(dressings[0], "RibbonSculpture").v != part(dressings[1], "RibbonSculpture").v
    other = fbt.table_dressing_parts(0, top_z=40.0)
    assert abs(bounds(part(other, "RibbonSculpture"))[2][0] - 40.0) < 1e-6


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
    name, nodes = fbt.build_coffee_table()
    assert name == "PebbleTable" and len(nodes) == 4
    reg = kit.PARTS[start:]
    assert [r[1] for r in reg] == ["nero_marquina"] + ["bronze"] * 3
    assert all(r[2] is None and r[3] is None for r in reg)                          # own UVs, no box map
    mark = len(kit.PARTS)
    name, nodes = fbt.build_table_dressing()
    assert name == "PebbleTableDressing" and len(nodes) == 8
    reg = {r[0].name: r for r in kit.PARTS[mark:]}
    assert reg["RibbonSculpture"][3] is None and reg["BookPair_Book0_Case"][3] is None
    assert reg["StoneBowl"][1:] == ("microcement", fbt.STONE, 4)
    assert reg["BottleVase_Glass"][1:] == ("glass_solid", fbt.GLASS, 4)
    assert reg["BottleVase_Branch"][1:] == ("stem", fbt.BARK, 4)
    for fn, gname, n in ((fbt.build_book_pair, "BookPair", 4), (fbt.build_stone_bowl, "StoneBowl", 1),
                         (fbt.build_bottle_vase, "BottleVase", 2), (fbt.build_ribbon_sculpture, "RibbonSculpture", 1)):
        name, nodes = fn()
        assert name == gname and len(nodes) == n
    name, nodes = fbt.preview()
    assert name == "PebbleTable_Dressed" and [g[0] for g in nodes] == ["PebbleTable", "PebbleTableDressing"]
    assert all(mat in ALLOWED and mat in kit.MAT_KEYS for _n, mat, _t, _m in kit.PARTS[start:])
    del kit.PARTS[start:]
