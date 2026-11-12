"""Credenza, three abstract sculptures and a potted olive tree for the MatForge
benchmark-2 living room (moody contemporary: copper Venetian plaster, grey
microcement, polished white marble, taupe lacquer).

Every piece is built round its own origin (kit.py conventions): the centre of
its footprint on the floor, z = 0 at the floor, centimetres, Z up, FRONT
facing -Y; every visible node goes through kit.part(...) and the piece comes
back as kit.group(...).

  build_credenza(length=300, depth=45, height=55)
      low lacquered credenza (lacquer_taupe), length x 45 x 55: a 2.5 cm top
      with 2.5 mm round edges on a carcass, full-overlay handle-less
      push-to-open doors (round(length / 75): four at 300 cm; 19 mm thick,
      1 mm edges) parted by 3 mm shadow gaps and hung 3 mm under the top, all
      on a 5 cm black steel plinth (metal_black) set back 4 cm all round.
      Footprint length x depth; the top is at z = height.
  build_sculpture_arch()
      microcement arch 40 x 9.7 x 30: an inverted U of round section (9.7 cm
      thick at the feet, 8.7 over the crown), its legs rising straight off
      two flat feet with 7 mm rounded rims into an elliptical crown.
  build_sculpture_head()
      abstract head-and-shoulders, 45 tall, microcement: a broad wedge of
      shoulders (28 wide, 17.2 high, 14 deep at the foot and 11.5 at the top,
      its chest face leaning back, round shoulders), a tapered neck (8.8 ->
      7.2 cm) leaning 10 degrees forward, and an ovoid head (21 long, 14.8
      wide, 17.6 deep) tilted back 20 degrees and turned 16, its chin jutting
      forward of the neck. No features at all.
  build_sculpture_wire(seed=0)
      twisted wire figure, 50 tall: 12 black 2.8 mm wires spiralling 1.1-1.35
      turns round an invisible tapered core with a gentle S, splayed out
      onto a 13 x 1.6 cm black disc base and splaying out again at the top.
  build_olive_tree(seed=0)
      olive tree about 170 tall (its highest sprig on a 166-174 target),
      crown 114-126 across: a 45 x 40 microcement planter (1.6 cm wall, 2 cm
      floor, soil 3.5 cm under the rim) on a four-legged walnut stand (splayed
      legs cradling the pot, a cross of rails under it, the pot's base 20 cm
      off the floor), a fluted, S-bent trunk (6.8-7.6 cm at the foot, flared
      at the soil, 5.2-5.8 at the split) splitting into 3-4 leaning branches
      (one reaching further than the others) with secondary branches and twigs
      (stem), and 150-180 olive sprig cards (olive_card, 18-26 cm square)
      along the outer twigs. Footprint about 145 x 145 with the cards' cut-out
      margins; the stand's feet stand within 42 x 42.

olive_card cards carry the whole 0-1 photo. The olive_sprig maps are 2048 x
2048, so every card is square (the leaves keep their proportions). In that
photo the sprig's cut end sits at CARD_CUT = (u 0.511, v 0.086), its bare
twig runs up V to v 0.27 and the leaves fill u 0.19-0.85, v 0.27-0.91
(measured from the opacity map); each card hangs from that point, which is
put on a twig's centre line.

Pure generators (no Max): credenza_layout / credenza_parts, arch_parts,
head_parts, wire_parts, olive_tree_geometry / olive_tree_parts. A part is a
(name, material key, furn_living._MD, tile cm, TurboSmooth iterations) tuple;
tile None marks a card node that keeps its own 0-1 UVs (no box map, no
smoothing). They are tested off-Max (tests/test_bench2_decor_geom.py); the
build_* wrappers only turn the cages into nodes. DRESSING suggests where the
sculptures stand on the credenza; preview() lays the set out.
"""
import math
import random

import kit
import furn_living as fl
from furn_living import (_MD, _add, _bez, _cross, _dot, _fillet2d, _mul, _norm, _revolve_md, _rot_axis,
                         _smooth, _sub, _tube_md)

# Benchmark-2 keys: kit.MAT_KEYS predates them, so they are declared here at
# import (runtime only, kit.py is not edited), as bench_arch.py declares
# wall_paint. The scene maps them to MatForge materials.
kit.MAT_KEYS.setdefault("lacquer_taupe", "matte taupe lacquered joinery (benchmark 2 credenza)")
kit.MAT_KEYS.setdefault("microcement", "grey microcement: planters and stone-like sculptures")
kit.MAT_KEYS.setdefault("olive_card", "olive sprig cut-out cards, the whole photo on 0-1 UVs (foliage)")

TWO_PI = 2.0 * math.pi
LACQUER = 60.0      # cm per texture repeat (box mapping)
METAL = 25.0
MICRO = 80.0
SOIL = 30.0
STEM = 20.0
WALNUT = 60.0


# ================================================================== helpers
def _xf(p, o, axes):
    """Local point -> parent space, for a frame with origin o and axes (X, Y, Z)."""
    X, Y, Z = axes
    return (o[0] + X[0] * p[0] + Y[0] * p[1] + Z[0] * p[2],
            o[1] + X[1] * p[0] + Y[1] * p[1] + Z[1] * p[2],
            o[2] + X[2] * p[0] + Y[2] * p[1] + Z[2] * p[2])


def _rotx(p, a):
    c, s = math.cos(a), math.sin(a)
    return (p[0], p[1] * c - p[2] * s, p[1] * s + p[2] * c)


def _rotz(p, a):
    c, s = math.cos(a), math.sin(a)
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c, p[2])


def _perp_frame(t):
    ref = (1.0, 0.0, 0.0) if abs(t[0]) < 0.9 else (0.0, 1.0, 0.0)
    e1 = _norm(_sub(ref, _mul(t, _dot(ref, t))))
    return e1, _cross(t, e1)


def _dedupe(pts, eps=1e-6):
    """Closed 2-D polygon without repeated neighbours (fillets that meet)."""
    out = []
    for p in pts:
        if out and math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) < eps:
            continue
        out.append((float(p[0]), float(p[1])))
    if len(out) > 2 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) < eps:
        out.pop()
    return out


def _offset_poly(pts, d):
    """Closed counter-clockwise polygon offset inwards by d (mitred bisectors)."""
    n = len(pts)

    def inward(a, b):
        ln = math.hypot(b[0] - a[0], b[1] - a[1]) or 1.0
        return (-(b[1] - a[1]) / ln, (b[0] - a[0]) / ln)

    out = []
    for i in range(n):
        a, p, c = pts[i - 1], pts[i], pts[(i + 1) % n]
        n1, n2 = inward(a, p), inward(p, c)
        bx, by = n1[0] + n2[0], n1[1] + n2[1]
        bl = math.hypot(bx, by)
        bx, by = (bx / bl, by / bl) if bl > 1e-9 else n1
        k = d / max(0.35, bx * n1[0] + by * n1[1])
        out.append((p[0] + bx * k, p[1] + by * k))
    return out


def _inside2d(pt, poly):
    """Even-odd point-in-polygon test."""
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i - 1], poly[i]
        if (y0 > y) != (y1 > y):
            if x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
                inside = not inside
    return inside


def _stations(lo, hi, r, seg=2, support=0.03):
    """Grid stations along one axis of a rounded box: arc stations at both
    ends (r tan of equal angle steps up to 45 degrees, so the projected
    rounds are split evenly), and a support station `support` inside each
    round so the flats shade dead flat right up to it."""
    c0, c1 = lo + r, hi - r
    out = [lo]
    out += [c0 - r * math.tan(math.radians(45.0 * k / seg)) for k in range(seg - 1, 0, -1)]
    out.append(c0)
    if c1 - c0 > 4.0 * support:
        out += [c0 + support, c1 - support]
    if c1 - c0 > 1e-6:
        out.append(c1)
    out += [c1 + r * math.tan(math.radians(45.0 * k / seg)) for k in range(1, seg)]
    out.append(hi)
    return out


