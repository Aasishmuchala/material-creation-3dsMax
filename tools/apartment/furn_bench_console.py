"""Slim black metal console and its dressing for the MatForge benchmark living room.

Every piece is built at its local origin (kit.py conventions): footprint
centred on X/Y, base on z = 0, centimetres, Z up, FRONT facing -Y; every
visible node is registered through kit.part(...) and returned as kit.group(...).

  build_console(L=150, D=35, H=85)
        black powder-coated steel console: 2 x 2 cm square-tube frame (3 mm
        corner radius) set 5 mm inside a 1 cm plate top, a 1 cm plate shelf
        welded between the legs (its top at 18 cm), flat-bar X braces with
        fillet welds on both short sides, round levelling glides.
        Footprint L x D (the top), height H.
  build_book_stack(seed=0)
        3-4 large hardbacks: cloth / leather / paper cases with rounded spines,
        hinge grooves and 3 mm squares round a page block with a hollow
        fore-edge, spines mostly to the front. About 35 x 27, 8-12 high.
  build_glass_jars()
        two clear glass storage jars (3.5 mm walls, punted base 7-9 mm thick,
        fire-polished rims) with plugged, knobbed glass lids; bodies 20.5 and
        12 cm tall (23 and 14.4 with lids), about 25 x 14 overall.
  build_glass_lamp(cord_to_edge=None, cord_drop=85.0)
        45 cm table lamp: solid clear glass block base (12 x 11) with the
        brass rod visible inside, thin brass stem and socket, clear globe
        bulb, 26 x 17 drum shade with rolled rims and a lapped seam at the
        back, brass spider. cord_to_edge (cm along +Y to the back edge of the
        surface it stands on) adds a black cord running back over the surface,
        down behind its edge by cord_drop (the surface height) and along the
        floor towards +X.
  build_twig_vase(seed=0, twig_mat="stem")
        matte stoneware bud vase (9 x 15) holding one bare, budded twig with
        three side shoots (about 48 cm overall, 13 x 14 in plan).

The geometry is made by pure-Python functions returning furn_living._MD
cages - console_parts, book_stack_parts, glass_jar_parts, glass_lamp_parts,
twig_vase_parts, each a list of (name, material key, _MD, tile cm, TurboSmooth
iterations) - so it is testable without 3ds Max
(tests/test_bench_console_geom.py); the build_* wrappers only turn the cages
into nodes.
"""
import math

import kit
from furn_living import (_MD, _hard, _fillet2d, _revolve_md, _tube_md, _slab, _Rand,
                         _sub, _mul, _dot, _cross, _norm)

METAL = 25.0        # cm per texture repeat: powder coat, brass
GLASS = 30.0
PAGES = 20.0
COVER_TILE = {"linen": 9.0, "leather": 25.0, "paper": 30.0}   # book cloth is a fine weave


# ================================================================== helpers
def _area2(pts):
    """Signed area of a closed 2-D polygon (> 0: counter-clockwise)."""
    a = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return 0.5 * a


def _offset2d(pts, d):
    """Closed (x, z) polygon offset inwards by d (mitred vertex bisectors)."""
    n = len(pts)
    s = 1.0 if _area2(pts) > 0.0 else -1.0

    def inward(a, b):
        ln = math.hypot(b[0] - a[0], b[1] - a[1]) or 1.0
        return (-s * (b[1] - a[1]) / ln, s * (b[0] - a[0]) / ln)
    out = []
    for i in range(n):
        a, p, c = pts[i - 1], pts[i], pts[(i + 1) % n]
        n1, n2 = inward(a, p), inward(p, c)
        bx, bz = n1[0] + n2[0], n1[1] + n2[1]
        bl = math.hypot(bx, bz)
        bx, bz = (bx / bl, bz / bl) if bl > 1e-9 else n1
        k = d / max(0.35, bx * n1[0] + bz * n1[1])
        out.append((p[0] + bx * k, p[1] + bz * k))
    return out


# rounded ends of a loft: (distance from the end, inset), in units of the radius
_ROUND_END = [(0.0, 1.0), (0.134, 0.5), (0.5, 0.134), (1.0, 0.0)]


