"""Off-Max geometry tests for tools/apartment/furn_bench_console.py.

pymxs is stubbed while the module is imported (and the previous entry put
back), so only the pure-Python cage generators run; the build_* wrappers are
exercised with furn_living._build / kit.soften / kit.group / kit.place faked.
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
    import furn_bench_console as fbc  # noqa: E402
finally:
    if _prev is None:
        sys.modules.pop("pymxs", None)
    else:
        sys.modules["pymxs"] = _prev

ALLOWED = {"leather", "metal_steel", "metal_chrome", "metal_black", "metal_brass", "glass_solid", "paper",
           "linen", "shade", "bedding", "stem", "leaf_card", "soil", "pot_matte", "canvas_bag", "paint_white",
           "wall_paint", "wood_light", "rug"}


# ------------------------------------------------------------------ helpers
def bounds(mds):
    if not isinstance(mds, (list, tuple)):
        mds = [mds]
    vs = [v for md in mds for v in md.v]
    return [(min(v[k] for v in vs), max(v[k] for v in vs)) for k in range(3)]


def check_mesh(md, closed=True):
    """Non-empty, finite, valid faces; closed meshes: every directed edge
    paired with its reverse exactly once and a positive enclosed volume
    (consistently outward faces)."""
    assert md.v and md.f
    assert all(math.isfinite(c) for v in md.v for c in v)
    nv = len(md.v)
    for f in md.f:
        assert len(f) >= 3 and len(set(f)) == len(f) and all(0 <= i < nv for i in f)
    if not closed:
        return
    count = {}
    for f in md.f:
        for i in range(len(f)):
            e = (f[i], f[(i + 1) % len(f)])
            count[e] = count.get(e, 0) + 1
    assert all(c == 1 for c in count.values()), "edge used twice in one direction"
    assert all((b, a) in count for (a, b) in count), "open edge"
    vol = 0.0
    for f in md.f:
        p0 = md.v[f[0]]
        for k in range(1, len(f) - 1):
            p1, p2 = md.v[f[k]], md.v[f[k + 1]]
            vol += (p0[0] * (p1[1] * p2[2] - p1[2] * p2[1]) - p0[1] * (p1[0] * p2[2] - p1[2] * p2[0])
                    + p0[2] * (p1[0] * p2[1] - p1[1] * p2[0])) / 6.0
    assert vol > 0.0, "faces point inwards"
    return vol


def check_parts(parts):
    assert parts
    for name, mat, md, tile, smooth in parts:
        assert mat in kit.MAT_KEYS and mat in ALLOWED, (name, mat)
        assert tile > 0 and smooth in (0, 1, 2)
        check_mesh(md)


def corner_clearance(md):
    """Smallest distance from any bounding-box corner to a vertex (0 for a
    razor-sharp box)."""
    b = bounds(md)
    best = 1e9
    for cx in b[0]:
        for cy in b[1]:
            for cz in b[2]:
                for v in md.v:
                    best = min(best, math.sqrt((v[0] - cx) ** 2 + (v[1] - cy) ** 2 + (v[2] - cz) ** 2))
    return best


def part(parts, name):
    return [p for p in parts if p[0] == name][0][2]


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


def seg_dist(p, a, b):
    ax, az = b[0] - a[0], b[1] - a[1]
    ln2 = ax * ax + az * az
    t = max(0.0, min(1.0, ((p[0] - a[0]) * ax + (p[1] - a[1]) * az) / ln2)) if ln2 > 0 else 0.0
    return math.hypot(p[0] - a[0] - ax * t, p[1] - a[1] - az * t)


# ------------------------------------------------------------------ console
def test_console_dimensions_and_meshes():
    parts = fbc.console_parts()
    check_parts(parts)
    (x0, x1), (y0, y1), (z0, z1) = bounds([p[2] for p in parts])
    assert abs(x0 + 75.0) < 1e-6 and abs(x1 - 75.0) < 1e-6
    assert abs(y0 + 17.5) < 1e-6 and abs(y1 - 17.5) < 1e-6
    assert abs(z0) < 1e-6 and abs(z1 - 85.0) < 1e-6
    top, shelf = part(parts, "BenchConsole_Top"), part(parts, "BenchConsole_Shelf")
    tb, sb = bounds(top), bounds(shelf)
    assert abs(tb[2][1] - tb[2][0] - 1.0) < 1e-6 and abs(tb[2][1] - 85.0) < 1e-6      # 1 cm plate on top
    assert abs(sb[2][1] - sb[2][0] - 1.0) < 1e-6 and abs(sb[2][1] - 18.0) < 1e-6      # 1 cm shelf, top at 18
    assert sb[0][1] < 73.0 and sb[1][1] < 17.0                                          # between the legs
    assert corner_clearance(top) > 0.1 and corner_clearance(shelf) > 0.1                # rounded, not razor-sharp


def test_console_tubes_braces_welds():
    parts = fbc.console_parts()
    frame = part(parts, "BenchConsole_Frame")
    leg = [v for v in frame.v if v[0] > 70.0 and v[1] > 14.0 and 0.5 < v[2] < 1.0]    # full section ring
    assert leg
    assert abs(max(v[0] for v in leg) - min(v[0] for v in leg) - 2.0) < 1e-6            # 2 x 2 cm tube
    assert abs(max(v[1] for v in leg) - min(v[1] for v in leg) - 2.0) < 1e-6
    corner = min(math.hypot(74.5 - v[0], 17.0 - v[1]) for v in leg)
    assert 0.05 < corner < 0.2                                                         # 3 mm corner radius
    braces = part(parts, "BenchConsole_Brace")
    xs = sorted(abs(v[0]) for v in braces.v)
    assert 73.29 < xs[0] and xs[-1] < 73.71                                            # in the side frames
    assert any(v[0] > 0 for v in braces.v) and any(v[0] < 0 for v in braces.v)
    bb = bounds(braces)
    assert bb[1][0] > -17.0 and bb[1][1] < 17.0 and bb[2][0] > 16.0 and bb[2][1] < 84.0
    welds = part(parts, "BenchConsole_Weld")
    wb = bounds(welds)
    assert wb[2][0] > 16.0 and wb[2][1] < 84.0 and wb[1][0] > -17.0 and wb[1][1] < 17.0
    glides = part(parts, "BenchConsole_Glide")
    assert abs(bounds(glides)[2][0]) < 1e-6 and abs(bounds(glides)[2][1] - 0.4) < 1e-6


def test_console_other_size():
    parts = fbc.console_parts(L=120.0, D=30.0, H=75.0)
    check_parts(parts)
    (x0, x1), (y0, y1), (z0, z1) = bounds([p[2] for p in parts])
    assert abs(x1 - x0 - 120.0) < 1e-6 and abs(y1 - y0 - 30.0) < 1e-6 and abs(z1 - 75.0) < 1e-6


# -------------------------------------------------------------------- books
def test_single_book_anatomy():
    parts = fbc.book_parts(30.0, 23.0, 3.0, "linen")
    check_parts(parts)
    case, pages = parts[0][2], parts[1][2]
    cb, pb = bounds(case), bounds(pages)
    assert abs(cb[1][1] - cb[1][0] - 30.0) < 1e-6 and abs(cb[2][1] - 3.0) < 1e-6 and abs(cb[2][0]) < 1e-6
    for k in range(3):                                                                 # block inside the case
        assert cb[k][0] < pb[k][0] and pb[k][1] < cb[k][1]
    assert abs((cb[1][1] - cb[1][0]) - (pb[1][1] - pb[1][0]) - 0.6) < 1e-6              # 3 mm squares
    assert abs(cb[0][1] - pb[0][1] - 0.3) < 1e-6
    mid = [v for v in pages.v if abs(v[2] - 1.5) < 0.05 and v[0] > 0]
    assert max(v[0] for v in mid) < pb[0][1] - 0.2                                     # hollow fore-edge
    assert cb[0][0] < -11.5 - 0.3                                                      # rounded spine bulges out
    assert corner_clearance(case) > 0.03


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_book_stack(seed):
    parts = fbc.book_stack_parts(seed)
    check_parts(parts)
    cases = [p for p in parts if p[0].endswith("_Case")]
    pages = [p for p in parts if p[0].endswith("_Pages")]
    assert 3 <= len(cases) <= 4 and len(pages) == len(cases)
    covers = [p[1] for p in cases]
    assert set(covers) <= {"paper", "linen", "leather"} and len(set(covers)) == 3
    assert all(a != b for a, b in zip(covers, covers[1:]))
    assert {p[1] for p in pages} == {"bedding"}
    (x0, x1), (y0, y1), (z0, z1) = bounds([p[2] for p in parts])
    assert abs(z0) < 1e-6 and 6.0 < z1 < 14.0
    assert 24.0 < x1 - x0 < 38.0 and 18.0 < y1 - y0 < 31.0
    assert max(abs(x0), abs(x1)) < 20.0 and max(abs(y0), abs(y1)) < 16.0
    # books rest on each other: each case starts where the one below ends
    tops = [bounds(c[2])[2] for c in cases]
    for (a0, a1), (b0, b1) in zip(tops, tops[1:]):
        assert abs(b0 - a1) < 1e-6


def test_book_stack_deterministic_and_varied():
    a = fbc.book_stack_parts(2)
    b = fbc.book_stack_parts(2)
    assert [p[2].v for p in a] == [p[2].v for p in b]
    assert bounds([p[2] for p in fbc.book_stack_parts(0)]) != bounds([p[2] for p in fbc.book_stack_parts(1)])


# --------------------------------------------------------------------- jars
def test_jar_profile_walls():
    for R, Hj, _x, _y in fbc.JARS:
        prof = fbc._jar_profile(R, Hj)
        outer, inner = split_at_top(prof)
        for z in (3.0, 0.5 * Hj, Hj - 2.0):
            wall = r_at(outer, z) - r_at(inner[::-1], z)
            assert 0.3 <= wall <= 0.4                                                  # 3-4 mm
        under = max(z for r, z in outer if r < 1.0)
        floor = min(z for r, z in inner if r < 1.0)
        assert floor - under > 1.8 * wall                                              # thicker base
        lid = fbc._jar_lid_profile(R, Hj)
        plug = [r for r, z in lid if z < Hj]
        assert plug and max(plug) < R - fbc.JAR_WALL - 0.1                             # clears the mouth
        assert min(z for r, z in lid if r > R - fbc.JAR_WALL) > Hj                     # flange rests on the rim


def test_glass_jars():
    parts = fbc.glass_jar_parts()
    check_parts(parts)
    assert {p[1] for p in parts} == {"glass_solid"} and len(parts) == 4
    tops = sorted(bounds(p[2])[2][1] for p in parts if p[0].endswith("_Lid"))
    assert tops[1] - tops[0] > 5.0                                                     # two heights
    (x0, x1), (y0, y1), (z0, z1) = bounds([p[2] for p in parts])
    assert abs(z0) < 1e-6 and 22.0 < z1 < 26.0
    assert max(abs(x0), abs(x1)) < 13.5 and max(abs(y0), abs(y1)) < 8.0


# --------------------------------------------------------------------- lamp
def test_glass_lamp():
    parts = fbc.glass_lamp_parts()
    check_parts(parts)
    assert {p[1] for p in parts} == {"glass_solid", "metal_brass", "shade"}
    (x0, x1), (y0, y1), (z0, z1) = bounds([p[2] for p in parts])
    assert abs(z0) < 1e-6 and 44.0 < z1 < 45.5
    assert 25.0 < x1 - x0 < 28.0 and 25.0 < y1 - y0 < 28.0
    Rb, Hb = fbc.LAMP_BASE
    base = bounds(part(parts, "GlassLamp_Base"))
    assert Rb - 0.1 < base[0][1] <= Rb and abs(base[2][1] - Hb) < 1e-6
    stem = [v for v in part(parts, "GlassLamp_Brass").v
            if Hb + 0.76 < v[2] < 28.29 and math.hypot(v[0], v[1]) < 2.0]
    assert stem and max(math.hypot(v[0], v[1]) for v in stem) < 0.51                  # thin stem
    R, s0, s1 = fbc.LAMP_SHADE
    bulb = bounds(part(parts, "GlassLamp_Bulb"))
    assert bulb[2][0] > s0 and bulb[2][1] < s1 - 3.0 and bulb[0][1] < R - 5.0          # hidden in the shade
    sh = bounds(part(parts, "GlassLamp_Shade"))
    assert abs(sh[2][0] - s0) < 0.01 and abs(sh[2][1] - s1) < 0.01


def test_glass_lamp_cord():
    parts = fbc.glass_lamp_parts(cord_to_edge=13.5, cord_drop=85.0)
    check_parts(parts)
    cord = part(parts, "GlassLamp_Cord")
    cb = bounds(cord)
    assert abs(cb[2][0] + 85.0) < 1e-3 and 13.5 < cb[1][1] < 15.0                     # down to the floor
    lying = [v for v in cord.v if v[1] < 12.5]
    assert lying and min(v[2] for v in lying) > -1e-6                                  # on the surface, not in it
    floor = [v for v in cord.v if v[0] > 5.0]
    assert floor and max(v[2] for v in floor) < -84.3 and cb[0][1] < 25.0             # then along the floor
    with pytest.raises(ValueError):
        fbc.glass_lamp_parts(cord_to_edge=5.0)


# --------------------------------------------------------------- twig vase
@pytest.mark.parametrize("seed", [0, 1, 5])
def test_twig_vase(seed):
    parts = fbc.twig_vase_parts(seed)
    check_parts(parts)
    vb = bounds(part(parts, "TwigVase_Vase"))
    assert abs(vb[2][0]) < 1e-6 and abs(vb[2][1] - 15.0) < 0.01 and 8.5 < vb[0][1] - vb[0][0] < 9.5
    paths = fbc._twig_paths(seed)
    assert len(paths) >= 8
    main, rad = paths[0]
    assert len(main) == len(rad) and abs(rad[0] - 0.3) < 1e-9
    assert all(0.015 <= r <= 0.3 + 1e-9 for _p, rr in paths for r in rr)
    for (x, y, z), r in zip(main, rad):
        d = math.hypot(x, y)
        if 11.5 <= z <= 15.3:
            assert d + r < fbc.VASE_NECK_R - 0.15                                      # clears the neck
        elif z < 11.5:
            assert d + r < 3.2 and z - r > 1.0                                         # inside the belly
    tb = bounds(part(parts, "TwigVase_Twig"))
    assert 40.0 < tb[2][1] < 70.0 and tb[2][0] > 0.9
    for path, rr in paths[1:]:                                                         # shoots leave above the lip
        assert path[0][2] > 15.5


def test_vase_walls():
    outer, inner = split_at_top(fbc.vase_profile())
    for r, z in inner:
        if 1.5 < z < 14.5:
            gap = min(seg_dist((r, z), a, b) for a, b in zip(outer, outer[1:]))
            assert 0.35 < gap < 0.9                                                    # 3.5-9 mm stoneware
    assert min(r for r, z in inner if 12.0 < z < 15.0) >= fbc.VASE_NECK_R - 0.02


# ------------------------------------------------------------- the dressing
def test_dressing_fits_the_console():
    surfaces = {85.0: (75.0, 17.5), 18.0: (72.7, 16.9)}
    boxes = {}
    for key, px, py, pz, deg, kw in fbc.DRESSING:
        c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        foot = [v for name, mat, md, tile, sm in fbc.PIECES[key](**kw) if not name.endswith("_Cord")
                for v in md.v if v[2] < 2.0]
        xs = [px + v[0] * c - v[1] * s for v in foot]
        ys = [py + v[0] * s + v[1] * c for v in foot]
        hx, hy = surfaces[pz]
        assert -hx < min(xs) and max(xs) < hx and -hy < min(ys) and max(ys) < hy, key
        box = (min(xs), max(xs), min(ys), max(ys))
        for other in boxes.get(pz, []):
            assert box[1] < other[0] or other[1] < box[0] or box[3] < other[2] or other[3] < box[2], key
        boxes.setdefault(pz, []).append(box)
        if pz < 85.0:
            assert pz + bounds([p[2] for p in fbc.PIECES[key](**kw)])[2][1] < 84.0     # fits under the top


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
    for fn, gname, n in ((fbc.build_console, "BenchConsole", 6), (fbc.build_book_stack, "BookStack", None),
                         (fbc.build_glass_jars, "GlassJars", 4), (fbc.build_glass_lamp, "GlassLamp", 4),
                         (fbc.build_twig_vase, "TwigVase", 2)):
        name, nodes = fn()
        assert name == gname and nodes and (n is None or len(nodes) == n)
    assert all(mat in ALLOWED for _n, mat, _t, _m in kit.PARTS[start:])
    name, nodes = fbc.preview()
    assert name == "BenchConsole_Dressed" and len(nodes) == 1 + len(fbc.DRESSING)
    del kit.PARTS[start:]