def _rbox_md(x0, x1, y0, y1, z0, z1, r, seg=2, support=0.03):
    """Closed quad box with every edge and corner rounded to radius r (2 * seg
    segments a quarter round, spherical corners): the surface of a station
    lattice projected onto the rounded box (each point outside the inner
    box is pulled to distance r from it). Faces point outwards."""
    x0, x1 = sorted((float(x0), float(x1)))
    y0, y1 = sorted((float(y0), float(y1)))
    z0, z1 = sorted((float(z0), float(z1)))
    r = max(1e-3, min(float(r), 0.49 * min(x1 - x0, y1 - y0, z1 - z0)))
    S = (_stations(x0, x1, r, seg, support), _stations(y0, y1, r, seg, support),
         _stations(z0, z1, r, seg, support))
    lo, hi = (x0 + r, y0 + r, z0 + r), (x1 - r, y1 - r, z1 - r)
    md = _MD()
    idx = {}

    def v(i, j, k):
        key = (i, j, k)
        got = idx.get(key)
        if got is None:
            p = (S[0][i], S[1][j], S[2][k])
            q = tuple(min(max(p[a], lo[a]), hi[a]) for a in range(3))
            d = _sub(p, q)
            ln = math.sqrt(_dot(d, d))
            if ln > 1e-12:
                p = _add(q, _mul(d, r / ln))
            got = idx[key] = md.add(p)
        return got

    nx, ny, nz = len(S[0]), len(S[1]), len(S[2])
    for j in range(ny - 1):
        for k in range(nz - 1):
            md.face((v(0, j, k), v(0, j, k + 1), v(0, j + 1, k + 1), v(0, j + 1, k)))           # -X
            i = nx - 1
            md.face((v(i, j, k), v(i, j + 1, k), v(i, j + 1, k + 1), v(i, j, k + 1)))           # +X
    for i in range(nx - 1):
        for k in range(nz - 1):
            md.face((v(i, 0, k), v(i + 1, 0, k), v(i + 1, 0, k + 1), v(i, 0, k + 1)))           # -Y
            j = ny - 1
            md.face((v(i, j, k), v(i, j, k + 1), v(i + 1, j, k + 1), v(i + 1, j, k)))           # +Y
    for i in range(nx - 1):
        for j in range(ny - 1):
            md.face((v(i, j, 0), v(i, j + 1, 0), v(i + 1, j + 1, 0), v(i + 1, j, 0)))           # -Z
            k = nz - 1
            md.face((v(i, j, k), v(i + 1, j, k), v(i + 1, j + 1, k), v(i, j + 1, k)))           # +Z
    return md


def _gnarl_md(path, radii, sides, mod=None, caps=True):
    """furn_living._tube_md (parallel-transport frames, same winding, capped)
    with the radius of ring i at frame angle a scaled by mod(i, a): fluted,
    twisting bark."""
    md = _MD()
    n = len(path)
    tang = [_norm(_sub(path[min(i + 1, n - 1)], path[max(i - 1, 0)])) for i in range(n)]
    ref = (0.0, 0.0, 1.0) if abs(tang[0][2]) < 0.9 else (1.0, 0.0, 0.0)
    q = _norm(_sub(ref, _mul(tang[0], _dot(ref, tang[0]))))
    for i in range(n):
        q = _norm(_sub(q, _mul(tang[i], _dot(q, tang[i]))))
        b = _cross(tang[i], q)
        for s in range(sides):
            a = TWO_PI * s / sides
            r = radii[i] * (mod(i, a) if mod else 1.0)
            ca, sa = math.cos(a), math.sin(a)
            md.add(tuple(path[i][k] + r * (ca * q[k] + sa * b[k]) for k in range(3)))
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


class _PointGrid(object):
    """Bucketed 3-D points: distance to the nearest one (card spacing)."""

    def __init__(self, cell=9.0):
        self.cell = float(cell)
        self.b = {}

    def _key(self, p):
        c = self.cell
        return (int(math.floor(p[0] / c)), int(math.floor(p[1] / c)), int(math.floor(p[2] / c)))

    def add(self, pts):
        for p in pts:
            self.b.setdefault(self._key(p), []).append(p)

    def nearest(self, p, cap):
        """Distance to the closest stored point, at most cap (<= cell)."""
        kx, ky, kz = self._key(p)
        best = cap * cap
        for i in (kx - 1, kx, kx + 1):
            for j in (ky - 1, ky, ky + 1):
                for k in (kz - 1, kz, kz + 1):
                    for q in self.b.get((i, j, k), ()):
                        d = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2
                        if d < best:
                            best = d
        return math.sqrt(best)


def _nodes(parts):
    """Max nodes for (name, mat, md, tile, smooth) parts; tile None: a card
    node keeping its own 0-1 UVs (no box map, no TurboSmooth)."""
    out = []
    for name, mat, md, tile, smooth in parts:
        if tile is None:
            out.append(kit.part(fl._build(md, name, 1.0), mat, None, None))
        else:
            out.append(fl._hard(md, name, mat, tile, smooth))
    return out


# ================================================================= credenza
def credenza_layout(length=300.0, depth=45.0, height=55.0, n_doors=None):
    """Key dimensions (cm) of the credenza: carcass between z0 (on the plinth)
    and z1 (under the top), the doors' x spans, gaps, thicknesses, radii."""
    L, D, H = float(length), float(depth), float(height)
    if L < 60.0 or D < 25.0 or H < 30.0:
        raise ValueError("credenza too small: %r x %r x %r" % (length, depth, height))
    lay = {"L": L, "D": D, "H": H, "plinth_h": 5.0, "plinth_set": 4.0, "top_t": 2.5, "door_t": 1.9,
           "gap": 0.3, "clear": 0.1, "r_top": 0.25, "r_door": 0.1, "r_body": 0.15, "r_plinth": 0.15}
    n = int(n_doors) if n_doors else max(2, int(round(L / 75.0)))
    A, g = 0.5 * L, lay["gap"]
    w = (L - (n - 1) * g) / n
    lay.update(n_doors=n, door_w=w, z0=lay["plinth_h"], z1=H - lay["top_t"],
               doors=[(-A + k * (w + g), -A + k * (w + g) + w) for k in range(n)])
    return lay


def credenza_parts(length=300.0, depth=45.0, height=55.0, n_doors=None):
    """[(name, mat, md, tile, smooth)] of the credenza (see build_credenza).
    The doors cover the carcass front edge to edge, their fronts flush with
    the top's; the 3 mm gaps open onto the carcass front 2 cm behind (a dark
    shadow line). The carcass stops 0.2 mm under the top and the plinth runs
    1 mm up into the carcass, so no two faces are coplanar."""
    lay = credenza_layout(length, depth, height, n_doors)
    A, B, H = 0.5 * lay["L"], 0.5 * lay["D"], lay["H"]
    z0, z1, t, g = lay["z0"], lay["z1"], lay["door_t"], lay["gap"]
    top = _rbox_md(-A, A, -B, B, z1, H, lay["r_top"])
    body = _rbox_md(-A, A, -B + t + lay["clear"], B, z0, z1 - 0.02, lay["r_body"])
    doors = _MD()
    for xa, xb in lay["doors"]:
        doors.merge(_rbox_md(xa, xb, -B, -B + t, z0, z1 - g, lay["r_door"]))
    s = lay["plinth_set"]
    plinth = _rbox_md(-A + s, A - s, -B + s, B - s, 0.0, z0 + 0.1, lay["r_plinth"])
    return [("Credenza_Top", "lacquer_taupe", top, LACQUER, 0),
            ("Credenza_Carcass", "lacquer_taupe", body, LACQUER, 0),
            ("Credenza_Doors", "lacquer_taupe", doors, LACQUER, 0),
            ("Credenza_Plinth", "metal_black", plinth, METAL, 0)]


