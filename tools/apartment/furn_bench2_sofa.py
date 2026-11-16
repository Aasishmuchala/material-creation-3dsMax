"""Long, low three-seat sofa for the MatForge benchmark-2 living room (moody
contemporary: copper Venetian plaster, grey microcement, white marble floor;
V-Ray in 3ds Max 2026). An original, generic design.

  build_sofa(width=270, seed=0, scatter=True)
      W width x D 100 x H 72 cm, seat height 42 at the front edge of the
      cushions. Built at the local origin (centre of the footprint, FRONT facing
      -Y, floor at z = 0) and returned as kit.group("BenchSofa", ...).

Anatomy (all the upholstery in "chenille", own UVs at a 25 cm repeat):
  * two pill arms 28 wide, 100 deep, 72 high: a stadium in plan (a full
    half-round front, a rounded rear), the top rounded right over (13 / 14.5 cm
    radii on a 13.5 half-width, so the section is a full round), a quarter
    sphere at the front-top corner, the bottom tucked under on a 4 cm radius, a
    slight belly on both faces. The wrapped panel's UV seam sits at the rear.
  * one continuous low back between the arms (its ends buried 11 cm in them):
    vertical below the deck, raked 15 degrees above it, under a soft top roll
    (68 high, 4 cm below the arms) that stands ~2 cm proud of the face below
    it; shallow dents where the two seats are leant against, the roll sagging
    5 mm mid-span and wavering a little (seeded).
  * an upholstered deck (the apron under the cushions), 22.5 cm tall, 3.5 cm
    behind the arm noses, its ends buried in the arms, a slight belly.
  * two long, deep seat cushions (107 x 75 x 16): self-piped welts on both
    seams, crowned tops, a sat-in hollow on each (deeper on the left), the
    front edge drooping at mid-span, soft creases radiating from the hollows,
    tension wrinkles out of the front corners and folds bunching over the front
    edge (seeded), squashed against each other, the arms and the raked back.
  * a slim recessed black plinth ("metal_black") 3.5 cm high, set 10 cm in at
    the front and sides and 6 cm at the back, so the sofa floats on a shadow line.
  * scatter=True: two knife-edge scatter cushions (furn_living._pillow_md) at
    the left end, a 50 cm rust velvet ("cushion") near the arm and a 48 cm grey
    linen ("linen", self-piped) beside it, yawed, leant and rolled differently,
    each settled on the seat cushion, against the back roll, the arm and each
    other.

All geometry is pure Python (furn_living._MD cages): sofa_layout, back_md,
arm_md, deck_md, plinth_md, seat_cushion_md, scatter_cushions and sofa_parts
(a list of Part tuples (name, material key, _MD, tile cm, TurboSmooth
iterations) carrying how the node is made), so tests/test_bench2_sofa_geom.py
checks it without 3ds Max; build_sofa only turns the parts into nodes.
"""
import math

import kit
import furn_living as fl
from furn_living import _MD, _Grid2, _Rand, _lean_pillow, _pillow_md, _slab, _smax, _smin, _smooth

# the benchmark-2 brief's upholstery key; kit.MAT_KEYS predates it (runtime only,
# kit.py is not edited). The scene maps it to its MatForge chenille.
kit.MAT_KEYS.setdefault("chenille", "beige chenille upholstery (benchmark 2 sofa)")

CHENILLE = 25.0                      # cm per UV unit on the chenille
METAL = 25.0                         # plinth powder coat (box-mapped)
BODY_NOISE = (40.0, 0.25, 0.25)      # Max Noise (scale, xy, z strength): arms, back, deck
CUSHION_NOISE = (24.0, 0.3, 0.35)    # seat cushions
PILLOW_NOISE = (12.0, 0.5, 0.6)      # scatter cushions (as furn_living's)
SEAT_STEP = 1.7                      # cm between seat-cushion cage lines (soft chenille creases)


