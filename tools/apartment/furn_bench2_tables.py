"""Organic Nero Marquina coffee table and its dressing for the MatForge benchmark-2 living room
(moody contemporary: copper Venetian plaster, grey microcement, polished white marble floor).

Every piece is built round its own origin (kit.py conventions): the centre of its footprint on
the floor, z = 0 at the floor, centimetres, Z up, FRONT facing -Y; every visible node is
registered through kit.part(...) and the piece comes back as kit.group(...).

  build_coffee_table(seed=0, length=150, width=75, height=36, thick=4, edge_r=1, n_pedestals=3,
                     vein_deg=-25)
        Footprint length x width (150 x 75), top at `height` (36). A 4 cm Nero Marquina slab
        whose plan is a smooth asymmetric pebble - a closed periodic cubic B-spline (C2) through
        13 control points (seed-jittered), scaled to exactly length x width: a broad blunt left
        end, a flattish back with a shallow dip, a narrower right end and a soft waist on the
        front. Every arris is rounded over edge_r (1 cm) with support rings 0.3 mm off each
        round, so the polished top and the vertical band shade dead flat. Own UVs ("nero_marquina",
        100 cm per repeat): the top and underside planar, the texture turned vein_deg so the map's
        main veins (~60 deg off U) cross the top at ~35 deg to its length; the edge band is
        unfolded off the top, so the veins run on over the rounded arris at true scale.
        Patinated bronze pedestals ("bronze", own cylindrical UVs, the seam at the back): with
        n_pedestals=3 an oval 29 x 22 under the broad left end (its long axis along the edge), a
        round 24 at the front right and a round 21 at the back, staggered so both show from the
        front; n_pedestals=2: the oval and one round 24 on opposite rays through the slab's
        centroid. Pedestal plan sizes stay within 20-30 cm. Each is pushed out along its ray
        until its column face stands exactly 2 cm inside the slab outline; each has a recessed
        1 x 1 cm plinth (a shadow line at the floor), a 5 mm round at the foot of the column, a
        6 mm round at its head, and runs 1 mm up into the slab (no coplanar faces). The table
        stands statically: the slab's centroid lies well inside the pedestals' support hull.
  build_table_dressing(seed=0, top_z=36)
        the props below arranged on the top, all in table space (one group positioned for a
        table whose top is at top_z): the book pair at the broad left end with the stone bowl
        on the top book, the ribbon sculpture near the middle towards the back, the bottle
        vase and its branch at the back right (the branch leans back and to the right).
  build_book_pair(seed=0)
        two large hardbacks (furn_bench_console.book_parts): a 33.5 x 26 x 3.2 cloth-bound
        ("linen") book with a 30 x 23.5 x 2.5 paper-covered ("paper") one on it turned 7-10
        deg, spines to the front, page blocks "bedding". Box UVs in each book's own frame, so
        the cloth weave stays square to the book however it is turned. About 34 x 28, 5.7 high.
  build_stone_bowl(seed=0)
        matte stone bowl ("microcement"), 15.1 across x 5.6 high: recessed underside on a foot
        ring, 8 mm walls rounding into a 9-10 mm base, a rounded 7.5 mm rim; slightly
        hand-made (the wall is 1-2 mm out of round, the rim not quite level).
  build_bottle_vase(seed=0)
        squat clear-glass bottle ("glass_solid") 9.6 across x 16.95 high: 3 mm walls over the
        body, shoulder and neck, a punted 6.5-10 mm base, a beaded lip; holding one bare
        corkscrew branch ("stem", contorted-hazel style: an 8.4 mm thick stem curling up
        about 50 cm out of the neck and leaning back-right, four corkscrew side twigs and
        spurs on the longer ones), its cut end on the inside of the base, clear of the neck;
        about 56 high above the table overall.
  build_ribbon_sculpture(seed=0, span=25, mat="metal_brass")
        abstract ribbon loop about 25 across and 25 high: a 4 x 0.5 cm band (1.8 mm rounded
        edges) swept round a closed, slightly saddle-shaped loop and twisted through 180
        degrees on the way (Mobius-like, so it closes on itself flipped); it stands on its edge,
        the band lying flat on a 7 cm straight run at the bottom. Own UVs along the band
        (brushing follows it).

The geometry is made by pure-Python functions returning furn_living._MD cages -
pebble_outline, slab_md, pedestal_layout, pedestal_md, coffee_table_parts, book_pair_layout,
stone_bowl_parts, bottle_profile, branch_paths, bottle_vase_parts, ribbon_centreline,
ribbon_parts, table_dressing_layout, table_dressing_parts - the *_parts lists holding
(name, material key, _MD, tile cm, TurboSmooth iterations). A part whose every face carries
UVs is built with its own UVs (tile = cm per UV unit; kit.part maptype None), the others are
box-mapped at tile. All of it runs without 3ds Max (tests/test_bench2_tables_geom.py); the
build_* wrappers only turn the cages into nodes.
"""
import math

import kit
import furn_living as fl
import furn_bench_console as fbc
from furn_living import (_MD, _Rand, _add, _cross, _dot, _fillet2d, _mul, _norm, _resample_closed, _revolve_md,
                         _smooth, _sub, _tube_md)

# keys the benchmark-2 scene maps to MatForge materials (declared at runtime; kit.py is not edited)
kit.MAT_KEYS.setdefault("nero_marquina", "polished Nero Marquina black marble (MatForge nero_marquina)")
kit.MAT_KEYS.setdefault("bronze", "dark patinated bronze metal")
kit.MAT_KEYS.setdefault("microcement", "grey microcement (also stone-like objects: bowls, sculptures)")

TABLE_H = 36.0          # top of the slab
SLAB_T = 4.0
EDGE_R = 1.0
VEIN_DEG = -25.0        # the map's main veins run ~60 deg off U: turned -25 they cross the top at ~35 deg
MARBLE = 100.0          # cm per texture repeat
BRONZE = 30.0
BRASS = 25.0
GLASS = 30.0
STONE = 80.0            # as the scene's other microcement objects
BARK = 10.0
SUPPORT = 0.03          # support rings 0.3 mm off every round: flats stay dead flat under smoothing
PED_CLEAR = 2.0         # pedestal column faces stand this far inside the slab outline
PED_SINK = 0.1          # pedestals run 1 mm up into the slab


