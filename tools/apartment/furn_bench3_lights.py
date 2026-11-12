"""Ceiling pieces for the MatForge benchmark-3 living room (quiet luxury: cream
boucle, green onyx, fluted oak, a tufted wool tapestry): a double-ring
alabaster pendant and the curved plaster coffer it hangs in.

Both are built round their own origin ON THE CEILING (centimetres, Z up,
FRONT facing -Y at rotation 0); every visible node goes through kit.part and
each piece comes back as kit.group: kit.place(group, x, y, ceiling_z, rot).

  build_ring_pendant(drop=110, seed=0) -> (group, ring_lines)
      Two horizontal rings of solid alabaster ("alabaster"). The outer ring
      is 150 cm across with a 12 cm round section, its centre line `drop` cm
      (45-300) below the origin; the inner ring is 95 cm across with an
      11 cm section and hangs 18 cm higher, its centre 6.4 cm off the outer
      ring's (INNER_OFFSET: 4 cm left, 5 cm back). Each is a real closed
      torus whose centre-line radius, height and section radius wobble by a
      few millimetres (seeded harmonics plus a faint carved ripple), so
      neither reads as a perfect machine-made torus. Own UVs: U along the
      ring, V round the section, both in whole repeats of ALABASTER (40) cm
      so the map closes seamlessly; the seams lie at the back (+Y) and along
      the top, out of sight from below. Each ring hangs plumb on four 1.5 mm
      steel cables ("metal_steel": the outer ring's at 45/135/225/315 deg,
      the inner's at 0/90/180/270 deg round its own centre), each from a
      5.2 cm round white canopy ("paint_white", 1.4 cm deep, 4 mm eased
      edge, its top on the ceiling) through a 1.7 cm steel cable-gripper
      nozzle down to a 2.4 cm steel ferrule set 5 mm into the top of the
      ring.
      Origin: the ceiling point above the outer ring's centre, z = 0 at the
      ceiling (the canopies' tops), the piece hanging down -Z. Footprint
      150 x 150 (the inner ring lies inside the outer one in plan); height
      drop + 6 cm (116 at drop 110).
      ring_lines = [outer, inner]: each ring's actual (wobbling) centre line
      as 96 (x, y, z) points relative to the origin, a closed loop (the last
      point joins the first), for the scene's light inside each ring (about
      5 cm of alabaster all round it); turn them with the group if it is
      rotated. `seed` changes only the carving: the canopies and cables
      keep their places, the ferrules follow the ring's top by a few mm.
  build_ceiling_coffer(a=420, b=300, depth=18, ceiling_z=0) -> (group, outline)
      An oval plaster coffer ("wall_paint") recessed `depth` cm (12-40) up
      into the ceiling. Its opening - where the flat ceiling turns up round a
      3 cm bullnose into a 7 cm lip (2 cm thick, 9 mm rounded top) - is an
      a x b ellipse (a along X, b along Y). Behind the lip a 12 cm trough,
      its floor 2.5 cm above the ceiling plane, hides an LED strip all round:
      an aluminium channel ("metal_steel", 1.6 x 0.9 cm) holding a domed opal
      diffuser ("emissive_warm") whose top, 3.45 cm above the ceiling plane,
      stays 3.55 cm under the lip's top, its centre line 2.2 cm behind the
      lip (4.2 cm out from the opening), so no line of sight from the room
      reaches it. From the trough's back wall a broad cove (a quarter
      ellipse depth - 3.5 cm high and at least 30 cm across - 30 at depth
      18 - tangent at both ends) sweeps up and in to the flat recess floor at
      z = ceiling_z + depth - the pendant hangs from there. One closed
      plaster solid, 2.5 cm thick over the recess; every visible arris is a
      real fillet (3 cm bullnose, 9 mm on the lip, 5 mm in the trough).
      Smooth modifier (auto 40 deg), no TurboSmooth.
      Origin: the centre of the oval ON THE MAIN CEILING PLANE (z = ceiling_z,
      default 0): place the group at the room's ceiling height H. The coffer
      RISES from there into the ceiling (z = ceiling_z .. ceiling_z + depth +
      2.5; nothing hangs below the ceiling plane) and its recess floor - the
      pendant's mount - is at H + depth. (ceiling_z = -depth instead puts the
      recess floor at the group's origin and the main ceiling plane at
      -depth.)
      outline: the coffer's outer edge on the main ceiling plane, 240 (x, y)
      points counter-clockwise relative to the origin: the opening offset
      17 cm outwards, about (a + 34) x (b + 34) = 454 x 334. The coffer
      brings its own 17 cm band of flat ceiling (under the trough) out to it,
      so the main ceiling slab must stop exactly there: cut its hole with
      these points (the coffer's outer face rises 20.5 cm from the plane, so
      it closes the hole for any slab up to that thick) and give the slab
      the wall_paint material, or the band shows as a ring.

Pure generators (no Max), tested in tests/test_bench3_lights_geom.py:
ring_specs, ring_wobble, ring_point, section_radius, ring_md, ring_line,
ring_lines, pendant_layout, pendant_parts, canopy_profile, nozzle_profile,
ferrule_profile; coffer_dims, coffer_section, coffer_plaster_md,
led_channel_section, led_diffuser_section, coffer_parts, coffer_outline,
coffer_led_line (the diffuser's top centre line, for a scene light along
the strip) and ellipse_offset (signed distance to an ellipse). A part is a
(name, material key, furn_living._MD, tile cm, TurboSmooth iterations) tuple;
tile None marks a cage that carries its own UVs (the alabaster rings: kept,
maptype None). The build_* wrappers only turn the cages into nodes.

Materials: alabaster (declared here), metal_steel, paint_white, wall_paint
(declared here as bench_arch does), emissive_warm.
"""
import math

