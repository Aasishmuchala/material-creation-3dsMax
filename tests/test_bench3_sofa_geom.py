"""Off-Max geometry tests for tools/apartment/furn_bench3_sofa.py (the long curved
boucle sofa of benchmark 3). pymxs is stubbed while the module is imported (and the
previous entry put back), so only the pure-Python cage generators run; the
build_curved_sofa wrapper is exercised with furn_living._build / kit.soften / kit.group
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
    import furn_bench3_sofa as fs  # noqa: E402
finally:
    if _prev is None:
        sys.modules.pop("pymxs", None)
    else:
        sys.modules["pymxs"] = _prev

SEATS = ("SeatL", "SeatC", "SeatR")
BODY = ("Plinth", "Base", "Back") + SEATS
CUSH = tuple("Cushion" + c[0] for c in fs.CUSHIONS)
NAMES = BODY + CUSH


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


def polar_of(L, v):
    """(radius, angle) of a point about the sofa's circle centre (angle from +Y to +X)."""
    x, y = v[0], v[1] - L["yc"]
    return math.hypot(x, y), math.atan2(x, y)


def nose_coords(L, v):
    """(along, lateral, distance from the axis) of v relative to the nose on its side:
    along = how far beyond the arm's path end, lateral = towards the seat from the nose's
    axis line."""
    sign = 1.0 if v[0] >= 0.0 else -1.0
    (px, py), t, m, _turn = fs.path_frame(L, sign * L["S"])
    a = 0.5 * L["T_arm"]
    q = (px + a * m[0], py + a * m[1])
    along = (v[0] - px) * sign * t[0] + (v[1] - py) * sign * t[1]
    lat = (v[0] - q[0]) * m[0] + (v[1] - q[1]) * m[1]
    return along, lat, math.hypot(v[0] - q[0], v[1] - q[1])


def inside_body(L, v, margin=0.0):
    """True when v lies inside the back / arm material by at least `margin` cm in plan:
    between the outer surface and the inner face of the section, or inside a nose."""
    d, s, _m = fs.path_dist(L, v[0], v[1])
    lim, out = fs.front_d(L, v[2], s), fs.outer_d(L, v[2], s)
    if lim is None:
        return False
    along, _lat, dist = nose_coords(L, v)
    if along > 0.0 and abs(s) >= L["S"] - 1e-6:
        return dist < 0.5 * L["T_arm"] - out - margin
    return out + margin < d < lim - margin


# ------------------------------------------------------------------ fixtures
def _by_name(parts):
    return {p.name.split("_", 1)[1]: p for p in parts}


@pytest.fixture(scope="module")
def L():
    return fs.sofa_layout()


@pytest.fixture(scope="module")
def parts():
    return _by_name(fs.curved_sofa_parts())


@pytest.fixture(scope="module")
def plain():
    return _by_name(fs.curved_sofa_parts(cushions=False, sag=False))


# ------------------------------------------------------- inventory / hygiene
def test_inventory_and_material_keys(parts):
    assert set(parts) == set(NAMES) and len(CUSH) == 7
    mats = {k: p.mat for k, p in parts.items()}
    assert mats["Plinth"] == "metal_black"
    assert all(mats[k] == "upholstery_alt" for k in BODY[1:])
    cm = [mats[k] for k in CUSH]
    assert cm.count("linen") == 2 and cm.count("upholstery_alt") == 5     # a few linen, most boucle
    for k, p in parts.items():
        assert p.mat in kit.MAT_KEYS, k
        assert p.tile > 0 and p.smooth in (0, 1), k
        name, mat, md, tile, smooth = p                       # unpacks like the other bench parts
        assert name == "CurvedSofa_" + k and md is p.md
    assert not parts["Plinth"].own_uv and parts["Plinth"].tile == fs.METAL
    for k in BODY[1:]:
        p = parts[k]
        assert p.own_uv and p.tile == fs.BOUCLE and p.noise and p.smooth == 1 and p.axes is None, k
    for k in CUSH:
        p = parts[k]
        assert p.smooth == 0 and p.own_uv and p.origin is not None and p.noise == fs.PILLOW_NOISE
        assert p.tile == (fs.BOUCLE if p.mat == "upholstery_alt" else fs.LINEN)
        ax = p.axes
        for i in range(3):                                    # orthonormal, right-handed node frame
            for j in range(3):
                assert abs(_dot(ax[i], ax[j]) - (1.0 if i == j else 0.0)) < 1e-9
        cr = (ax[0][1] * ax[1][2] - ax[0][2] * ax[1][1], ax[0][2] * ax[1][0] - ax[0][0] * ax[1][2],
              ax[0][0] * ax[1][1] - ax[0][1] * ax[1][0])
        assert _dot(cr, ax[2]) > 0.999


