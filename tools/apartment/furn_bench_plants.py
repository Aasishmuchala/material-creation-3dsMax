"""Large indoor plants and stoneware planters for the white-apartment benchmark scene.

Pieces (centimetres, Z up, each built round its own origin: the centre of its
footprint on the floor, z = 0 at the floor; every visible node goes through
kit.part and the piece is returned as kit.group):

  build_banana_plant(seed=0, pot=(45, 50), with_pot=True)
      bird of paradise (Strelitzia nicolai), 174-186 cm tall: 11-13 big leaf
      cards (blades 61-89 x 20.5-29.5 cm) on long upright petioles rising in
      three fans out of flattened, overlapping sheaths, the newest leaf still
      rolled into a spike in the main fan; potted in the tall 45 x 50 planter.
  build_bushy_plant(seed=0, pot=(32, 34), with_pot=True)
      bushy plant 86-104 cm tall: 3-4 leaning main stems with side branches,
      26-37 leaf cards (blades 12-25 cm) in a spiral phyllotaxis on short
      petioles; potted in the 32 x 34 planter.
  build_planter(diameter=45, height=50)
      matte white stoneware planter: slight taper, real wall, bullnosed rim,
      filleted foot ring under a recessed base, an irregular soil surface.

with_pot=False leaves the planter out of a plant: the plant still stands at
the soil level of a build_planter(*pot) placed at the same spot.

Leaf cards (key leaf_card) carry the WHOLE leaf photo on their 0-1 UVs: the
card's length runs along V with the petiole end at v = 0, its width along U,
the midrib on u = 0.5. Each card is a grid bent along its length (droop),
folded along the midrib, rippled towards its margins and twisted, every leaf
from its own draws of a seeded RNG. The card is sized from the blade it must
show (LC_* below), so the cut-out margins are wider than the blade.

Everything is generated in pure Python (LeafCard, planter_md, soil_md and the
*_geometry functions return furn_living._MD cages), so it is tested off-Max
(tests/test_bench_plants_geom.py); the build_* wrappers only turn the cages
into Max nodes.
"""
import math
import random

import kit
from furn_living import (_MD, _add, _build, _cross, _dot, _fillet2d, _hard, _mul, _norm, _revolve_md,
                         _rot_axis, _smooth, _sub, _tube_md)

TWO_PI = 2.0 * math.pi
POT_TILE = 35.0       # matte stoneware: one texture repeat per 35 cm
SOIL_TILE = 30.0
STEM_TILE = 20.0


# ====================================================== leaf-card photo layout
# Where the leaf sits in the leaf_card maps (strelitzia_leaf albedo / opacity,
# traced from the opacity mask): the midrib is the line u = 0.5, the petiole
# stub enters at v = 0, the blade runs from v = LC_V0 to its tip at v = LC_V1,
# and LC_OUTLINE gives its half-width in u along v (widest, LC_HWMAX, at
# v = 0.38). A blade of length BL and width BW therefore needs a card
# BL / (LC_V1 - LC_V0) long and BW / (2 LC_HWMAX) wide.
LC_V0 = 0.042
LC_V1 = 0.922
LC_HWMAX = 0.186
LC_OUTLINE = [(0.048, 0.044), (0.079, 0.080), (0.120, 0.116), (0.172, 0.150), (0.224, 0.166),
              (0.275, 0.176), (0.327, 0.184), (0.379, 0.186), (0.431, 0.185), (0.482, 0.181),
              (0.534, 0.176), (0.586, 0.166), (0.638, 0.153), (0.689, 0.137), (0.741, 0.119),
              (0.793, 0.104), (0.845, 0.085), (0.896, 0.057)]


def _outline_hw(v):
    """Half-width (u units) of the photographed blade at v."""
    if v <= LC_OUTLINE[0][0] or v >= LC_V1:
        return 0.0
    prev = LC_OUTLINE[0]
    for cur in LC_OUTLINE[1:] + [(LC_V1, 0.0)]:
        if v <= cur[0]:
            t = (v - prev[0]) / (cur[0] - prev[0])
            return prev[1] + (cur[1] - prev[1]) * t
        prev = cur
    return 0.0


def _stations(offsets):
    """Grid lines symmetric about the midrib u = 0.5 (exact 0, 0.5 and 1)."""
    out = set()
    for o in offsets:
        out.add(round(0.5 - o, 6))
        out.add(round(0.5 + o, 6))
    return sorted(out)


def _rows(n):
    """v stations: the petiole stub, the blade base LC_V0, n even rows to the
    card's far edge (exactly 1.0)."""
    return [0.0, 0.5 * LC_V0, LC_V0] + [LC_V0 + (1.0 - LC_V0) * k / float(n) for k in range(1, n)] + [1.0]


# banana leaves: dense across the blade (u 0.31-0.69), coarse over the cut-out margins
BANANA_US = _stations((0.0, 0.012, 0.03, 0.055, 0.085, 0.12, 0.155, 0.19, 0.25, 0.34, 0.5))
BANANA_VS = _rows(22)
BUSH_US = _stations((0.0, 0.03, 0.075, 0.125, 0.19, 0.3, 0.5))
BUSH_VS = [0.0, LC_V0] + [LC_V0 + (1.0 - LC_V0) * k / 11.0 for k in range(1, 11)] + [1.0]


# =================================================================== maths
def _rotz(v, a):
    c, s = math.cos(a), math.sin(a)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c, v[2])


def _dir(h, a, rot):
    """Unit vector a radians off vertical, leaning towards h turned by rot about Z."""
    hx, hy, _ = _rotz(h, rot)
    sa = math.sin(a)
    return (sa * hx, sa * hy, math.cos(a))


def _xf(p, o, axes):
    """Local point -> world, for a frame with origin o and axes (X, Y, Z)."""
    X, Y, Z = axes
    return (o[0] + X[0] * p[0] + Y[0] * p[1] + Z[0] * p[2],
            o[1] + X[1] * p[0] + Y[1] * p[1] + Z[1] * p[2],
            o[2] + X[2] * p[0] + Y[2] * p[1] + Z[2] * p[2])


