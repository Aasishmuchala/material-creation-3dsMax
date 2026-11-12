"""Off-Max geometry tests for tools/apartment/furn_bench2_decor.py (benchmark 2:
the taupe lacquered credenza, three abstract sculptures and the potted olive
tree).

pymxs is stubbed while the module is imported (and the previous entry put
back), so only the pure-Python cage generators run; the build_* wrappers are
run against a small recording fake of the pymxs runtime.
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
    import furn_bench2_decor as fbd  # noqa: E402
finally:
    if _prev is None:
        sys.modules.pop("pymxs", None)
    else:
        sys.modules["pymxs"] = _prev

NEW_KEYS = ("lacquer_taupe", "microcement", "olive_card")
USED = {"lacquer_taupe", "metal_black", "microcement", "wood_dark", "soil", "stem", "olive_card"}
OLIVE_SEEDS = (0, 1, 6)          # four, four and three main branches


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
    """Non-empty, finite, valid faces; closed meshes: every directed edge
    paired with its reverse exactly once and a positive enclosed volume
    (consistently outward faces)."""
    assert md.v and md.f
    assert all(math.isfinite(c) for v in md.v for c in v), "NaN / inf vertex"
    nv = len(md.v)
    for f in md.f:
        assert len(f) >= 3 and len(set(f)) == len(f) and all(0 <= i < nv for i in f)
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


def check_parts(parts):
    assert parts
    for name, mat, md, tile, smooth in parts:
        assert mat in kit.MAT_KEYS and mat in USED, (name, mat)
        if tile is None:                          # a card node: own 0-1 UVs, open sheets
            assert mat == "olive_card" and smooth == 0, name
            check_mesh(md, closed=False)
            assert len(md.fuv) == len(md.f) and all(uv is not None for uv in md.fuv), name
        else:
            assert tile > 0 and smooth in (0, 1), name
            check_mesh(md)


def part(parts, name):
    return [p for p in parts if p[0] == name][0][2]


def components(md):
    """Vertex index sets of the connected pieces of a mesh."""
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
    groups = {}
    for f in md.f:
        for i in f:
            groups.setdefault(find(i), set()).add(i)
    return list(groups.values())


def corner_clearance(pts):
    """Smallest distance from a bounding-box corner to a vertex: 0 for a
    razor-sharp box, r (sqrt 3 - 1) for corners rounded to radius r."""
    b = [(min(v[k] for v in pts), max(v[k] for v in pts)) for k in range(3)]
    return min(math.dist(v, (cx, cy, cz)) for cx in b[0] for cy in b[1] for cz in b[2] for v in pts)


def seg_dist(p, a, b):
    ab = [b[i] - a[i] for i in range(3)]
    l2 = sum(c * c for c in ab)
    t = 0.0 if l2 < 1e-12 else max(0.0, min(1.0, sum(ab[i] * (p[i] - a[i]) for i in range(3)) / l2))
    return math.dist(p, [a[i] + ab[i] * t for i in range(3)])


def polyline_dist(p, path):
    return min(seg_dist(p, a, b) for a, b in zip(path, path[1:]))


def split_at_top(prof):
    """(outer, inner) halves of a vessel section, split at its highest point."""
    i = max(range(len(prof)), key=lambda k: prof[k][1])
    return prof[:i + 1], prof[i:]


def r_at(chain, z):
    """Radius where a (r, z) chain crosses height z (first crossing)."""
    for (r0, z0), (r1, z1) in zip(chain, chain[1:]):
        if min(z0, z1) <= z <= max(z0, z1) and z0 != z1:
            return r0 + (r1 - r0) * (z - z0) / (z1 - z0)
    raise AssertionError("no crossing at z=%s" % z)


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


# --------------------------------------------------------------- materials
def test_new_material_keys_are_declared_at_import():
    for key in NEW_KEYS:
        assert key in kit.MAT_KEYS and kit.MAT_KEYS[key]
    used = set()
    for fn in (fbd.credenza_parts, fbd.arch_parts, fbd.head_parts, fbd.wire_parts, fbd.olive_tree_parts):
        used |= {p[1] for p in fn()}
    assert used == USED and all(k in kit.MAT_KEYS for k in used)


# ------------------------------------------------------------ rounded box
def test_rounded_box_is_a_closed_solid_with_true_rounds():
    a, b, c, r = 20.0, 10.0, 4.0, 0.5
    md = fbd._rbox_md(-10.0, 10.0, -5.0, 5.0, 0.0, 4.0, r)
    vol = check_mesh(md)
    assert bounds(md) == pytest.approx([(-10.0, 10.0), (-5.0, 5.0), (0.0, 4.0)], abs=1e-9)
    ia, ib, ic = a - 2 * r, b - 2 * r, c - 2 * r
    exact = (ia * ib * ic + 2 * r * (ia * ib + ia * ic + ib * ic) + math.pi * r * r * (ia + ib + ic)
             + 4.0 / 3.0 * math.pi * r ** 3)
    assert vol == pytest.approx(exact, rel=0.002)
    assert corner_clearance(md.v) == pytest.approx(r * (math.sqrt(3.0) - 1.0), rel=1e-6)
    for p in md.v:                     # every vertex lies on the rounded box
        q = (min(max(p[0], -9.5), 9.5), min(max(p[1], -4.5), 4.5), min(max(p[2], 0.5), 3.5))
        assert math.dist(p, q) == pytest.approx(r, abs=1e-9)


# ---------------------------------------------------------------- credenza
def test_credenza_dimensions_and_rounded_top():
    parts = fbd.credenza_parts()
    check_parts(parts)
    assert [p[0] for p in parts] == ["Credenza_Top", "Credenza_Carcass", "Credenza_Doors", "Credenza_Plinth"]
    assert [p[1] for p in parts] == ["lacquer_taupe"] * 3 + ["metal_black"]
    (x0, x1), (y0, y1), (z0, z1) = bounds([p[2] for p in parts])
    assert (x0, x1, y0, y1, z0, z1) == pytest.approx((-150.0, 150.0, -22.5, 22.5, 0.0, 55.0), abs=1e-9)
    top = part(parts, "Credenza_Top")
    assert bounds(top)[2] == pytest.approx((52.5, 55.0), abs=1e-9)                # a 2.5 cm top
    k = math.sqrt(3.0) - 1.0
    assert 0.2 * k < corner_clearance(top.v) < 0.3 * k                             # 2-3 mm round edges
    flat = [v for v in top.v if v[2] > 55.0 - 1e-9]
    assert min(v[1] for v in flat) == pytest.approx(-22.25, abs=1e-6)               # rounded over at the front


def test_credenza_handleless_doors_behind_shadow_gaps():
    lay = fbd.credenza_layout()
    parts = fbd.credenza_parts()
    doors = part(parts, "Credenza_Doors")
    comps = components(doors)
    assert len(comps) == lay["n_doors"] == 4                                        # four doors, no handles
    boxes = sorted([[(min(doors.v[i][k] for i in c), max(doors.v[i][k] for i in c)) for k in range(3)]
                    for c in comps])
    assert boxes[0][0][0] == pytest.approx(-150.0) and boxes[-1][0][1] == pytest.approx(150.0)
    for a, b in zip(boxes, boxes[1:]):
        assert b[0][0] - a[0][1] == pytest.approx(0.3, abs=1e-9)                    # 3 mm shadow gaps
    under_top = bounds(part(parts, "Credenza_Top"))[2][0]
    for bx in boxes:
        assert bx[1] == pytest.approx((-22.5, -20.6), abs=1e-9)                     # 19 mm, flush with the top
        assert bx[2][0] == pytest.approx(5.0) and under_top - bx[2][1] == pytest.approx(0.3, abs=1e-9)
        assert 70.0 < bx[0][1] - bx[0][0] < 80.0
    one = [doors.v[i] for i in comps[0]]
    assert 0.05 < corner_clearance(one) < 0.1                                       # 1 mm door edges
    body = bounds(part(parts, "Credenza_Carcass"))
    assert body[1][0] == pytest.approx(-20.5, abs=1e-9)          # the gaps run 2 cm deep onto the carcass
    assert body[0] == pytest.approx((-150.0, 150.0)) and under_top - body[2][1] == pytest.approx(0.02)


def test_credenza_plinth_recessed_and_dark():
    parts = fbd.credenza_parts()
    pl = part(parts, "Credenza_Plinth")
    (x0, x1), (y0, y1), (z0, z1) = bounds(pl)
    assert (x0, x1, y0, y1) == pytest.approx((-146.0, 146.0, -18.5, 18.5), abs=1e-9)   # set back 4 cm
    assert z0 == pytest.approx(0.0, abs=1e-12)
    body = bounds(part(parts, "Credenza_Carcass"))
    assert body[2][0] == pytest.approx(5.0) and 0.0 < z1 - body[2][0] <= 0.15         # 5 cm, up into the carcass
    assert 0.1 < corner_clearance(pl.v) < 0.12


@pytest.mark.parametrize("length,n_doors", [(240.0, 3), (180.0, 2), (360.0, 5)])
def test_credenza_other_lengths(length, n_doors):
    parts = fbd.credenza_parts(length)
    check_parts(parts)
    (x0, x1), (y0, y1), (z0, z1) = bounds([p[2] for p in parts])
    assert x1 - x0 == pytest.approx(length) and y1 - y0 == pytest.approx(45.0) and z1 == pytest.approx(55.0)
    assert len(components(part(parts, "Credenza_Doors"))) == n_doors
    with pytest.raises(ValueError):
        fbd.credenza_parts(40.0)


# --------------------------------------------------------------- sculptures
def test_arch_is_an_inverted_u_of_round_section():
    parts = fbd.arch_parts()
    check_parts(parts)
    md = parts[0][2]
    (x0, x1), (y0, y1), (z0, z1) = bounds(md)
    assert (x0, x1) == pytest.approx((-20.0, 20.0), abs=0.02)                       # 40 long
    assert (z0, z1) == pytest.approx((0.0, 30.0), abs=0.02)                         # 30 high
    assert 8.5 < y1 - y0 < 10.5 and y0 == pytest.approx(-y1)                        # thick round section
    path, rad = fbd.arch_path()
    crown = max(range(len(path)), key=lambda i: path[i][2])
    assert rad[crown] < max(rad) - 0.3                                              # slimmer over the crown
    assert min(v[2] for v in md.v if abs(v[0]) < 2.0) > 20.0                         # an opening under it
    assert min(abs(v[0]) for v in md.v if v[2] < 12.0) > 10.0                        # between straight legs
    feet = [v for v in md.v if v[2] < 1e-9]                                         # two flat feet...
    assert {math.copysign(1.0, v[0]) for v in feet} == {-1.0, 1.0} and len(feet) > 40
    a = 20.0 - max(rad)
    assert max(math.hypot(abs(v[0]) - a, v[1]) for v in feet) < max(rad) - 0.5       # ...with rounded rims


def test_head_and_shoulders():
    parts = fbd.head_parts()
    check_parts(parts)
    sh, neck, head = (part(parts, n) for n in ("SculptureHead_Shoulders", "SculptureHead_Neck",
                                               "SculptureHead_Head"))
    (x0, x1), (y0, y1), (z0, z1) = bounds([sh, neck, head])
    assert z0 == pytest.approx(0.0, abs=1e-9) and z1 == pytest.approx(45.0, abs=1e-6)  # 45 tall
    sb, nb, hb = bounds(sh), bounds(neck), bounds(head)
    assert 25.0 < sb[0][1] - sb[0][0] < 32.0 and 12.0 < sb[1][1] - sb[1][0] < 15.0     # a broad wedge...
    assert 16.0 < sb[2][1] < 18.5
    yf0, yb0 = fbd._shoulder_y(0.0)
    yf1, yb1 = fbd._shoulder_y(sb[2][1])
    assert (yb0 - yf0) - (yb1 - yf1) > 2.0 and yf1 - yf0 > 1.5                       # ...its chest leaning back
    for v in sh.v:
        yf, yb = fbd._shoulder_y(v[2])
        assert yf - 1e-9 <= v[1] <= yb + 1e-9
    assert fbd.NECK[1][0] > fbd.NECK[-2][0] + 0.5                                   # a tapered neck,
    assert all(fbd.shoulders_contain(v, 0.3) for v in neck.v if v[2] < nb[2][0] + 1.0)  # buried in the shoulders
    assert all(fbd.head_contains(v, 0.3) for v in neck.v if v[2] > nb[2][1] - 1.5)      # and in the head
    assert hb[2][0] > sb[2][1] + 5.0                                                # an ovoid head clear of them
    assert 19.0 < hb[2][1] - hb[2][0] < 22.0 and 13.0 < hb[0][1] - hb[0][0] < 17.0
    neck_hi = [v for v in neck.v if v[2] > hb[2][0]]
    assert hb[1][0] < min(v[1] for v in neck_hi) - 2.0                              # the chin juts forward


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_wire_figure(seed):
    parts = fbd.wire_parts(seed)
    check_parts(parts)
    base, wires = part(parts, "SculptureWire_Base"), part(parts, "SculptureWire_Wires")
    R, T = fbd.WIRE_DISC
    bb = bounds(base)
    assert bb[2] == pytest.approx((0.0, T)) and bb[0][1] == pytest.approx(R, abs=0.01)  # small disc base
    assert len(components(wires)) == 12                                             # a dozen wires
    assert 46.0 < bounds(wires)[2][1] < 51.0                                        # about 50 tall
    paths = fbd.wire_paths(seed)
    assert len(paths) == 12
    for path in paths:
        r0 = math.hypot(path[0][0], path[0][1])
        assert 0.0 < path[0][2] < T and r0 + fbd.WIRE_R < R - 0.3                   # welded into the disc,
        assert r0 > 3.2                                                             # splayed at the base
        mid = [p for p in path if 20.0 < p[2] < 30.0]
        assert mid and max(math.hypot(p[0], p[1]) for p in mid) < 4.0               # round a slim core
    ends = [path[-1] for path in paths]
    assert max(math.hypot(p[0], p[1]) for p in ends) > 4.5                          # splayed at the top
    assert max(p[2] for p in ends) - min(p[2] for p in ends) > 1.0
    # spiralling: every wire winds about a turn round the bundle, all the same way
    centre = [tuple(sum(p[8 + k][q] for p in paths) / 12.0 for q in range(2)) for k in range(34)]
    turns = []
    for path in paths:
        tot, prev = 0.0, None
        for k in range(34):
            ang = math.atan2(path[8 + k][1] - centre[k][1], path[8 + k][0] - centre[k][0])
            if prev is not None:
                tot += (ang - prev + math.pi) % (2.0 * math.pi) - math.pi
            prev = ang
        turns.append(tot / (2.0 * math.pi))
    assert all(abs(t) > 0.9 for t in turns) and len({t > 0 for t in turns}) == 1
    assert fbd.wire_paths(seed) == paths and fbd.wire_paths(seed + 10) != paths


# --------------------------------------------------------------- olive cards
def test_flat_olive_card_carries_the_whole_photo_unmirrored():
    size = 22.0
    cu, cv = fbd.CARD_CUT
    md = fbd.olive_card_md(size)
    check_mesh(md, closed=False)
    us = [t[0] for uv in md.fuv for t in uv]
    vs = [t[1] for uv in md.fuv for t in uv]
    assert (min(us), max(us), min(vs), max(vs)) == (0.0, 1.0, 0.0, 1.0)
    for f, uv in zip(md.f, md.fuv):
        a, b, c = (md.v[i] for i in f[:3])
        n = cross([b[k] - a[k] for k in range(3)], [c[k] - a[k] for k in range(3)])
        assert n[2] > 0.0 and abs(n[0]) + abs(n[1]) < 1e-9                         # the front faces +Z
        for i, t in zip(f, uv):                                                     # U along +X, V along +Y,
            p = md.v[i]                                                             # hung from the cut end
            assert p == pytest.approx(((t[0] - cu) * size, (t[1] - cv) * size, 0.0), abs=1e-9)
    b = bounds(md)
    assert b[0][1] - b[0][0] == pytest.approx(size) and b[1][1] - b[1][0] == pytest.approx(size)  # square


def test_olive_card_droops_folds_and_twists():
    size = 22.0
    cu, cv = fbd.CARD_CUT
    pt = fbd.olive_card_point
    assert pt(cu, cv, size, 0.5, 1.5, 0.3) == pytest.approx((0.0, 0.0, 0.0), abs=1e-12)
    droop = math.radians(30.0)
    tip = pt(cu, 1.0, size, droop)
    S = (1.0 - cv) * size
    kap = droop / S
    assert tip[2] < -2.0                                                            # arcs back, away from the front
    assert math.hypot(tip[1], tip[2]) == pytest.approx(2.0 * math.sin(0.5 * kap * S) / kap)   # twig keeps its length
    near = pt(cu, 1.0 - 1e-5, size, droop)
    assert math.degrees(math.atan2(tip[2] - near[2], tip[1] - near[1])) == pytest.approx(-30.0, abs=0.05)
    mid = pt(cu, 0.6, size, 0.0, 1.2)
    for u in (0.0, 1.0):                                                            # folded along the twig
        e = pt(u, 0.6, size, 0.0, 1.2)
        assert e[2] - mid[2] == pytest.approx(1.2 * min(1.0, abs(u - cu) / 0.5) ** 1.2, rel=1e-9)
    left, right = pt(0.0, 1.0, size, 0.0, 0.0, 0.4), pt(1.0, 1.0, size, 0.0, 0.0, 0.4)
    assert left[2] < -1.0 and right[2] > 1.0                                        # turned about the twig


# ---------------------------------------------------------------- olive tree
@pytest.fixture(scope="module")
def olives():
    return {s: fbd.olive_tree_geometry(s) for s in OLIVE_SEEDS}


def test_olive_card_count_sizes_and_angles(olives):
    for g in olives.values():
        assert 120 <= g["n_cards"] == len(g["cards"]) == len(g["specs"]) <= 200
        assert g["n_main"] in (3, 4)
        for md, sp in zip(g["cards"], g["specs"]):
            assert 18.0 <= sp["size"] <= 26.0
            check_mesh(md, closed=False)
            us = [t[0] for uv in md.fuv for t in uv]
            vs = [t[1] for uv in md.fuv for t in uv]
            assert (min(us), max(us), min(vs), max(vs)) == (0.0, 1.0, 0.0, 1.0)     # a whole sprig photo
            row = [md.v[i] for f, uv in zip(md.f, md.fuv) for i, t in zip(f, uv) if t[1] == 0.0]
            assert max(math.dist(p, q) for p in row for q in row) == pytest.approx(sp["size"], rel=0.01)
        levels = [sp["level"] for sp in g["specs"]]
        assert set(levels) <= {1, 2, 3} and levels.count(3) > 0.6 * len(levels)     # mostly on the outer twigs
        assert sum(sp["terminal"] for sp in g["specs"]) >= 40                       # every tip ends in a sprig
        dirs = [sp["axes"][1] for sp in g["specs"]]
        assert min(d[2] for d in dirs) < -0.2 and max(d[2] for d in dirs) > 0.5      # varied angles:
        assert min(d[2] for d in dirs) >= -0.55 - 1e-9                              # some hanging, none straight down
        quads = {(d[0] > 0.0, d[1] > 0.0) for d in dirs}
        assert len(quads) == 4                                                      # all round the crown


def test_olive_height_and_crown(olives):
    for g in olives.values():
        assert 160.0 <= g["height"] <= 180.0 and abs(g["height"] - g["target_h"]) < 6.0   # about 170 tall
        assert 0.7 < g["scale"] < 1.45
        ex, ey = g["crown"]
        assert 95.0 < ex < 145.0 and 95.0 < ey < 145.0
        assert 0.5 * (ex + ey) == pytest.approx(g["target_w"], abs=0.5)
        assert 108.0 < 0.5 * (ex + ey) < 132.0                                      # about 120 across
        assert math.hypot(*g["crown_centre"]) < 12.0                                 # balanced over the pot
        (x0, x1), (y0, y1), (z0, z1) = bounds(g["cards"] + [g["trunk"]] + g["twigs"])
        assert max(-x0, x1, -y0, y1) < 85.0 and z1 < 195.0


def test_olive_cards_hang_from_the_twigs(olives):
    cu, cv = fbd.CARD_CUT
    for g in olives.values():
        wood = []
        for b in g["branches"]:
            if b["level"] >= 1:
                lo = [min(p[k] for p in b["path"]) - 0.5 for k in range(3)]
                hi = [max(p[k] for p in b["path"]) + 0.5 for k in range(3)]
                wood.append((lo, hi, b["path"]))
        for md, sp in zip(g["cards"], g["specs"]):
            cut = [md.v[i] for f, uv in zip(md.f, md.fuv) for i, t in zip(f, uv) if t == (cu, cv)]
            assert cut and all(math.dist(p, sp["attach"]) < 1e-9 for p in cut)     # the sprig's cut end...
            A = sp["attach"]
            near = [path for lo, hi, path in wood if all(lo[k] <= A[k] <= hi[k] for k in range(3))]
            assert near and min(polyline_dist(A, path) for path in near) < 1e-6     # ...on a twig's centre line


def test_olive_wood_closed_gnarled_and_clear_of_the_pot(olives):
    for g in olives.values():
        check_mesh(g["trunk"])
        assert len(g["twigs"]) == g["n_main"]
        for md in g["twigs"]:
            check_mesh(md)
        d = g["pot"]
        trunk = g["branches"][0]
        assert trunk["level"] == 0
        p0 = trunk["path"][0]
        assert p0[2] < d["soil_z"] - 1.0                                            # rises out of the soil
        assert math.hypot(p0[0], p0[1]) + 1.3 * max(trunk["radii"]) < d["r_in"]
        assert max(trunk["radii"]) > 4.0 and min(trunk["radii"][:20]) > 2.4         # thick, flared at the soil
        i = 8
        ring = g["trunk"].v[i * 16:(i + 1) * 16]
        rr = [math.dist(p, trunk["path"][i]) for p in ring]
        assert max(rr) / min(rr) > 1.2                                              # fluted, gnarled bark
        mains = [b for b in g["branches"] if b["level"] == 1]
        assert len(mains) == g["n_main"]
        for b in mains:                                                             # leaning out of the split
            assert math.dist(b["path"][0], g["split"]) < 5.0
            assert math.hypot(b["path"][-1][0] - g["split"][0], b["path"][-1][1] - g["split"][1]) > 15.0
            assert b["radii"][0] > 1.9 > 0.6 > b["radii"][-1]
        twigs = [b for b in g["branches"] if b["level"] == 3]
        assert len(twigs) >= 4 * g["n_main"] and all(0.09 <= min(b["radii"]) <= max(b["radii"]) <= 0.3
                                                     for b in twigs)
        for p in g["probes"]:                                                       # no sprig dips into the pot
            if math.hypot(p[0], p[1]) < d["R"] + 2.0:
                assert p[2] > d["top"] + 3.0
        assert min(p[2] for b in g["branches"][1:] for p in b["path"]) > d["top"] + 10.0


def test_olive_planter_soil_and_stand(olives):
    d = fbd.olive_pot_dims()
    pot = fbd.olive_pot_md()
    vol = check_mesh(pot)
    b = bounds(pot)
    assert b[2] == pytest.approx((fbd.STAND_H, fbd.STAND_H + 40.0), abs=1e-9)        # 40 tall, 20 off the floor
    assert b[0][1] == pytest.approx(22.5, abs=0.05)                                  # 45 across
    shell = (math.pi * 22.5 ** 2 * 40.0 - math.pi * d["r_in"] ** 2 * (40.0 - d["floor"])
             - math.pi * 19.5 ** 2 * 0.4)
    assert vol == pytest.approx(shell, rel=0.02)                                     # a real wall
    outer, inner = split_at_top(fbd.olive_pot_profile())
    assert r_at(outer, 20.0) - r_at(inner[::-1], 20.0) == pytest.approx(1.6, abs=0.01)
    for g in olives.values():
        soil = g["soil"]
        check_mesh(soil)
        zs = [v[2] for v in soil.v]
        assert d["top"] - 6.0 < max(zs) < d["top"] - 1.0 and min(zs) > d["z0"] + d["floor"]
        rs = [math.hypot(v[0], v[1]) for v in soil.v]
        assert max(rs) - d["r_in"] > 0.2 and max(rs) < d["R"] - 0.3                  # into the wall, not through
    st = fbd.stand_md()
    check_mesh(st)
    lay = fbd.stand_layout()
    sb = bounds(st)
    assert sb[2] == pytest.approx((0.0, fbd.STAND_H + fbd.STAND["cradle"]), abs=1e-9)
    feet = [v for v in st.v if v[2] < 1e-9]                                          # four feet on the floor
    assert {(v[0] > 0.0, v[1] > 0.0) for v in feet} == {(False, False), (False, True), (True, False), (True, True)}
    assert 0.0 < fbd.STAND_H - lay["rail_z"][1] < 0.05                               # the pot rests on the rails
    assert max(math.hypot(v[0], v[1]) for v in st.v if abs(v[2] - lay["rail_z"][1]) < 1e-6) > d["R"]
    assert min(math.hypot(v[0], v[1]) for v in st.v if v[2] > fbd.STAND_H) > d["R"] + 0.1   # legs clear the pot


def test_olive_tree_is_deterministic_per_seed(olives):
    again = fbd.olive_tree_geometry(OLIVE_SEEDS[0])
    first = olives[OLIVE_SEEDS[0]]
    assert [md.v for md in again["cards"]] == [md.v for md in first["cards"]]
    assert again["trunk"].v == first["trunk"].v
    assert olives[OLIVE_SEEDS[1]]["trunk"].v != first["trunk"].v


def test_olive_tree_parts():
    parts = fbd.olive_tree_parts(1)
    check_parts(parts)
    names = [p[0] for p in parts]
    assert names[:4] == ["OliveTree_Stand", "OliveTree_Pot", "OliveTree_Soil", "OliveTree_Trunk"]
    g = fbd.olive_tree_geometry(1)
    leaves = [p for p in parts if p[0] == "OliveTree_Leaves"]
    assert len(leaves) == -(-g["n_cards"] // fbd.CARDS_PER_NODE)
    assert sum(len(p[2].f) for p in leaves) == sum(len(md.f) for md in g["cards"])
    assert names.count("OliveTree_Twigs") == g["n_main"]
    (x0, x1), (y0, y1), (z0, z1) = bounds([p[2] for p in parts])
    assert z0 == pytest.approx(0.0, abs=1e-9) and 160.0 < z1 < 195.0


# ---------------------------------------------------------------- dressing
def test_dressing_fits_on_the_credenza():
    lay = fbd.credenza_layout()
    A, B = 0.5 * lay["L"], 0.5 * lay["D"]
    boxes = []
    for key, px, py, pz, deg, kw in fbd.DRESSING:
        assert pz == pytest.approx(lay["H"])                                         # standing on the top
        c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        pts = [v for _n, _m, md, _t, _s in fbd.PIECES[key](**kw) for v in md.v]
        assert min(v[2] for v in pts) == pytest.approx(0.0, abs=1e-9)
        xs = [px + v[0] * c - v[1] * s for v in pts]
        ys = [py + v[0] * s + v[1] * c for v in pts]
        box = (min(xs), max(xs), min(ys), max(ys))
        assert -A + 1.0 < box[0] and box[1] < A - 1.0 and -B + 1.0 < box[2] and box[3] < B - 1.0, key
        for other in boxes:
            assert box[1] < other[0] or other[1] < box[0] or box[3] < other[2] or other[3] < box[2], key
        boxes.append(box)


# ---------------------------------------------------------------- wrappers
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


@pytest.mark.parametrize("build,args,gname,keys", [
    (fbd.build_credenza, (), "Credenza", {"lacquer_taupe", "metal_black"}),
    (fbd.build_sculpture_arch, (), "SculptureArch", {"microcement"}),
    (fbd.build_sculpture_head, (), "SculptureHead", {"microcement"}),
    (fbd.build_sculpture_wire, (1,), "SculptureWire", {"metal_black"}),
    (fbd.build_olive_tree, (6,), "OliveTree", {"wood_dark", "microcement", "soil", "stem", "olive_card"}),
])
def test_build_wrappers_register_every_node(fake_max, build, args, gname, keys):
    group = build(*args)
    assert group.name == gname
    parts = list(kit.PARTS)
    assert {key for _n, key, _t, _m in parts} == keys
    for node, key, tile, maptype in parts:
        assert key in kit.MAT_KEYS and node.parent is group                         # one dummy per piece
        assert len(node.src) < 300000                                               # a modest MAXScript literal
        if key == "olive_card":                                                     # own 0-1 UVs: no box map,
            assert tile is None and maptype is None                                 # no smoothing
            assert "setTVert" in node.src and "buildTVFaces" in node.src and not node.mods
        else:                                                                       # box-mapped at real scale
            assert tile > 0 and maptype == 4
            assert [m.kind for m in node.mods] in ([], ["TurboSmooth"])
    if gname == "Credenza":                                                         # explicit rounds and support
        assert all(not node.mods for node, _k, _t, _m in parts)                     # loops: no TurboSmooth
    if gname == "OliveTree":
        n = fbd.olive_tree_geometry(6)["n_cards"]
        assert sum(1 for _n, key, _t, _m in parts if key == "olive_card") == -(-n // fbd.CARDS_PER_NODE)


def test_preview_dresses_the_credenza(fake_max):
    group = fbd.preview()
    assert group.name == "Credenza_Dressed"
    kids = [d for d in fake_max.dummies if d.parent is group]
    assert len(kids) == 1 + len(fbd.DRESSING)
    assert {d.name for d in kids} == {"Credenza", "SculptureHead", "SculptureArch", "SculptureWire"}
    assert any(d.name == "OliveTree" and d.parent is None for d in fake_max.dummies)
