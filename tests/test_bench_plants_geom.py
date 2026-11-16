"""Geometry tests for tools/apartment/furn_bench_plants.py (no 3ds Max needed).

All plant and planter geometry is pure Python (furn_living._MD cages); the
Max-facing build_* wrappers are run against a small recording fake of the
pymxs runtime.
"""
import math
import os
import sys
import types

import pytest

sys.modules.setdefault("pymxs", types.SimpleNamespace(runtime=types.SimpleNamespace()))
_APT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "apartment")
if _APT not in sys.path:
    sys.path.insert(0, _APT)

import furn_bench_plants as fbp  # noqa: E402
import furn_living  # noqa: E402
import kit  # noqa: E402

BANANA_SEEDS = (0, 1, 2, 3)
BUSH_SEEDS = (0, 1, 2, 3)
POTS = [(45.0, 50.0), (32.0, 34.0)]


# ----------------------------------------------------------------- helpers
def _finite(md):
    return all(math.isfinite(c) for p in md.v for c in p)


def _no_degenerate(md):
    return all(len(set(f)) == len(f) >= 3 for f in md.f) and all(0 <= i < len(md.v) for f in md.f for i in f)


def _bbox(pts):
    xs, ys, zs = zip(*pts)
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def _is_closed(md):
    """Watertight and consistently wound: every directed edge once, its twin once."""
    cnt = {}
    for f in md.f:
        for i in range(len(f)):
            e = (f[i], f[(i + 1) % len(f)])
            cnt[e] = cnt.get(e, 0) + 1
    return all(c == 1 for c in cnt.values()) and all((b, a) in cnt for a, b in cnt)


def _volume(md):
    """Signed volume (positive when the faces point outwards)."""
    vol = 0.0
    for f in md.f:
        a = md.v[f[0]]
        for k in range(1, len(f) - 1):
            b, c = md.v[f[k]], md.v[f[k + 1]]
            vol += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0])
                    + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
    return vol


def _dist_to_polyline(p, path):
    best = float("inf")
    for a, b in zip(path, path[1:]):
        ab = [b[i] - a[i] for i in range(3)]
        ap = [p[i] - a[i] for i in range(3)]
        l2 = sum(c * c for c in ab)
        t = 0.0 if l2 < 1e-12 else max(0.0, min(1.0, sum(ab[i] * ap[i] for i in range(3)) / l2))
        best = min(best, math.dist(p, [a[i] + ab[i] * t for i in range(3)]))
    return best


def _vertex_uvs(md):
    """vertex index -> the (u, v) pairs the faces give it."""
    out = {}
    for f, uv in zip(md.f, md.fuv):
        for i, t in zip(f, uv):
            out.setdefault(i, set()).add((round(t[0], 6), round(t[1], 6)))
    return out


def _check_cards(g, us, vs):
    """Every card carries the whole 0-1 photo, its stem end (u 0.5, v 0) on
    the petiole axis and its blade base (u 0.5, v LC_V0) on the petiole tip."""
    md = g["leaves"]
    assert len(md.fuv) == len(md.f) and all(uv is not None and len(uv) == 4 for uv in md.fuv)
    all_u = [t[0] for uv in md.fuv for t in uv]
    all_v = [t[1] for uv in md.fuv for t in uv]
    assert min(all_u) == 0.0 and max(all_u) == 1.0 and min(all_v) == 0.0 and max(all_v) == 1.0
    assert len(md.f) == (len(us) - 1) * (len(vs) - 1) * len(g["specs"])
    assert len(g["leaf_cards"]) == len(g["specs"])                   # one card per leaf node
    for card in g["leaf_cards"]:
        assert len(card.f) == (len(us) - 1) * (len(vs) - 1) and _finite(card) and _no_degenerate(card)
        cu = [t[0] for uv in card.fuv for t in uv]
        cv = [t[1] for uv in card.fuv for t in uv]
        assert (min(cu), max(cu), min(cv), max(cv)) == (0.0, 1.0, 0.0, 1.0)
    vuv = _vertex_uvs(md)
    stem_end = [md.v[i] for i, s in vuv.items() if (0.5, 0.0) in s]
    attach = [md.v[i] for i, s in vuv.items() if (0.5, round(fbp.LC_V0, 6)) in s]
    assert len(stem_end) == len(attach) == len(g["specs"])
    for sp in g["specs"]:
        assert min(math.dist(p, sp["attach"]) for p in attach) < 1e-6
        assert min(math.dist(p, sp["stub"]) for p in stem_end) < 1e-6
        assert math.dist(sp["petiole"][-1], sp["attach"]) < 1e-6
        # the photo's stalk stub runs back inside the petiole tube
        assert _dist_to_polyline(sp["stub"], sp["petiole"]) < 0.8 * sp["petiole_r"][1]


