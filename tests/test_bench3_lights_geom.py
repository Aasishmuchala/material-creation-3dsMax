"""Off-Max geometry tests for tools/apartment/furn_bench3_lights.py.

pymxs is stubbed while the module is imported (and the previous entry put
back), so only the pure-Python cage generators run; the build_* wrappers are
exercised against a fake runtime. Every mesh must be a closed, consistently
wound solid facing outward, free of NaN, at real-world size.
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

_prev = sys.modules.get("pymxs")
sys.modules["pymxs"] = types.SimpleNamespace(runtime=types.SimpleNamespace())
try:
    import kit  # noqa: E402
    import furn_living  # noqa: E402
    import furn_bench3_lights as fb3  # noqa: E402
finally:
    if _prev is None:
        sys.modules.pop("pymxs", None)
    else:
        sys.modules["pymxs"] = _prev

ALLOWED = {"alabaster", "metal_steel", "paint_white", "wall_paint", "emissive_warm"}


# ------------------------------------------------------------------ helpers
def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def dist(a, b):
    return math.sqrt(dot(sub(a, b), sub(a, b)))


def bounds(mds):
    if not isinstance(mds, (list, tuple)):
        mds = [mds]
    vs = [v for md in mds for v in md.v]
    return [(min(v[k] for v in vs), max(v[k] for v in vs)) for k in range(3)]


def check_mesh(md, name=""):
    """Non-empty, finite, valid faces, every directed edge paired with its
    reverse exactly once (closed, consistently wound), positive volume."""
    assert md.v and md.f, "%s: empty" % name
    assert all(math.isfinite(c) for v in md.v for c in v), "%s: NaN / inf" % name
    nv = len(md.v)
    for f in md.f:
        assert len(f) >= 3 and len(set(f)) == len(f) and all(0 <= i < nv for i in f), (name, f)
    ec = Counter()
    for f in md.f:
        for i in range(len(f)):
            ec[(f[i], f[(i + 1) % len(f)])] += 1
    bad = [e for e, c in ec.items() if c != 1 or ec.get((e[1], e[0]), 0) != 1]
    assert not bad, "%s: %d open or doubled edges, e.g. %r" % (name, len(bad), bad[:3])
    vol = fb3._volume(md)
    assert vol > 0.0, "%s: faces point inwards" % name
    return vol


def check_parts(parts):
    assert parts
    names = [p[0] for p in parts]
    assert len(set(names)) == len(names)
    for name, mat, md, tile, smooth in parts:
        assert mat in kit.MAT_KEYS and mat in ALLOWED, (name, mat)
        assert (tile is None or tile > 0) and smooth in (0, 1)
        check_mesh(md, name)
    return {p[0]: p for p in parts}


def part(parts, name):
    return [p for p in parts if p[0] == name][0][2]


def face_normal(md, f):
    a = md.v[f[0]]
    n = [0.0, 0.0, 0.0]
    for k in range(1, len(f) - 1):
        u, w = sub(md.v[f[k]], a), sub(md.v[f[k + 1]], a)
        n[0] += u[1] * w[2] - u[2] * w[1]
        n[1] += u[2] * w[0] - u[0] * w[2]
        n[2] += u[0] * w[1] - u[1] * w[0]
    return n


def area2d(pts):
    return 0.5 * sum(p[0] * q[1] - q[0] * p[1] for p, q in zip(pts, pts[1:] + pts[:1]))


def turn_deg(a, p, c):
    d1, d2 = (p[0] - a[0], p[1] - a[1]), (c[0] - p[0], c[1] - p[1])
    l1, l2 = math.hypot(*d1), math.hypot(*d2)
    return math.degrees(math.acos(max(-1.0, min(1.0, (d1[0] * d2[0] + d1[1] * d2[1]) / (l1 * l2)))))


def torus_dev(v, spec):
    """Distance of v from the nominal (perfect) torus surface of a ring spec."""
    cx, cy, cz = spec["centre"]
    q = math.hypot(v[0] - cx, v[1] - cy) - spec["R"]
    return math.hypot(q, v[2] - cz) - spec["r"]


# ================================================================ pendant
def test_material_keys_registered():
    assert "alabaster" in kit.MAT_KEYS and "wall_paint" in kit.MAT_KEYS and "metal_steel" in kit.MAT_KEYS
    for parts in (fb3.pendant_parts(), fb3.coffer_parts()):
        for name, mat, _md, _t, _s in parts:
            assert mat in kit.MAT_KEYS and mat in ALLOWED, (name, mat)


def test_ring_specs_proportions():
    outer, inner = fb3.ring_specs(110.0)
    assert abs(2.0 * (outer["R"] + outer["r"]) - 150.0) < 1e-9 and abs(2.0 * outer["r"] - 12.0) < 1e-9
    assert abs(2.0 * (inner["R"] + inner["r"]) - 95.0) < 1e-9 and abs(2.0 * inner["r"] - 11.0) < 1e-9
    assert 11.0 <= 2.0 * inner["r"] <= 2.0 * outer["r"] <= 12.0
    assert abs(outer["centre"][2] + 110.0) < 1e-9                       # drop: ceiling to the outer centre line
    assert abs(inner["centre"][2] - outer["centre"][2] - 18.0) < 1e-9    # inner ring 18 cm higher
    off = math.hypot(inner["centre"][0] - outer["centre"][0], inner["centre"][1] - outer["centre"][1])
    assert 3.0 < off < 10.0                                              # slightly offset
    assert outer["centre"][:2] == (0.0, 0.0)                             # origin over the outer ring's centre
    for spec in (outer, inner):
        assert len(spec["az"]) == 4
        az = sorted(spec["az"])
        assert all(abs((b - a) - 90.0) < 1e-9 for a, b in zip(az, az[1:]))
    assert not set(outer["az"]) & set(inner["az"])                        # the two rings' cables interleave
    for bad in (fb3.DROP_MIN - 1.0, fb3.DROP_MAX + 1.0):
        with pytest.raises(ValueError):
            fb3.ring_specs(bad)


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_pendant_meshes(seed):
    parts = fb3.pendant_parts(110.0, seed)
    check_parts(parts)
    assert [p[0] for p in parts] == ["RingPendant_OuterRing", "RingPendant_InnerRing", "RingPendant_Canopies",
                                     "RingPendant_Grippers", "RingPendant_Cables"]
    (x0, x1), (y0, y1), (z0, z1) = bounds([p[2] for p in parts])
    assert z1 == 0.0                                                     # canopies on the ceiling, nothing above
    assert abs(z0 + 116.0) < 0.6                                         # drop + half the 12 cm section
    assert 149.0 < x1 - x0 < 151.0 and 149.0 < y1 - y0 < 151.0           # footprint 150 x 150
    assert max(abs(x0), abs(x1), abs(y0), abs(y1)) < 75.6
    outer, inner = fb3.ring_specs(110.0)
    for name, spec, sec in (("RingPendant_OuterRing", outer, 12.0), ("RingPendant_InnerRing", inner, 11.0)):
        (a0, a1), (b0, b1), (c0, c1) = bounds(part(parts, name))
        dia = 2.0 * (spec["R"] + spec["r"])
        assert abs((a1 - a0) - dia) < 1.0 and abs((b1 - b0) - dia) < 1.0
        assert abs((c1 - c0) - sec) < 0.8
        assert abs(0.5 * (c0 + c1) - spec["centre"][2]) < 0.4
    for name in ("RingPendant_OuterRing", "RingPendant_InnerRing"):  # own UVs, kept by the scene
        assert [p[3] for p in parts if p[0] == name] == [None]


@pytest.mark.parametrize("seed", [0, 3, 7])
def test_rings_are_hand_carved_tori(seed):
    parts = fb3.pendant_parts(110.0, seed)
    for name, spec in zip(("RingPendant_OuterRing", "RingPendant_InnerRing"), fb3.ring_specs(110.0)):
        md = part(parts, name)
        devs = [torus_dev(v, spec) for v in md.v]
        assert max(abs(d) for d in devs) < 0.6                           # a few mm, no more
        assert max(devs) - min(devs) > 0.3                                # but never a perfect torus
        assert abs(sum(devs) / len(devs)) < 0.05
        vol = 2.0 * math.pi ** 2 * spec["R"] * spec["r"] ** 2            # a solid torus, not a shell
        assert 0.97 * vol < fb3._volume(md) < 1.02 * vol


def test_ring_uvs_seamless():
    outer = fb3.ring_specs(110.0)[0]
    md = part(fb3.pendant_parts(110.0, 0), "RingPendant_OuterRing")
    assert len(md.fuv) == len(md.f) and all(u is not None and len(u) == len(f) for f, u in zip(md.f, md.fuv))
    us = [t[0] for uv in md.fuv for t in uv]
    vs = [t[1] for uv in md.fuv for t in uv]
    ru, rv = max(us), max(vs)
    assert min(us) == 0.0 and min(vs) == 0.0
    assert ru == int(ru) and rv == int(rv) and ru >= 6 and rv >= 1      # whole repeats: the map closes
    assert 0.85 < ru * fb3.ALABASTER / (2.0 * math.pi * outer["R"]) < 1.15
    assert 0.85 < rv * fb3.ALABASTER / (2.0 * math.pi * outer["r"]) < 1.25
    per_vert = {}
    for f, uv in zip(md.f, md.fuv):
        for i, t in zip(f, uv):
            per_vert.setdefault(i, set()).add((round(t[0], 9), round(t[1], 9)))
    cx, cy, cz = outer["centre"]
    for i, uvs in per_vert.items():
        if len(uvs) == 1:
            continue
        assert len(uvs) <= 4
        (u0, v0) = min(uvs)
        for (u1, v1) in uvs:                                              # seam copies differ by whole repeats
            assert abs((u1 - u0) - round(u1 - u0)) < 1e-9 and abs((v1 - v0) - round(v1 - v0)) < 1e-9
        v = md.v[i]                                                       # seams at the back or on the top
        assert (v[1] - cy > 60.0 and abs(v[0] - cx) < 0.5) or v[2] - cz > 0.8 * outer["r"]


def test_ring_lines_inside_the_rings():
    lines = fb3.ring_lines(110.0, 1)
    parts = fb3.pendant_parts(110.0, 1)
    assert len(lines) == 2
    for line, spec, name in zip(lines, fb3.ring_specs(110.0), ("RingPendant_OuterRing", "RingPendant_InnerRing")):
        assert len(line) == fb3.LINE_N
        assert all(len(p) == 3 and all(math.isfinite(c) for c in p) for p in line)
        assert dist(line[0], line[-1]) < 2.0 * math.pi * spec["R"] / fb3.LINE_N + 0.1   # a closed loop, not repeated
        cx, cy, cz = spec["centre"]
        for p in line:
            assert abs(math.hypot(p[0] - cx, p[1] - cy) - spec["R"]) < 0.5
            assert abs(p[2] - cz) < 0.3
        mean = tuple(sum(p[k] for p in line) / len(line) for k in range(3))
        assert dist(mean, spec["centre"]) < 0.3
        md = part(parts, name)
        ang = [math.atan2(v[1] - cy, v[0] - cx) for v in md.v]
        for p in line[::4]:                                               # the light has alabaster all round it
            a = math.atan2(p[1] - cy, p[0] - cx)
            near = [v for v, b in zip(md.v, ang) if abs((b - a + math.pi) % (2.0 * math.pi) - math.pi) < 0.05]
            dmin = min(dist(p, v) for v in near)
            assert spec["r"] - 0.5 < dmin < spec["r"] + 0.6
            assert dmin > 4.8


def test_rings_clear_each_other():
    lines = fb3.ring_lines(110.0, 0)
    outer, inner = fb3.ring_specs(110.0)
    gap = min(dist(p, q) for p in lines[0] for q in lines[1]) - outer["r"] - inner["r"] - 1.0
    assert gap > 12.0


def test_suspension():
    L = fb3.pendant_layout(110.0, 2)
    parts = fb3.pendant_parts(110.0, 2)
    cables, canopies, grippers = (part(parts, "RingPendant_%s" % n) for n in ("Cables", "Canopies", "Grippers"))
    assert len(L["cables"]) == 8 and [c["ring"] for c in L["cables"]].count(0) == 4
    lines = fb3.ring_lines(110.0, 2, n=360)
    for c in L["cables"]:
        x, y = c["xy"]
        spec, wob = L["rings"][c["ring"]]["spec"], L["rings"][c["ring"]]["wob"]
        th = math.radians(c["az"])
        assert abs(math.hypot(x - spec["centre"][0], y - spec["centre"][1]) - spec["R"]) < 1e-9
        own = [v for v in cables.v if math.hypot(v[0] - x, v[1] - y) < 0.5]
        assert own and all(math.hypot(v[0] - x, v[1] - y) <= fb3.CABLE_R + 1e-9 for v in own)  # plumb, 1.5 mm
        assert max(math.hypot(v[0] - x, v[1] - y) for v in own) > fb3.CABLE_R - 1e-9
        zb, zt = min(v[2] for v in own), max(v[2] for v in own)
        fb, ft = c["ferrule"]
        assert fb + 1.0 < zb < ft and c["tip"] < zt < -fb3.CANOPY_H        # into the ferrule and the nozzle
        assert abs((c["surface_z"] - fb) - fb3.FERRULE_SINK) < 1e-9
        top = fb3.ring_point(spec, wob, th, 0.5 * math.pi)                # ferrule seated on the ring's crest
        assert abs(c["surface_z"] - top[2]) < 0.05 and math.hypot(top[0] - x, top[1] - y) < 0.5
        base = (x, y, fb)                                                 # its base buried in the alabaster
        core = fb3.ring_point(spec, wob, th)
        assert dist(base, core) < fb3.section_radius(spec, wob, th, 0.5 * math.pi) - 0.3
        can = [v for v in canopies.v if math.hypot(v[0] - x, v[1] - y) < 3.0]
        assert can and max(v[2] for v in can) == 0.0 and abs(min(v[2] for v in can) + fb3.CANOPY_H) < 1e-9
        assert abs(max(math.hypot(v[0] - x, v[1] - y) for v in can) - fb3.CANOPY_R) < 0.01   # 5.2 cm across
        grip = [v for v in grippers.v if math.hypot(v[0] - x, v[1] - y) < 1.0]
        assert min(v[2] for v in grip) == fb and max(v[2] for v in grip) == -fb3.CANOPY_H + 0.1
        other = lines[1 - c["ring"]]                                      # well clear of the other ring
        o_spec = L["rings"][1 - c["ring"]]["spec"]
        for q in other:
            zc = min(max(q[2], zb), zt)
            assert dist(q, (x, y, zc)) - o_spec["r"] - 0.5 > 8.0
    assert check_mesh(cables) < 8 * math.pi * fb3.CABLE_R ** 2 * 110.0


def test_drop_moves_only_what_hangs():
    a, b = fb3.pendant_parts(60.0, 0), fb3.pendant_parts(160.0, 0)
    for (na, _m, ma, _t, _s), (nb, _m2, mb, _t2, _s2) in zip(a, b):
        assert na == nb and len(ma.v) == len(mb.v)
        if na == "RingPendant_Canopies":
            assert ma.v == mb.v
        elif "Ring" in na.split("_")[1]:
            assert all(abs(p[0] - q[0]) < 1e-9 and abs(p[1] - q[1]) < 1e-9 and abs(p[2] - q[2] - 100.0) < 1e-9
                       for p, q in zip(ma.v, mb.v))
    for drop in (fb3.DROP_MIN, 110.0, fb3.DROP_MAX):
        outer, inner = fb3.ring_lines(drop, 0)
        assert abs(sum(p[2] for p in outer) / len(outer) + drop) < 0.1
        hi = max(bounds(p[2])[2][1] for p in fb3.pendant_parts(drop, 0) if p[1] == "alabaster")
        assert hi < -15.0                                                 # rings well below the ceiling


def test_seed_varies_carving_not_layout():
    a, b, c = fb3.pendant_parts(110.0, 4), fb3.pendant_parts(110.0, 4), fb3.pendant_parts(110.0, 5)
    assert [p[2].v for p in a] == [p[2].v for p in b]
    assert part(a, "RingPendant_OuterRing").v != part(c, "RingPendant_OuterRing").v
    assert part(a, "RingPendant_InnerRing").v != part(c, "RingPendant_InnerRing").v
    assert part(a, "RingPendant_Canopies").v == part(c, "RingPendant_Canopies").v
    la, lc = fb3.pendant_layout(110.0, 4), fb3.pendant_layout(110.0, 5)
    assert [x["xy"] for x in la["cables"]] == [x["xy"] for x in lc["cables"]]
    assert fb3.ring_lines(110.0, 4) != fb3.ring_lines(110.0, 5)


def test_fitting_profiles_are_rounded():
    for prof in (fb3.canopy_profile(), fb3.nozzle_profile(), fb3.ferrule_profile(-100.0)):
        assert prof[0][0] == 0.0 and prof[-1][0] == 0.0                   # axis to axis: a closed solid
        assert all(r >= 0.0 for r, z in prof)
    can = fb3.canopy_profile()
    assert max(z for r, z in can) == 0.0 and min(z for r, z in can) == -fb3.CANOPY_H
    eased = [p for p in can if p[1] < -fb3.CANOPY_H + 0.4 and p[0] > fb3.CANOPY_R - 0.6]
    assert len(eased) >= 4                                                # a real 4 mm round, not a corner


# ================================================================ coffer
def test_coffer_meshes():
    parts = fb3.coffer_parts()
    check_parts(parts)
    assert [p[0] for p in parts] == ["Coffer_Plaster", "Coffer_LEDChannel", "Coffer_LED"]
    assert [p[1] for p in parts] == ["wall_paint", "metal_steel", "emissive_warm"]
    d = fb3.coffer_dims()
    (x0, x1), (y0, y1), (z0, z1) = bounds(part(parts, "Coffer_Plaster"))
    assert abs(x1 - 227.0) < 1e-6 and abs(x0 + 227.0) < 1e-6
    assert abs(y1 - 167.0) < 1e-6 and abs(y0 + 167.0) < 1e-6
    assert z0 == 0.0 and abs(z1 - 20.5) < 1e-9                            # rises into the ceiling only
    assert abs(d["s_out"] - 17.0) < 1e-9 and abs(d["top"] - 20.5) < 1e-9
    vol = fb3._volume(part(parts, "Coffer_Plaster"))
    assert 4.0e5 < vol < 7.0e5                                            # a real plaster solid, about 0.5 m3


def test_coffer_outline_is_the_slab_edge():
    outline = fb3.coffer_outline()
    d = fb3.coffer_dims()
    assert len(outline) == fb3.CF_N and area2d(outline) > 0.0              # counter-clockwise
    xs, ys = [p[0] for p in outline], [p[1] for p in outline]
    assert abs(max(xs) - min(xs) - 454.0) < 0.01 and abs(max(ys) - min(ys) - 334.0) < 0.01
    plaster = part(fb3.coffer_parts(), "Coffer_Plaster")
    at_plane = {(round(v[0], 6), round(v[1], 6)) for v in plaster.v if v[2] == 0.0}
    assert all((round(x, 6), round(y, 6)) in at_plane for x, y in outline)   # the cage's own outer corners
    for x, y in outline:
        assert abs(fb3.ellipse_offset(x, y, d["A"], d["B"]) - d["s_out"]) < 1e-6
    for md in (p[2] for p in fb3.coffer_parts()):                         # nothing reaches past the outline
        assert max(fb3.ellipse_offset(v[0], v[1], d["A"], d["B"]) for v in md.v) < d["s_out"] + 1e-6
    assert fb3.coffer_outline(depth=30.0) == outline                      # depth does not move the slab edge
    assert fb3.build_ceiling_coffer.__defaults__ == (420.0, 300.0, 18.0, 0.0)
    assert fb3.build_ring_pendant.__defaults__ == (110.0, 0)


def test_coffer_section_is_filleted():
    sec = fb3.coffer_section()
    d = fb3.coffer_dims()
    assert sec[0] == (d["s_r"], d["top"]) and sec[-1] == (d["s_r"], d["depth"])
    assert all(math.hypot(q[0] - p[0], q[1] - p[1]) > 1e-4 for p, q in zip(sec, sec[1:]))
    buried = {(d["s_out"], d["top"]), (d["s_out"], 0.0)}                  # against the slab: may be square
    for a, p, c in zip(sec, sec[1:], sec[2:]):
        if p not in buried:
            assert turn_deg(a, p, c) < 16.0, p
    band = [s for s, h in sec if h == 0.0]
    assert min(band) == pytest.approx(fb3.CF_NOSE)                        # 3 cm bullnose into the lip
    lip = [(s, h) for s, h in sec if abs(s) < 1e-9]
    assert min(h for s, h in lip) == pytest.approx(fb3.CF_NOSE)
    assert max(h for s, h in lip) == pytest.approx(fb3.CF_LIP_H - fb3.CF_LIP_R)
    assert max(h for s, h in sec if s <= fb3.CF_LIP_T + 1e-9 and h < d["hc"] + 5.0) == pytest.approx(fb3.CF_LIP_H)
    i0 = sec.index((d["s_back"], d["hc"]))                                # foot of the cove on the back wall
    wall, cove = sec[i0 - 1], sec[i0:]
    assert wall[0] == d["s_back"] and wall[1] < d["hc"]                   # a straight upright wall below it
    assert turn_deg(wall, cove[0], cove[1]) < 5.0                         # the cove leaves it upright
    assert abs(math.degrees(math.atan2(cove[-1][1] - cove[-2][1], cove[-2][0] - cove[-1][0]))) < 2.0  # lands flat
    assert all(q[0] < p[0] and q[1] > p[1] for p, q in zip(cove, cove[1:]))   # sweeps up and in all the way
    for s in (0.0, fb3.CF_LIP_T):                                         # the cove clears the lip
        assert fb3.cove_height(d, s) > fb3.CF_LIP_H + fb3.CF_CLEAR
    hs = [h for s, h in sec]
    assert min(hs) == 0.0 and max(hs) == d["top"]


def test_coffer_opening_and_recess_floor():
    d = fb3.coffer_dims()
    plaster = part(fb3.coffer_parts(), "Coffer_Plaster")
    offs = [fb3.ellipse_offset(v[0], v[1], d["A"], d["B"]) for v in plaster.v]
    face = [v for v, s in zip(plaster.v, offs)
            if abs(s) < 1e-6 and fb3.CF_NOSE - 0.01 < v[2] < fb3.CF_LIP_H - fb3.CF_LIP_R + 0.01]
    assert len(face) == 2 * fb3.CF_N                                       # the lip face: the a x b opening
    assert all(abs((v[0] / d["A"]) ** 2 + (v[1] / d["B"]) ** 2 - 1.0) < 1e-9 for v in face)
    assert sorted({round(v[2], 6) for v in face}) == [fb3.CF_NOSE, fb3.CF_LIP_H - fb3.CF_LIP_R]
    floor = [v for v, s in zip(plaster.v, offs) if s < d["s_r"] - 0.5 and v[2] < d["top"] - 0.1]
    assert len(floor) == 4 * fb3.CF_N + 1 and all(v[2] == d["depth"] for v in floor)
    down = 0
    for f in plaster.f:
        if all(plaster.v[i][2] == d["depth"] for i in f):
            n = face_normal(plaster, f)
            assert n[2] < 0.0 and abs(n[0]) + abs(n[1]) < 1e-6 * abs(n[2]) + 1e-9   # faces the room
            down += 1
    assert down == 5 * fb3.CF_N                                            # 4 quad rings and the centre fan
    assert min(v[2] for v, s in zip(plaster.v, offs) if s < -0.5) >= fb3.CF_LIP_H + fb3.CF_CLEAR - 1e-9


def test_led_is_hidden_in_the_trough():
    d = fb3.coffer_dims()
    parts = fb3.coffer_parts()
    for name in ("Coffer_LEDChannel", "Coffer_LED"):
        md = part(parts, name)
        offs = [fb3.ellipse_offset(v[0], v[1], d["A"], d["B"]) for v in md.v]
        assert min(offs) > fb3.CF_LIP_T + fb3.CF_INNER_R + 0.3               # behind the lip, on the flat floor
        assert max(offs) < d["s_back"] - fb3.CF_INNER_R - 0.3                 # clear of the back wall
        zs = [v[2] for v in md.v]
        assert min(zs) >= fb3.CF_BOARD - 0.06                                 # on the trough floor (0.5 mm in)
        assert max(zs) < fb3.CF_LIP_H - 3.0                                   # well under the lip top
    led = part(parts, "Coffer_LED")
    assert abs(max(v[2] for v in led.v) - (fb3.CF_BOARD + fb3.LED_TOP)) < 1e-9
    chan = part(parts, "Coffer_LEDChannel")
    assert max(v[2] for v in led.v) > max(v[2] for v in chan.v)              # dome just proud of the lips
    # sight lines in the section: from eyes anywhere in the room below the
    # ceiling, every line to the diffuser runs into plaster (the section's
    # solid: band, bullnose, lip, trough floor) or into the main slab beyond
    # the outline - none reaches it through the air over the lip
    sec = fb3.coffer_section()
    edges = list(zip(sec, sec[1:] + sec[:1]))

    def cross(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])

    def hits(p, q):
        for a, b in edges:
            d1, d2 = cross(a, b, p), cross(a, b, q)
            d3, d4 = cross(p, q, a), cross(p, q, b)
            if ((d1 > 0) != (d2 > 0) or d1 == 0 or d2 == 0) and ((d3 > 0) != (d4 > 0) or d3 == 0 or d4 == 0):
                return True
        return False

    targets = [(fb3.LED_S + w, fb3.CF_BOARD + z) for w, z in fb3.led_diffuser_section()]
    seen = 0
    for es in range(-500, 501, 20):
        for eh in (-30.0, -120.0, -200.0):
            for ts, th in targets:
                s0 = es + (ts - es) * (-eh / (th - eh))                      # where the line meets the ceiling
                if s0 >= d["s_out"]:
                    continue                                                  # under the main slab
                assert hits((es, eh), (ts, th)), (es, eh, ts, th)
                seen += 1
    assert seen > 500
    assert not hits((-200.0, -150.0), (5.0, 13.0))                       # the test does see the lit cove over it


def test_coffer_led_line():
    d = fb3.coffer_dims()
    line = fb3.coffer_led_line()
    assert len(line) == 120
    led = part(fb3.coffer_parts(), "Coffer_LED")
    tops = {(round(v[0], 6), round(v[1], 6), round(v[2], 6)) for v in led.v}
    for p in line:
        assert abs(fb3.ellipse_offset(p[0], p[1], d["A"], d["B"]) - fb3.LED_S) < 1e-6
        assert (round(p[0], 6), round(p[1], 6), round(p[2], 6)) in tops   # on the diffuser's crown
    assert all(abs(p[2] - (fb3.CF_BOARD + fb3.LED_TOP)) < 1e-12 for p in line)
    assert area2d([(p[0], p[1]) for p in line]) > 0.0


def test_coffer_parameters():
    for kw in ({"depth": fb3.DEPTH_MIN - 0.1}, {"depth": fb3.DEPTH_MAX + 0.1}, {"a": 110.0}, {"b": 100.0},
               {"a": 600.0, "b": 150.0}):
        with pytest.raises(ValueError):
            fb3.coffer_parts(**kw)
    deep = fb3.coffer_parts(depth=30.0)
    check_parts(deep)
    d = fb3.coffer_dims(depth=30.0)
    assert d["ra"] > 30.0 and abs(bounds(part(deep, "Coffer_Plaster"))[2][1] - 32.5) < 1e-9
    small = fb3.coffer_parts(260.0, 200.0, 14.0)
    check_parts(small)
    x0, x1 = bounds(part(small, "Coffer_Plaster"))[0]
    assert abs(x1 - x0 - 294.0) < 1e-6
    base, low = fb3.coffer_parts(), fb3.coffer_parts(ceiling_z=-18.0)   # hung from its recess floor instead
    for (n0, _k0, m0, _t0, _s0), (n1, _k1, m1, _t1, _s1) in zip(base, low):
        assert n0 == n1 and len(m0.v) == len(m1.v)
        assert all(p[0] == q[0] and p[1] == q[1] and abs(p[2] - 18.0 - q[2]) < 1e-9 for p, q in zip(m0.v, m1.v))
    assert abs(bounds(part(low, "Coffer_Plaster"))[2][0] + 18.0) < 1e-9


def test_ellipse_offset():
    A, B = 210.0, 150.0
    for t in [k * 0.37 for k in range(18)]:
        x, y = A * math.cos(t), B * math.sin(t)
        nx, ny = B * math.cos(t), A * math.sin(t)
        ln = math.hypot(nx, ny)
        for s in (-30.0, -1.0, 0.0, 2.5, 17.0, 60.0):
            assert abs(fb3.ellipse_offset(x + s * nx / ln, y + s * ny / ln, A, B) - s) < 1e-6
    assert fb3.ellipse_offset(0.0, 0.0, A, B) == -B


# ================================================================ wrappers
class _Node(object):
    def __init__(self, name=""):
        self.name, self.parent, self.pos = name, None, None


class _FakeRT(object):
    """Just enough pymxs for _build / kit.part / kit.soften / kit.group / kit.place."""

    def __init__(self):
        self.scripts, self.mods = [], []

    def execute(self, s):
        self.scripts.append(s)
        return _Node(s.split('name:"', 1)[1].split('"', 1)[0])

    def Smooth(self):
        return types.SimpleNamespace(kind="Smooth")

    def TurboSmooth(self):
        return types.SimpleNamespace(kind="TurboSmooth", iterations=None)

    def addModifier(self, node, mod):
        self.mods.append((node.name, mod))

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
    for mod in (kit, furn_living, fb3):
        monkeypatch.setattr(mod, "rt", fake)
    monkeypatch.setattr(kit, "PARTS", [])
    group, lines = fb3.build_ring_pendant(drop=100.0, seed=3)
    assert group.name == "RingPendant" and lines == fb3.ring_lines(100.0, 3)
    coffer, outline = fb3.build_ceiling_coffer()
    assert coffer.name == "CeilingCoffer" and outline == fb3.coffer_outline()
    reg = {n.name: (k, t, m) for n, k, t, m in kit.PARTS}
    assert len(kit.PARTS) == 5 + 3 and len(reg) == 8
    assert reg["RingPendant_OuterRing"] == ("alabaster", None, None)      # own UVs kept
    assert reg["RingPendant_InnerRing"] == ("alabaster", None, None)
    assert all(t > 0 and m == 4 for name, (k, t, m) in reg.items() if "Ring" not in name.split("_")[1])
    assert {k for k, t, m in reg.values()} <= ALLOWED
    assert all(n.parent is not None for n, k, t, m in kit.PARTS)
    for s in fake.scripts:
        name = s.split('name:"', 1)[1].split('"', 1)[0]
        assert "convertToPoly" in s
        assert ("setTVert" in s) == name.endswith("Ring")                 # only the rings carry UVs
    smooth = Counter(n for n, m in fake.mods if m.kind == "Smooth")
    turbo = {n: m.iterations for n, m in fake.mods if m.kind == "TurboSmooth"}
    assert set(smooth) == set(reg) - {"RingPendant_OuterRing", "RingPendant_InnerRing"}
    assert turbo == {"RingPendant_Canopies": 1, "RingPendant_Grippers": 1}
    fb3.preview()