class Part(tuple):
    """(name, mat, md, tile, smooth) plus how its node is made: own_uv (the cage
    carries UVs at `tile` cm per unit; else box-mapped at `tile`), Max Noise
    `noise` with `seed`, and for a framed node (a tilted scatter cushion) its
    axes (rows: local X, Y, Z) and origin."""

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


def _softplus(t, s):
    """Smooth max(t, 0) with a knee of width ~s."""
    if t / s > 30.0:
        return t
    return s * math.log1p(math.exp(t / s))


def _clamp(t, a=0.0, b=1.0):
    return a if t < a else b if t > b else t


# ===================================================================== layout
def sofa_layout(width=270.0, depth=100.0, height=72.0, seat_h=42.0, arm_w=28.0, back_h=68.0, plinth_h=3.5,
                seat_t=16.0):
    """Key dimensions (cm) of the sofa, all derived from the arguments."""
    W, D, H = float(width), float(depth), float(height)
    if W < 2.0 * arm_w + 80.0:
        raise ValueError("width %.0f: too narrow for two %.0f cm arms and two seats" % (W, arm_w))
    x_in = 0.5 * W - arm_w                       # inner faces of the arms
    y0, y1 = -0.5 * D, 0.5 * D
    z_b = float(plinth_h)                        # underside of the upholstery
    z_deck = float(seat_h) - seat_t              # deck top = seat cushion bottom
    L = dict(W=W, D=D, H=H, seat_h=float(seat_h), arm_w=float(arm_w), back_h=float(back_h), seat_t=float(seat_t),
             x_in=x_in, x_arm=0.5 * W - 0.5 * arm_w, y0=y0, y1=y1, z_b=z_b, z_deck=z_deck)
    # arms: stadium plan, bellied sides, full round top (horizontal radius just
    # under the half-width, so the top cap is a 1 cm strip, no pole)
    L.update(arm_A=0.5 * arm_w - 0.5, arm_bulge=0.5, arm_rb=4.0, arm_rt=(0.5 * arm_w - 1.0, 14.5),
             arm_front_ry=15.0)
    # back section: front face (vertical, raked above the deck), top roll, rear face
    yf, yr = y1 - 28.0, y1 - 1.2
    rake, knee, b, over = 0.27, 2.0, 10.0, 2.0
    zc = float(back_h) - b                       # the roll's widest line
    lin_c = yf + rake * _softplus(zc - z_deck, knee)
    yc = lin_c - over + 10.0                     # roll centre: its front stands `over` proud of the face
    L.update(back_yf=yf, back_yr=yr, back_rake=rake, back_knee=knee, back_rbf=1.5, back_rbr=5.0,
             roll_zc=zc, roll_b=b, roll_b2=6.0, roll_af=10.0, roll_yc=yc, back_x=x_in + 11.0,
             dent=0.7, dent_z=float(seat_h) + 5.0, dent_sx=30.0, dent_sz=9.0, roll_sag=0.5)
    # deck (apron under the cushions), seat cushions, plinth
    L.update(deck_yf=y0 + 3.5, deck_yr=yf + 8.0, deck_x=x_in + 10.0,
             seat_yf=y0 + 2.5, seat_yr=yf + 6.0,
             plinth_x=0.5 * W - 10.0, plinth_yf=y0 + 10.0, plinth_yr=y1 - 6.0)
    return L


# ======================================================================= back
def _dent(L, x, z):
    """How far (cm) the back's front face is pushed in where the two seats lean on it."""
    tot = 0.0
    for xs in (-0.5 * L["x_in"], 0.5 * L["x_in"]):
        tot += math.exp(-((x - xs) / L["dent_sx"]) ** 2 - ((z - L["dent_z"]) / L["dent_sz"]) ** 2)
    return L["dent"] * tot