def _loft_md(prof, y0, y1, caps, rad=0.1):
    """Extrude a closed (x, z) profile along +Y from y0 to y1 with both ends
    rounded over (the section shrinks inwards by up to rad over the last rad
    of length). caps: polygons (index tuples into prof) closing the ends,
    each fanned from its first index (which must see the whole polygon);
    sides and caps are wound outwards whatever order they come in."""
    st = [(y0 + rad * a, _offset2d(prof, rad * b) if b else prof) for a, b in _ROUND_END]
    st += [(y1 - rad * a, _offset2d(prof, rad * b) if b else prof) for a, b in reversed(_ROUND_END)]
    md = _MD()
    n = len(prof)
    rings = [[md.add((x, y, z)) for (x, z) in pr] for y, pr in st]
    ccw = _area2(prof) > 0.0
    for k in range(len(st) - 1):
        ra, rb = rings[k], rings[k + 1]
        for i in range(n):
            i2 = (i + 1) % n
            md.face((ra[i], rb[i], rb[i2], ra[i2]) if ccw else (ra[i], ra[i2], rb[i2], rb[i]))
    for poly in caps:
        for k, rev in ((0, False), (-1, True)):            # counter-clockwise in (x, z) faces -Y
            pr = st[k][1]
            p = list(poly) if _area2([pr[i] for i in poly]) > 0.0 else [poly[0]] + list(poly[:0:-1])
            md.face([rings[k][i] for i in ([p[0]] + p[:0:-1] if rev else p)])    # keeps the fan apex
    return md


def _chaikin(pts, it=2, closed=True):
    """Corner-cutting smoothing of a 3-D polyline."""
    for _ in range(it):
        n = len(pts)
        out = [] if closed else [pts[0]]
        for i in range(n if closed else n - 1):
            a, b = pts[i], pts[(i + 1) % n]
            out.append(tuple(0.75 * a[k] + 0.25 * b[k] for k in range(3)))
            out.append(tuple(0.25 * a[k] + 0.75 * b[k] for k in range(3)))
        if not closed:
            out.append(pts[-1])
        pts = out
    return pts


def _rbox(x0, x1, y0, y1, z0, z1, r, rv=None, p=4, q=4, m=1):
    """Axis-aligned rounded box (furn_living._slab cage): r rounds the four
    vertical edges, rv = (bottom, top) the horizontal ones."""
    rb, rt_ = rv if rv else (r, r)
    return _slab(0.5 * (x1 - x0), 0.5 * (y1 - y0), z0, z1, r, p=p, q=q, rb=(rb, rb), rt_=(rt_, rt_),
                 mb=m, ms=1, mt=m, cx=0.5 * (x0 + x1), cy=0.5 * (y0 + y1), amin=1)


def _bar_md(p0, p1, w, t, r, ex=(1.0, 0.0, 0.0), rend=0.1):
    """Straight bar from p0 to p1: section t along ex, w across, its long
    edges rounded r, its end faces rend."""
    ez = _norm(_sub(p1, p0))
    ex = _norm(_sub(ex, _mul(ez, _dot(ex, ez))))
    ey = _cross(ez, ex)
    ln = math.sqrt(_dot(_sub(p1, p0), _sub(p1, p0)))
    md = _slab(0.5 * t, 0.5 * w, 0.0, ln, r, p=4, q=4, rb=(rend, rend), rt_=(rend, rend),
               mb=1, ms=1, mt=1, amin=1)
    return md.map(lambda v: tuple(p0[k] + v[0] * ex[k] + v[1] * ey[k] + v[2] * ez[k] for k in range(3)))


def _nodes(parts):
    """Max nodes for (name, mat, md, tile, smooth) parts."""
    return [_hard(md, name, mat, tile, smooth) for name, mat, md, tile, smooth in parts]


# ================================================================== console
def _weld_loop(cy, cz, sy, sz, d, xc, w, t, rad=0.12):
    """Fillet weld round the end of a flat brace (w wide in the side plane, t
    thick along X, centred on x = xc) entering the inner corner (cy, cz) of a
    side frame. sy, sz: signs of the opening as seen from the corner; d: the
    brace direction (y, z) pointing into the opening. The bead follows the
    brace / frame junction: leg face -> corner -> rail face on each broad
    face of the bar, across its narrow faces between them."""
    du, dv = sy * d[0], sz * d[1]                  # both > 0 in corner-local axes
    h = 0.5 * w
    loc = [(0.0, h / du), (0.0, 0.0), (h / dv, 0.0)]
    pts = []
    for sx in (1.0, -1.0):
        for (u, v) in (loc if sx > 0 else loc[::-1]):
            pts.append((xc + sx * 0.5 * t, cy + sy * u, cz + sz * v))
    pts = _chaikin(pts, 2)
    c = tuple(sum(p[k] for p in pts) / len(pts) for k in range(3))
    return _tube_md(pts, rad, 6, closed=True, normals=[_sub(p, c) for p in pts])


