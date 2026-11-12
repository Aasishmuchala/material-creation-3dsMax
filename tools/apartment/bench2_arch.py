"""Architecture for the moody benchmark-2 living room (MatForge, V-Ray, 3ds Max 2026).

Five pieces, each generated as pure-Python cages (furn_living._MD) by a
*_profile / *_md / *_parts function that runs without Max
(tests/test_bench2_arch_geom.py) and handed to Max by a thin build_* wrapper.
Parts are (node name, material key, _MD, tile cm, TurboSmooth iterations);
tile None means the cage carries its own UVs (kept: maptype None). No piece
uses TurboSmooth (it would melt the crisp plaster and metal profiles): every
node gets a Smooth modifier (auto 40 deg) instead, and every visible edge is
a real fillet in the section (1 mm on metal lips, 3 mm on plasterboard beads,
10 mm on the plaster panel).

  build_bulkhead(length, width=60, depth=25, gap=10, gap_depth=10, slot_y=0,
                 ceiling_z=0, spots=(), cove_led=False)
        plasterboard soffit band hanging `depth` below the ceiling along a
        wall: 3 mm beaded arrises, a 10 x 10 cm shadow gap (reveal) where its
        room face meets the main ceiling, a recessed 6 x 5 cm linear track
        slot lined with a black aluminium channel (1.5 mm walls, a 0.2 mm
        hairline to the plaster); optional track spots (x positions) and a
        warm LED strip on the reveal ledge. Origin: centre of its plan on the
        ceiling plane (z = ceiling_z, default 0: kit.place it at the ceiling
        height); wall at +Y (y = width/2), room face -Y; ends 1 mm into the
        end walls. Footprint length x width, z = -depth .. 0 (top and back
        run 1 mm into ceiling and wall).
  build_feature_wall(width, height, seed=0, proud=3.5, flip=False)
        copper Venetian plaster panel standing `proud` cm off the wall, every
        arris rounded 1 cm, cut by a sweeping S-groove 2 cm wide and 1.5 cm
        deep running from the top edge near one corner down and out through
        the opposite side (flip mirrors it): the groove is a sculpted joint
        between two plaster fields (0.9 cm shoulders either side of a 2 mm
        joint) over a backing slab, all one mesh so a single 200 cm box map
        runs across it. Origin: bottom centre ON the wall face (y = 0); face
        at y = -proud; x = -width/2 .. width/2, z = 0 .. height.
  build_shadow_skirting(rect_cm, openings=(), height=8, depth=1.5)
        black aluminium shadow-gap profile lining a recessed 1.5 x 8 cm reveal
        at the foot of the walls whose faces are rect_cm (scene cm): mitred
        corners, square ends at openings [(side, a0, a1)] as bench_arch's
        skirting. The reveal sits BEHIND the wall faces (u <= 0): the scene's
        wall plaster must stop at z = height + 0.15 (it bears on the
        profile's top flange). Already in place: leave the group at the origin.
  build_switch_plate(centre_z=105)
        square brushed-brass switch plate 8.6 x 8.6 x 0.6 cm, 3.5 mm corner
        radius, eased front edges, one tilted rocker; back face on the wall
        (y = 0), front -Y, centred on x = 0 at centre_z above the floor.
  build_marble_floor(rect_cm, seed=0, tile=(120, 60), gap=0.15, stagger=1/3,
                     along="x", lippage=0.02)
        polished marble tiles 120 x 60 x 2 cm, staggered rows, 1.5 mm open
        joints over a dark subfloor, eased 1 mm edges, sub-millimetre
        lippage; every tile is its own window (random offset, mirror / half
        turn) into a 120 cm texture repeat, written as cage UVs. Top at
        z = 0, already in place over rect_cm (scene cm).

Materials: paint_white (bulkhead), metal_black (track channel, spots,
reveal profile, subfloor), emissive_warm (spot lenses, cove LED),
copper_plaster (feature wall, declared here), metal_brass (switch),
marble_floor (tiles, declared here).
"""
import math

from pymxs import runtime as rt

import furn_living as FL
import kit
from bench_arch import (_earclip, _lathe, _opening_span, _outward, _perim_point, _profile, _rbox_md,
                        _rect, _sweep, _volume)          # _volume: re-exported for the tests
from furn_living import _MD, _Rand, _fillet2d, _smooth

# new material keys for the moody room (runtime only; kit.py is not edited)
kit.MAT_KEYS.setdefault("copper_plaster", "copper Venetian plaster (feature wall)")
kit.MAT_KEYS.setdefault("marble_floor", "polished white marble floor tiles")

PAINT = 120.0           # paint_white repeat
METAL = 25.0
PLASTER = 200.0         # copper_plaster box-map repeat
MARBLE = 120.0          # marble_floor texture repeat (cm of floor per UV unit)
EPS = 0.1               # buried faces run 1 mm into wall / ceiling / floor


# ===================================================================== helpers
def _merge(mds):
    out = _MD()
    for m in mds:
        out.merge(m)
    return out


def _signed_area(pts):
    a = 0.0
    for i in range(len(pts)):
        p, q = pts[i], pts[(i + 1) % len(pts)]
        a += p[0] * q[1] - q[0] * p[1]
    return 0.5 * a


def _clean_loop(pts, tol=1e-6):
    out = []
    for p in pts:
        if out and math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) < tol:
            continue
        out.append((float(p[0]), float(p[1])))
    while len(out) > 2 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) < tol:
        out.pop()
    return out