from pymxs import runtime as rt

import furn_living as FL
import kit
from furn_living import _MD, _Rand, _fillet2d, _revolve_md, _tube_md

# benchmark-3 keys (runtime only, kit.py is not edited); the scene maps them
# to MatForge materials. wall_paint is bench_arch's key, declared alike so
# this module does not depend on importing bench_arch first.
kit.MAT_KEYS.setdefault("alabaster", "translucent white alabaster (benchmark-3 ring pendant; own UVs)")
kit.MAT_KEYS.setdefault("wall_paint", "white plaster wall paint (walls, cornices)")

TWO_PI = 2.0 * math.pi
STEP = math.radians(22.5)
ALABASTER = 40.0        # cm per alabaster texture repeat (whole repeats round each ring)
METAL = 25.0            # box-map repeats, cm
PAINT = 60.0
PLASTER = 150.0
GLOW = 10.0


# ===================================================================== helpers
def _prof(pts, radii, closed=False, step=STEP):
    """_fillet2d, then drop points that coincide with their neighbour."""
    out = []
    for p in _fillet2d(pts, radii, closed=closed, step=step):
        if out and math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) < 1e-6:
            continue
        out.append((p[0], p[1]))
    if closed and len(out) > 2 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) < 1e-6:
        out.pop()
    return out


def _volume(md):
    """Signed volume: > 0 when a closed mesh faces outwards."""
    v, tot = md.v, 0.0
    for f in md.f:
        a = v[f[0]]
        for k in range(1, len(f) - 1):
            b, c = v[f[k]], v[f[k + 1]]
            tot += (a[0] * (b[1] * c[2] - b[2] * c[1]) + a[1] * (b[2] * c[0] - b[0] * c[2])
                    + a[2] * (b[0] * c[1] - b[1] * c[0]))
    return tot / 6.0


def _outward(md):
    """Turn a closed, consistently wound cage so its normals face out."""
    if _volume(md) < 0.0:
        md.f = [tuple(reversed(f)) for f in md.f]
        md.fuv = [None if u is None else tuple(reversed(u)) for u in md.fuv]
    return md


def _loft(md, stations, closed=False):
    """Quads between consecutive loops of vertex indices (all the same length,
    each loop closed on itself; a pole is one index repeated). closed=True
    also joins the last loop to the first."""
    m, n = len(stations), len(stations[0])
    for k in range(m if closed else m - 1):
        ra, rb = stations[k], stations[(k + 1) % m]
        for i in range(n):
            i2 = (i + 1) % n
            md.face((ra[i], ra[i2], rb[i2], rb[i]))
    return md


def _spin(prof, segs, origin=(0.0, 0.0, 0.0)):
    """Closed solid of revolution about +Z of an (already filleted) (r, z)
    section running from the axis at the bottom round the material to the
    axis at the top, moved to origin."""
    return _outward(_revolve_md(prof, segs, x=origin[0], y=origin[1], z=origin[2]))