@pytest.fixture(scope="module")
def bananas():
    return {s: fbp.banana_plant_geometry(s) for s in BANANA_SEEDS}


@pytest.fixture(scope="module")
def bushes():
    return {s: fbp.bushy_plant_geometry(s) for s in BUSH_SEEDS}


# ================================================================ planters
@pytest.mark.parametrize("diameter,height", POTS)
def test_planter_is_a_closed_solid_of_real_size(diameter, height):
    md = fbp.planter_md(diameter, height)
    assert md.v and md.f and _finite(md) and _no_degenerate(md)
    assert _is_closed(md)
    lo, hi = _bbox(md.v)
    assert lo[2] == pytest.approx(0.0, abs=1e-6)
    assert hi[2] == pytest.approx(height, abs=1e-6)
    assert max(math.hypot(p[0], p[1]) for p in md.v) == pytest.approx(diameter / 2.0, abs=0.05)
    # a real stoneware shell: outer solid minus the cavity above the floor
    d = fbp.planter_dims(diameter, height)

    def disc_volume(r_of_z, z0, z1, n=400):
        return sum(math.pi * r_of_z(z0 + (z1 - z0) * (k + 0.5) / n) ** 2 * (z1 - z0) / n for k in range(n))

    expect = (disc_volume(lambda z: fbp._r_out(d, z), 0.0, height)
              - disc_volume(lambda z: fbp._r_in(d, z), d["floor"], height))
    assert _volume(md) == pytest.approx(expect, rel=0.08)          # positive: outward normals


@pytest.mark.parametrize("diameter,height", POTS)
def test_planter_taper_wall_and_rounded_edges(diameter, height):
    d = fbp.planter_dims(diameter, height)
    assert 1.0 <= d["wall"] <= 1.6
    prof = fbp.planter_profile(diameter, height)
    # slight taper: the outer wall leans out 1-4 degrees
    outer = [p for p in prof if p[0] > fbp._r_out(d, p[1]) - 0.01 and 2.0 < p[1] < height - 2.0]
    lo, hi = min(outer, key=lambda p: p[1]), max(outer, key=lambda p: p[1])
    assert 1.0 < math.degrees(math.atan2(hi[0] - lo[0], hi[1] - lo[1])) < 4.0
    # no razor edge anywhere on the section: every corner is a fillet in <= 15 deg steps
    worst = 0.0
    for a, b, c in zip(prof, prof[1:], prof[2:]):
        d1, d2 = (b[0] - a[0], b[1] - a[1]), (c[0] - b[0], c[1] - b[1])
        l1, l2 = math.hypot(*d1), math.hypot(*d2)
        assert l1 > 1e-6 and l2 > 1e-6
        worst = max(worst, math.degrees(math.acos(max(-1.0, min(1.0, (d1[0] * d2[0] + d1[1] * d2[1]) / (l1 * l2))))))
    assert worst <= 15.5
    # bullnosed rim: several arc stations above the rim's mid-height
    assert len([p for p in prof if p[1] > height - 0.5 * d["wall"]]) >= 6
    # the foot fillet is a real radius (>= 3 mm): the base corner is rounded off
    assert min(p[0] for p in prof if p[1] > 0.3 and p[0] > fbp._r_out(d, 0.0) - 1.5) < fbp._r_out(d, 0.3) - 0.01