def _outline_solid(loop, prof_at, to3d):
    """Closed solid from a closed outline: loop [(a, b)] in a plane (wound
    either way), prof_at((a, b)) -> open section [(u, c)] at that outline
    vertex (u inwards from the outline, c off the plane; the same point count
    at every vertex, so the section may vary - a per-vertex arris radius),
    to3d(a, b, c) -> (x, y, z). The two end
    loops of the section are capped (ear-clipped faces), the result wound
    outward. Corners are mitred; raises ValueError where the section is
    deeper than the outline allows."""
    loop = _clean_loop(loop)
    if _signed_area(loop) < 0.0:
        loop = loop[::-1]
    n = len(loop)
    profs = [prof_at(p) for p in loop]
    npf = len(profs[0])
    if npf < 2 or any(len(p) != npf for p in profs):
        raise ValueError("section point count must be the same at every vertex")
    tang = []
    for i in range(n):
        a, b = loop[i], loop[(i + 1) % n]
        ln = math.hypot(b[0] - a[0], b[1] - a[1])
        tang.append(((b[0] - a[0]) / ln, (b[1] - a[1]) / ln, ln))
    offs = []
    for i in range(n):
        t1, t2 = tang[i - 1], tang[i]
        n1, n2 = (-t1[1], t1[0]), (-t2[1], t2[0])
        k = 1.0 + n1[0] * n2[0] + n1[1] * n2[1]
        if k < 0.1:
            raise ValueError("outline folds back at vertex %d" % i)
        offs.append(((n1[0] + n2[0]) / k, (n1[1] + n2[1]) / k))
    for i in range(n):                       # every edge keeps a positive length at depth
        t, m0, m1 = tang[i], offs[i], offs[(i + 1) % n]
        for j in range(npf):
            u0, u1 = profs[i][j][0], profs[(i + 1) % n][j][0]
            p0 = (loop[i][0] + u0 * m0[0], loop[i][1] + u0 * m0[1])
            p1 = (loop[(i + 1) % n][0] + u1 * m1[0], loop[(i + 1) % n][1] + u1 * m1[1])
            if (p1[0] - p0[0]) * t[0] + (p1[1] - p0[1]) * t[1] <= 1e-4:
                raise ValueError("section too deep for outline edge %d" % i)
    md = _MD()
    rings = [[md.add(to3d(loop[i][0] + u * offs[i][0], loop[i][1] + u * offs[i][1], c))
              for (u, c) in profs[i]] for i in range(n)]
    for i in range(n):
        ra, rb = rings[i], rings[(i + 1) % n]
        for j in range(npf - 1):
            md.face((ra[j], ra[j + 1], rb[j + 1], rb[j]))
    for j, flip in ((0, False), (npf - 1, True)):
        pts = [(loop[i][0] + profs[i][j][0] * offs[i][0], loop[i][1] + profs[i][j][0] * offs[i][1])
               for i in range(n)]
        for a, b, c in _earclip(pts):
            ia, ib, ic = rings[a][j], rings[b][j], rings[c][j]
            md.face((ia, ic, ib) if flip else (ia, ib, ic))
    return _outward(md)


def _arris(r, back, front=0.0, n=4):
    """Open section [(u, c)] of a slab edge: a quarter round of radius r from
    the front face (c = front, u = r) to the side, then straight back to c =
    back; c grows away from the room."""
    out = []
    for k in range(n + 1):
        ph = 0.5 * math.pi * k / n
        out.append((r * (1.0 - math.sin(ph)), front + r * (1.0 - math.cos(ph))))
    out.append((0.0, back))
    return out


def _plate_md(w, h, t, rc, rf, rb, x=0.0, z=0.0, y_back=0.0, n=3):
    """Rounded plate in the wall plane: w (x) by h (z), t thick from y_back
    towards -Y; corner radius rc in elevation, front edges rf, back edges rb."""
    hw, hh = 0.5 * w, 0.5 * h
    loop = _fillet2d([(x - hw, z - hh), (x + hw, z - hh), (x + hw, z + hh), (x - hw, z + hh)], [rc] * 4,
                     closed=True, step=math.radians(15.0))
    sec = []
    for k in range(n + 1):                   # front edge: front face -> side
        ph = 0.5 * math.pi * k / n
        sec.append((rf * (1.0 - math.sin(ph)), -t + rf * (1.0 - math.cos(ph))))
    for k in range(n + 1):                   # back edge: side -> back face (on the wall)
        ph = 0.5 * math.pi * k / n
        sec.append((rb * (1.0 - math.cos(ph)), -rb + rb * math.sin(ph)))
    sec = [(u, c + y_back) for (u, c) in sec]
    return _outline_solid(loop, lambda p: sec, lambda a, b, c: (a, c, b))


def _bbox(md):
    xs, ys, zs = zip(*md.v)
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


# ===================================================================== bulkhead
BH_SLOT_W, BH_SLOT_D = 6.0, 5.0      # clear inside of the track slot
BH_CHANNEL_T = 0.15                  # aluminium channel wall
BH_CLEAR = 0.02                      # hairline between channel and plaster
BH_ARRIS = 0.3                       # plasterboard corner-bead arris