def console_parts(L=150.0, D=35.0, H=85.0, tube=2.0, plate=1.0, shelf_top=18.0, inset=0.5):
    """Cages of the console: [(name, mat, md, tile, smooth)].
    Frame: four legs on glides, top rails all round under the top plate,
    lower side rails at the shelf; the shelf plate spans between the legs
    (its long edges are the front and back stretchers). Rails stop 0.2 mm
    short of the leg faces so no two faces are coplanar."""
    xo, yo = 0.5 * L - inset, 0.5 * D - inset      # frame outer faces
    xi, yi = xo - tube, yo - tube                  # inner faces of the legs
    zt = H - plate                                 # top of the frame = underside of the top plate
    foot, r, e, ov = 0.4, 0.3, 0.02, 0.3           # glide height, tube radius, recess, overlap
    frame, feet = _MD(), _MD()
    glide = _fillet2d([(0.0, 0.0), (0.8, 0.0), (0.8, 0.25), (0.55, foot), (0.0, foot)],
                      [0.0, 0.08, 0.06, 0.05, 0.0], step=math.radians(22.5))
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            x0, x1 = sorted((sx * xo, sx * xi))
            y0, y1 = sorted((sy * yo, sy * yi))
            frame.merge(_rbox(x0, x1, y0, y1, foot, zt, r, (0.12, 0.05)))
            feet.merge(_revolve_md(glide, 24, x=sx * (xo - 0.5 * tube), y=sy * (yo - 0.5 * tube)))
    for sy in (-1.0, 1.0):                         # top front / back rails
        y0, y1 = sorted((sy * (yo - e), sy * (yi + e)))
        frame.merge(_rbox(-xi - ov, xi + ov, y0, y1, zt - tube, zt, r))
    for sx in (-1.0, 1.0):                         # side rails: top, and at the shelf
        x0, x1 = sorted((sx * (xo - e), sx * (xi + e)))
        frame.merge(_rbox(x0, x1, -yi - ov, yi + ov, zt - tube, zt, r))
        frame.merge(_rbox(x0, x1, -yi - ov, yi + ov, shelf_top - tube, shelf_top - e, r))
    top = _slab(0.5 * L, 0.5 * D, zt, H, 0.6, p=24, q=6, rb=(0.25, 0.25), rt_=(0.3, 0.3), mb=2, ms=1, mt=2)
    # shelf: 1 mm behind the leg faces, its ends 2 mm into the legs and side rails
    shelf = _slab(xi + 0.2, yo - 0.1, shelf_top - plate, shelf_top, 0.6, p=24, q=6,
                  rb=(0.25, 0.25), rt_=(0.3, 0.3), mb=2, ms=1, mt=2)
    braces, welds = _MD(), _MD()
    w, t, ext = 1.4, 0.4, 1.2                      # flat bar 14 x 4 mm, ends buried 12 mm
    zlo, zhi = shelf_top - e, zt - tube            # the opening of each side frame
    for sx in (-1.0, 1.0):
        xc = sx * (xo - 0.5 * tube)
        for (ya, za), (yb, zb) in (((-yi, zlo), (yi, zhi)), ((yi, zlo), (-yi, zhi))):
            dl = math.hypot(yb - ya, zb - za)
            d = ((yb - ya) / dl, (zb - za) / dl)
            braces.merge(_bar_md((xc, ya - ext * d[0], za - ext * d[1]), (xc, yb + ext * d[0], zb + ext * d[1]),
                                 w, t, 0.12))
            for (cy, cz, dd) in ((ya, za, d), (yb, zb, (-d[0], -d[1]))):
                sy = 1.0 if cy < 0.0 else -1.0
                sz = 1.0 if cz < 0.5 * (zlo + zhi) else -1.0
                welds.merge(_weld_loop(cy, cz, sy, sz, dd, xc, w, t))
    return [("BenchConsole_Frame", "metal_black", frame, METAL, 1),
            ("BenchConsole_Top", "metal_black", top, METAL, 1),
            ("BenchConsole_Shelf", "metal_black", shelf, METAL, 1),
            ("BenchConsole_Brace", "metal_black", braces, METAL, 1),
            ("BenchConsole_Weld", "metal_black", welds, METAL, 1),
            ("BenchConsole_Glide", "metal_black", feet, METAL, 1)]


def build_console(L=150.0, D=35.0, H=85.0):
    """Slim black steel console L x D x H (top plate footprint), front -Y."""
    return kit.group("BenchConsole", _nodes(console_parts(L, D, H)))


# ==================================================================== books
_BOOKS = [  # head-tail H, spine-to-fore-edge W, thickness T (cm): large hardback formats
    (33.0, 25.5, 3.1), (30.5, 23.5, 2.3), (28.5, 22.0, 3.6), (25.5, 19.5, 1.9), (31.5, 24.5, 2.7)]
_COVERS = ("linen", "leather", "paper")