def _harm(terms, t):
    return sum(a * math.cos(f * t + p) for a, f, p in terms)


# ================================================================ ring pendant
OUTER_D, OUTER_SEC = 150.0, 12.0      # outer ring: overall diameter, round section
INNER_D, INNER_SEC = 95.0, 11.0       # inner ring
RING_RISE = 18.0                      # the inner ring hangs this much higher
INNER_OFFSET = (-4.0, 5.0)            # inner ring centre off the outer ring's (plan)
DROP_MIN, DROP_MAX = 45.0, 300.0      # ceiling to the outer ring's centre line
RING_N_THETA, RING_N_PHI = 160, 32    # torus cage: round the ring, round the section
LINE_N = 96                           # points of each returned centre line
CABLE_R = 0.075                       # 1.5 mm steel cable
CABLE_SIDES = 12
CABLE_AZ = ((45.0, 135.0, 225.0, 315.0), (0.0, 90.0, 180.0, 270.0))   # outer, inner (deg)
CANOPY_R, CANOPY_H = 2.6, 1.4         # round ceiling canopy, 5.2 cm across
NOZZLE_L = 1.7                        # cable-gripper nozzle under the canopy
FERRULE_R, FERRULE_H, FERRULE_SINK = 0.42, 2.4, 0.5
CABLE_IN_FERRULE, CABLE_IN_NOZZLE = 0.25, 0.3


def ring_specs(drop=110.0):
    """Nominal geometry of the two rings relative to the pendant origin (the
    ceiling point above the outer ring's centre): [outer, inner] dicts with
    name, centre (x, y, z of the centre-line plane), R (centre-line radius),
    r (section radius) and az (cable azimuths, degrees round the ring's own
    centre). The inner ring hangs RING_RISE higher, off by INNER_OFFSET."""
    drop = float(drop)
    if not DROP_MIN <= drop <= DROP_MAX:
        raise ValueError("drop %.1f cm outside %.0f-%.0f cm" % (drop, DROP_MIN, DROP_MAX))
    return [
        {"name": "Outer", "centre": (0.0, 0.0, -drop), "R": 0.5 * (OUTER_D - OUTER_SEC),
         "r": 0.5 * OUTER_SEC, "az": CABLE_AZ[0]},
        {"name": "Inner", "centre": (INNER_OFFSET[0], INNER_OFFSET[1], -drop + RING_RISE),
         "R": 0.5 * (INNER_D - INNER_SEC), "r": 0.5 * INNER_SEC, "az": CABLE_AZ[1]},
    ]


def ring_wobble(seed, k):
    """Hand-carved irregularity of ring k (0 outer, 1 inner) for a seed, as
    (amplitude cm, frequency, phase) cosine terms: R - the centre-line radius
    (2-5 lobes, 0.4-1 mm each), z - its height (1-3 lobes, 0.2-0.6 mm),
    r_along - the section radius along the ring (0.2-0.6 mm), r_round - the
    section out of round (0.2-0.5 mm), carve - (amplitude, m, n, phase)
    ripples cos(m theta + n phi) of 0.15-0.3 mm, the carver's strokes."""
    rnd = _Rand(seed * 977 + 31 * k + 5)

    def terms(freqs, lo, hi):
        return [(rnd.uniform(lo, hi), f, rnd.uniform(0.0, TWO_PI)) for f in freqs]

    wob = {"R": terms((2, 3, 4, 5), 0.04, 0.10), "z": terms((1, 2, 3), 0.02, 0.06),
           "r_along": terms((2, 3, 5, 7), 0.02, 0.06), "r_round": terms((2, 3), 0.02, 0.05)}
    wob["carve"] = [(rnd.uniform(0.015, 0.03), 11 + int(6.0 * rnd.uniform(0.0, 0.999)),
                     2 + int(2.0 * rnd.uniform(0.0, 0.999)), rnd.uniform(0.0, TWO_PI)) for _ in range(2)]
    return wob


def section_radius(spec, wob, th, ph):
    """Radius of the ring's section at azimuth th, section angle ph (rad)."""
    r = spec["r"] + _harm(wob["r_along"], th) + _harm(wob["r_round"], ph)
    for a, m, n, p in wob["carve"]:
        r += a * math.cos(m * th + n * ph + p)
    return r