def bulkhead_profile(width=60.0, depth=25.0, gap=10.0, gap_depth=10.0, slot_y=0.0):
    """Closed (y, z) section of the plasterboard bulkhead, z = 0 on the main
    ceiling, wall at y = width/2, room face at y = -width/2: soffit with the
    slot cut for the channel (1 mm arrises at its lips), 3 mm beaded arrises
    soffit / fascia / reveal ledge, a filleted internal corner at the back of
    the reveal; back and top run 1 mm into the wall and the ceiling."""
    W, D, G, GD = float(width), float(depth), float(gap), float(gap_depth)
    a = 0.5 * BH_SLOT_W + BH_CHANNEL_T + BH_CLEAR
    hs = BH_SLOT_D + BH_CHANNEL_T + BH_CLEAR
    if W < 30.0 or D < hs + 8.0 or not 2.0 <= G <= D - hs - 3.0 or not 2.0 <= GD <= 0.5 * W:
        raise ValueError("bulkhead too small for its slot / reveal: %r x %r" % (width, depth))
    if not (-0.5 * W + a + 2.0 <= slot_y <= 0.5 * W - a - 2.0):
        raise ValueError("track slot at y=%r does not fit the soffit" % slot_y)
    return _profile([
        (0.5 * W + EPS, EPS, 0.0),
        (0.5 * W + EPS, -D, 0.0),
        (slot_y + a, -D, 0.1),
        (slot_y + a, -D + hs, 0.0),
        (slot_y - a, -D + hs, 0.0),
        (slot_y - a, -D, 0.1),
        (-0.5 * W, -D, BH_ARRIS),
        (-0.5 * W, -G, BH_ARRIS),
        (-0.5 * W + GD, -G, 0.1),
        (-0.5 * W + GD, EPS, 0.0),
    ])


def channel_profile(depth=25.0, slot_y=0.0):
    """Closed (y, z) section of the black aluminium U channel lining the slot:
    6 cm clear, 5 cm deep from the soffit, 1.5 mm walls, rounded lips standing
    0.3 mm above the soffit plane."""
    D = float(depth)
    ai, t = 0.5 * BH_SLOT_W, BH_CHANNEL_T
    zl, zi = -D + 0.03, -D + BH_SLOT_D
    return _profile([
        (slot_y + ai + t, zl, 0.05), (slot_y + ai + t, zi + t, 0.1), (slot_y - ai - t, zi + t, 0.1),
        (slot_y - ai - t, zl, 0.05), (slot_y - ai, zl, 0.05), (slot_y - ai, zi, 0.05),
        (slot_y + ai, zi, 0.05), (slot_y + ai, zl, 0.05),
    ])


SPOT_R, SPOT_L = 2.6, 12.0           # track spot body radius, length below its adapter


def bulkhead_parts(length, width=60.0, depth=25.0, gap=10.0, gap_depth=10.0, slot_y=0.0, ceiling_z=0.0,
                   spots=(), cove_led=False):
    """[(name, key, md, tile, smooth)] of the bulkhead (see build_bulkhead)."""
    L, D, cz = float(length), float(depth), float(ceiling_z)
    if L < 30.0:
        raise ValueError("bulkhead too short: %r" % length)
    path = [(-0.5 * L - EPS, 0.0), (0.5 * L + EPS, 0.0)]
    to3d = lambda a, b, c: (a, b, c + cz)
    parts = [("Bulkhead_Board", "paint_white", _sweep(path, bulkhead_profile(width, depth, gap, gap_depth, slot_y),
                                                       to3d), PAINT, 0),
             ("Bulkhead_Track", "metal_black", _sweep(path, channel_profile(depth, slot_y), to3d), METAL, 0)]
    if spots:
        body, lens = [], []
        for x in spots:
            x = float(x)
            if abs(x) > 0.5 * L - 6.0:
                raise ValueError("spot at x=%r is outside the track" % x)
            za = cz - D + BH_SLOT_D - 0.1                     # magnetic adapter, just under the channel top
            body.append(_rbox_md(x - 2.0, x + 2.0, slot_y - 2.4, slot_y + 2.4, za - 3.4, za, 0.15))
            zb = za - 3.3                                     # body top, 1 mm up into the adapter
            body.append(_lathe([(0.0, 0.0), (SPOT_R, 0.0, 0.35), (SPOT_R, SPOT_L, 0.2), (SPOT_R - 0.3, SPOT_L, 0.06),
                                (SPOT_R - 0.3, SPOT_L - 1.6, 0.05), (0.0, SPOT_L - 1.6)],
                               (x, slot_y, zb), "-z", 32))
            lens.append(_lathe([(0.0, 0.0), (SPOT_R - 0.45, 0.0, 0.03), (SPOT_R - 0.45, 0.14, 0.03), (0.0, 0.14)],
                               (x, slot_y, zb - SPOT_L + 1.62), "-z", 32))   # 1.2 mm proud of the recess
        parts.append(("Bulkhead_Spots", "metal_black", _merge(body), METAL, 0))
        parts.append(("Bulkhead_SpotLens", "emissive_warm", _merge(lens), 10.0, 0))
    if cove_led:
        yb = -0.5 * float(width) + float(gap_depth)           # back of the reveal
        led = _rbox_md(-0.5 * L, 0.5 * L, yb - 2.4, yb - 0.4, cz - gap, cz - gap + 0.35, 0.08)
        parts.append(("Bulkhead_CoveLED", "emissive_warm", led, 10.0, 0))
    return parts


# ================================================================ feature wall
FW_PROUD = 3.5          # panel face off the surrounding wall
FW_ARRIS = 1.0          # panel arrises (fully rounded)
FW_GROOVE_W = 2.0       # groove width at the face
FW_GROOVE_D = 1.5       # groove depth: the floor of the joint
FW_JOINT = 0.2          # joint between the plaster fields: 0.9 cm shoulders either side
FW_CORNER = 1.6         # elevation radius of the panel corners and the groove run-outs


