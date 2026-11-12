"""Long curved boucle sofa for the MatForge benchmark-3 living room (quiet luxury:
cream boucle, green onyx, walnut, fluted oak; V-Ray in 3ds Max 2026). An original,
generic design.

  build_curved_sofa(chord=340, depth=95, seed=0, radius=300, cushions=True)
      A smooth arc: footprint `chord` (340) wide in X, `depth` (95) deep radially
      (seat front to the outer face of the back), back 72 high, seat 40. The back
      runs on the convex outside of the curve, the seat faces the curve's centre:
      at rotation 0 the front faces -Y and the arc bulges towards +Y (circle centre
      in front of the sofa, on the -Y axis). `radius` is the outer back radius (300):
      the footprint is chord x 133.2 (at the defaults), its bounding box centred on the
      origin, the floor at z = 0; the arc's centre is sofa_layout(...)["yc"] (-233.4)
      on the Y axis, so a coffee table set ~100-150 in front of the origin sits in the
      curve. Returned as kit.group("CurvedSofa", ...).

Anatomy (upholstery "upholstery_alt", the cream boucle, own UVs at BOUCLE = 20 cm per
UV unit; the Max Noise + TurboSmooth of furn_living's soft goods):
  * one continuous back that wraps round both ends as arms: a pill section (outer
    face upright, a 5 cm tuck-under at the foot, a full round top roll, the inner face
    raked 30 -> 23 cm thick) swept along the plan path outer arc -> 38 cm corner round
    -> straight arm along the radial end line, the arm section turning symmetric
    (23 thick) round the corner and its top falling from 72 to 65 at the front; each
    arm closed by a half-revolved nose (a true round in plan and elevation). Own UVs:
    U along the path at true length on every offset (s - d * turning angle), V round
    the section; U carries on round each nose at true length. UV seams: along the
    underside, and on each arm's inner face where its nose begins (a U-turn needs
    one; there it faces the seat and is covered by the seat cushion below z 40). The
    roll sags ~5 mm mid-span and the outer face wavers +-1.2 mm (seeded).
  * one continuous upholstered base (deck) under the three seats, 4 cm behind their
    front, its ends 14 cm in from the end lines (9-16 cm into the arms, its front
    running into the round noses) and its rear 14-16 cm into the back; a 5 cm
    tuck-under at the front, a 3 mm crown.
  * three long seat cushions following the arc (wedges between radial seams, ~70 wide
    at the front, ~102 at the back, 67 deep; the end cushions' outer ends along the
    arms' inner faces), 19 cm thick + a 1.5 cm crown (seat 40 at the front edge),
    self-piped welts on both seams, a 5.5 cm pillow round on the top edges, 7.5 / 6.5
    cm plan corners (14 where an end cushion fills the back's round inner corner), a
    seeded sat-in hollow each (1-1.8 cm) and the front edge drooping mid-span; 2.7 mm
    apart at the seams, pressed 2 mm onto the raked back and the arms (the turned
    slab puts the boxing strip's UV seam at a rear corner).
  * a recessed black plinth ("metal_black", box-mapped) 4 cm high, set 9 cm in at the
    front and 7 cm at the back and the ends, eased 3 mm edges.
  * cushions=True: seven loose back cushions (furn_living._pillow_md) - five boucle
    ("upholstery_alt"), two linen ("linen", one self-piped) - of 34-62 cm, five in a row
    against the back and two leant in front of them, each yawed, leant and rolled
    differently, then settled: sunk 1.3 cm into the seat, pressed 6 mm against the back
    roll or the cushions behind it. Own UVs at real scale (BOUCLE / LINEN cm per unit).

All geometry is pure Python (furn_living._MD cages): sofa_layout, path_frame,
path_dist, section_params, front_d, outer_d, back_section, back_md, sector_map,
squash, plinth_md, base_md, seat_cushion_md, back_cushions and curved_sofa_parts (a
list of Part tuples (name, material key, _MD, tile cm, TurboSmooth iterations)
carrying how the node is made), so tests/test_bench3_sofa_geom.py checks it without
3ds Max; build_curved_sofa only turns the parts into nodes (~36k cage faces). Every
key used ("upholstery_alt", "linen", "metal_black") is already in kit.MAT_KEYS.
"""
import math

import kit
import furn_living as fl
from furn_living import _MD, _Grid2, _Rand, _pillow_md, _slab, _smax, _smin, _smooth

BOUCLE = 20.0                        # cm per UV unit on the boucle (the brief's ~20 cm repeat)
LINEN = 14.0                         # cm per UV unit on the linen cushions (fine linen, as the curtains)
METAL = 25.0                         # plinth powder coat (box-mapped)
BODY_NOISE = (40.0, 0.25, 0.25)      # Max Noise (scale, xy, z strength): back, base
CUSHION_NOISE = (24.0, 0.3, 0.35)    # seat cushions
PILLOW_NOISE = (12.0, 0.5, 0.6)      # back cushions (as furn_living's scatter cushions)
SEAT_STEP = 2.6                      # cm between seat-cushion cage lines
SEC = (2, 3, 7, 6)                   # back section points per half: bottom flat, foot round, face, top roll
NAMES_SEAT = ("SeatL", "SeatC", "SeatR")
SPAN_REF = 158.8                     # half run of the back between the arms at the default size (cm)