# ===================================================================== 2-D tools
def _area2(pts):
    """Signed area of a closed polygon (> 0: counter-clockwise)."""
    a = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i][0], pts[i][1]
        x1, y1 = pts[(i + 1) % n][0], pts[(i + 1) % n][1]
        a += x0 * y1 - x1 * y0
    return 0.5 * a


def _centroid2(pts):
    """Area centroid of a closed polygon (points may carry a z)."""
    a = cx = cy = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i][0], pts[i][1]
        x1, y1 = pts[(i + 1) % n][0], pts[(i + 1) % n][1]
        c = x0 * y1 - x1 * y0
        a += c
        cx += (x0 + x1) * c
        cy += (y0 + y1) * c
    return (cx / (3.0 * a), cy / (3.0 * a))


def _normals2(pts):
    """Outward unit normals of a closed counter-clockwise polyline (central differences)."""
    n = len(pts)
    out = []
    for i in range(n):
        a, b = pts[i - 1], pts[(i + 1) % n]
        tx, ty = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(tx, ty)
        out.append((ty / ln, -tx / ln))
    return out


def _turns(pts):
    """Signed turning angle at every vertex of a closed polyline (> 0: left turn)."""
    n = len(pts)
    out = []
    for i in range(n):
        a, p, c = pts[i - 1], pts[i], pts[(i + 1) % n]
        d1 = (p[0] - a[0], p[1] - a[1])
        d2 = (c[0] - p[0], c[1] - p[1])
        out.append(math.atan2(d1[0] * d2[1] - d1[1] * d2[0], d1[0] * d2[0] + d1[1] * d2[1]))
    return out


def curvature_radii(pts):
    """Signed radius of curvature at every vertex of a closed counter-clockwise polyline
    (> 0 convex, < 0 concave)."""
    n = len(pts)
    tr = _turns(pts)
    out = []
    for i in range(n):
        a, p, c = pts[i - 1], pts[i], pts[(i + 1) % n]
        ds = 0.5 * (math.hypot(p[0] - a[0], p[1] - a[1]) + math.hypot(c[0] - p[0], c[1] - p[1]))
        out.append(ds / tr[i] if abs(tr[i]) > 1e-12 else float("inf"))
    return out


def _seg_dist(px, py, ax, ay, bx, by):
    ex, ey = bx - ax, by - ay
    l2 = ex * ex + ey * ey
    t = ((px - ax) * ex + (py - ay) * ey) / l2 if l2 > 0.0 else 0.0
    t = max(0.0, min(1.0, t))
    return math.hypot(px - ax - ex * t, py - ay - ey * t)


def boundary_distance(pts, x, y):
    """Distance from (x, y) to the closed polyline pts."""
    n = len(pts)
    return min(_seg_dist(x, y, pts[i][0], pts[i][1], pts[(i + 1) % n][0], pts[(i + 1) % n][1])
               for i in range(n))


def point_in_polygon(pts, x, y):
    inside = False
    n = len(pts)
    j = n - 1
    for i in range(n):
        xi, yi = pts[i][0], pts[i][1]
        xj, yj = pts[j][0], pts[j][1]
        if (yi > y) != (yj > y) and x < xi + (y - yi) * (xj - xi) / (yj - yi):
            inside = not inside
        j = i
    return inside


def _ray_exit(pts, ox, oy, dx, dy):
    """(t, edge index) of the first crossing of the ray o + t d with the closed polyline."""
    best = None
    n = len(pts)
    for i in range(n):
        ax, ay = pts[i][0], pts[i][1]
        ex, ey = pts[(i + 1) % n][0] - ax, pts[(i + 1) % n][1] - ay
        den = dx * ey - dy * ex
        if abs(den) < 1e-12:
            continue
        t = ((ax - ox) * ey - (ay - oy) * ex) / den
        u = ((ax - ox) * dy - (ay - oy) * dx) / den
        if t > 1e-9 and -1e-12 <= u <= 1.0 + 1e-12 and (best is None or t < best[0]):
            best = (t, i)
    return best


def _bspline_closed(ctrl, per=32):
    """Closed uniform cubic B-spline (C2) of the control polygon, `per` samples a span."""
    n = len(ctrl)
    dim = len(ctrl[0])
    out = []
    for i in range(n):
        p0, p1, p2, p3 = ctrl[i - 1], ctrl[i], ctrl[(i + 1) % n], ctrl[(i + 2) % n]
        for k in range(per):
            t = k / float(per)
            t2, t3 = t * t, t * t * t
            b0 = (1.0 - t) ** 3 / 6.0
            b1 = (3.0 * t3 - 6.0 * t2 + 4.0) / 6.0
            b2 = (-3.0 * t3 + 3.0 * t2 + 3.0 * t + 1.0) / 6.0
            b3 = t3 / 6.0
            out.append(tuple(b0 * p0[d] + b1 * p1[d] + b2 * p2[d] + b3 * p3[d] for d in range(dim)))
    return out


def _arc2(cx, cz, r, a0, a1, k):
    """k + 1 points of an arc (degrees a0 -> a1) in a 2-D section plane."""
    out = []
    for j in range(k + 1):
        a = math.radians(a0 + (a1 - a0) * j / float(k))
        out.append((cx + r * math.cos(a), cz + r * math.sin(a)))
    return out


def _offset_left(pts, d):
    """Corner points of an open polyline offset by d to the left of its direction of travel
    (each segment shifted along its left normal, neighbouring offset lines intersected)."""
    lines = []
    for a, b in zip(pts, pts[1:]):
        ln = math.hypot(b[0] - a[0], b[1] - a[1])
        ux, uy = (b[0] - a[0]) / ln, (b[1] - a[1]) / ln
        lines.append((a[0] - uy * d, a[1] + ux * d, ux, uy))
    out = [(lines[0][0], lines[0][1])]
    for (px, py, ux, uy), (qx, qy, vx, vy) in zip(lines, lines[1:]):
        t = ((qx - px) * vy - (qy - py) * vx) / (ux * vy - uy * vx)
        out.append((px + ux * t, py + uy * t))
    _px, _py, ux, uy = lines[-1]
    out.append((pts[-1][0] - uy * d, pts[-1][1] + ux * d))
    return out


