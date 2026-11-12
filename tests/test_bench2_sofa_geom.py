"""Off-Max geometry tests for tools/apartment/furn_bench2_sofa.py (the long, low
chenille sofa of benchmark 2). pymxs is stubbed while the module is imported (and
the previous entry put back), so only the pure-Python cage generators run; the
build_sofa wrapper is exercised with furn_living._build / kit.soften / kit.group
faked."""
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
    import furn_living as fl  # noqa: E402
    import furn_bench2_sofa as fs  # noqa: E402
finally:
    if _prev is None:
        sys.modules.pop("pymxs", None)
    else:
        sys.modules["pymxs"] = _prev

BODY = ("Plinth", "Deck", "Back", "ArmL", "ArmR", "SeatL", "SeatR")
NAMES = BODY + ("ScatterVelvet", "ScatterLinen")


# ------------------------------------------------------------------ helpers
def bounds(mds):
    if not isinstance(mds, (list, tuple)):
        mds = [mds]
    vs = [v for md in mds for v in md.v]
    return [(min(v[k] for v in vs), max(v[k] for v in vs)) for k in range(3)]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _newell(pts):
    n = [0.0, 0.0, 0.0]
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    return n


def volume(md):
    vol = 0.0
    for f in md.f:
        p0 = md.v[f[0]]
        for k in range(1, len(f) - 1):
            p1, p2 = md.v[f[k]], md.v[f[k + 1]]
            vol += (p0[0] * (p1[1] * p2[2] - p1[2] * p2[1]) - p0[1] * (p1[0] * p2[2] - p1[2] * p2[0])
                    + p0[2] * (p1[0] * p2[1] - p1[1] * p2[0])) / 6.0
    return vol


def check_mesh(md):
    """Non-empty, finite, valid tri / quad faces with finite UVs; closed: every
    directed edge paired with its reverse exactly once, outward faces."""
    assert md.v and md.f
    assert all(math.isfinite(c) for v in md.v for c in v)
    nv = len(md.v)
    for f in md.f:
        assert 3 <= len(f) <= 4 and len(set(f)) == len(f) and all(0 <= i < nv for i in f)
    assert len(md.fuv) == len(md.f)
    for uv in md.fuv:
        if uv is not None:
            assert all(math.isfinite(c) for t in uv for c in t)
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


