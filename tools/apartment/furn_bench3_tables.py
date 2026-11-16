"""Nesting green-onyx coffee tables, a turned walnut side table and a brass tray side table for
the MatForge benchmark-3 living room (quiet luxury: cream boucle, green onyx on dark bronze,
walnut, fluted oak, alabaster). Original, generic designs.

Every piece is built round its own origin (kit.py conventions): the centre of its footprint on
the floor, z = 0 at the floor, centimetres, Z up, FRONT facing -Y; every visible node is
registered through kit.part(...) and the piece comes back as kit.group(...).

  build_onyx_tables(seed=0)
      a pair of nesting coffee tables as ONE group whose origin is under the centre of the
      larger table's footprint. Two slabs of polished green onyx ("onyx"), 4.5 cm thick, every
      arris rounded 1.5 cm (support rings 0.3 mm off each round, so the polished faces shade
      dead flat). Each outline is a smooth asymmetric pebble - a closed periodic cubic B-spline
      (C2) through a seed-jittered control polygon, scaled to exactly its length x width:
        lower  120 x 62, top at 32: a long river stone, broad and blunt at the left, tapering to
               a nose at the right, a shallow hollow along the front;
        upper   85 x 55, top at 39: an egg-shaped pebble, broad at the right, its footprint
               centre at UPPER_AT (53, 25), turned 12 degrees, so its narrower left end hangs
               over the lower slab's back-right end 2.5 cm above it (about a fifth of its area
               overlaps the lower slab in plan): two tiers.
      Each slab stands on three slim dark-bronze legs ("bronze", 3.5 cm round): a 6.8 cm
      mounting flange under the slab (1 mm into it), the shaft flaring down through a 2 cm neck
      into a 4.2 cm ball that sits in a socket cup on a 5.2 cm round glide (the ball-jointed
      foot). The leg axes stand LEG_INSET (10 / 7.5 cm) in from the slab edge: of the triples
      round that inset outline at least 28 cm apart that hold the slab's centroid 8 cm or more
      inside their triangle, the one hardest to tip (tip_ratio: centroid depth over the
      outline's overhang, per tipping edge); the upper table's legs stand clear of the lower
      slab, a LEG_CLEAR (3.5 cm) air gap from leg to edge. Own UVs: the slabs planar at 100 cm
      per repeat (ONYX_TILE) on top and underside, the map turned BAND_DEG to each slab's
      length so the onyx bands cross it on the diagonal, each slab its own window of the stone
      (seeded); the rounds and the edge band are unfolded off the top, so the bands run on
      over the arris at true scale. The legs: U round each leg at true scale (seam at the
      back, +Y), V up it. Footprint about 156 x 86 (x -60..96, y -31..55.5 by seed); 39 high.
  build_walnut_side_table()
      round walnut side table ("wood_dark"), 55 across, 50 high: a 3 cm top (1.2 cm round over
      the top arris, 0.9 cm under it) on a turned pedestal - a base ring with a cove sweeping
      into a gently swelling, tapering shaft, a pair of beads under a trumpet capital - on a
      40 cm round foot (2.8 cm at its soft rounded edge, rising in a shallow cone to a 3.8 cm
      landing under the column, the underside recessed inside a 3 cm bearing ring). Own UVs,
      walnut grain (the map's V) running left-right (X) across the top and the foot, up the
      column (cylindrical, true scale on the shaft, seam at the back). Footprint 55 round.
  build_brass_tray_table()
      small brass tray side table ("metal_brass"), 52 high: a 40 cm spun tray (2 mm sheet, the
      floor's top at 50, a 2 cm wall flared 8 degrees with a rolled 5 mm bead round the rim,
      1.2 cm round where the wall meets the floor), screwed to a 6 cm hub on a 1.9 cm stem
      with turned ferrules, on a weighted 30 cm disc base (1.5 cm at its rounded edge, a
      shallow dome rising to a 5.2 cm hub, the underside recessed inside a 2 cm bearing
      ring). Own UVs: U round the axis at every ring's own radius (spun / turned brushing runs
      round, assuming the brushed-brass map's brushing lies along U), V along the section.
      Footprint 40 round.

All the geometry comes from pure-Python functions returning furn_living._MD cages -
pebble_outline, slab_md, leg_profile, leg_md, leg_layout, onyx_tables_layout,
onyx_tables_parts, walnut_top_md / walnut_foot_md / walnut_column_md, walnut_side_table_parts,
tray_profile, tray_base_profile, tray_stem_profile, brass_tray_table_parts - the *_parts
lists holding (name, material key, _MD, tile cm, TurboSmooth iterations). Every part carries
its own UVs on every face (tile = cm per UV unit; kit.part maptype None) and is dense enough to
need no TurboSmooth. Tested off-Max in tests/test_bench3_tables_geom.py; the build_* wrappers
only turn the cages into nodes.
"""
import math
import random

import kit
import furn_living as fl
from furn_living import _MD, _resample_closed
from furn_bench2_tables import (_arc2, _bspline_closed, _centroid2, _normals2, _ring_solid, boundary_distance,
                                point_in_polygon)

# keys the benchmark-3 scene maps to MatForge materials (declared at runtime; kit.py is not edited)
kit.MAT_KEYS.setdefault("onyx", "polished green onyx slab (benchmark-3 coffee tables)")
kit.MAT_KEYS.setdefault("bronze", "dark bronze metal")