@pytest.mark.parametrize("diameter,height", POTS)
def test_soil_fills_the_mouth_below_the_rim(diameter, height):
    d = fbp.planter_dims(diameter, height)
    md = fbp.soil_md(diameter, height, mounds=[(1.0, -2.0, 1.1, 7.0)], seed=3)
    assert md.v and md.f and _finite(md) and _no_degenerate(md)
    assert _is_closed(md) and _volume(md) > 0.0
    zs = [p[2] for p in md.v]
    assert height - 6.0 <= max(zs) <= height - 1.5                 # 1.5-6 cm below the rim
    assert min(zs) > d["floor"]
    for p in md.v:                                                  # never through the outer wall,
        assert math.hypot(p[0], p[1]) <= fbp._r_out(d, p[2]) - 0.3
    # ...but into the inner one, so no gap shows at the edge
    assert max(math.hypot(p[0], p[1]) - fbp._r_in(d, p[2]) for p in md.v) > 0.2
    # an irregular surface, not a flat disc
    top = [p[2] for p in md.v if math.hypot(p[0], p[1]) < fbp._r_in(d, d["soil_z"]) - 2.0
           and math.hypot(p[0] - 1.0, p[1] + 2.0) > 12.0]
    assert max(top) - min(top) > 0.15


# ============================================================== leaf cards
def test_leaf_card_has_true_size_droop_twist_and_fold():
    leaf = fbp.LeafCard(80.0, 26.0, droop=math.radians(40.0), twist=math.radians(15.0), fold=1.6)
    assert leaf.L == pytest.approx(80.0 / (fbp.LC_V1 - fbp.LC_V0))
    assert leaf.W == pytest.approx(26.0 / (2.0 * fbp.LC_HWMAX))
    vs = [fbp.LC_V0 + (fbp.LC_V1 - fbp.LC_V0) * k / 400.0 for k in range(401)]
    mid = [leaf.point(0.5, v) for v in vs]
    assert sum(math.dist(a, b) for a, b in zip(mid, mid[1:])) == pytest.approx(80.0, rel=0.003)
    _M, T, X, _N = leaf.frame(80.0)
    assert math.degrees(math.atan2(-T[2], T[1])) == pytest.approx(40.0, abs=0.3)   # drooped 40 deg
    assert math.degrees(math.acos(X[0])) == pytest.approx(15.0, abs=0.3)           # twisted 15 deg
    assert leaf.point(0.5, fbp.LC_V1)[2] < -10.0
    # folded along the midrib: the widest edges stand 1.6 cm proud, 26 cm apart
    v = 0.379
    M, _T, _X, N = leaf.frame((v - fbp.LC_V0) * leaf.L)
    left, right = leaf.point(0.5 - fbp.LC_HWMAX, v), leaf.point(0.5 + fbp.LC_HWMAX, v)
    for p in (left, right):
        assert sum((p[i] - M[i]) * N[i] for i in range(3)) == pytest.approx(1.6, abs=0.01)
    assert math.dist(left, right) == pytest.approx(26.0, abs=0.01)
    # the stalk end of the photo points back down the petiole
    assert leaf.point(0.5, 0.0) == pytest.approx((0.0, -fbp.LC_V0 * leaf.L, 0.0))