# ============================================================ sculpture: arch
def arch_path(length=40.0, height=30.0, r=4.6, swell=0.05, fillet=0.7, n_arc=28, n_leg=5, n_fil=4):
    """(centre line, radii) of the arch in the XZ plane: two straight legs at
    x = +-a joined by a half ellipse (vertical tangents where they meet), the
    round section swelling to r (1 + swell) at the feet and slimming to
    r (1 - swell) over the crown. Each foot ends on z = 0 in a flat face
    whose rim is rounded over by `fillet` (rings along the leg axis)."""
    rf, rc = r * (1.0 + swell), r * (1.0 - swell)
    a = 0.5 * length - rf
    b = 0.89 * a
    zb = height - rc - b
    if zb < fillet + 1.0:
        raise ValueError("arch too flat for its section")
    main = [(-a, 0.0, fillet + (zb - fillet) * k / n_leg) for k in range(n_leg)]
    for k in range(n_arc + 1):
        ph = math.pi * (1.0 - k / float(n_arc))
        main.append((a * math.cos(ph), 0.0, zb + b * math.sin(ph)))
    main += [(a, 0.0, zb - (zb - fillet) * k / n_leg) for k in range(1, n_leg + 1)]
    cum = [0.0]
    for p, q in zip(main, main[1:]):
        cum.append(cum[-1] + math.dist(p, q))
    rad = [r * (1.0 + swell * math.cos(TWO_PI * c / cum[-1])) for c in cum]
    head, head_r, tail, tail_r = [], [], [], []
    for j in range(n_fil):
        th = 0.5 * math.pi * (n_fil - j) / n_fil                     # 90 deg (on the floor) .. small
        head.append((-a, 0.0, fillet * (1.0 - math.sin(th))))
        head_r.append(rf - fillet * (1.0 - math.cos(th)))
        th = 0.5 * math.pi * (j + 1) / n_fil
        tail.append((a, 0.0, fillet * (1.0 - math.sin(th))))
        tail_r.append(rf - fillet * (1.0 - math.cos(th)))
    return head + main + tail, head_r + rad + tail_r


def arch_parts(length=40.0, height=30.0, r=4.6):
    path, rad = arch_path(length, height, r)
    return [("SculptureArch", "microcement", _tube_md(path, rad, 20), MICRO, 1)]


# ============================================================ sculpture: head
SHOULDERS = [(-10.0, 0.0), (10.0, 0.0), (15.5, 12.0), (4.2, 17.2), (-4.2, 17.2), (-15.5, 12.0)]
SHOULDER_R = [1.8, 1.8, 5.0, 2.6, 2.6, 5.0]
SHOULDER_Y = (-7.5, 6.5)        # chest and back faces at the foot
SHOULDER_LEAN = (2.0, -0.5)     # how far they have come in at the top
SHOULDER_EDGE = 1.2             # chest / back edges rounded over
NECK = [(0.0, 0.0), (4.4, 0.0), (4.15, 4.5), (3.85, 9.5), (3.65, 13.5), (3.6, 16.0), (0.0, 16.0)]
NECK_R = [0.0, 0.6, 3.0, 4.0, 3.0, 0.6, 0.0]
NECK_BASE = (1.0, 12.0)         # (y, z) of the neck's foot, 5.2 cm down in the shoulders
NECK_LEAN = math.radians(10.0)  # its top forward (-Y)
HEAD_H, HEAD_R, HEAD_EGG, HEAD_SX = 21.0, 8.8, 0.14, 0.84
HEAD_TILT, HEAD_TURN = math.radians(20.0), math.radians(16.0)
HEAD_NECK_BACK = 1.8            # the neck meets the head this far behind its axis (the chin juts)
BUST_H = 45.0


def _prism_md(prof, y0, y1, r_end, n_end=3):
    """Closed solid: a convex counter-clockwise (x, z) profile run from y0 to
    y1 with both ends rounded over by r_end (quarter rounds of inward
    offsets), flat end faces fanned from their centroids."""
    st = []
    for k in range(n_end + 1):
        th = 0.5 * math.pi * k / n_end
        st.append((y0 + r_end * (1.0 - math.cos(th)), r_end * (1.0 - math.sin(th))))
    for k in range(n_end, -1, -1):
        th = 0.5 * math.pi * k / n_end
        st.append((y1 - r_end * (1.0 - math.cos(th)), r_end * (1.0 - math.sin(th))))
    md = _MD()
    rings = []
    for y, inset in st:
        poly = _offset_poly(prof, inset) if inset > 1e-9 else prof
        rings.append([md.add((x, y, z)) for (x, z) in poly])
    n = len(prof)
    for k in range(len(rings) - 1):
        ra, rb = rings[k], rings[k + 1]
        for i in range(n):
            i2 = (i + 1) % n
            md.face((ra[i], rb[i], rb[i2], ra[i2]))
    for ring, front in ((rings[0], True), (rings[-1], False)):
        pts = [md.v[i] for i in ring]
        c = md.add(tuple(sum(p[k] for p in pts) / len(pts) for k in range(3)))
        for i in range(n):
            i2 = (i + 1) % n
            md.face((c, ring[i], ring[i2]) if front else (c, ring[i2], ring[i]))
    return md


def shoulder_profile():
    """Front view (x, z) of the shoulder wedge, every corner rounded."""
    return _dedupe(_fillet2d(SHOULDERS, SHOULDER_R, closed=True, step=math.radians(15.0)))


def _shoulder_y(z):
    """(chest, back) y of the shoulder wedge at height z."""
    t = max(0.0, min(1.0, z / max(p[1] for p in SHOULDERS)))
    return SHOULDER_Y[0] + SHOULDER_LEAN[0] * t, SHOULDER_Y[1] + SHOULDER_LEAN[1] * t


def shoulders_md():
    y0, y1 = SHOULDER_Y
    md = _prism_md(shoulder_profile(), y0, y1, SHOULDER_EDGE)

    def lean(p):
        yf, yb = _shoulder_y(p[2])
        return (p[0], yf + (p[1] - y0) / (y1 - y0) * (yb - yf), p[2])
    return md.map(lean)


def shoulders_contain(p, margin=0.0):
    """True when p lies inside the shoulder wedge by more than margin (its
    flats; the rounded edges are ignored)."""
    yf, yb = _shoulder_y(p[2])
    prof = _offset_poly(shoulder_profile(), margin) if margin > 0.0 else shoulder_profile()
    return _inside2d((p[0], p[2]), prof) and yf + margin < p[1] < yb - margin


def _neck_xf(p):
    q = _rotx(p, NECK_LEAN)
    return (q[0], q[1] + NECK_BASE[0], q[2] + NECK_BASE[1])


def neck_md():
    return _revolve_md(_fillet2d(NECK, NECK_R, step=math.radians(15.0)), 32).map(_neck_xf)


def _egg_peak(k):
    u = (-1.0 + math.sqrt(1.0 + 8.0 * k * k)) / (4.0 * k) if k else 0.0
    return math.sqrt(1.0 - u * u) * (1.0 + k * u)