def test_meshes_closed_finite_and_outward(parts):
    vols = {k: check_mesh(p.md) for k, p in parts.items()}
    assert 80000.0 < vols["Plinth"] < 130000.0                # ~315 x 79 x 4.1, recessed
    assert 330000.0 < vols["Base"] < 450000.0                 # ~320 x 77 x 17
    assert 650000.0 < vols["Back"] < 900000.0                 # ~23-30 thick, 68 high, ~540 cm path
    for k in SEATS:
        assert 100000.0 < vols[k] < 135000.0, k               # ~92 x 68 x 19 wedge, crowned
    for k in CUSH:
        assert 8000.0 < vols[k] < 32000.0, k
    assert sum(len(p.md.f) for p in parts.values()) < 60000  # cage budget before TurboSmooth


def test_every_face_fans_cleanly(parts):
    """_build fans every polygon from its first vertex: no zero-area or flipped fan
    triangles (the bent slab caps and the nose poles included)."""
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
def test_footprint_orientation_and_heights(parts, L):
    body = [parts[k].md for k in BODY]
    (x0, x1), (y0, y1), (z0, z1) = bounds(body)
    assert -170.15 < x0 < -169.85 and 169.85 < x1 < 170.15               # chord 340
    assert abs(y0 + y1) < 0.4 and 132.0 < y1 - y0 < 134.5                 # bbox centred, 133 deep in plan
    assert abs(z0) < 1e-9 and 71.6 < z1 <= 72.0 + 1e-9                    # back 72
    assert bounds([parts[k].md for k in CUSH])[1][1] < y1 - 15.0
    # 95 deep radially: seat fronts on Ri, back's outer face on Ro
    r_seat = min(polar_of(L, v)[0] for k in SEATS for v in parts[k].md.v)
    r_back = max(polar_of(L, v)[0] for v in parts["Back"].md.v if abs(v[0]) < 100.0)
    assert abs(r_seat - L["Ri"]) < 0.05 and abs(r_back - L["Ro"]) < 0.2
    assert abs(L["Ro"] - L["Ri"] - 95.0) < 1e-9
    # the arc bulges to +Y (the circle centre is in front, on the -Y axis) ...
    back = parts["Back"].md.v
    assert L["yc"] < y0 and max(back, key=lambda v: v[1])[0] == pytest.approx(0.0, abs=10.0)
    ends = [v[1] for v in back if abs(v[0]) > 165.0]
    assert ends and max(ends) < y1 - 25.0
    # ... and the seat faces the centre: front -Y at rotation 0
    cy = lambda vs: sum(v[1] for v in vs) / len(vs)
    assert cy(parts["SeatC"].md.v) < cy([v for v in back if abs(v[0]) < 30.0]) - 40.0
    assert abs(sum(v[0] for v in parts["SeatC"].md.v) / len(parts["SeatC"].md.v)) < 0.5
    # upholstery floats on the plinth: only the plinth reaches the floor
    assert abs(bounds([parts[k].md for k in BODY[1:]])[2][0] - L["z_b"]) < 1e-6 and L["z_b"] == 4.0


def test_plinth_is_recessed_and_eased(parts, L):
    md = parts["Plinth"].md
    b = bounds(md)
    assert abs(b[2][0]) < 1e-9 and abs(b[2][1] - 4.1) < 1e-6                # 4 cm, 1 mm into the upholstery
    ds = [fs.path_dist(L, v[0], v[1])[0] for v in md.v]
    assert min(ds) > 6.9                                                    # 7 cm in from the back and ends
    assert min(polar_of(L, v)[0] for v in md.v) > L["Ri"] + 8.9             # 9 cm behind the seat fronts
    # 3 mm eases: the top cap sits 3 mm in from the widest ring
    tops = [v for v in md.v if v[2] > 4.0]
    zw = [v for v in md.v if 0.2 < v[2] < 3.9]
    assert zw and min(fs.path_dist(L, v[0], v[1])[0] for v in tops) > min(
        fs.path_dist(L, v[0], v[1])[0] for v in zw) + 0.25