SUPPORT = 0.03          # support rings 0.3 mm off every round: flats stay dead flat under smoothing
SINK = 0.1              # joined parts run 1 mm into each other (no coplanar faces)

# ------------------------------------------------------------------ onyx tables
ONYX_TILE = 100.0       # cm per texture repeat on the slabs
BRONZE_TILE = 30.0
ONYX_T = 4.5            # slab thickness
ONYX_R = 1.5            # round on every arris
SLABS = {
    # length (x), width (y), top of the slab, outline points, control polygon (x in half lengths,
    # y in half widths, counter-clockwise from the right end)
    "lower": {"length": 120.0, "width": 62.0, "top": 32.0, "n": 224, "salt": 11,
              "ctrl": [(1.00, -0.28), (0.93, 0.18), (0.68, 0.60), (0.25, 0.86), (-0.25, 0.97), (-0.70, 0.92),
                       (-0.98, 0.52), (-1.02, -0.10), (-0.80, -0.70), (-0.35, -0.98), (0.12, -0.88),
                       (0.48, -0.80), (0.80, -0.72)]},
    "upper": {"length": 85.0, "width": 55.0, "top": 39.0, "n": 176, "salt": 23,
              "ctrl": [(1.00, -0.12), (0.93, 0.40), (0.64, 0.86), (0.18, 1.00), (-0.32, 0.88), (-0.72, 0.55),
                       (-1.00, 0.06), (-0.90, -0.40), (-0.58, -0.74), (-0.08, -0.92), (0.42, -1.00), (0.86, -0.82)]},
}
UPPER_AT = (53.0, 25.0, 12.0)    # footprint centre (x, y) and turn (deg) of the upper slab
BAND_DEG = {"lower": 28.0, "upper": -36.0}       # the map's U axis against each slab's length
UV_WINDOW = {"lower": (0.5, 0.5), "upper": (0.13, 0.81)}   # map coordinates at each slab's centre
LEG_R = 1.75            # 3.5 cm legs
LEG_INSET = {"lower": 10.0, "upper": 7.5}
LEG_CLEAR = 3.5         # air gap from an upper-table leg to the lower slab's edge
LEG_MIN_SEP = 28.0      # legs of one table at least this far apart (axis to axis)
LEG_SEGS = 40
# the ball-jointed foot and the mounting flange
PAD_R, PAD_H = 2.6, 0.7          # round glide on the floor
CUP_R, CUP_TOP = 2.2, 1.9        # socket cup on the glide
BALL_R = 2.1
BALL_Z = CUP_TOP + 0.9           # ball centre: the cup holds its lower part
NECK_R = 1.0
FLANGE_R, FLANGE_T = 3.4, 0.6

# ------------------------------------------------------------------ walnut side table
WALNUT_TILE = 70.0      # cm per repeat of the walnut map (grain along V)
GRAIN_DEG = -90.0       # the map turned so its V (the grain) runs along X on the top and foot
WT_TOP_R, WT_TOP_T, WT_H = 27.5, 3.0, 50.0
WT_TOP_RT, WT_TOP_RB = 1.2, 0.9          # round over / under the top's edge
WT_FOOT_R = 20.0
WT_FOOT_EDGE = 2.8                        # foot thickness at its rounded edge
WT_LAND_R, WT_LAND_Z = 7.5, 3.8           # flat landing under the column
WT_COL_R = 3.2                            # reference radius of the column's cylindrical UVs

# ------------------------------------------------------------------ brass tray table
BRASS_TILE = 25.0
TRAY_R, TRAY_H, TRAY_LIP = 20.0, 52.0, 2.0      # rim radius, top of the rim bead, floor-to-rim
TRAY_T, TRAY_BEAD, TRAY_FLARE = 0.2, 0.25, 8.0  # sheet, bead radius, wall flare (deg)
TRAY_FILLET = 1.2                               # outside round where the wall meets the floor
TRAY_HUB_R = 3.0
BASE_R, BASE_EDGE, BASE_HUB_R, BASE_HUB_Z = 15.0, 1.5, 2.6, 3.2
STEM_R = 0.95


# ===================================================================== small tools
def _rng(seed, salt):
    """Deterministic, well-mixed generator for a seed (furn_living._Rand's first draws step
    almost linearly from one seed to the next)."""
    return random.Random(int(seed) * 7919 + int(salt))


def _rot2(p, deg, dx=0.0, dy=0.0):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return (dx + p[0] * c - p[1] * s, dy + p[0] * s + p[1] * c)


def _xform(md, deg, dx=0.0, dy=0.0, dz=0.0):
    """Turn a cage about Z (degrees, counter-clockwise from above), then move it (UVs stay)."""
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return md.map(lambda p: (dx + p[0] * c - p[1] * s, dy + p[0] * s + p[1] * c, dz + p[2]))