def ring_point(spec, wob, th, ph=None):
    """Point of a ring at azimuth th (rad, round the ring's own centre): on its
    centre line (ph None) or on its surface at section angle ph (0 outwards,
    pi/2 the top)."""
    cx, cy, cz = spec["centre"]
    rc = spec["R"] + _harm(wob["R"], th)
    zc = cz + _harm(wob["z"], th)
    c, s = math.cos(th), math.sin(th)
    if ph is None:
        return (cx + rc * c, cy + rc * s, zc)
    rho = section_radius(spec, wob, th, ph)
    e = rc + rho * math.cos(ph)
    return (cx + e * c, cy + e * s, zc + rho * math.sin(ph))


def ring_md(spec, wob, n_th=RING_N_THETA, n_ph=RING_N_PHI):
    """Closed torus cage of one ring with its own UVs: U along the ring, V
    round the section, both in whole repeats of about ALABASTER cm (the map
    closes on itself); the U seam at the back (+Y), the V seam along the top."""
    md = _MD()
    th0 = ph0 = 0.5 * math.pi
    grid = [[md.add(ring_point(spec, wob, th0 + TWO_PI * i / n_th, ph0 + TWO_PI * j / n_ph))
             for j in range(n_ph)] for i in range(n_th)]
    ru = max(1, int(round(TWO_PI * spec["R"] / ALABASTER)))
    rv = max(1, int(round(TWO_PI * spec["r"] / ALABASTER)))
    for i in range(n_th):
        i2 = (i + 1) % n_th
        u0, u1 = ru * i / float(n_th), ru * (i + 1) / float(n_th)
        for j in range(n_ph):
            j2 = (j + 1) % n_ph
            v0, v1 = rv * j / float(n_ph), rv * (j + 1) / float(n_ph)
            md.face((grid[i][j], grid[i2][j], grid[i2][j2], grid[i][j2]),
                    ((u0, v0), (u1, v0), (u1, v1), (u0, v1)))
    return _outward(md)


def ring_line(spec, wob, n=LINE_N):
    """The ring's (wobbling) centre line: n points, a closed loop from the back."""
    return [ring_point(spec, wob, 0.5 * math.pi + TWO_PI * i / n) for i in range(n)]


def _surface_z(spec, wob, th, rad):
    """z of the ring's upper surface at azimuth th, plan distance rad from the
    ring's centre (rad within the section)."""
    rc = spec["R"] + _harm(wob["R"], th)
    zc = spec["centre"][2] + _harm(wob["z"], th)
    ph = 0.5 * math.pi
    for _ in range(6):
        rho = section_radius(spec, wob, th, ph)
        ph = math.acos(max(-1.0, min(1.0, (rad - rc) / rho)))
    return zc + section_radius(spec, wob, th, ph) * math.sin(ph)


def pendant_layout(drop=110.0, seed=0):
    """Rings (spec, wobble) and the eight suspensions. Each cable: ring index,
    azimuth, plan point xy (on the ring's nominal centre circle, plumb under
    its canopy), surface_z (top of the ring there), ferrule (base z, top z),
    tip (z of the nozzle tip under the canopy) and cable (bottom z, top z:
    0.25 cm into the ferrule, 0.3 cm into the nozzle)."""
    rings, cables = [], []
    tip = -(CANOPY_H + NOZZLE_L)
    for k, spec in enumerate(ring_specs(drop)):
        wob = ring_wobble(seed, k)
        rings.append({"spec": spec, "wob": wob})
        cx, cy, _cz = spec["centre"]
        for az in spec["az"]:
            th = math.radians(az)
            zs = _surface_z(spec, wob, th, spec["R"])
            fb = zs - FERRULE_SINK
            ft = fb + FERRULE_H
            cables.append({"ring": k, "az": az,
                           "xy": (cx + spec["R"] * math.cos(th), cy + spec["R"] * math.sin(th)),
                           "surface_z": zs, "ferrule": (fb, ft), "tip": tip,
                           "cable": (ft - CABLE_IN_FERRULE, tip + CABLE_IN_NOZZLE)})
    return {"drop": float(drop), "seed": seed, "rings": rings, "cables": cables}


def ring_lines(drop=110.0, seed=0, n=LINE_N):
    """[outer, inner] centre lines (n points each, closed loops) relative to the
    pendant origin - where the scene puts a light inside each ring."""
    return [ring_line(r["spec"], r["wob"], n) for r in pendant_layout(drop, seed)["rings"]]