# ===================================================================== 3-D tools
def _ring_solid(outline, normals, prof, side_uv=None, cap_uv=None):
    """Closed solid from a closed counter-clockwise plan outline and a section prof
    [(inset, z)] running from the bottom face's rim up round the outside to the top face's
    rim: one ring per profile point (the outline offset `inset` inwards along its normals),
    quads between rings, the end rings closed by fans from their area centroid (the outline
    must be star-shaped about it). side_uv(i, k, band, wrap) -> (u, v) of ring k's vertex i in
    a face of band k (wrap: the vertex closes the ring after the last one); cap_uv(x, y)."""
    N, K = len(outline), len(prof)
    md = _MD()
    rings = [[md.add((p[0] - nx * d, p[1] - ny * d, z)) for p, (nx, ny) in zip(outline, normals)]
             for d, z in prof]
    for k in range(K - 1):
        ra, rb = rings[k], rings[k + 1]
        for i in range(N):
            i2 = (i + 1) % N
            uv = None
            if side_uv is not None:
                w = i2 == 0
                uv = (side_uv(i, k, k, False), side_uv(i2, k, k, w), side_uv(i2, k + 1, k, w),
                      side_uv(i, k + 1, k, False))
            md.face((ra[i], ra[i2], rb[i2], rb[i]), uv)
    for k, top in ((0, False), (K - 1, True)):
        ring = rings[k]
        cx, cy = _centroid2([md.v[j] for j in ring])
        c = md.add((cx, cy, prof[k][1]))
        for i in range(N):
            i2 = (i + 1) % N
            tri = (ring[i], ring[i2], c) if top else (ring[i2], ring[i], c)
            md.face(tri, [cap_uv(md.v[j][0], md.v[j][1]) for j in tri] if cap_uv else None)
    return md


def _volume(md):
    tot = 0.0
    for f in md.f:
        a = md.v[f[0]]
        for k in range(1, len(f) - 1):
            b, c = md.v[f[k]], md.v[f[k + 1]]
            tot += (a[0] * (b[1] * c[2] - b[2] * c[1]) + a[1] * (b[2] * c[0] - b[0] * c[2])
                    + a[2] * (b[0] * c[1] - b[1] * c[0]))
    return tot / 6.0


def _outward(md):
    """Turn a closed, consistently wound mesh so its faces point out."""
    if _volume(md) < 0.0:
        md.f = [tuple(reversed(f)) for f in md.f]
        md.fuv = [None if u is None else tuple(reversed(u)) for u in md.fuv]
    return md


def _xform(md, deg, dx=0.0, dy=0.0, dz=0.0):
    """Turn a cage about Z (degrees, counter-clockwise from above), then move it."""
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return md.map(lambda p: (dx + p[0] * c - p[1] * s, dy + p[0] * s + p[1] * c, dz + p[2]))


def _place(parts, x, y, z, deg):
    for _name, _mat, md, _tile, _sm in parts:
        _xform(md, deg, x, y, z)
    return parts


def _box_uv(md, tile):
    """Per-face box-projected UVs (as _build would make them, but in the cage's own frame,
    so they stay square to the object however it is turned afterwards)."""
    fuv = []
    for f in md.f:
        P = [md.v[i] for i in f]
        nx = ny = nz = 0.0
        for k in range(len(P)):
            a, b = P[k], P[(k + 1) % len(P)]
            nx += (a[1] - b[1]) * (a[2] + b[2])
            ny += (a[2] - b[2]) * (a[0] + b[0])
            nz += (a[0] - b[0]) * (a[1] + b[1])
        ax = max(range(3), key=lambda i: abs((nx, ny, nz)[i]))
        fuv.append(tuple(((q[1], q[2]), (q[0], q[2]), (q[0], q[1]))[ax] for q in P))
    md.fuv = [tuple((u / tile, v / tile) for u, v in f) for f in fuv]
    return md


# ================================================================ pebble slab
# Control polygon of the pebble (x in units of half the length, y of half the width),
# counter-clockwise from the right tip: a broad blunt left end, a flattish back with a shallow
# dip, a narrower right end and a soft waist on the front. The closed cubic B-spline through
# it is C2 (curvature-continuous: the reflections on the polished edge flow without a kink).
PEBBLE_CTRL = [(1.00, 0.02), (0.88, 0.62), (0.50, 0.90), (0.05, 0.86), (-0.40, 1.00), (-0.85, 0.92),
               (-1.04, 0.25), (-0.95, -0.60), (-0.55, -1.00), (-0.05, -0.92), (0.35, -0.70), (0.75, -0.72),
               (0.98, -0.38)]


def pebble_outline(seed=0, length=150.0, width=75.0, n=192):
    """The slab's plan: n points counter-clockwise round a smooth asymmetric pebble whose
    bounding box is exactly length x width, centred on the origin. Points are spaced by arc
    length plus turning (denser round the ends)."""
    rnd = _Rand(seed * 7 + 11)
    ctrl = [(0.5 * length * (x + rnd.uniform(-0.025, 0.025)), 0.5 * width * (y + rnd.uniform(-0.025, 0.025)))
            for x, y in PEBBLE_CTRL]
    pts = _resample_closed(_bspline_closed(ctrl, 32), n, 25.0)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    sx, sy = length / (max(xs) - min(xs)), width / (max(ys) - min(ys))
    cx, cy = 0.5 * (max(xs) + min(xs)), 0.5 * (max(ys) + min(ys))
    return [((x - cx) * sx, (y - cy) * sy) for x, y in pts]


def slab_profile(z0, z1, r_top=EDGE_R, r_bot=EDGE_R, k=8, s=SUPPORT):
    """[(inset, z)] of the slab edge from the underside's rim up round the outside to the
    top's rim: a support ring s inside each round, the bottom round (r_bot, k segments), the
    vertical band (support rings s from both ends), the top round."""
    return ([(r_bot + s, z0)] + _arc2(r_bot, z0 + r_bot, r_bot, 270.0, 180.0, k)
            + [(0.0, z0 + r_bot + s), (0.0, z1 - r_top - s)]
            + _arc2(r_top, z1 - r_top, r_top, 180.0, 90.0, k) + [(r_top + s, z1)])


def marble_uv(x, y, deg=VEIN_DEG, tile=MARBLE):
    """Planar marble UVs: one repeat per `tile` cm, the map turned `deg` counter-clockwise
    (a direction at angle a in the map shows at a + deg on the table), its centre on (0, 0)."""
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return (0.5 + (x * c + y * s) / tile, 0.5 + (y * c - x * s) / tile)