def _round_poly(pts, radii, step_deg=9.0, support=SUPPORT, closed=False):
    """Polyline with corner i replaced by a tangent circular arc of radius radii[i] (shrunk where
    a neighbouring segment is too short; split into steps of at most step_deg) and a support
    point `support` in from every arc end along each straight run, so the flats next to a round
    shade dead flat. An open polyline keeps its two end points."""
    n = len(pts)
    step = math.radians(step_deg)
    pieces = []
    for i in range(n):
        p = (float(pts[i][0]), float(pts[i][1]))
        r = float(radii[i])
        if r <= 0.0 or (not closed and i in (0, n - 1)):
            pieces.append(([p], False))
            continue
        a, c = pts[i - 1], pts[(i + 1) % n]
        l1 = math.hypot(p[0] - a[0], p[1] - a[1])
        l2 = math.hypot(c[0] - p[0], c[1] - p[1])
        d1 = ((p[0] - a[0]) / l1, (p[1] - a[1]) / l1)
        d2 = ((c[0] - p[0]) / l2, (c[1] - p[1]) / l2)
        turn = math.acos(max(-1.0, min(1.0, d1[0] * d2[0] + d1[1] * d2[1])))
        if turn < 1e-4:
            pieces.append(([p], False))
            continue
        tl = r * math.tan(0.5 * turn)
        lim = 0.5 * min(l1, l2)
        if tl > lim:
            tl = lim
            r = tl / math.tan(0.5 * turn)
        sgn = 1.0 if d1[0] * d2[1] - d1[1] * d2[0] > 0.0 else -1.0
        t1 = (p[0] - d1[0] * tl, p[1] - d1[1] * tl)
        cen = (t1[0] - d1[1] * sgn * r, t1[1] + d1[0] * sgn * r)
        a0 = math.atan2(t1[1] - cen[1], t1[0] - cen[0])
        k = max(2, int(math.ceil(turn / step)))
        pieces.append(([(cen[0] + r * math.cos(a0 + sgn * turn * j / k), cen[1] + r * math.sin(a0 + sgn * turn * j / k))
                        for j in range(k + 1)], True))
    out = []
    for i in range(n):
        seg, arc = pieces[i]
        if i > 0 or closed:
            prev, parc = pieces[i - 1]
            a, b = prev[-1], seg[0]
            ln = math.hypot(b[0] - a[0], b[1] - a[1])
            if ln > 3.0 * support:
                ux, uy = (b[0] - a[0]) / ln, (b[1] - a[1]) / ln
                if parc:
                    out.append((a[0] + ux * support, a[1] + uy * support))
                if arc:
                    out.append((b[0] - ux * support, b[1] - uy * support))
        out.extend(seg)
    clean = []
    for q in out:
        if clean and math.hypot(q[0] - clean[-1][0], q[1] - clean[-1][1]) < 1e-7:
            continue
        clean.append(q)
    if closed and len(clean) > 2 and math.hypot(clean[0][0] - clean[-1][0], clean[0][1] - clean[-1][1]) < 1e-7:
        clean.pop()
    return clean