def _min_d2(pts, clouds):
    best = float("inf")
    for cloud in clouds:
        for a in pts:
            for b in cloud:
                d = (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2
                if d < best:
                    best = d
    return best


def _hash01(ix, iy, seed):
    h = (ix * 374761393 + iy * 668265263 + seed * 362437 + 1013904223) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return (h ^ (h >> 16)) / 4294967295.0


def _vnoise(x, y, seed=0):
    """Smooth value noise in [0, 1]."""
    ix, iy = int(math.floor(x)), int(math.floor(y))
    fx, fy = x - ix, y - iy
    sx, sy = fx * fx * (3.0 - 2.0 * fx), fy * fy * (3.0 - 2.0 * fy)
    a, b = _hash01(ix, iy, seed), _hash01(ix + 1, iy, seed)
    c, d = _hash01(ix, iy + 1, seed), _hash01(ix + 1, iy + 1, seed)
    lo, hi = a + (b - a) * sx, c + (d - c) * sx
    return lo + (hi - lo) * sy


def _fbm(x, y, seed=0, octaves=3):
    tot = norm = 0.0
    amp = f = 1.0
    for o in range(octaves):
        tot += amp * _vnoise(x * f, y * f, seed + 31 * o)
        norm += amp
        amp *= 0.5
        f *= 2.0
    return tot / norm


# =============================================================== leaf cards
_FE = 0.08                                    # midrib rounding (fraction of the half-width)
_FN = math.sqrt(1.0 + _FE * _FE) - _FE
_FS = 0.55 / (math.sqrt(1.0 + _FE * _FE) * _FN) + 0.9


def _fold_profile(xn):
    """Cross-section of a leaf folded along its midrib: 0 on the midrib, 1 at
    the widest blade edge (xn = |x| / blade half-width): a V rounded over the
    midrib blending into a gentle cup, then flattening out (C1) over the
    card's cut-out margins so they do not fly up."""
    if xn <= 1.0:
        return 0.55 * (math.sqrt(xn * xn + _FE * _FE) - _FE) / _FN + 0.45 * xn * xn
    return 1.0 + 0.5 * _FS * (1.0 - math.exp(-2.0 * (xn - 1.0)))



def photo_fit(v_attach, v_tip, mid_u=0.5):
    """uv_xf for a leaf photo framed unlike the strelitzia one the cards are
    cut for: the card's attach point (u 0.5, LC_V0) shows the photo at
    (mid_u, v_attach), where its stalk starts, and the blade end LC_V1 its
    tip v_tip, scaled the same both ways so the leaf keeps its shape. The
    rubber-plant photo's stalk only starts at v 0.097 (strelitzia: 0.0), so
    unfitted its leaves hung 0.8-1.4 cm off their petioles."""
    k = (v_tip - v_attach) / (LC_V1 - LC_V0)
    # held inside the photo: past its edge the bitmap wraps, and the card's
    # top margin showed the foot of the stalk as specks floating over each tip
    hold = lambda t: min(0.999, max(0.001, t))
    return lambda u, v: (hold(mid_u + (u - 0.5) * k), hold(v_attach + (v - LC_V0) * k))


class LeafCard(object):
    """One leaf card in its own frame: origin at the petiole attach point
    (u = 0.5, v = LC_V0), +Y along the blade where it leaves the petiole, +Z
    the front-face normal there, +X = +U (X x Y = Z, so the photo reads
    unmirrored from +Z). The midrib droops (bends towards -Z) by `droop`
    radians at the tip, more towards the tip (exponent q), twists by `twist`
    radians about itself, the halves rise by `fold` cm at the widest point
    (asym: one half more than the other) and the margins ripple (amplitude,
    wavelength, phase). Arc length along the midrib is preserved, so the
    blade really is blade_len long."""

    def __init__(self, blade_len, blade_w, droop=0.0, twist=0.0, fold=0.0, asym=0.0,
                 ripple=(0.0, 20.0, 0.0), q=1.6, steps=160):
        self.blade_len = float(blade_len)
        self.blade_w = float(blade_w)
        self.L = self.blade_len / (LC_V1 - LC_V0)        # card length (V)
        self.W = self.blade_w / (2.0 * LC_HWMAX)         # card width (U)
        self.hw = 0.5 * self.blade_w
        self.droop, self.twist = float(droop), float(twist)
        self.fold, self.asym = float(fold), float(asym)
        self.rip_a, self.rip_l, self.rip_p = (float(c) for c in ripple)
        self.q = float(q)
        smax = (1.0 - LC_V0) * self.L
        self.ds = smax / steps
        ys, zs = [0.0], [0.0]
        for k in range(steps):                           # midrib: integrate the unit tangent
            th = self.theta((k + 0.5) * self.ds)
            ys.append(ys[-1] + math.cos(th) * self.ds)
            zs.append(zs[-1] + math.sin(th) * self.ds)
        self._ys, self._zs = ys, zs

    def theta(self, s):
        """Midrib angle (radians, negative = drooping) at arc length s."""
        return -self.droop * (max(s, 0.0) / self.blade_len) ** self.q

    def frame(self, s):
        """(M, T, X, N): midrib point, tangent, lateral axis and front normal
        at arc length s from the attach point (s < 0: the straight stub)."""
        if s <= 0.0:
            return (0.0, s, 0.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)
        f = s / self.ds
        k = min(int(f), len(self._ys) - 2)
        t = f - k
        M = (0.0, self._ys[k] + (self._ys[k + 1] - self._ys[k]) * t,
             self._zs[k] + (self._zs[k + 1] - self._zs[k]) * t)
        th = self.theta(s)
        ct, st = math.cos(th), math.sin(th)
        tau = self.twist * (s / self.blade_len) ** 1.2
        c, sn = math.cos(tau), math.sin(tau)
        return M, (0.0, ct, st), (c, -st * sn, ct * sn), (-sn, -st * c, ct * c)

    def lift(self, x, s):
        xn = abs(x) / self.hw
        fade = _smooth((s + 0.03 * self.L) / (0.08 * self.L))     # flat over the stub
        side = 1.0 + (self.asym if x > 0.0 else -self.asym)
        rip = self.rip_a * min(xn, 1.4) ** 2 * math.sin(TWO_PI * s / self.rip_l + self.rip_p)
        return fade * (self.fold * side * _fold_profile(xn) + rip)

    def point(self, u, v):
        x = (u - 0.5) * self.W
        s = (v - LC_V0) * self.L
        M, _T, X, N = self.frame(s)
        h = self.lift(x, s)
        return (M[0] + X[0] * x + N[0] * h, M[1] + X[1] * x + N[1] * h, M[2] + X[2] * x + N[2] * h)

    def card_md(self, us, vs, uv_xf=None):
        """The card as a quad grid over the u / v stations, every corner
        carrying its own (u, v): the whole 0-1 square of the photo, or where
        uv_xf (u, v) -> (u, v) sends it for a photo framed otherwise
        (photo_fit)."""
        md = _MD()
        rows = [[md.add(self.point(u, v)) for u in us] for v in vs]
        uv = uv_xf or (lambda u, v: (u, v))
        for j in range(len(vs) - 1):
            for i in range(len(us) - 1):
                md.face((rows[j][i], rows[j][i + 1], rows[j + 1][i + 1], rows[j + 1][i]),
                        (uv(us[i], vs[j]), uv(us[i + 1], vs[j]), uv(us[i + 1], vs[j + 1]), uv(us[i], vs[j + 1])))
        return md


    def probes(self):
        """Points on the visible blade (its photographed outline and midrib)."""
        pts = [self.point(0.5, LC_V0), self.point(0.5, LC_V1)]
        for v, hw in LC_OUTLINE:
            pts += [self.point(0.5 - hw, v), self.point(0.5, v), self.point(0.5 + hw, v)]
        return pts

    def coarse(self):
        """Nine points spread over the blade, for cheap leaf-leaf clearance."""
        pts = []
        for v in (0.28, 0.52, 0.76):
            hw = 0.6 * _outline_hw(v)
            pts += [self.point(0.5 - hw, v), self.point(0.5, v), self.point(0.5 + hw, v)]
        return pts

    def midrib(self, r0, n=18, reach=0.85, gap=0.04):
        """The midrib as a tapering tube path [(point, radius)] continuing the
        petiole: on the attach point it runs through the card (the blade
        grows out of it), then sinks within 5 cm to just under the blade, so
        it stands proud on the underside like a real midrib and never pokes
        through the photo's own midrib on top."""
        out = []
        smax = reach * self.blade_len
        for k in range(1, n + 1):
            s = smax * (k / float(n)) ** 1.3
            r = max(0.06, r0 * (1.0 - 0.9 * (s / smax) ** 0.75))
            M, _T, _X, N = self.frame(s)
            off = (r + gap) * _smooth(s / 5.0)
            out.append(((M[0] - N[0] * off, M[1] - N[1] * off, M[2] - N[2] * off), r))
        return out


# ================================================================== sweeps
def _ellipse(a, b, sides):
    return [(a * math.cos(TWO_PI * k / sides), b * math.sin(TWO_PI * k / sides)) for k in range(sides)]


def _sweep_md(path, rings, ref, caps=True):
    """Tube along a 3-D polyline with free cross-sections: rings[i] lists ring
    i's vertex offsets (a, b) along the section axes A (ref taken off the
    path tangent at the start, then parallel-transported, so the sections
    never flip) and B = T x A, counter-clockwise from A. Capped ends make it
    a closed solid with outward normals (same winding as _tube_md)."""
    md = _MD()
    n = len(path)
    sides = len(rings[0])
    tang = []
    for i in range(n):
        tang.append(_norm(_sub(path[min(i + 1, n - 1)], path[max(i - 1, 0)])))
    A = _sub(ref, _mul(tang[0], _dot(ref, tang[0])))
    if _dot(A, A) < 1e-10:
        A = _cross(tang[0], (1.0, 0.0, 0.0) if abs(tang[0][0]) < 0.9 else (0.0, 1.0, 0.0))
    A = _norm(A)
    for i in range(n):
        A = _norm(_sub(A, _mul(tang[i], _dot(A, tang[i]))))
        B = _cross(tang[i], A)
        p = path[i]
        for ca, cb in rings[i]:
            md.add((p[0] + ca * A[0] + cb * B[0], p[1] + ca * A[1] + cb * B[1], p[2] + ca * A[2] + cb * B[2]))
    for i in range(n - 1):
        for s in range(sides):
            s2 = (s + 1) % sides
            md.face((i * sides + s, i * sides + s2, (i + 1) * sides + s2, (i + 1) * sides + s))
    if caps:
        c0 = md.add(path[0])
        c1 = md.add(path[-1])
        last = (n - 1) * sides
        for s in range(sides):
            s2 = (s + 1) % sides
            md.face((c0, s2, s))
            md.face((c1, last + s, last + s2))
    return md


def _petiole_unit(lean, alpha, drift, n=20, a0=0.5):
    """Unit-length petiole from the origin: its angle off vertical grows from
    a0 * alpha at the base to alpha at the blade (it splays out of the
    sheath, then runs nearly straight), its lean drifting by `drift` radians
    about Z. Returns the n + 1 points and the end tangent."""
    pts = [(0.0, 0.0, 0.0)]
    for k in range(n):
        t = (k + 0.5) / n
        d = _dir(lean, alpha * (a0 + (1.0 - a0) * t ** 0.8), drift * t)
        pts.append(_add(pts[-1], _mul(d, 1.0 / n)))
    return pts, _dir(lean, alpha, drift)


def _petiole_rings(n, r_base, r_top, sides, sheath=0.16):
    """Petiole sections: tapering from r_base to r_top, the bottom `sheath`
    of its length widened into a flattened sheath (wide in the fan plane)."""
    rings = []
    for i in range(n + 1):
        t = i / float(n)
        r = r_base + (r_top - r_base) * t ** 0.7
        w = max(0.0, 1.0 - t / sheath) ** 2
        rings.append(_ellipse(r * (1.0 + 0.8 * w), r * (1.0 - 0.25 * w), sides))
    return rings


def _blade_axes(T, nf, beta, face, roll):
    """World axes (X, Y = T, Z) of a blade leaving its petiole along T: the
    front normal Z turns from the fan normal (beta = 0: the blade faces
    sideways, a young upright leaf) to 'up' (beta = 90 deg: it lies face up
    and droops over, an old leaning leaf), then rolls about T."""
    up = (0.0, 0.0, 1.0)
    ud = _sub(up, _mul(T, _dot(up, T)))
    ud = _norm(ud) if _dot(ud, ud) > 1e-10 else _norm(_cross(T, nf))
    npl = _norm(_sub(nf, _mul(T, _dot(nf, T))))
    Z = _norm(_add(_mul(npl, face * math.cos(beta)), _mul(ud, math.sin(beta))))
    Z = _norm(_rot_axis(Z, T, roll))
    return _cross(T, Z), T, Z


def _up_axes(T, roll):
    """Blade axes facing up (front normal = 'up' off the midrib), rolled about T."""
    up = (0.0, 0.0, 1.0)
    ud = _sub(up, _mul(T, _dot(up, T)))
    ud = _norm(ud) if _dot(ud, ud) > 1e-10 else _norm(_cross(T, (1.0, 0.0, 0.0)))
    Z = _norm(_rot_axis(ud, T, roll))
    return _cross(T, Z), T, Z


# ================================================================ planters
def planter_dims(diameter=45.0, height=50.0):
    """Wall 1.0-1.6 cm (3 % of the diameter), the base 4 % of the height
    narrower in radius than the rim (about 2.3 deg of taper), a floor
    1.5-2 cm thick, the soil 3-4.5 cm below the rim."""
    R, H = 0.5 * float(diameter), float(height)
    return {"R": R, "H": H, "wall": min(1.6, max(1.0, 0.03 * float(diameter))), "Rb": R - 0.04 * H,
            "floor": max(1.5, 0.04 * H), "soil_z": H - max(3.0, 0.09 * H)}


def _r_out(d, z):
    return d["Rb"] + (d["R"] - d["Rb"]) * z / d["H"]


def _r_in(d, z):
    return _r_out(d, z) - d["wall"]


def planter_profile(diameter=45.0, height=50.0):
    """(r, z) section of the pot, counter-clockwise round the material: the
    recessed underside, a 1.9 cm foot ring (7 mm fillet at the floor), the
    tapered outer wall, a bullnosed rim (two fillets of almost half the wall),
    the inner wall and a 1.2 cm fillet into the floor. Every corner is
    filleted in 15-degree steps; the straight walls carry extra stations so
    TurboSmooth keeps them straight."""
    d = planter_dims(diameter, height)
    R, H, t, Rb, zf = d["R"], d["H"], d["wall"], d["Rb"], d["floor"]
    rec = 0.35
    nw = max(2, int(round(H / 10.0)))
    pts = [(0.0, rec), (Rb - 2.6, rec), (Rb - 1.9, 0.0), (Rb, 0.0)]
    rad = [0.0, 0.2, 0.25, 0.7]
    for k in range(1, nw):
        z = H * k / nw
        pts.append((_r_out(d, z), z))
        rad.append(0.0)
    pts += [(R, H), (R - t, H)]
    rad += [0.48 * t, 0.48 * t]
    for k in range(nw - 1, 0, -1):
        z = zf + (H - zf) * k / nw
        pts.append((_r_in(d, z), z))
        rad.append(0.0)
    pts += [(_r_in(d, zf), zf), (0.0, zf)]
    rad += [1.2, 0.0]
    return _fillet2d(pts, rad, step=math.radians(15.0))


def planter_md(diameter=45.0, height=50.0):
    """Closed quad cage of the pot (poles on the axis top and bottom)."""
    return _revolve_md(planter_profile(diameter, height), 64 if diameter >= 40.0 else 56)


def soil_md(diameter=45.0, height=50.0, mounds=(), seed=0, depth=3.0):
    """Closed slab of potting soil whose rim runs 4.5 mm into the pot wall
    (no gap at the wall even after TurboSmooth): an irregular top (two
    octaves of clods, 0.2-0.5 cm), heaped up round the plant's stems by
    `mounds` [(x, y, height, radius)]."""
    d = planter_dims(diameter, height)
    zt = d["soil_z"]
    re = _r_in(d, zt) + 0.45
    rbot = _r_in(d, zt - depth) + 0.45
    S = 72 if diameter >= 40.0 else 60
    K = 14

    def top(x, y):
        z = (zt + 0.5 * (_fbm(x / 6.0, y / 6.0, seed) - 0.5)
             + 0.18 * (_vnoise(x / 1.8, y / 1.8, seed + 7) - 0.5))
        for mx, my, mh, mr in mounds:
            z += mh * math.exp(-((x - mx) ** 2 + (y - my) ** 2) / (mr * mr))
        return z

    md = _MD()
    ct = md.add((0.0, 0.0, top(0.0, 0.0)))
    radii = [re * (k / float(K)) ** 0.9 for k in range(1, K)] + [re - 0.25, re]
    rings = []
    for rr in radii:
        ring = []
        for j in range(S):
            a = TWO_PI * j / S
            x, y = rr * math.cos(a), rr * math.sin(a)
            ring.append(md.add((x, y, top(x, y))))
        rings.append(ring)
    edge = rings[-1]
    side = [md.add((md.v[i][0], md.v[i][1], md.v[i][2] - 0.3)) for i in edge]   # tight edge under TurboSmooth
    bot = [md.add((rbot * math.cos(TWO_PI * j / S), rbot * math.sin(TWO_PI * j / S), zt - depth))
           for j in range(S)]
    cb = md.add((0.0, 0.0, zt - depth))
    for j in range(S):
        j2 = (j + 1) % S
        md.face((ct, rings[0][j], rings[0][j2]))
        for k in range(len(rings) - 1):
            md.face((rings[k][j], rings[k + 1][j], rings[k + 1][j2], rings[k][j2]))
        md.face((edge[j], side[j], side[j2], edge[j2]))
        md.face((side[j], bot[j], bot[j2], side[j2]))
        md.face((cb, bot[j2], bot[j]))
    return md


# ============================================================ banana plant
def banana_plant_geometry(seed=0, pot=(45.0, 50.0), uv_xf=None):
    """Pure-Python Strelitzia nicolai for a planter of size `pot`: three fans
    of leaves (the main one roughly facing the front, -Y) rising from
    sheaths at the soil, oldest outside: older leaves lean further out, face
    more upwards and droop more, younger ones stand upright with sideways
    faces on longer petioles. Each leaf picks, of five draws of its lean and
    roll, the one that keeps its blade furthest from the leaves already
    placed. All petiole lengths are then scaled together so the top of the
    tallest visible blade lands on a target height of 174-186 cm.

    Returns a dict: leaf_cards (one _MD per card, with its UVs), leaves (the
    cards merged), stems (_MD petioles + midribs + the rolled new leaf, all
    closed), specs (one dict per leaf), probes (points on the visible
    blades), height / radius (visible extent above the floor / from the pot
    axis), soil_z, mounds (soil heaped at the fan bases), n_leaves, ..."""
    rng = random.Random(1009 + 7919 * int(seed or 0))

    def uni(a, b):
        return a + (b - a) * rng.random()

    def sign():
        return 1.0 if rng.random() < 0.5 else -1.0

    dims = planter_dims(*pot)
    soil_z = dims["soil_z"]
    z0 = soil_z - 2.4                               # petioles start buried in the soil slab
    target = uni(174.0, 186.0)
    n = 11 + int(rng.random() * 3)                  # 11-13 leaves
    s1 = int(round(n * 0.42))
    s2 = int(round((n - s1) * 0.55))
    sizes = (s1, s2, n - s1 - s2)
    az0 = uni(-0.35, 0.35)
    pos_az = uni(0.0, TWO_PI)
    r_lim = max(2.0, _r_in(dims, soil_z) - 7.0)
    fans = []
    for f in range(3):
        if f == 0:
            rb, pa, az = uni(0.5, 2.5), uni(0.0, TWO_PI), az0
        else:
            rb = min(r_lim, uni(5.5, 8.5))
            pa = pos_az + (f - 1) * math.pi + uni(-0.5, 0.5)
            az = az0 + (1.0 if f == 1 else -1.0) * uni(0.8, 1.3)
        fans.append(((rb * math.cos(pa), rb * math.sin(pa), z0),
                     (math.cos(az), math.sin(az), 0.0), (-math.sin(az), math.cos(az), 0.0)))

    leaves, clouds = [], []
    for f, size in enumerate(sizes):
        B, hf, nf = fans[f]
        for j in range(size):
            a = 1.0 - j / float(size - 1) if size > 1 else 0.5      # age: 1 = oldest, outermost
            side = 1.0 if j % 2 == 0 else -1.0                       # distichous: alternate sides
            alpha = math.radians(max(4.0, 7.0 + 17.0 * a + uni(-3.0, 3.0)))
            Lp = (78.0 - 22.0 * a) * uni(0.92, 1.08)
            BL = min(89.0, max(61.0, 66.0 + 17.0 * a + uni(-5.0, 5.0)))
            BW = BL * uni(max(0.29, 20.5 / BL), min(0.36, 29.5 / BL))    # 20.5-29.5, never clamped
            beta = math.radians(min(85.0, max(0.0, 12.0 + 56.0 * a + uni(-10.0, 10.0))))
            droop = math.radians(max(8.0, 18.0 + 46.0 * a + uni(-7.0, 7.0)))
            twist = math.radians(uni(6.0, 22.0)) * sign()
            fold = uni(0.12, 0.26) * 0.5 * BW
            asym = uni(-0.25, 0.25)
            ripple = (uni(0.5, 1.2), uni(14.0, 24.0), uni(0.0, TWO_PI))
            q = uni(1.4, 2.0)
            face = sign()
            drift = uni(-0.14, 0.14)
            r_base, r_top = uni(1.3, 1.6), uni(0.9, 1.15)
            off_h, off_n = side * a * uni(0.8, 2.2), uni(-0.5, 0.5)    # older sheaths outside
            base = (B[0] + hf[0] * off_h + nf[0] * off_n, B[1] + hf[1] * off_h + nf[1] * off_n, z0)
            cands = [(uni(-0.22, 0.22), math.radians(uni(-14.0, 14.0))) for _ in range(5)]
            card = LeafCard(BL, BW, droop, twist, fold, asym, ripple, q)
            coarse = card.coarse()
            best = None
            for delta, roll in cands:
                lean = _rotz((hf[0] * side, hf[1] * side, 0.0), delta)
                Q, T = _petiole_unit(lean, alpha, drift)
                end = _add(base, _mul(Q[-1], Lp))
                axes = _blade_axes(T, nf, beta, face, roll)
                pts = [_xf(c, end, axes) for c in coarse]
                score = _min_d2(pts, clouds)
                if best is None or score > best[0]:
                    best = (score, Q, axes, pts)
            clouds.append(best[3])
            leaves.append({"fan": f, "age": a, "card": card, "base": base, "Lp": Lp, "Q": best[1],
                           "axes": best[2], "r_base": r_base, "r_top": r_top, "hf": hf})

    # the newest leaf, still rolled into a spike, beside the youngest of the main fan
    B0, hf0, nf0 = fans[0]
    young = [lf for lf in leaves if lf["fan"] == 0][-1]
    s_lean = _rotz(hf0, uni(0.0, TWO_PI))
    sQ, sT = _petiole_unit(s_lean, math.radians(uni(2.0, 6.0)), 0.0, 16, 0.6)
    s_Lp = 0.72 * young["Lp"]
    s_Lr = uni(36.0, 48.0)
    s_bend = math.radians(uni(3.0, 9.0))
    s_rmax = uni(1.15, 1.4)
    s_base = (B0[0] + nf0[0] * uni(-0.4, 0.4), B0[1] + nf0[1] * uni(-0.4, 0.4), z0)
    kax = _norm(_cross(sT, s_lean))
    m = 16
    roll_pts = [(0.0, 0.0, 0.0)]
    for k in range(m):
        d = _rot_axis(sT, kax, s_bend * (k + 0.5) / m)
        roll_pts.append(_add(roll_pts[-1], _mul(d, s_Lr / m)))

    # one petiole scale for all leaves: the tallest visible blade top on target
    items = []
    for lf in leaves:
        dz = max(_xf(pp, (0.0, 0.0, 0.0), lf["axes"])[2] for pp in lf["card"].probes())
        items.append((lf["base"][2], lf["Lp"] * lf["Q"][-1][2], dz))
    items.append((s_base[2], s_Lp * sQ[-1][2], roll_pts[-1][2]))
    p = min((target - bz - dz) / ez for bz, ez, dz in items if ez > 1e-6)
    p = min(1.6, max(0.6, p))

    stems, cards = _MD(), _MD()
    card_mds, probes, specs = [], [], []
    for lf in leaves:
        card, axes = lf["card"], lf["axes"]
        Lp = p * lf["Lp"]
        path = [_add(lf["base"], _mul(qq, Lp)) for qq in lf["Q"]]
        end = path[-1]
        mid = card.midrib(lf["r_top"])
        rings = _petiole_rings(len(path) - 1, lf["r_base"], lf["r_top"], 10)
        rings += [_ellipse(r, r, 10) for _pt, r in mid]
        stems.merge(_sweep_md(path + [_xf(pt, end, axes) for pt, _r in mid], rings, lf["hf"]))
        cmd = card.card_md(BANANA_US, BANANA_VS, uv_xf)      # uv_xf: another leaf photo (photo_fit)
        cmd.map(lambda v, end=end, axes=axes: _xf(v, end, axes))
        card_mds.append(cmd)
        cards.merge(cmd)
        pr = [_xf(pp, end, axes) for pp in card.probes()]
        probes.extend(pr)
        specs.append({"fan": lf["fan"], "age": lf["age"], "blade_len": card.blade_len, "blade_w": card.blade_w,
                      "card_len": card.L, "card_w": card.W, "droop_deg": math.degrees(card.droop),
                      "twist_deg": math.degrees(card.twist), "fold": card.fold, "petiole_len": Lp,
                      "petiole_r": (lf["r_base"], lf["r_top"]), "petiole": path, "attach": end,
                      "stub": _xf(card.point(0.5, 0.0), end, axes), "top": max(pt[2] for pt in pr)})

    s_path = [_add(s_base, _mul(qq, p * s_Lp)) for qq in sQ]
    s_end = s_path[-1]
    s_path += [_add(s_end, rp) for rp in roll_pts[1:]]
    s_rings = [_ellipse(r, r, 12) for r in (0.95 - 0.17 * i / 16.0 for i in range(17))]
    for k in range(1, m + 1):
        s = s_Lr * k / m
        r = (0.78 + (s_rmax - 0.78) * _smooth(s / 6.0)) * max(0.0, 1.0 - (s / s_Lr) ** 1.8) ** 0.7 + 0.05
        ring = []
        for i in range(12):                       # the rolled blade's edge spirals up the spike
            g = (i / 12.0 + 1.6 * s / s_Lr) % 1.0
            rr = r * (1.0 - 0.1 * g)
            ring.append((rr * math.cos(TWO_PI * i / 12.0), rr * math.sin(TWO_PI * i / 12.0)))
        s_rings.append(ring)
    stems.merge(_sweep_md(s_path, s_rings, hf0))
    probes.append(s_path[-1])

    mounds = [(B[0], B[1], 1.1, 7.0) for B, _hf, _nf in fans]
    return {"leaves": cards, "leaf_cards": card_mds, "stems": stems, "specs": specs, "probes": probes,
            "height": max(pt[2] for pt in probes),
            "radius": max(math.hypot(pt[0], pt[1]) for pt in probes),
            "soil_z": soil_z, "mounds": mounds, "pot": tuple(pot), "petiole_scale": p, "target": target,
            "n_leaves": len(specs), "spike": s_path}


# ============================================================= bushy plant
def _stem_path(start, length, lean0, lean1, az, wob, n):
    """Stem polyline: leaning lean0 -> lean1 off vertical towards azimuth az,
    wandering sideways by a small sine (wob = amplitude, cycles, phase)."""
    amp, freq, ph = wob
    side = (-math.sin(az), math.cos(az), 0.0)
    pts = [start]
    for k in range(n):
        t = (k + 0.5) / n
        lean = lean0 + (lean1 - lean0) * t
        d = (math.sin(lean) * math.cos(az), math.sin(lean) * math.sin(az), math.cos(lean))
        d = _norm(_add(d, _mul(side, amp * math.sin(TWO_PI * freq * t + ph))))
        pts.append(_add(pts[-1], _mul(d, length / n)))
    return pts


def _path_at(path, s):
    f = max(0.0, min(1.0, s)) * (len(path) - 1)
    i = min(int(f), len(path) - 2)
    t = f - i
    a, b = path[i], path[i + 1]
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def _path_tan(path, s):
    f = max(0.0, min(1.0, s)) * (len(path) - 1)
    i = min(int(f), len(path) - 2)
    return _norm(_sub(path[i + 1], path[i]))


def _perp_frame(t):
    ref = (1.0, 0.0, 0.0) if abs(t[0]) < 0.9 else (0.0, 1.0, 0.0)
    e1 = _norm(_sub(ref, _mul(t, _dot(ref, t))))
    return e1, _cross(t, e1)


def _qbez(a, b, c, t):
    u = 1.0 - t
    return tuple(u * u * a[i] + 2.0 * u * t * b[i] + t * t * c[i] for i in range(3))


def _pot_clearance(pts, dims, margin=1.0):
    """Height (cm) above the rim of the lowest point over the pot mouth
    (within `margin` of the rim radius); +inf when none is over it."""
    worst = float("inf")
    lim = dims["R"] + margin
    for p in pts:
        if p[0] * p[0] + p[1] * p[1] < lim * lim:
            worst = min(worst, p[2] - dims["H"])
    return worst


def bushy_plant_geometry(seed=0, pot=(32.0, 34.0), uv_xf=None):
    """Pure-Python bushy plant for a planter of size `pot`: 3-4 main stems
    leaning out of the soil (the tallest sized from the target height), each
    with 1-3 side branches that turn up towards their tips; 26-37 leaves
    shared out by leafy length from a hand above the rim to the tips, set in
    a golden-angle spiral (turned a little outwards) on short petioles: low
    leaves large, spread flat and drooping over the rim, high ones smaller
    and more upright, a young upright leaf closing every branch tip. Each
    leaf keeps the best of three draws of its spiral angle and roll (most
    room to the leaves already placed, never down into the pot). The stem
    skeleton is then scaled (leaves and radii kept) so the tallest visible
    leaf tip lands on a target height of 86-104 cm above the floor.

    uv_xf: see LeafCard.card_md (another leaf photo on the cards).

    Returns a dict like banana_plant_geometry plus n_main / n_branches."""
    rng = random.Random(2003 + 7919 * int(seed or 0))

    def uni(a, b):
        return a + (b - a) * rng.random()

    def sign():
        return 1.0 if rng.random() < 0.5 else -1.0

    dims = planter_dims(*pot)
    soil_z = dims["soil_z"]
    z0 = soil_z - 2.0
    target = uni(86.0, 104.0)
    n_leaves = 48 + int(rng.random() * 17)          # 48-64 leaves: a dense bush, not bare stalks
    n_main = 3 + (1 if rng.random() < 0.5 else 0)
    L_ref = (target - z0 - 12.0) / 0.97             # tallest stem: its tip leaf ends on target
    psi0 = uni(0.0, TWO_PI)
    tall = int(rng.random() * n_main)
    n_side = [1 + int(rng.random() * 2.6) for _ in range(n_main)]
    while sum(n_side) > max(0, n_leaves // 3 - n_main) and max(n_side) > 0:   # >= ~3 leaves a branch
        n_side[n_side.index(max(n_side))] -= 1
    branches = []
    for mi in range(n_main):
        az = psi0 + TWO_PI * mi / n_main + uni(-0.35, 0.35)
        rb = uni(0.6, 3.0)
        B = (rb * math.cos(az), rb * math.sin(az), z0)
        lean = math.radians(uni(7.0, 20.0))
        L = L_ref * (1.0 if mi == tall else uni(0.72, 0.94))
        laz = az + uni(-0.3, 0.3)
        path = _stem_path(B, L, 0.5 * lean, 1.3 * lean, laz, (uni(0.03, 0.09), uni(1.5, 2.8), uni(0.0, TWO_PI)), 20)
        r0, r1 = uni(0.7, 0.88), uni(0.24, 0.3)
        branches.append({"main": mi, "base": B, "path": path, "r0": r0, "r1": r1, "start": uni(0.08, 0.12),
                         "sides": 7})
        sig = sorted(uni(0.22, 0.62) for _ in range(n_side[mi]))
        sgn = sign()
        for sb in sig:
            P = _path_at(path, sb)
            baz = laz + sgn * uni(0.9, 1.9)
            sgn = -sgn
            blean = math.radians(uni(34.0, 55.0))
            bpath = _stem_path(P, L_ref * uni(0.26, 0.44), blean, 0.4 * blean, baz,
                               (uni(0.02, 0.06), uni(1.5, 2.5), uni(0.0, TWO_PI)), 10)
            rp = r0 + (r1 - r0) * sb ** 0.8
            branches.append({"main": mi, "base": B, "path": bpath, "r0": min(0.5, 0.62 * rp),
                             "r1": uni(0.13, 0.17), "start": 0.1, "sides": 6})

    # share the leaves out by leafy length (at least two per branch: one on the tip)
    spans = []
    for br in branches:
        pth = br["path"]
        ln = sum(math.sqrt(_dot(_sub(pth[i + 1], pth[i]), _sub(pth[i + 1], pth[i]))) for i in range(len(pth) - 1))
        spans.append((1.0 - br["start"]) * ln)
    rest = n_leaves - 2 * len(branches)
    quota = [rest * s / sum(spans) for s in spans]
    counts = [2 + int(qq) for qq in quota]
    order = sorted(range(len(branches)), key=lambda i: -(quota[i] - int(quota[i])))
    for i in order[:n_leaves - sum(counts)]:
        counts[i] += 1

    golden = math.radians(137.5)
    leaves, clouds = [], []
    for bi, br in enumerate(branches):
        path, st, nb_ = br["path"], br["start"], counts[bi]
        phi = uni(0.0, TWO_PI)
        for k in range(nb_):
            terminal = k == nb_ - 1
            if terminal:
                sg = 1.0
            else:                                    # closer together towards the tip
                x = (k + 0.5 + uni(-0.25, 0.25)) / (nb_ - 1.0)
                sg = st + (1.0 - st) * 0.92 * x ** 0.85
            rel = (sg - st) / (1.0 - st)
            phi += golden + math.radians(uni(-12.0, 12.0))
            if terminal:                             # young leaf closing the tip: small, upright
                BL = uni(12.4, 15.0)
                ang, extra = math.radians(uni(10.0, 20.0)), math.radians(uni(3.0, 8.0))
                lp, droop, zmin = uni(0.8, 1.4), math.radians(uni(4.0, 14.0)), 0.5
            else:                                    # low leaves larger, flatter, drooping more
                BL = min(24.8, max(12.2, (23.8 - 10.0 * rel ** 0.9) * uni(0.9, 1.04)))
                ang = math.radians(66.0 - 30.0 * rel + uni(-8.0, 8.0))
                extra = math.radians(uni(6.0, 20.0))
                lp = uni(1.6, 3.2)
                droop = math.radians(50.0 - 30.0 * rel + uni(-8.0, 8.0))
                zmin = 0.3 * rel
            BW = BL * uni(0.36, 0.46)
            twist = math.radians(uni(4.0, 18.0)) * sign()
            fold = uni(0.06, 0.16) * 0.5 * BW
            asym = uni(-0.25, 0.25)
            ripple = (uni(0.06, 0.18), uni(5.0, 9.0), uni(0.0, TWO_PI))
            q = uni(1.3, 2.0)
            cands = [(math.radians(uni(-25.0, 25.0)), math.radians(uni(-25.0, 25.0))) for _ in range(3)]
            card = LeafCard(BL, BW, droop, twist, fold, asym, ripple, q)
            coarse, local = card.coarse(), card.probes()
            S = _path_at(path, sg)
            ts = _path_tan(path, sg)
            e1, e2 = _perp_frame(ts)
            ho = math.hypot(S[0], S[1])

            def place(dphi, roll, lift, S=S, ts=ts, e1=e1, e2=e2, ho=ho, phi=phi, ang=ang, extra=extra, lp=lp,
                      coarse=coarse, local=local):
                radial = _add(_mul(e1, math.cos(phi + dphi)), _mul(e2, math.sin(phi + dphi)))
                out = (S[0] / ho, S[1] / ho, 0.0) if ho > 1e-3 else radial
                dr = _add(radial, _mul(out, 0.7))                     # turned a little outwards
                dr = _norm(_sub(dr, _mul(ts, _dot(dr, ts))))
                dp = _norm(_add(_mul(ts, math.cos(ang)), _mul(dr, math.sin(ang))))
                T0 = _norm(_add(_mul(ts, math.cos(ang + extra)), _mul(dr, math.sin(ang + extra))))
                for _ in range(12):                                   # blades reach out or up, not down
                    if T0[2] >= lift:
                        break
                    T0 = _norm(_add(T0, (0.0, 0.0, 0.15)))
                a_off = _add(_mul(dp, 0.5 * lp), _mul(T0, 0.5 * lp))
                axes = _up_axes(T0, roll)
                A = _add(S, a_off)
                pts = [_xf(c, A, axes) for c in coarse]
                clear = _pot_clearance([_xf(c, A, axes) for c in local], dims)
                score = _min_d2(pts, clouds) if clear >= 2.0 else -1e6 + clear
                return (score, dp, a_off, axes, pts, clear, dphi, roll)

            best = None
            for dphi, roll in cands:
                cand = place(dphi, roll, zmin)
                if best is None or cand[0] > best[0]:
                    best = cand
            lift = zmin
            while best[5] < 2.0 and lift < 0.9:                      # still dipping into the pot
                lift += 0.1
                best = place(best[6], best[7], lift)
            clouds.append(best[4])
            leaves.append({"branch": bi, "base": br["base"], "S": S, "dp": best[1], "a_off": best[2],
                           "axes": best[3], "card": card, "lp": lp, "terminal": terminal})

    # one skeleton scale (about each main stem's base): tallest leaf tip on target
    items = []
    for lf in leaves:
        h = lf["S"][2] - lf["base"][2]
        c = lf["a_off"][2] + max(_xf(pp, (0.0, 0.0, 0.0), lf["axes"])[2] for pp in lf["card"].probes())
        items.append((lf["base"][2], h, c))
    ks = min((target - bz - c) / h for bz, h, c in items if h > 1e-6)
    ks = min(1.8, max(0.6, ks))

    def scaled(P, B):
        return (B[0] + ks * (P[0] - B[0]), B[1] + ks * (P[1] - B[1]), B[2] + ks * (P[2] - B[2]))

    stems, cards = _MD(), _MD()
    card_mds, probes, specs = [], [], []
    for br in branches:
        path = [scaled(P, br["base"]) for P in br["path"]]
        nn = len(path)
        radii = [br["r0"] + (br["r1"] - br["r0"]) * (i / (nn - 1.0)) ** 0.8 for i in range(nn)]
        stems.merge(_tube_md(path, radii, br["sides"]))
        probes.append(path[-1])
    for lf in leaves:
        card, axes = lf["card"], lf["axes"]
        S = scaled(lf["S"], lf["base"])
        A = _add(S, lf["a_off"])
        P1 = _add(S, _mul(lf["dp"], 0.5 * lf["lp"]))
        # a 3-4 mm petiole bending from the stem onto the blade's own direction:
        # its last segment runs along the midrib, so the photo's stalk stub sits inside it
        ppath = [_qbez(S, P1, A, t) for t in (0.0, 0.3, 0.6, 0.85, 1.0)]
        stems.merge(_tube_md(ppath, [0.2, 0.185, 0.172, 0.165, 0.16], 6))
        cmd = card.card_md(BUSH_US, BUSH_VS, uv_xf)
        cmd.map(lambda v, A=A, axes=axes: _xf(v, A, axes))
        card_mds.append(cmd)
        cards.merge(cmd)
        pr = [_xf(pp, A, axes) for pp in card.probes()]
        probes.extend(pr)
        specs.append({"branch": lf["branch"], "terminal": lf["terminal"], "blade_len": card.blade_len,
                      "blade_w": card.blade_w, "card_len": card.L, "card_w": card.W,
                      "droop_deg": math.degrees(card.droop), "twist_deg": math.degrees(card.twist),
                      "fold": card.fold, "petiole": ppath, "petiole_r": (0.2, 0.16), "attach": A,
                      "stub": _xf(card.point(0.5, 0.0), A, axes), "top": max(pt[2] for pt in pr)})

    mounds = [(br["base"][0], br["base"][1], 0.7, 4.5) for br in branches if br["sides"] == 7]
    return {"leaves": cards, "leaf_cards": card_mds, "stems": stems, "specs": specs, "probes": probes,
            "height": max(pt[2] for pt in probes),
            "radius": max(math.hypot(pt[0], pt[1]) for pt in probes),
            "soil_z": soil_z, "mounds": mounds, "pot": tuple(pot), "stem_scale": ks, "target": target,
            "n_leaves": len(specs), "n_main": n_main, "n_branches": len(branches)}


# ========================================================= Max-facing wrappers
def _leaf_nodes(mds, name):
    """One node per leaf card (a 20-50 KB mesh literal each, where one merged
    node made a 650 KB MAXScript string), keeping its own 0-1 UVs (no box
    mapping) and no TurboSmooth, which would shrink the card's UV border."""
    return [kit.part(_build(md, name, 1.0), "leaf_card", None, None) for md in mds]


def _planter_nodes(diameter, height, prefix, mounds=(), seed=0):
    return [_hard(planter_md(diameter, height), prefix + "_Pot", "pot_matte", POT_TILE),
            _hard(soil_md(diameter, height, mounds, seed), prefix + "_Soil", "soil", SOIL_TILE)]


def build_planter(diameter=45.0, height=50.0, seed=0):
    """Matte white stoneware planter with its soil (see planter_profile);
    seed varies the soil surface."""
    return kit.group("Planter", _planter_nodes(float(diameter), float(height), "Planter", (), int(seed or 0)))


def build_banana_plant(seed=0, pot=(45.0, 50.0), with_pot=True, uv_xf=None):
    """Bird of paradise, 174-186 cm, in its 45 x 50 planter (see
    banana_plant_geometry). The visible leaves spread 125-160 cm across; the
    cut-out card margins reach 10-20 cm beyond them."""
    g = banana_plant_geometry(seed, pot, uv_xf)
    nodes = _planter_nodes(pot[0], pot[1], "BananaPlant", g["mounds"], int(seed or 0)) if with_pot else []
    nodes.append(_hard(g["stems"], "BananaPlant_Petioles", "stem", STEM_TILE))
    nodes.extend(_leaf_nodes(g["leaf_cards"], "BananaPlant_Leaf"))
    return kit.group("BananaPlant", nodes)


def build_bushy_plant(seed=0, pot=(32.0, 34.0), with_pot=True, uv_xf=None):
    """Bushy plant, 86-104 cm, in its 32 x 34 planter (see bushy_plant_geometry)."""
    g = bushy_plant_geometry(seed, pot, uv_xf)
    nodes = _planter_nodes(pot[0], pot[1], "BushyPlant", g["mounds"], int(seed or 0) + 1) if with_pot else []
    nodes.append(_hard(g["stems"], "BushyPlant_Stems", "stem", STEM_TILE))
    nodes.extend(_leaf_nodes(g["leaf_cards"], "BushyPlant_Leaf"))
    return kit.group("BushyPlant", nodes)


def preview():
    """Both plants and both empty planters side by side along X."""
    kit.place(build_banana_plant(0), -110.0, 0.0)
    kit.place(build_bushy_plant(0), 40.0, 0.0)
    kit.place(build_planter(45.0, 50.0), 140.0, 0.0)
    kit.place(build_planter(32.0, 34.0), 210.0, 0.0)