def _roll_front(L, z):
    """Front of the top roll at height z: an ellipse quadrant above its widest line
    (radii roll_af x roll_b), a flatter one (roll_b2) below; None below the roll."""
    zc = L["roll_zc"]
    if z >= zc:
        q = min(1.0, (z - zc) / L["roll_b"])
    else:
        q = (zc - z) / L["roll_b2"]
        if q >= 1.0:
            return None
    return L["roll_yc"] - L["roll_af"] * math.sqrt(max(0.0, 1.0 - q * q))


def back_front_y(L, z, x=None):
    """y of the back's front face at height z: a 1.5 cm rounded foot, vertical up to
    the deck, then raked (soft knee) up into the roll, which takes over a little
    below its widest line. With x: including the seat dents."""
    z_b, r = L["z_b"], L["back_rbf"]
    if z < z_b + r:
        d = z_b + r - z
        y = L["back_yf"] + r - math.sqrt(max(0.0, r * r - d * d))
    else:
        y = L["back_yf"] + L["back_rake"] * _softplus(z - L["z_deck"], L["back_knee"])
        if z > L["roll_zc"]:
            y += 3.0 * (z - L["roll_zc"])          # the face turns back above the roll's lip
        rf = _roll_front(L, z)
        if rf is not None:
            y = _smin(y, rf, 0.8)
    if x is not None:
        y += _dent(L, x, z)
    return y


def back_rear_y(L, z):
    """y of the back's rear face at height z (5 cm rounded foot, vertical, roll)."""
    z_b, r, yr = L["z_b"], L["back_rbr"], L["back_yr"]
    if z < z_b + r:
        d = z_b + r - z
        return yr - r + math.sqrt(max(0.0, r * r - d * d))
    zc = L["roll_zc"]
    if z <= zc:
        return yr
    q = min(1.0, (z - zc) / L["roll_b"])
    return L["roll_yc"] + (yr - L["roll_yc"]) * math.sqrt(max(0.0, 1.0 - q * q))


def back_section(L):
    """The back's section as rungs [(y_front, y_rear, z)] from the underside to just
    below the top of the roll (front and rear points at common heights, so the end
    caps are ladders of horizontal quads), and the apex (y, z) of the roll."""
    z_b, zc, b = L["z_b"], L["roll_zc"], L["roll_b"]
    r = max(L["back_rbf"], L["back_rbr"])
    zs = [z_b + r * (1.0 - math.cos(math.radians(a))) for a in (0.0, 22.5, 45.0, 67.5)]
    z_lo, z_hi = z_b + r, zc - 4.5
    n = max(4, int(math.ceil((z_hi - z_lo) / 2.8)))
    zs += [z_lo + (z_hi - z_lo) * i / n for i in range(n)]
    zs += [z_hi, zc - 3.0, zc - 1.5]
    zs += [zc + b * math.sin(math.radians(10.0 * k)) for k in range(9)]     # the roll, by angle
    return [(back_front_y(L, z), back_rear_y(L, z), z) for z in zs], (L["roll_yc"], zc + b)