# ------------------------------------------------------------------- the back
def test_path_frame_and_distance(L):
    S = L["S"]
    prev = None
    for i in range(401):
        s = -S + 2.0 * S * i / 400.0
        (px, py), t, m, turn = fs.path_frame(L, s)
        assert abs(math.hypot(*t) - 1.0) < 1e-9 and abs(math.hypot(*m) - 1.0) < 1e-9
        assert abs(t[0] * m[0] + t[1] * m[1]) < 1e-9 and t[0] * m[1] - t[1] * m[0] < 0.0   # m = t turned -90
        if prev is not None:                                                # continuous, unit speed
            (qx, qy), _t, _m, tq = prev
            assert abs(math.hypot(px - qx, py - qy) - 2.0 * S / 400.0) < 0.02
            assert abs(turn - tq) < 0.12
        prev = ((px, py), t, m, turn)
        for d in (3.0, 15.0, 22.0):                                         # path_dist inverts the frame
            dd, ss, mm = fs.path_dist(L, px + d * m[0], py + d * m[1])
            assert abs(dd - d) < 1e-6 and abs(ss - s) < 1e-6 and abs(mm[0] - m[0]) < 1e-9
    assert fs.path_frame(L, 0.0)[0] == pytest.approx((0.0, L["yc"] + L["Ro"]))
    assert fs.path_frame(L, S)[3] == pytest.approx(L["Th"] + 0.5 * math.pi)  # the arm runs to the front