class Part(tuple):
    """(name, mat, md, tile, smooth) plus how its node is made: own_uv (the cage
    carries UVs at `tile` cm per unit; else box-mapped at `tile`), Max Noise
    `noise` with `seed`, and for a framed node (a leant back cushion) its axes
    (rows: local X, Y, Z) and origin."""

    def __new__(cls, name, mat, md, tile, smooth, own_uv=True, noise=None, seed=0, axes=None, origin=None):
        self = tuple.__new__(cls, (name, mat, md, tile, smooth))
        self.own_uv, self.noise, self.seed, self.axes, self.origin = own_uv, noise, seed, axes, origin
        return self

    name = property(lambda self: self[0])
    mat = property(lambda self: self[1])
    md = property(lambda self: self[2])
    tile = property(lambda self: self[3])
    smooth = property(lambda self: self[4])

    def __repr__(self):
        return "Part(%s, %s, %d verts, %d faces)" % (self[0], self[1], len(self[2].v), len(self[2].f))


def _clamp(t, a=0.0, b=1.0):
    return a if t < a else b if t > b else t


# ===================================================================== layout
def sofa_layout(chord=340.0, depth=95.0, radius=300.0):
    """Key dimensions (cm) and the plan geometry of the sofa. Plan angles are measured
    from +Y towards +X about the circle centre (0, yc); the back's outer face path runs
    from the left nose (s = -S) along the left arm, round the left corner, along the
    outer arc (s = 0 at its middle) and on to the right nose (s = S)."""
    C, D, Ro = float(chord), float(depth), float(radius)
    if not 75.0 <= D <= 130.0:
        raise ValueError("depth %.0f: keep it within 75-130 cm" % D)
    L = dict(chord=C, depth=D, Ro=Ro, Ri=Ro - D, H=72.0, arm_h=65.0, seat_h=40.0, seat_t=19.0, z_b=4.0,
             rho=38.0, T_bot=30.0, T_arm=23.0, rb_out=5.0, rb_in=3.0, roll_v=12.0, nose_back=2.5)
    if L["Ri"] < 100.0:
        raise ValueError("radius %.0f: too tight a curve for a %.0f deep sofa" % (Ro, D))
    rho, T = L["rho"], L["T_arm"]
    half = 0.5 * C - rho
    if half <= 0.0 or half >= Ro - rho:
        raise ValueError("chord %.0f does not fit an arc of outer radius %.0f" % (C, Ro))
    th_f = math.asin(half / (Ro - rho))                 # where the outer arc meets the corner round
    Th = th_f + math.asin(rho / (Ro - rho))            # the radial end lines (outer faces of the arms)
    if Th > math.radians(80.0):
        raise ValueError("chord %.0f: the arc would wrap past 160 degrees" % C)
    b_len = math.sqrt((Ro - rho) ** 2 - rho * rho)      # corner round -> arm line tangent point (radius)
    r_end = L["Ri"] + L["nose_back"] + 0.5 * T         # the path's end: the nose tip 2.5 behind the seat front
    if b_len - r_end < 5.0:
        raise ValueError("depth %.0f: no room for the arms" % D)
    s_A = Ro * th_f
    s_B = s_A + rho * (Th + 0.5 * math.pi - th_f)
    S = s_B + b_len - r_end
    seat_span = L["Ri"] * (Th - math.asin(T / L["Ri"]))
    if seat_span < 60.0:
        raise ValueError("chord %.0f: too short for three seats" % C)
    # footprint: the apex of the back (Ro) and the arm noses (the lowest points) centred on y = 0
    nose = r_end * math.cos(Th) + 0.5 * T * math.sin(Th) - 0.5 * T
    seat = L["Ri"] * math.cos(Th - math.asin(T / L["Ri"]))
    y_lo = min(nose, seat)
    L.update(th_f=th_f, Th=Th, b_len=b_len, r_end=r_end, s_A=s_A, s_B=s_B, S=S, yc=-0.5 * (Ro + y_lo),
             F=((Ro - rho) * math.sin(th_f), (Ro - rho) * math.cos(th_f)),
             foot_y=0.5 * (Ro - y_lo), z_deck=L["seat_h"] - L["seat_t"])
    # base (deck), seat cushions, plinth (radii from the circle centre), back cushions
    L.update(base_r0=L["Ri"] + 4.0, base_r1=Ro - 14.0, base_inset=14.0, base_bulge=0.5,
             seat_bulge=1.0, seat_gap=0.12, arm_overlap=1.2,
             plinth_r0=L["Ri"] + 9.0, plinth_r1=Ro - 7.0, plinth_inset=7.0,
             r_ref=Ro - 30.0)
    L["seat_r0"] = L["Ri"] + L["seat_bulge"]
    L["seat_r1"] = Ro - front_d(L, L["z_deck"], 0.0) + 2.0
    rm = 0.5 * (L["seat_r0"] + L["seat_r1"])
    L["seam"] = (Th - math.asin(T / rm)) / 3.0          # radial seams: three equal seats at mid-depth
    L["span_ref"] = L["r_ref"] * (Th - math.asin(T / L["r_ref"]))   # half the back's run between the arms
    return L