def _bez2(p0, p1, p2, p3, t):
    u = 1.0 - t
    return (u * u * u * p0[0] + 3.0 * u * u * t * p1[0] + 3.0 * u * t * t * p2[0] + t * t * t * p3[0],
            u * u * u * p0[1] + 3.0 * u * u * t * p1[1] + 3.0 * u * t * t * p2[1] + t * t * t * p3[1])


def groove_curve(width, height, seed=0, flip=False, step=2.5, ext=6.0):
    """Centre line [(x, z)] of the S-groove on a width x height panel
    (x = -width/2 .. width/2, z = 0 .. height): it leaves the top edge 18-34
    per cent of the width in from the left corner, falls steeply (50-64 deg),
    eases through the middle and steepens again to leave through the right
    side at 36-52 per cent of the height (flip mirrors it left for right).
    Sampled every ~`step` cm; one extra point `ext` cm past each edge along
    the end tangents (the joint outlines are clipped to the panel)."""
    W, H = float(width), float(height)
    if W < 60.0 or H < 60.0:
        raise ValueError("feature wall too small: %r x %r" % (width, height))
    rnd = _Rand(seed * 17 + 11)
    p0 = (-0.5 * W + W * rnd.uniform(0.18, 0.34), H)
    p3 = (0.5 * W, H * rnd.uniform(0.36, 0.52))
    dx, dz = p3[0] - p0[0], p3[1] - p0[1]
    chord = math.hypot(dx, dz)
    a_c = math.atan2(-dz, dx)                                  # chord angle below the horizontal
    a0 = math.radians(rnd.uniform(50.0, 64.0))
    a1 = min(a_c + math.radians(rnd.uniform(6.0, 16.0)), math.radians(50.0))
    l1, l2 = chord * rnd.uniform(0.34, 0.42), chord * rnd.uniform(0.30, 0.40)
    p1 = (p0[0] + l1 * math.cos(a0), p0[1] - l1 * math.sin(a0))
    p2 = (p3[0] - l2 * math.cos(a1), p3[1] + l2 * math.sin(a1))
    dense = [_bez2(p0, p1, p2, p3, k / 600.0) for k in range(601)]
    cum = [0.0]
    for a, b in zip(dense, dense[1:]):
        cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    n = max(12, int(math.ceil(cum[-1] / step)))
    pts, j = [], 0
    for k in range(n + 1):
        s = cum[-1] * k / n
        while j < len(cum) - 2 and cum[j + 1] < s:
            j += 1
        f = (s - cum[j]) / max(cum[j + 1] - cum[j], 1e-12)
        a, b = dense[j], dense[j + 1]
        pts.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
    pts[0], pts[-1] = p0, p3
    pts = ([(p0[0] - ext * math.cos(a0), p0[1] + ext * math.sin(a0))] + pts
           + [(p3[0] + ext * math.cos(a1), p3[1] - ext * math.sin(a1))])
    for x, z in pts[2:-2]:
        if not (-0.5 * W + 3.0 < x < 0.5 * W and 3.0 < z < H):
            raise ValueError("groove leaves the panel at (%.1f, %.1f): panel too narrow" % (x, z))
    return [(-x, z) for x, z in pts] if flip else pts


def _offset_polyline(pts, d):
    """Open 2-D polyline offset by d to the left of its direction."""
    out, n = [], len(pts)
    for i in range(n):
        a, b = pts[max(i - 1, 0)], pts[min(i + 1, n - 1)]
        tx, tz = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(tx, tz)
        out.append((pts[i][0] - tz / ln * d, pts[i][1] + tx / ln * d))
    return out


def _cross_rect(p_out, p_in, W, H):
    """Where the segment from an outside point to an inside point enters the
    rectangle x = -W/2 .. W/2, z = 0 .. H (snapped onto the boundary)."""
    best = None
    for k, lim in ((0, -0.5 * W), (0, 0.5 * W), (1, 0.0), (1, H)):
        d = p_in[k] - p_out[k]
        if abs(d) < 1e-12:
            continue
        t = (lim - p_out[k]) / d
        if not 0.0 <= t <= 1.0:
            continue
        q = [p_out[0] + (p_in[0] - p_out[0]) * t, p_out[1] + (p_in[1] - p_out[1]) * t]
        q[k] = lim
        if -0.5 * W - 1e-9 <= q[0] <= 0.5 * W + 1e-9 and -1e-9 <= q[1] <= H + 1e-9:
            if best is None or t > best[0]:
                best = (t, (q[0], q[1]))
    return best[1]


def _clip_run(pts, W, H):
    """The stretch of an open polyline inside the panel, with its entry and
    exit points on the boundary; it must cross the boundary exactly twice."""
    ins = [-0.5 * W < x < 0.5 * W and 0.0 < z < H for x, z in pts]
    if ins[0] or ins[-1] or not any(ins):
        raise ValueError("groove must run from edge to edge")
    i0 = ins.index(True)
    i1 = len(ins) - 1 - ins[::-1].index(True)
    if not all(ins[i0:i1 + 1]):
        raise ValueError("groove leaves the panel")
    return [_cross_rect(pts[i0 - 1], pts[i0], W, H)] + pts[i0:i1 + 1] + [_cross_rect(pts[i1 + 1], pts[i1], W, H)]