def canopy_profile():
    """(r, z) section of a ceiling canopy: 5.2 cm drum, top on the ceiling
    (z = 0), 4 mm eased bottom edge, slight taper, 0.5 mm arris at the top."""
    prof = _prof([(0.0, -CANOPY_H), (CANOPY_R - 0.1, -CANOPY_H), (CANOPY_R, 0.0), (0.0, 0.0)],
                 [0.0, 0.4, 0.05, 0.0], step=math.radians(18.0))
    return [(r, min(z, 0.0)) for r, z in prof]       # the arc's end lands exactly on the ceiling


def nozzle_profile():
    """(r, z) section of the cable gripper under a canopy: 9 mm at the top
    (1 mm up inside the canopy) tapering to a rounded 4.8 mm tip."""
    zt = -(CANOPY_H + NOZZLE_L)
    return _prof([(0.0, zt), (0.24, zt), (0.42, zt + 0.8), (0.45, -CANOPY_H + 0.1), (0.0, -CANOPY_H + 0.1)],
                 [0.0, 0.08, 0.2, 0.0, 0.0], step=math.radians(18.0))


def ferrule_profile(zb):
    """(r, z) section of a ring ferrule from its base at zb (buried 5 mm in
    the alabaster): an 8.4 mm sleeve, a stepped 6.8 mm neck and a domed top
    where the cable enters."""
    zt = zb + FERRULE_H
    return _prof([(0.0, zb), (FERRULE_R, zb), (FERRULE_R, zb + 1.5), (0.34, zb + 1.62), (0.34, zt - 0.22),
                   (0.2, zt), (0.0, zt)],
                  [0.0, 0.0, 0.05, 0.04, 0.15, 0.08, 0.0], step=math.radians(18.0))


def pendant_parts(drop=110.0, seed=0):
    """[(name, mat, md, tile, smooth)] of the ring pendant (see build_ring_pendant)."""
    L = pendant_layout(drop, seed)
    parts = [("RingPendant_%sRing" % r["spec"]["name"], "alabaster", ring_md(r["spec"], r["wob"]), None, 0)
             for r in L["rings"]]
    canopies, grippers, cables = _MD(), _MD(), _MD()
    for c in L["cables"]:
        x, y = c["xy"]
        canopies.merge(_spin(canopy_profile(), 40, (x, y, 0.0)))
        grippers.merge(_spin(nozzle_profile(), 20, (x, y, 0.0)))
        grippers.merge(_spin(ferrule_profile(c["ferrule"][0]), 20, (x, y, 0.0)))
        z0, z1 = c["cable"]
        cables.merge(_outward(_tube_md([(x, y, z0), (x, y, z1)], CABLE_R, CABLE_SIDES)))
    parts += [("RingPendant_Canopies", "paint_white", canopies, PAINT, 1),
              ("RingPendant_Grippers", "metal_steel", grippers, METAL, 1),
              ("RingPendant_Cables", "metal_steel", cables, METAL, 0)]
    return parts


# ============================================================== ceiling coffer
CF_NOSE = 3.0           # bullnose where the ceiling turns up into the lip
CF_LIP_T = 2.0          # lip thickness (the opening is its inner face)
CF_LIP_H = 7.0          # lip top above the ceiling plane: hides the LED
CF_LIP_R = 0.9          # rounded lip top
CF_BOARD = 2.5          # trough floor above the ceiling plane
CF_TROUGH = 12.0        # trough width, lip to back wall
CF_BACK = 3.0           # plaster behind the trough, out to the outline
CF_INNER_R = 0.5        # internal fillets in the trough
CF_WALL = 1.0           # straight back wall above the trough floor before the cove
CF_COVE_MIN = 30.0      # the cove's horizontal reach (at least)
CF_SKIN = 2.5           # plaster over the recess floor
CF_CLEAR = 3.0          # the cove stays this far above the lip top
CF_N = 240              # points round the oval
DEPTH_MIN, DEPTH_MAX = 12.0, 40.0
LED_W, LED_H, LED_WALL = 1.6, 0.9, 0.12    # aluminium channel
LED_TOP = 0.95          # diffuser dome above the trough floor
LED_S = CF_LIP_T + 2.2  # strip centre line, out from the opening