def slab_md(outline, z0, z1, r=EDGE_R, vein_deg=VEIN_DEG, tile=MARBLE):
    """The slab: outline (counter-clockwise, outer face), underside z0, top z1, every arris
    rounded r. Own UVs: top and underside planar (marble_uv); the rounds and the band are
    unfolded off the top - a point at arc length l down the edge from where the top round
    starts takes the UV of the outline pushed out by l - r - so the veins carry on over the
    arris at true scale; the UV seam sits where the bottom round meets the underside."""
    normals = _normals2(outline)
    prof = slab_profile(z0, z1, r, r)
    K = len(prof)
    e = [-d for d, _z in prof]
    for k in range(K - 3, 0, -1):
        e[k] = e[k + 1] + math.hypot(prof[k + 1][0] - prof[k][0], prof[k + 1][1] - prof[k][1])

    def side_uv(i, k, band, _wrap):
        (px, py), (nx, ny) = outline[i], normals[i]
        off = -prof[k][0] if band in (0, K - 2) else e[k]          # flat strips by the caps: planar
        return marble_uv(px + nx * off, py + ny * off, vein_deg, tile)

    return _ring_solid(outline, normals, prof, side_uv, lambda x, y: marble_uv(x, y, vein_deg, tile))


# ================================================================== pedestals
# (ray angle from the slab centroid in degrees, half axes a, b, superellipse exponent, long axis
# along the slab edge): an oval under the broad left end, round ones under the narrow right end
PEDESTALS = {3: [(171.0, 14.6, 10.8, 2.0, True), (-18.0, 12.0, 12.0, 2.0, False), (34.0, 10.5, 10.5, 2.0, False)],
             2: [(176.0, 14.6, 10.8, 2.0, True), (-4.0, 12.0, 12.0, 2.0, False)]}


def _oval(a, b, expo=2.0, n=72, rot=0.0, cx=0.0, cy=0.0, seam=(0.0, 1.0)):
    """n points counter-clockwise round a superellipse (half axes a, b; exponent 2 = ellipse)
    evenly by arc length, turned rot radians, centred on (cx, cy), starting at the point
    facing `seam` (where the cylindrical UV seam goes)."""
    m = 8 * n
    dense = []
    for j in range(m):
        t = 2.0 * math.pi * j / m
        c, s = math.cos(t), math.sin(t)
        dense.append((a * math.copysign(abs(c) ** (2.0 / expo), c), b * math.copysign(abs(s) ** (2.0 / expo), s)))
    pts = _resample_closed(dense, n, 0.0)
    cr, sr = math.cos(rot), math.sin(rot)
    pts = [(cx + x * cr - y * sr, cy + x * sr + y * cr) for x, y in pts]
    nr = _normals2(pts)
    i0 = max(range(n), key=lambda i: nr[i][0] * seam[0] + nr[i][1] * seam[1])
    return pts[i0:] + pts[:i0]


def pedestal_layout(outline, seed=0, n_pedestals=3, clear=PED_CLEAR):
    """Pedestal columns under the slab outline: each spec of PEDESTALS[n_pedestals] (ray
    angles and sizes jittered by seed) is pushed out from the slab's area centroid along its
    ray until its column face stands exactly `clear` inside the outline (bisection). Returns
    [{'centre', 'a', 'b', 'expo', 'rot', 'column'}], column = 72 points of the column face."""
    if n_pedestals not in PEDESTALS:
        raise ValueError("n_pedestals must be 2 or 3, not %r" % (n_pedestals,))
    rnd = _Rand(seed * 13 + 7)
    cx, cy = _centroid2(outline)
    if not point_in_polygon(outline, cx, cy):
        raise ValueError("slab centroid outside its outline")
    n = len(outline)
    out = []
    for ang, a, b, expo, follow in PEDESTALS[n_pedestals]:
        ang = math.radians(ang + rnd.uniform(-4.0, 4.0))
        da = rnd.uniform(-0.4, 0.4)
        a, b = a + da, (b + da if a == b else b + rnd.uniform(-0.4, 0.4))
        dx, dy = math.cos(ang), math.sin(ang)
        t_exit, ei = _ray_exit(outline, cx, cy, dx, dy)
        rot = 0.0
        if follow:                                   # long axis along the slab edge there
            p, q = outline[ei], outline[(ei + 1) % n]
            rot = math.atan2(q[1] - p[1], q[0] - p[0])
        shape = _oval(a, b, expo, 72, rot)
        R = max(math.hypot(x, y) for x, y in shape)
        ex, ey = cx + dx * t_exit, cy + dy * t_exit
        near = []                                    # only edges the column can come near
        for i in range(n):
            p, q = outline[i], outline[(i + 1) % n]
            if min(_seg_dist(p[0], p[1], cx, cy, ex, ey), _seg_dist(q[0], q[1], cx, cy, ex, ey)) < R + clear + 4.0:
                near.append((p[0], p[1], q[0], q[1]))

        def clearance(t):
            ox, oy = cx + dx * t, cy + dy * t
            return min(_seg_dist(ox + x, oy + y, *e) for x, y in shape for e in near)

        if clearance(0.0) < clear:
            raise ValueError("pedestal %.0f x %.0f does not fit under the slab" % (2 * a, 2 * b))
        lo, hi = 0.0, t_exit
        for _ in range(34):
            mid = 0.5 * (lo + hi)
            if clearance(mid) >= clear:
                lo = mid
            else:
                hi = mid
        ox, oy = cx + dx * lo, cy + dy * lo
        out.append({"centre": (ox, oy), "a": a, "b": b, "expo": expo, "rot": rot,
                    "column": _oval(a, b, expo, 72, rot, ox, oy)})
    return out


def pedestal_profile(z_top, foot=1.0, foot_h=1.0, r_bot=0.5, r_top=0.6, s=SUPPORT):
    """[(inset from the column face, z)] of a pedestal from its underside's rim up round the
    outside to its top's rim: a plinth `foot` in and `foot_h` tall (1.5 mm round at the floor,
    1 mm fillet into the column's underside), the column's 5 mm bottom round, the column face,
    the 6 mm top round; support rings s off every round."""
    return ([(foot + 0.15 + s, 0.0)] + _arc2(foot + 0.15, 0.15, 0.15, 270.0, 180.0, 3)
            + [(foot, 0.15 + s), (foot, foot_h - 0.1 - s)] + _arc2(foot - 0.1, foot_h - 0.1, 0.1, 0.0, 90.0, 3)
            + [(foot - 0.1 - s, foot_h), (r_bot + s, foot_h)] + _arc2(r_bot, foot_h + r_bot, r_bot, 270.0, 180.0, 6)
            + [(0.0, foot_h + r_bot + s), (0.0, z_top - r_top - s)]
            + _arc2(r_top, z_top - r_top, r_top, 180.0, 90.0, 6) + [(r_top + s, z_top)])