def back_md(L, seed=0):
    """The continuous back: back_section swept along X between x = -+back_x (its ends
    buried in the arms), capped by ladders of horizontal quads, then dented where the
    seats lean on it, its roll sagging mid-span and wavering a little (seeded). Own
    UVs: U along the back, V round the section (seam on the underside)."""
    rows, apex = back_section(L)
    m = len(rows)
    loop = [(yf, z) for yf, _yr, z in rows] + [apex] + [(yr, z) for _yf, yr, z in reversed(rows)]
    N = len(loop)                                   # 2 m + 1: front chain, apex, rear chain
    per = [0.0]
    for j in range(N):
        a, c = loop[j], loop[(j + 1) % N]
        per.append(per[-1] + math.hypot(c[0] - a[0], c[1] - a[1]))
    xe = L["back_x"]
    ns = max(8, int(math.ceil(2.0 * xe / 3.5)))
    xs = [-xe + 2.0 * xe * i / ns for i in range(ns + 1)]
    md = _MD()
    rings = [[md.add((x, y, z)) for (y, z) in loop] for x in xs]
    t = CHENILLE
    # the loop runs up the front, over the roll and down the rear: clockwise with y
    # to the right and z up, so (r0[j], r1[j], r1[j2], r0[j2]) faces outwards
    for i in range(ns):
        r0, r1 = rings[i], rings[i + 1]
        u0, u1 = xs[i] / t, xs[i + 1] / t
        for j in range(N):
            j2 = (j + 1) % N
            md.face((r0[j], r1[j], r1[j2], r0[j2]),
                    ((u0, per[j] / t), (u1, per[j] / t), (u1, per[j + 1] / t), (u0, per[j + 1] / t)))
    for ring, flip in ((rings[0], False), (rings[-1], True)):
        polys = [(ring[k], ring[k + 1], ring[2 * m - k - 1], ring[2 * m - k]) for k in range(m - 1)]
        polys.append((ring[m - 1], ring[m], ring[m + 1]))
        for pg in polys:
            md.face(tuple(reversed(pg)) if flip else pg)

    rnd = _Rand(seed * 19 + 3)
    ph1, ph2 = rnd.uniform(0.0, 2.0 * math.pi), rnd.uniform(0.0, 2.0 * math.pi)
    lam1, lam2 = rnd.uniform(80.0, 120.0), rnd.uniform(55.0, 80.0)
    x_in, zc = L["x_in"], L["roll_zc"]

    def deform(p):
        x, y, z = p
        yf, yr = back_front_y(L, z), back_rear_y(L, z)
        wf = _clamp((yr - y) / max(yr - yf, 1e-3))          # 1 on the front face, 0 on the rear
        wtop = _smooth((z - (zc - 8.0)) / 10.0)
        u = _clamp((x + x_in) / (2.0 * x_in))
        y += wf * (_dent(L, x, z) + 0.15 * math.sin(2.0 * math.pi * x / lam2 + ph2))
        waver = 0.5 + 0.5 * math.sin(2.0 * math.pi * x / lam1 + ph1)
        z -= wtop * (L["roll_sag"] * math.sin(math.pi * u) ** 2 + 0.18 * waver)
        return (x, y, z)
    return md.map(deform)


def arm_md(L, side, seed=0):
    """Pill arm on side -1 (left) or +1 (right), see the module doc. The _slab is built
    with its front at +Y and turned 180 degrees, so the wrapped panel's UV seam (the
    start of the slab's ring) lands at the arm's rear; the top wavers a little (seeded)."""
    A, B = L["arm_A"], 0.5 * L["D"]
    rear, front = (A, A), (A, L["arm_front_ry"])
    rb = L["arm_rb"]
    md = _slab(A, B, L["z_b"], L["H"], [rear, rear, front, front], p=16, q=34, rb=(rb, rb), rt_=L["arm_rt"],
               mb=3, ms=6, mt=10, bulge=L["arm_bulge"], uv_tile=CHENILLE)
    rnd = _Rand(seed * 23 + (7 if side < 0 else 13))
    a1, a2 = rnd.uniform(0.0, 2.0 * math.pi), rnd.uniform(0.0, 2.0 * math.pi)
    tilt = rnd.uniform(-0.15, 0.15)
    xa, zb, H = side * L["x_arm"], L["z_b"], L["H"]

    def place(p):
        x, y, z = p
        w = _clamp((z - zb) / (H - zb)) ** 2
        x += w * (tilt + 0.1 * math.sin(2.0 * math.pi * y / 61.0 + a1))
        z -= 0.15 * _smooth((z - (H - 9.0)) / 6.0) * (0.5 + 0.5 * math.sin(2.0 * math.pi * y / 47.0 + a2))
        return (xa - x, -y, z)
    return md.map(place)