def coffer_dims(a=420.0, b=300.0, depth=18.0):
    """Key sizes of the coffer: A, B (opening semi-axes), depth, hc (cove
    start above the ceiling plane), ra / rb (cove reach / rise), s_back
    (trough back wall), s_out (outline), s_r (cove end, inside the opening;
    offsets from the opening ellipse, + outwards), top (z of the coffer's
    back over the recess)."""
    A, B, D = 0.5 * float(a), 0.5 * float(b), float(depth)
    if not DEPTH_MIN <= D <= DEPTH_MAX:
        raise ValueError("coffer depth %.1f cm outside %.0f-%.0f cm" % (D, DEPTH_MIN, DEPTH_MAX))
    if min(A, B) < 60.0:
        raise ValueError("coffer %r x %r too small" % (a, b))
    hc = CF_BOARD + CF_WALL
    rb = D - hc
    ra = max(CF_COVE_MIN, 1.6 * rb)
    s_back = CF_LIP_T + CF_TROUGH
    d = {"A": A, "B": B, "depth": D, "hc": hc, "ra": ra, "rb": rb, "s_back": s_back,
         "s_out": s_back + CF_BACK, "s_r": s_back - ra, "top": D + CF_SKIN}
    if min(A, B) ** 2 / max(A, B) < ra - s_back + 20.0:
        raise ValueError("coffer %r x %r too tight at its ends for the cove" % (a, b))
    if cove_height(d, CF_LIP_T) < CF_LIP_H + CF_CLEAR:
        raise ValueError("coffer depth %.1f cm leaves no room for the cove over the lip" % D)
    return d


def cove_height(d, s):
    """Height of the cove's underside above the ceiling plane at offset s
    (s_r <= s <= s_back) from the opening."""
    c = 1.0 - (d["s_back"] - s) / d["ra"]
    return d["hc"] + d["rb"] * math.sqrt(max(0.0, 1.0 - c * c))


def ellipse_offset(x, y, A, B, iters=40):
    """Signed distance (cm) from (x, y) to the ellipse of semi-axes A (X) and
    B (Y): + outside, - inside (Newton on the nearest point)."""
    px, py = abs(float(x)), abs(float(y))
    if px < 1e-12 and py < 1e-12:
        return -min(A, B)
    t = math.atan2(A * py, B * px)
    k = A * A - B * B
    for _ in range(iters):
        c, s = math.cos(t), math.sin(t)
        f = k * c * s - px * A * s + py * B * c
        fp = k * (c * c - s * s) - px * A * c - py * B * s
        if abs(fp) < 1e-15:
            break
        dt = f / fp
        t = min(max(t - dt, 0.0), 0.5 * math.pi)
        if abs(dt) < 1e-14:
            break
    dist = math.hypot(px - A * math.cos(t), py - B * math.sin(t))
    return dist if (px / A) ** 2 + (py / B) ** 2 > 1.0 else -dist


_FRAMES = {}


def _oval_frame(A, B, n=CF_N):
    """n points of the ellipse (A, B) spaced evenly by arc length, from +X
    counter-clockwise, with the outward unit normal: ((x, y, nx, ny), ...)."""
    key = (float(A), float(B), int(n))
    if key not in _FRAMES:
        m = 4096
        ts = [TWO_PI * k / m for k in range(m + 1)]
        cum = [0.0]
        for t0, t1 in zip(ts, ts[1:]):
            cum.append(cum[-1] + math.hypot(A * (math.cos(t1) - math.cos(t0)), B * (math.sin(t1) - math.sin(t0))))
        out, j = [], 0
        for i in range(n):
            target = cum[-1] * i / n
            while cum[j + 1] < target:
                j += 1
            t = ts[j] + (ts[j + 1] - ts[j]) * (target - cum[j]) / (cum[j + 1] - cum[j])
            nx, ny = B * math.cos(t), A * math.sin(t)
            ln = math.hypot(nx, ny)
            out.append((A * math.cos(t), B * math.sin(t), nx / ln, ny / ln))
        _FRAMES[key] = tuple(out)
    return _FRAMES[key]