def _perim_s(p, W, H):
    """Counter-clockwise arc length round the panel from its bottom-left corner."""
    x, z = p
    d = [abs(z), abs(x - 0.5 * W), abs(z - H), abs(x + 0.5 * W)]
    k = d.index(min(d))
    return (x + 0.5 * W, W + z, W + H + 0.5 * W - x, 2.0 * W + H + H - z)[k]


def _corners_between(sa, sb, W, H):
    """Panel corners met walking counter-clockwise from sa to sb."""
    P = 2.0 * (W + H)
    span = (sb - sa) % P
    out = []
    for s, c in ((0.0, (-0.5 * W, 0.0)), (W, (0.5 * W, 0.0)), (W + H, (0.5 * W, H)), (2.0 * W + H, (-0.5 * W, H))):
        d = (s - sa) % P
        if 1e-9 < d < span - 1e-9:
            out.append((d, c))
    return [c for _d, c in sorted(out)]


def _edge_of(p, W, H):
    """Panel edge a boundary point lies on: 0 bottom, 1 right, 2 top, 3 left."""
    d = [abs(p[1]), abs(p[0] - 0.5 * W), abs(p[1] - H), abs(p[0] + 0.5 * W)]
    return d.index(min(d))


def _line_cross(pts, axis, val, from_end=False):
    """First (or last) point where an open polyline crosses coord[axis] = val."""
    rng = range(len(pts) - 1)
    for i in (reversed(rng) if from_end else rng):
        a, b = pts[i], pts[i + 1]
        da, db = a[axis] - val, b[axis] - val
        if da * db <= 0.0 and da != db:
            t = da / (da - db)
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
    raise ValueError("groove does not reach the panel edge")


def _closest_on(pts, p):
    """(parameter i + t, point) of the point of an open polyline nearest p."""
    best = None
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        ax, az = b[0] - a[0], b[1] - a[1]
        l2 = ax * ax + az * az
        t = max(0.0, min(1.0, ((p[0] - a[0]) * ax + (p[1] - a[1]) * az) / l2)) if l2 > 0.0 else 0.0
        q = (a[0] + ax * t, a[1] + az * t)
        d = math.hypot(q[0] - p[0], q[1] - p[1])
        if best is None or d < best[0]:
            best = (d, i + t, q)
    return best[1], best[2]


def _arc_between(c, p, q, step=math.radians(15.0)):
    """Points of the shorter circular arc round c from p to q (ends kept)."""
    r = 0.5 * (math.hypot(p[0] - c[0], p[1] - c[1]) + math.hypot(q[0] - c[0], q[1] - c[1]))
    a0 = math.atan2(p[1] - c[1], p[0] - c[0])
    sw = math.atan2(q[1] - c[1], q[0] - c[0]) - a0
    sw = (sw + math.pi) % (2.0 * math.pi) - math.pi
    n = max(1, int(math.ceil(abs(sw) / step)))
    return [p] + [(c[0] + r * math.cos(a0 + sw * k / n), c[1] + r * math.sin(a0 + sw * k / n))
                  for k in range(1, n)] + [q]


def feature_wall_outlines(width, height, seed=0, flip=False):
    """(field left of the groove, field right of it, groove centre line):
    the two plaster fields as closed counter-clockwise (x, z) outlines, the
    joint FW_JOINT wide between them all along. Where the joint runs out
    through a panel edge each field turns onto the edge on an exact fillet
    (FW_CORNER: the circle tangent to the edge and to the joint), and the
    panel corners are rounded FW_CORNER in elevation."""
    W, H, R = float(width), float(height), FW_CORNER
    curve = groove_curve(W, H, seed, flip)
    edge_val = (0.0, 0.5 * W, H, -0.5 * W)
    fields = []
    for side in (1.0, -1.0):
        run = _offset_polyline(curve, side * 0.5 * FW_JOINT)          # the field's edge along the joint
        cen = _offset_polyline(curve, side * (0.5 * FW_JOINT + R))    # fillet centres lie on this
        clipped = _clip_run(run, W, H)
        ends = []
        for at_end, j in ((False, clipped[0]), (True, clipped[-1])):
            k = _edge_of(j, W, H)
            axis = 1 if k in (0, 2) else 0
            inset = edge_val[k] + (R if k in (0, 3) else -R)
            c = _line_cross(cen, axis, inset, at_end)
            te = (c[0], edge_val[k]) if axis == 1 else (edge_val[k], c[1])
            s, tr = _closest_on(run, c)
            ends.append((te, c, tr, s))
        (te0, c0, tr0, s0), (te1, c1, tr1, s1) = ends
        mid = [p for i, p in enumerate(run) if s0 < i < s1
               and math.hypot(p[0] - tr0[0], p[1] - tr0[1]) > 0.5 and math.hypot(p[0] - tr1[0], p[1] - tr1[1]) > 0.5]
        loop = _arc_between(c0, te0, tr0) + mid + _arc_between(c1, tr1, te1)
        if side < 0.0:
            loop = loop[::-1]
        corners = _corners_between(_perim_s(loop[-1], W, H), _perim_s(loop[0], W, H), W, H)
        radii = [0.0] * len(loop) + [R] * len(corners)
        fields.append(_clean_loop(_fillet2d(loop + corners, radii, closed=True, step=math.radians(15.0))))
    return fields[0], fields[1], curve


def _seg_dist(p, a, b):
    ax, az = b[0] - a[0], b[1] - a[1]
    l2 = ax * ax + az * az
    t = max(0.0, min(1.0, ((p[0] - a[0]) * ax + (p[1] - a[1]) * az) / l2)) if l2 > 0.0 else 0.0
    return math.hypot(p[0] - a[0] - ax * t, p[1] - a[1] - az * t)