def test_back_section(L):
    K = 2 * sum(fs.SEC)
    for s in (0.0, 0.5 * L["s_A"], L["s_A"], 0.5 * (L["s_A"] + L["s_B"]), L["s_B"], L["S"]):
        sec = fs.back_section(L, s)
        tb, rbi, h = fs.section_params(L, s)
        assert len(sec) == K
        assert sec[K // 2] == pytest.approx((0.5 * L["T_arm"], h))           # apex of the roll
        assert sec[0][1] == L["z_b"] and max(z for _d, z in sec) == pytest.approx(h)
        assert min(d for d, _z in sec) == pytest.approx(0.0) and max(d for d, _z in sec) == pytest.approx(tb)
        area = 0.5 * sum(sec[i][0] * sec[(i + 1) % K][1] - sec[(i + 1) % K][0] * sec[i][1] for i in range(K))
        assert area < 0.0                                                     # clockwise (d right, z up)
        for d, z in sec[K // 2 + 1:]:                                         # the inner side is front_d
            if z > L["z_b"] + 1e-6:
                assert fs.front_d(L, z, s) == pytest.approx(d, abs=1e-6)
        for d, z in sec[1:K // 2]:
            if z > L["z_b"] + 1e-6:
                assert fs.outer_d(L, z, s) == pytest.approx(d, abs=1e-6)
    # raked on the back: 30 thick at the foot, 23 under the roll; symmetric on the arms
    assert fs.front_d(L, 10.0, 0.0) > fs.front_d(L, 55.0, 0.0) + 5.0
    arm = fs.back_section(L, L["S"])
    for k in range(1, K // 2):
        assert arm[K - k] == pytest.approx((L["T_arm"] - arm[k][0], arm[k][1]))
    assert fs.section_params(L, 0.0)[2] == 72.0 and fs.section_params(L, L["S"])[2] == pytest.approx(65.0)
    assert fs.front_d(L, 73.0, 0.0) is None and fs.front_d(L, 3.0, 0.0) is None


def test_back_wraps_round_as_arms(parts, L):
    md = parts["Back"].md
    assert components(md) == 1                                               # one continuous piece
    b = bounds(md)
    assert abs(b[2][0] - L["z_b"]) < 1e-9 and 71.5 < b[2][1] <= 72.0 + 1e-9
    top_mid = max(v[2] for v in md.v if abs(v[0]) < 5.0)
    top_end = max(v[2] for v in md.v if 125.0 < abs(v[0]) < 135.0)
    assert top_end - top_mid > 0.2                                           # the roll sags mid-span
    a = 0.5 * L["T_arm"]
    for sign in (-1.0, 1.0):
        nose = [v for v in md.v if v[0] * sign > 0.0 and 0.05 < nose_coords(L, v)[0] < a + 0.5
                and abs(nose_coords(L, v)[1]) < a + 0.5]
        assert len(nose) > 60
        for v in nose:                                                       # a true round in plan
            assert nose_coords(L, v)[2] <= a + 1e-6
        tip = max(nose, key=lambda v: nose_coords(L, v)[0])
        assert nose_coords(L, tip)[0] == pytest.approx(a, abs=0.05)
        assert abs(polar_of(L, tip)[0] - (L["Ri"] + L["nose_back"])) < 0.6   # 2.5 behind the seat fronts
        assert max(v[2] for v in nose) < 65.0 + 1e-6                          # the arm is lower at the front
    assert min(v[1] for v in md.v) == pytest.approx(-L["foot_y"], abs=0.15)   # the noses are the lowest points


def test_back_uvs_run_along_the_path(parts, L):
    md = parts["Back"].md
    assert all(uv is not None for uv in md.fuv)
    vs = {}
    for f, uv in zip(md.f, md.fuv):
        for i, t in zip(f, uv):
            vs.setdefault(i, []).append(t[1])
    seam = [md.v[i] for i, v in vs.items() if max(v) - min(v) > 5.0]
    under = [v for v in seam if abs(v[2] - L["z_b"]) < 1e-6]
    assert len(under) > 100                                                  # V seam on the underside ...
    for v in seam:                                                           # ... and on the inner side of
        if v not in under:                                                   # each nose (its last meridian)
            along, lat, _dist = nose_coords(L, v)
            assert abs(along) < 1e-6 and lat > 0.0, v
    # U at true scale on the outer face (BOUCLE cm per unit)
    seen = 0
    for f, uv in zip(md.f, md.fuv):
        P = [md.v[i] for i in f]
        if len(f) == 4 and all(30.0 < p[2] < 50.0 for p in P) and abs(P[0][0]) < 100.0:
            if abs(P[0][2] - P[1][2]) < 1e-6:
                continue
            e = math.dist(P[1], P[2])
            if e > 1.0:
                assert abs(abs(uv[2][0] - uv[1][0]) * fs.BOUCLE - e) < 0.02 * e + 0.05
                seen += 1
    assert seen > 50


# ------------------------------------------------------------------- the base
def test_base_under_the_seats_and_buried_in_the_back(parts, L):
    md = parts["Base"].md
    b = bounds(md)
    assert abs(b[2][0] - L["z_b"]) < 1e-9 and L["z_deck"] < b[2][1] < L["z_deck"] + 0.35   # 3 mm crown
    assert abs(min(polar_of(L, v)[0] for v in md.v) - (L["Ri"] + 4.0)) < 0.05             # 4 cm behind the seats
    hidden = 0
    for v in md.v:                         # out of the seat region it is inside the back or an arm ...
        d, s, _m = fs.path_dist(L, v[0], v[1])
        lim = fs.front_d(L, v[2], s)
        along, lat, _dist = nose_coords(L, v)
        if along > 0.0 and abs(s) >= L["S"] - 1e-6:
            # ... and in front of an arm its front face runs into the round nose: its end
            # (14 in from the end line, 2.5 on the seat side of the nose's axis) stays inside
            assert lat > 2.0, v
            if lat < 5.0:
                assert inside_body(L, v, 0.2), v
        elif lim is not None and d < lim:          # (it crosses the inner face into the seat region)
            assert d > fs.outer_d(L, v[2], s) + 0.3, v
            hidden += 1
    assert hidden > 300
    assert components(md) == 1


# -------------------------------------------------------------- seat cushions
def _seam_dist(v, L, th):
    """Signed distance (cm, + to the right) of v from the radial seam at angle th."""
    r, a = polar_of(L, v)
    return r * math.sin(a - th)


def test_seat_cushions_size_height_and_fit(parts, L):
    for k in SEATS:
        md = parts[k].md
        b = bounds(md)
        assert abs(b[2][0] - L["z_deck"]) < 0.02                            # on the base
        assert 19.0 < b[2][1] - b[2][0] < 21.0                               # 19 cm + crown
        assert abs(min(polar_of(L, v)[0] for v in md.v) - L["Ri"]) < 0.05    # fronts on the front arc
        front = [v[2] for v in md.v if polar_of(L, v)[0] < L["Ri"] + 8.0]
        assert 39.0 < max(front) < 41.0                                      # seat height 40
        pen, arm = [], []
        for v in md.v:                       # pressed onto the raked back and the arms: <= 3.5 mm in
            d, s, _m = fs.path_dist(L, v[0], v[1])
            lim = fs.front_d(L, v[2], s)
            if lim is not None:
                pen.append(lim - d)
                if abs(s) > L["s_B"]:
                    arm.append(lim - d)
        assert 0.0 < max(pen) < 0.35, k
        if k == "SeatC":
            assert not arm or max(arm) < -20.0                               # clear of the arms
        else:
            assert arm and 0.0 < max(arm) < 0.35, k                          # the end ones touch an arm
        assert components(md) == 3, k                                        # body + two self-piped welts
    th = L["seam"]
    for a, c, t in (("SeatL", "SeatC", -th), ("SeatC", "SeatR", th)):       # 2-6 mm apart at the seams
        ra = max(_seam_dist(v, L, t) for v in parts[a].md.v)
        rc = min(_seam_dist(v, L, t) for v in parts[c].md.v)
        assert -0.3 < ra < 0.0 < rc < 0.3 and 0.15 < rc - ra < 0.6
    # three wedges following the arc: wider at the back than at the front
    for k in SEATS:
        md = parts[k].md
        fr = [v for v in md.v if polar_of(L, v)[0] < L["Ri"] + 3.0 and 26.0 < v[2] < 34.0]
        bk = [v for v in md.v if polar_of(L, v)[0] > L["seat_r1"] - 9.0 and 26.0 < v[2] < 34.0]
        span = lambda vs: math.dist(min(vs, key=lambda v: v[0]), max(vs, key=lambda v: v[0]))
        assert span(bk) > span(fr) + 15.0, k
    assert bounds(parts["SeatL"].md)[0] == pytest.approx((-bounds(parts["SeatR"].md)[0][1],
                                                           -bounds(parts["SeatR"].md)[0][0]), abs=0.05)


def test_seat_cushions_sag(parts, plain, L):
    for i, k in enumerate(SEATS):
        a, b = parts[k].md, plain[k].md
        assert a.f == b.f and len(a.v) == len(b.v)
        hx, hy, dep, _sx, _sy = fs.seat_hollow(L, i, 0)
        assert 0.8 < dep < 2.1
        dz, p = min((q[2] - p[2], p) for p, q in zip(b.v, a.v))
        assert 0.85 * dep < -dz < 1.05 * dep + 0.1, k                        # as deep as drawn ...
        sa, sb = fs.seat_sides(L, i)
        A, B = fs.sector_size(L, L["seat_r0"], L["seat_r1"], sa, sb)
        hw = fs.sector_map(L, A, B, L["seat_r0"], L["seat_r1"], sa, sb)(hx, hy)
        assert math.hypot(p[0] - hw[0], p[1] - hw[1]) < 7.0, k               # ... where drawn
        mid = 0.5 * (fs.side_angle(L, sa, 240.0) + fs.side_angle(L, sb, 240.0))
        front = [q[2] - p[2] for p, q in zip(b.v, a.v)
                 if polar_of(L, p)[0] < L["Ri"] + 8.0 and abs(polar_of(L, p)[1] - mid) < 0.03 and p[2] > 35.0]
        assert front and -(0.6 + 0.5 * dep) < min(front) < -0.15, k          # the front edge droops mid-span
    assert [fs.seat_hollow(L, i, 0)[2] for i in range(3)] != [fs.seat_hollow(L, i, 1)[2] for i in range(3)]


def test_seat_cushion_uv_seam_at_the_rear(parts, L):
    """The wrapped boxing strip's U seam (its U jumps by the perimeter) sits at a rear
    corner, against the back, not on a front corner."""
    z0 = L["z_deck"]
    z1 = z0 + L["seat_t"]
    for k in SEATS:
        md = parts[k].md
        assert all(uv is not None for uv in md.fuv[:len(md.fuv) // 2])
        us = {}
        for f, uv in zip(md.f, md.fuv):
            if uv is not None and all(z0 + 3.5 < md.v[i][2] < z1 - 6.0 for i in f):   # boxing strip only
                for i, t in zip(f, uv):
                    us.setdefault(i, []).append(t[0])
        seam = [md.v[i] for i, u in us.items() if max(u) - min(u) > 5.0]
        assert seam, k
        assert all(polar_of(L, v)[0] > L["seat_r1"] - 12.0 for v in seam), k


# ----------------------------------------------------------- back cushions
def _local(p):
    o, ax = p.origin, p.axes
    return [tuple(_dot(_sub(v, o), ax[k]) for k in range(3)) for v in p.md.v]


def test_back_cushions_shape_and_pose(parts, L):
    assert len({(c[2], c[3]) for c in fs.CUSHIONS}) >= 6                    # varying sizes
    for c in fs.CUSHIONS:
        nm, w, h, t = c[0], c[2], c[3], c[4]
        p = parts["Cushion" + nm]
        loc = _local(p)
        ext = [max(v[k] for v in loc) - min(v[k] for v in loc) for k in range(3)]
        assert w - 5.0 < ext[0] <= w + 1.0 and h - 5.0 < ext[1] <= h + 1.0, nm
        assert 0.7 * t < ext[2] < 1.4 * t, nm
        ax, o = p.axes, p.origin
        to_c = (-o[0], L["yc"] - o[1])
        ln, lh = math.hypot(*to_c), math.hypot(ax[2][0], ax[2][1])
        assert (ax[2][0] * to_c[0] + ax[2][1] * to_c[1]) / (ln * lh) > 0.95, nm   # faces the centre
        assert 10.0 < math.degrees(math.asin(ax[2][2])) < 28.0, nm                # leant back
        assert ax[1][2] > 0.85, nm                                                # standing up
        b = bounds(p.md)
        assert b[2][0] > L["seat_h"] - 2.0 and b[2][1] < L["seat_h"] + h + 2.0, nm
        # own UVs at real scale: one unit is `tile` cm of the face
        us = [t2[0] for uv in p.md.fuv if uv is not None for t2 in uv]
        vs = [t2[1] for uv in p.md.fuv if uv is not None for t2 in uv]
        assert abs((max(us) - min(us)) * p.tile - ext[0]) < 1.0, nm
        assert abs((max(vs) - min(vs)) * p.tile - ext[1]) < 1.0, nm
    # in a row along the back, left to right, the front ones before the back ones
    th = [polar_of(L, parts["Cushion" + c[0]].origin)[1] for c in fs.CUSHIONS if c[6] == "back"]
    assert th == sorted(th)
    arm = math.radians(1.0) + L["Th"] - math.asin(L["T_arm"] / L["r_ref"])
    assert all(abs(polar_of(L, v)[1]) < arm for k in CUSH for v in parts[k].md.v)


def _polar_grid(L, vs):
    rr = L["r_ref"]
    return fl._Grid2(0, 1, 2.0).add([(rr * polar_of(L, v)[1], v[2], polar_of(L, v)[0]) for v in vs])


def _gap(L, grid, vs):
    rr, out = L["r_ref"], None
    for v in vs:
        r, a = polar_of(L, v)
        pts = grid.near(rr * a, v[2], 2.0)
        if pts:
            g = min(p[2] for p in pts) - r
            out = g if out is None else min(out, g)
    return out


def test_back_cushions_rest_on_their_supports(parts, L):
    seat = fl._Grid2(0, 1, 2.0).add([v for k in SEATS for v in parts[k].md.v])
    for c in fs.CUSHIONS:
        md = parts["Cushion" + c[0]].md
        sinks = []
        for v in md.v:
            pts = seat.near(v[0], v[1], 2.0)
            if pts:
                sinks.append(v[2] - max(q[2] for q in pts))
        assert -1.6 < min(sinks) < -1.0, c[0]                                # sunk ~1.3 cm into the seat
        gb = []
        for v in md.v:
            d, s, _m = fs.path_dist(L, v[0], v[1])
            lim = fs.front_d(L, v[2], s)
            if lim is not None:
                gb.append(d - lim)
        if c[6] == "back":
            assert -0.75 < min(gb) < -0.45, c[0]                             # pressed 6 mm into the back
        else:
            assert min(gb) > 3.0, c[0]                                       # leant on the cushions behind
    names = [c[0] for c in fs.CUSHIONS]
    for j, nm in enumerate(names):                                            # no cushion passes through
        for prev in names[:j]:                                                # one placed before it
            g = _gap(L, _polar_grid(L, parts["Cushion" + prev].md.v), parts["Cushion" + nm].md.v)
            assert g is None or g > -0.75, (nm, prev)
    for nm, behind in (("F1", ("L2", "C1")), ("F2", ("R1", "R2"))):
        grid = _polar_grid(L, [v for b in behind for v in parts["Cushion" + b].md.v])
        assert -0.75 < _gap(L, grid, parts["Cushion" + nm].md.v) < -0.3, nm   # resting on them


# --------------------------------------------------------- parameters, seeds
def test_parameters():
    ps = _by_name(fs.curved_sofa_parts(chord=300.0, depth=90.0, seed=1, radius=260.0))
    for p in ps.values():
        check_mesh(p.md)
    L2 = fs.sofa_layout(300.0, 90.0, 260.0)
    (x0, x1), (y0, y1), (z0, z1) = bounds([ps[k].md for k in BODY])
    assert abs(x1 - x0 - 300.0) < 0.3 and abs(y0 + y1) < 0.4 and z1 <= 72.0 + 1e-9
    assert min(polar_of(L2, v)[0] for k in SEATS for v in ps[k].md.v) == pytest.approx(L2["Ri"], abs=0.05)
    loc = _local(ps["CushionL2"])
    assert max(v[0] for v in loc) - min(v[0] for v in loc) < 57.0                # smaller cushions
    for bad in (dict(chord=60.0), dict(depth=60.0), dict(chord=700.0), dict(radius=180.0)):
        with pytest.raises(ValueError):
            fs.sofa_layout(**bad)


def test_deterministic_and_seeded():
    a = fs.curved_sofa_parts(seed=2, cushions=False)
    b = fs.curved_sofa_parts(seed=2, cushions=False)
    assert all(pa.md.v == pb.md.v and pa.md.f == pb.md.f for pa, pb in zip(a, b))
    c = _by_name(fs.curved_sofa_parts(seed=3, cushions=False))
    a = _by_name(a)
    for k in SEATS + ("Back",):
        assert a[k].md.f == c[k].md.f and a[k].md.v != c[k].md.v, k        # same cage, own irregularities
    assert a["Plinth"].md.v == c["Plinth"].md.v and a["Base"].md.v == c["Base"].md.v


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
        g = fs.build_curved_sofa()
        reg = kit.PARTS[start:]
        g2 = fs.build_curved_sofa(chord=320.0, seed=1, cushions=False)
    finally:
        del kit.PARTS[start:]
    assert g.name == "CurvedSofa" and [n.name for n in g.nodes] == ["CurvedSofa_" + k for k in NAMES]
    assert len(g2.nodes) == len(BODY)
    keys = {n.name: (m, t, mt) for n, m, t, mt in reg}
    assert keys["CurvedSofa_Plinth"] == ("metal_black", fs.METAL, 4)       # box-mapped
    for k in BODY[1:]:
        assert keys["CurvedSofa_" + k] == ("upholstery_alt", None, None)    # own UVs
    for c in fs.CUSHIONS:
        assert keys["CurvedSofa_Cushion" + c[0]] == (c[1], None, None)
    tiles = dict(built[:len(NAMES)])
    assert tiles["CurvedSofa_Plinth"] is None and tiles["CurvedSofa_Back"] == fs.BOUCLE
    assert tiles["CurvedSofa_CushionR1"] == fs.LINEN and tiles["CurvedSofa_CushionC1"] == fs.BOUCLE
    assert all(m in kit.MAT_KEYS for m, _t, _mt in keys.values())