def deck_md(L):
    """Upholstered deck under the seat cushions (the apron seen below them): its ends
    10 cm into the arms, its rear 8 cm into the back, a slight belly on the front and
    a 3 mm crown under the cushions. Own UVs."""
    yf, yr = L["deck_yf"], L["deck_yr"]
    A = L["deck_x"]
    return _slab(A, 0.5 * (yr - yf), L["z_b"], L["z_deck"], 4.5, p=max(24, int(round(2.0 * A / 4.0))), q=14,
                 rb=(3.0, 3.0), rt_=(4.0, 4.0), mb=2, ms=3, mt=3, cy=0.5 * (yf + yr), crown=0.3, bulge=0.5,
                 uv_tile=CHENILLE)


def plinth_md(L):
    """Recessed black steel plinth 3.5 cm high (1 mm into the upholstery above it),
    2 cm plan radius, 3 mm eased edges."""
    yf, yr = L["plinth_yf"], L["plinth_yr"]
    return _slab(L["plinth_x"], 0.5 * (yr - yf), 0.0, L["z_b"] + 0.1, 2.0, p=12, q=6, rb=(0.3, 0.3),
                 rt_=(0.3, 0.3), mb=1, ms=1, mt=1, cy=0.5 * (yf + yr), amin=1)


# ============================================================== seat cushions
def _grooves(a, b, lst):
    """Soft creases in a 2-D chart: each (a0, b0, a1, b1, depth, sigma) is a Gaussian
    groove (depth > 0) or ridge (< 0) along the segment, fading over its last 30 %."""
    tot = 0.0
    for a0, b0, a1, b1, dep, sg in lst:
        da, db = a1 - a0, b1 - b0
        t = ((a - a0) * da + (b - b0) * db) / (da * da + db * db)
        if t <= 0.0 or t >= 1.0:
            continue
        ea, eb = a0 + t * da - a, b0 + t * db - b
        q = (ea * ea + eb * eb) / (sg * sg)
        if q > 9.0:
            continue
        tot += dep * math.exp(-q) * _smooth(t / 0.3) * _smooth((1.0 - t) / 0.3)
    return tot


def seat_crease_lists(L, side, seed=0):
    """Seeded sat-in hollow and creases of one seat cushion: (hollow, top, front).
    hollow = (x, y, depth, sx, sy); top: grooves in the (x, y) chart of the top
    panel; front: grooves in the (x, s) chart unfolded over the front edge,
    s = distance back over the top (> 0) or down the front (< 0)."""
    rnd = _Rand(seed * 31 + (17 if side < 0 else 29))

    def j(a):
        return rnd.uniform(-a, a)

    A = 0.5 * L["x_in"]
    cx, yf = side * A, L["seat_yf"]
    # one seat is used more: a broad 1.9 cm hollow on the left, a 1.15 cm one on the right
    hollow = (cx + side * (5.0 + j(5.0)), yf + 29.0 + j(4.0), (1.9 if side < 0 else 1.15) * (1.0 + j(0.12)),
              24.0 + j(3.0), 20.0 + j(2.0))
    xs, ys = hollow[0], hollow[1]
    top = []
    base = rnd.uniform(0.0, 360.0)
    for k in range(3):                          # creases radiating out of the hollow
        a = math.radians(base + 120.0 * k + j(25.0))
        r0, ln = 6.0 + j(1.5), 15.0 + j(4.0)
        ca, sa = math.cos(a), math.sin(a)
        top.append((xs + r0 * ca, ys + r0 * sa, xs + (r0 + ln) * ca, ys + (r0 + ln) * sa,
                    0.28 + j(0.05), 2.0 + j(0.25)))
    for sx in (-1.0, 1.0):                      # tension wrinkles out of the front corners
        x0, y0 = cx + sx * (A - 3.0), yf + 3.0
        for ang in (35.0, 60.0):
            a = math.radians(ang + j(7.0))
            ln = 10.0 + j(2.0)
            top.append((x0, y0, x0 - sx * ln * math.cos(a), y0 + ln * math.sin(a), 0.2 + j(0.03), 1.5))
    front = []
    for f in (-0.62, -0.2, 0.18, 0.58):         # chenille bunching over the front edge
        x0 = cx + f * A + j(4.0)
        front.append((x0, 5.0 + j(1.0), x0 + j(2.5), -8.0 + j(1.5), 0.3 + j(0.04), 1.6 + j(0.2)))
    front.append((cx + j(6.0), 3.0, cx + j(6.0), -6.0, -0.15, 1.4))          # and one soft ridge
    return hollow, top, front