def _dist_polyline(p, pts):
    return min(_seg_dist(p, a, b) for a, b in zip(pts, pts[1:]))


def feature_wall_parts(width, height, seed=0, proud=FW_PROUD, flip=False):
    """[(name, key, md, tile, smooth)]: ONE mesh of three closed shells - the
    two plaster fields (face at y = -proud, 1 cm arrises on the panel edges
    easing to 0.9 cm shoulders along the joint, backs on the groove floor)
    and the backing slab (groove floor back to 1 mm into the wall, y = 0.1)."""
    W, H, P = float(width), float(height), float(proud)
    if not 2.5 <= P <= 6.0:
        raise ValueError("feature wall should stand 2.5-6 cm proud, not %r" % proud)
    left, right, curve = feature_wall_outlines(W, H, seed, flip)
    rg = 0.5 * (FW_GROOVE_W - FW_JOINT)
    yb = -P + FW_GROOVE_D

    def section(p):
        d = _dist_polyline(p, curve)
        return _arris(rg + (FW_ARRIS - rg) * _smooth((d - 0.5 * FW_JOINT) / 4.0), yb, -P)

    to3d = lambda a, b, c: (a, c, b)
    shells = [_outline_solid(o, section, to3d) for o in (left, right)]
    rect = _fillet2d([(-0.5 * W, 0.0), (0.5 * W, 0.0), (0.5 * W, H), (-0.5 * W, H)], [FW_CORNER] * 4,
                     closed=True, step=math.radians(15.0))
    shells.append(_outline_solid(rect, lambda p: [(0.0, yb), (0.0, EPS)], to3d))
    return [("FeatureWall", "copper_plaster", _merge(shells), PLASTER, 0)]


# ============================================================ shadow skirting
SK_H, SK_D, SK_T = 8.0, 1.5, 0.15   # reveal height, depth behind the wall face, profile wall


def shadow_profile(height=SK_H, depth=SK_D):
    """Closed (u, z) section of the aluminium shadow-gap profile, u off the
    wall face (u <= 0 runs into the wall): a foot 3 mm under the floor
    surface, the reveal floor flush with it, the recessed web `depth` behind
    the wall face (filleted internal corners), the top flange whose 1.5 mm
    nose meets the wall face with a 1 mm arris and carries the plaster above
    (its top and back buried)."""
    h, d, t = float(height), float(depth), SK_T
    if not 4.0 <= h <= 20.0 or not 0.8 <= d <= 4.0:
        raise ValueError("shadow gap %r deep x %r high is out of range" % (depth, height))
    return _profile([
        (0.0, -0.3, 0.0),               # foot, under the floor surface
        (0.0, 0.0, 0.0),                # flush with the floor
        (-d, 0.0, 0.05),                # reveal floor / web (internal)
        (-d, h, 0.05),                  # web / flange underside (internal)
        (0.0, h, 0.1),                  # flange nose arris
        (0.0, h + t, 0.0),              # the plaster starts here
        (-d - t, h + t, 0.0),
        (-d - t, -0.3, 0.0),
    ])


def shadow_skirting_md(rect_cm, openings=(), height=SK_H, depth=SK_D):
    """The reveal profile round the wall faces rect_cm (scene cm), mitred at
    the corners, stopped square (closed ends) at openings [(side, a0, a1)] as
    bench_arch.skirting_md; each run its own closed shell, all in one mesh."""
    x0, y0, x1, y1 = _rect(rect_cm)
    prof = shadow_profile(height, depth)
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    W, D = x1 - x0, y1 - y0
    P = 2.0 * (W + D)
    xyz = lambda a, b, c: (a, b, c)
    spans = sorted(s for s in (_opening_span(o, x0, y0, x1, y1) for o in openings) if s)
    merged = []
    for a, b in spans:
        if merged and a <= merged[-1][1] + 1e-6:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    if not merged:
        return _sweep(corners, prof, xyz, closed=True)
    cs = [0.0, W, W + D, 2.0 * W + D]
    cs += [c + P for c in cs]
    md = _MD()
    for k in range(len(merged)):
        sa = merged[k][1]
        sb = merged[(k + 1) % len(merged)][0] + (P if k == len(merged) - 1 else 0.0)
        if sb - sa < 2.0:
            continue
        path = [_perim_point(sa, x0, y0, x1, y1)]
        path += [_perim_point(c, x0, y0, x1, y1) for c in cs if sa + 1e-6 < c < sb - 1e-6]
        path.append(_perim_point(sb, x0, y0, x1, y1))
        md.merge(_sweep(path, prof, xyz, closed=False))
    return md


def shadow_skirting_parts(rect_cm, openings=(), height=SK_H, depth=SK_D):
    return [("ShadowSkirting", "metal_black", shadow_skirting_md(rect_cm, openings, height, depth), METAL, 0)]


# ================================================================ switch plate
SW_SIZE, SW_T = 8.6, 0.6            # square plate, thickness
SW_ROCKER = (5.4, 5.4, 0.45)        # rocker width, height, height proud of the plate face
SW_TILT = 2.0                       # rocker rocked 2 deg about X: top edge out