_EGG_NORM = _egg_peak(HEAD_EGG)


def _egg_r(h):
    """Radius of the head's egg at height h above its chin pole (widest,
    HEAD_R, a little above the middle: the crown end is the fuller one)."""
    u = 2.0 * h / HEAD_H - 1.0
    if abs(u) >= 1.0:
        return 0.0
    return HEAD_R * math.sqrt(1.0 - u * u) * (1.0 + HEAD_EGG * u) / _EGG_NORM


def _egg_profile(n=22):
    pts = [(_egg_r(0.5 * HEAD_H * (1.0 - math.cos(math.pi * i / n))), 0.5 * HEAD_H * (1.0 - math.cos(math.pi * i / n)))
           for i in range(n + 1)]
    pts[0], pts[-1] = (0.0, 0.0), (0.0, HEAD_H)
    return pts


def _head_rot(p):
    """Egg frame (z up from the chin pole) -> bust axes round the head's centre."""
    q = (p[0] * HEAD_SX, p[1], p[2] - 0.5 * HEAD_H)
    return _rotz(_rotx(q, -HEAD_TILT), HEAD_TURN)


def _head_centre():
    """Centre of the head: its crown on BUST_H, the neck's top in its
    mid-plane HEAD_NECK_BACK behind its axis (so the chin juts forward of
    the neck)."""
    ztop = max(_head_rot(p)[2] for p in _revolve_md(_egg_profile(), 32).v)
    nt = _neck_xf((0.0, 0.0, NECK[-1][1]))
    ez = _head_rot((0.0, 0.0, 0.5 * HEAD_H + 1.0))           # the head's axis (unit)
    ey = _head_rot((0.0, 1.0, 0.5 * HEAD_H))                 # its 'back' direction (unit)
    cz = BUST_H - ztop
    p = _sub(nt, _mul(ey, HEAD_NECK_BACK))                    # on the axis, level with the neck's top
    t = (p[2] - cz) / ez[2]
    return (p[0] - ez[0] * t, p[1] - ez[1] * t, cz)


HEAD_C = _head_centre()


def head_md():
    return _revolve_md(_egg_profile(), 32).map(lambda p: _add(_head_rot(p), HEAD_C))


def head_contains(p, margin=0.0):
    """True when p lies inside the head's egg by more than margin."""
    q = _rotx(_rotz(_sub(p, HEAD_C), -HEAD_TURN), HEAD_TILT)
    return math.hypot(q[0] / HEAD_SX, q[1]) < _egg_r(q[2] + 0.5 * HEAD_H) - margin


def head_parts():
    return [("SculptureHead_Shoulders", "microcement", shoulders_md(), MICRO, 1),
            ("SculptureHead_Neck", "microcement", neck_md(), MICRO, 1),
            ("SculptureHead_Head", "microcement", head_md(), MICRO, 1)]


# ============================================================ sculpture: wire
WIRE_H = 50.0
WIRE_R = 0.14                    # 2.8 mm wire
WIRE_DISC = (6.5, 1.6)           # base radius, thickness
WIRE_CORE = (7.5, 0.84)          # core from z 7.5 up to 0.84 of the height


def wire_core_r(t):
    """Radius of the invisible core at t (0 at its foot, 1 at its top):
    tapering 2.3 -> 0.9 cm with a gentle belly."""
    return (2.3 + (0.9 - 2.3) * t) * (1.0 + 0.2 * math.sin(math.pi * t))


def wire_paths(seed=0, n=12, height=WIRE_H):
    """Centre lines of the n wires: each starts 3.5 mm down in the disc at
    3.4-5.3 cm from the axis, sweeps in onto the core by z 7.5, spirals up it
    (the same turn for all, give or take 0.08, each wire at its own radius
    and wandering a little, so they cross), then splays out to 2.4-7.2 cm and
    ends at 0.93-1.0 of the height. The core sways in a gentle S."""
    rng = random.Random(3001 + 7919 * int(seed or 0))

    def uni(a, b):
        return a + (b - a) * rng.random()

    zb = WIRE_DISC[1] - 0.35
    zc0, zc1 = WIRE_CORE[0], WIRE_CORE[1] * height
    turns = uni(1.1, 1.35) * (1.0 if rng.random() < 0.5 else -1.0)
    sway_a, sway_r = uni(0.0, TWO_PI), uni(0.4, 1.0)
    paths = []
    for i in range(n):
        phi = TWO_PI * i / n + uni(-0.2, 0.2)
        m = uni(0.78, 1.22)
        trn = turns + uni(-0.08, 0.08)
        r_foot, d_foot = uni(3.4, 5.3), uni(-0.5, 0.5)
        z_end, r_top, d_top = height * uni(0.93, 1.0), uni(2.4, 7.2), uni(-0.7, 0.7)
        wa, wf, wp = uni(0.08, 0.25), uni(2.0, 4.0), uni(0.0, TWO_PI)
        zs = [zb + (zc0 - zb) * k / 8.0 for k in range(8)]
        zs += [zc0 + (zc1 - zc0) * k / 34.0 for k in range(34)]
        zs += [zc1 + (z_end - zc1) * k / 10.0 for k in range(11)]
        pts = []
        for z in zs:
            t = min(1.0, max(0.0, (z - zc0) / (zc1 - zc0)))
            r = wire_core_r(t) * m + wa * math.sin(TWO_PI * wf * t + wp)
            th = phi + TWO_PI * trn * t
            if z < zc0:
                w = 1.0 - _smooth((z - zb) / (zc0 - zb))
                r += (r_foot - r) * w ** 1.5
                th += d_foot * w
            elif z > zc1:
                tau = (z - zc1) / (z_end - zc1)
                r += (r_top - r) * tau ** 1.6
                th += d_top * tau + TWO_PI * trn * (z - zc1) / (zc1 - zc0)
            sway = sway_r * math.sin(math.pi * t)
            pts.append((r * math.cos(th) + sway * math.cos(sway_a), r * math.sin(th) + sway * math.sin(sway_a), z))
        paths.append(pts)
    return paths


def wire_parts(seed=0, n=12, height=WIRE_H):
    R, T = WIRE_DISC
    disc = _revolve_md(_fillet2d([(0.0, 0.0), (R, 0.0), (R, T), (0.0, T)], [0.0, 0.25, 0.45, 0.0],
                                 step=math.radians(15.0)), 48)
    wires = _MD()
    for path in wire_paths(seed, n, height):
        wires.merge(_tube_md(path, WIRE_R, 6))
    return [("SculptureWire_Base", "metal_black", disc, METAL, 1),
            ("SculptureWire_Wires", "metal_black", wires, METAL, 1)]


# ================================================================ olive tree
POT_D, POT_H = 45.0, 40.0
STAND_H = 20.0                   # the pot's base stands this high
CARD_CUT = (0.511, 0.086)        # the sprig's cut end in the olive_sprig photo (u, v)
# probes on the visible sprig: cut end, tip, the leaves' far left / right, middle
CARD_PROBES = ((0.511, 0.086), (0.53, 0.91), (0.19, 0.61), (0.846, 0.6), (0.51, 0.55))
CARD_US = (0.0, CARD_CUT[0], 1.0)
CARD_VS = (0.0, CARD_CUT[1], 0.3, 0.55, 0.78, 1.0)
CARDS_PER_NODE = 20