def coffer_section(a=420.0, b=300.0, depth=18.0):
    """Open (s, h) section of the swept part of the coffer, s the offset from
    the opening ellipse (+ outwards), h above the ceiling plane. It runs from
    the coffer's back over the cove end (s_r, top) out to the outline, down
    its outer face (both buried), in along the flat band of ceiling, round
    the 3 cm bullnose, up the lip and over its rounded top, down into the
    trough and along its floor, up the back wall and in along the cove to
    the recess floor (s_r, depth). The recess floor and the back over it
    close it as flat ovals (coffer_plaster_md)."""
    d = coffer_dims(a, b, depth)
    corners = [(d["s_r"], d["top"]), (d["s_out"], d["top"]), (d["s_out"], 0.0), (0.0, 0.0), (0.0, CF_LIP_H),
               (CF_LIP_T, CF_LIP_H), (CF_LIP_T, CF_BOARD), (d["s_back"], CF_BOARD), (d["s_back"], d["hc"])]
    radii = [0.0, 0.0, 0.0, CF_NOSE, CF_LIP_R, CF_LIP_R, CF_INNER_R, CF_INNER_R, 0.0]
    sec = _prof(corners, radii, step=math.radians(15.0))
    n = 24
    for k in range(1, n + 1):
        t = 0.5 * math.pi * k / n
        sec.append((d["s_back"] - d["ra"] * (1.0 - math.cos(t)), d["hc"] + d["rb"] * math.sin(t)))
    sec[-1] = (d["s_r"], d["depth"])
    return sec


def coffer_plaster_md(a=420.0, b=300.0, depth=18.0, ceiling_z=0.0):
    """The coffer's one closed plaster solid: the section swept round the oval
    (offset loops of the opening ellipse), the recess floor and the back over
    it filled in with loops scaled towards the centre."""
    d = coffer_dims(a, b, depth)
    frame = _oval_frame(d["A"], d["B"])
    n, z0 = len(frame), float(ceiling_z)
    base = [(x + d["s_r"] * nx, y + d["s_r"] * ny) for x, y, nx, ny in frame]
    sig = (0.2, 0.4, 0.6, 0.8)
    md = _MD()
    stations = [[md.add((0.0, 0.0, z0 + d["top"]))] * n]
    stations += [[md.add((g * p[0], g * p[1], z0 + d["top"])) for p in base] for g in sig]
    stations += [[md.add((x + s * nx, y + s * ny, z0 + h)) for x, y, nx, ny in frame]
                 for s, h in coffer_section(a, b, depth)]
    stations += [[md.add((g * p[0], g * p[1], z0 + d["depth"])) for p in base] for g in reversed(sig)]
    stations.append([md.add((0.0, 0.0, z0 + d["depth"]))] * n)
    return _outward(_loft(md, stations))


def led_channel_section():
    """Closed (w, z) section of the aluminium U channel: 1.6 x 0.9 cm, 1.2 mm
    walls, its foot 0.5 mm down in the trough floor."""
    w, t = 0.5 * LED_W, LED_WALL
    return _prof([(-w, -0.05), (w, -0.05), (w, LED_H), (w - t, LED_H), (w - t, 0.07), (-w + t, 0.07),
                  (-w + t, LED_H), (-w, LED_H)],
                 [0.0, 0.0, 0.04, 0.04, 0.03, 0.03, 0.04, 0.04], closed=True, step=math.radians(30.0))


def led_diffuser_section():
    """Closed (w, z) section of the opal diffuser clipped into the channel:
    flat underside, straight sides 0.2 mm off the channel walls, a shallow
    dome peaking at LED_TOP, just proud of the channel's lips."""
    hw = 0.5 * LED_W - LED_WALL - 0.02
    zb, zs = 0.1, 0.72
    sag = LED_TOP - zs
    rad = (hw * hw + sag * sag) / (2.0 * sag)
    cz = LED_TOP - rad
    a0 = math.atan2(zs - cz, hw)
    pts = [(-hw, zb), (hw, zb), (hw, zs)]
    for k in range(1, 8):
        a = a0 + (math.pi - 2.0 * a0) * k / 8.0
        pts.append((rad * math.cos(a), cz + rad * math.sin(a)))
    pts.append((-hw, zs))
    return _prof(pts, [0.03, 0.03] + [0.0] * (len(pts) - 2), closed=True, step=math.radians(30.0))


def _oval_sweep(frame, section, s0, h0):
    """Closed solid: a closed (w, z) section swept round the oval, w along the
    outward normal from offset s0, z up from h0."""
    md = _MD()
    stations = [[md.add((x + (s0 + w) * nx, y + (s0 + w) * ny, h0 + z)) for x, y, nx, ny in frame]
                for w, z in section]
    return _outward(_loft(md, stations, closed=True))