def polar(L, r, th):
    """Plan point at radius r and angle th about the circle centre."""
    return (r * math.sin(th), L["yc"] + r * math.cos(th))


def path_frame(L, s):
    """((x, y), unit tangent, unit inward normal, turning angle) of the back's outer-face
    path at s (the turning angle is 0 at the middle, positive to the right)."""
    a = abs(s)
    Ro, rho, Th = L["Ro"], L["rho"], L["Th"]
    if a <= L["s_A"]:
        th = a / Ro
        px, py = Ro * math.sin(th), Ro * math.cos(th)
        t, m, turn = (math.cos(th), -math.sin(th)), (-math.sin(th), -math.cos(th)), th
    elif a <= L["s_B"]:
        al = L["th_f"] + (a - L["s_A"]) / rho
        px, py = L["F"][0] + rho * math.sin(al), L["F"][1] + rho * math.cos(al)
        t, m, turn = (math.cos(al), -math.sin(al)), (-math.sin(al), -math.cos(al)), al
    else:
        r = L["b_len"] - (a - L["s_B"])
        px, py = r * math.sin(Th), r * math.cos(Th)
        t, m, turn = (-math.sin(Th), -math.cos(Th)), (-math.cos(Th), math.sin(Th)), Th + 0.5 * math.pi
    if s < 0.0:
        px, t, m, turn = -px, (t[0], -t[1]), (-m[0], m[1]), -turn
    return (px, py + L["yc"]), t, m, turn


def path_dist(L, X, Y):
    """(d, s, (mx, my)) of a plan point inside the sofa: its inward distance from the
    back's outer-face path, the path parameter of the closest point and the inward
    normal there. The arm lines count as running on past the noses."""
    x, y = abs(X), Y - L["yc"]
    Ro, rho, Th, th_f = L["Ro"], L["rho"], L["Th"], L["th_f"]
    r = math.hypot(x, y)
    phi = math.atan2(x, y)
    best = None
    if phi <= th_f and r > 1e-9:
        best = (Ro - r, Ro * phi, (-x / r, -y / r))
    dx, dy = x - L["F"][0], y - L["F"][1]
    rr = math.hypot(dx, dy)
    al = math.atan2(dx, dy)
    if rr > 1e-9 and th_f <= al <= Th + 0.5 * math.pi and (best is None or rho - rr < best[0]):
        best = (rho - rr, L["s_A"] + rho * (al - th_f), (-dx / rr, -dy / rr))
    proj = x * math.sin(Th) + y * math.cos(Th)
    d = -x * math.cos(Th) + y * math.sin(Th)
    if proj <= L["b_len"] and (best is None or d < best[0]):
        best = (d, min(L["S"], L["s_B"] + L["b_len"] - proj), (-math.cos(Th), math.sin(Th)))
    if best is None:                                    # outside, beyond a corner
        best = (Ro - r, Ro * th_f, (-x / max(r, 1e-9), -y / max(r, 1e-9)))
    d, s, m = best
    if X < 0.0:
        s, m = -s, (-m[0], m[1])
    return d, s, m


# ================================================================ back section
def section_params(L, s):
    """(foot thickness, inner foot round, top height) of the back section at s: raked on
    the back, turning symmetric (T_arm thick) round the corner, the top falling from H
    to arm_h along the corner and the arm."""
    a = abs(s)
    w = _smooth((a - L["s_A"]) / (L["s_B"] - L["s_A"]))
    tb = L["T_bot"] + (L["T_arm"] - L["T_bot"]) * w
    rbi = L["rb_in"] + (L["rb_out"] - L["rb_in"]) * w
    h = L["H"] - (L["H"] - L["arm_h"]) * _smooth((a - L["s_A"]) / (L["S"] - L["s_A"]))
    return tb, rbi, h


def front_d(L, z, s):
    """Inward distance of the back's (or arm's) inner face from the outer-face path at
    height z, for the section at s; None above the top or below the foot."""
    tb, rbi, h = section_params(L, s)
    zb, tt, rv = L["z_b"], L["T_arm"], L["roll_v"]
    zs = h - rv
    if z > h or z < zb:
        return None
    if z >= zs:
        q = (z - zs) / rv
        return 0.5 * tt + 0.5 * tt * math.sqrt(max(0.0, 1.0 - q * q))
    if z >= zb + rbi:
        return tt + (tb - tt) * (zs - z) / (zs - zb - rbi)
    dz = zb + rbi - z
    return tb - rbi + math.sqrt(max(0.0, rbi * rbi - dz * dz))


def outer_d(L, z, s):
    """Inward distance of the back's (or arm's) outer surface from the outer-face path at
    height z (0 on the upright face, more round the foot and the top roll); None above
    the top or below the foot."""
    h = section_params(L, s)[2]
    zb, rbo, rv, a = L["z_b"], L["rb_out"], L["roll_v"], 0.5 * L["T_arm"]
    zs = h - rv
    if z > h or z < zb:
        return None
    if z >= zs:
        q = (z - zs) / rv
        return a - a * math.sqrt(max(0.0, 1.0 - q * q))
    if z >= zb + rbo:
        return 0.0
    dz = zb + rbo - z
    return rbo - math.sqrt(max(0.0, rbo * rbo - dz * dz))