def seat_cushion_md(L, side, seed=0, creases=True, sag=True):
    """Seat cushion on side -1 (left) / +1 (right): a self-piped box cushion
    107 x 75 x 16 (at the default width) on the deck, crowned 1.6 cm, a sat-in
    hollow and the front edge drooping mid-span (sag=False leaves both out), seeded
    creases (creases=False leaves them out), squashed against its neighbour (2.4 mm
    apart), the arm and the raked back. Own UVs (top / bottom panels and a wrapped
    boxing strip)."""
    A = 0.5 * L["x_in"]
    cx = side * A
    yf, yr = L["seat_yf"], L["seat_yr"]
    B, cy = 0.5 * (yr - yf), 0.5 * (yf + yr)
    z0, T = L["z_deck"], L["seat_t"]
    z1 = z0 + T
    rt = 3.4
    use_sag = sag
    (xs, ys, sag, sx, sy), top, front = seat_crease_lists(L, side, seed)
    droop = 0.5
    if not use_sag:
        sag = droop = 0.0
    xw = L["x_in"] - L["arm_bulge"]
    lo, hi = (cx - A + rt, yf + rt, z0 + rt), (cx + A - rt, yr - rt, z1 - rt)

    def deform(p):
        x, y, z = p
        wt = _clamp((z - z0) / T) ** 2          # the hollow fades out towards the bottom panel
        dz = sag * math.exp(-((x - xs) / sx) ** 2 - ((y - ys) / sy) ** 2)
        dz += droop * max(0.0, 1.0 - ((x - cx) / A) ** 2) ** 2 * _smooth((yf + 16.0 - y) / 16.0)
        c = 0.0
        if creases:
            wtop = _smooth((z - (z1 - rt)) / rt)
            if wtop > 0.0:
                c += wtop * _grooves(x, y, top)
            wfr = (1.0 - _smooth((y - (yf + 9.0)) / 4.0)) * _smooth((z - (z0 + 3.0)) / 2.5)
            if wfr > 0.0:
                c += wfr * _grooves(x, (y - yf) - (z1 - z), front)
        if c:                                   # along the rounded box's outward normal
            q = [min(max(p[k], lo[k]), hi[k]) for k in range(3)]
            n = (x - q[0], y - q[1], z - q[2])
            ln = math.sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2])
            if ln > 1e-6:
                x, y, z = x - c * n[0] / ln, y - c * n[1] / ln, z - c * n[2] / ln
        z -= dz * wt
        if side < 0:
            x = _smax(_smin(x, -0.12, 0.35), -xw, 0.35)
        else:
            x = _smin(_smax(x, 0.12, 0.35), xw, 0.35)
        y = _smin(y, back_front_y(L, z, x) + 0.2, 0.5)
        return (x, y, z)

    p = max(24, int(round(2.0 * A / SEAT_STEP)))
    q = max(16, int(round(2.0 * B / SEAT_STEP)))
    # built round the origin with its front at +Y (5 cm front corners, 4 cm rear ones)
    # and turned 180 degrees into place, so the boxing strip's UV seam (the start of
    # the slab's ring) lands at a rear corner, against the back, not on a front corner
    md = _slab(A, B, z0, z1, [(4.0, 4.0), (4.0, 4.0), (5.0, 5.0), (5.0, 5.0)], p=p, q=q, rb=(2.4, 2.4),
               rt_=(rt, rt), mb=2, ms=3, mt=4, crown=1.6 + (0.15 if side > 0 else 0.0), bulge=0.9,
               piping=("top", "bottom"), pipe_r=0.45, pipe_sides=6, uv_tile=CHENILLE)
    return md.map(lambda v: deform((cx - v[0], cy - v[1], v[2])))