def coffer_parts(a=420.0, b=300.0, depth=18.0, ceiling_z=0.0):
    """[(name, mat, md, tile, smooth)] of the coffer (see build_ceiling_coffer)."""
    d = coffer_dims(a, b, depth)
    frame = _oval_frame(d["A"], d["B"])
    h0 = float(ceiling_z) + CF_BOARD
    return [("Coffer_Plaster", "wall_paint", coffer_plaster_md(a, b, depth, ceiling_z), PLASTER, 0),
            ("Coffer_LEDChannel", "metal_steel", _oval_sweep(frame, led_channel_section(), LED_S, h0), METAL, 0),
            ("Coffer_LED", "emissive_warm", _oval_sweep(frame, led_diffuser_section(), LED_S, h0), GLOW, 0)]


def coffer_outline(a=420.0, b=300.0, depth=18.0):
    """The coffer's outer edge on the main ceiling plane: [(x, y)] counter-
    clockwise, exactly the plaster cage's outer corner loop - where the main
    ceiling slab stops."""
    d = coffer_dims(a, b, depth)
    s = d["s_out"]
    return [(x + s * nx, y + s * ny) for x, y, nx, ny in _oval_frame(d["A"], d["B"])]


def coffer_led_line(a=420.0, b=300.0, depth=18.0, ceiling_z=0.0, n=120):
    """Centre line of the LED diffuser's top (n points, a closed loop, z
    absolute in the coffer's frame); it shines straight up (+Z) at the cove."""
    d = coffer_dims(a, b, depth)
    z = float(ceiling_z) + CF_BOARD + LED_TOP
    return [(x + LED_S * nx, y + LED_S * ny, z) for x, y, nx, ny in _oval_frame(d["A"], d["B"], n)]


# ================================================================ Max wrappers
def _autosmooth(node, deg=40.0):
    """Smooth modifier, auto at deg: fillets shade smooth, the buried 90-degree
    corners stay crisp (_build puts every face in smoothing group 1)."""
    try:
        sm = rt.Smooth()
        kit.setp(sm, "autoSmooth", True)
        kit.setp(sm, "threshold", float(deg))
        rt.addModifier(node, sm)
    except Exception:
        pass
    return node


def _nodes(parts):
    """Max nodes for (name, mat, md, tile, smooth) parts. tile None: the cage
    carries its own UVs (the alabaster rings: dense, one smoothing group, no
    modifiers; the scene keeps the UVs, maptype None); otherwise a Smooth
    modifier, `smooth` TurboSmooth iterations and a box map of `tile` cm."""
    out = []
    for name, mat, md, tile, smooth in parts:
        if tile is None:
            out.append(kit.part(FL._build(md, name, ALABASTER), mat, None, None))
            continue
        node = _autosmooth(FL._build(md, name))
        if smooth:
            kit.soften(node, None, smooth)
        out.append(kit.part(node, mat, tile))
    return out


def build_ring_pendant(drop=110.0, seed=0):
    """Double-ring alabaster pendant hanging from its canopies at the origin
    (ceiling, z = 0). Returns (group, ring_lines): [outer, inner] centre
    lines relative to the origin for the scene's lights (see the module doc)."""
    group = kit.group("RingPendant", _nodes(pendant_parts(drop, seed)))
    return group, ring_lines(drop, seed)


def build_ceiling_coffer(a=420.0, b=300.0, depth=18.0, ceiling_z=0.0):
    """Oval plaster coffer with a hidden cove LED, origin at the centre of the
    oval on the main ceiling plane (z = ceiling_z), rising `depth` cm into the
    ceiling. Returns (group, outline): the [(x, y)] loop where the main
    ceiling slab must stop (see the module doc)."""
    group = kit.group("CeilingCoffer", _nodes(coffer_parts(a, b, depth, ceiling_z)))
    return group, coffer_outline(a, b, depth)


def preview(ceiling=280.0):
    """The coffer under a ceiling at `ceiling` cm with the pendant hanging from
    its recess floor (run inside 3ds Max)."""
    coffer, _outline = build_ceiling_coffer()
    kit.place(coffer, 0.0, 0.0, ceiling)
    pendant, _lines = build_ring_pendant()
    kit.place(pendant, 0.0, 0.0, ceiling + coffer_dims()["depth"])
    return pendant