def back_section(L, s):
    """Closed (d, z) section of the back / arm at s, K = 2 * sum(SEC) points, d = inward
    distance from the outer face. Index 0 is the middle of the underside, the points run
    out along the underside, round the 5 cm foot, up the outer face and over the outer
    half of the top roll to its apex (index K / 2), then down the inner half, the raked
    inner face, the inner foot round and back along the underside. Along the arms (where
    the noses are revolved) it is symmetric about d = T_arm / 2."""
    nb, nf, nw, nr = SEC
    tb, rbi, h = section_params(L, s)
    zb, rbo, tt, rv = L["z_b"], L["rb_out"], L["T_arm"], L["roll_v"]
    zs = h - rv
    dm = 0.5 * (rbo + tb - rbi)
    a = 0.5 * tt
    pts = [(dm, zb)]
    pts += [(dm + (rbo - dm) * j / nb, zb) for j in range(1, nb + 1)]
    for j in range(1, nf + 1):
        ph = -0.5 * math.pi * (1.0 + j / nf)
        pts.append((rbo + rbo * math.cos(ph), zb + rbo + rbo * math.sin(ph)))
    pts += [(0.0, zb + rbo + (zs - zb - rbo) * j / nw) for j in range(1, nw + 1)]
    for j in range(1, 2 * nr + 1):
        ps = math.pi * (1.0 - 0.5 * j / nr)
        pts.append((a + a * math.cos(ps), zs + rv * math.sin(ps)))
    pts += [(tt + (tb - tt) * j / nw, zs + (zb + rbi - zs) * j / nw) for j in range(1, nw + 1)]
    for j in range(1, nf + 1):
        ph = -0.5 * math.pi * j / nf
        pts.append((tb - rbi + rbi * math.cos(ph), zb + rbi + rbi * math.sin(ph)))
    pts += [(tb - rbi + (dm - tb + rbi) * j / nb, zb) for j in range(1, nb)]
    return pts


def back_stations(L):
    """Path parameters of the back's section rings: ~3.5 cm apart on the arc, 7 degrees
    of turn round the corners, ~4 cm along the arms."""
    sA, sB, S = L["s_A"], L["s_B"], L["S"]

    def seg(a, b, n):
        return [a + (b - a) * i / n for i in range(n)]
    n_arc = max(16, int(math.ceil(2.0 * sA / 3.5)))
    n_fil = max(8, int(math.ceil(math.degrees((sB - sA) / L["rho"]) / 7.0)))
    n_arm = max(3, int(math.ceil((S - sB) / 4.0)))
    return (seg(-S, -sB, n_arm) + seg(-sB, -sA, n_fil) + seg(-sA, sA, n_arc) + seg(sA, sB, n_fil)
            + seg(sB, S, n_arm) + [S])


