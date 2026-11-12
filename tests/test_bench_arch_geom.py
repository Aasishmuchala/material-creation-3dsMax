"""Geometry tests for tools/apartment/bench_arch.py - runs without 3ds Max.

Every mesh must be a closed, consistently wound solid facing outward, free of
NaN, at real-world size; every section must be a simple polygon whose visible
corners are all filleted (only corners buried in a wall, floor or ceiling may
turn sharply). The build_* wrappers are run against a fake pymxs runtime.
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
    import bench_arch as B  # noqa: E402
    import furn_living  # noqa: E402
    import kit  # noqa: E402
finally:                     # leave other tests' pymxs stand-ins as they were
    if _saved_pymxs is None:
        sys.modules.pop("pymxs", None)
    else:
        sys.modules["pymxs"] = _saved_pymxs


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


def parts_dict(parts):
    return {name: (key, tile, md) for name, key, tile, md in parts}


def _turn(a, p, c):
    d1 = (p[0] - a[0], p[1] - a[1])
    d2 = (c[0] - p[0], c[1] - p[1])
    l1, l2 = math.hypot(*d1), math.hypot(*d2)
    return math.degrees(math.acos(max(-1.0, min(1.0, (d1[0] * d2[0] + d1[1] * d2[1]) / (l1 * l2)))))


def _crosses(p1, p2, q1, q2):
    def o(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    d1, d2, d3, d4 = o(q1, q2, p1), o(q1, q2, p2), o(p1, p2, q1), o(p1, p2, q2)
    return d1 * d2 < -1e-14 and d3 * d4 < -1e-14


def assert_section(prof, hidden, closed=True, name=""):
    """Simple polygon, no duplicate points, and every vertex that turns more
    than 25 degrees is buried (hidden(p) true): no razor-sharp visible edge."""
    n = len(prof)
    assert n >= 4
    for i in range(n if closed else n - 1):
        a, b = prof[i], prof[(i + 1) % n]
        assert math.hypot(b[0] - a[0], b[1] - a[1]) > 1e-6, "%s: duplicate point %d" % (name, i)
    segs = [(prof[i], prof[(i + 1) % n]) for i in range(n if closed else n - 1)]
    for i in range(len(segs)):
        for j in range(i + 2, len(segs)):
            if closed and i == 0 and j == len(segs) - 1:
                continue
            assert not _crosses(segs[i][0], segs[i][1], segs[j][0], segs[j][1]), \
                "%s: section crosses itself (segments %d, %d)" % (name, i, j)
    rng = range(n) if closed else range(1, n - 1)
    for i in rng:
        t = _turn(prof[i - 1], prof[i], prof[(i + 1) % n])
        if t > 25.0:
            assert hidden(prof[i]), "%s: sharp visible corner (%.0f deg) at %r" % (name, t, prof[i])


def extent(prof, k):
    vals = [p[k] for p in prof]
    return min(vals), max(vals)


# ------------------------------------------------------------------ 2-D tools
def test_earclip_keeps_area_and_winding():
    comb = [(0, 0), (10, 0), (10, 6), (8, 6), (8, 2), (6, 2), (6, 6), (4, 6), (4, 2), (2, 2), (2, 6), (0, 6)]
    for poly in (comb, comb[::-1]):
        tris = B._earclip(poly)
        assert len(tris) == len(poly) - 2
        area = sum(B._area2([poly[a], poly[b], poly[c]]) for a, b, c in tris)
        assert area == pytest.approx(B._area2(poly))
        sign = 1.0 if B._area2(poly) > 0 else -1.0
        assert all(sign * B._area2([poly[a], poly[b], poly[c]]) > 0 for a, b, c in tris)


@pytest.mark.parametrize("name,prof,hidden,closed", [
    ("cornice", B.cornice_profile(), lambda p: p[0] < 0 or p[1] < 0, True),
    ("skirting", B.skirting_profile(), lambda p: p[0] < 0 or p[1] < 0, True),
    ("casing", B.casing_profile(), lambda p: p[1] < 0, True),
    ("frame", B.frame_profile(), lambda p: False, True),
    ("sash", B.sash_profile(), lambda p: False, True),
    ("bar", B.bar_profile(), lambda p: False, True),
    ("kick", B.kick_profile(), lambda p: p[0] < 0, True),
    ("astragal", B.astragal_profile(), lambda p: p[1] > B.Y_ROOM, True),
    ("moulding", B.panel_moulding_profile(), lambda p: p[0] < 0 or p[1] < 0, True),
    ("panel", B.raised_panel_profile(0.0), lambda p: False, False),
])
def test_sections_are_simple_and_filleted(name, prof, hidden, closed):
    assert_section(prof, hidden, closed, name)


def test_section_sizes():
    u, h = extent(B.cornice_profile(), 0), extent(B.cornice_profile(), 1)
    assert u == pytest.approx((-0.1, 14.0)) and h == pytest.approx((-0.1, 18.0))      # 14 deep, 18 tall
    sk = B.skirting_profile()
    assert extent(sk, 0) == pytest.approx((-0.1, 2.5)) and extent(sk, 1) == pytest.approx((-0.1, 18.0))
    sk = B.skirting_profile(22.0, 2.2)
    assert extent(sk, 1)[1] == pytest.approx(22.0) and extent(sk, 0)[1] == pytest.approx(2.2)
    cs = B.casing_profile()
    assert extent(cs, 0) == pytest.approx((0.0, 12.0)) and extent(cs, 1)[1] == pytest.approx(2.6)
    assert extent(B.frame_profile(), 0) == pytest.approx((0.0, 7.0))
    assert extent(B.frame_profile(), 1) == pytest.approx((-3.5, 3.5))
    assert extent(B.sash_profile(), 0) == pytest.approx((0.0, 6.2))                    # ~6 cm sash
    assert extent(B.bar_profile(), 0) == pytest.approx((-1.3, 1.3))
    with pytest.raises(ValueError):
        B.skirting_profile(6.0, 2.5)


# ------------------------------------------------------------------ cornice
def test_cornice_mitred_ring():
    md = B.cornice_md((0.0, 0.0, 500.0, 420.0), 330.0)
    assert_solid(md, "cornice")
    assert components(md) == 1
    (x0, y0, z0), (x1, y1, z1) = B._bbox(md)
    assert (x0, y0, x1, y1) == pytest.approx((-0.1, -0.1, 500.1, 420.1))
    assert (z0, z1) == pytest.approx((312.0, 330.1))
    # projection off the walls: 14 cm, reached only at the ceiling band
    depth = max(min(x, 500.0 - x, y, 420.0 - y) for x, y, z in md.v)
    assert depth == pytest.approx(14.0, abs=1e-6)
    assert all(z > 329.3 for x, y, z in md.v if min(x, 500.0 - x, y, 420.0 - y) > 13.9)
    # the four corners are mitred: one ring of each lies on the 45-degree diagonal
    for cx, cy, sx, sy in ((0, 0, 1, 1), (500, 0, -1, 1), (500, 420, -1, -1), (0, 420, 1, -1)):
        diag = [p for p in md.v if abs(sx * (p[0] - cx) - sy * (p[1] - cy)) < 1e-6 and sx * (p[0] - cx) > 1.0]
        assert len(diag) >= 60


def test_cornice_rect_forms_and_errors():
    a = B.cornice_md(((0.0, 0.0), (400.0, 300.0)), 280.0)
    b = B.cornice_md((400.0, 300.0, 0.0, 0.0), 280.0)
    assert a.v == b.v and a.f == b.f
    with pytest.raises(ValueError):
        B.cornice_md((0.0, 0.0, 20.0, 300.0), 280.0)


# ------------------------------------------------------------------ skirting
def test_skirting_closed_ring():
    md = B.skirting_md((-250.0, -200.0, 250.0, 200.0))
    assert_solid(md, "skirting")
    assert components(md) == 1
    (x0, y0, z0), (x1, y1, z1) = B._bbox(md)
    assert (x0, y0, x1, y1) == pytest.approx((-250.1, -200.1, 250.1, 200.1))
    assert (z0, z1) == pytest.approx((-0.1, 18.0))
    assert max(min(x + 250, 250 - x, y + 200, 200 - y) for x, y, z in md.v) == pytest.approx(2.5)


def test_skirting_stops_at_openings():
    rect = (0.0, 0.0, 600.0, 450.0)
    ops = [("s", 120.0, 230.0), ("n", 200.0, 360.0), ("w", 380.0, 470.0), (1, 50.0, 60.0)]
    md = B.skirting_md(rect, ops)
    assert_solid(md, "skirting runs")
    # runs: s 230 .. e 50 | e 60 .. n 360 | n 200 .. the nw corner (the w opening is clamped to
    # y = 380 .. 450, so that run ends square in the corner) | w 380 .. s 120: 4 separate shells
    assert components(md) == 4
    near = 3.0
    for x, y, z in md.v:
        if y < near:
            assert not 120.0 + 1e-6 < x < 230.0 - 1e-6
        if y > 450.0 - near:
            assert not 200.0 + 1e-6 < x < 360.0 - 1e-6
        if x > 600.0 - near:
            assert not 50.0 + 1e-6 < y < 60.0 - 1e-6
        if x < near and y < 450.0 - near:
            assert not 380.0 + 1e-6 < y
    # the ends are square: vertices at the opening edges stand across the wall
    ends = [p for p in md.v if abs(p[0] - 120.0) < 1e-6 and p[1] < near]
    assert ends and max(p[1] for p in ends) == pytest.approx(2.5)
    # nothing left when the openings cover everything
    assert B.skirting_md(rect, [("s", 0, 600), ("e", 0, 450), ("n", 0, 600), ("w", 0, 450)]).v == []


# ------------------------------------------------------------------ French window
def test_french_window_parts():
    parts = parts_dict(B.french_window_parts(140.0, 260.0, 0.0))
    assert set(parts) == {"FrenchWin_Frame", "FrenchWin_Sashes", "FrenchWin_Glass", "FrenchWin_Hardware"}
    for name, (key, tile, md) in parts.items():
        assert key in kit.MAT_KEYS and tile > 0
        assert_solid(md, name)
    assert parts["FrenchWin_Glass"][0] == "glass"
    assert parts["FrenchWin_Hardware"][0] in ("metal_brass", "metal_chrome")
    (x0, y0, z0), (x1, y1, z1) = B._bbox(parts["FrenchWin_Frame"][2])
    assert (x0, x1, z0, z1) == pytest.approx((-70.0, 70.0, 0.0, 260.0))
    assert (y0, y1) == pytest.approx((-3.5, 3.5))
    # sashes lap the frame on the room side and stay inside its outline
    (sx0, sy0, sz0), (sx1, sy1, sz1) = B._bbox(parts["FrenchWin_Sashes"][2])
    assert -70.0 < sx0 and sx1 < 70.0 and 0.0 < sz0 and sz1 < 260.0
    assert sy0 < -5.0 and sy1 <= 3.5
    # frame + transom bar; leaves, kick rails, 4 glazing bars, transom sash + bar, astragal
    assert components(parts["FrenchWin_Frame"][2]) == 2
    assert components(parts["FrenchWin_Sashes"][2]) == 11
    # glass: 3 panes per leaf + 2 in the transom, 4 mm thick, inside the sashes
    gmd = parts["FrenchWin_Glass"][2]
    assert components(gmd) == 8
    (gx0, gy0, gz0), (gx1, gy1, gz1) = B._bbox(gmd)
    assert gy1 - gy0 == pytest.approx(0.4)
    assert -64.0 < gx0 and gx1 < 64.0
    # hardware stays within the frame width and in front of the leaves
    (hx0, hy0, hz0), (hx1, hy1, hz1) = B._bbox(parts["FrenchWin_Hardware"][2])
    assert -70.0 < hx0 and hx1 < 70.0 and hy1 < -3.0 and hy0 > -14.0
    assert 0.0 < hz0 and hz1 < 260.0


def test_french_window_panes_per_leaf():
    gmd = parts_dict(B.french_window_parts())["FrenchWin_Glass"][2]
    parent = {}
    # split the panes by connected component, then count by position
    comps = {}
    for f in gmd.f:
        for i in f:
            parent.setdefault(i, i)
    for f in gmd.f:
        for i in f[1:]:
            a, b = i, f[0]
            while parent[a] != a:
                a = parent[a]
            while parent[b] != b:
                b = parent[b]
            parent[a] = b
    for i in parent:
        r = i
        while parent[r] != r:
            r = parent[r]
        comps.setdefault(r, []).append(gmd.v[i])
    centres = [(sum(p[0] for p in ps) / len(ps), sum(p[2] for p in ps) / len(ps)) for ps in comps.values()]
    left = [c for c in centres if c[0] < 0 and c[1] < 200]
    right = [c for c in centres if c[0] > 0 and c[1] < 200]
    top = [c for c in centres if c[1] > 200]
    assert len(left) == 3 and len(right) == 3 and len(top) == 2


def test_french_window_sill_and_size():
    a = parts_dict(B.french_window_parts(140.0, 260.0, 0.0))
    b = parts_dict(B.french_window_parts(140.0, 260.0, 15.0))
    for name in a:
        (ax0, ay0, az0), (ax1, ay1, az1) = B._bbox(a[name][2])
        (bx0, by0, bz0), (bx1, by1, bz1) = B._bbox(b[name][2])
        assert bz0 - az0 == pytest.approx(15.0, abs=1e-6) or name == "FrenchWin_Hardware"
        assert (bx0, bx1) == pytest.approx((ax0, ax1))
    c = parts_dict(B.french_window_parts(120.0, 240.0, 0.0))
    for name, (key, tile, md) in c.items():
        assert_solid(md, name)
    (x0, y0, z0), (x1, y1, z1) = B._bbox(c["FrenchWin_Frame"][2])
    assert (x0, x1, z1) == pytest.approx((-60.0, 60.0, 240.0))
    with pytest.raises(ValueError):
        B.french_window_parts(60.0, 260.0)


# ------------------------------------------------------------------ radiator
def test_radiator_parts():
    parts = parts_dict(B.radiator_parts(80.0, 60.0))
    assert set(parts) == {"Radiator_Body", "Radiator_Valves"}
    assert parts["Radiator_Body"][0] == "paint_white"
    for name, (key, tile, md) in parts.items():
        assert key in kit.MAT_KEYS
        assert_solid(md, name)
    body = parts["Radiator_Body"][2]
    (x0, y0, z0), (x1, y1, z1) = B._bbox(body)
    assert (x0, x1) == pytest.approx((-40.0, 40.0), abs=1e-6)
    assert (z0, z1) == pytest.approx((0.0, 60.0), abs=1e-6)
    assert (y0, y1) == pytest.approx((-4.25, 4.25), abs=1e-3)       # 2 x 1.25 tubes, 6 cm apart
    n = int(round(80.0 / 4.6))
    assert n >= 15
    assert components(body) == n + 2 + 4                 # sections, two hubs, four feet
    # feet stand on the floor, the sections clear it by 9 cm
    assert sum(1 for p in body.v if abs(p[2]) < 1e-9) >= 4
    assert min(p[2] for p in body.v if abs(p[0] - (-40.0 + 1.25)) < 1e-6) > 8.9
    valves = parts["Radiator_Valves"][2]
    (vx0, vy0, vz0), (vx1, vy1, vz1) = B._bbox(valves)
    assert vx0 < -40.0 and vx1 > 40.0 and vx1 < 50.0 and vz0 >= -0.5 and vz1 < 20.0
    small = parts_dict(B.radiator_parts(45.0, 50.0))
    (x0, y0, z0), (x1, y1, z1) = B._bbox(small["Radiator_Body"][2])
    assert (x0, x1, z1) == pytest.approx((-22.5, 22.5, 50.0), abs=1e-6)
    with pytest.raises(ValueError):
        B.radiator_parts(80.0, 20.0)


# ------------------------------------------------------------------ panel door
def test_panel_door_parts():
    parts = parts_dict(B.panel_door_parts(90.0, 240.0, 16.0, 0.0))
    assert set(parts) == {"PanelDoor_Leaf", "PanelDoor_Lining", "PanelDoor_Casing", "PanelDoor_Hardware"}
    for name, (key, tile, md) in parts.items():
        assert key in kit.MAT_KEYS
        assert_solid(md, name)
        assert key == ("metal_brass" if name == "PanelDoor_Hardware" else "paint_white")
    leaf = parts["PanelDoor_Leaf"][2]
    (x0, y0, z0), (x1, y1, z1) = B._bbox(leaf)
    assert (x0, x1) == pytest.approx((-45.0, 45.0))
    assert (z0, z1) == pytest.approx((0.8, 240.8))
    assert y1 - y0 == pytest.approx(4.4)
    # 2 stiles, 3 rails, 2 raised panels, a planted moulding round each panel on each face
    assert components(leaf) == 11
    (x0, y0, z0), (x1, y1, z1) = B._bbox(parts["PanelDoor_Lining"][2])
    assert (x0, x1, y0, y1, z0, z1) == pytest.approx((-47.8, 47.8, -8.0, 8.0, 0.0, 243.6))
    (x0, y0, z0), (x1, y1, z1) = B._bbox(parts["PanelDoor_Casing"][2])
    assert (x0, x1, z0, z1) == pytest.approx((-58.2, 58.2, 0.0, 253.7))
    assert (y0, y1) == pytest.approx((-11.0, 11.0))
    assert components(parts["PanelDoor_Casing"][2]) == 6       # 2 architraves, 4 plinth blocks
    # handle: lever on each face near the lock stile, at about 105 cm
    hw = parts["PanelDoor_Hardware"][2]
    lev = [p for p in hw.v if p[1] < -12.0]
    assert lev and all(25.0 < p[0] < 45.0 and 100.0 < p[2] < 110.0 for p in lev)
    assert max(p[1] for p in hw.v) > 3.0                       # the lever on the far face


def test_panel_door_swing_and_wall():
    shut = parts_dict(B.panel_door_parts(90.0, 240.0, 16.0, 0.0))
    open_ = parts_dict(B.panel_door_parts(90.0, 240.0, 16.0, 90.0))
    (x0, y0, z0), (x1, y1, z1) = B._bbox(open_["PanelDoor_Leaf"][2])
    assert y0 < -90.0 and x1 < -40.0                       # swung into the room (-Y) on its hinges
    assert_solid(open_["PanelDoor_Leaf"][2], "open leaf")
    assert B._volume(open_["PanelDoor_Leaf"][2]) == pytest.approx(B._volume(shut["PanelDoor_Leaf"][2]))
    assert open_["PanelDoor_Lining"][2].v == shut["PanelDoor_Lining"][2].v
    lev = [p for p in open_["PanelDoor_Hardware"][2].v if p[2] > 100 and p[2] < 110]
    assert min(p[1] for p in lev) < -70.0                  # the handles went with the leaf
    thick = parts_dict(B.panel_door_parts(80.0, 230.0, 24.0, 0.0))
    for name, (key, tile, md) in thick.items():
        assert_solid(md, name)
    (x0, y0, z0), (x1, y1, z1) = B._bbox(thick["PanelDoor_Lining"][2])
    assert (y0, y1) == pytest.approx((-12.0, 12.0))
    with pytest.raises(ValueError):
        B.panel_door_parts(90.0, 120.0)


# ------------------------------------------------------------------ Max wrappers
class _Node(object):
    def __init__(self, name=""):
        self.name, self.parent = name, None


class _FakeRT(object):
    """Just enough pymxs for _build / kit.part / kit.group / the Smooth modifier."""

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


def test_build_wrappers(monkeypatch):
    fake = _FakeRT()
    for mod in (kit, furn_living, B):
        monkeypatch.setattr(mod, "rt", fake)
    monkeypatch.setattr(kit, "PARTS", [])
    rect = (0.0, 0.0, 520.0, 430.0)
    groups = [B.build_cornice(rect, 330.0), B.build_skirting(rect, [("s", 100.0, 240.0)]),
              B.build_french_window(), B.build_radiator(), B.build_panel_door(swing=20.0)]
    assert [g.name for g in groups] == ["Cornice", "Skirting", "FrenchWindow", "Radiator", "PanelDoor"]
    keys = [(n.name, k) for n, k, t, m in kit.PARTS]
    assert ("Cornice", "wall_paint") in keys and ("Skirting", "paint_white") in keys
    assert ("FrenchWin_Glass", "glass") in keys and ("Radiator_Valves", "metal_chrome") in keys
    assert len(kit.PARTS) == 2 + 4 + 2 + 4
    assert all(t and m == 4 for n, k, t, m in kit.PARTS)        # box-mapped at real-world scale
    assert all(n.parent is not None for n, k, t, m in kit.PARTS)
    # one auto-smooth modifier per node, set to 40 degrees
    assert len(fake.mods) == len(kit.PARTS)
    assert all(getattr(m, "autoSmooth", None) is True and m.threshold == 40.0 for n, m in fake.mods)
    assert all("convertToPoly" in s for s in fake.scripts)