def olive_card_point(u, v, size, droop=0.0, fold=0.0, twist=0.0):
    """Card-local point of photo (u, v) on a size x size card: origin on the
    sprig's cut end CARD_CUT, +Y up the twig (V), +X = +U, +Z the photo's
    front (X x Y = Z: the photo reads unmirrored from +Z). The twig arcs
    towards -Z by `droop` radians over the card (constant curvature from the
    cut end), the card turns by up to `twist` radians about it towards the
    tip, and both halves rise to `fold` cm at the side edges (a V along the
    twig, flat over the bare stalk)."""
    x = (u - CARD_CUT[0]) * size
    s = (v - CARD_CUT[1]) * size
    S = (1.0 - CARD_CUT[1]) * size
    if s > 0.0 and abs(droop) > 1e-9:
        kap = droop / S
        th = -kap * s
        M = (0.0, math.sin(kap * s) / kap, (math.cos(kap * s) - 1.0) / kap)
    else:
        th = 0.0
        M = (0.0, s, 0.0)
    N = (0.0, -math.sin(th), math.cos(th))
    tau = twist * max(0.0, s) / S
    c, sn = math.cos(tau), math.sin(tau)
    X = (c, sn * N[1], sn * N[2])
    Nt = (-sn, c * N[1], c * N[2])
    h = fold * min(1.0, abs(x) / (0.5 * size)) ** 1.2 * _smooth((s + 0.02 * size) / (0.15 * size))
    return (M[0] + X[0] * x + Nt[0] * h, M[1] + X[1] * x + Nt[1] * h, M[2] + X[2] * x + Nt[2] * h)


def olive_card_md(size, droop=0.0, fold=0.0, twist=0.0):
    """One card in its own frame (see olive_card_point): a quad grid over
    CARD_US x CARD_VS, every corner carrying its photo (u, v) - the whole
    0-1 square. The grid line u = CARD_CUT[0] is the fold along the twig."""
    md = _MD()
    rows = [[md.add(olive_card_point(u, v, size, droop, fold, twist)) for u in CARD_US] for v in CARD_VS]
    for j in range(len(CARD_VS) - 1):
        for i in range(len(CARD_US) - 1):
            md.face((rows[j][i], rows[j][i + 1], rows[j + 1][i + 1], rows[j + 1][i]),
                    ((CARD_US[i], CARD_VS[j]), (CARD_US[i + 1], CARD_VS[j]),
                     (CARD_US[i + 1], CARD_VS[j + 1]), (CARD_US[i], CARD_VS[j + 1])))
    return md


def olive_pot_dims(diameter=POT_D, height=POT_H, base_z=STAND_H):
    R, H, z0 = 0.5 * float(diameter), float(height), float(base_z)
    return {"R": R, "H": H, "z0": z0, "wall": 1.6, "floor": 2.0, "r_in": R - 1.6, "top": z0 + H,
            "soil_z": z0 + H - 3.5}


def olive_pot_profile(diameter=POT_D, height=POT_H):
    """(r, z) section of the planter from its own base, counter-clockwise
    round the material: a recessed underside on a 2.3 cm foot ring, a
    straight 1.6 cm wall rounded 1 cm at the foot, a bullnosed rim, the inner
    wall and a 1.2 cm fillet into the 2 cm floor; extra stations on the
    straight walls keep them straight under TurboSmooth."""
    d = olive_pot_dims(diameter, height, 0.0)
    R, H, t, fz = d["R"], d["H"], d["wall"], d["floor"]
    pts = [(0.0, 0.4), (R - 3.0, 0.4), (R - 2.3, 0.0), (R, 0.0)]
    rad = [0.0, 0.2, 0.25, 1.0]
    nw = 4
    for k in range(1, nw):
        pts.append((R, H * k / nw))
        rad.append(0.0)
    pts += [(R, H), (R - t, H)]
    rad += [0.48 * t, 0.48 * t]
    for k in range(nw - 1, 0, -1):
        pts.append((R - t, fz + (H - fz) * k / nw))
        rad.append(0.0)
    pts += [(R - t, fz), (0.0, fz)]
    rad += [1.2, 0.0]
    return _fillet2d(pts, rad, step=math.radians(15.0))


def olive_pot_md(diameter=POT_D, height=POT_H, base_z=STAND_H):
    return _revolve_md(olive_pot_profile(diameter, height), 64, z=base_z)


def soil_md(r_edge, z_top, depth=3.0, mounds=(), seed=0, n_ang=60, n_rad=12):
    """Closed slab of potting soil whose rim (radius r_edge) runs into the pot
    wall: an irregular top (two octaves of clods) heaped by `mounds`
    [(x, y, height, radius)], a flat underside `depth` lower."""
    def top(x, y):
        z = z_top + 0.45 * (_fbm(x / 6.0, y / 6.0, seed) - 0.5) + 0.18 * (_vnoise(x / 1.8, y / 1.8, seed + 7) - 0.5)
        for mx, my, mh, mr in mounds:
            z += mh * math.exp(-((x - mx) ** 2 + (y - my) ** 2) / (mr * mr))
        return z

    md = _MD()
    ct = md.add((0.0, 0.0, top(0.0, 0.0)))
    radii = [r_edge * (k / float(n_rad)) ** 0.9 for k in range(1, n_rad)] + [r_edge - 0.25, r_edge]
    rings = []
    for rr in radii:
        ring = []
        for j in range(n_ang):
            a = TWO_PI * j / n_ang
            x, y = rr * math.cos(a), rr * math.sin(a)
            ring.append(md.add((x, y, top(x, y))))
        rings.append(ring)
    edge = rings[-1]
    side = [md.add((md.v[i][0], md.v[i][1], md.v[i][2] - 0.3)) for i in edge]
    bot = [md.add((r_edge * math.cos(TWO_PI * j / n_ang), r_edge * math.sin(TWO_PI * j / n_ang), z_top - depth))
           for j in range(n_ang)]
    cb = md.add((0.0, 0.0, z_top - depth))
    for j in range(n_ang):
        j2 = (j + 1) % n_ang
        md.face((ct, rings[0][j], rings[0][j2]))
        for k in range(len(rings) - 1):
            md.face((rings[k][j], rings[k + 1][j], rings[k + 1][j2], rings[k][j2]))
        md.face((edge[j], side[j], side[j2], edge[j2]))
        md.face((side[j], bot[j], bot[j2], side[j2]))
        md.face((cb, bot[j2], bot[j]))
    return md


STAND = {"cradle": 7.0, "splay_deg": 8.0, "leg_r": (1.1, 1.55), "rail": (2.2, 3.5), "clear": 0.25}


def stand_layout(pot_r=0.5 * POT_D, base_z=STAND_H):
    """Leg axes of the plant stand: four legs on the diagonals, splayed out
    splay_deg, their tops `cradle` cm above the pot's base and clear of its
    wall, the rails' top 0.2 mm under the pot."""
    tg = math.tan(math.radians(STAND["splay_deg"]))
    hl = base_z + STAND["cradle"]
    rc_top = pot_r + STAND["leg_r"][1] + STAND["clear"]
    return {"leg_h": hl, "tan": tg, "rc_top": rc_top, "rc_bot": rc_top + hl * tg,
            "rail_z": (base_z - 0.02 - STAND["rail"][1], base_z - 0.02)}