def switch_parts(centre_z=105.0):
    """Brass plate 8.6 x 8.6 x 0.6 cm (3.5 mm corners, 1.2 mm eased front
    edges, 0.3 mm on the back) with one square rocker sunk 2.5 mm into it
    and rocked 2 deg; back face on the wall at y = 0, centre (0, centre_z)."""
    zc = float(centre_z)
    plate = _plate_md(SW_SIZE, SW_SIZE, SW_T, 0.35, 0.12, 0.03, 0.0, zc, 0.0)
    rw, rh, rp = SW_ROCKER
    rocker = _plate_md(rw, rh, rp + 0.25, 0.3, 0.1, 0.03)       # built round the origin, back on y = 0
    ca, sa = math.cos(math.radians(SW_TILT)), math.sin(math.radians(SW_TILT))
    rocker.map(lambda p: (p[0], p[1] * ca - p[2] * sa - SW_T + 0.25, p[1] * sa + p[2] * ca + zc))
    return [("SwitchPlate", "metal_brass", plate, METAL, 0), ("SwitchPlate_Rocker", "metal_brass", rocker, METAL, 0)]


# ================================================================ marble floor
FLOOR_T = 2.0                       # tile thickness, top at z = 0
FLOOR_EASE = 0.1                    # rounded (eased) tile edges
SUB_TOP, SUB_BOT = -1.4, -2.6       # dark subfloor under the open joints


def _grid_joints(lo, hi, pitch, base, min_piece):
    """Joints of a grid of `pitch` through `base` strictly inside lo..hi,
    leaving out any closer than min_piece to an end (the sliver joins its
    neighbour, as a tiler would)."""
    out = []
    k = int(math.floor((lo - base) / pitch)) - 1
    while True:
        j = base + k * pitch
        if j >= hi - min_piece:
            return out
        if j > lo + min_piece:
            out.append(j)
        k += 1


def floor_layout(rect_cm, seed=0, tile=(120.0, 60.0), stagger=1.0 / 3.0, along="x", min_piece=6.0):
    """Cells of the staggered tile layout over rect_cm, centred on the room:
    [dict(x0, x1, y0, y1 (cell, joints on its edges), row, ta, tb (origin of
    the full tile the cell is cut from, along / across), u0, v0 (its UV
    window), fa, fb (mirrored along / across), dz, gx, gy (lippage plane))]."""
    X0, Y0, X1, Y1 = _rect(rect_cm)
    pa, pb = float(tile[0]), float(tile[1])
    if along not in ("x", "y") or pa < pb or pb < 2.0 * min_piece or not 0.0 <= stagger < 1.0:
        raise ValueError("bad floor layout parameters")
    A0, A1, B0, B1 = (X0, X1, Y0, Y1) if along == "x" else (Y0, Y1, X0, X1)
    rnd = _Rand(seed * 7919 + 13)
    rem = (B1 - B0) % pb
    # cut rows at both walls alike, and none narrower than a third of a tile
    base_b = B0 + 0.5 * rem + (0.5 * pb if 0.5 * rem < max(min_piece, pb / 3.0) else 0.0)
    rows = [B0] + _grid_joints(B0, B1, pb, base_b, min_piece) + [B1]
    rem_a = (A1 - A0) % pa
    cells = []
    for r in range(len(rows) - 1):
        b0, b1 = rows[r], rows[r + 1]
        base_a = A0 + 0.5 * rem_a + ((r * stagger) % 1.0) * pa
        cols = [A0] + _grid_joints(A0, A1, pa, base_a, min_piece) + [A1]
        for c in range(len(cols) - 1):
            a0, a1 = cols[c], cols[c + 1]
            cell = dict(row=r, ta=a0 if a0 > A0 + 1e-9 else a1 - pa, tb=b0 if b0 > B0 + 1e-9 else b1 - pb,
                        u0=rnd.uniform(0.0, 1.0), v0=rnd.uniform(0.0, 1.0),
                        fa=rnd.uniform(0.0, 1.0) < 0.5, fb=rnd.uniform(0.0, 1.0) < 0.5,
                        dz=rnd.uniform(0.6, 1.0), gx=rnd.uniform(-1.0, 1.0), gy=rnd.uniform(-1.0, 1.0))
            if along == "x":
                cell.update(x0=a0, x1=a1, y0=b0, y1=b1)
            else:
                cell.update(x0=b0, x1=b1, y0=a0, y1=a1)
            cells.append(cell)
    return cells