def pedestal_md(column, z_top, tile=BRONZE):
    """Solid pedestal under the column outline (counter-clockwise, its face), floor to
    z_top. Own UVs: U round the column face from the seam (column[0]), V up the profile;
    top and underside planar."""
    normals = _normals2(column)
    prof = pedestal_profile(z_top)
    S = [0.0]
    for i in range(len(column)):
        a, b = column[i], column[(i + 1) % len(column)]
        S.append(S[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    L = [0.0]
    for a, b in zip(prof, prof[1:]):
        L.append(L[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))

    def side_uv(i, k, _band, wrap):
        return ((S[-1] if wrap else S[i]) / tile, L[k] / tile)

    return _ring_solid(column, normals, prof, side_uv, lambda x, y: (x / tile, y / tile))


def coffee_table_parts(seed=0, length=150.0, width=75.0, height=TABLE_H, thick=SLAB_T, edge_r=EDGE_R,
                       n_pedestals=3, vein_deg=VEIN_DEG):
    """[(name, mat, md, tile, smooth)] of the pebble coffee table (see build_coffee_table)."""
    if thick < 2.5 * edge_r or height < thick + 10.0:
        raise ValueError("slab %.1f thick with %.1f rounds on a %.1f table" % (thick, edge_r, height))
    outline = pebble_outline(seed, length, width)
    z0, z1 = height - thick, height
    parts = [("PebbleTable_Top", "nero_marquina", slab_md(outline, z0, z1, edge_r, vein_deg), MARBLE, 0)]
    for k, ped in enumerate(pedestal_layout(outline, seed, n_pedestals)):
        parts.append(("PebbleTable_Pedestal%d" % k, "bronze", pedestal_md(ped["column"], z0 + PED_SINK), BRONZE, 0))
    return parts


# ===================================================================== book pair
BOOK_PAIR = [(33.5, 26.0, 3.2, "linen"), (30.0, 23.5, 2.5, "paper")]   # head-tail H, spine-fore-edge W, T


def book_pair_layout(seed=0):
    """Two large hardbacks, the bigger cloth-bound one below: spines to the front (-Y), the
    top one turned 7-10 deg (its sense by seed) and nudged. Returns (parts, info) with
    info = {'books': [(H, W, T, cover, deg, dx, dy)], 'tops': [z of each book's top],
    'top_z': height of the pair, 'bowl_xy': where the bowl stands on the top book}."""
    rnd = _Rand(seed * 37 + 17)

    def j(a):
        return rnd.uniform(-a, a)
    turn = 1.0 if seed % 2 == 0 else -1.0
    books = []
    for i, (H, W, T, cover) in enumerate(BOOK_PAIR):
        deg = 90.0 + (j(2.5) if i == 0 else turn * (8.5 + j(1.5)))
        books.append((H * (1.0 + j(0.02)), W * (1.0 + j(0.02)), T * (1.0 + j(0.05)), cover, deg,
                      0.0 if i == 0 else j(1.2), 0.0 if i == 0 else j(1.0)))
    parts, tops, z = [], [], 0.0
    for i, (H, W, T, cover, deg, dx, dy) in enumerate(books):
        for name, mat, md, tile, sm in fbc.book_parts(H, W, T, cover, "BookPair_Book%d" % i):
            parts.append((name, mat, _xform(_box_uv(md, tile), deg, dx, dy, z), tile, sm))
        z += T
        tops.append(z)
    H, W, T, _cover, deg, dx, dy = books[-1]
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    lx, ly = 0.08 * W + j(0.5), j(1.2)            # towards the fore-edge: clear of the hinge groove
    return parts, {"books": books, "tops": tops, "top_z": z, "bowl_xy": (dx + lx * c - ly * s, dy + lx * s + ly * c)}


# ===================================================================== stone bowl
_BOWL = [(0.0, 0.25), (2.8, 0.25), (3.0, 0.0), (3.9, 0.0), (5.4, 0.9), (7.4, 4.0), (7.55, 5.6), (6.8, 5.6),
         (6.6, 4.2), (4.2, 1.3), (0.0, 1.15)]
_BOWL_R = [0.0, 0.15, 0.12, 0.25, 2.0, 2.5, 0.35, 0.35, 2.0, 2.2, 0.0]
BOWL_H = 5.6


def bowl_profile():
    """(r, z) section of the bowl: recessed underside inside a foot ring, the wall swelling
    out and up to a rounded 7.5 mm rim, the inside falling into a 9-10 mm base."""
    return _fillet2d(_BOWL, _BOWL_R, step=math.radians(15.0))


def stone_bowl_parts(seed=0):
    """[(name, mat, md, tile, smooth)] of the matte stone bowl, a little hand-made: the wall
    1-2 mm out of round (more towards the rim), the rim 0.7 mm off level."""
    md = _revolve_md(bowl_profile(), 48)
    rnd = _Rand(seed * 23 + 9)
    p1, p2, p3 = (rnd.uniform(0.0, 2.0 * math.pi) for _ in range(3))

    def hand(p):
        x, y, z = p
        if math.hypot(x, y) < 1e-9:
            return p
        th = math.atan2(y, x)
        k = 1.0 + _smooth(z / BOWL_H) * (0.010 * math.sin(2.0 * th + p1) + 0.006 * math.sin(3.0 * th + p2))
        return (x * k, y * k, z + 0.07 * _smooth((z - 2.0) / 3.6) * math.sin(th + p3))
    md.map(hand)
    return [("StoneBowl", "microcement", md, STONE, 1)]


# ===================================================================== bottle vase
VASE_WALL = 0.3
BOTTLE_R = 4.8                   # body
BOTTLE_LIP = 16.95               # top of the lip
BOTTLE_FLOOR = 1.1               # inside of the base, on the axis
BOTTLE_NECK_R = 1.55 - VASE_WALL    # inside of the neck
_BOTTLE_WALL = [(BOTTLE_R, 1.0), (BOTTLE_R, 9.2), (1.55, 13.0), (1.55, BOTTLE_LIP)]   # body, shoulder, neck


def bottle_profile():
    """(r, z) section of the squat bottle, counter-clockwise round the glass: punted base
    standing on a ring, the body, a round shoulder and the neck (3 mm walls: the inner chain
    is the outer one offset 3 mm, its rounds concentric), a beaded lip, a 6.5-10 mm base."""
    inner = _offset_left(_BOTTLE_WALL, VASE_WALL)
    pts = [(0.0, 0.35), (3.3, 0.08), (3.7, 0.0), (BOTTLE_R, 0.0), (BOTTLE_R, 9.2), (1.55, 13.0), (1.55, 16.25),
           (1.85, 16.55), (1.85, BOTTLE_LIP), (BOTTLE_NECK_R, BOTTLE_LIP), inner[2], inner[1],
           (BOTTLE_R - VASE_WALL, 1.0), (0.0, BOTTLE_FLOOR)]
    radii = [0.0, 0.6, 0.3, 0.45, 3.2, 1.0, 0.25, 0.18, 0.15, 0.1, 1.0 + VASE_WALL, 3.2 - VASE_WALL, 0.6, 0.0]
    return _fillet2d(pts, radii, step=math.radians(15.0))


def _corkscrew(start, axis_at, side, length, pitch, amp, phase=0.0, ramp=4.0, ds=0.6):
    """Centre line curling round a slowly bending axis like a contorted-hazel shoot: each
    step's direction is the axis tilted by up to `amp` (tan of the helix angle, eased in over
    `ramp` cm) round a phase advancing 2 pi per `pitch` cm (both a little irregular).
    axis_at(f) gives the axis at fraction f of the length; side is a fixed vector across it.
    Returns (points, step directions)."""
    m = max(4, int(round(length / ds)))
    step = length / m
    P, pts, dirs = start, [start], []
    for k in range(m):
        s = (k + 0.5) * step
        ax = _norm(axis_at(s / length))
        e1 = _norm(_sub(side, _mul(ax, _dot(side, ax))))
        e2 = _cross(ax, e1)
        g = amp * _smooth(s / ramp) * (1.0 + 0.25 * math.sin(s / 5.3 + phase))
        th = phase + 2.0 * math.pi * s / pitch * (1.0 + 0.12 * math.sin(s / 7.7 + phase))
        D = _norm(_add(ax, _add(_mul(e1, g * math.cos(th)), _mul(e2, g * math.sin(th)))))
        P = _add(P, _mul(D, step))
        pts.append(P)
        dirs.append(D)
    return pts, dirs


def branch_paths(seed=0):
    """[(centre line, radii)] of one bare corkscrew branch standing in the bottle (bottle
    space): the cut end on the inside of the base, a straight run up the middle of the neck,
    then a stem curling up ~50 cm out of the lip and leaning back-right, four corkscrew side
    twigs spread round it and a short spur on each twig longer than 13 cm."""
    rnd = _Rand(seed * 19 + 5)

    def j(a):
        return rnd.uniform(-a, a)
    r0 = 0.42
    p0 = (0.9 + j(0.25), -0.4 + j(0.25), BOTTLE_FLOOR + 0.08)
    p1 = (0.1 + j(0.1), 0.1 + j(0.1), BOTTLE_LIP + 0.8)
    inside = [tuple(p0[k] + (p1[k] - p0[k]) * f for k in range(3)) for f in (0.0, 0.2, 0.4, 0.6, 0.8)]
    az = math.radians(40.0 + j(12.0))
    lean_max = math.radians(27.0 + j(4.0))
    bend = j(0.45)
    L = 50.0 + j(4.0)

    def main_axis(f):
        lean = lean_max * _smooth(1.7 * f)
        a = az + bend * f
        return (math.sin(lean) * math.cos(a), math.sin(lean) * math.sin(a), math.cos(lean))

    above, dirs = _corkscrew(p1, main_axis, (-math.sin(az), math.cos(az), 0.0), L, 11.0 + j(1.5),
                             0.85 + j(0.12), j(math.pi), 6.0, 0.6)
    main = inside + above
    ni, m = len(inside), len(above) - 1
    rad = [r0] * (ni + 1) + [max(0.065, r0 * (1.0 - 0.84 * (k / float(m)) ** 0.85)) for k in range(1, m + 1)]
    paths = [(main, rad)]
    for t_i, f in enumerate((0.3, 0.46, 0.62, 0.78)):
        f += j(0.03)
        k = int(f * m)
        base, D = above[k], dirs[k]
        e1 = _norm(_cross(D, (0.0, 0.0, 1.0)))
        e2 = _cross(D, e1)
        psi = 2.4 * t_i + j(0.5) + 1.0                # spread round the stem
        perp = _add(_mul(e1, math.cos(psi)), _mul(e2, math.sin(psi)))
        beta = math.radians(40.0 + j(10.0))
        d0 = _norm(_add(_mul(D, math.cos(beta)), _mul(perp, math.sin(beta))))
        Lt = (19.0 - 10.0 * f) * (1.0 + j(0.15))
        up = 0.35 + j(0.1)
        side = _norm(_cross(d0, (0.0, 0.0, 1.0)))
        twig, tdirs = _corkscrew(base, lambda q, d0=d0, up=up: (d0[0], d0[1], d0[2] + up * q), side, Lt,
                                 6.5 + j(1.0), 0.7 + j(0.12), j(math.pi), 2.5, 0.5)
        rt0 = min(0.22, 0.6 * rad[ni + k])
        nt = len(twig) - 1
        trad = [max(0.035, rt0 * (1.0 - 0.8 * (q / float(nt)) ** 0.9)) for q in range(nt + 1)]
        paths.append((twig, trad))
        if Lt > 13.0:                                 # a short spur off the longer twigs
            q = int(0.5 * nt)
            Dt = tdirs[min(q, len(tdirs) - 1)]
            e1 = _norm(_cross(Dt, (0.0, 0.0, 1.0)))
            sd = _norm(_add(_mul(Dt, 0.64), _mul(_add(e1, (0.0, 0.0, 0.5)), 0.77)))
            spur, _sd = _corkscrew(twig[q], lambda _f, sd=sd: sd, _norm(_cross(sd, (0.0, 0.0, 1.0))),
                                   4.5 + j(1.0), 4.5, 0.5, j(math.pi), 1.5, 0.45)
            rs0 = min(0.1, 0.6 * trad[q])
            ns = len(spur) - 1
            paths.append((spur, [max(0.03, rs0 * (1.0 - 0.7 * i / float(ns))) for i in range(ns + 1)]))
    return paths


def bottle_vase_parts(seed=0):
    """[(name, mat, md, tile, smooth)] of the glass bottle and its branch."""
    branch = _MD()
    for path, rad in branch_paths(seed):
        branch.merge(_tube_md(path, rad, 7 if rad[0] > 0.3 else 6))
    return [("BottleVase_Glass", "glass_solid", _revolve_md(bottle_profile(), 48), GLASS, 1),
            ("BottleVase_Branch", "stem", branch, BARK, 1)]


# ===================================================================== ribbon sculpture
# Control polygon of the loop (x across, y out of its plane, z up): five collinear points make
# a straight 8 cm run at the bottom for the band to lie on; the rest rises into a slightly
# lopsided loop with a gentle saddle (+y on the right, -y on the left).
RIBBON_CTRL = [(-8.0, 0.0, 0.0), (-4.0, 0.0, 0.0), (0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (8.0, 0.0, 0.0),
               (12.0, 1.2, 3.0), (13.6, 3.6, 11.0), (10.0, 3.2, 20.0), (1.5, -0.8, 25.5), (-8.5, -3.6, 23.0),
               (-13.8, -3.4, 13.0), (-12.0, -1.2, 3.0)]
RIBBON_BAND = 4.0
RIBBON_THICK = 0.5


def _band_section(w, t, r=0.18, k=3, s=SUPPORT):
    """Closed rounded rectangle (a across, b through) with support points, centrally
    symmetric: point j + m/2 is minus point j."""
    ea, eb = 0.5 * w - r, 0.5 * t - r
    corners = ((ea, -eb, -90.0), (ea, eb, 0.0), (-ea, eb, 90.0), (-ea, -eb, 180.0))
    out = []
    for ci, (ca, cb, a0) in enumerate(corners):
        for i in range(k + 1):
            a = math.radians(a0 + 90.0 * i / k)
            out.append((ca + r * math.cos(a), cb + r * math.sin(a)))
        na, nb, n0 = corners[(ci + 1) % 4]
        p0 = out[-1]
        p1 = (na + r * math.cos(math.radians(n0)), nb + r * math.sin(math.radians(n0)))
        ln = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        if ln > 3.0 * s:
            ux, uy = (p1[0] - p0[0]) / ln, (p1[1] - p0[1]) / ln
            out.append((p0[0] + ux * s, p0[1] + uy * s))
            out.append((p1[0] - ux * s, p1[1] - uy * s))
    return out


def _resample3(pts, n):
    """n points evenly by arc length round a closed 3-D polyline (starting at pts[0])."""
    cum = [0.0]
    m = len(pts)
    for i in range(m):
        a, b = pts[i], pts[(i + 1) % m]
        cum.append(cum[-1] + math.sqrt(_dot(_sub(b, a), _sub(b, a))))
    out, seg = [], 0
    for k in range(n):
        target = cum[-1] * k / n
        while cum[seg + 1] < target:
            seg += 1
        a, b = pts[seg], pts[(seg + 1) % m]
        t = (target - cum[seg]) / max(cum[seg + 1] - cum[seg], 1e-12)
        out.append(tuple(a[q] + (b[q] - a[q]) * t for q in range(3)))
    return out, cum[-1]


def ribbon_centreline(seed=0, n=200, scale=1.0):
    """n points evenly round the loop's centre line (from the middle of its bottom run, which
    lies on z = 0, along +X first), scaled about that point; and the loop length."""
    rnd = _Rand(seed * 29 + 13)
    ctrl = [c if c[2] == 0.0 else (c[0] + rnd.uniform(-0.6, 0.6), c[1] + rnd.uniform(-0.4, 0.4),
                                   c[2] + rnd.uniform(-0.6, 0.6)) for c in RIBBON_CTRL]
    per = 40
    dense = _bspline_closed(ctrl, per)
    dense = dense[2 * per:] + dense[:2 * per]        # start at the middle of the straight run (x = 0)
    dense = [(p[0] * scale, p[1] * scale, p[2] * scale) for p in dense]
    return _resample3(dense, n)


def _ribbon_rings(cl, S, w, t):
    """Ring vertices of the twisted band round the centre line cl (closed, n points, length
    S): frame T (tangent), B0 (the loop-plane normal +Y made square to T), N0 = T x B0; the
    section's width axis turns from B0 by psi, which stays 0 until the centre line has risen
    w / 2 + 0.6 off the bottom run, then eases through 180 deg and is 180 deg again before it
    comes back down. Returns (rings [[(x, y, z)]], psi list, section)."""
    n = len(cl)
    sec = _band_section(w, t)
    zt = 0.5 * w + 0.6
    s = [S * i / n for i in range(n)]
    i_a = next(i for i in range(n) if cl[i][2] >= zt)
    i_b = next(i for i in range(n - 1, -1, -1) if cl[i][2] >= zt)
    sa, sb = s[i_a], s[i_b]
    rings, psis = [], []
    for i in range(n):
        T = _norm(_sub(cl[(i + 1) % n], cl[i - 1]))
        B0 = _norm(_sub((0.0, 1.0, 0.0), _mul(T, T[1])))
        N0 = _cross(T, B0)
        u = 0.0 if s[i] <= sa else (1.0 if s[i] >= sb else (s[i] - sa) / (sb - sa))
        psi = math.pi * u * u * (3.0 - 2.0 * u)
        W = _add(_mul(B0, math.cos(psi)), _mul(N0, math.sin(psi)))
        Kd = _add(_mul(B0, -math.sin(psi)), _mul(N0, math.cos(psi)))
        rings.append([_add(cl[i], _add(_mul(W, a), _mul(Kd, b))) for a, b in sec])
        psis.append(psi)
    return rings, psis, sec


def ribbon_md(seed=0, span=25.0, w=RIBBON_BAND, t=RIBBON_THICK, n=200, tile=BRASS):
    """The ribbon loop as one closed solid standing on z = 0, centred on its bottom run, its
    overall width (x) `span`. The last ring joins the first one half a section round (the
    180-degree twist). Own UVs: U along the band, V round its section. Returns (md, info)."""
    cl, S = ribbon_centreline(seed, n)
    rings, _psis, sec = _ribbon_rings(cl, S, w, t)
    xs = [p[0] for r in rings for p in r]
    ext = max(p[0] for p in cl) - min(p[0] for p in cl)
    k = (span - (max(xs) - min(xs) - ext)) / ext       # the band's own overhang kept, the loop scaled
    cl, S = ribbon_centreline(seed, n, k)
    rings, psis, sec = _ribbon_rings(cl, S, w, t)
    lift = 0.5 * t                                     # the band's flat underside on z = 0
    m, h = len(sec), len(sec) // 2
    per = [0.0]
    for q in range(m):
        a, b = sec[q], sec[(q + 1) % m]
        per.append(per[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    md = _MD()
    idx = [[md.add((p[0], p[1], p[2] + lift)) for p in r] for r in rings]
    for i in range(n):
        i2 = (i + 1) % n
        u0, u1 = S * i / n / tile, S * (i + 1) / n / tile
        for q in range(m):
            q2 = (q + 1) % m
            if i2:
                face = (idx[i][q], idx[i][q2], idx[i2][q2], idx[i2][q])
            else:                                      # Mobius join: half a section round
                face = (idx[i][q], idx[i][q2], idx[0][(q2 + h) % m], idx[0][(q + h) % m])
            v0, v1 = per[q] / tile, per[q + 1] / tile
            md.face(face, ((u0, v0), (u0, v1), (u1, v1), (u1, v0)))
    _outward(md)
    return md, {"centreline": [(p[0], p[1], p[2] + lift) for p in cl], "length": S, "psi": psis,
                "section": sec, "scale": k}


def ribbon_parts(seed=0, span=25.0, mat="metal_brass"):
    """[(name, mat, md, tile, smooth)] of the ribbon sculpture ('metal_brass' or 'bronze')."""
    if mat not in ("metal_brass", "bronze"):
        raise ValueError("ribbon material %r: metal_brass or bronze" % (mat,))
    return [("RibbonSculpture", mat, ribbon_md(seed, span)[0], BRASS, 0)]


# ================================================================== dressing
def table_dressing_layout(seed=0, top_z=TABLE_H):
    """Where the props stand on the table top (table space): {key: (x, y, z, deg)}. The bowl
    goes on the top book (see table_dressing_parts)."""
    rnd = _Rand(seed * 53 + 29)

    def j(a):
        return rnd.uniform(-a, a)
    return {"book_pair": (-40.0 + j(1.5), -3.0 + j(1.5), top_z, j(4.0)),
            "ribbon": (3.0 + j(1.5), 9.0 + j(1.5), top_z, 18.0 + j(6.0)),
            "bottle_vase": (40.0 + j(1.5), 12.0 + j(1.5), top_z, j(20.0))}


def table_dressing_parts(seed=0, top_z=TABLE_H):
    """Every prop's parts placed on a table whose top is at top_z (table space)."""
    lay = table_dressing_layout(seed, top_z)
    books, info = book_pair_layout(seed)
    bx, by, bz, bdeg = lay["book_pair"]
    parts = _place(books, bx, by, bz, bdeg)
    c, s = math.cos(math.radians(bdeg)), math.sin(math.radians(bdeg))
    ux, uy = info["bowl_xy"]
    parts += _place(stone_bowl_parts(seed), bx + ux * c - uy * s, by + ux * s + uy * c, bz + info["top_z"],
                    37.0 * seed)
    parts += _place(ribbon_parts(seed), *lay["ribbon"])
    parts += _place(bottle_vase_parts(seed), *lay["bottle_vase"])
    return parts


# ================================================================ Max wrappers
def _nodes(parts):
    """Max nodes for (name, mat, md, tile, smooth) parts: own UVs when every face has them."""
    out = []
    for name, mat, md, tile, smooth in parts:
        if md.fuv and len(md.fuv) == len(md.f) and all(u is not None for u in md.fuv):
            node = fl._build(md, name, tile)
            if smooth:
                kit.soften(node, None, smooth)
            out.append(kit.part(node, mat, None, None))
        else:
            out.append(fl._hard(md, name, mat, tile, smooth))
    return out


def build_coffee_table(seed=0, length=150.0, width=75.0, height=TABLE_H, thick=SLAB_T, edge_r=EDGE_R,
                       n_pedestals=3, vein_deg=VEIN_DEG):
    """Organic Nero Marquina coffee table, footprint length x width, top at height (see the
    module docstring). Front -Y, base on z = 0, centred on its footprint."""
    return kit.group("PebbleTable", _nodes(coffee_table_parts(seed, length, width, height, thick, edge_r,
                                                             n_pedestals, vein_deg)))


def build_table_dressing(seed=0, top_z=TABLE_H):
    """The coffee table's props, in table space for a top at top_z: place this group exactly
    as the table (kit.place with the same x, y, rotation)."""
    return kit.group("PebbleTableDressing", _nodes(table_dressing_parts(seed, top_z)))


def build_book_pair(seed=0):
    """Two stacked coffee-table books, about 34 x 31 x 5.7, at the origin."""
    return kit.group("BookPair", _nodes(book_pair_layout(seed)[0]))


def build_stone_bowl(seed=0):
    """Matte stone bowl 15.1 x 5.6 at the origin."""
    return kit.group("StoneBowl", _nodes(stone_bowl_parts(seed)))


def build_bottle_vase(seed=0):
    """Glass bottle vase (9.6 x 16.95) with its corkscrew branch, at the origin."""
    return kit.group("BottleVase", _nodes(bottle_vase_parts(seed)))


def build_ribbon_sculpture(seed=0, span=25.0, mat="metal_brass"):
    """Twisted ribbon loop about `span` across, standing on its bottom run at the origin."""
    return kit.group("RibbonSculpture", _nodes(ribbon_parts(seed, span, mat)))


def preview(x=0.0, y=0.0, rot=0.0, seed=0):
    """The table dressed, as one group placed at (x, y, rot) (run inside 3ds Max)."""
    nodes = [build_coffee_table(seed), build_table_dressing(seed)]
    return kit.place(kit.group("PebbleTable_Dressed", nodes), x, y, 0.0, rot)