# =========================================================== scatter cushions
# name, mat, size, thickness, centre (cm in from the left arm's inner face), yaw,
# lean (deg from vertical), roll, then _pillow_md: pinch, puff, wrinkle, ear,
# 'karate chop' dent, self piping, UV variants (front, back); last how it rests:
# 'corner' leans into the arm as well as on the back (its yaw kept), 'rest' turns
# (within +-12 deg of its yaw) until it rests on two supports - the back and the
# cushion before it - instead of balancing on one.
SCATTER = [
    ("Velvet", "cushion", 50.0, 16.0, 27.0, 14.0, 23.0, -4.0, 0.08, 0.85, 1.35, 1.2, 1.7, False, (1, 6), "corner"),
    ("Linen", "linen", 48.0, 15.0, 70.0, -9.0, 15.0, 5.0, 0.1, 1.05, 1.0, 1.45, 0.7, True, (3, 4), "rest"),
]


def _settle(md, org, seat_top, back_front, arm_x, sink=1.3, press=0.6, give=0.3, iters=4, to_arm=False):
    """Translate a leant cushion (in place) until it clears the arm (pressed `give`
    into it at most; to_arm: also slid over to touch it), rests `sink` deep in the
    seat and touches what it leans on (`press` deep); returns its moved origin."""
    org = list(org)
    for _ in range(iters):
        pen = None
        for v in md.v:
            ax = arm_x(v[1], v[2])
            if ax is not None and (pen is None or ax - give - v[0] > pen):
                pen = ax - give - v[0]
        if pen is not None and (pen > 1e-4 or to_arm):
            md.map(lambda p, d=pen: (p[0] + d, p[1], p[2]))
            org[0] += pen
        zmin = min(v[2] for v in md.v)
        dz = max(seat_top(v[0], v[1]) - sink - v[2] for v in md.v if v[2] < zmin + 5.0)
        md.map(lambda p, d=dz: (p[0], p[1], p[2] + d))
        org[2] += dz
        best = None
        for v in md.v:
            yf = back_front(v[0], v[2])
            if yf is not None and (best is None or yf + press - v[1] < best):
                best = yf + press - v[1]
        if best is not None:
            md.map(lambda p, d=best: (p[0], p[1] + d, p[2]))
            org[1] += best
    return tuple(org)


def scatter_cushions(L, seats, back, arm_left, seed=0):
    """The two scatter cushions at the left end (see SCATTER), each yawed, leant and
    rolled, then settled on the seat cushions, against the back (and the cushion
    placed before it) and clear of the left arm. Returns
    [(name, mat, md, tile, axes, origin, seed)]: md in sofa space, tile = one UV
    repeat per face."""
    seat_grid = _Grid2(0, 1, 2.0).add([v for md in seats for v in md.v])
    lean_grid = _Grid2(0, 2, 2.0).add(back.v)
    arm_grid = _Grid2(1, 2, 2.0).add([v for v in arm_left.v if v[0] > -L["x_arm"]])   # its inner half

    def seat_top(x, y):
        pts = seat_grid.near(x, y, 2.5)
        return max(p[2] for p in pts) if pts else L["seat_h"]

    def back_front(x, z):
        pts = lean_grid.near(x, z, 2.5)
        return min(p[1] for p in pts) if pts else None

    def arm_x(y, z):
        pts = arm_grid.near(y, z, 2.5)
        return max(p[0] for p in pts) if pts else None

    out = []
    for k, (nm, mat, size, thick, dx, yaw, lean, roll, pinch, puff, wrinkle, ear, chop, pipe, uvv, how) in \
            enumerate(SCATTER):
        rnd = _Rand(seed * 41 + 7 * k + 3)
        ps = 71 + 10 * seed + k
        base = _pillow_md(size, size, thick, pinch=pinch, puff=puff, wrinkle=wrinkle, ear=ear, piping=pipe,
                          pipe_r=0.4, dent=chop, seed=ps, uv_var=uvv)
        xc = -L["x_in"] + dx + rnd.uniform(-1.5, 1.5)
        yaw += rnd.uniform(-3.0, 3.0)
        lean += rnd.uniform(-2.0, 2.0)
        roll += rnd.uniform(-2.0, 2.0)
        best = None
        for dyaw in ((-12.0, -8.0, -4.0, 0.0, 4.0, 8.0, 12.0) if how == "rest" else (0.0,)):
            md = _MD()
            md.merge(base)
            axes, org = _lean_pillow(md, xc, yaw + dyaw, lean, roll, seat_top, back_front)
            org = _settle(md, org, seat_top, back_front, arm_x, to_arm=(how == "corner"))
            score = _float_gap(md, org[0], back_front) + 0.02 * abs(dyaw)
            if best is None or score < best[0]:
                best = (score, md, axes, org)
        _s, md, axes, org = best
        lean_grid.add(md.v)
        out.append(("BenchSofa_Scatter" + nm, mat, md, size, axes, org, ps))
    return out


