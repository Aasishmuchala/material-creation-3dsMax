"""Off-Max geometry tests for tools/apartment/furn_bench3_decor.py (benchmark 3: the
hand-tufted wall tapestry, the flowering tree in its brass pot, the slate velvet pouf and
the knitted lounge chair).

pymxs is stubbed while the module is imported (and the previous entry put back), so only
the pure-Python cage generators run; the build_* wrappers are run against a small
recording fake of the pymxs runtime.
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
    import furn_bench3_decor as fb3  # noqa: E402
finally:
    if _prev is None:
        sys.modules.pop("pymxs", None)
    else:
        sys.modules["pymxs"] = _prev

NEW_KEYS = ("tapestry", "blossom_card", "slate_velvet", "knit_stripe")
USED = {"tapestry", "metal_brass", "soil", "stem", "blossom_card", "slate_velvet", "knit_stripe",
        "metal_black"}
TREE_SEEDS = (0, 1, 3, 5)        # three, four, five and five main branches


# ------------------------------------------------------------------ helpers
def bounds(mds):
    if not isinstance(mds, (list, tuple)):
        mds = [mds]
    vs = [v for md in mds for v in md.v]
    return [(min(v[k] for v in vs), max(v[k] for v in vs)) for k in range(3)]


def volume(md):
    vol = 0.0
    for f in md.f:
        p0 = md.v[f[0]]
        for k in range(1, len(f) - 1):
            p1, p2 = md.v[f[k]], md.v[f[k + 1]]
            vol += (p0[0] * (p1[1] * p2[2] - p1[2] * p2[1]) - p0[1] * (p1[0] * p2[2] - p1[2] * p2[0])
                    + p0[2] * (p1[0] * p2[1] - p1[1] * p2[0])) / 6.0
    return vol


def check_mesh(md, closed=True):
    """Non-empty, finite, valid faces with finite UVs; closed meshes: every directed edge
    paired with its reverse exactly once and a positive enclosed volume (outward faces)."""
    assert md.v and md.f
    assert all(math.isfinite(c) for v in md.v for c in v), "NaN / inf vertex"
    nv = len(md.v)
    for f in md.f:
        assert len(f) >= 3 and len(set(f)) == len(f) and all(0 <= i < nv for i in f)
    assert len(md.fuv) == len(md.f)
    for f, uv in zip(md.f, md.fuv):
        if uv is not None:
            assert len(uv) == len(f) and all(math.isfinite(c) for t in uv for c in t)
    if not closed:
        return 0.0
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


def newell(pts):
    n = [0.0, 0.0, 0.0]
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    ln = math.sqrt(sum(c * c for c in n))
    return tuple(c / ln for c in n)


def uv_area(uv):
    return 0.5 * sum(uv[i][0] * uv[(i + 1) % len(uv)][1] - uv[(i + 1) % len(uv)][0] * uv[i][1]
                     for i in range(len(uv)))


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


def seg_dist(p, a, b):
    ab = [b[i] - a[i] for i in range(3)]
    l2 = sum(c * c for c in ab)
    t = 0.0 if l2 < 1e-12 else max(0.0, min(1.0, sum(ab[i] * (p[i] - a[i]) for i in range(3)) / l2))
    return math.dist(p, [a[i] + ab[i] * t for i in range(3)])


def polyline_dist(p, path):
    return min(seg_dist(p, a, b) for a, b in zip(path, path[1:]))


def part(parts, name):
    return [p for p in parts if p[0] == name][0][2]


def check_parts(parts):
    assert parts
    for name, mat, md, tile, smooth in parts:
        assert mat in kit.MAT_KEYS and mat in USED, (name, mat)
        if tile is None:                                  # a whole photo on the cage's 0-1 UVs
            assert mat in ("tapestry", "blossom_card") and smooth == 0, name
            check_mesh(md, closed=False)
            assert all(uv is not None for uv in md.fuv), name
            us = [t[0] for uv in md.fuv for t in uv]
            vs = [t[1] for uv in md.fuv for t in uv]
            assert min(us) >= -1e-9 and max(us) <= 1.0 + 1e-9 and min(vs) >= -1e-9 and max(vs) <= 1.0 + 1e-9
        else:
            assert tile > 0 and smooth in (0, 1), name
            check_mesh(md, closed=(name != "Tapestry_Edge"))


# --------------------------------------------------------------- materials
def test_new_material_keys_are_declared_at_import():
    for key in NEW_KEYS:
        assert key in kit.MAT_KEYS and kit.MAT_KEYS[key]
    used = set()
    for fn in (fb3.tapestry_parts, fb3.flowering_tree_parts, fb3.velvet_pouf_parts, fb3.knit_chair_parts):
        used |= {p[1] for p in fn()}
    assert used == USED and all(k in kit.MAT_KEYS for k in used)


def test_periodic_interpolation_and_fillet_path():
    vals = (57.0, 65.0, 75.0, 65.0, 57.0, 53.0, 35.5, 53.0)
    for k, v in enumerate(vals):
        assert fb3._periodic(vals, math.radians(45.0 * k)) == pytest.approx(v)
        assert fb3._periodic(vals, math.radians(45.0 * k + 360.0)) == pytest.approx(v)
    pts = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    out = fb3._fillet_path(pts, [0.0, 2.0, 3.0, 0.0], (2, 3, 2), (4, 5))
    assert len(out) == 1 + 7 + 9 and out[0] == pts[0] and out[-1] == pytest.approx(pts[-1])
    assert min(math.dist(a, b) for a, b in zip(out, out[1:])) > 1e-3       # no repeated points
    assert math.dist(out[2], (8.0, 0.0)) < 1e-9                             # round 1 starts 2 cm early
    corner = min(math.dist(p, (10.0, 0.0)) for p in out)
    assert corner == pytest.approx(2.0 * (math.sqrt(2.0) - 1.0), abs=0.02)
    with pytest.raises(ValueError):
        fb3._fillet_path([(0, 0), (1, 0), (2, 0)], [0, 1, 0], (1, 1), (1,))


# ================================================================ tapestry
@pytest.fixture(scope="module")
def tapestry():
    return fb3.tapestry_md(300.0, 230.0, 0)


def test_tapestry_is_a_closed_panel_of_the_right_size(tapestry):
    md, tags, lay = tapestry
    vol = check_mesh(md)
    assert len(tags) == len(md.f)
    (x0, x1), (y0, y1), (z0, z1) = bounds(md)
    assert (x0, x1, z0, z1) == pytest.approx((-150.0, 150.0, 0.0, 230.0), abs=1e-9)   # 300 x 230
    assert y1 == pytest.approx(0.0, abs=1e-9) and -3.6 < y0 < -2.8                    # 2.5 cm, front -Y
    assert vol == pytest.approx(300.0 * 230.0 * 2.5, rel=0.03)
    back = [i for f, t in zip(md.f, tags) if t == "edge" for i in f if abs(md.v[i][1]) < 1e-9]
    assert len(back) > 500                                                          # flat back on the wall
    for f, t in zip(md.f, tags):
        if t == "edge" and all(abs(md.v[i][1]) < 1e-9 for i in f):
            assert newell([md.v[i] for i in f])[1] > 0.999                          # facing the wall


def test_tapestry_outline_is_soft_and_irregular(tapestry):
    md, tags, lay = tapestry
    out = fb3.tapestry_outline(lay)
    assert len(out) == 2 * (lay["p"] + lay["q"])
    xs, zs = [p[0] for p in out], [p[1] for p in out]
    assert (min(xs), max(xs), min(zs), max(zs)) == pytest.approx((-150.0, 150.0, 0.0, 230.0), abs=1e-9)
    corners = min(math.dist(p, (cx, cz)) for p in out for cx in (-150.0, 150.0) for cz in (0.0, 230.0))
    assert corners > 1.2                                                            # rounded corners
    bottom = [p[1] for p in out if abs(p[0]) < 120.0 and p[1] < 20.0]
    left = [p[0] for p in out if -150.0 <= p[0] < -130.0 and 30.0 < p[1] < 200.0]
    assert max(bottom) - min(bottom) > 0.4 and max(left) - min(left) > 0.4         # gently wavy edges
    assert max(bottom) - min(bottom) < 4.0 and max(left) - min(left) < 4.0
    area = 0.5 * sum(out[i][0] * out[(i + 1) % len(out)][1] - out[(i + 1) % len(out)][0] * out[i][1]
                     for i in range(len(out)))
    assert 0.97 * 300.0 * 230.0 < area < 300.0 * 230.0                              # counter-clockwise
    other = fb3.tapestry_outline(fb3.tapestry_layout(300.0, 230.0, 1))
    assert max(math.dist(a, b) for a, b in zip(out, other)) > 0.3                   # seeded


def test_tapestry_rolled_edge_and_undulating_face(tapestry):
    md, tags, lay = tapestry
    R, T = fb3.TAP_ROLL, fb3.TAP_T
    st = fb3.tapestry_section(R)
    assert st[0] == pytest.approx((R, 0.0)) and st[4] == pytest.approx((0.0, R))   # back, outermost
    assert st[fb3.TAP_CREST] == pytest.approx((R, 2.0 * R))                         # the crest, 3 mm proud
    assert st[-1] == pytest.approx((R + fb3.TAP_BLEND, T)) and 2.0 * R - T == pytest.approx(0.3)
    assert all(b[1] >= a[1] - 1e-12 for a, b in zip(st[:fb3.TAP_CREST + 1], st[1:fb3.TAP_CREST + 1]))
    # the face proper: depth T plus a few mm of relief
    inner = {i for f, t in zip(md.f, tags) if t == "face" and len(f) == 4 for i in f
             if 6.0 < md.v[i][2] < 224.0 and abs(md.v[i][0]) < 144.0}
    depth = [-md.v[i][1] for i in inner]
    assert len(depth) > 3000
    assert 0.15 < max(depth) - min(depth) < 1.2                                     # undulating a few mm
    assert sum(depth) / len(depth) == pytest.approx(T, abs=0.1)
    assert max(-v[1] for v in md.v) > 2.0 * R * 0.9                                 # the roll stands proud
    rel = [fb3.tapestry_relief(lay, x, 229.0) for x in range(-140, 141, 7)]
    mid = [fb3.tapestry_relief(lay, x, 100.0) for x in range(-140, 141, 7)]
    assert max(map(abs, rel)) < max(map(abs, mid))                                  # calm under the batten


def test_tapestry_photo_covers_the_face_once_unmirrored(tapestry):
    md, tags, lay = tapestry
    face = [(f, uv) for f, uv, t in zip(md.f, md.fuv, tags) if t == "face"]
    assert all(uv is not None for f, uv in face)
    us = [c[0] for f, uv in face for c in uv]
    vs = [c[1] for f, uv in face for c in uv]
    assert (min(us), max(us), min(vs), max(vs)) == pytest.approx((0.0, 1.0, 0.0, 1.0), abs=1e-12)
    xs = [md.v[i][0] for f, uv in face for i in f]
    zs = [md.v[i][2] for f, uv in face for i in f]
    x0, x1, z0, z1 = min(xs), max(xs), min(zs), max(zs)
    for f, uv in face:                                      # u left -> right, v bottom -> top (planar)
        for i, t in zip(f, uv):
            assert t == pytest.approx(((md.v[i][0] - x0) / (x1 - x0), (md.v[i][2] - z0) / (z1 - z0)), abs=1e-12)
    assert all(uv_area(uv) > 0.0 for f, uv in face)                                 # read from the front
    for f, uv in face:
        if len(f) == 4:
            assert newell([md.v[i] for i in f])[1] < -0.5                           # the face looks at -Y
    total = sum(uv_area(uv) for f, uv in face)
    assert 0.97 < total < 1.0                                                       # once over the whole face
    for f, uv, t in zip(md.f, md.fuv, tags):                # the roll and back: the same, clamped
        if t == "edge":
            for i, c in zip(f, uv):
                want = (min(1.0, max(0.0, (md.v[i][0] - x0) / (x1 - x0))), min(1.0, max(0.0, (md.v[i][2] - z0) / (z1 - z0))))
                assert c == pytest.approx(want, abs=1e-12)


def test_tapestry_parts_and_other_sizes():
    parts = fb3.tapestry_parts()
    check_parts(parts)
    faces = [p for p in parts if p[0] == "Tapestry_Face"]
    assert len(faces) >= 2 and all(len(p[2].f) <= fb3.NODE_FACES for p in faces)
    assert [p[1] for p in parts] == ["tapestry"] * (len(faces) + 1)
    md, tags, _lay = fb3.tapestry_md()
    assert sum(len(p[2].f) for p in faces) == tags.count("face")
    assert len(part(parts, "Tapestry_Edge").f) == tags.count("edge")
    for w, h in ((200.0, 150.0), (120.0, 90.0)):
        md2, tags2, _l = fb3.tapestry_md(w, h, 3)
        check_mesh(md2)
        (x0, x1), (y0, y1), (z0, z1) = bounds(md2)
        assert (x0, x1, z0, z1) == pytest.approx((-w / 2.0, w / 2.0, 0.0, h), abs=1e-9)
    with pytest.raises(ValueError):
        fb3.tapestry_md(30.0, 30.0)
    a, b = fb3.tapestry_md(300.0, 230.0, 2)[0], fb3.tapestry_md(300.0, 230.0, 2)[0]
    assert a.v == b.v and a.v != fb3.tapestry_md(300.0, 230.0, 4)[0].v              # deterministic, seeded


# ==================================================================== pouf
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_pouf_is_a_plump_welted_drum(seed):
    parts = fb3.velvet_pouf_parts(seed)
    check_parts(parts)
    body, welt = part(parts, "VelvetPouf_Body"), part(parts, "VelvetPouf_Welt")
    (x0, x1), (y0, y1), (z0, z1) = bounds(body)
    assert z0 == pytest.approx(0.0, abs=1e-12) and z1 == pytest.approx(42.0, abs=0.1)   # 42 tall
    radius = [math.hypot(v[0], v[1]) for v in body.v]
    assert 24.6 < max(radius) < 25.4                                                # about 50 across
    assert check_mesh(body) == pytest.approx(math.pi * 24.6 ** 2 * 40.5, rel=0.06)
    lay = fb3.pouf_layout(seed=seed)
    for deg in (0.0, 77.0, 190.0, 300.0):
        prof = fb3.pouf_profile(lay, math.radians(deg))
        assert prof[0][1] == 0.0 and prof[3][1] == pytest.approx(lay["rb"])         # rounded bottom edge
        side = prof[3:12]
        mid = max(r for r, z in side)
        assert mid - side[0][0] > 0.8 and mid - side[-1][0] > 0.8                   # bulging sides
        assert prof[-1][1] == pytest.approx(lay["seam_z"], abs=0.4)                 # the welt seam
    flat = [v for v in body.v if v[2] < 1e-9]
    assert len(flat) > 200                                                          # a flat bottom panel
    top = max(body.v, key=lambda v: v[2])
    assert math.hypot(top[0], top[1]) < 3.0 and top[2] - lay["seam_z"] > 2.0        # a domed top
    assert components(welt) == 1 and welt.v and check_mesh(welt) > 80.0
    wr = [math.hypot(v[0], v[1]) for v in welt.v]
    seam_r = [fb3.pouf_profile(lay, math.radians(d))[-1][0] for d in range(0, 360, 15)]
    assert max(wr) > max(seam_r) + 0.5                                              # the welt stands proud
    assert bounds(welt)[2][1] < z1 - 0.8                                            # under the dome's peak
    assert max(radius) - min(math.hypot(v[0], v[1]) for v in body.v if abs(v[2] - 21.0) < 2.0) > 0.08


def test_pouf_uvs_and_seed():
    lay = fb3.pouf_layout(seed=0)
    md = fb3.pouf_body_md(lay)
    assert all(uv is not None for uv in md.fuv)
    U = [t[0] for f, uv in zip(md.f, md.fuv) for t in uv]
    assert max(U) == pytest.approx(2.0 * math.pi * 25.0 / fb3.VELVET, rel=0.01)     # wrapped at true scale
    band = [(f, uv) for f, uv in zip(md.f, md.fuv) if max(abs(t[0]) for t in uv) > 1.6]
    assert band and all(uv_area(uv) > 0.0 for f, uv in band)                        # unmirrored band
    assert fb3.pouf_body_md(fb3.pouf_layout(seed=0)).v == md.v
    assert fb3.pouf_body_md(fb3.pouf_layout(seed=5)).v != md.v
    with pytest.raises(ValueError):
        fb3.pouf_layout(10.0, 10.0)


# ========================================================== flowering tree
@pytest.fixture(scope="module")
def trees():
    return {s: fb3.flowering_tree_geometry(s) for s in TREE_SEEDS}


def test_flat_blossom_card_carries_the_whole_photo_unmirrored():
    size = 17.0
    cu, cv = fb3.BLOSSOM_CUT
    assert (cu, cv) == (0.497, 0.154)          # measured off the yellow_blossom cut-out
    md = fb3.blossom_card_md(size)
    check_mesh(md, closed=False)
    us = [t[0] for uv in md.fuv for t in uv]
    vs = [t[1] for uv in md.fuv for t in uv]
    assert (min(us), max(us), min(vs), max(vs)) == (0.0, 1.0, 0.0, 1.0)
    for f, uv in zip(md.f, md.fuv):
        assert newell([md.v[i] for i in f]) == pytest.approx((0.0, 0.0, 1.0), abs=1e-9)   # front +Z
        for i, t in zip(f, uv):                               # U along +X, V along +Y, hung from the cut end
            assert md.v[i] == pytest.approx(((t[0] - cu) * size, (t[1] - cv) * size, 0.0), abs=1e-9)
    pt = fb3.blossom_card_point
    assert pt(cu, cv, size, 0.4, 1.0, 0.3) == pytest.approx((0.0, 0.0, 0.0), abs=1e-12)
    tip = pt(cu, 1.0, size, math.radians(25.0))
    assert tip[2] < -1.0                                                            # droops back
    left, right = pt(0.0, 1.0, size, 0.0, 0.0, 0.4), pt(1.0, 1.0, size, 0.0, 0.0, 0.4)
    assert left[2] < -1.0 and right[2] > 1.0                                        # twisted about the sprig


def test_tree_cards_count_size_and_photo(trees):
    for g in trees.values():
        assert 120 <= g["n_cards"] == len(g["cards"]) == len(g["specs"]) <= 180
        assert 3 <= g["n_main"] <= 5
        for md, sp in zip(g["cards"], g["specs"]):
            assert 14.0 <= sp["size"] <= 20.0
            check_mesh(md, closed=False)
            us = [t[0] for uv in md.fuv for t in uv]
            vs = [t[1] for uv in md.fuv for t in uv]
            assert (min(us), max(us), min(vs), max(vs)) == (0.0, 1.0, 0.0, 1.0)     # a whole sprig photo
            row = [md.v[i] for f, uv in zip(md.f, md.fuv) for i, t in zip(f, uv) if t[1] == 0.0]
            assert max(math.dist(p, q) for p in row for q in row) == pytest.approx(sp["size"], rel=0.01)
            X, Y, Z = sp["axes"]
            assert sum(a * b for a, b in zip(X, (Y[1] * Z[2] - Y[2] * Z[1], Y[2] * Z[0] - Y[0] * Z[2],
                                                 Y[0] * Z[1] - Y[1] * Z[0]))) == pytest.approx(1.0)
        dirs = [sp["axes"][1] for sp in g["specs"]]
        assert min(d[2] for d in dirs) >= -0.45 - 1e-9                              # none hanging straight down
        assert max(d[2] for d in dirs) > 0.6 and min(d[2] for d in dirs) < 0.0
        assert len({(d[0] > 0.0, d[1] > 0.0) for d in dirs}) == 4                    # all round the crown
        assert sum(sp["terminal"] for sp in g["specs"]) >= 35                       # every tip flowers


def test_tree_cards_hang_by_their_cut_end_on_the_twigs(trees):
    cut = fb3.BLOSSOM_CUT
    for g in trees.values():
        wood = []
        for b in g["branches"]:
            if b["level"] >= 1:
                lo = [min(p[k] for p in b["path"]) - 0.5 for k in range(3)]
                hi = [max(p[k] for p in b["path"]) + 0.5 for k in range(3)]
                wood.append((lo, hi, b["path"]))
        for md, sp in zip(g["cards"], g["specs"]):
            pts = [md.v[i] for f, uv in zip(md.f, md.fuv) for i, t in zip(f, uv) if t == cut]
            assert pts and all(math.dist(p, sp["attach"]) < 1e-9 for p in pts)     # the sprig's cut end...
            A = sp["attach"]
            near = [path for lo, hi, path in wood if all(lo[k] <= A[k] <= hi[k] for k in range(3))]
            assert near and min(polyline_dist(A, path) for path in near) < 1e-6     # ...on a twig's centre line


def test_tree_height_crown_and_balance(trees):
    for g in trees.values():
        assert 140.0 <= g["height"] <= 160.0 and abs(g["height"] - g["target_h"]) < 6.0   # about 150 tall
        ex, ey = g["crown"]
        assert 0.5 * (ex + ey) == pytest.approx(g["target_w"], abs=0.5)
        assert 80.0 < 0.5 * (ex + ey) < 100.0 and 65.0 < min(ex, ey) and max(ex, ey) < 125.0   # loose, airy
        assert math.hypot(*g["crown_centre"]) < 8.0                                 # balanced over the pot
        (x0, x1), (y0, y1), (z0, z1) = bounds(g["cards"] + [g["trunk"]] + g["twigs"])
        assert max(-x0, x1, -y0, y1) < 75.0 and z1 < 170.0
        d = g["pot"]
        for p in g["probes"]:                                                       # no sprig dips into the pot
            if math.hypot(p[0], p[1]) < d["R"] + 2.0:
                assert p[2] > d["H"] + 3.0
        assert d["H"] + 17.0 < g["split"][2] < d["H"] + 49.0


def test_tree_trunk_thin_twisting_and_rooted(trees):
    for g in trees.values():
        check_mesh(g["trunk"])
        assert len(g["twigs"]) == g["n_main"]
        for md in g["twigs"]:
            check_mesh(md)
        d = g["pot"]
        trunk = g["branches"][0]
        assert trunk["level"] == 0
        p0 = trunk["path"][0]
        assert p0[2] < d["soil_z"] - 1.0                                            # rises out of the soil
        assert math.hypot(p0[0], p0[1]) + 1.3 * max(trunk["radii"]) < fb3.pot_inner_r(d, d["soil_z"] - 3.0)
        assert 2.0 < max(trunk["radii"]) < 2.6 and 1.1 < trunk["radii"][-4] < 1.35  # thin, flared at the soil
        top = trunk["path"][-4]
        axis = [(p0[0] + (top[0] - p0[0]) * t, p0[1] + (top[1] - p0[1]) * t) for t in (0.25, 0.5, 0.75)]
        n = len(trunk["path"]) - 4
        wander = max(math.hypot(trunk["path"][int(n * t)][0] - a[0], trunk["path"][int(n * t)][1] - a[1])
                     for t, a in zip((0.25, 0.5, 0.75), axis))
        assert wander > 1.5                                                         # twisting
        ring = g["trunk"].v[8 * 14:9 * 14]
        rr = [math.dist(p, trunk["path"][8]) for p in ring]
        assert max(rr) / min(rr) > 1.08                                             # ridged bark
        lows = [b for b in g["branches"] if b["level"] == 2 and b["low"]]
        assert 1 <= len(lows) <= 3
        for b in lows:                                                              # low branches off the trunk
            assert polyline_dist(b["path"][0], trunk["path"][:-3]) < 1e-6
            assert d["soil_z"] + 8.0 < b["path"][0][2] < g["split"][2]
        mains = [b for b in g["branches"] if b["level"] == 1]
        for b in mains:
            assert math.dist(b["path"][0], g["split"]) < 5.0
            assert b["radii"][0] > 0.95 > 0.35 > b["radii"][-1]
        # every branch clear of the pot's rim (the cards' attach point moved to
        # the photo's real cut end, which reshuffles the grown tree: one branch
        # now starts 7.5 cm above the rim)
        assert min(p[2] for b in g["branches"][1:] for p in b["path"]) > d["H"] + 5.0


def test_brass_pot_and_soil(trees):
    d = fb3.brass_pot_dims()
    pot = fb3.brass_pot_md()
    vol = check_mesh(pot)
    (x0, x1), (y0, y1), (z0, z1) = bounds(pot)
    assert (z0, z1) == pytest.approx((0.0, 38.0), abs=1e-9)                         # 38 tall
    assert 20.8 < x1 < 21.0 and x0 == pytest.approx(-x1, abs=1e-6)                  # 42 across the rim
    floor = [math.hypot(v[0], v[1]) for v in pot.v if v[2] < 1e-9]
    assert max(floor) < fb3.POT_FOOT[0] + 1e-6 and min(floor) > fb3.POT_FOOT[0] - 2.0   # on its low foot ring
    shell = math.pi / 3.0 * 36.0 * ((d["rb"] ** 2 + d["rb"] * d["rw"] + d["rw"] ** 2)
                                   - ((d["rb"] - 0.4) ** 2 + (d["rb"] - 0.4) * (d["rw"] - 0.4) + (d["rw"] - 0.4) ** 2))
    assert 0.6 * shell < vol < 0.6 * shell + 2.0 * math.pi * 17.0 ** 2 + 1200.0      # a thin spun wall
    prof = fb3.brass_pot_profile()
    top = max(range(len(prof)), key=lambda k: prof[k][1])
    outer, inner = prof[:top + 1], prof[top:]

    def r_at(chain, z):
        for (r0, z0_), (r1, z1_) in zip(chain, chain[1:]):
            if min(z0_, z1_) <= z <= max(z0_, z1_) and z0_ != z1_:
                return r0 + (r1 - r0) * (z - z0_) / (z1_ - z0_)
        raise AssertionError(z)
    assert r_at(outer, 20.0) - r_at(inner, 20.0) == pytest.approx(0.4, abs=0.03)   # 4 mm wall
    assert r_at(outer, 30.0) > r_at(outer, 10.0) + 2.0                              # flaring to the rim
    for g in trees.values():
        soil = g["soil"]
        check_mesh(soil)
        zs = [v[2] for v in soil.v]
        assert d["H"] - 6.5 < max(zs) < d["H"] - 1.5 and min(zs) > d["z_floor"]
        for v in soil.v:                                       # into the wall, never through it
            r = math.hypot(v[0], v[1])
            assert r < fb3.pot_inner_r(d, v[2]) + 0.4 - 0.1
        rim = [v for v in soil.v if math.hypot(v[0], v[1]) > fb3.pot_inner_r(d, v[2])]
        assert len(rim) >= 60


def test_tree_parts_and_seed(trees):
    parts = fb3.flowering_tree_parts(1)
    check_parts(parts)
    names = [p[0] for p in parts]
    assert names[:3] == ["FlowerTree_Pot", "FlowerTree_Soil", "FlowerTree_Trunk"]
    g = trees[1]
    cards = [p for p in parts if p[0] == "FlowerTree_Blossoms"]
    assert len(cards) == -(-g["n_cards"] // fb3.CARDS_PER_NODE)
    assert sum(len(p[2].f) for p in cards) == sum(len(md.f) for md in g["cards"])
    assert names.count("FlowerTree_Twigs") == g["n_main"]
    (x0, x1), (y0, y1), (z0, z1) = bounds([p[2] for p in parts])
    assert z0 == pytest.approx(0.0, abs=1e-9) and 140.0 < z1 < 165.0
    again = fb3.flowering_tree_geometry(0)
    assert [md.v for md in again["cards"]] == [md.v for md in trees[0]["cards"]]
    assert again["trunk"].v == trees[0]["trunk"].v and trees[1]["trunk"].v != trees[0]["trunk"].v


# ============================================================ lounge chair
@pytest.fixture(scope="module")
def chair():
    return fb3.knit_chair_parts(0)


def test_chair_size_seat_and_base(chair):
    check_parts(chair)
    assert [p[0] for p in chair] == ["KnitChair_Base", "KnitChair_Shell", "KnitChair_Seat"]
    assert [p[1] for p in chair] == ["metal_black", "knit_stripe", "knit_stripe"]
    base, shell, seat = (p[2] for p in chair)
    (x0, x1), (y0, y1), (z0, z1) = bounds([base, shell, seat])
    assert (x0, x1, y0, y1) == pytest.approx((-40.0, 40.0, -42.5, 42.5), abs=0.02)  # 80 x 85
    assert z0 == pytest.approx(0.0, abs=1e-12) and z1 == pytest.approx(75.0, abs=0.05)   # 75 high
    bb = bounds(base)
    assert bb[0] == pytest.approx((-26.0, 26.0), abs=1e-6) and bb[2] == pytest.approx((0.0, 14.0), abs=1e-9)
    assert bounds(shell)[2][0] == pytest.approx(fb3.CHAIR_ZB) and 0.0 < 14.0 - fb3.CHAIR_ZB <= 0.15
    sb = bounds(seat)
    assert sb[2][0] == pytest.approx(fb3.CHAIR_DECK - 0.1) and 38.5 < sb[2][1] < 40.5      # seat about 38
    top_ring = [v for v in seat.v if abs(v[2] - fb3.CHAIR_SEAT) < 1e-9]
    assert len(top_ring) >= fb3.CUSHION_N
    assert 44.0 < sb[0][1] - sb[0][0] < 58.0 and 44.0 < sb[1][1] - sb[1][0] < 58.0     # a real seat
    front_roll = max(v[2] for v in shell.v if abs(v[0]) < 1.0 and v[1] < -30.0)
    front_seat = max(v[2] for v in seat.v if abs(v[0]) < 6.0 and v[1] < -26.0)
    assert front_roll == pytest.approx(35.5, abs=0.3) and front_seat > front_roll + 2.0   # lip over the roll
    arm = max(v[2] for v in shell.v if v[0] > 30.0 and abs(v[1]) < 8.0)
    assert 54.0 < arm < 60.0                                                        # arms
    back_top = max(v[2] for v in shell.v if v[1] > 30.0)
    assert back_top == pytest.approx(75.0, abs=0.05)


def test_chair_cushion_tucked_into_the_shell(chair):
    lay = fb3.chair_layout(0)
    seat = chair[2][2]
    for v in seat.v[::7]:
        phi = math.atan2(v[1], v[0])
        r = math.hypot(v[0], v[1])
        mer = fb3.chair_meridian(lay, phi)
        assert r < fb3.chair_inner_rho(mer, v[2]) + lay["overlap"] + 0.05            # at most 5 mm in
        assert r < fb3.chair_rho_out(phi) - 5.0                                     # never out through it
    zs0, zs1 = fb3.CHAIR_DECK - 0.1 + 1.5, fb3.CHAIR_SEAT - 4.0
    zm = zs0 + 0.5 * (zs1 - zs0)                                                    # a ring on the straight side
    ring = [v for v in seat.v if abs(v[2] - zm) < 1e-6]
    assert len(ring) == fb3.CUSHION_N
    for v in ring:                                                                  # pressed 5 mm into it
        phi = math.atan2(v[1], v[0])
        assert math.hypot(v[0], v[1]) == pytest.approx(
            fb3.chair_inner_rho(fb3.chair_meridian(lay, phi), zm) + lay["overlap"], abs=1e-6)


def test_chair_meridian_shape():
    lay = fb3.chair_layout(0)
    assert fb3.MER_K == 39 and fb3.MER_INNER == (25, 31, 34) and fb3.MER_RIM == 20
    for deg in range(0, 360, 15):
        phi = math.radians(deg)
        mer = fb3.chair_meridian(lay, phi)
        assert len(mer) == fb3.MER_K
        assert mer[0] == (0.0, fb3.CHAIR_ZB) and mer[-1] == pytest.approx((0.0, fb3.CHAIR_DECK))
        assert max(r for r, z in mer) == pytest.approx(fb3.chair_rho_out(phi), abs=1e-4)   # on the plan outline
        assert min(math.dist(a, b) for a, b in zip(mer, mer[1:])) > 0.05
        area = 0.5 * sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(mer, mer[1:] + mer[:1]))
        assert area > 300.0                                                         # counter-clockwise, solid
        zt = max(z for r, z in mer)
        top = [r for r, z in mer if z > zt - 0.5]
        assert max(top) - min(top) < 0.6 * fb3._periodic(fb3.RIM_W, phi)            # a full round rim
    back = fb3.chair_meridian(lay, math.radians(90.0))
    i0, i1, _i2 = fb3.MER_INNER
    assert back[i0][0] - back[i1][0] > 8.0                                          # reclined back


def test_chair_knit_uvs_run_round_the_chair(chair):
    shell, seat = chair[1][2], chair[2][2]
    K, N = fb3.MER_K, fb3.CHAIR_N
    assert all(uv is not None for uv in shell.fuv) and all(uv is not None for uv in seat.fuv)
    us = {}
    for f, uv in zip(shell.f, shell.fuv):
        for i, t in zip(f, uv):
            if i >= 2:
                us.setdefault((i - 2) // (K - 2), set()).add(round(t[0], 9))
    assert len(us) == N
    assert all(len(us[j]) == 1 for j in range(1, N)) and len(us[0]) == 2           # U constant on a meridian,
    seq = [min(us[j]) for j in range(N)] + [max(us[0])]                             # the seam up the back
    assert all(b > a for a, b in zip(seq, seq[1:]))                                 # increasing round the chair
    rim = [shell.v[2 + j * (K - 2) + fb3.MER_RIM - 1] for j in range(N)]
    length = sum(math.dist(rim[j], rim[(j + 1) % N]) for j in range(N))
    assert seq[-1] * fb3.KNIT == pytest.approx(length, rel=1e-9)                    # true length of the rim
    assert 200.0 < length < 290.0
    dev = []
    for f, uv in zip(shell.f, shell.fuv):
        for i, t in zip(f, uv):
            if i < 2:
                continue
            j, k = (i - 2) // (K - 2), (i - 2) % (K - 2) + 1
            x, y, z = shell.v[i]
            if k <= fb3.MER_RIM and 27.0 < z < 33.0 and y > -20.0:
                dev.append(t[1] * fb3.KNIT - (z - 30.0))
    assert len(dev) > 100 and max(map(abs, dev)) < 0.8                              # level stripes outside
    assert all(uv_area(uv) > 0.0 for f, uv in zip(shell.f, shell.fuv) if len(f) == 4)   # unmirrored
    top = [uv for f, uv in zip(seat.f, seat.fuv) if all(seat.v[i][2] > fb3.CHAIR_SEAT - 1e-9 for i in f)]
    assert len(top) == (fb3.CUSHION_N // 4) ** 2 and all(uv_area(uv) > 0.0 for uv in top)


def test_chair_seeded_and_deterministic(chair):
    again = fb3.knit_chair_parts(0)
    assert all(a[2].v == b[2].v for a, b in zip(chair, again))
    other = fb3.knit_chair_parts(3)
    assert other[1][2].v != chair[1][2].v and other[0][2].v == chair[0][2].v


# ================================================================ wrappers
class _FakeNode(object):
    def __init__(self, src=""):
        self.src, self.parent, self.mods, self.pos, self.rot = src, None, [], None, None
        self.name = src.split('name:"', 1)[1].split('"', 1)[0] if 'name:"' in src else ""


class _FakeRT(object):
    """Just enough pymxs.runtime for furn_living._build and kit.soften / part / group / place."""

    def __init__(self):
        self.dummies = []

    def execute(self, src):
        return _FakeNode(src)

    def Dummy(self):
        d = _FakeNode()
        self.dummies.append(d)
        return d

    def TurboSmooth(self):
        return types.SimpleNamespace(kind="TurboSmooth", iterations=0)

    def addModifier(self, node, mod):
        node.mods.append(mod)

    def isProperty(self, obj, name):
        return False

    def Name(self, s):
        return s

    def Point3(self, *a):
        return tuple(a)

    def angleaxis(self, *a):
        return a

    def rotate(self, node, aa):
        node.rot = aa


@pytest.fixture
def fake_max(monkeypatch):
    fake = _FakeRT()
    monkeypatch.setattr(kit, "rt", fake)
    monkeypatch.setattr(furn_living, "rt", fake)
    monkeypatch.setattr(kit, "PARTS", [])
    return fake


OWN_UV = {"tapestry", "blossom_card", "knit_stripe"}


@pytest.mark.parametrize("build,args,gname,keys", [
    (fb3.build_tapestry, (), "Tapestry", {"tapestry"}),
    (fb3.build_flowering_tree, (3,), "FloweringTree", {"metal_brass", "soil", "stem", "blossom_card"}),
    (fb3.build_velvet_pouf, (1,), "VelvetPouf", {"slate_velvet"}),
    (fb3.build_knit_lounge_chair, (2,), "KnitLoungeChair", {"knit_stripe", "metal_black"}),
])
def test_build_wrappers_register_every_node(fake_max, build, args, gname, keys):
    group = build(*args)
    assert group.name == gname
    parts = list(kit.PARTS)
    assert {key for _n, key, _t, _m in parts} == keys
    for node, key, tile, maptype in parts:
        assert key in kit.MAT_KEYS and node.parent is group                         # one dummy per piece
        assert len(node.src) < 300000, (node.name, len(node.src))                   # a modest MAXScript literal
        mods = [m.kind for m in node.mods]
        if key in ("tapestry", "blossom_card"):                                     # a photo on 0-1 UVs:
            assert tile is None and maptype is None and not mods                    # kept, not smoothed
            assert "setTVert" in node.src and "buildTVFaces" in node.src
        elif key == "knit_stripe" or node.name == "VelvetPouf_Body":                # own UVs at real scale
            assert tile is None and maptype is None and mods == ["TurboSmooth"]
            assert "setTVert" in node.src
        else:                                                                       # box-mapped at real scale
            assert tile > 0 and maptype == 4 and "setTVert" not in node.src
            assert mods == ([] if key == "rug" else ["TurboSmooth"])


def test_preview_builds_every_piece(fake_max):
    nodes = fb3.preview()
    assert [n.name for n in nodes] == ["Tapestry", "KnitLoungeChair", "VelvetPouf", "FloweringTree"]
    assert all(n.pos is not None for n in nodes)