def stand_md(pot_r=0.5 * POT_D, base_z=STAND_H):
    """Walnut plant stand: four round tapered legs (2.2 cm feet, 3.1 cm at the
    domed tops) splayed out on the diagonals, horizontal feet flat on the
    floor (sheared, so every section stays level), and a halved cross of
    2.2 x 3.5 cm rails between opposite legs carrying the pot."""
    lay = stand_layout(pot_r, base_z)
    hl, tg, rcb = lay["leg_h"], lay["tan"], lay["rc_bot"]
    r_foot, r_top = STAND["leg_r"]
    prof = _fillet2d([(0.0, 0.0), (r_foot, 0.0), (r_top, hl - 1.5), (0.0, hl)], [0.0, 0.3, 1.4, 0.0],
                     step=math.radians(15.0))
    md = _MD()
    for k in range(4):
        a = math.radians(45.0 + 90.0 * k)
        ca, sa = math.cos(a), math.sin(a)
        leg = _revolve_md(prof, 20)
        leg.map(lambda p, ca=ca, sa=sa: (p[0] + (rcb - p[2] * tg) * ca, p[1] + (rcb - p[2] * tg) * sa, p[2]))
        md.merge(leg)
    w = STAND["rail"][0]
    z0, z1 = lay["rail_z"]
    half = rcb - 0.5 * (z0 + z1) * tg                  # the rails end on the leg axes
    for k in range(2):
        rail = _rbox_md(-half, half, -0.5 * w, 0.5 * w, z0, z1, 0.2)
        rail.map(lambda p, a=math.radians(45.0 + 90.0 * k): _rotz(p, a))
        md.merge(rail)
    return md


class _Branch(object):
    """A branch centre line with radii r0 (base) -> r1 (tip)."""

    def __init__(self, level, path, r0, r1, az, sides, root, expo=0.8):
        self.level, self.path, self.az, self.sides, self.root = level, list(path), az, sides, root
        self.r0, self.r1, self.expo = float(r0), float(r1), expo
        cum = [0.0]
        for a, b in zip(self.path, self.path[1:]):
            cum.append(cum[-1] + math.dist(a, b))
        self.cum = cum

    def length(self):
        return self.cum[-1]

    def radius_at(self, f):
        return self.r0 + (self.r1 - self.r0) * max(0.0, min(1.0, f)) ** self.expo

    def radii(self):
        return [self.radius_at(c / self.cum[-1]) for c in self.cum]

    def _locate(self, f):
        s = max(0.0, min(1.0, f)) * self.cum[-1]
        i = 0
        while i < len(self.cum) - 2 and self.cum[i + 1] < s:
            i += 1
        span = self.cum[i + 1] - self.cum[i]
        return i, ((s - self.cum[i]) / span if span > 1e-12 else 0.0)

    def at(self, f):
        i, t = self._locate(f)
        a, b = self.path[i], self.path[i + 1]
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)

    def tangent(self, f):
        i, _t = self._locate(f)
        return _norm(_sub(self.path[i + 1], self.path[i]))


def _bpath(start, length, az, lean0, lean1, wob, n):
    """Branch centre line from start in n equal steps, leaning lean0 -> lean1
    off vertical towards azimuth az (over 90 degrees: below the horizontal),
    wandering sideways by a sine (amplitude, cycles, phase)."""
    amp, freq, ph = wob
    side = (-math.sin(az), math.cos(az), 0.0)
    pts = [tuple(float(c) for c in start)]
    for k in range(n):
        t = (k + 0.5) / n
        lean = lean0 + (lean1 - lean0) * t
        d = (math.sin(lean) * math.cos(az), math.sin(lean) * math.sin(az), math.cos(lean))
        d = _norm(_add(d, _mul(side, amp * math.sin(TWO_PI * freq * t + ph))))
        pts.append(_add(pts[-1], _mul(d, length / n)))
    return pts


def _spread(n, a, b, rng, jitter=0.3):
    """n increasing fractions spread over [a, b], each jittered in its slot."""
    step = (b - a) / float(max(n, 1))
    return [a + step * (k + 0.5 + rng.uniform(-jitter, jitter)) for k in range(n)]


def _clamp_down(d, fallback, zmin=-0.55):
    """d, but pointing no further down than z = zmin (unit vectors)."""
    if d[2] >= zmin:
        return d
    h = math.hypot(d[0], d[1])
    hx, hy = (d[0] / h, d[1] / h) if h > 1e-6 else (fallback[0], fallback[1])
    hl = math.hypot(hx, hy) or 1.0
    c = math.sqrt(1.0 - zmin * zmin)
    return (hx / hl * c, hy / hl * c, zmin)


def _trunk(base, top, r_base, r_top, soil_z, rng, n=20):
    """Centre line, radii and fluting of the trunk from `base` (in the soil)
    to the split point `top`: a cubic S-bend leaving the soil and reaching
    the split upright, wandering up to 2.6 cm, flared 35 % where it leaves
    the soil, closed by a low dome 2.9 cm above the split; spiralling flutes,
    deeper near the roots."""
    h = top[2] - base[2]
    c1 = (base[0], base[1], base[2] + h / 3.0)
    c2 = (top[0], top[1], top[2] - h / 3.0)
    a1, a2 = rng.uniform(1.2, 2.6), rng.uniform(1.2, 2.6)
    f1, f2 = rng.uniform(1.0, 1.6), rng.uniform(0.7, 1.2)
    p1, p2 = rng.uniform(0.0, TWO_PI), rng.uniform(0.0, TWO_PI)
    path, radii = [], []
    for k in range(n + 1):
        t = k / float(n)
        p = _bez(base, c1, c2, top, t)
        env = math.sin(math.pi * t) ** 2
        p = (p[0] + env * a1 * math.sin(TWO_PI * f1 * t + p1), p[1] + env * a2 * math.sin(TWO_PI * f2 * t + p2), p[2])
        path.append(p)
        radii.append((r_base + (r_top - r_base) * t) * (1.0 + 0.35 * math.exp(-max(0.0, p[2] - soil_z) / 3.5)))
    for dz, f in ((1.3, 0.85), (2.3, 0.6), (2.9, 0.3)):
        path.append((top[0], top[1], top[2] + dz))
        radii.append(r_top * f)
    cum = [0.0]
    for a, b in zip(path, path[1:]):
        cum.append(cum[-1] + math.dist(a, b))
    q1, q2, q3 = rng.uniform(0.0, TWO_PI), rng.uniform(0.0, TWO_PI), rng.uniform(0.0, TWO_PI)

    def mod(i, a):
        g = 1.0 + 0.8 * math.exp(-max(0.0, path[i][2] - soil_z) / 6.0)
        s = cum[i]
        return (1.0 + g * (0.1 * math.sin(3.0 * a + 0.11 * s + q1) + 0.055 * math.sin(5.0 * a - 0.07 * s + q2))
                + 0.025 * math.sin(7.0 * a + 0.2 * s + q3))
    return path, radii, mod