def back_md(L, seed=0, noses=8):
    """The continuous back with its wrapped arms (see the module doc) as one closed cage.
    Seeded irregularity on the arc only (fading out round the corners, so the noses
    stay exact): the roll sags up to 4 mm mid-span and wavers 1.5 mm, the outer face
    wavers +-1.2 mm. Own UVs (BOUCLE cm per unit)."""
    K = 2 * sum(SEC)
    rnd = _Rand(seed * 37 + 11)
    ph1, ph2 = rnd.uniform(0.0, 2.0 * math.pi), rnd.uniform(0.0, 2.0 * math.pi)
    lam1, lam2 = rnd.uniform(90.0, 130.0), rnd.uniform(50.0, 75.0)
    sA, t = L["s_A"], BOUCLE

    def irregular(s, d, z, h):
        fade = math.sin(math.pi * _clamp((s + sA) / (2.0 * sA))) ** 2
        if fade <= 0.0:
            return d, z
        wtop = _smooth((z - (h - 9.0)) / 8.0)
        z -= wtop * fade * (0.4 + 0.15 * (0.5 + 0.5 * math.sin(2.0 * math.pi * s / lam1 + ph1)))
        d -= (1.0 - _smooth(d / 4.0)) * fade * 0.12 * math.sin(2.0 * math.pi * s / lam2 + ph2)
        return d, z

    md = _MD()
    rings, uvs, ends = [], [], []
    for s in back_stations(L):
        (px, py), tg, m, turn = path_frame(L, s)
        sec = back_section(L, s)
        h = section_params(L, s)[2]
        per = [0.0]
        for k in range(K):
            a, b = sec[k], sec[(k + 1) % K]
            per.append(per[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        ring = []
        for d, z in sec:
            d2, z2 = irregular(s, d, z, h)
            ring.append(md.add((px + d2 * m[0], py + d2 * m[1], z2)))
        rings.append(ring)
        uvs.append(([(s - d * turn) / t for d, _z in sec], [p / t for p in per]))
        ends.append(((px, py), tg, m, sec))
    for i in range(len(rings) - 1):
        r0, r1 = rings[i], rings[i + 1]
        (u0, v0), (u1, v1) = uvs[i], uvs[i + 1]
        for k in range(K):
            k2 = (k + 1) % K
            kv = k + 1                                  # V of the wrap face's far side is the perimeter
            md.face((r0[k], r0[k2], r1[k2], r1[k]),
                    ((u0[k], v0[k]), (u0[k2], v0[kv]), (u1[k2], v1[kv]), (u1[k], v1[k])))
    for end, sign in ((0, -1.0), (len(rings) - 1, 1.0)):
        _nose(L, md, rings[end], ends[end], uvs[end], sign, noses)
    return md


def _nose(L, md, ring, frame, uv, sign, M):
    """Close an arm end: the outer half of its (symmetric) section revolved 180 degrees
    about the vertical axis through the section's middle, bulging along sign * tangent.
    Own UVs continue U round the nose at true length; their seam is the last meridian."""
    (px, py), tg, m, sec = frame
    K = len(ring)
    half = K // 2
    a = 0.5 * L["T_arm"]
    qx, qy = px + a * m[0], py + a * m[1]
    nd = (sign * tg[0], sign * tg[1])
    us, vs = uv
    rows, ruv = [[ring[k] for k in range(half + 1)]], [[(us[k], vs[k]) for k in range(half + 1)]]
    for j in range(1, M + 1):
        al = math.pi * j / M
        ca, sa = math.cos(al), math.sin(al)
        row, rw = [ring[0]], [(us[0], vs[0])]
        for k in range(1, half):
            d, z = sec[k]
            rk = a - d
            if j == M:
                row.append(ring[K - k])
            else:
                row.append(md.add((qx + rk * (-ca * m[0] + sa * nd[0]), qy + rk * (-ca * m[1] + sa * nd[1]), z)))
            rw.append((us[k] + sign * rk * al / BOUCLE, vs[k]))
        row.append(ring[half])
        rw.append((us[half], vs[half]))
        rows.append(row)
        ruv.append(rw)
    for j in range(M):
        for k in range(half):
            a0, b0, c0, d0 = rows[j][k], rows[j][k + 1], rows[j + 1][k + 1], rows[j + 1][k]
            ua, ub, uc, ud = ruv[j][k], ruv[j][k + 1], ruv[j + 1][k + 1], ruv[j + 1][k]
            if sign > 0:
                md.face((a0, b0, c0, d0), (ua, ub, uc, ud))
            else:
                md.face((a0, d0, c0, b0), (ua, ud, uc, ub))


# ============================================================ sector mapping
def side_angle(L, side, r):
    """Plan angle at radius r of a slab end: ("radial", angle) or ("line", (sign, inset)) -
    the line `inset` cm inside the left (sign -1) or right (+1) end line, parallel to it."""
    kind, val = side
    if kind == "radial":
        return val
    sign, inset = val
    return sign * (L["Th"] - math.asin(_clamp(inset / r, -1.0, 1.0)))


def sector_size(L, r0, r1, side_a, side_b):
    """(A, B) half extents of the flat slab that sector_map bends into the sector."""
    rm = 0.5 * (r0 + r1)
    return 0.5 * rm * (side_angle(L, side_b, rm) - side_angle(L, side_a, rm)), 0.5 * (r1 - r0)


def sector_map(L, A, B, r0, r1, side_a, side_b):
    """Map a point of a flat slab (x in [-A, A] left to right, y in [-B, B] front to back)
    into the plan sector between radii r0 (front) and r1 (back) and the two ends: the
    radius follows y, the angle runs linearly from side_a to side_b at that radius
    (orientation preserving, so outward faces stay outward)."""
    def f(x, y):
        r = r0 + (y + B) / (2.0 * B) * (r1 - r0)
        ta, tb = side_angle(L, side_a, r), side_angle(L, side_b, r)
        return polar(L, r, ta + (x + A) / (2.0 * A) * (tb - ta))
    return f


def squash(L, X, Y, z, into=0.2, k=0.5):
    """Press a plan point of a soft cushion at height z against the back / arms: no
    deeper than `into` cm into their inner face, eased over ~1 cm (smooth max)."""
    d, s, m = path_dist(L, X, Y)
    lim = front_d(L, z, s)
    if lim is None or d - (lim - into) > 3.0:
        return X, Y
    dn = _smax(d, lim - into, k)
    return X + (dn - d) * m[0], Y + (dn - d) * m[1]


# ================================================================ plinth, base
def plinth_md(L):
    """Recessed black plinth 4 cm high (1 mm into the upholstery above it): the sofa's
    plan inset 9 cm at the front and 7 cm at the back and ends, a big round under the
    back corners, 3 mm eased edges."""
    sa, sb = ("line", (-1.0, L["plinth_inset"])), ("line", (1.0, L["plinth_inset"]))
    r0, r1 = L["plinth_r0"], L["plinth_r1"]
    A, B = sector_size(L, r0, r1, sa, sb)
    f = sector_map(L, A, B, r0, r1, sa, sb)
    md = _slab(A, B, 0.0, L["z_b"] + 0.1, [(3.0, 3.0), (3.0, 3.0), (34.0, 34.0), (34.0, 34.0)],
               p=max(36, int(round(2.0 * A / 6.0))), q=8, rb=(0.3, 0.3), rt_=(0.3, 0.3), mb=1, ms=1, mt=1, amin=1)
    return md.map(lambda p: f(p[0], p[1]) + (p[2],))


def base_md(L):
    """The continuous upholstered base (deck) under the three seats: z_b up to the deck,
    its front 4 cm behind the seat fronts with a 5 cm tuck-under, its ends 14 cm inside
    the end lines (in the arms and their noses), its rear 14 cm inside the back's outer
    face (in the back). Built turned 180 degrees so the boxing strip's UV seam sits at a
    buried rear corner. Own UVs."""
    sa, sb = ("line", (-1.0, L["base_inset"])), ("line", (1.0, L["base_inset"]))
    r0, r1 = L["base_r0"] + L["base_bulge"], L["base_r1"]
    A, B = sector_size(L, r0, r1, sa, sb)
    f = sector_map(L, A, B, r0, r1, sa, sb)
    md = _slab(A, B, L["z_b"], L["z_deck"], [(15.0, 15.0), (15.0, 15.0), (4.0, 4.0), (4.0, 4.0)],
               p=max(40, int(round(2.0 * A / 4.0))), q=14, rb=(5.0, 5.0), rt_=(3.5, 3.5), mb=2, ms=3, mt=2,
               crown=0.3, bulge=L["base_bulge"], uv_tile=BOUCLE)
    return md.map(lambda p: f(-p[0], -p[1]) + (p[2],))


# ============================================================== seat cushions
def seat_sides(L, idx):
    """Plan ends of seat cushion idx (0 left, 1 centre, 2 right): radial seams between
    them, the arms' inner faces (overlapped arm_overlap cm, then squashed) at the ends."""
    th, arm = L["seam"], L["T_arm"] - L["arm_overlap"]
    return (("line", (-1.0, arm)), ("radial", -th)) if idx == 0 else \
        (("radial", -th), ("radial", th)) if idx == 1 else (("radial", th), ("line", (1.0, arm)))


def seat_hollow(L, idx, seed=0):
    """Seeded sat-in hollow of seat cushion idx in its flat frame: (x, y, depth, sx, sy)."""
    rnd = _Rand(seed * 31 + 17 + 6 * idx)
    r0, r1 = L["seat_r0"], L["seat_r1"]
    A, B = sector_size(L, r0, r1, *seat_sides(L, idx))
    dep = (1.5, 1.0, 1.8)[idx] * (1.0 + rnd.uniform(-0.12, 0.12))
    x = (-0.12, 0.05, 0.1)[idx] * A + rnd.uniform(-6.0, 6.0)
    return (x, -B + 28.0 + rnd.uniform(-4.0, 4.0), dep, 24.0 + rnd.uniform(-3.0, 3.0), 19.0 + rnd.uniform(-2.0, 2.0))


def seat_cushion_md(L, idx, seed=0, sag=True):
    """Seat cushion idx (0 left, 1 centre, 2 right): a self-piped box cushion bent into
    its wedge of the arc, 19 cm thick on the deck, crowned 1.5 cm, a 5.5 cm pillow round
    on the top edges, 3 cm under; a seeded sat-in hollow and the front edge drooping
    5 mm mid-span (sag=False leaves both out); pressed 2.4 mm off its neighbours and
    onto the raked back and the arms. Own UVs (top / bottom panels, a wrapped boxing
    strip whose seam lands at a rear corner: the slab is built turned 180 degrees)."""
    sa, sb = seat_sides(L, idx)
    r0, r1 = L["seat_r0"], L["seat_r1"]
    A, B = sector_size(L, r0, r1, sa, sb)
    f = sector_map(L, A, B, r0, r1, sa, sb)
    z0, T = L["z_deck"], L["seat_t"]
    xs, ys, dep, sx, sy = seat_hollow(L, idx, seed)
    droop = 0.5
    if not sag:
        dep = droop = 0.0
    g = L["seat_gap"]

    def deform(p):
        x, y, z = -p[0], -p[1], p[2]
        wt = _clamp((z - z0) / T) ** 2
        dz = dep * math.exp(-((x - xs) / sx) ** 2 - ((y - ys) / sy) ** 2)
        dz += droop * max(0.0, 1.0 - (x / A) ** 2) ** 2 * _smooth((16.0 - (y + B)) / 16.0)
        z -= dz * wt
        if idx > 0:
            x = _smax(x, -A + g, 0.35)
        if idx < 2:
            x = _smin(x, A - g, 0.35)
        X, Y = f(x, y)
        X, Y = squash(L, X, Y, z)
        return (X, Y, z)

    # plan corners (the slab turned 180 degrees: FL, FR = rear right, rear left; BR, BL =
    # front left, front right): 7.5 at the front, 6.5 at the rear, both above the 5.5 top
    # round so no corner ring collapses; 14 where an end cushion fits the back's rounded
    # inner corner by the arm (a squarer corner was squashed 5-9 cm and folded)
    rr = [(6.5, 6.5), (6.5, 6.5), (7.5, 7.5), (7.5, 7.5)]
    if idx == 0:
        rr[1] = (14.0, 14.0)
    elif idx == 2:
        rr[0] = (14.0, 14.0)
    md = _slab(A, B, z0, z0 + T, rr,
               p=max(24, int(round(2.0 * A / SEAT_STEP))), q=max(16, int(round(2.0 * B / SEAT_STEP))),
               rb=(3.0, 3.0), rt_=(5.5, 5.5), mb=2, ms=3, mt=5, crown=1.5 + 0.1 * idx, bulge=L["seat_bulge"],
               piping=("top", "bottom"), pipe_r=0.45, pipe_sides=6, uv_tile=BOUCLE)
    return md.map(deform)


# ============================================================ back cushions
# name, mat, width, height, thickness, centre (fraction of the half run of the back
# between the arms, measured r_ref from the circle centre; - left), row ('back': against
# the back, 'front': leant on the cushions behind it), yaw (+ turns the face to the
# right), lean (deg from vertical), roll, then _pillow_md: pinch, puff, wrinkle, ear,
# 'karate chop' dent, self piping, UV variants (top, bottom; 0 / 4 only: no quarter
# turns, so the real-scale rescale below keeps width on U).
CUSHIONS = [
    ("L1", "upholstery_alt", 52.0, 40.0, 15.0, -0.79, "back", 7.0, 19.0, -3.0, 0.08, 0.9, 1.2, 1.2, 1.2, False, (0, 4)),
    ("L2", "upholstery_alt", 60.0, 60.0, 18.0, -0.39, "back", -4.0, 15.0, 2.0, 0.09, 0.85, 1.3, 1.3, 1.6, False, (4, 0)),
    ("C1", "upholstery_alt", 58.0, 58.0, 17.0, 0.01, "back", 3.0, 14.0, -2.0, 0.10, 0.95, 1.0, 1.1, 1.0, False, (0, 0)),
    ("R1", "linen", 48.0, 48.0, 15.0, 0.39, "back", -6.0, 18.0, 3.0, 0.10, 1.05, 1.0, 1.45, 0.7, True, (0, 4)),
    ("R2", "upholstery_alt", 56.0, 56.0, 17.0, 0.755, "back", -8.0, 17.0, -2.0, 0.08, 0.9, 1.25, 1.2, 1.4, False, (4, 4)),
    ("F1", "linen", 62.0, 34.0, 13.0, -0.19, "front", 2.0, 22.0, 1.0, 0.10, 1.0, 0.9, 1.3, 0.0, False, (0, 0)),
    ("F2", "upholstery_alt", 44.0, 44.0, 14.0, 0.655, "front", 9.0, 24.0, -4.0, 0.09, 0.9, 1.3, 1.3, 1.0, False, (0, 4)),
]


def _turn(yaw, lean, roll):
    """The rotation furn_living._lean_pillow gives a flat cushion: stood on its -Y edge,
    leant back `lean` degrees from vertical (its +Z face to the front, -Y), rolled about
    the depth axis, then yawed about Z."""
    th = math.radians(90.0 - lean)
    c1, s1 = math.cos(th), math.sin(th)
    c2, s2 = math.cos(math.radians(roll)), math.sin(math.radians(roll))
    c3, s3 = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))

    def rot(p):
        x, y, z = p
        y, z = y * c1 - z * s1, y * s1 + z * c1
        x, z = x * c2 + z * s2, -x * s2 + z * c2
        return (x * c3 - y * s3, x * s3 + y * c3, z)
    return rot