def _lathe_md(prof, segs, cx=0.0, cy=0.0, tile=None, u_radius=None, phase=0.5 * math.pi):
    """Revolve an (r, z) section about the vertical axis through (cx, cy). Run the section
    counter-clockwise round the material (r right, z up) from the axis back to the axis: the
    r = 0 ends become poles and the solid is closed, faces outward. With tile: own UVs - V the
    arc length along the section, U round the axis from a seam at angle `phase` (+Y, the back,
    by default), at each ring's own radius (u_radius None: spun / turned brushing runs round
    at true scale) or at the fixed radius u_radius (cylindrical: lines of constant U stand
    straight up, e.g. the grain of a turned column); both in units of tile cm."""
    md = _MD()
    rings = []
    for r, z in prof:
        if r < 1e-6:
            rings.append([md.add((cx, cy, z))] * segs)
        else:
            rings.append([md.add((cx + r * math.cos(phase + 2.0 * math.pi * j / segs),
                                  cy + r * math.sin(phase + 2.0 * math.pi * j / segs), z)) for j in range(segs)])
    L = [0.0]
    for a, b in zip(prof, prof[1:]):
        L.append(L[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    for k in range(len(prof) - 1):
        ra, rb = rings[k], rings[k + 1]
        if u_radius is None:
            ka, kb = max(prof[k][0], 0.0), max(prof[k + 1][0], 0.0)
        else:
            ka = kb = u_radius
        for j in range(segs):
            j2 = (j + 1) % segs
            uv = None
            if tile:
                a0, a1 = 2.0 * math.pi * j / segs, 2.0 * math.pi * (j + 1) / segs
                uv = ((a0 * ka / tile, L[k] / tile), (a1 * ka / tile, L[k] / tile),
                      (a1 * kb / tile, L[k + 1] / tile), (a0 * kb / tile, L[k + 1] / tile))
            md.face((ra[j], ra[j2], rb[j2], rb[j]), uv)
    return md


def _arc_through(cx, cz, r, a0, a1, step=12.0):
    """Points on the arc round (cx, cz) from a0 to a1 degrees (a1 > a0), at most `step` apart
    and through every multiple of 90 degrees in between, so the arc's extremes are exact."""
    marks = [a0]
    k = int(math.floor(a0 / 90.0)) + 1
    while 90.0 * k < a1 - 1e-9:
        if 90.0 * k > a0 + 1e-9:
            marks.append(90.0 * k)
        k += 1
    marks.append(a1)
    out = []
    for s, e in zip(marks, marks[1:]):
        m = max(1, int(math.ceil((e - s) / step - 1e-9)))
        for j in range(m):
            a = math.radians(s + (e - s) * j / m)
            out.append((cx + r * math.cos(a), cz + r * math.sin(a)))
    out.append((cx + r * math.cos(math.radians(a1)), cz + r * math.sin(math.radians(a1))))
    return out


def edge_profile(z0, z1, r_top, r_bot, k=8, s=SUPPORT):
    """[(inset, z)] of a slab edge from the underside's rim up round the outside to the top's
    rim: a support ring s inside each round, the bottom round (r_bot, k segments), the vertical
    band (support rings s from both ends), the top round (r_top). Returns (profile, k_bot,
    k_top): rings k_bot..k_top run round the edge (k_bot where the bottom round meets the
    underside, k_top where the top round meets the top)."""
    if z1 - z0 < r_top + r_bot + 4.0 * s:
        raise ValueError("edge %.2f high cannot take %.2f + %.2f rounds" % (z1 - z0, r_top, r_bot))
    prof = ([(r_bot + s, z0)] + _arc2(r_bot, z0 + r_bot, r_bot, 270.0, 180.0, k)
            + [(0.0, z0 + r_bot + s), (0.0, z1 - r_top - s)]
            + _arc2(r_top, z1 - r_top, r_top, 180.0, 90.0, k) + [(r_top + s, z1)])
    return prof, 1, len(prof) - 2


def planar_uv(x, y, deg, tile, u0=0.5, v0=0.5):
    """Planar UVs, one repeat per `tile` cm, the map turned `deg` counter-clockwise (a direction
    at angle a in the map shows at a + deg on the piece), (u0, v0) of the map at (0, 0)."""
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return (u0 + (x * c + y * s) / tile, v0 + (y * c - x * s) / tile)


def ring_solid_md(outline, prof, k_bot, k_top, uv_xy):
    """Closed solid on a closed counter-clockwise plan outline with the section prof
    [(inset, z)] from the underside's rim round the outside to the top's rim (end rings closed
    by fans from their centroid). Own UVs from uv_xy(x, y): planar on the top and underside and
    on the section rings outside k_bot..k_top; rings k_bot..k_top (round the edge) are unfolded
    off the top - a point at arc length l down the edge from ring k_top takes the UV of the
    outline pushed out by l - inset(k_top) - so the figure runs on over the arris at true
    scale. The UV seam sits on ring k_bot (where the bottom round meets the underside)."""
    normals = _normals2(outline)
    e = [-d for d, _z in prof]
    for k in range(k_top - 1, k_bot - 1, -1):
        e[k] = e[k + 1] + math.hypot(prof[k + 1][0] - prof[k][0], prof[k + 1][1] - prof[k][1])

    def side_uv(i, k, band, _wrap):
        (px, py), (nx, ny) = outline[i], normals[i]
        off = e[k] if k_bot <= band < k_top else -prof[k][0]
        return uv_xy(px + nx * off, py + ny * off)

    return _ring_solid(outline, normals, prof, side_uv, uv_xy)


def circle_outline(r, n, start_deg=-90.0):
    """n points counter-clockwise round a circle of radius r, the first one at start_deg."""
    return [(r * math.cos(math.radians(start_deg) + 2.0 * math.pi * i / n),
             r * math.sin(math.radians(start_deg) + 2.0 * math.pi * i / n)) for i in range(n)]


# ===================================================================== onyx tables
def pebble_outline(which="lower", seed=0, n=None):
    """Plan of one slab ('lower' or 'upper') in its own frame: n points (SLABS[which]['n'] by
    default) counter-clockwise round a smooth asymmetric pebble - a closed cubic B-spline
    through the seed-jittered control polygon - whose bounding box is exactly length x width,
    centred on the origin; spaced by arc length plus turning (denser round the ends)."""
    spec = SLABS[which]
    L, W = spec["length"], spec["width"]
    rnd = _rng(seed, spec["salt"])
    ctrl = [(0.5 * L * (x + rnd.uniform(-0.03, 0.03)), 0.5 * W * (y + rnd.uniform(-0.03, 0.03)))
            for x, y in spec["ctrl"]]
    pts = _resample_closed(_bspline_closed(ctrl, 32), n or spec["n"], 25.0)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    sx, sy = L / (max(xs) - min(xs)), W / (max(ys) - min(ys))
    cx, cy = 0.5 * (max(xs) + min(xs)), 0.5 * (max(ys) + min(ys))
    return [((x - cx) * sx, (y - cy) * sy) for x, y in pts]


def slab_md(outline, z0, z1, r=ONYX_R, band_deg=0.0, u0=0.5, v0=0.5, tile=ONYX_TILE):
    """An onyx slab on the outline (its own frame), underside z0, top z1, every arris rounded r.
    Own UVs planar (planar_uv(band_deg, tile, u0, v0) - (u0, v0) of the map at the outline's
    centre), the edge unfolded off the top (ring_solid_md)."""
    prof, kb, kt = edge_profile(z0, z1, r, r)
    return ring_solid_md(outline, prof, kb, kt, lambda x, y: planar_uv(x, y, band_deg, tile, u0, v0))


def leg_profile(z_top):
    """(r, z) section of an onyx-table leg from the floor (on the axis) up round the outside to
    1 mm inside the slab underside z_top: the round glide (2 mm round under it, 2.2 mm over
    it), the socket cup (1.8 mm cove at its foot, 1.2 mm round rim) holding the ball, a hair
    groove where the ball leaves the cup, the ball (BALL_R) up to the neck (1.5 mm cove), the
    neck flaring into the 3.5 cm shaft (3.5 / 6 mm rounds), a 3 mm cove into the mounting
    flange (2 mm round on its edge)."""
    if z_top < 15.0:
        raise ValueError("leg %.1f cm long is too short" % z_top)
    zq = CUP_TOP - 0.05
    rim_in = math.sqrt(BALL_R ** 2 - (CUP_TOP - BALL_Z) ** 2) + 0.06
    pts = [(0.0, 0.0), (PAD_R, 0.0), (PAD_R, PAD_H), (CUP_R, PAD_H), (CUP_R, CUP_TOP), (rim_in, CUP_TOP)]
    rad = [0.0, 0.2, 0.22, 0.18, 0.12, 0.04]
    a0 = math.asin((zq - BALL_Z) / BALL_R)
    a1 = math.acos(NECK_R / BALL_R)
    m = max(3, int(math.ceil((a1 - a0) / math.radians(8.0))))
    for j in range(m + 1):
        a = a0 + (a1 - a0) * j / m
        pts.append((BALL_R * math.cos(a), BALL_Z + BALL_R * math.sin(a)))
        rad.append(0.15 if j == m else 0.0)
    z_neck = BALL_Z + BALL_R * math.sin(a1)
    pts += [(NECK_R, z_neck + 0.45), (LEG_R, z_neck + 1.45), (LEG_R, z_top - FLANGE_T),
            (FLANGE_R, z_top - FLANGE_T), (FLANGE_R, z_top + SINK), (0.0, z_top + SINK)]
    rad += [0.35, 0.6, 0.3, 0.2, 0.0, 0.0]
    return _round_poly(pts, rad, step_deg=10.0)


def leg_md(x, y, z_top, segs=LEG_SEGS, tile=BRONZE_TILE):
    """One bronze leg standing at (x, y) under a slab whose underside is at z_top; own UVs
    (U round it at true scale, seam at the back, V up it)."""
    return _lathe_md(leg_profile(z_top), segs, x, y, tile)


def leg_candidates(outline, inset, n_cand=64, avoid=None, clear=0.0):
    """Places a leg axis may stand under the outline: n_cand points evenly round it, each pushed
    `inset` in along its normal (kept where it really stands at least inset - 0.3 from the
    edge); with `avoid` (another slab's outline) only those outside it by at least `clear`."""
    ring = _resample_closed(outline, n_cand, 0.0)
    out = []
    for (x, y), (nx, ny) in zip(ring, _normals2(ring)):
        p = (x - nx * inset, y - ny * inset)
        if not point_in_polygon(outline, p[0], p[1]) or boundary_distance(outline, p[0], p[1]) < inset - 0.3:
            continue
        if avoid is not None and (point_in_polygon(avoid, p[0], p[1]) or boundary_distance(avoid, p[0], p[1]) < clear):
            continue
        out.append(p)
    return out


def tip_ratio(legs, outline):
    """How hard the slab is to tip over: for each side of the legs' triangle, the depth of the
    slab's centroid inside it over the furthest the outline overhangs beyond it (the arm of a
    load pressing on the edge there; at least 1 cm) - the smallest of the three. With the
    slab's weight W, a load of W * tip_ratio on the worst edge just balances it."""
    c = _centroid2(outline)
    a, b, d = legs
    s = 1.0 if (b[0] - a[0]) * (d[1] - a[1]) - (b[1] - a[1]) * (d[0] - a[0]) > 0.0 else -1.0
    worst = float("inf")
    for p, q in ((a, b), (b, d), (d, a)):
        ex, ey = q[0] - p[0], q[1] - p[1]
        ln = math.hypot(ex, ey)
        dep = s * (ex * (c[1] - p[1]) - ey * (c[0] - p[0])) / ln
        over = max(-s * (ex * (y - p[1]) - ey * (x - p[0])) / ln for x, y in outline)
        worst = min(worst, dep / max(over, 1.0))
    return worst


def leg_layout(outline, inset, avoid=None, clear=0.0, n_cand=64, min_sep=LEG_MIN_SEP, min_margin=8.0, n_probe=72):
    """Three leg axes under a slab outline (plan, counter-clockwise): of every triple of
    leg_candidates at least min_sep apart whose triangle holds the slab's area centroid at
    least min_margin inside, the one that is hardest to tip (largest tip_ratio, judged on
    n_probe points of the outline). Returns (legs ordered counter-clockwise round the centroid
    starting from the front, margin = the centroid's distance to the nearest side)."""
    cand = leg_candidates(outline, inset, n_cand, avoid, clear)
    c = _centroid2(outline)
    probe = _resample_closed(outline, n_probe, 0.0)
    n = len(cand)
    D = [[0.0] * n for _ in range(n)]       # centroid's distance left of the line i -> j
    O = [[0.0] * n for _ in range(n)]       # furthest the outline reaches right of it
    far = [[False] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            ex, ey = cand[j][0] - cand[i][0], cand[j][1] - cand[i][1]
            ln = math.hypot(ex, ey)
            if i == j or ln < 1e-9:
                continue
            far[i][j] = ln >= min_sep
            D[i][j] = (ex * (c[1] - cand[i][1]) - ey * (c[0] - cand[i][0])) / ln
            O[i][j] = max(1.0, max((ey * (x - cand[i][0]) - ex * (y - cand[i][1])) / ln for x, y in probe))
    best, pick = 0.0, None
    for i in range(n):
        for j in range(i + 1, n):
            if not far[i][j]:
                continue
            for k in range(j + 1, n):
                if not (far[j][k] and far[i][k]):
                    continue
                if ((cand[j][0] - cand[i][0]) * (cand[k][1] - cand[i][1])
                        - (cand[j][1] - cand[i][1]) * (cand[k][0] - cand[i][0])) > 0.0:
                    edges = ((i, j), (j, k), (k, i))
                else:
                    edges = ((i, k), (k, j), (j, i))
                if min(D[a][b] for a, b in edges) < min_margin:
                    continue
                t = min(D[a][b] / O[a][b] for a, b in edges)
                if t > best + 1e-9:
                    best, pick = t, (i, j, k)
    if pick is None:
        raise ValueError("no stable leg triple under the slab (%d candidates)" % n)
    legs = [cand[q] for q in pick]
    legs.sort(key=lambda p: (math.atan2(p[1] - c[1], p[0] - c[0]) + 0.5 * math.pi) % (2.0 * math.pi))
    a, b, d = legs
    s = 1.0 if (b[0] - a[0]) * (d[1] - a[1]) - (b[1] - a[1]) * (d[0] - a[0]) > 0.0 else -1.0
    margin = min(s * ((q[0] - p[0]) * (c[1] - p[1]) - (q[1] - p[1]) * (c[0] - p[0]))
                 / math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in ((a, b), (b, d), (d, a)))
    return legs, margin


def onyx_tables_layout(seed=0):
    """Where everything of the nesting pair stands (group space: origin under the centre of the
    lower slab's footprint). {'lower' / 'upper': {'local': outline in the slab's own frame,
    'outline': in group space, 'at': (x, y, deg), 'top', 'under': its underside, 'centroid',
    'legs': [(x, y)] * 3, 'margin': how deep the centroid sits inside the legs' triangle}}."""
    out = {}
    for which in ("lower", "upper"):
        spec = SLABS[which]
        local = pebble_outline(which, seed)
        at = (0.0, 0.0, 0.0) if which == "lower" else UPPER_AT
        world = [_rot2(p, at[2], at[0], at[1]) for p in local]
        out[which] = {"local": local, "outline": world, "at": at, "top": spec["top"],
                      "under": spec["top"] - ONYX_T, "centroid": _centroid2(world)}
    lo, up = out["lower"], out["upper"]
    if up["under"] <= lo["top"]:
        raise ValueError("the upper slab must clear the lower one")
    lo["legs"], lo["margin"] = leg_layout(lo["outline"], LEG_INSET["lower"])
    up["legs"], up["margin"] = leg_layout(up["outline"], LEG_INSET["upper"], avoid=lo["outline"],
                                          clear=LEG_R + LEG_CLEAR)
    return out


def onyx_slab_uv(which, seed=0):
    """(band_deg, u0, v0) of a slab's planar UVs: the map turned BAND_DEG (+- 5 deg), its window
    UV_WINDOW (+- 0.2) - seeded, so every pair shows its own stone."""
    rnd = _rng(seed, SLABS[which]["salt"] + 3)
    u0, v0 = UV_WINDOW[which]
    return BAND_DEG[which] + rnd.uniform(-5.0, 5.0), u0 + rnd.uniform(-0.2, 0.2), v0 + rnd.uniform(-0.2, 0.2)


def onyx_tables_parts(seed=0):
    """[(name, mat, md, tile, smooth)] of the nesting pair (see build_onyx_tables)."""
    L = onyx_tables_layout(seed)
    parts = []
    for which, tag in (("lower", "Lower"), ("upper", "Upper")):
        s = L[which]
        deg, u0, v0 = onyx_slab_uv(which, seed)
        md = _xform(slab_md(s["local"], s["under"], s["top"], ONYX_R, deg, u0, v0), s["at"][2], s["at"][0], s["at"][1])
        parts.append(("OnyxTables_%sTop" % tag, "onyx", md, ONYX_TILE, 0))
        for k, (x, y) in enumerate(s["legs"]):
            parts.append(("OnyxTables_%sLeg%d" % (tag, k), "bronze", leg_md(x, y, s["under"]), BRONZE_TILE, 0))
    return parts


def footprint(parts):
    """((x0, x1), (y0, y1), (z0, z1)) of a list of parts."""
    vs = [v for p in parts for v in p[2].v]
    return tuple((min(v[k] for v in vs), max(v[k] for v in vs)) for k in range(3))


# ===================================================================== walnut side table
def walnut_uv(x, y):
    """Planar walnut UVs on the top and the foot: the grain (the map's V) runs along X."""
    return planar_uv(x, y, GRAIN_DEG, WALNUT_TILE)


def walnut_top_md(n=160):
    """The 55 cm, 3 cm top (its top at WT_H): 1.2 cm round over the top arris, 0.9 cm under it."""
    prof, kb, kt = edge_profile(WT_H - WT_TOP_T, WT_H, WT_TOP_RT, WT_TOP_RB)
    return ring_solid_md(circle_outline(WT_TOP_R, n), prof, kb, kt, walnut_uv)


def foot_profile(r_edge=1.0, r_bot=0.45, k=8, s=SUPPORT):
    """[(inset, z)] of the round foot from its recessed underside (3 mm up, inside a 3 cm
    bearing ring) round the outside - 4.5 mm round at the floor, the edge, a 1 cm round over -
    and in up a shallow cone to the flat landing (radius WT_LAND_R at WT_LAND_Z) under the
    column. Returns (profile, k_bot, k_top) as edge_profile."""
    d_land = WT_FOOT_R - WT_LAND_R
    z_c = WT_FOOT_EDGE - r_edge               # centre of the round over the edge
    rise = WT_LAND_Z - z_c
    # the round ends tangent to the cone that runs up to the landing's rim: its slope al solves
    # (d_land - r + r sin al) tan al + r cos al = rise (bisection; f rises with al)
    lo, hi = 0.0, math.radians(30.0)
    for _ in range(60):
        al = 0.5 * (lo + hi)
        f = (d_land - r_edge + r_edge * math.sin(al)) * math.tan(al) + r_edge * math.cos(al) - rise
        if f > 0.0:
            hi = al
        else:
            lo = al
    al = 0.5 * (lo + hi)
    top = _arc2(r_edge, z_c, r_edge, 180.0, 90.0 + math.degrees(al), k)
    e = top[-1]
    prof = [(3.25, 0.3), (2.95, 0.0), (r_bot + s, 0.0)] + _arc2(r_bot, r_bot, r_bot, 270.0, 180.0, 4)
    prof += [(0.0, r_bot + s), (0.0, z_c - s)] + top
    prof += [(e[0] + math.cos(al) * s, e[1] + math.sin(al) * s), (d_land, WT_LAND_Z)]
    return prof, 3, 10 + k


def walnut_foot_md(n=160):
    """The 40 cm round foot (see foot_profile)."""
    prof, kb, kt = foot_profile()
    return ring_solid_md(circle_outline(WT_FOOT_R, n), prof, kb, kt, walnut_uv)


COL = {"base_r": 6.6, "base_h": 0.95, "cove_b": 2.4, "r0": 3.6, "r1": 2.8, "swell": 0.14,
       "bead_r": 0.8, "bead_in": 0.2, "cove_c": 3.6, "cap_r": 7.2, "cap_t": 0.7}


def column_profile(z0=WT_LAND_Z - SINK, z1=WT_H - WT_TOP_T + SINK):
    """(r, z) section of the turned pedestal from the foot's landing (1 mm into it) to the
    top's underside (1 mm into it), all from COL: a 6.6 cm base ring (3.5 mm round over it), a
    2.4 cm cove sweeping up into a shaft that tapers from 3.6 to 2.8 cm radius with a slight
    swell, a pair of 8 mm beads (1 mm coves where they meet the shaft and each other), a 3.6 cm
    cove flaring into the trumpet capital's 7.2 cm flange rim under the top (3.5 mm round)."""
    c = COL
    base_top = z0 + c["base_h"]
    r0, r1, rb, bi = c["r0"], c["r1"], c["bead_r"], c["bead_in"]
    zs0 = base_top + c["cove_b"]                       # the base cove ends here, the shaft starts
    half = math.sqrt(rb * rb - bi * bi)                # a bead meets the shaft radius this far off its centre
    z_cap = z1 - SINK - c["cap_t"]                     # underside of the capital's rim
    zc0 = z_cap - c["cove_c"]                          # the capital cove starts here
    zs1 = zc0 - 4.0 * half                             # the shaft ends, the beads start
    pts = [(0.0, z0), (c["base_r"], z0), (c["base_r"], base_top)]
    rad = [0.0, 0.0, 0.35]
    for p in _arc2(r0 + c["cove_b"], base_top + c["cove_b"], c["cove_b"], 270.0, 180.0, 9):   # base cove
        pts.append(p)
        rad.append(0.0)
    m = 10
    for j in range(1, m + 1):                                                                # the shaft
        t = j / float(m)
        pts.append((r0 + (r1 - r0) * t + c["swell"] * math.sin(math.pi * t), zs0 + (zs1 - zs0) * t))
        rad.append(0.0)
    rad[-1] = 0.1
    a = math.degrees(math.atan2(half, bi))
    for b in range(2):                                                                       # two beads
        cz = zs1 + (2 * b + 1) * half
        arc = _arc2(r1 - bi, cz, rb, -a, a, 12)[1:]
        pts += arc
        rad += [0.0] * (len(arc) - 1) + [0.1]
    for p in _arc2(r1 + c["cove_c"], zc0, c["cove_c"], 180.0, 90.0, 12)[1:]:              # capital cove
        pts.append(p)
        rad.append(0.0)
    pts += [(c["cap_r"], z_cap), (c["cap_r"], z1), (0.0, z1)]
    rad += [0.35, 0.0, 0.0]
    return _round_poly(pts, rad, step_deg=10.0)


def walnut_column_md(segs=48):
    """The turned pedestal (column_profile); cylindrical UVs at the reference radius WT_COL_R,
    so the grain (the map's V) runs straight up it; seam at the back."""
    return _lathe_md(column_profile(), segs, tile=WALNUT_TILE, u_radius=WT_COL_R)


def walnut_side_table_parts():
    """[(name, mat, md, tile, smooth)] of the walnut side table (see build_walnut_side_table)."""
    return [("WalnutSideTable_Top", "wood_dark", walnut_top_md(), WALNUT_TILE, 0),
            ("WalnutSideTable_Column", "wood_dark", walnut_column_md(), WALNUT_TILE, 0),
            ("WalnutSideTable_Foot", "wood_dark", walnut_foot_md(), WALNUT_TILE, 0)]


# ===================================================================== brass tray table
def tray_profile():
    """Closed-off (r, z) section of the spun tray from the axis under its floor round the
    outside and back to the axis on the floor's top: TRAY_T sheet, the floor's top at
    TRAY_H - TRAY_LIP, the wall flared TRAY_FLARE degrees out of a TRAY_FILLET round (the
    inside round concentric), a rolled bead of radius TRAY_BEAD whose top is at TRAY_H and
    whose outside is at TRAY_R (0.5 mm coves where it leaves the wall)."""
    al = math.radians(TRAY_FLARE)
    w = (math.sin(al), math.cos(al))                      # up the wall
    nrm = (math.cos(al), -math.sin(al))                   # out of it
    C = (TRAY_R - TRAY_BEAD, TRAY_H - TRAY_BEAD)          # bead centre on the wall's mid-line
    h = 0.5 * TRAY_T
    z_f = TRAY_H - TRAY_LIP
    z_u = z_f - TRAY_T

    def on_line(side, z):
        s = (z - C[1] - side * h * nrm[1]) / w[1]
        return (C[0] + side * h * nrm[0] + s * w[0], z)
    back = math.sqrt(TRAY_BEAD ** 2 - h * h)
    jo = (C[0] + h * nrm[0] - back * w[0], C[1] + h * nrm[1] - back * w[1])
    ji = (C[0] - h * nrm[0] - back * w[0], C[1] - h * nrm[1] - back * w[1])
    a0 = math.degrees(math.atan2(jo[1] - C[1], jo[0] - C[0]))
    a1 = math.degrees(math.atan2(ji[1] - C[1], ji[0] - C[0]))
    if a1 < a0:
        a1 += 360.0
    bead = _arc_through(C[0], C[1], TRAY_BEAD, a0, a1, 12.0)[1:-1]
    pts = [(0.0, z_u), on_line(1.0, z_u), jo] + bead + [ji, on_line(-1.0, z_f), (0.0, z_f)]
    rad = [0.0, TRAY_FILLET, 0.05] + [0.0] * len(bead) + [0.05, TRAY_FILLET - TRAY_T, 0.0]
    return _round_poly(pts, rad, step_deg=8.0)


def tray_stem_profile():
    """(r, z) section of the stem: a turned ferrule (1 mm into the base hub), the 1.9 cm stem,
    a ferrule under the tray and the 6 cm hub the tray is screwed to (1 mm into its floor)."""
    z0 = BASE_HUB_Z - SINK
    z_u = TRAY_H - TRAY_LIP - TRAY_T
    hub0 = z_u - 1.2
    pts = [(0.0, z0), (1.35, z0), (1.35, z0 + 0.9), (STEM_R, z0 + 1.25), (STEM_R, hub0 - 1.15), (1.35, hub0 - 0.8),
           (1.35, hub0), (TRAY_HUB_R, hub0), (TRAY_HUB_R, z_u + SINK), (0.0, z_u + SINK)]
    rad = [0.0, 0.0, 0.3, 0.25, 0.25, 0.3, 0.2, 0.3, 0.0, 0.0]
    return _round_poly(pts, rad, step_deg=10.0)


def tray_base_profile():
    """(r, z) section of the weighted disc base: the underside recessed 2.5 mm inside a 2 cm
    bearing ring, 3 mm round at the floor, a 1.5 cm edge with a 5.5 mm round over it, a shallow
    dome rising to the hub (5 mm cove at its foot, 3 mm round on its top)."""
    pts = [(0.0, 0.25), (BASE_R - 2.3, 0.25), (BASE_R - 2.05, 0.0), (BASE_R, 0.0), (BASE_R, BASE_EDGE),
           (BASE_HUB_R, BASE_EDGE + 0.55), (BASE_HUB_R, BASE_HUB_Z), (0.0, BASE_HUB_Z)]
    rad = [0.0, 0.08, 0.08, 0.3, 0.55, 0.5, 0.3, 0.0]
    return _round_poly(pts, rad, step_deg=10.0)


def brass_tray_table_parts():
    """[(name, mat, md, tile, smooth)] of the brass tray table (see build_brass_tray_table)."""
    return [("BrassTrayTable_Base", "metal_brass", _lathe_md(tray_base_profile(), 96, tile=BRASS_TILE), BRASS_TILE, 0),
            ("BrassTrayTable_Stem", "metal_brass", _lathe_md(tray_stem_profile(), 32, tile=BRASS_TILE), BRASS_TILE, 0),
            ("BrassTrayTable_Tray", "metal_brass", _lathe_md(tray_profile(), 128, tile=BRASS_TILE), BRASS_TILE, 0)]


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


def build_onyx_tables(seed=0):
    """The nesting pair of green-onyx coffee tables as one group, its origin under the centre of
    the larger (lower) table's footprint, front -Y, floor z = 0 (see the module docstring)."""
    return kit.group("OnyxTables", _nodes(onyx_tables_parts(seed)))


def build_walnut_side_table():
    """Round walnut side table, 55 across x 50 high, on a turned pedestal and a 40 cm foot."""
    return kit.group("WalnutSideTable", _nodes(walnut_side_table_parts()))


def build_brass_tray_table():
    """Brass tray side table: 40 cm tray with a 2 cm lip, slim stem, weighted disc base; 52 high."""
    return kit.group("BrassTrayTable", _nodes(brass_tray_table_parts()))


def preview(x=0.0, y=0.0, rot=0.0, seed=0):
    """The three pieces side by side, as one group placed at (x, y, rot) (run inside 3ds Max)."""
    nodes = [kit.place(build_onyx_tables(seed), 0.0, 0.0),
             kit.place(build_walnut_side_table(), 150.0, 30.0),
             kit.place(build_brass_tray_table(), -110.0, 10.0)]
    return kit.place(kit.group("Bench3Tables", nodes), x, y, 0.0, rot)