def _float_gap(md, xc, back_front, press=0.6):
    """How far the less supported half (left or right of x = xc) of a settled cushion
    stands off what it leans on (0: both halves touch)."""
    gaps = [None, None]
    for v in md.v:
        yf = back_front(v[0], v[2])
        if yf is None:
            continue
        k = 0 if v[0] < xc else 1
        d = yf + press - v[1]
        if gaps[k] is None or d < gaps[k]:
            gaps[k] = d
    return max(g for g in gaps if g is not None) if any(g is not None for g in gaps) else 0.0


# ====================================================================== parts
def sofa_parts(width=270.0, seed=0, scatter=True, creases=True):
    """Every part of the sofa as pure-Python cages (sofa space, cm): a list of Part."""
    L = sofa_layout(width)
    back = back_md(L, seed)
    arms = [arm_md(L, s, seed) for s in (-1, 1)]
    seats = [seat_cushion_md(L, s, seed, creases) for s in (-1, 1)]
    parts = [Part("BenchSofa_Plinth", "metal_black", plinth_md(L), METAL, 1, own_uv=False),
             Part("BenchSofa_Deck", "chenille", deck_md(L), CHENILLE, 1, noise=BODY_NOISE, seed=101 + seed),
             Part("BenchSofa_Back", "chenille", back, CHENILLE, 1, noise=BODY_NOISE, seed=102 + seed),
             Part("BenchSofa_ArmL", "chenille", arms[0], CHENILLE, 1, noise=BODY_NOISE, seed=103 + seed),
             Part("BenchSofa_ArmR", "chenille", arms[1], CHENILLE, 1, noise=BODY_NOISE, seed=104 + seed),
             Part("BenchSofa_SeatL", "chenille", seats[0], CHENILLE, 1, noise=CUSHION_NOISE, seed=105 + seed),
             Part("BenchSofa_SeatR", "chenille", seats[1], CHENILLE, 1, noise=CUSHION_NOISE, seed=106 + seed)]
    if scatter:
        for name, mat, md, tile, axes, org, ps in scatter_cushions(L, seats, back, arms[0], seed):
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


def build_sofa(width=270.0, seed=0, scatter=True):
    """Long low three-seat sofa W width x D 100 x H 72, seat 42, in chenille (see the
    module doc); scatter=False leaves the two scatter cushions out. Front faces -Y,
    base on z = 0, centred on the footprint."""
    return kit.group("BenchSofa", [_emit(p) for p in sofa_parts(width, seed, scatter)])


def preview():
    """Build one sofa at the origin (run inside 3ds Max)."""
    return build_sofa()