def olive_tree_geometry(seed=0):
    """Pure-Python olive tree in its planter on the stand.

    The crown's skeleton is grown round the split point first: 3-4 main
    branches leaning 24-40 degrees out (turning up towards their tips,
    50-64 cm; one leads, 6 degrees lower and 15 % longer, so the crown is
    not a lollipop), 3-5 secondary branches on each (48-78 degrees, 13-36 cm) with
    2-4 twigs each (55-112 degrees: some droop) and 1-2 twigs off each main's
    end. 150-180 cards are shared out over the leafy outer parts (twigs from
    a quarter of their length, secondaries from 0.6, mains from 0.88), one
    on every tip continuing it, the rest leaving their twig at 30-62 degrees
    in a golden-angle spiral, pushed outwards, some hanging (never more than
    33 degrees below the horizontal), facing up and out within +-50 degrees;
    each keeps the best of three draws (most room to the cards already
    placed). The skeleton is then scaled about the split point (directions,
    radii and cards kept) so the crown is target_w (114-126 cm) across, and
    the split raised or lowered so the highest sprig reaches target_h
    (166-174 cm), the split staying 18-48 cm above the rim; the trunk leans
    to keep the crown over the pot.

    Returns a dict: trunk (_MD: trunk + mains, closed), twigs (one _MD per
    main: its secondaries and twigs, closed), cards (one _MD per card, own
    UVs), specs (per card: size, attach point, level, terminal, probes, ...),
    soil, branches (world centre lines [{level, path, radii, root}], the
    trunk first), probes (points on the visible sprigs), height, crown
    (x, y extents), crown_centre, scale, split, target_h, target_w, n_cards,
    n_main, pot (olive_pot_dims), trunk_base."""
    seed = int(seed or 0)
    rng = random.Random(5003 + 7919 * seed)

    def uni(a, b):
        return a + (b - a) * rng.random()

    def sign():
        return 1.0 if rng.random() < 0.5 else -1.0

    dims = olive_pot_dims()
    target_h = uni(166.0, 174.0)
    target_w = uni(114.0, 126.0)

    # ---- skeleton round the split point (0, 0, 0), unscaled
    n_main = 4 if rng.random() < 0.5 else 3
    az0 = uni(0.0, TWO_PI)
    lead = int(rng.random() * n_main)               # one branch reaches further out: no lollipop
    mains = []
    for k in range(n_main):
        az = az0 + TWO_PI * k / n_main + uni(-0.35, 0.35)
        lean = math.radians(uni(24.0, 40.0) + (6.0 if k == lead else 0.0))
        path = _bpath((0.0, 0.0, -3.0), uni(50.0, 64.0) * (1.15 if k == lead else 1.0), az, lean,
                      lean * uni(0.45, 0.7), (uni(0.04, 0.1), uni(1.2, 2.2), uni(0.0, TWO_PI)), 16)
        mains.append(_Branch(1, path, uni(2.0, 2.25), uni(0.45, 0.55), az, 12, k))
    branches = list(mains)

    def twig(parent, f, az, lmin, lmax, rmax):
        tl = math.radians(uni(55.0, 100.0))
        path = _bpath(parent.at(f), uni(lmin, lmax), az, tl, tl + math.radians(uni(-15.0, 12.0)),
                      (uni(0.02, 0.06), uni(0.8, 1.6), uni(0.0, TWO_PI)), 6)
        return _Branch(3, path, min(rmax, 0.7 * parent.radius_at(f)), 0.09, az, 5, parent.root)

    for m in mains:
        side = sign()
        for f in _spread(3 + int(rng.random() * 3), 0.3, 0.92, rng):
            az = m.az + side * uni(0.6, 1.6)
            side = -side
            lean = math.radians(uni(48.0, 78.0))
            path = _bpath(m.at(f), uni(20.0, 34.0) * (1.05 - 0.35 * f), az, lean, lean * uni(0.55, 0.85),
                          (uni(0.03, 0.08), uni(1.0, 2.0), uni(0.0, TWO_PI)), 10)
            sec = _Branch(2, path, min(0.75, 0.62 * m.radius_at(f)), 0.16, az, 7, m.root)
            branches.append(sec)
            tside = sign()
            for g in _spread(2 + int(rng.random() * 2.6), 0.3, 0.95, rng):
                branches.append(twig(sec, g, az + tside * uni(0.5, 1.3), 9.0, 17.0, 0.26))
                tside = -tside
        for g in _spread(1 + int(rng.random() * 1.8), 0.78, 0.96, rng):
            branches.append(twig(m, g, m.az + sign() * uni(0.6, 1.4), 10.0, 18.0, 0.3))

    # ---- cards: one on every leafy tip, the rest shared out by leafy length
    leafy = [(b, {1: 0.88, 2: 0.6, 3: 0.25}[b.level]) for b in branches]
    n_cards = int(uni(150.0, 181.0))
    spans = [(1.0 - f0) * b.length() for b, f0 in leafy]
    rest = n_cards - len(leafy)
    if rest < 0:
        raise ValueError("more leafy branches than cards")
    quota = [rest * s / sum(spans) for s in spans]
    counts = [1 + int(q) for q in quota]
    order = sorted(range(len(leafy)), key=lambda i: -(quota[i] - int(quota[i])))
    for i in order[:n_cards - sum(counts)]:
        counts[i] += 1
    golden = math.radians(137.5)
    grid = _PointGrid(9.0)
    cards = []
    for (b, f0), cnt in zip(leafy, counts):
        psi = uni(0.0, TWO_PI)
        fs = [1.0] + [f0 + (1.0 - f0) * 0.93 * (j + 0.5 + uni(-0.3, 0.3)) / (cnt - 1) for j in range(cnt - 1)]
        for j, f in enumerate(fs):
            terminal = j == 0
            size = uni(18.0, 26.0)
            droop, fold = math.radians(uni(6.0, 30.0)), uni(0.5, 1.8)
            twist = math.radians(uni(5.0, 22.0)) * sign()
            local = [olive_card_point(u, v, size, droop, fold, twist) for u, v in CARD_PROBES]
            A = b.at(f)
            t = b.tangent(f)
            e1, e2 = _perp_frame(t)
            hr = math.hypot(A[0], A[1])
            out = (A[0] / hr, A[1] / hr, 0.0) if hr > 1.0 else (math.cos(b.az), math.sin(b.az), 0.0)
            psi += golden + uni(-0.3, 0.3)
            best = None
            for _c in range(3):
                if terminal:
                    jit = _add(_mul(e1, uni(-0.2, 0.2)), _mul(e2, uni(-0.2, 0.2)))
                    d = _norm(_add(_add(t, jit), _mul(out, 0.15)))
                else:
                    ps = psi + uni(-0.6, 0.6)
                    gam = math.radians(uni(30.0, 62.0))
                    radial = _add(_mul(e1, math.cos(ps)), _mul(e2, math.sin(ps)))
                    d = _add(_mul(t, math.cos(gam)), _mul(radial, math.sin(gam)))
                    d = _norm(_add(_add(d, _mul(out, 0.35)), (0.0, 0.0, -uni(0.0, 0.45))))
                d = _clamp_down(d, out)
                up_p = _sub((0.0, 0.0, 1.0), _mul(d, d[2]))
                out_p = _sub(out, _mul(d, _dot(out, d)))
                pref = _add(_mul(up_p, 0.75), _mul(out_p, 0.45))
                pref = _norm(pref) if _dot(pref, pref) > 1e-8 else _perp_frame(d)[0]
                n = _norm(_rot_axis(pref, d, math.radians(uni(-50.0, 50.0))))
                axes = (_cross(d, n), d, n)
                pts = [_xf(p, A, axes) for p in local]
                score = min(grid.nearest(p, 9.0) for p in pts[1:])
                if best is None or score > best[0]:
                    best = (score, axes, pts)
            grid.add(best[2][1:])
            cards.append({"branch": b, "f": f, "A": A, "axes": best[1], "size": size, "droop": droop,
                          "fold": fold, "twist": twist, "local": local, "terminal": terminal})

    # ---- one skeleton scale about the split point: the crown's width on target
    offs = [(c["A"], [_xf(p, (0.0, 0.0, 0.0), c["axes"]) for p in c["local"]]) for c in cards]

    def extents(k):
        xs = [k * A[0] + o[0] for A, os in offs for o in os]
        ys = [k * A[1] + o[1] for A, os in offs for o in os]
        return min(xs), max(xs), min(ys), max(ys)

    def width(k):
        x0, x1, y0, y1 = extents(k)
        return 0.5 * ((x1 - x0) + (y1 - y0))

    lo, hi = 0.7, 1.45
    if width(lo) >= target_w:
        k = lo
    elif width(hi) <= target_w:
        k = hi
    else:
        for _ in range(28):
            mid = 0.5 * (lo + hi)
            if width(mid) < target_w:
                lo = mid
            else:
                hi = mid
        k = 0.5 * (lo + hi)
    x0, x1, y0, y1 = extents(k)
    top_rel = max(max(k * A[2] + o[2] for A, os in offs for o in os), max(k * b.path[-1][2] for b in branches))
    z_split = min(dims["top"] + 48.0, max(dims["top"] + 18.0, target_h - top_rel))
    lean_r, lean_a = uni(0.0, 2.5), uni(0.0, TWO_PI)
    px = -0.3 * (x0 + x1) + lean_r * math.cos(lean_a)       # lean the trunk to balance the crown
    py = -0.3 * (y0 + y1) + lean_r * math.sin(lean_a)
    pr = math.hypot(px, py)
    if pr > 6.0:
        px, py = px * 6.0 / pr, py * 6.0 / pr
    P0 = (px, py, z_split)

    def world(p):
        return (P0[0] + k * p[0], P0[1] + k * p[1], P0[2] + k * p[2])

    # ---- meshes
    br, ba = uni(0.0, 2.0), uni(0.0, TWO_PI)
    base = (br * math.cos(ba), br * math.sin(ba), dims["soil_z"] - 2.5)
    t_path, t_rad, t_mod = _trunk(base, P0, uni(3.4, 3.8), uni(2.6, 2.9), dims["soil_z"], rng)
    trunk = _gnarl_md(t_path, t_rad, 16, t_mod)
    wbranches = [{"level": 0, "path": t_path, "radii": t_rad, "root": -1}]
    for m in mains:
        ph1, ph2 = uni(0.0, TWO_PI), uni(0.0, TWO_PI)

        def mod(i, a, cum=m.cum, ph1=ph1, ph2=ph2):
            return 1.0 + 0.06 * math.sin(3.0 * a + 0.15 * cum[i] + ph1) + 0.035 * math.sin(2.0 * a - 0.1 * cum[i] + ph2)
        wp = [world(p) for p in m.path]
        trunk.merge(_gnarl_md(wp, m.radii(), m.sides, mod))
    twigs = [_MD() for _ in mains]
    for b in branches:
        wp = [world(p) for p in b.path]
        if b.level >= 2:
            twigs[b.root].merge(_tube_md(wp, b.radii(), b.sides))
        wbranches.append({"level": b.level, "path": wp, "radii": b.radii(), "root": b.root})
    card_mds, specs, probes = [], [], []
    for c in cards:
        A, axes = world(c["A"]), c["axes"]
        md = olive_card_md(c["size"], c["droop"], c["fold"], c["twist"])
        md.map(lambda p, A=A, axes=axes: _xf(p, A, axes))
        card_mds.append(md)
        pr_ = [_xf(p, A, axes) for p in c["local"]]
        probes.extend(pr_)
        specs.append({"size": c["size"], "attach": A, "level": c["branch"].level, "terminal": c["terminal"],
                      "droop_deg": math.degrees(c["droop"]), "twist_deg": math.degrees(c["twist"]),
                      "fold": c["fold"], "axes": axes, "probes": pr_})
    soil = soil_md(dims["r_in"] + 0.4, dims["soil_z"], 3.0, [(base[0], base[1], 1.3, 6.5)], seed)
    tips = [world(b.path[-1]) for b in branches]
    return {"trunk": trunk, "twigs": twigs, "cards": card_mds, "specs": specs, "soil": soil,
            "branches": wbranches, "probes": probes,
            "height": max(max(p[2] for p in probes), max(p[2] for p in tips)),
            "crown": (x1 - x0, y1 - y0), "crown_centre": (P0[0] + 0.5 * (x0 + x1), P0[1] + 0.5 * (y0 + y1)),
            "scale": k, "split": P0, "target_h": target_h, "target_w": target_w, "n_cards": len(cards),
            "n_main": n_main, "pot": dims, "trunk_base": base}