def components(md):
    parent = list(range(len(md.v)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for f in md.f:
        r0 = find(f[0])
        for k in f[1:]:
            rk = find(k)
            if rk != r0:
                parent[rk] = r0
    return len({find(i) for f in md.f for i in f})


def planes(md):
    """(centroid, unit outward normal) of every face of a (near-)convex mesh."""
    out = []
    for f in md.f:
        P = [md.v[i] for i in f]
        n = _newell(P)
        ln = math.sqrt(_dot(n, n))
        if ln > 1e-9:
            out.append((tuple(sum(p[k] for p in P) / len(P) for k in range(3)), tuple(c / ln for c in n)))
    return out


def outside(pl, p, rad=10.0):
    """Signed distance-like measure of p from a (near-)convex mesh: > 0 outside (a lower
    bound of the true distance), < 0 inside (minus the distance to the nearest face
    plane). Only faces within `rad` cm of p count when there are any: the arms bulge
    a little and waver, so a face plane 60 cm away may cut a few mm into them."""
    loc = [(c, n) for c, n in pl if math.dist(c, p) < rad]
    return max(_dot(_sub(p, c), n) for c, n in (loc or pl))


def tri_normal(a, b, c):
    u, v = _sub(b, a), _sub(c, a)
    n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    ln = math.sqrt(_dot(n, n))
    return (n[0] / ln, n[1] / ln, n[2] / ln) if ln > 1e-15 else (0.0, 0.0, 0.0)


# ------------------------------------------------------------------ fixtures
def _by_name(parts):
    return {p.name.split("_", 1)[1]: p for p in parts}


@pytest.fixture(scope="module")
def L():
    return fs.sofa_layout()


@pytest.fixture(scope="module")
def parts():
    return _by_name(fs.sofa_parts())


@pytest.fixture(scope="module")
def plain():
    return _by_name(fs.sofa_parts(scatter=False, creases=False))


# ------------------------------------------------------- inventory / hygiene
def test_inventory_and_material_keys(parts):
    assert set(parts) == set(NAMES)
    assert "chenille" in kit.MAT_KEYS
    mats = {k: p.mat for k, p in parts.items()}
    assert mats == dict({k: "chenille" for k in BODY}, Plinth="metal_black", ScatterVelvet="cushion",
                        ScatterLinen="linen")
    for k, p in parts.items():
        assert p.mat in kit.MAT_KEYS, k
        assert p.tile > 0 and p.smooth in (0, 1), k
        name, mat, md, tile, smooth = p                       # unpacks like the other bench parts
        assert name == "BenchSofa_" + k and md is p.md
    assert not parts["Plinth"].own_uv and parts["Plinth"].tile == fs.METAL
    for k in BODY[1:]:
        assert parts[k].own_uv and parts[k].tile == fs.CHENILLE and parts[k].noise and parts[k].axes is None
    for k in ("ScatterVelvet", "ScatterLinen"):
        ax = parts[k].axes
        assert parts[k].smooth == 0 and parts[k].origin is not None
        for i in range(3):                                    # orthonormal, right-handed node frame
            for j in range(3):
                assert abs(_dot(ax[i], ax[j]) - (1.0 if i == j else 0.0)) < 1e-9
        cr = (ax[0][1] * ax[1][2] - ax[0][2] * ax[1][1], ax[0][2] * ax[1][0] - ax[0][0] * ax[1][2],
              ax[0][0] * ax[1][1] - ax[0][1] * ax[1][0])
        assert _dot(cr, ax[2]) > 0.999


def test_meshes_closed_finite_and_outward(parts):
    vols = {k: check_mesh(p.md) for k, p in parts.items()}
    assert 300000.0 < vols["Deck"] < 450000.0                 # ~234 x 77 x 22.5 cm, rounded
    assert 300000.0 < vols["Back"] < 400000.0
    for k in ("ArmL", "ArmR"):
        assert 150000.0 < vols[k] < 180000.0                  # 28 x 100 x 68.5 pill
    for k in ("SeatL", "SeatR"):
        assert 110000.0 < vols[k] < 135000.0                  # 107 x 75 x 16, crowned, squashed
    assert 12000.0 < vols["ScatterVelvet"] < 22000.0 and 9000.0 < vols["ScatterLinen"] < 18000.0
    assert sum(len(p.md.f) for p in parts.values()) < 60000  # cage budget before TurboSmooth


def test_every_face_fans_cleanly(parts):
    """_build fans every polygon from its first vertex: no zero-area or flipped fan
    triangles (the back's end-cap rungs and the slab caps included)."""
    for k, p in parts.items():
        V = p.md.v
        for f in p.md.f:
            n = _newell([V[i] for i in f])
            ln = math.sqrt(_dot(n, n))
            assert ln > 1e-9, k
            for j in range(1, len(f) - 1):
                u, w = _sub(V[f[j]], V[f[0]]), _sub(V[f[j + 1]], V[f[0]])
                cr = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
                assert _dot(cr, n) / ln > -1e-9, k


# ------------------------------------------------------- real-world dimensions
def test_overall_size_and_floating_body(parts, L):
    body = [parts[k].md for k in BODY]
    (x0, x1), (y0, y1), (z0, z1) = bounds(body)
    assert -135.1 < x0 < -134.9 and 134.9 < x1 < 135.1                   # W 270
    assert abs(y0 + 50.0) < 1e-6 and abs(y1 - 50.0) < 1e-6                # D 100, front at -Y
    assert abs(z0) < 1e-9 and 71.8 < z1 <= 72.0 + 1e-9                    # H 72
    uph = [parts[k].md for k in BODY[1:]]
    assert abs(bounds(uph)[2][0] - L["z_b"]) < 1e-6 and L["z_b"] == 3.5     # upholstery floats 3.5 cm up
    # only the recessed plinth reaches the floor, set well in under the body
    pb = bounds(parts["Plinth"].md)
    assert abs(pb[2][0]) < 1e-9 and abs(pb[2][1] - 3.6) < 1e-6
    assert pb[0][1] <= x1 - 9.9 and pb[0][0] >= x0 + 9.9
    assert pb[1][0] >= bounds(parts["Deck"].md)[1][0] + 6.0 and pb[1][1] <= 44.0 + 1e-6
    corner = min(math.dist(v, (pb[0][1], pb[1][0], pb[2][1])) for v in parts["Plinth"].md.v)
    assert corner > 0.3                                                     # eased, not razor-sharp


def test_pill_arms(parts, L):
    for k, s in (("ArmL", -1.0), ("ArmR", 1.0)):
        md = parts[k].md
        b = bounds(md)
        xa = s * L["x_arm"]
        assert 27.9 < b[0][1] - b[0][0] < 28.15                            # 28 wide
        assert abs(b[1][0] + 50.0) < 1e-6 and abs(b[1][1] - 50.0) < 1e-6
        assert abs(b[2][0] - 3.5) < 1e-6 and 71.8 < b[2][1] <= 72.0 + 1e-9
        mid = [v for v in md.v if abs(v[1]) < 5.0]
        top = [abs(v[0] - xa) for v in mid if v[2] > 71.5]
        assert top and max(top) < 3.2                                       # rounded right over the top
        shoulder = [v[0] for v in mid if 55.0 < v[2] < 58.0]
        assert max(shoulder) - min(shoulder) > 26.8                         # full width below the roll
        foot = [v[0] for v in md.v if v[2] < 3.5 + 1e-6]
        assert max(foot) - min(foot) < 20.5                                 # tucked under on a 4 cm radius
        side = [v[1] for v in md.v if 9.5 < abs(v[0] - xa) < 10.5 and 20.0 < v[2] < 50.0]
        assert min(side) > -46.0                                            # a half-round nose in plan
        nose = [abs(v[0] - xa) for v in md.v if v[1] < -49.0]
        assert nose and max(nose) < 5.0
        prof = [v[1] for v in md.v if abs(v[0] - xa) < 1.0 and v[2] > 70.5]
        assert prof and min(prof) > -44.0                                   # side view: a rounded front-top corner
        prof = [v[1] for v in md.v if abs(v[0] - xa) < 1.0 and 65.5 < v[2] < 67.0]
        assert prof and -48.5 < min(prof) < -46.0
    assert bounds(parts["ArmL"].md)[0][1] == pytest.approx(-L["x_in"], abs=0.1)


def test_back_is_low_raked_and_rolled(parts, L):
    md = parts["Back"].md
    b = bounds(md)
    assert abs(b[0][0] + L["x_in"] + 11.0) < 1e-6 and abs(b[0][1] - L["x_in"] - 11.0) < 1e-6
    assert 67.5 < b[2][1] <= 68.0 + 1e-9 and L["H"] - b[2][1] >= 3.5      # a little under the arms
    assert b[1][1] <= 48.8 + 1e-6
    f = lambda z: fs.back_front_y(L, z)
    rake = math.degrees(math.atan2(f(50.0) - f(32.0), 18.0))
    assert 13.0 < rake < 17.0                                               # raked above the deck
    assert abs(f(10.0) - f(20.0)) < 0.05                                    # upright behind the deck
    assert f(L["roll_zc"]) < f(L["roll_zc"] - 4.5) - 0.5                   # the roll stands proud
    assert fs.back_rear_y(L, 30.0) == pytest.approx(48.8)
    rows, apex = fs.back_section(L)
    zs = [z for _f, _r, z in rows]
    assert zs == sorted(zs) and len(set(zs)) == len(zs) and apex[1] > zs[-1]
    assert all(yf < yr for yf, yr, _z in rows)

    def front_at(xc, zc):
        return min(v[1] for v in md.v if abs(v[0] - xc) < 2.0 and abs(v[2] - zc) < 1.5)
    dent = front_at(0.5 * L["x_in"], L["dent_z"]) - front_at(0.0, L["dent_z"])
    assert 0.35 < dent < 1.0                                                # leant-in dents at the seats
    top_mid = max(v[2] for v in md.v if abs(v[0]) < 5.0)
    top_end = max(v[2] for v in md.v if abs(v[0] - 90.0) < 5.0)
    assert top_end - top_mid > 0.2                                          # the roll sags mid-span


def test_back_and_deck_ends_are_buried_in_the_arms(parts, L):
    arms = {-1: planes(parts["ArmL"].md), 1: planes(parts["ArmR"].md)}
    xi = L["x_in"]
    for key, depth in (("Back", 9.5), ("Deck", 9.0)):
        ends = [v for v in parts[key].md.v if abs(v[0]) >= xi + depth]
        assert len(ends) > 20, key
        for v in ends:
            assert outside(arms[-1 if v[0] < 0 else 1], v) < 0.05, (key, v)
    # just inside the arm's face the back's front part is already inside it (between
    # the arm's tucked-under foot and its top roll, ahead of its rounded rear corner)
    near = [v for v in parts["Back"].md.v if xi + 0.5 <= abs(v[0]) <= xi + 4.5 and 8.0 < v[2] < 55.0 and v[1] < 36.0]
    assert len(near) > 20 and max(outside(arms[-1 if v[0] < 0 else 1], v) for v in near) < 0.05


def test_deck_under_the_cushions(parts, L):
    b = bounds(parts["Deck"].md)
    assert abs(b[2][0] - 3.5) < 1e-6 and 26.0 < b[2][1] < 26.4            # deck top at 26, 3 mm crown
    assert -47.2 < b[1][0] < -46.5                                         # 3 cm behind the arm noses
    seat_front = min(bounds(parts["SeatL"].md)[1][0], bounds(parts["SeatR"].md)[1][0])
    assert seat_front < b[1][0] - 0.5                                      # cushions overhang it a little


# -------------------------------------------------------------- seat cushions
def test_seat_cushions_size_height_and_fit(parts, L):
    xi = L["x_in"]
    for k, s in (("SeatL", -1.0), ("SeatR", 1.0)):
        md = parts[k].md
        b = bounds(md)
        assert abs(b[2][0] - L["z_deck"]) < 0.02                           # on the deck
        assert 16.0 < b[2][1] - b[2][0] < 18.0                              # 16 cm + crown
        front = max(v[2] for v in md.v if v[1] < -42.0)
        assert 41.5 < front < 42.5                                          # seat height 42
        assert -49.5 < b[1][0] < -47.5                                      # behind the arm noses
        if s < 0:
            assert b[0][0] >= -(xi - 0.4) and -0.3 < b[0][1] < -0.05        # between the arm and its twin
        else:
            assert b[0][1] <= xi - 0.4 and 0.05 < b[0][0] < 0.3
        assert 105.5 < b[0][1] - b[0][0] < 107.0
        # pressed against the raked back: never more than 3.5 mm into it, touching it
        d = [v[1] - fs.back_front_y(L, v[2], v[0]) for v in md.v]
        assert max(d) < 0.35 and max(d) > -0.2
        assert components(md) == 3                                          # body + two self-piped welts


def test_seat_cushions_sag_and_creases(parts, plain, L):
    hl, _t, _f = fs.seat_crease_lists(L, -1, 0)
    hr, _t, _f = fs.seat_crease_lists(L, 1, 0)
    assert hl[2] > 1.5 and 0.9 < hr[2] < 1.4                               # the left seat is used more
    for k, s, h in (("SeatL", -1, hl), ("SeatR", 1, hr)):
        a = fs.seat_cushion_md(L, s, 0, creases=False)
        assert a.v == plain[k].md.v                                         # what sofa_parts builds
        b = fs.seat_cushion_md(L, s, 0, creases=False, sag=False)
        dz, p = min((q[2] - p[2], p) for p, q in zip(b.v, a.v))
        assert math.hypot(p[0] - h[0], p[1] - h[1]) < 6.0, k                # sat in at the hollow ...
        assert 0.85 * h[2] < -dz < 1.05 * h[2], k                           # ... as deep as drawn
        front = [q[2] - p[2] for p, q in zip(b.v, a.v)
                 if p[1] < L["seat_yf"] + 1.0 and abs(p[0] - s * 0.5 * L["x_in"]) < 5.0]
        assert front and -0.9 < min(front) < -0.3                          # the front edge droops mid-span
    for k in ("SeatL", "SeatR"):
        a, b = plain[k].md, parts[k].md
        assert len(a.v) == len(b.v) and a.f == b.f
        moved = max(math.dist(p, q) for p, q in zip(a.v, b.v))
        assert 0.2 < moved < 0.7, k                                         # soft 2-7 mm creases
        for f in b.f:
            na = tri_normal(a.v[f[0]], a.v[f[1]], a.v[f[2]])
            nb = tri_normal(b.v[f[0]], b.v[f[1]], b.v[f[2]])
            assert _dot(na, nb) > 0.8, k                                    # nothing folds over


def test_grooves():
    lst = [(0.0, 0.0, 10.0, 0.0, 0.3, 1.0)]
    assert fs._grooves(5.0, 0.0, lst) == pytest.approx(0.3)
    assert fs._grooves(5.0, 3.5, lst) == 0.0 and fs._grooves(-1.0, 0.0, lst) == 0.0
    assert 0.0 < fs._grooves(1.0, 0.0, lst) < 0.3                          # fades at the ends


# ----------------------------------------------------------- scatter cushions
def _local(p):
    o, ax = p.origin, p.axes
    return [tuple(_dot(_sub(v, o), ax[k]) for k in range(3)) for v in p.md.v]


def test_scatter_cushions_shape_and_pose(parts, L):
    vel, lin = parts["ScatterVelvet"], parts["ScatterLinen"]
    for p, size, thick in ((vel, 50.0, 16.0), (lin, 48.0, 15.0)):
        loc = _local(p)
        ext = [max(v[k] for v in loc) - min(v[k] for v in loc) for k in range(3)]
        assert size - 5.0 < ext[0] <= size + 1.0 and size - 5.0 < ext[1] <= size + 1.0
        assert 0.7 * thick < ext[2] < 1.4 * thick
        assert p.tile == size
    # both at the left end, the velvet in the corner
    cv, cl = vel.origin, lin.origin
    assert -L["x_in"] < cv[0] < cl[0] < 0.0
    yaw = [math.degrees(math.atan2(p.axes[0][1], p.axes[0][0])) for p in (vel, lin)]
    lean = [math.degrees(math.asin(p.axes[2][2])) for p in (vel, lin)]
    assert abs(yaw[0] - yaw[1]) > 5.0 and abs(lean[0] - lean[1]) > 4.0   # turned and leant differently
    assert 15.0 < lean[0] < 30.0 and 8.0 < lean[1] < 22.0
    for p in (vel, lin):
        b = bounds(p.md)
        assert b[1][1] < L["y1"] and b[2][0] > L["z_deck"] + 10.0


def test_scatter_cushions_rest_on_their_supports(parts, L):
    seat = fl._Grid2(0, 1, 2.0).add(parts["SeatL"].md.v + parts["SeatR"].md.v)
    back = fl._Grid2(0, 2, 2.0).add(parts["Back"].md.v)
    arm = planes(parts["ArmL"].md)
    vel, lin = parts["ScatterVelvet"].md, parts["ScatterLinen"].md

    def gap(md, grid, a, b, c, sign):
        vals = []
        for v in md.v:
            pts = grid.near(v[a], v[b], 2.0)
            if pts:
                vals.append(sign * (v[c] - (max(p[c] for p in pts) if sign > 0 else min(p[c] for p in pts))))
        return min(vals) if vals else None

    for md in (vel, lin):
        assert -1.6 < gap(md, seat, 0, 1, 2, 1.0) < -1.0                   # sunk ~1.3 cm into the seat
        g = gap(md, back, 0, 2, 1, -1.0)
        assert g is not None and -0.75 < g < 0.3                            # leaning on the back roll
    depth = max(-outside(arm, v) for v in vel.v if v[0] < -L["x_in"] + 12.0)
    assert -0.4 < depth < 0.35                                              # the velvet leans into the arm
    assert all(outside(arm, v) > -0.35 for v in lin.v)
    vg = fl._Grid2(0, 2, 2.0).add(vel.v)
    g = gap(lin, vg, 0, 2, 1, -1.0)
    assert g is None or g > -0.75                                           # the linen does not pass through it


# --------------------------------------------------------- parameters, seeds
def test_width_parameter():
    ps = _by_name(fs.sofa_parts(width=220.0, seed=1))
    for p in ps.values():
        check_mesh(p.md)
    (x0, x1), (y0, y1), (z0, z1) = bounds([ps[k].md for k in BODY])
    assert -110.1 < x0 < -109.9 and 109.9 < x1 < 110.1 and abs(y1 - y0 - 100.0) < 1e-6 and z1 <= 72.0 + 1e-9
    b = bounds(ps["SeatR"].md)
    assert 80.5 < b[0][1] - b[0][0] < 82.0                                 # (220 - 2 x 28) / 2 seats
    assert bounds(ps["ScatterLinen"].md)[0][0] > -82.0
    with pytest.raises(ValueError):
        fs.sofa_layout(width=120.0)


def test_deterministic_and_seeded():
    a = fs.sofa_parts(seed=2, scatter=False)
    b = fs.sofa_parts(seed=2, scatter=False)
    assert all(pa.md.v == pb.md.v and pa.md.f == pb.md.f for pa, pb in zip(a, b))
    c = _by_name(fs.sofa_parts(seed=3, scatter=False))
    a = _by_name(a)
    for k in ("SeatL", "SeatR", "ArmL", "Back"):
        assert a[k].md.f == c[k].md.f and a[k].md.v != c[k].md.v, k        # same cage, own irregularities
    assert a["Plinth"].md.v == c["Plinth"].md.v


# ---------------------------------------------------------- the Max wrapper
class _FakeNode(object):
    def __init__(self, name):
        self.name = name


def test_build_wrapper_registers_every_part(monkeypatch):
    built = []

    def fake_build(md, name, uv_tile=None):
        built.append((name, uv_tile))
        return _FakeNode(name)

    monkeypatch.setattr(fl, "_build", fake_build)
    monkeypatch.setattr(fl, "rt", types.SimpleNamespace(Matrix3=lambda *a: a, Point3=lambda *a: a))
    monkeypatch.setattr(kit, "soften", lambda node, *a, **k: node)
    monkeypatch.setattr(kit, "group", lambda name, nodes: types.SimpleNamespace(name=name, nodes=list(nodes)))
    start = len(kit.PARTS)
    try:
        g = fs.build_sofa()
        reg = kit.PARTS[start:]
        g2 = fs.build_sofa(width=240.0, seed=1, scatter=False)
    finally:
        del kit.PARTS[start:]
    assert g.name == "BenchSofa" and [n.name for n in g.nodes] == ["BenchSofa_" + k for k in NAMES]
    assert len(g2.nodes) == len(BODY)
    keys = {n.name: (m, t, mt) for n, m, t, mt in reg}
    assert keys["BenchSofa_Plinth"] == ("metal_black", fs.METAL, 4)       # box-mapped
    for k in BODY[1:]:
        assert keys["BenchSofa_" + k] == ("chenille", None, None)          # own UVs
    assert keys["BenchSofa_ScatterVelvet"] == ("cushion", None, None)
    assert keys["BenchSofa_ScatterLinen"] == ("linen", None, None)
    tiles = dict(built[:len(NAMES)])
    assert tiles["BenchSofa_Plinth"] is None and tiles["BenchSofa_Back"] == fs.CHENILLE
    assert tiles["BenchSofa_ScatterVelvet"] == 50.0 and tiles["BenchSofa_ScatterLinen"] == 48.0
    assert all(m in kit.MAT_KEYS for m, _t, _mt in keys.values())


def test_seat_cushion_uv_seam_at_the_rear(parts, L):
    """The wrapped boxing strip's U seam (its U jumps by the perimeter) sits at a rear
    corner, against the back, not on a front corner."""
    z0 = L["z_deck"]
    z1 = z0 + L["seat_t"]
    for k in ("SeatL", "SeatR"):
        md = parts[k].md
        us = {}
        for f, uv in zip(md.f, md.fuv):
            if uv is not None and all(z0 + 2.5 < md.v[i][2] < z1 - 2.5 for i in f):   # boxing strip only
                for i, t in zip(f, uv):
                    us.setdefault(i, []).append(t[0])
        seam = [md.v[i] for i, u in us.items() if max(u) - min(u) > 5.0]
        assert seam, k
        assert all(v[1] > L["seat_yr"] - 12.0 for v in seam), k