def test_flat_leaf_card_reads_unmirrored_from_its_front():
    leaf = fbp.LeafCard(60.0, 20.0)
    md = leaf.card_md(fbp.BUSH_US, fbp.BUSH_VS)
    for f, uv in zip(md.f, md.fuv):
        a, b, c = (md.v[i] for i in f[:3])
        n = ((b[1] - a[1]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[1] - a[1]),
             (b[2] - a[2]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[2] - a[2]),
             (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
        assert n[2] > 0.0 and abs(n[0]) + abs(n[1]) < 1e-9          # faces +Z (the front)
        for i, t in zip(f, uv):                                      # U along +X, V along +Y
            p = md.v[i]
            assert p[0] == pytest.approx((t[0] - 0.5) * leaf.W, abs=1e-9)
            assert p[1] == pytest.approx((t[1] - fbp.LC_V0) * leaf.L, abs=1e-9)


# =========================================================== banana plant
def test_banana_counts_and_real_leaf_sizes(bananas):
    for g in bananas.values():
        specs = g["specs"]
        assert 10 <= len(specs) == g["n_leaves"] <= 14
        for sp in specs:
            assert 60.0 <= sp["blade_len"] <= 90.0
            assert 20.0 <= sp["blade_w"] <= 30.0
            assert 35.0 <= sp["petiole_len"] <= 110.0                 # long upright petioles
            assert sp["card_len"] == pytest.approx(sp["blade_len"] / (fbp.LC_V1 - fbp.LC_V0))
        # petioles of different heights, blades at different angles
        assert max(sp["petiole_len"] for sp in specs) - min(sp["petiole_len"] for sp in specs) > 12.0
        assert max(sp["droop_deg"] for sp in specs) - min(sp["droop_deg"] for sp in specs) > 15.0


def test_banana_height_and_footprint(bananas):
    for g in bananas.values():
        assert 170.0 <= g["height"] <= 190.0                          # tallest visible leaf tip
        assert g["radius"] <= 85.0                                    # visible spread <= 1.7 m
        lo, hi = _bbox(g["leaves"].v + g["stems"].v)
        assert hi[2] <= 200.0                                         # incl. the cut-out card margins
        assert max(-lo[0], -lo[1], hi[0], hi[1]) <= 110.0
        assert g["soil_z"] - 3.5 <= lo[2] < g["soil_z"] - 1.0        # petioles start buried in the soil
        assert min(p[2] for p in g["probes"]) > 70.0                  # blades well clear of the pot


def test_banana_meshes_are_finite_and_stems_closed(bananas):
    for g in bananas.values():
        for md in (g["leaves"], g["stems"]):
            assert md.v and md.f and _finite(md) and _no_degenerate(md)
        assert _is_closed(g["stems"]) and _volume(g["stems"]) > 0.0


def test_banana_cards_map_the_whole_photo_onto_the_petioles(bananas):
    for g in bananas.values():
        _check_cards(g, fbp.BANANA_US, fbp.BANANA_VS)


def test_banana_no_two_leaves_alike(bananas):
    for g in bananas.values():
        for key in ("blade_len", "blade_w", "droop_deg", "twist_deg", "fold", "petiole_len"):
            vals = [round(sp[key], 4) for sp in g["specs"]]
            assert len(set(vals)) == len(vals), key
        assert any(sp["twist_deg"] > 0 for sp in g["specs"]) and any(sp["twist_deg"] < 0 for sp in g["specs"])


def test_banana_deterministic_per_seed(bananas):
    again = fbp.banana_plant_geometry(0)
    assert again["leaves"].v == bananas[0]["leaves"].v and again["stems"].v == bananas[0]["stems"].v
    assert bananas[1]["leaves"].v != bananas[0]["leaves"].v


# ============================================================ bushy plant
def test_bush_counts_sizes_height_and_branching(bushes):
    for g in bushes.values():
        assert 45 <= g["n_leaves"] == len(g["specs"]) <= 66
        for sp in g["specs"]:
            assert 12.0 <= sp["blade_len"] <= 25.0
        assert 80.0 <= g["height"] <= 110.0
        assert g["n_main"] >= 3 and g["n_branches"] > g["n_main"]   # branching stems
        assert g["radius"] <= 60.0
        lo, hi = _bbox(g["leaves"].v + g["stems"].v)
        assert hi[2] <= 115.0 and max(-lo[0], -lo[1], hi[0], hi[1]) <= 75.0
        for key in ("blade_len", "droop_deg", "twist_deg"):
            vals = [round(sp[key], 4) for sp in g["specs"]]
            assert len(set(vals)) == len(vals), key


def test_bush_meshes_finite_closed_and_clear_of_the_pot(bushes):
    for g in bushes.values():
        for md in (g["leaves"], g["stems"]):
            assert md.v and md.f and _finite(md) and _no_degenerate(md)
        assert _is_closed(g["stems"]) and _volume(g["stems"]) > 0.0
        d = fbp.planter_dims(*g["pot"])
        for p in g["probes"]:                                         # no leaf dips into the planter
            if math.hypot(p[0], p[1]) < d["R"] + 0.5:
                assert p[2] > d["H"] + 0.5
        lo, _hi = _bbox(g["stems"].v)
        assert g["soil_z"] - 4.0 < lo[2] < g["soil_z"] - 1.0         # stems rise out of the soil
        assert len(g["mounds"]) == g["n_main"]                        # soil heaped round each stem
        _check_cards(g, fbp.BUSH_US, fbp.BUSH_VS)


def test_bush_deterministic_per_seed(bushes):
    again = fbp.bushy_plant_geometry(2)
    assert again["leaves"].v == bushes[2]["leaves"].v
    assert bushes[3]["leaves"].v != bushes[2]["leaves"].v


# ===================================================== Max-facing wrappers
class _FakeNode(object):
    def __init__(self, src=""):
        self.src, self.parent, self.mods = src, None, []
        self.name = src.split('name:"', 1)[1].split('"', 1)[0] if 'name:"' in src else ""


class _FakeRT(object):
    """Just enough pymxs.runtime for furn_living._build / kit.soften / kit.group."""

    def execute(self, src):
        return _FakeNode(src)

    def Dummy(self):
        return _FakeNode()

    def TurboSmooth(self):
        return types.SimpleNamespace(kind="TurboSmooth", iterations=0)

    def addModifier(self, node, mod):
        node.mods.append(mod)

    def isProperty(self, obj, name):
        return False

    def Name(self, s):
        return s


@pytest.fixture
def fake_max(monkeypatch):
    fake = _FakeRT()
    monkeypatch.setattr(kit, "rt", fake)
    monkeypatch.setattr(furn_living, "rt", fake)
    monkeypatch.setattr(kit, "PARTS", [])
    return fake


@pytest.mark.parametrize("build,args,keys,n_leaves", [
    (fbp.build_banana_plant, (0,), {"leaf_card", "stem", "pot_matte", "soil"},
     lambda: fbp.banana_plant_geometry(0)["n_leaves"]),
    (fbp.build_bushy_plant, (1,), {"leaf_card", "stem", "pot_matte", "soil"},
     lambda: fbp.bushy_plant_geometry(1)["n_leaves"]),
    (fbp.build_planter, (45.0, 50.0), {"pot_matte", "soil"}, lambda: 0),
    (fbp.build_planter, (32.0, 34.0), {"pot_matte", "soil"}, lambda: 0),
])
def test_build_wrappers_register_every_node(fake_max, build, args, keys, n_leaves):
    group = build(*args)
    parts = list(kit.PARTS)
    assert {key for _n, key, _t, _m in parts} == keys
    assert sum(1 for _n, key, _t, _m in parts if key == "leaf_card") == n_leaves()
    assert sum(1 for _n, key, _t, _m in parts if key != "leaf_card") == (3 if n_leaves() else 2)
    for node, key, tile, maptype in parts:
        assert key in kit.MAT_KEYS
        assert node.parent is group                                  # one dummy per piece
        if key == "leaf_card":                                       # own 0-1 UVs: no box map, no smoothing
            assert tile is None and maptype is None
            assert "setTVert" in node.src and "buildTVFaces" in node.src and not node.mods
        else:                                                        # box-mapped at real scale, TurboSmoothed
            assert tile and maptype == 4
            assert [m.kind for m in node.mods] == ["TurboSmooth"]


def test_plant_without_pot_has_only_stems_and_leaves(fake_max):
    fbp.build_banana_plant(2, with_pot=False)
    keys = [key for _n, key, _t, _m in kit.PARTS]
    assert keys.count("stem") == 1
    assert keys.count("leaf_card") == fbp.banana_plant_geometry(2)["n_leaves"] == len(keys) - 1