def _real_scale_uv(md, w, h, tile, ou, ov):
    """_pillow_md's one-repeat-per-face UVs (0 / 4 variants) rescaled to `tile` cm per
    unit about the face centre and shifted (ou, ov), so the weave has its true size."""
    md.fuv = [None if uv is None else tuple(((u - 0.5) * w / tile + ou, (v - 0.5) * h / tile + ov) for u, v in uv)
              for uv in md.fuv]
    return md


def back_cushions(L, seats, seed=0, sink=1.3, press=0.6, iters=6):
    """The loose back cushions of CUSHIONS, in order: each yawed (facing the circle
    centre), leant and rolled, set at its place along the back, then settled - dropped
    until it sinks `sink` into the seat cushions, pushed out along its radius until it
    presses `press` into the back's inner face (front_d) or into a cushion placed
    before it. Returns [(name, mat, md, tile, axes, origin, seed)]: md in sofa space,
    tile = cm per UV unit."""
    seat_grid = _Grid2(0, 1, 2.0).add([v for md in seats for v in md.v])
    obs = _Grid2(0, 1, 2.0)
    yc, rr = L["yc"], L["r_ref"]

    def seat_top(x, y):
        pts = seat_grid.near(x, y, 2.5)
        return max(p[2] for p in pts) if pts else L["seat_h"]

    def gap(v):
        """How far v stands in front of the back or the cushions already placed."""
        d, s, _m = path_dist(L, v[0], v[1])
        lim = front_d(L, v[2], s)
        g = None if lim is None else d - lim
        x, y = v[0], v[1] - yc
        pts = obs.near(rr * math.atan2(x, y), v[2], 2.5)
        if pts:
            go = min(p[2] for p in pts) - math.hypot(x, y)
            g = go if g is None else min(g, go)
        return g

    out = []
    kz = _clamp(L["span_ref"] / SPAN_REF, 0.75, 1.0)            # smaller cushions on a shorter sofa
    for k, (nm, mat, w, h, thick, frac, row, yaw, lean, roll, pinch, puff, wrinkle, ear, chop, pipe, uvv) in \
            enumerate(CUSHIONS):
        w, h, thick = w * kz, h * kz, thick * kz
        rnd = _Rand(seed * 41 + 7 * k + 3)
        ps = 301 + 10 * seed + k
        tile = BOUCLE if mat == "upholstery_alt" else LINEN
        md = _pillow_md(w, h, thick, pinch=pinch, puff=puff, wrinkle=wrinkle, ear=ear, piping=pipe, pipe_r=0.4,
                        dent=chop, seed=ps, uv_var=uvv)
        _real_scale_uv(md, w, h, tile, rnd.uniform(0.0, 1.0), rnd.uniform(0.0, 1.0))
        th = (frac * L["span_ref"] + rnd.uniform(-1.5, 1.5)) / rr
        rot = _turn(yaw + rnd.uniform(-3.0, 3.0), lean + rnd.uniform(-2.0, 2.0), roll + rnd.uniform(-2.0, 2.0))
        tc, ec = (math.cos(th), -math.sin(th)), (math.sin(th), math.cos(th))
        r0 = rr - 25.0 - (14.0 if row == "front" else 0.0)
        z0 = L["seat_h"] + 0.5 * h

        def place(p, rot=rot, tc=tc, ec=ec, r0=r0, z0=z0):
            x, y, z = rot(p)
            return (x * tc[0] + (r0 + y) * ec[0], yc + x * tc[1] + (r0 + y) * ec[1], z0 + z)
        md.map(place)
        axes = []
        for b in ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)):
            x, y, z = rot(b)
            axes.append((x * tc[0] + y * ec[0], x * tc[1] + y * ec[1], z))
        org = list(place((0.0, 0.0, 0.0)))
        for it in range(iters):
            zmin = min(v[2] for v in md.v)
            dz = max(seat_top(v[0], v[1]) - sink - v[2] for v in md.v if v[2] < zmin + 5.0)
            md.map(lambda p, d=dz: (p[0], p[1], p[2] + d))
            org[2] += dz
            gs = [g for g in (gap(v) for v in md.v) if g is not None]
            if not gs:
                break
            dl = min(gs) + press
            md.map(lambda p, d=dl: (p[0] + d * ec[0], p[1] + d * ec[1], p[2]))
            org[0] += dl * ec[0]
            org[1] += dl * ec[1]
        obs.add([(rr * math.atan2(v[0], v[1] - yc), v[2], math.hypot(v[0], v[1] - yc)) for v in md.v])
        out.append(("CurvedSofa_Cushion" + nm, mat, md, tile, tuple(axes), tuple(org), ps))
    return out