def _book_sections(W, T, tb=0.28, sq=0.3, groove=0.06, n_arc=10):
    """Sections (x, z) of a hardback lying flat, x from the spine (-W/2) to the
    fore-edge (+W/2), z 0..T. Returns (case, case_caps, pages, page_caps).
    The case is the board - rounded spine - board 'C': the outer chain, the
    bottom board's half-round nose, the inner chain reversed, the top board's
    nose; it is capped by strips between the chains and the two noses, and a
    hinge groove is pressed in beside the spine. The page block fills it
    0.1 mm clear of the boards, its back rounded into the spine, its
    fore-edge hollowed (a rounded-and-backed book)."""
    a = min(0.6, 0.25 * T)                 # spine arc starts this far in from the spine line
    b = 0.12 * T                           # rounded spine bulges past the boards
    xc = -0.5 * W + a
    xg = xc + 0.9                          # hinge groove
    xn = 0.5 * W - 0.5 * tb                # centre line of the boards' round noses
    top = [(xn, T, T - tb), (xn - 0.12, T, T - tb), (xg + 0.3, T, T - tb),
           (xg + 0.1, T - groove, T - tb), (xg - 0.1, T - groove, T - tb), (xg - 0.3, T, T - tb)]
    outer = [(x, z) for x, z, _ in top]
    inner = [(x, zi) for x, _, zi in top]
    for j in range(n_arc + 1):
        ph = math.pi * j / n_arc
        outer.append((xc - (a + b) * math.sin(ph), 0.5 * T + 0.5 * T * math.cos(ph)))
        inner.append((xc - (a + b - tb) * math.sin(ph), 0.5 * T + (0.5 * T - tb) * math.cos(ph)))
    for x, z, zi in reversed(top):
        outer.append((x, T - z))
        inner.append((x, T - zi))
    n = len(outer)

    def nose(zc):                          # from the outer face round the edge to the inner face
        return [(xn + 0.5 * tb * math.cos(math.radians(t)), zc + 0.5 * tb * math.sin(math.radians(t)))
                for t in (-60.0, -30.0, 0.0, 30.0, 60.0)]
    case = outer + nose(0.5 * tb) + inner[::-1] + nose(T - 0.5 * tb)
    m_in = lambda i: 2 * n + 4 - i         # index of inner[i] in case
    case_caps = [(i, i + 1, m_in(i + 1), m_in(i)) for i in range(n - 1)]
    case_caps += [tuple(range(n - 1, n + 6)), (m_in(0),) + tuple(range(2 * n + 5, 2 * n + 10)) + (0,)]
    # page block: mirror-symmetric chains from the fore-edge middle to the spine middle
    zt, zm = T - tb - 0.01, 0.5 * T
    hh = zt - zm
    xf = 0.5 * W - sq
    cc = min(0.35, 0.1 * T)                # hollow fore-edge
    rr = 0.06                              # the block's cut edges, barely eased
    up = [(xf - cc * (1.0 - f * f), zm + (hh - rr) * f) for f in (0.0, 0.4, 0.75, 1.0)]
    up += [(xf - rr + rr * math.cos(math.radians(45.0)), zt - rr + rr * math.sin(math.radians(45.0))),
           (xf - rr, zt), (xc + 0.15, zt)]
    ra = a + b - tb - 0.03
    for j in range(1, n_arc // 2 + 1):
        ph = math.pi * j / n_arc
        up.append((xc - ra * math.sin(ph), zm + hh * math.cos(ph)))
    m = len(up)                            # up[0] and up[-1] sit on z = T/2
    pages = up + [(x, 2.0 * zm - z) for x, z in reversed(up[1:-1])]
    # one n-gon cap fanned from the middle of the back, which sees the whole
    # outline (a ladder of quads would bridge the hollow fore-edge)
    page_caps = [tuple(range(m - 1, len(pages))) + tuple(range(m - 1))]
    return case, case_caps, pages, page_caps


def book_parts(H, W, T, cover="linen", name="Book", tb=0.28, sq=0.3):
    """One hardback lying flat, centred on the origin, spine along -X, head
    towards +Y, base on z = 0: [(name, mat, md, tile, smooth)]. Board edges
    are half-round (1.4 mm), head and tail rounded over 1 mm, the page
    block's edges 0.5 mm."""
    case, ccaps, pages, pcaps = _book_sections(W, T, tb, sq)
    yc = 0.5 * H
    return [(name + "_Case", cover, _loft_md(case, -yc, yc, ccaps, 0.1), COVER_TILE.get(cover, 30.0), 1),
            (name + "_Pages", "bedding", _loft_md(pages, sq - yc, yc - sq, pcaps, 0.05), PAGES, 1)]


def book_stack_parts(seed=0):
    """3-4 large hardbacks stacked largest first, each a little turned and
    shifted, spines to the front (-Y) except one turned round; covers cycle
    through linen, leather and paper so neighbours always differ."""
    rnd = _Rand(seed * 31 + 7)
    n = 4 if rnd.uniform(0.0, 1.0) < 0.55 else 3
    start = seed % len(_BOOKS)
    picks = []
    for i in range(n):
        h, w, t = _BOOKS[(start + 2 * i) % len(_BOOKS)]
        k = rnd.uniform(0.97, 1.03)
        picks.append((h * k, w * rnd.uniform(0.98, 1.02), t * rnd.uniform(0.92, 1.08)))
    picks.sort(key=lambda b: -b[0] * b[1])
    back = (seed % (n - 1)) + 1            # this one shows its fore-edge at the front
    parts, z = [], 0.0
    for i, (h, w, t) in enumerate(picks):
        cover = _COVERS[(seed + i) % len(_COVERS)]
        deg = (-90.0 if i == back else 90.0) + rnd.uniform(-4.0, 4.0)
        ca, sa = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        dx, dy = rnd.uniform(-0.9, 0.9), rnd.uniform(-0.7, 0.7)
        for nm, mat, md, tile, sm in book_parts(h, w, t, cover, "Book%d" % i):
            md.map(lambda p, z=z, ca=ca, sa=sa, dx=dx, dy=dy:
                   (p[0] * ca - p[1] * sa + dx, p[0] * sa + p[1] * ca + dy, p[2] + z))
            parts.append((nm, mat, md, tile, sm))
        z += t
    return parts


def build_book_stack(seed=0):
    """Stack of 3-4 large hardbacks (linen / leather / paper covers)."""
    return kit.group("BookStack", _nodes(book_stack_parts(seed)))


# ============================================================== glass jars
JAR_WALL = 0.35


def _jar_profile(R, Hj, wall=JAR_WALL, base=0.9):
    """(r, z) section of a straight glass jar body: punted underside standing
    on a ring, 3.5 mm wall, fire-polished round rim, thick base."""
    return _fillet2d([(0.0, 0.18), (R - 0.85, 0.0), (R, 0.0), (R, Hj), (R - wall, Hj), (R - wall, base),
                      (0.0, base)], [0.0, 0.5, 0.55, 0.16, 0.16, 0.9, 0.0], step=math.radians(15.0))


def _jar_lid_profile(R, Hj, wall=JAR_WALL, gap=0.03):
    """Glass lid resting on the rim: a 7 mm flange, a hollow plug ring 11 mm
    down into the mouth (1.2 mm clear of the wall) and a mushroom knob."""
    rp = R - wall - 0.12
    zf0 = Hj + gap
    zf1 = zf0 + 0.7
    return _fillet2d([(0.0, zf0 - 0.15), (rp - 0.35, zf0 - 0.15), (rp - 0.35, zf0 - 1.1), (rp, zf0 - 1.1),
                      (rp, zf0), (R + 0.1, zf0), (R + 0.1, zf1), (1.25, zf1), (0.85, zf1 + 0.55),
                      (1.45, zf1 + 1.15), (1.35, zf1 + 1.55), (0.0, zf1 + 1.65)],
                     [0.0, 0.1, 0.12, 0.12, 0.1, 0.25, 0.3, 0.35, 0.3, 0.35, 0.3, 0.0], step=math.radians(15.0))


JARS = [  # outer radius, body height, x, y: a tall narrow jar beside a short wide one
    (5.2, 20.5, -6.9, 1.2), (6.0, 12.0, 6.4, -1.0)]


def glass_jar_parts():
    parts = []
    for k, (R, Hj, x, y) in enumerate(JARS):
        parts.append(("GlassJar%d_Body" % k, "glass_solid", _revolve_md(_jar_profile(R, Hj), 48, x=x, y=y), GLASS, 1))
        parts.append(("GlassJar%d_Lid" % k, "glass_solid", _revolve_md(_jar_lid_profile(R, Hj), 48, x=x, y=y),
                      GLASS, 1))
    return parts


def build_glass_jars():
    """Pair of clear glass storage jars with glass lids (two heights)."""
    return kit.group("GlassJars", _nodes(glass_jar_parts()))


# ============================================================== glass lamp
LAMP_SHADE = (13.0, 27.5, 44.5)      # drum radius, bottom, top
LAMP_BASE = (6.0, 11.0)              # glass block radius (at the foot), height


def glass_lamp_parts(cord_to_edge=None, cord_drop=85.0):
    """[(name, mat, md, tile, smooth)] of the table lamp (see build_glass_lamp)."""
    Rb, Hb = LAMP_BASE
    base = _revolve_md(_fillet2d([(0.0, 0.0), (Rb, 0.0), (Rb - 0.4, Hb), (0.0, Hb)], [0.0, 0.45, 0.8, 0.0],
                                 step=math.radians(15.0)), 64)
    brass = _MD()
    brass.merge(_revolve_md(_fillet2d([(0.0, 0.6), (0.32, 0.6), (0.32, Hb - 0.1), (0.0, Hb - 0.1)],
                                      [0.0, 0.08, 0.0, 0.0]), 12))                    # rod inside the glass
    brass.merge(_revolve_md(_fillet2d([(0.0, Hb - 0.05), (2.3, Hb - 0.05), (2.3, Hb + 0.35), (1.0, Hb + 0.75),
                                       (0.0, Hb + 0.75)], [0.0, 0.1, 0.25, 0.3, 0.0]), 32))   # cap
    zs = 28.3
    brass.merge(_revolve_md(_fillet2d([(0.0, Hb + 0.7), (0.5, Hb + 0.7), (0.5, zs), (0.0, zs)],
                                      [0.0, 0.05, 0.05, 0.0]), 16))                   # thin stem
    brass.merge(_revolve_md(_fillet2d([(0.0, zs), (1.5, zs), (1.62, zs + 0.3), (1.62, 32.6), (1.45, 32.8),
                                       (1.3, 32.85), (1.3, 33.6), (0.0, 33.6)],
                                      [0.0, 0.15, 0.1, 0.12, 0.1, 0.05, 0.1, 0.0]), 32))  # socket
    brass.merge(_revolve_md(_fillet2d([(1.3, 32.75), (2.7, 32.75), (2.7, 32.9), (1.3, 32.9)],
                                      [0.04, 0.05, 0.05, 0.04], closed=True), 32, closed=True))   # washer
    R, z0, z1 = LAMP_SHADE
    for zr in (z0 + 0.3, z1 - 0.35):                                                  # wire rings
        circ = [((R - 0.42) * math.cos(2 * math.pi * i / 48), (R - 0.42) * math.sin(2 * math.pi * i / 48), zr)
                for i in range(48)]
        brass.merge(_tube_md(circ, 0.15, 6, closed=True, normals=[(c[0], c[1], 0.0) for c in circ]))
    for k in range(3):                                                                # spider
        a = math.radians(90.0 + 120.0 * k)
        p0 = (2.5 * math.cos(a), 2.5 * math.sin(a), 32.82)
        p1 = ((R - 0.45) * math.cos(a), (R - 0.45) * math.sin(a), z1 - 0.4)
        brass.merge(_tube_md([tuple(p0[i] + (p1[i] - p0[i]) * f for i in range(3)) for f in (0.0, 0.5, 1.0)],
                             0.12, 6))
    # clear globe bulb: a 0.7 mm glass shell on a short neck in the socket
    rn, rg, tg = 1.25, 3.0, 0.07
    zc = 33.6 + 0.4 + math.sqrt(rg * rg - rn * rn)
    a0 = math.asin(rn / rg)
    a1 = math.asin((rn - tg) / (rg - tg))
    bulb = [(rn - tg, 33.4), (rn, 33.4)]
    bulb += [(rg * math.sin(a0 + (math.pi - a0) * i / 16), zc - rg * math.cos(a0 + (math.pi - a0) * i / 16))
             for i in range(17)]
    bulb[-1] = (0.0, zc + rg)
    bulb += [((rg - tg) * math.sin(math.pi - (math.pi - a1) * i / 16), zc - (rg - tg) * math.cos(math.pi - (math.pi - a1) * i / 16))
             for i in range(17)]
    bulb[2 + 17] = (0.0, zc + rg - tg)
    # drum shade: 2.5 mm linen wall, the fabric rolled over both rings, a
    # lapped vertical seam at the back (+Y)
    shade = _revolve_md(_fillet2d([(R - 0.125, z0), (R + 0.125, z0), (R + 0.125, z1), (R - 0.125, z1)],
                                  [0.1, 0.1, 0.1, 0.1], closed=True), 72, closed=True)
    for zr in (z0 + 0.28, z1 - 0.28):
        circ = [(R * math.cos(2 * math.pi * i / 72), R * math.sin(2 * math.pi * i / 72), zr) for i in range(72)]
        shade.merge(_tube_md(circ, 0.28, 6, closed=True, normals=[(c[0], c[1], 0.0) for c in circ]))
    shade.merge(_rbox(-0.6, 0.6, R + 0.05, R + 0.17, z0 + 0.6, z1 - 0.6, 0.04, (0.03, 0.03)))
    parts = [("GlassLamp_Base", "glass_solid", base, GLASS, 1),
             ("GlassLamp_Brass", "metal_brass", brass, METAL, 1),
             ("GlassLamp_Bulb", "glass_solid", _revolve_md(bulb, 32, closed=True), GLASS, 1),
             ("GlassLamp_Shade", "shade", shade, 12.0, 1)]
    if cord_to_edge is not None:
        ye = float(cord_to_edge)
        if ye < Rb + 3.5:
            raise ValueError("cord_to_edge %.1f: the lamp base (r %.1f) would not stand on the surface" % (ye, Rb))
        rc = 0.3
        # out of the groove under the glass, a lazy curve back over the surface,
        # round the plate edge (3 mm radius) and straight down behind it
        y1, y2 = Rb + 1.5, ye - 0.9
        lie = _chaikin([(0.0, 2.0, rc), (0.0, y1, rc), (0.7, y1 + 0.35 * (y2 - y1), rc),
                        (1.4, y1 + 0.75 * (y2 - y1), rc), (1.5, y2, rc), (1.5, ye - 0.3, rc)], 3, closed=False)
        arc = [(1.5, ye - 0.3 + 0.6 * math.sin(math.radians(a)), -0.3 + 0.6 * math.cos(math.radians(a)))
               for a in (22.5, 45.0, 67.5, 90.0)]
        zf = rc - float(cord_drop)                 # lying on the floor
        foot = [(1.5 + 0.9 * (1.0 - math.cos(math.radians(a))), ye + 0.3, zf + 0.9 - 0.9 * math.sin(math.radians(a)))
                for a in (0.0, 30.0, 60.0, 90.0)]
        floor = [(6.0, ye + 0.6, zf), (14.0, ye + 0.4, zf), (24.0, ye + 0.9, zf)]
        path = lie + arc + [(1.5, ye + 0.3, -2.0)] + foot + floor
        parts.append(("GlassLamp_Cord", "metal_black", _tube_md(path, rc, 8), METAL, 1))
    return parts


def build_glass_lamp(cord_to_edge=None, cord_drop=85.0):
    """Small table lamp: clear solid-glass base, thin brass stem, linen drum
    shade, 45 cm tall, shade 26 across. cord_to_edge / cord_drop: see the
    module doc."""
    return kit.group("GlassLamp", _nodes(glass_lamp_parts(cord_to_edge, cord_drop)))


# =============================================================== twig vase
_VASE = [(0.0, 0.3), (3.0, 0.0), (3.6, 0.0), (4.6, 3.6), (4.2, 8.0), (1.6, 12.6), (1.45, 14.4), (1.7, 15.0),
         (1.05, 15.0), (0.9, 14.4), (0.95, 12.4), (3.65, 7.9), (4.05, 3.7), (3.3, 1.0), (0.0, 1.0)]
_VASE_R = [0.0, 0.2, 0.35, 3.0, 3.0, 2.0, 0.6, 0.2, 0.2, 0.4, 1.5, 3.0, 2.5, 0.8, 0.0]
VASE_NECK_R = 0.9                     # narrowest inner radius of the neck (z 12-15)


def vase_profile():
    """(r, z) section of the bud vase: recessed underside on a foot ring,
    round belly, narrow neck with a rolled lip, 5-7 mm walls, 7 mm base."""
    return _fillet2d(_VASE, _VASE_R, step=math.radians(15.0))


def _twig_paths(seed=0):
    """[(centre line, radii)] of one bare twig in the bud vase. The main stem
    rises straight from the vase bottom up the neck, then zig-zags from node to
    node (a kink at each, as a twig grows), leaning out more with height and
    ending in a terminal bud; three side shoots leave upper nodes, the other
    nodes carry small lateral buds."""
    rnd = _Rand(seed * 13 + 3)
    main = [(0.55 + (0.06 - 0.55) * f, 0.2 + (0.02 - 0.2) * f, 1.32 + (15.8 - 1.32) * f)
            for f in (0.0, 0.25, 0.5, 0.75, 1.0)]
    az = math.radians(-55.0 + rnd.uniform(-20.0, 20.0))       # leans towards the front right
    lean_end = math.radians(rnd.uniform(14.0, 20.0))
    side = (-math.sin(az), math.cos(az), 0.0)
    nodes = []                                                # (index in main, direction)
    n_int = 8
    for i in range(n_int):
        lean = lean_end * (i + 1) / n_int
        d = (math.sin(lean) * math.cos(az), math.sin(lean) * math.sin(az), math.cos(lean))
        kink = (1.0 if i % 2 else -1.0) * math.tan(math.radians(rnd.uniform(4.0, 9.0)))
        d = _norm(tuple(d[k] + side[k] * kink for k in range(3)))
        ln = rnd.uniform(3.6, 5.6) * (1.0 - 0.04 * i)
        p = main[-1]
        for f in (1.0 / 3.0, 2.0 / 3.0, 1.0):
            main.append(tuple(p[k] + d[k] * ln * f for k in range(3)))
        nodes.append((len(main) - 1, d))
    d = nodes[-1][1]
    p = main[-1]
    for f in (0.3, 0.6, 0.9):                                 # terminal bud
        main.append(tuple(p[k] + d[k] * f for k in range(3)))
    cum = [0.0]
    for a, b in zip(main, main[1:]):
        cum.append(cum[-1] + math.sqrt(_dot(_sub(b, a), _sub(b, a))))
    rad = [0.3 - 0.25 * (s / cum[-4]) ** 0.85 if s <= cum[-4] else 0.05 for s in cum]
    rad[-3:] = [0.085, 0.07, 0.025]
    out = [(main, rad)]

    def shoot(p, d, r0, n, seed2):
        rr = _Rand(seed2)
        path = [p]
        for i in range(n):
            d = _norm((d[0], d[1], d[2] + 0.18))              # shoots bend up towards the light
            e = _norm(_cross(d, (0.0, 0.0, 1.0)) if abs(d[2]) < 0.99 else (1.0, 0.0, 0.0))
            d = _norm(tuple(d[k] + e[k] * (1.0 if i % 2 else -1.0) * rr.uniform(0.06, 0.15) for k in range(3)))
            ln = rr.uniform(2.6, 4.8)
            q = path[-1]
            for f in (0.5, 1.0):
                path.append(tuple(q[k] + d[k] * ln * f for k in range(3)))
        q = path[-1]
        for f in (0.25, 0.5, 0.75):
            path.append(tuple(q[k] + d[k] * f for k in range(3)))
        m = len(path)
        rads = [r0 - (r0 - 0.035) * (j / float(m - 4)) for j in range(m - 3)] + [0.06, 0.05, 0.018]
        return path, rads

    branch_at = (2, 4, 6)
    for j, (ni, dm) in enumerate(nodes[:-1]):
        e1 = _norm(_cross(dm, (0.0, 0.0, 1.0)))
        e2 = _cross(dm, e1)
        psi = math.radians(137.5 * j + rnd.uniform(-20.0, 20.0))
        perp = tuple(math.cos(psi) * e1[k] + math.sin(psi) * e2[k] for k in range(3))
        if j in branch_at:
            beta = math.radians(rnd.uniform(36.0, 54.0))
            bd = _norm(tuple(dm[k] * math.cos(beta) + perp[k] * math.sin(beta) for k in range(3)))
            out.append(shoot(main[ni], bd, 0.6 * rad[ni], 3 if j < 6 else 2, seed * 7 + j))
        else:                                                 # lateral bud on the node
            bd = _norm(tuple(dm[k] * 0.75 + perp[k] * 0.66 for k in range(3)))
            p = main[ni]
            out.append(([tuple(p[k] + bd[k] * f for k in range(3)) for f in (0.0, 0.2, 0.42, 0.6)],
                        [0.07, 0.085, 0.06, 0.015]))
    return out


def twig_vase_parts(seed=0, twig_mat="stem"):
    vase = _revolve_md(vase_profile(), 48)
    twig = _MD()
    for path, rad in _twig_paths(seed):
        twig.merge(_tube_md(path, rad, 6))
    return [("TwigVase_Vase", "pot_matte", vase, 20.0, 1),
            ("TwigVase_Twig", twig_mat, twig, 10.0, 1)]


def build_twig_vase(seed=0, twig_mat="stem"):
    """Small matte stoneware bud vase holding one bare twig. twig_mat: 'stem'
    (plant stems), or 'wood_light' for a bleached, barked-off branch."""
    return kit.group("TwigVase", _nodes(twig_vase_parts(seed, twig_mat)))


# ================================================================= preview
# Suggested dressing of build_console() standing at the origin unrotated:
# (piece, x, y, z, rotation deg, kwargs) - on the top (z = 85) and the shelf (z = 18).
DRESSING = [
    ("book_stack", -46.0, -1.0, 85.0, 6.0, {"seed": 0}),
    ("twig_vase", -14.0, 4.0, 85.0, 0.0, {}),
    ("glass_jars", 14.0, 1.5, 85.0, -8.0, {}),
    ("glass_lamp", 52.0, 4.0, 85.0, 0.0, {"cord_to_edge": 13.5, "cord_drop": 85.0}),
    ("book_stack", -40.0, 0.0, 18.0, -3.0, {"seed": 1}),
]
PIECES = {"console": console_parts, "book_stack": book_stack_parts, "glass_jars": glass_jar_parts,
          "glass_lamp": glass_lamp_parts, "twig_vase": twig_vase_parts}
_BUILD = {"console": build_console, "book_stack": build_book_stack, "glass_jars": build_glass_jars,
          "glass_lamp": build_glass_lamp, "twig_vase": build_twig_vase}


def preview(x=0.0, y=0.0, rot=0.0):
    """The console dressed as DRESSING, as one group placed at (x, y, rot)."""
    nodes = [build_console()]
    for key, px, py, pz, deg, kw in DRESSING:
        nodes.append(kit.place(_BUILD[key](**kw), px, py, pz, deg))
    return kit.place(kit.group("BenchConsole_Dressed", nodes), x, y, 0.0, rot)