def olive_tree_parts(seed=0):
    """[(name, mat, md, tile, smooth)] of the potted olive tree (see
    build_olive_tree); the cards go in nodes of CARDS_PER_NODE (tile None:
    their own 0-1 UVs), the twigs in one node per main branch."""
    g = olive_tree_geometry(seed)
    parts = [("OliveTree_Stand", "wood_dark", stand_md(), WALNUT, 1),
             ("OliveTree_Pot", "microcement", olive_pot_md(), MICRO, 1),
             ("OliveTree_Soil", "soil", g["soil"], SOIL, 1),
             ("OliveTree_Trunk", "stem", g["trunk"], STEM, 1)]
    parts += [("OliveTree_Twigs", "stem", md, STEM, 1) for md in g["twigs"] if md.f]
    for i in range(0, len(g["cards"]), CARDS_PER_NODE):
        chunk = _MD()
        for md in g["cards"][i:i + CARDS_PER_NODE]:
            chunk.merge(md)
        parts.append(("OliveTree_Leaves", "olive_card", chunk, None, 0))
    return parts


# ========================================================= Max-facing wrappers
def build_credenza(length=300.0, depth=45.0, height=55.0):
    """Low taupe-lacquered credenza length x depth x height, handle-less
    push-to-open doors behind 3 mm shadow gaps, black plinth set back 4 cm;
    front -Y, top at z = height (see credenza_parts)."""
    return kit.group("Credenza", _nodes(credenza_parts(length, depth, height)))


def build_sculpture_arch():
    """Microcement arch 40 x 9.7 x 30 (see arch_path)."""
    return kit.group("SculptureArch", _nodes(arch_parts()))


def build_sculpture_head():
    """Abstract microcement head-and-shoulders, 45 tall, facing -Y."""
    return kit.group("SculptureHead", _nodes(head_parts()))


def build_sculpture_wire(seed=0):
    """Twisted black wire figure on a disc base, 50 tall (see wire_paths)."""
    return kit.group("SculptureWire", _nodes(wire_parts(seed)))


def build_olive_tree(seed=0):
    """Olive tree in a microcement planter on a walnut stand, about 170 tall
    with a crown about 120 across (see olive_tree_geometry)."""
    return kit.group("OliveTree", _nodes(olive_tree_parts(seed)))


# ================================================================= preview
# Suggested dressing of build_credenza() standing at the origin unrotated:
# (piece, x, y, z, rotation deg, kwargs) - the sculptures on its top (z = 55).
DRESSING = [
    ("sculpture_head", 52.0, 2.0, 55.0, -20.0, {}),
    ("sculpture_arch", 92.0, 2.5, 55.0, 8.0, {}),
    ("sculpture_wire", 128.0, 3.0, 55.0, 0.0, {"seed": 0}),
]
PIECES = {"credenza": credenza_parts, "sculpture_arch": arch_parts, "sculpture_head": head_parts,
          "sculpture_wire": wire_parts, "olive_tree": olive_tree_parts}
_BUILD = {"credenza": build_credenza, "sculpture_arch": build_sculpture_arch, "sculpture_head": build_sculpture_head,
          "sculpture_wire": build_sculpture_wire, "olive_tree": build_olive_tree}


def preview(x=0.0, y=0.0, rot=0.0):
    """The credenza dressed as DRESSING (one group placed at x, y, rot) and
    the olive tree to its left."""
    nodes = [build_credenza()]
    for key, px, py, pz, deg, kw in DRESSING:
        nodes.append(kit.place(_BUILD[key](**kw), px, py, pz, deg))
    group = kit.place(kit.group("Credenza_Dressed", nodes), x, y, 0.0, rot)
    kit.place(build_olive_tree(0), x - 230.0, y - 20.0, 0.0, rot)
    return group