# ====================================================================== parts
def curved_sofa_parts(chord=340.0, depth=95.0, seed=0, radius=300.0, cushions=True, sag=True):
    """Every part of the sofa as pure-Python cages (sofa space, cm): a list of Part."""
    L = sofa_layout(chord, depth, radius)
    seats = [seat_cushion_md(L, i, seed, sag) for i in range(3)]
    parts = [Part("CurvedSofa_Plinth", "metal_black", plinth_md(L), METAL, 1, own_uv=False),
             Part("CurvedSofa_Base", "upholstery_alt", base_md(L), BOUCLE, 1, noise=BODY_NOISE, seed=201 + seed),
             Part("CurvedSofa_Back", "upholstery_alt", back_md(L, seed), BOUCLE, 1, noise=BODY_NOISE, seed=202 + seed)]
    for i, (nm, md) in enumerate(zip(NAMES_SEAT, seats)):
        parts.append(Part("CurvedSofa_" + nm, "upholstery_alt", md, BOUCLE, 1, noise=CUSHION_NOISE,
                          seed=205 + i + seed))
    if cushions:
        for name, mat, md, tile, axes, org, ps in back_cushions(L, seats, seed=seed):
            parts.append(Part(name, mat, md, tile, 0, noise=PILLOW_NOISE, seed=ps, axes=axes, origin=org))
    return parts


# ==================================================================== 3ds Max
def _emit(p):
    if p.axes is not None:
        return fl._soft_framed(p.md, p.name, p.mat, p.noise, p.seed, p.axes, p.origin, tile=p.tile, own_uv=True,
                               smooth=p.smooth)
    if p.own_uv:
        return fl._soft(p.md, p.name, p.mat, p.noise, p.seed, p.smooth, tile=p.tile, own_uv=True)
    return fl._hard(p.md, p.name, p.mat, p.tile, p.smooth)


def build_curved_sofa(chord=340.0, depth=95.0, seed=0, radius=300.0, cushions=True):
    """Long curved boucle sofa, chord x depth (radially), back 72, seat 40 (see the module
    doc); cushions=False leaves the seven back cushions out. Front faces -Y (the arc
    bulges to +Y), floor at z = 0, the footprint's bounding box centred on the origin."""
    return kit.group("CurvedSofa", [_emit(p) for p in curved_sofa_parts(chord, depth, seed, radius, cushions)])


def preview():
    """Build one sofa at the origin (run inside 3ds Max)."""
    return build_curved_sofa()