def marble_floor_parts(rect_cm, seed=0, tile=(120.0, 60.0), gap=0.15, stagger=1.0 / 3.0, along="x",
                       lippage=0.02):
    """[(name, key, md, tile, smooth)]: the tiles (one mesh, own UVs: tile
    None) and the dark subfloor. Each tile stands in its cell with gap/2 all
    round (also at the walls), top on a plane up to `lippage` cm under
    z = 0, 1 mm rounded ease, 2 cm thick; its top and ease carry UVs from
    its own window of the 120 cm marble repeat (sides box-mapped)."""
    g, lip = float(gap), float(lippage)
    if not 0.05 <= g <= 1.0 or not 0.0 <= lip <= 0.1:
        raise ValueError("gap / lippage out of range")
    pa, pb = float(tile[0]), float(tile[1])
    e = FLOOR_EASE
    rings = [(e, 0.0), (e * (1.0 - math.sin(math.radians(45.0))), e * (1.0 - math.cos(math.radians(45.0)))),
             (0.0, e)]                                   # (inset, drop) of the eased edge
    md = _MD()
    for cell in floor_layout(rect_cm, seed, tile, stagger, along):
        x0, x1 = cell["x0"] + 0.5 * g, cell["x1"] - 0.5 * g
        y0, y1 = cell["y0"] + 0.5 * g, cell["y1"] - 0.5 * g
        xc, yc, hx, hy = 0.5 * (x0 + x1), 0.5 * (y0 + y1), 0.5 * (x1 - x0), 0.5 * (y1 - y0)
        dz = -lip * cell["dz"]
        gx, gy = 0.3 * lip * cell["gx"] / hx, 0.3 * lip * cell["gy"] / hy

        def top(x, y):
            return dz + gx * (x - xc) + gy * (y - yc)

        def uv(x, y, cell=cell):
            a, b = (x, y) if along == "x" else (y, x)
            la, lb = a - cell["ta"], b - cell["tb"]
            if cell["fa"]:
                la = pa - la
            if cell["fb"]:
                lb = pb - lb
            return (cell["u0"] + la / MARBLE, cell["v0"] + lb / MARBLE)

        R = []
        for inset, drop in rings:
            q = [(x0 + inset, y0 + inset), (x1 - inset, y0 + inset), (x1 - inset, y1 - inset), (x0 + inset, y1 - inset)]
            R.append([md.add((x, y, top(x, y) - drop)) for x, y in q])
        R.append([md.add((x, y, -FLOOR_T)) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))])
        md.face(tuple(R[0]), [uv(md.v[i][0], md.v[i][1]) for i in R[0]])
        for k in range(3):
            for i in range(4):
                i2 = (i + 1) % 4
                f = (R[k][i], R[k + 1][i], R[k + 1][i2], R[k][i2])
                md.face(f, [uv(md.v[j][0], md.v[j][1]) for j in f] if k < 2 else None)
        md.face((R[3][0], R[3][3], R[3][2], R[3][1]))
    X0, Y0, X1, Y1 = _rect(rect_cm)
    sub = _rbox_md(X0, X1, Y0, Y1, SUB_BOT, SUB_TOP, 0.05)
    return [("MarbleFloor_Tiles", "marble_floor", md, None, 0),
            ("MarbleFloor_Subfloor", "metal_black", sub, 100.0, 0)]


# ================================================================ Max wrappers
def _autosmooth(node, deg=40.0):
    """Smooth modifier, auto at deg: fillets and the groove shade smooth,
    flats and mitres stay crisp (_build puts every face in group 1)."""
    try:
        sm = rt.Smooth()
        kit.setp(sm, "autoSmooth", True)
        kit.setp(sm, "threshold", float(deg))
        rt.addModifier(node, sm)
    except Exception:
        pass
    return node


def _nodes(parts):
    """Max nodes for (name, key, md, tile, smooth) parts; tile None: the cage
    carries its own UVs (MARBLE cm per unit where it has none) and the scene
    must keep them (maptype None)."""
    nodes = []
    for name, key, md, tile, smooth in parts:
        node = FL._build(md, name, MARBLE if tile is None else None)
        _autosmooth(node)
        if smooth:
            kit.soften(node, None, smooth)
        nodes.append(kit.part(node, key, None, None) if tile is None else kit.part(node, key, tile))
    return nodes


def build_bulkhead(length, width=60.0, depth=25.0, gap=10.0, gap_depth=10.0, slot_y=0.0, ceiling_z=0.0,
                   spots=(), cove_led=False):
    """Plasterboard bulkhead along a wall (see the module doc): origin on the
    ceiling plane at the centre of its plan, wall side +Y."""
    return kit.group("Bulkhead", _nodes(bulkhead_parts(length, width, depth, gap, gap_depth, slot_y, ceiling_z,
                                                       spots, cove_led)))


def build_feature_wall(width, height, seed=0, proud=FW_PROUD, flip=False):
    """Copper plaster feature panel with the S-groove; origin bottom centre on
    the wall face, panel face at y = -proud."""
    return kit.group("FeatureWall", _nodes(feature_wall_parts(width, height, seed, proud, flip)))


def build_shadow_skirting(rect_cm, openings=(), height=SK_H, depth=SK_D):
    """Shadow-gap reveal profile round the wall faces rect_cm, stopped at
    openings; already in place (leave the group at the origin)."""
    return kit.group("ShadowSkirting", _nodes(shadow_skirting_parts(rect_cm, openings, height, depth)))


def build_switch_plate(centre_z=105.0):
    """Brass switch plate on the wall face (back on y = 0), centre at centre_z."""
    return kit.group("SwitchPlate", _nodes(switch_parts(centre_z)))


def build_marble_floor(rect_cm, seed=0, tile=(120.0, 60.0), gap=0.15, stagger=1.0 / 3.0, along="x",
                       lippage=0.02):
    """Staggered polished marble tiles over rect_cm, top at z = 0; already in
    place (leave the group at the origin)."""
    return kit.group("MarbleFloor", _nodes(marble_floor_parts(rect_cm, seed, tile, gap, stagger, along, lippage)))


def preview():
    """Every piece in a 5 x 4 m test room: marble floor and reveal round it, a
    bulkhead along the west wall at a 280 cm ceiling, the feature wall and a
    switch on the north wall."""
    room = (-250.0, -200.0, 250.0, 200.0)
    build_marble_floor(room)
    build_shadow_skirting(room, [("s", -60.0, 60.0)])
    kit.place(build_bulkhead(400.0, spots=(-120.0, 0.0, 120.0), cove_led=True), -220.0, 0.0, 280.0, 90.0)
    kit.place(build_feature_wall(320.0, 270.0), 40.0, 200.0, 0.0, 180.0)
    kit.place(build_switch_plate(), -150.0, 200.0, 0.0, 180.0)
