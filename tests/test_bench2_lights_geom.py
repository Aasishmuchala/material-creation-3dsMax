"""Off-Max geometry tests for tools/apartment/furn_bench2_lights.py.

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
    import furn_bench2_lights as fbl  # noqa: E402
finally:
    if _prev is None:
        sys.modules.pop("pymxs", None)
    else:
        sys.modules["pymxs"] = _prev

ALLOWED = {"metal_black", "metal_steel", "glass_solid", "emissive_warm"}
R_MAX = fbl.GLOBE_R * 1.015


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


def check_mesh(md, closed=True):
    """Non-empty, finite, valid faces; closed meshes: every directed edge
    paired with its reverse exactly once and a positive enclosed volume."""
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
    vol = fbl._volume(md)
    assert vol > 0.0, "faces point inwards"
    return vol


def check_parts(parts):
    assert parts
    for name, mat, md, tile, smooth in parts:
        assert mat in kit.MAT_KEYS and mat in ALLOWED, (name, mat)
        assert tile > 0 and smooth in (0, 1)
        check_mesh(md)


def part(parts, name):
    return [p for p in parts if p[0] == name][0][2]


def seg_dist(p, a, b):
    ax, az = b[0] - a[0], b[1] - a[1]
    ln2 = ax * ax + az * az
    t = max(0.0, min(1.0, ((p[0] - a[0]) * ax + (p[1] - a[1]) * az) / ln2)) if ln2 > 0 else 0.0
    return math.hypot(p[0] - a[0] - ax * t, p[1] - a[1] - az * t)


def r_at(chain, w):
    """Radius where an (r, w) chain crosses height w (largest crossing)."""
    out = []
    for (r0, w0), (r1, w1) in zip(chain, chain[1:]):
        if min(w0, w1) <= w <= max(w0, w1) and w0 != w1:
            out.append(r0 + (r1 - r0) * (w - w0) / (w1 - w0))
    assert out, "no crossing at w=%s" % w
    return max(out)


# ------------------------------------------------------------------ layout
def test_material_keys_registered():
    for parts in (fbl.chandelier_parts(), fbl.track_spot_parts()):
        for name, mat, _md, _t, _s in parts:
            assert mat in kit.MAT_KEYS and mat in ALLOWED, (name, mat)


def test_layout_composition():
    L = fbl.chandelier_layout(80.0)
    arms = L["arms"]
    assert len(arms) == 6 and len(L["hubs"]) == 2
    assert abs(L["hubs"][0][2] - L["hubs"][1][2] - fbl.TIER) < 1e-9
    for tier in (0, 1):                                    # three arms per tier, three directions
        firsts = [a["corners"][1] for a in arms if a["tier"] == tier]
        assert len(firsts) == 3
        dirs = {tuple(int(math.copysign(1, c)) if abs(c) > 1e-9 else 0 for c in sub(p, L["hubs"][tier]))
                for p in firsts}
        assert len(dirs) == 3
    sockets = set()
    for a in arms:                                         # runs axis-aligned, at right angles
        cs = a["corners"]
        runs = [sub(q, p) for p, q in zip(cs, cs[1:])]
        for v in runs:
            assert sorted(abs(c) > 1e-9 for c in v) == [False, False, True]
        for v0, v1 in zip(runs, runs[1:]):
            assert abs(dot(v0, v1)) < 1e-9
        assert abs(runs[0][2]) < 1e-9                      # leaves its hub horizontally
        sockets.add("up" if a["dir"][2] > 0.5 else "down" if a["dir"][2] < -0.5 else "side")
    assert sockets == {"up", "down", "side"}
    lengths = [sum(ln for _n, ln in a["runs"]) for a in arms]
    assert len(set(lengths)) == 6 and 20.0 < min(lengths) and max(lengths) < 50.0
    g = [a["globe"] for a in arms]
    R = fbl.GLOBE_R
    span_x = max(p[0] for p in g) - min(p[0] for p in g) + 2 * R
    span_y = max(p[1] for p in g) - min(p[1] for p in g) + 2 * R
    assert 104.0 < span_x < 116.0 and 54.0 < span_y < 66.0  # about 110 x 60
    cx, cy = sum(p[0] for p in g) / 6.0, sum(p[1] for p in g) / 6.0
    assert math.hypot(cx, cy) < 1.5                        # balanced on the drop rod
    for a in arms:                                         # bulb and globe on the socket axis
        for key, w in (("bulb", fbl.BULB_W), ("globe", fbl.globe_centre_w())):
            exp = tuple(a["lip"][k] + a["dir"][k] * w for k in range(3))
            assert dist(a[key], exp) < 1e-9
    assert fbl.bulb_positions(80.0) == [a["bulb"] for a in arms]


def test_globes_clear_each_other_and_the_ceiling():
    for drop in (fbl.DROP_MIN, 80.0):
        g = [a["globe"] for a in fbl.chandelier_layout(drop)["arms"]]
        for i in range(6):
            assert g[i][2] + R_MAX < -4.0                  # below the ceiling
            for j in range(i + 1, 6):
                assert dist(g[i], g[j]) > 2 * R_MAX + 4.0
    with pytest.raises(ValueError):
        fbl.chandelier_layout(fbl.DROP_MIN - 1.0)
    with pytest.raises(ValueError):
        fbl.chandelier_layout(fbl.DROP_MAX + 1.0)


# ------------------------------------------------------------------ meshes
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_chandelier_meshes(seed):
    parts = fbl.chandelier_parts(80.0, seed)
    check_parts(parts)
    names = [p[0] for p in parts]
    assert len(set(names)) == len(names)
    assert len([n for n in names if n.startswith("Chandelier_Globe")]) == 6
    (x0, x1), (y0, y1), (z0, z1) = bounds([p[2] for p in parts])
    assert abs(z1) < 1e-9                                  # canopy against the ceiling
    assert 104.0 < x1 - x0 < 116.0 and 54.0 < y1 - y0 < 66.0
    L = fbl.chandelier_layout(80.0)
    assert abs(z0 - min(a["globe"][2] for a in L["arms"]) + fbl.GLOBE_R) < 0.8
    cb = bounds(part(parts, "Chandelier_Canopy"))
    assert abs(cb[0][1] - fbl.CANOPY_R) < 0.02 and abs(cb[2][0] + fbl.CANOPY_H + fbl.COLLAR_H) < 1e-9
    frame = part(parts, "Chandelier_Frame")
    hub_top = L["hubs"][0][2] + 0.5 * fbl.HUB_H            # drop rod: 1.2 cm round
    ring = [v for v in frame.v if hub_top + 0.05 < v[2] < L["z_collar"] + 0.45 and math.hypot(v[0], v[1]) < 1.0]
    assert len(ring) >= 12 and all(abs(math.hypot(v[0], v[1]) - fbl.ROD_R) < 1e-6 for v in ring)
    assert abs(bounds(frame)[2][0] - L["finial_tip"][2]) < 1e-9


def test_globe_profile_wall_and_neck():
    prof = fbl.globe_profile()
    c = fbl.globe_centre_w()
    away = [p for p in prof if p[1] > c - 8.0]
    assert len(away) > 40
    for r, w in away:                                      # a hollow sphere, 2.5 mm wall
        d = math.hypot(r, w - c)
        assert abs(d - fbl.GLOBE_R) < 1e-6 or abs(d - fbl.GLOBE_R + fbl.GLOBE_WALL) < 1e-6
    neck = [p for p in prof if p[1] < fbl.NECK_TOP - 0.7]
    assert min(r for r, w in neck) >= fbl.NECK_RI - 1e-9 and max(r for r, w in neck) <= fbl.NECK_RO + 1e-9
    assert abs(min(w for r, w in prof) - fbl.NECK_RIM) < 1e-9
    rim = [p for p in prof if p[1] < fbl.NECK_RIM + 0.05]  # fire-polished, not square
    assert len(rim) >= 4
    i = max(range(len(prof)), key=lambda k: prof[k][1])
    outer, inner = prof[:i + 1], prof[i + 1:]
    for r, w in inner:                                     # wall everywhere 2.4-4 mm (thicker at the fillet)
        if w > fbl.NECK_RIM + 0.2:
            gap = min(seg_dist((r, w), a, b) for a, b in zip(outer, outer[1:]))
            assert 0.24 < gap < 0.4
    assert 2.0 * fbl.NECK_RI > 2.0 * fbl.BULB_R + 1.0      # the bulb goes in through the neck


def test_globe_meshes_are_hollow_spheres():
    parts = fbl.chandelier_parts(80.0, 0)
    L = fbl.chandelier_layout(80.0)
    shell = 4.0 * math.pi * fbl.GLOBE_R ** 2 * fbl.GLOBE_WALL
    for k, arm in enumerate(L["arms"]):
        md = part(parts, "Chandelier_Globe%d" % (k + 1))
        vol = fbl._volume(md)
        assert 0.85 * shell < vol < 1.1 * shell            # glass, not a solid ball (4190 cm3)
        ds = [dist(v, arm["globe"]) for v in md.v]
        ws = [dot(sub(v, arm["globe"]), arm["dir"]) for v in md.v]
        assert max(d for d, w in zip(ds, ws) if w > -8.0) < R_MAX + 0.5      # the sphere
        assert min(d for d, w in zip(ds, ws) if w > 0.0) > fbl.GLOBE_R * 0.985 - fbl.GLOBE_WALL - 0.5
        rim = sub(arm["lip"], arm["globe"])                                    # the neck reaches into the cup
        assert min(ws) < dot(rim, arm["dir"]) - 1.0


def test_cup_and_bulb_fit_the_globe():
    cup = fbl.cup_profile()
    i = max(range(len(cup)), key=lambda k: cup[k][1])
    assert abs(cup[i][1]) < 1e-9                           # the lip is at w = 0
    assert fbl.CUP_RO - fbl.CUP_RI > 0.2                   # real wall
    assert fbl.NECK_RO + 0.08 < fbl.CUP_RI                 # neck clears the cup (globe tilt included)
    assert fbl.CUP_FLOOR + 0.5 < fbl.NECK_RIM < 0.0        # neck held inside the cup
    assert 1.25 < fbl.NECK_RI - 0.5                        # lampholder clears the neck
    bulb = fbl.bulb_profile()
    j = max(range(len(bulb)), key=lambda k: bulb[k][1])
    b_out, b_in = bulb[:j + 1], bulb[j + 1:]
    assert abs(max(r for r, w in bulb) - fbl.BULB_R) < 1e-9
    assert all(r < fbl.NECK_RI - 0.5 for r, w in bulb)     # passes through the neck
    tip = max(w for r, w in bulb)
    assert tip < fbl.globe_centre_w() + fbl.GLOBE_R - fbl.GLOBE_WALL - 5.0
    for w in (1.5, 4.0, 6.5):                              # 0.7 mm envelope wall
        assert abs(r_at(b_out, w) - r_at(b_in[::-1], w) - fbl.BULB_WALL) < 1e-6
    glass, metal, coil = fbl.bulb_md(0.7)
    for md in (glass, metal, coil):
        check_mesh(md)
    ri = fbl.BULB_R - fbl.BULB_WALL
    for v in coil.v + [v for v in metal.v if v[2] > 0.2]:  # filament and leads inside the envelope
        assert math.hypot(v[0], v[1]) < ri - 0.2 and v[2] < tip - 1.0
    cw = [v[2] for v in coil.v]
    assert abs(0.5 * (min(cw) + max(cw)) - fbl.BULB_W) < 0.1
    sock = fbl.socket_md(0.3)
    check_mesh(sock)
    screws = [v for v in sock.v if math.hypot(v[0], v[1]) > fbl.CUP_RO + 0.1]
    assert len(screws) > 30 and max(math.hypot(v[0], v[1]) for v in screws) < fbl.CUP_RO + 0.9
    tips = min(math.hypot(v[0], v[1]) for v in sock.v
               if abs(v[2] - fbl.SCREW_W) < 0.2 and math.hypot(v[0], v[1]) > fbl.NECK_RO - 0.1)
    assert fbl.NECK_RO < tips < fbl.NECK_RO + 0.05         # thumbscrews nip the neck


def test_bulb_positions_inside_globes():
    parts = fbl.chandelier_parts(80.0, 1)
    L = fbl.chandelier_layout(80.0)
    coil = part(parts, "Chandelier_Filament")
    for arm, b in zip(L["arms"], fbl.bulb_positions(80.0)):
        near = [v for v in coil.v if dist(v, b) < 3.0]
        assert near
        cen = tuple(sum(v[k] for v in near) / len(near) for k in range(3))
        assert dist(cen, b) < 0.15                         # the light sits in the filament
        assert dist(b, arm["globe"]) < fbl.GLOBE_R - 2.5
        assert all(dist(v, arm["globe"]) < fbl.GLOBE_R * 0.985 - fbl.GLOBE_WALL - 0.8 for v in near)


@pytest.mark.parametrize("seed", [0, 5])
def test_frame_and_cups_clear_the_globes(seed):
    parts = fbl.chandelier_parts(80.0, seed)
    L = fbl.chandelier_layout(80.0)
    frame = part(parts, "Chandelier_Frame")
    canopy = part(parts, "Chandelier_Canopy")
    sockets = part(parts, "Chandelier_Sockets")
    for arm in L["arms"]:
        g = arm["globe"]
        assert min(dist(v, g) for v in frame.v + canopy.v) > R_MAX + 1.5
        for v in sockets.v:
            if dist(v, g) < R_MAX + 1.0:                   # only its own cup comes close
                assert dist(v, arm["lip"]) < 3.6
    for k in range(6):                                     # globes of different arms never meet
        a = part(parts, "Chandelier_Globe%d" % (k + 1))
        for j in range(k + 1, 6):
            gj = L["arms"][j]["globe"]
            assert min(dist(v, gj) for v in a.v) > R_MAX + 3.0


def test_rods_have_soft_ends():
    md = fbl._rod_md([(0.0, 0.0, 0.0), (10.0, 0.0, 0.0)], 0.6)
    check_mesh(md)
    (x0, x1), _yb, _zb = bounds(md)
    assert -0.6 < x0 < -0.55 and 10.55 < x1 < 10.6
    for v in md.v:                                         # domed: narrows towards the tips
        if v[0] < -0.5 or v[0] > 10.5:
            assert math.hypot(v[1], v[2]) < 0.35
    path = fbl.arm_path(fbl.chandelier_layout()["arms"][5])
    for a, b in zip(path, path[1:]):                       # bent, no kinks or doubled points
        assert dist(a, b) > 0.05
    for a, b, c in zip(path, path[1:], path[2:]):
        u, w = sub(b, a), sub(c, b)
        assert dot(u, w) / math.sqrt(dot(u, u) * dot(w, w)) > math.cos(math.radians(16.0))


def test_drop_moves_only_what_hangs():
    a, b = fbl.chandelier_parts(60.0, 0), fbl.chandelier_parts(100.0, 0)
    for (na, _m, ma, _t, _s), (nb, _m2, mb, _t2, _s2) in zip(a, b):
        assert na == nb and len(ma.v) == len(mb.v)
        if na == "Chandelier_Canopy":
            assert ma.v == mb.v
        elif na != "Chandelier_Frame":
            assert all(abs(p[0] - q[0]) < 1e-9 and abs(p[1] - q[1]) < 1e-9 and abs(p[2] - q[2] - 40.0) < 1e-9
                       for p, q in zip(ma.v, mb.v))
    for drop in (40.0, 80.0, 150.0):                       # visible rod = drop
        L = fbl.chandelier_layout(drop)
        assert abs(L["z_collar"] - (L["hubs"][0][2] + 0.5 * fbl.HUB_H) - drop) < 1e-9
    hi = max(bounds(p[2])[2][1] for p in fbl.chandelier_parts(fbl.DROP_MIN, 0) if "Globe" in p[0])
    assert hi < -4.0


def test_seed_varies_globes_not_layout():
    a, b, c = fbl.chandelier_parts(80.0, 3), fbl.chandelier_parts(80.0, 3), fbl.chandelier_parts(80.0, 4)
    assert [p[2].v for p in a] == [p[2].v for p in b]
    assert part(a, "Chandelier_Frame").v == part(c, "Chandelier_Frame").v
    assert part(a, "Chandelier_Globe1").v != part(c, "Chandelier_Globe1").v
    assert part(a, "Chandelier_Filament").v != part(c, "Chandelier_Filament").v
    radii = {round(fbl.globe_variation(s, k)["R"], 4) for s in range(4) for k in range(6)}
    assert len(radii) > 10 and min(radii) >= 9.85 - 1e-9 and max(radii) <= 10.15 + 1e-9


# --------------------------------------------------------------- track spot
def spot_local(v, d):
    rel = sub(v, (0.0, 0.0, fbl.SPOT_KZ))
    w = dot(rel, d)
    r = math.sqrt(max(0.0, dot(rel, rel) - w * w))
    return r, w - fbl.SPOT_NECK


@pytest.mark.parametrize("tilt", [0.0, 30.0, 60.0, 90.0])
def test_track_spot(tilt):
    parts = fbl.track_spot_parts(tilt)
    check_parts(parts)
    led_c, d = fbl.track_spot_aim(tilt)
    assert abs(dot(d, d) - 1.0) < 1e-12 and abs(d[0]) < 1e-12 and d[1] <= 1e-12
    assert abs(math.degrees(math.acos(max(-1.0, min(1.0, -d[2])))) - tilt) < 1e-6
    body = [spot_local(v, d) for v in part(parts, "TrackSpot_Body").v]
    shell = [(r, w) for r, w in body if r > 1.0]
    assert abs(max(r for r, w in shell) - fbl.SPOT_R) < 1e-6                  # 6 cm across
    assert abs(min(w for r, w in shell)) < 1e-6 and abs(max(w for r, w in shell) - fbl.SPOT_LEN) < 1e-6
    baffle = [spot_local(v, d) for v in part(parts, "TrackSpot_Baffle").v]
    assert max(r for r, w in baffle) < fbl.SPOT_RI                             # inside the front ring
    assert min(w for r, w in baffle) > fbl.SPOT_FLOOR and max(w for r, w in baffle) < fbl.SPOT_LEN - 0.2
    assert min(r for r, w in baffle) < 1.4                                     # stepped down to the LED
    led = [spot_local(v, d) for v in part(parts, "TrackSpot_LED").v]
    assert max(r for r, w in led) < fbl.BAFFLE_HOLE and max(w for r, w in led) < fbl.BAFFLE_TOP - 2.0
    r_c, w_c = spot_local(led_c, d)
    assert r_c < 1e-6 and abs(w_c - fbl.LED_FACE) < 1e-9
    for name, _m, md, _t, _s in parts:                     # only the adapter rises into the track
        zmax = bounds(md)[2][1]
        if name == "TrackSpot_Adapter":
            assert abs(zmax - fbl.ADAPTER_UP) < 1e-9
            up = [v for v in md.v if v[2] > 0.0]
            assert all(abs(v[0]) <= fbl.ADAPTER_X + 1e-9 and abs(v[1]) <= fbl.ADAPTER_Y + 1e-9 for v in up)
        else:
            assert zmax < -fbl.ADAPTER_DOWN - 0.05, name
    body_v = part(parts, "TrackSpot_Body").v
    for v, (r, w) in zip(body_v, body):                    # the body swings clear of knuckle and stem
        if r > 1.0:
            assert math.hypot(v[1], v[2] - fbl.SPOT_KZ) > 1.6
            assert not (abs(v[0]) < 1.0 and abs(v[1]) < 1.0 and v[2] > fbl.SPOT_KZ)


def test_track_spot_range():
    for bad in (-5.0, 95.0):
        with pytest.raises(ValueError):
            fbl.track_spot_parts(bad)
    assert fbl.track_spot_parts(30.0)[0][2].v == fbl.track_spot_parts(60.0)[0][2].v   # adapter fixed


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
    (name, nodes), bulbs = fbl.build_chandelier(drop=90.0, seed=2)
    assert name == "Chandelier" and len(nodes) == len(fbl.chandelier_parts()) == 12
    assert bulbs == fbl.bulb_positions(90.0) and len(bulbs) == 6
    assert all(len(b) == 3 and all(math.isfinite(c) for c in b) for b in bulbs)
    name, nodes = fbl.build_track_spot(45.0)
    assert name == "TrackSpot" and len(nodes) == 4
    assert all(mat in ALLOWED for _n, mat, _t, _m in kit.PARTS[start:])
    fbl.preview()
    del kit.PARTS[start:]


def test_track_spot_pan_keeps_the_adapter_on_the_track():
    """Swivelling the spot turns the body and its beam about the stem; the
    adapter stays along the track (X), so it never cuts across the slot."""
    flat = {n: md for n, _, md, _, _ in fbl.track_spot_parts(40.0)}
    turned = {n: md for n, _, md, _, _ in fbl.track_spot_parts(40.0, 35.0)}
    ad0, ad1 = flat["TrackSpot_Adapter"], turned["TrackSpot_Adapter"]
    # the adapter box (its first vertices) does not move
    box = [v for v in ad0.v if v[2] > 0.0]
    assert box and all(max(abs(a - b) for a, b in zip(v, w)) < 1e-9
                       for v, w in zip(box, [w for w in ad1.v if w[2] > 0.0]))
    (p0, d0), (p1, d1) = fbl.track_spot_aim(40.0), fbl.track_spot_aim(40.0, 35.0)
    a = math.radians(35.0)
    assert d1[0] == pytest.approx(d0[0] * math.cos(a) - d0[1] * math.sin(a))
    assert d1[1] == pytest.approx(d0[0] * math.sin(a) + d0[1] * math.cos(a))
    assert d1[2] == pytest.approx(d0[2])
    body0 = flat["TrackSpot_Body"].v
    body1 = turned["TrackSpot_Body"].v
    assert any(abs(v[0] - w[0]) > 0.5 for v, w in zip(body0, body1))
