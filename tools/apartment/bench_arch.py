"""Architecture for the bright pre-war benchmark living room (MatForge, V-Ray, 3ds Max 2026).

Five pieces. Every one is generated as pure-Python quad cages (furn_living._MD)
by a *_md / *_parts function that runs without Max (tests/test_bench_arch_geom.py),
and handed to Max by a thin build_* wrapper (furn_living._build + kit.part +
kit.group). Hard edges are real fillets in the sections (1-6 mm, 4-9 mm on the
arrises a hand touches), so nothing is razor sharp; each node gets a Smooth
modifier (auto 40 deg) instead of TurboSmooth, which would melt the mouldings.

  build_cornice(rect_cm, ceiling_z)       plaster crown cornice 18 cm tall x 14 cm deep:
                                          band, bead between quirks, ledge, 6 cm cove,
                                          ledge, 2 cm ovolo, corona, top cove, ceiling
                                          band; run round the room with mitred corners
  build_skirting(rect_cm, openings)       18 cm skirting board 2.5 cm thick: V quirk line,
                                          ledge, ogee and a thin rounded top; mitred
                                          corners, square capped ends at openings
  build_french_window(width, height, sill_z)
                                          two-leaf French balcony door 140 x 260 with a
                                          fixed transom: 7 cm rounded frame, lapped 6 cm
                                          sashes (ovolo sticking, putty rebates), tall
                                          bottom rails, 2 glazing bars per leaf (3 panes),
                                          astragal, brass cremone bolt + lever, vase-ended
                                          fiche hinges, 4 mm glass in the rebates
  build_radiator(width, height)           cast-iron style column radiator 80 x 60: hairpin
                                          tube sections on domed hubs, cast feet, wheel
                                          valve + lockshield on chrome floor pipes
  build_panel_door(width, height, wall, swing)
                                          90 x 240 leaf with two raised-and-fielded panels
                                          and planted ogee mouldings (both faces), jamb
                                          lining + stop bead, 12 cm moulded architraves on
                                          plinth blocks (both faces), brass lever roses,
                                          escutcheons and hinge knuckles

Conventions (kit.py): centimetres, Z up. The window, radiator and door are built
round their own origin (centre of the footprint, z = 0 on the floor) with the
ROOM side facing -Y, for kit.place(). The cornice and skirting take the room's
wall-face rectangle in scene centimetres and come back already in place (their
group sits at the origin; do not move it).

Materials: wall_paint (cornice), paint_white (joinery, radiator), glass (panes),
metal_brass (window and door hardware), metal_chrome (radiator valves).
"""
import math

from pymxs import runtime as rt

import kit
from furn_living import _MD, _add, _bez, _build, _fillet2d, _mul, _norm, _revolve_md, _sub, _tube_md

# The benchmark brief names the scene's white plaster key "wall_paint" for the
# cornice; kit.MAT_KEYS predates it, so declare it here (runtime only - kit.py
# itself is not edited). The scene maps it like its walls (white_paint_wall).
kit.MAT_KEYS.setdefault("wall_paint", "white plaster wall paint (walls, cornices)")

PLASTER = 150.0     # wall_paint repeat, as the scene's walls
JOINERY = 60.0      # paint_white repeat, as the scene's casings and doors
METAL = 25.0
GLASS = 100.0
STEP = math.radians(22.5)


# ===================================================================== 2-D tools
def _arc(cx, cy, r, a0, a1, step=15.0, sag=0.01):
    """Arc points (x, y, 0) from angle a0 to a1 (degrees, either direction),
    ends included; segments of at most `step` degrees and chord sag `sag` cm
    (a 6 cm cove gets 14 segments, a 7 mm bead 12)."""
    if r > sag:
        step = min(step, math.degrees(2.0 * math.acos(1.0 - sag / r)))
    n = max(2, int(math.ceil(abs(a1 - a0) / step)))
    out = []
    for k in range(n + 1):
        a = math.radians(a0 + (a1 - a0) * k / n)
        out.append((cx + r * math.cos(a), cy + r * math.sin(a), 0.0))
    return out


def _profile(items, closed=True, step=STEP):
    """A section from corner points (x, y, fillet radius) and arcs (lists of
    points): coincident neighbours merge (keeping the larger radius), then
    every corner is rounded with _fillet2d."""
    pts = []
    for it in items:
        for p in (it if isinstance(it, list) else [it]):
            q = (float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0)
            if pts and abs(pts[-1][0] - q[0]) < 1e-7 and abs(pts[-1][1] - q[1]) < 1e-7:
                pts[-1] = (q[0], q[1], max(pts[-1][2], q[2]))
                continue
            pts.append(q)
    if closed and len(pts) > 2 and abs(pts[0][0] - pts[-1][0]) < 1e-7 and abs(pts[0][1] - pts[-1][1]) < 1e-7:
        r = max(pts[0][2], pts.pop()[2])
        pts[0] = (pts[0][0], pts[0][1], r)
    out = _fillet2d([p[:2] for p in pts], [p[2] for p in pts], closed=closed, step=step)
    res = []
    for p in out:                    # neighbouring fillets may meet at one point
        if res and math.hypot(p[0] - res[-1][0], p[1] - res[-1][1]) < 1e-6:
            continue
        res.append((p[0], p[1]))
    if closed and len(res) > 2 and math.hypot(res[0][0] - res[-1][0], res[0][1] - res[-1][1]) < 1e-6:
        res.pop()
    return res


def _area2(pts):
    a = 0.0
    for i in range(len(pts)):
        p, q = pts[i], pts[(i + 1) % len(pts)]
        a += p[0] * q[1] - q[0] * p[1]
    return 0.5 * a


def _earclip(pts):
    """Triangulate a simple polygon; the triangles keep the polygon's winding."""
    n = len(pts)
    if n < 3:
        return []
    area = _area2(pts)
    idx = list(range(n)) if area > 0 else list(range(n - 1, -1, -1))

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    tris = []
    while len(idx) > 3:
        m = len(idx)
        pick = None
        for k in range(m):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % m]
            a, b, c = pts[i0], pts[i1], pts[i2]
            if cross(a, b, c) <= 1e-12:
                continue
            clear = True
            for j in idx:
                if j == i0 or j == i1 or j == i2:
                    continue
                p = pts[j]
                if cross(a, b, p) > 1e-12 and cross(b, c, p) > 1e-12 and cross(c, a, p) > 1e-12:
                    clear = False
                    break
            if clear:
                pick = k
                break
        if pick is None:             # only collinear leftovers: clip the least reflex one
            pick = max(range(m), key=lambda k: cross(pts[idx[k - 1]], pts[idx[k]], pts[idx[(k + 1) % m]]))
        tris.append((idx[pick - 1], idx[pick], idx[(pick + 1) % m]))
        idx.pop(pick)
    tris.append(tuple(idx))
    if area < 0:
        tris = [(a, c, b) for (a, b, c) in tris]
    return tris


# ===================================================================== 3-D tools
def _volume(md):
    """Signed volume (divergence theorem): > 0 when a closed mesh faces outward."""
    v, tot = md.v, 0.0
    for f in md.f:
        a = v[f[0]]
        for k in range(1, len(f) - 1):
            b, c = v[f[k]], v[f[k + 1]]
            tot += (a[0] * (b[1] * c[2] - b[2] * c[1]) + a[1] * (b[2] * c[0] - b[0] * c[2])
                    + a[2] * (b[0] * c[1] - b[1] * c[0]))
    return tot / 6.0


def _outward(md):
    """Turn a closed, consistently wound mesh so its normals face out."""
    if _volume(md) < 0.0:
        md.f = [tuple(reversed(f)) for f in md.f]
        md.fuv = [None if u is None else tuple(reversed(u)) for u in md.fuv]
    return md


def _merge(mds):
    out = _MD()
    for m in mds:
        out.merge(m)
    return out


def _sweep(path, prof, to3d, closed=False, prof_closed=True, support=0.2, caps=True):
    """Sweep the section prof [(u, c)] along a polyline path [(a, b)] that lies
    in a plane: u is the offset to the LEFT of the direction of travel, c the
    coordinate off the plane, to3d(a, b, c) -> (x, y, z). Corners are mitred
    (cut on the bisector, as a plasterer or joiner runs a moulding round a
    room) and corners sharper than 35 deg get a support ring `support` cm to
    either side, so smoothing cannot leak along a run; open paths end square.
    caps closes the solid: section-shaped end faces on an open path, and for
    an open section on a closed path the two loops its end points sweep (the
    field of a raised panel, the faces of a rounded box). Closed results are
    wound outward."""
    n = len(path)
    segs = n if closed else n - 1
    if segs < 1 or (closed and n < 3):
        raise ValueError("path too short")
    tang = []
    for i in range(segs):
        a, b = path[i], path[(i + 1) % n]
        ln = math.hypot(b[0] - a[0], b[1] - a[1])
        if ln < 1e-9:
            raise ValueError("zero-length path segment %d" % i)
        tang.append(((b[0] - a[0]) / ln, (b[1] - a[1]) / ln, ln))
    offs, sharp = [], []
    for i in range(n):
        if not closed and (i == 0 or i == n - 1):
            t = tang[0] if i == 0 else tang[-1]
            offs.append((-t[1], t[0]))
            sharp.append(False)
            continue
        t1, t2 = tang[i - 1], tang[i % segs]
        n1, n2 = (-t1[1], t1[0]), (-t2[1], t2[0])
        k = 1.0 + n1[0] * n2[0] + n1[1] * n2[1]
        if k < 0.1:
            raise ValueError("path folds back at vertex %d" % i)
        offs.append(((n1[0] + n2[0]) / k, (n1[1] + n2[1]) / k))
        sharp.append(t1[0] * t2[0] + t1[1] * t2[1] < math.cos(math.radians(35.0)))
    us = [p[0] for p in prof]

    def run_min(i):                  # shortest length of segment i over the section
        t, m0, m1 = tang[i], offs[i], offs[(i + 1) % n]
        g = (m1[0] - m0[0]) * t[0] + (m1[1] - m0[1]) * t[1]
        return min(t[2] + u * g for u in us)

    for i in range(segs):
        if run_min(i) <= 1e-4:
            raise ValueError("section too deep for path segment %d" % i)
    st = []                          # stations: (point on the path, offset vector)
    for i in range(n):
        P, m = path[i], offs[i]
        if sharp[i] and support > 0.0:
            ti, to = tang[i - 1], tang[i % segs]
            s1 = min(support, 0.25 * run_min((i - 1) % segs))
            s2 = min(support, 0.25 * run_min(i % segs))
            st.append(((P[0] - s1 * ti[0], P[1] - s1 * ti[1]), m))
            st.append((P, m))
            st.append(((P[0] + s2 * to[0], P[1] + s2 * to[1]), m))
        else:
            st.append((P, m))
    md = _MD()
    rings = [[md.add(to3d(B[0] + u * m[0], B[1] + u * m[1], c)) for (u, c) in prof] for (B, m) in st]
    npf, ns = len(prof), len(rings)
    for r in range(ns if closed else ns - 1):
        ra, rb = rings[r], rings[(r + 1) % ns]
        for j in range(npf if prof_closed else npf - 1):
            j2 = (j + 1) % npf
            md.face((ra[j], ra[j2], rb[j2], rb[j]))
    if caps and not closed and prof_closed:
        for a, b, c in _earclip([(p[0], p[1]) for p in prof]):
            md.face((rings[0][a], rings[0][c], rings[0][b]))
            md.face((rings[-1][a], rings[-1][b], rings[-1][c]))
    if caps and closed and not prof_closed:
        for j, rev in ((0, False), (npf - 1, True)):
            pts = [(B[0] + prof[j][0] * m[0], B[1] + prof[j][0] * m[1]) for (B, m) in st]
            idx = [rg[j] for rg in rings]
            for a, b, c in _earclip(pts):
                md.face((idx[a], idx[c], idx[b]) if rev else (idx[a], idx[b], idx[c]))
    if (closed and prof_closed) or (caps and closed != prof_closed):
        _outward(md)
    return md


def _rbox_md(x0, x1, y0, y1, z0, z1, r=0.3):
    """Closed box with every edge rounded: radius r round the top and bottom,
    a little more (1.6 r) on the vertical edges so the caps stay clean."""
    x0, x1 = sorted((float(x0), float(x1)))
    y0, y1 = sorted((float(y0), float(y1)))
    z0, z1 = sorted((float(z0), float(z1)))
    r = max(0.02, min(r, 0.45 * (x1 - x0), 0.45 * (y1 - y0), 0.45 * (z1 - z0)))
    rc = min(1.6 * r, 0.49 * min(x1 - x0, y1 - y0))
    path = _fillet2d([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], [rc] * 4, closed=True,
                     step=math.radians(30.0))
    prof = [p[:2] for p in _arc(r, z1 - r, r, 90.0, 180.0, 30.0)]
    prof += [p[:2] for p in _arc(r, z0 + r, r, 180.0, 270.0, 30.0)]
    return _sweep(path, prof, lambda a, b, c: (a, b, c), closed=True, prof_closed=False)


def _rod_md(path, r, sides=12, seg=4, ends=(True, True)):
    """Round bar along a 3-D polyline, domed at the chosen ends; r may be a
    per-point list."""
    rad = list(r) if isinstance(r, (list, tuple)) else [float(r)] * len(path)
    pts, rr = list(path), rad[:]
    if ends[0]:
        t = _norm(_sub(path[1], path[0]))
        pre = []
        for k in range(seg, 0, -1):
            th = 0.5 * math.pi * k / (seg + 0.4)
            pre.append((_sub(path[0], _mul(t, rad[0] * math.sin(th))), rad[0] * math.cos(th)))
        pts = [p for p, _ in pre] + pts
        rr = [q for _, q in pre] + rr
    if ends[1]:
        t = _norm(_sub(path[-1], path[-2]))
        for k in range(1, seg + 1):
            th = 0.5 * math.pi * k / (seg + 0.4)
            pts.append(_add(path[-1], _mul(t, rad[-1] * math.sin(th))))
            rr.append(rad[-1] * math.cos(th))
    return _outward(_tube_md(pts, rr, sides))


_AXES = {"+z": lambda p: p, "-z": lambda p: (p[0], -p[1], -p[2]),
         "+y": lambda p: (p[0], p[2], -p[1]), "-y": lambda p: (p[0], -p[2], p[1]),
         "+x": lambda p: (p[2], p[1], -p[0]), "-x": lambda p: (-p[2], p[1], p[0])}


def _lathe(items, origin=(0.0, 0.0, 0.0), axis="+z", segs=24):
    """Solid of revolution: section (r, h) from the axis at the bottom to the
    axis at the top (corner tuples / arcs as for _profile, open), turned
    about +Z, then pointed along `axis` and moved to origin."""
    prof = _profile(items, closed=False, step=math.radians(30.0))
    md = _revolve_md(prof, segs)
    f = _AXES[axis]
    md.map(lambda p: _add(f(p), origin))
    return _outward(md)


def _bbox(md):
    xs, ys, zs = zip(*md.v)
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def _rect(rect_cm):
    """(x0, y0, x1, y1) or ((x0, y0), (x1, y1)) -> sorted floats."""
    if len(rect_cm) == 2:
        (x0, y0), (x1, y1) = rect_cm
    else:
        x0, y0, x1, y1 = rect_cm
    x0, x1 = sorted((float(x0), float(x1)))
    y0, y1 = sorted((float(y0), float(y1)))
    if x1 - x0 < 60.0 or y1 - y0 < 60.0:
        raise ValueError("room rectangle too small: %r" % (rect_cm,))
    return x0, y0, x1, y1


def _xyz(a, b, c):
    return (a, b, c)


# ===================================================================== cornice
CORNICE_H, CORNICE_D = 18.0, 14.0


def cornice_profile():
    """Closed (u, h) section: u off the wall, h down from the ceiling (cm).
    From the wall upwards: a 1.2 cm band, a 7 mm bead between quirks, a
    short fillet, a ledge, the 6 cm cove, a ledge and fillet, a 2 cm ovolo,
    the corona, a last ledge and a 2 cm cove into a 6 mm band on the ceiling.
    The back and top run 1 mm into wall and ceiling (no coplanar faces)."""
    e = 0.1
    return _profile([
        (-e, CORNICE_H, 0.0),                       # in the wall
        (1.2, 18.0, 0.12),                          # bottom band arris
        (1.2, 16.8, 0.04),                          # quirk under the bead
        _arc(1.2, 16.1, 0.7, 90.0, -90.0),          # bead (h grows downwards)
        (1.2, 15.4, 0.04),                          # quirk over the bead
        (1.2, 14.8, 0.1),
        (2.2, 14.8, 0.06),                          # ledge
        (2.2, 14.2, 0.0),
        _arc(8.2, 14.2, 6.0, 180.0, 270.0),         # the big cove
        (9.2, 8.2, 0.12),                           # ledge arris
        (9.2, 7.4, 0.04),                           # quirk
        _arc(9.2, 5.4, 2.0, 90.0, 0.0),             # ovolo
        (11.2, 3.2, 0.06),                          # corona, then a ledge
        (12.0, 3.2, 0.1),
        (12.0, 2.6, 0.0),
        _arc(14.0, 2.6, 2.0, 180.0, 270.0),         # top cove
        (CORNICE_D, 0.6, 0.12),                     # 6 mm band on the ceiling
        (CORNICE_D, -e, 0.0),                       # in the ceiling
        (-e, -e, 0.0),
    ])


def cornice_md(rect_cm, ceiling_z):
    """The cornice run round the wall faces rect_cm (scene cm), mitred at the
    four internal corners, its top on the ceiling at ceiling_z."""
    x0, y0, x1, y1 = _rect(rect_cm)
    cz = float(ceiling_z)
    prof = [(u, cz - h) for (u, h) in cornice_profile()]
    return _sweep([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], prof, _xyz, closed=True)


# ===================================================================== skirting
def skirting_profile(height=18.0, thick=2.5):
    """Closed (u, z) section of a tall moulded skirting board: flat face, a
    V quirk line 5 cm from the top, a small ledge, an ogee (ovolo over a
    cove) and a thin top band with a rounded top; back and bottom 1 mm into
    wall and floor."""
    h, t = float(height), float(thick)
    if h < 10.0 or t < 2.0:
        raise ValueError("skirting too small")
    e = 0.1
    zq, zo = h - 5.0, h - 3.6                       # quirk line, start of the ogee
    return _profile([
        (-e, -e, 0.0),
        (t, -e, 0.0),                               # front foot on the floor
        (t, zq, 0.03),
        (t - 0.22, zq + 0.14, 0.02),                # V quirk
        (t, zq + 0.28, 0.03),
        (t, zo, 0.06),
        (t - 0.2, zo, 0.03),                        # ledge
        _arc(t - 0.95, zo, 0.75, 0.0, 90.0),        # ovolo
        _arc(t - 0.95, zo + 1.4, 0.65, 270.0, 180.0),   # cove (together: the ogee)
        (t - 1.6, h, 0.45),                         # thin top band, rounded top
        (-e, h, 0.0),
    ])


_SIDE = {"s": 0, "south": 0, "e": 1, "east": 1, "n": 2, "north": 2, "w": 3, "west": 3}


def _perim_point(s, x0, y0, x1, y1):
    """Point at arc length s round the rectangle, counter-clockwise from
    (x0, y0): side 0 = s (y = y0), 1 = e (x = x1), 2 = n (y = y1), 3 = w."""
    W, D = x1 - x0, y1 - y0
    s %= 2.0 * (W + D)
    if s <= W:
        return (x0 + s, y0)
    s -= W
    if s <= D:
        return (x1, y0 + s)
    s -= D
    if s <= W:
        return (x1 - s, y1)
    return (x0, y1 - (s - W))


def _opening_span(op, x0, y0, x1, y1):
    """(side, a0, a1) -> perimeter interval. side: 's' / 'e' / 'n' / 'w' (or
    0-3, see _perim_point); a0, a1 run along that wall in scene cm (x on the
    s and n walls, y on the e and w walls)."""
    side, a0, a1 = op
    k = _SIDE[side.lower()] if isinstance(side, str) else int(side) % 4
    a0, a1 = sorted((float(a0), float(a1)))
    W, D = x1 - x0, y1 - y0
    if k in (0, 2):
        a0, a1 = max(a0, x0), min(a1, x1)
    else:
        a0, a1 = max(a0, y0), min(a1, y1)
    if a1 <= a0:
        return None
    if k == 0:
        return (a0 - x0, a1 - x0)
    if k == 1:
        return (W + a0 - y0, W + a1 - y0)
    if k == 2:
        return (W + D + x1 - a1, W + D + x1 - a0)
    return (2.0 * W + D + y1 - a1, 2.0 * W + D + y1 - a0)


def skirting_md(rect_cm, openings=(), height=18.0, thick=2.5):
    """Skirting round the wall faces rect_cm (scene cm): mitred at the
    corners, stopped square (with a closed end) at each opening. openings:
    [(side, a0, a1)] wall spans to leave clear - door architraves / plinth
    blocks, French windows - see _opening_span. Each run is its own closed
    shell, all in one mesh."""
    x0, y0, x1, y1 = _rect(rect_cm)
    prof = skirting_profile(height, thick)
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    W, D = x1 - x0, y1 - y0
    P = 2.0 * (W + D)
    spans = sorted(s for s in (_opening_span(o, x0, y0, x1, y1) for o in openings) if s)
    merged = []
    for a, b in spans:
        if merged and a <= merged[-1][1] + 1e-6:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    if not merged:
        return _sweep(corners, prof, _xyz, closed=True)
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
        md.merge(_sweep(path, prof, _xyz, closed=False))
    return md


# ================================================================ French window
WIN_FRAME = 7.0          # outer frame member width
WIN_DEPTH = 7.0          # frame depth, y = -3.5 .. 3.5
WIN_LAP = 1.0            # sash lip lapping over the frame face
WIN_GAP = 0.3            # shadow gap round the sash body
WIN_SASH = 6.2           # sash member width, lip edge to glass edge
WIN_TRANSOM = 9.0        # transom bar height
WIN_KICK = 13.0          # extra bottom rail on the leaves
WIN_BAR = 1.3            # half width of a glazing bar
Y_ROOM, Y_LIP, Y_EXT = -5.7, -3.7, 0.3      # sash room face, lip back, sash exterior face
Y_G0, Y_G1 = -1.6, -1.2                     # 4 mm glass


def _sticking():
    """Glass edge of a sash member or glazing bar, from its exterior face to
    its room face, as (depth into the member, y, fillet r): the putty rebate
    (1 cm, the glass bedded 0.5 mm off it), then the room-side ovolo with its
    quirk and fillet."""
    pts = [(1.0, Y_EXT, 0.12), (1.0, Y_G0 - 0.05, 0.04), (0.0, Y_G0 - 0.05, 0.08),
           (0.0, -4.5, 0.05), (0.2, -4.5, 0.03)]
    pts += _arc(1.1, -4.5, 0.9, 180.0, 270.0)       # ovolo
    pts += [(1.1, -5.4, 0.03), (1.1, Y_ROOM, 0.08)]
    return pts


def frame_profile():
    """Closed (u, y) section of the outer frame: u from the wall side in."""
    h = WIN_DEPTH / 2.0
    return _profile([(0.0, -h, 0.4), (WIN_FRAME, -h, 0.25), (WIN_FRAME, h, 0.2), (0.0, h, 0.2)])


def sash_profile():
    """Closed (u, y) section of a sash member: u from the lip edge (lapping
    WIN_LAP over the frame face, 2 mm proud of it) to the glass edge at
    WIN_SASH; the body sits in the frame opening behind a 3 mm shadow gap."""
    b = WIN_LAP + WIN_GAP
    pts = [(0.0, Y_ROOM, 0.3), (0.0, Y_LIP, 0.15), (b, Y_LIP, 0.1), (b, Y_EXT, 0.15)]
    pts += [(WIN_SASH - du, y, r) for (du, y, r) in _sticking()]
    return _profile(pts)


def bar_profile():
    """Closed (v, y) section of a glazing bar (v across it): ovolo and putty
    rebate on both sides, 2.6 cm wide on the room face."""
    st = _sticking()
    right = [(WIN_BAR - du, y, r) for (du, y, r) in st]
    left = [(-WIN_BAR + du, y, r) for (du, y, r) in reversed(st)]
    return _profile(right + left)


def kick_profile():
    """Closed (u, y) section of the extra bottom rail of a leaf: u up from
    1.1 cm inside the bottom sash member to its glass edge at WIN_KICK."""
    return _profile([(-1.1, Y_ROOM, 0.0), (-1.1, Y_EXT, 0.0)]
                    + [(WIN_KICK - du, y, r) for (du, y, r) in _sticking()])


def astragal_profile():
    """Closed (u, y) section of the cover strip on the meeting stiles: a
    flattened half-round bead (3.2 x 0.9 cm) on two 1 mm fillets."""
    face = [(1.6 * math.cos(math.radians(a)), Y_ROOM - 0.1 + 0.9 * math.sin(math.radians(a)), 0.0)
            for a in range(180, 361, 10)]
    return _profile([(-1.7, Y_ROOM + 0.05, 0.0), (-1.7, Y_ROOM - 0.1, 0.05), (-1.6, Y_ROOM - 0.1, 0.04)]
                    + face + [(1.6, Y_ROOM - 0.1, 0.04), (1.7, Y_ROOM - 0.1, 0.05), (1.7, Y_ROOM + 0.05, 0.0)])


def _xzy(a, b, c):
    """Path in the wall plane (a = x, b = z), section depth c = y."""
    return (a, c, b)


def french_window_parts(width=140.0, height=260.0, sill_z=0.0):
    """Two-leaf French balcony door with a fixed transom light. width x height
    is the outer frame (x = -width/2 .. width/2, z = sill_z .. sill_z +
    height), frame depth y = -3.5 .. 3.5; the sashes stand 2.2 cm proud of
    it on the room side (-Y) and the hardware a few cm more. Returns
    [(node name, material key, tile cm, _MD)]."""
    W, H, z0 = float(width), float(height), float(sill_z)
    F, L, S, K, T = WIN_FRAME, WIN_LAP, WIN_SASH, WIN_KICK, WIN_TRANSOM
    if W < 90.0 or H < 180.0:
        raise ValueError("French window too small: %r x %r" % (width, height))
    frame, sash, glass, hw = [], [], [], []
    frame.append(_sweep([(-W / 2, z0), (W / 2, z0), (W / 2, z0 + H), (-W / 2, z0 + H)],
                        frame_profile(), _xzy, closed=True))
    tl = max(30.0, 0.16 * H)                         # clear height of the transom light
    zt = z0 + H - F - tl - T                         # underside of the transom bar
    frame.append(_rbox_md(-W / 2 + F - 0.1, W / 2 - F + 0.1, -WIN_DEPTH / 2, WIN_DEPTH / 2, zt, zt + T, 0.25))
    sp, bp = sash_profile(), bar_profile()
    xi = W / 2 - F                                   # half width of the frame opening
    lz0, lz1 = z0 + F - L, zt + L                    # lip edges of the leaves
    for (a, b) in ((-xi - L, -0.15), (0.15, xi + L)):
        sash.append(_sweep([(a, lz0), (b, lz0), (b, lz1), (a, lz1)], sp, _xzy, closed=True))
        gx0, gx1 = a + S, b - S                      # glass edges of the stiles
        sash.append(_sweep([(gx0 - 1.1, lz0 + S), (gx1 + 1.1, lz0 + S)], kick_profile(), _xzy))
        gz0, gz1 = lz0 + S + K, lz1 - S
        hp = (gz1 - gz0 - 4.0 * WIN_BAR) / 3.0       # three equal panes
        lights, zlo = [], gz0
        for k in (1, 2):
            zc = gz0 + k * hp + (2 * k - 1) * WIN_BAR
            sash.append(_sweep([(gx0 - 1.1, zc), (gx1 + 1.1, zc)], bp, _xzy))
            lights.append((zlo, zc - WIN_BAR))
            zlo = zc + WIN_BAR
        lights.append((zlo, gz1))
        for (za, zb) in lights:
            glass.append(_rbox_md(gx0 - 0.75, gx1 + 0.75, Y_G0, Y_G1, za - 0.75, zb + 0.75, 0.05))
    # fixed transom sash, one vertical bar on the meeting line
    tz0, tz1 = zt + T - L, z0 + H - F + L
    sash.append(_sweep([(-xi - L, tz0), (xi + L, tz0), (xi + L, tz1), (-xi - L, tz1)], sp, _xzy, closed=True))
    gx0, gx1, gz0, gz1 = -xi - L + S, xi + L - S, tz0 + S, tz1 - S
    sash.append(_sweep([(0.0, gz0 - 1.1), (0.0, gz1 + 1.1)], bp, _xzy))
    for (xa, xb) in ((gx0, -WIN_BAR), (WIN_BAR, gx1)):
        glass.append(_rbox_md(xa - 0.75, xb + 0.75, Y_G0, Y_G1, gz0 - 0.75, gz1 + 0.75, 0.05))
    # astragal over the meeting gap, carried by the right (active) leaf
    sash.append(_sweep([(0.9, lz0 + 0.6), (0.9, lz1 - 0.6)], astragal_profile(), _xzy))
    # brass cremone: rod in two guides, gearbox plate, boss, lever hanging closed
    xr, yr = 3.9, Y_ROOM - 0.95
    zh = min(z0 + 105.0, lz0 + 0.55 * (lz1 - lz0))
    hw.append(_rod_md([(xr, yr, lz0 + 3.0), (xr, yr, lz1 - 3.0)], 0.5, 12))
    for zg in (lz0 + 25.0, lz1 - 25.0):
        hw.append(_rbox_md(xr - 0.8, xr + 0.8, Y_ROOM - 1.6, Y_ROOM + 0.05, zg - 0.7, zg + 0.7, 0.25))
    hw.append(_rbox_md(xr - 1.15, xr + 1.15, Y_ROOM - 1.7, Y_ROOM + 0.05, zh - 7.5, zh + 7.5, 0.45))
    hw.append(_lathe([(0.0, 0.0), (1.15, 0.0, 0.1), (1.15, 0.6, 0.2), (0.9, 1.5, 0.25), (0.0, 1.5)],
                     (xr, Y_ROOM - 1.65, zh), "-y", 24))
    p0, p1 = (xr, Y_ROOM - 2.8, zh), (xr, Y_ROOM - 5.0, zh)
    p2, p3 = (xr, Y_ROOM - 4.6, zh - 4.0), (xr, Y_ROOM - 3.3, zh - 12.0)
    path = [_bez(p0, p1, p2, p3, k / 14.0) for k in range(15)]
    hw.append(_rod_md(path, [0.75 - 0.2 * k / 14.0 for k in range(15)], 12, ends=(False, True)))
    # vase-ended fiche hinges on the outer edges of the leaves
    fiche = [(0.0, 0.0), (0.35, 0.0, 0.1), (0.55, 0.55, 0.2), (0.42, 1.05, 0.15), (0.72, 1.35, 0.1),
             (0.72, 10.65, 0.1), (0.42, 10.95, 0.15), (0.55, 11.45, 0.2), (0.35, 12.0, 0.1), (0.0, 12.0)]
    for sx in (-1.0, 1.0):
        for zk in (lz0 + 18.0, 0.5 * (lz0 + lz1) - 6.0, lz1 - 30.0):
            hw.append(_lathe(fiche, (sx * (xi + L + 0.6), -WIN_DEPTH / 2 - 0.7, zk), "+z", 16))
    return [("FrenchWin_Frame", "paint_white", JOINERY, _merge(frame)),
            ("FrenchWin_Sashes", "paint_white", JOINERY, _merge(sash)),
            ("FrenchWin_Glass", "glass", GLASS, _merge(glass)),
            ("FrenchWin_Hardware", "metal_brass", METAL, _merge(hw))]


# ===================================================================== radiator
RAD_TUBE = 1.25          # column tube radius
RAD_SPACING = 6.0        # front to back column centres
RAD_FOOT = 9.0           # floor to the underside of the sections
RAD_HUB = 1.6            # hub (nipple) radius


def radiator_parts(width=80.0, height=60.0):
    """Column radiator width x height overall, feet included (x = -width/2 ..
    width/2, z = 0 .. height, depth y = -4.25 .. 4.25): hairpin sections - two
    columns joined by round bends top and bottom - threaded on two domed hubs,
    cast feet under the second section from each end; a wheel valve (left)
    and a lockshield (right) on chrome tails and floor pipes with rosettes
    stand outside the width. Returns [(node name, material key, tile, _MD)]."""
    W, H = float(width), float(height)
    TR, br = RAD_TUBE, RAD_SPACING / 2.0
    if W < 20.0 or H < RAD_FOOT + 4.0 * br + 2.0 * TR + 4.0:
        raise ValueError("radiator too small: %r x %r" % (width, height))
    zt, zb = H - TR, RAD_FOOT + TR                   # centre lines of the top / bottom bends
    n = max(3, int(round(W / 4.6)))
    xs = [-W / 2 + TR + i * (W - 2 * TR) / (n - 1) for i in range(n)]
    body = []
    for x in xs:
        loop = []
        for k in range(9):                           # top bend, front column over to the back
            a = math.radians(180.0 - 22.5 * k)
            loop.append((x, br * math.cos(a), zt - br + br * math.sin(a)))
        for k in range(9):                           # bottom bend, back round to the front
            a = math.radians(-22.5 * k)
            loop.append((x, br * math.cos(a), zb + br + br * math.sin(a)))
        body.append(_outward(_tube_md(loop, TR, 16, closed=True, normals=[(1.0, 0.0, 0.0)] * len(loop))))
    for zh in (zt - 0.6, zb + 0.6):                  # hubs, plugged with domed ends
        body.append(_rod_md([(-W / 2 + RAD_HUB, 0.0, zh), (W / 2 - RAD_HUB, 0.0, zh)], RAD_HUB, 16, seg=5))
    foot = [(0.0, 0.0), (2.0, 0.0, 0.25), (2.0, 0.7, 0.3), (1.0, 2.4, 0.6), (0.85, zb + 0.9), (0.0, zb + 0.9)]
    for i in (1, n - 2):
        for y in (-2.2, 2.2):
            body.append(_lathe(foot, (xs[i], y, 0.0), "+z", 20))
    valves = []
    zv = zb + 0.6                                    # bottom hub axis
    for side in (-1.0, 1.0):
        xe = side * W / 2
        xv = xe + side * 5.0                         # valve body centre / floor pipe
        ax = "+x" if side > 0 else "-x"
        valves.append(_rod_md([(xe - side * 1.0, 0.0, zv), (xv, 0.0, zv)], 0.75, 12, ends=(False, False)))
        valves.append(_lathe([(0.0, 0.0), (1.3, 0.0, 0.12), (1.3, 1.6, 0.12), (0.0, 1.6)],
                             (xe + side * 0.4, 0.0, zv), ax, 6))            # hex union nut
        valves.append(_lathe([(0.0, 0.0), (1.15, 0.0, 0.15), (1.5, 0.6, 0.3), (1.5, 4.2, 0.3), (1.15, 4.8, 0.15),
                              (0.0, 4.8)], (xe + side * 2.6, 0.0, zv), ax, 20))
        valves.append(_rod_md([(xv, 0.0, zv), (xv, 0.0, -0.5)], 0.75, 12, ends=(False, False)))
        valves.append(_lathe([(0.0, 0.0), (2.4, 0.0, 0.1), (2.4, 0.25, 0.15), (1.2, 0.55, 0.2), (0.0, 0.55)],
                             (xv, 0.0, 0.0), "+z", 28))                     # floor rosette
        if side < 0:                                 # wheel valve
            valves.append(_lathe([(0.0, 0.0), (0.9, 0.0, 0.1), (0.9, 1.6, 0.1), (0.5, 1.9, 0.1), (0.5, 2.6),
                                  (0.0, 2.6)], (xv, 0.0, zv + 1.2), "+z", 16))
            valves.append(_lathe([(0.0, 0.0), (2.3, 0.0, 0.3), (2.4, 0.7, 0.35), (2.2, 1.3, 0.3), (0.8, 1.6, 0.4),
                                  (0.0, 1.6)], (xv, 0.0, zv + 3.6), "+z", 28))
        else:                                        # lockshield cap
            valves.append(_lathe([(0.0, 0.0), (1.1, 0.0, 0.1), (1.1, 1.4, 0.3), (0.8, 2.0, 0.4), (0.0, 2.1)],
                                 (xv, 0.0, zv + 1.2), "+z", 20))
    return [("Radiator_Body", "paint_white", 30.0, _merge(body)),
            ("Radiator_Valves", "metal_chrome", METAL, _merge(valves))]


# =================================================================== panel door
DOOR_T = 4.4             # leaf thickness
DOOR_GAP = 0.3           # gap round the leaf in its lining
DOOR_FLOOR = 0.8         # gap under the leaf
LINING_T = 2.5           # jamb lining board
CASING_W = 12.0          # architrave width
PLINTH_H = 22.0          # architrave plinth blocks (the skirting butts into them)


def casing_profile():
    """Closed (u, t) section of the architrave: u from its opening-side edge
    outwards, t off the wall face: rounded inner arris, a 7.9 cm face, a step
    up to the back band, whose ogee (ovolo over a cove) falls to a rounded
    outer lip; the back runs 1 mm into the plaster."""
    e = 0.1
    return _profile([
        (0.0, -e, 0.0),
        (0.0, 1.9, 0.4),                            # inner arris
        (7.9, 1.9, 0.04),
        (7.9, 2.6, 0.3),                            # step up to the back band
        (9.0, 2.6, 0.0),
        _arc(9.0, 1.9, 0.7, 90.0, 0.0),             # ovolo
        _arc(10.4, 1.9, 0.7, 180.0, 270.0),         # cove
        (11.6, 1.2, 0.0),
        (CASING_W, 1.2, 0.35),                      # outer lip
        (CASING_W, -e, 0.0),
    ])


def raised_panel_profile(yc):
    """Open (u, y) section of a raised-and-fielded panel round its edge, from
    the front field to the back field (u in from the panel edge, centre plane
    y = yc): a 2.5 mm shoulder, a 4.5 cm bevel down to the 1.6 cm border that
    runs 1 cm into the stile and rail grooves."""
    df, ds, db, uf, ub = 1.6, 1.35, 0.8, 8.6, 4.1
    return _profile([(uf + 0.2, yc - df, 0.0), (uf, yc - df, 0.1), (uf, yc - ds, 0.05), (ub, yc - db, 0.3),
                     (0.0, yc - db, 0.1), (0.0, yc + db, 0.1), (ub, yc + db, 0.3), (uf, yc + ds, 0.05),
                     (uf, yc + df, 0.1), (uf + 0.2, yc + df, 0.0)], closed=False)


def panel_moulding_profile():
    """Closed (u, w) section of the planted ogee round a panel: u from the
    stile / rail edge into the opening, w off the panel border; its top sits
    1 mm under the leaf face."""
    return _profile([
        (-0.1, -0.05, 0.0),
        (2.6, -0.05, 0.0),
        (2.6, 0.1, 0.05),
        _arc(2.6, 0.7, 0.6, 270.0, 180.0),          # cove
        _arc(1.4, 0.7, 0.6, 0.0, 90.0),             # ovolo
        (-0.1, 1.3, 0.0),
    ])


def _mirror_x(md):
    """Mirror a cage in X, keeping its faces outward (winding and corner UVs
    reversed together)."""
    md.v = [(-x, y, z) for x, y, z in md.v]
    md.f = [tuple(reversed(fc)) for fc in md.f]
    md.fuv = [tuple(reversed(uv)) if uv else uv for uv in md.fuv]
    return md


def panel_door_parts(width=90.0, height=240.0, wall=16.0, swing=0.0, hand="left"):
    """Single panelled door. width x height is the LEAF (x = -width/2 ..
    width/2, z = 0.8 .. 0.8 + height); the wall is `wall` cm thick, centred
    on y = 0, room side -Y. The jamb lining (2.5 cm, the wall's depth) leaves
    a 3 mm gap round the leaf: the structural opening is width + 5.6 by
    height + 3.6. Architraves 12 cm wide on both faces, on 22 cm plinth
    blocks: overall width + 24.6 wide and height + 13.7 high. swing opens the
    leaf into the room about its hinges (left edge), in degrees; hand
    "right" mirrors the whole door, hinges on the right edge (+X). Returns
    [(node name, material key, tile, _MD)]."""
    W, H, WT = float(width), float(height), float(wall)
    if W < 60.0 or H < 180.0 or WT < 8.0:
        raise ValueError("door too small: %r x %r in %r" % (width, height, wall))
    yl0 = -WT / 2.0 + 1.2                            # room face of the leaf
    yl1 = yl0 + DOOR_T
    yc = 0.5 * (yl0 + yl1)
    zl0, zl1 = DOOR_FLOOR, DOOR_FLOOR + H
    st = min(12.0, 0.14 * W)                         # stile width
    zlock = min(105.0, zl0 + 0.44 * H)               # lock rail centre = handle height
    zb1, zm0, zm1, zt0 = zl0 + 2.0 * st, zlock - 10.0, zlock + 10.0, zl1 - st
    if zm0 - zb1 < 20.0 or zt0 - zm1 < 20.0:
        raise ValueError("door too short for two panels")
    # ---- leaf: stiles, rails, raised panels, planted mouldings on both faces
    # 2 mm arrises (3 mm on the long edges): the planted mouldings, sunk 1 mm into
    # the stile and rail edges, then close against them without a gap
    leaf = [_rbox_md(-W / 2, -W / 2 + st, yl0, yl1, zl0, zl1, 0.2),
            _rbox_md(W / 2 - st, W / 2, yl0, yl1, zl0, zl1, 0.2)]
    for (za, zb) in ((zl0, zb1), (zm0, zm1), (zt0, zl1)):
        leaf.append(_rbox_md(-W / 2 + st - 0.05, W / 2 - st + 0.05, yl0, yl1, za, zb, 0.2))
    ox0, ox1 = -W / 2 + st, W / 2 - st
    mp = panel_moulding_profile()
    for (oz0, oz1) in ((zb1, zm0), (zm1, zt0)):
        leaf.append(_sweep([(ox0 - 1.0, oz0 - 1.0), (ox1 + 1.0, oz0 - 1.0), (ox1 + 1.0, oz1 + 1.0),
                            (ox0 - 1.0, oz1 + 1.0)], raised_panel_profile(yc), _xzy, closed=True,
                           prof_closed=False))
        for sgn in (-1.0, 1.0):
            leaf.append(_sweep([(ox0, oz0), (ox1, oz0), (ox1, oz1), (ox0, oz1)],
                               [(u, yc + sgn * (0.8 + w)) for (u, w) in mp], _xzy, closed=True))
    # ---- brass: lever roses + levers and escutcheons on both faces, hinge knuckles
    hw = []
    xh = W / 2 - 6.0                                 # 6 cm backset
    for sgn, yf, ax in ((-1.0, yl0, "-y"), (1.0, yl1, "+y")):
        hw.append(_lathe([(0.0, -0.05), (2.6, -0.05, 0.1), (2.6, 0.35, 0.12), (2.1, 0.85, 0.35), (1.2, 1.0, 0.3),
                          (0.0, 1.0)], (xh, yf, zlock), ax, 32))
        p0, p1 = (xh, yf + sgn * 0.6, zlock), (xh, yf + sgn * 5.4, zlock)
        p2, p3 = (xh - 3.0, yf + sgn * 5.8, zlock), (xh - 12.5, yf + sgn * 5.6, zlock - 0.5)
        path = [_bez(p0, p1, p2, p3, k / 15.0) for k in range(16)]
        hw.append(_rod_md(path, [0.9 - 0.15 * k / 15.0 for k in range(16)], 12, ends=(False, True)))
        hw.append(_lathe([(0.0, -0.05), (1.5, -0.05, 0.1), (1.5, 0.25, 0.1), (1.2, 0.45, 0.2), (0.0, 0.45)],
                         (xh, yf, zlock - 9.0), ax, 24))
    hx, hy = -W / 2 - 0.15, yl0                      # hinge axis
    knuckle = [(0.0, 0.0), (0.45, 0.0, 0.1), (0.6, 0.45, 0.15), (0.72, 0.8, 0.1), (0.72, 10.2, 0.1),
               (0.6, 10.55, 0.15), (0.45, 11.0, 0.1), (0.0, 11.0)]
    for zk in (zl0 + 25.0, zl0 + 0.5 * H, zl1 - 25.0):
        hw.append(_lathe(knuckle, (hx, hy, zk - 5.5), "+z", 20))
    if swing:
        th = -math.radians(float(swing))             # positive swing opens towards -Y (the room)
        c, s = math.cos(th), math.sin(th)

        def rot(p):
            dx, dy = p[0] - hx, p[1] - hy
            return (hx + dx * c - dy * s, hy + dx * s + dy * c, p[2])
        for m in leaf + hw:
            m.map(rot)
    # ---- jamb lining with its stop bead, architraves on plinth blocks
    gx, gz = W / 2 + DOOR_GAP, zl1 + DOOR_GAP
    upath = [(-gx, 0.0), (-gx, gz), (gx, gz), (gx, 0.0)]        # left of travel = into the wall
    lining = [_sweep(upath, _profile([(0.0, -WT / 2, 0.25), (LINING_T, -WT / 2, 0.0), (LINING_T, WT / 2, 0.0),
                                      (0.0, WT / 2, 0.25)]), _xzy)]
    ys0 = yl1 + 0.15
    lining.append(_sweep(upath, _profile([(-1.3, ys0, 0.25), (0.1, ys0, 0.0), (0.1, ys0 + 3.8, 0.0),
                                          (-1.3, ys0 + 3.8, 0.25)]), _xzy))
    cx, cz = gx + 0.6, gz + 0.6                      # 6 mm margin on the lining
    cpath = [(-cx, PLINTH_H - 0.1), (-cx, cz), (cx, cz), (cx, PLINTH_H - 0.1)]
    cp = casing_profile()
    casing = []
    for sgn in (-1.0, 1.0):
        casing.append(_sweep(cpath, [(u, sgn * (WT / 2 + t)) for (u, t) in cp], _xzy))
        for side in (-1.0, 1.0):
            casing.append(_rbox_md(side * (cx - 0.3), side * (cx + CASING_W + 0.3), sgn * (WT / 2 - 0.1),
                                   sgn * (WT / 2 + 3.0), 0.0, PLINTH_H, 0.35))
    parts = [("PanelDoor_Leaf", "paint_white", JOINERY, _merge(leaf)),
             ("PanelDoor_Lining", "paint_white", JOINERY, _merge(lining)),
             ("PanelDoor_Casing", "paint_white", JOINERY, _merge(casing)),
             ("PanelDoor_Hardware", "metal_brass", METAL, _merge(hw))]
    if hand == "right":
        parts = [(n, k, t, _mirror_x(md)) for n, k, t, md in parts]
    return parts


# ================================================================ Max wrappers
def _autosmooth(node, deg=40.0):
    """Smooth modifier, auto at deg: round sections shade smooth, the flats
    and mitres stay crisp (_build puts every face in smoothing group 1)."""
    try:
        sm = rt.Smooth()
        kit.setp(sm, "autoSmooth", True)
        kit.setp(sm, "threshold", float(deg))
        rt.addModifier(node, sm)
    except Exception:
        pass
    return node


def _group(name, parts):
    nodes = []
    for pname, key, tile, md in parts:
        node = _build(md, pname)
        _autosmooth(node)
        nodes.append(kit.part(node, key, tile))
    return kit.group(name, nodes)


def build_cornice(rect_cm, ceiling_z):
    """Plaster crown cornice round the room whose wall faces are rect_cm
    ((x0, y0, x1, y1), scene cm), its top on the ceiling at ceiling_z. The
    geometry is already in place: leave the returned group at the origin."""
    return _group("Cornice", [("Cornice", "wall_paint", PLASTER, cornice_md(rect_cm, ceiling_z))])


def build_skirting(rect_cm, openings=(), height=18.0, thick=2.5):
    """Skirting round the wall faces rect_cm, stopped at openings [(side,
    a0, a1)] with side 's' (y = y0), 'e' (x = x1), 'n' (y = y1) or 'w'
    (x = x0) and a0..a1 the span along that wall (scene cm). Already in
    place: leave the group at the origin."""
    return _group("Skirting", [("Skirting", "paint_white", JOINERY, skirting_md(rect_cm, openings, height, thick))])


def build_french_window(width=140.0, height=260.0, sill_z=0.0):
    """Two-leaf French door with a transom, frame width x height from sill_z;
    origin at the frame centre on the floor, frame depth centred on y = 0,
    room side -Y: kit.place it in the wall opening."""
    return _group("FrenchWindow", french_window_parts(width, height, sill_z))


def build_radiator(width=80.0, height=60.0):
    """Column radiator width x height on its feet, origin under its centre,
    front -Y (back 4.25 cm behind the origin: keep it ~5 cm off the wall)."""
    return _group("Radiator", radiator_parts(width, height))


def build_panel_door(width=90.0, height=240.0, wall=16.0, swing=0.0, hand="left"):
    """Panelled door, leaf width x height, lining and architraves for a wall
    `wall` cm thick centred on y = 0 (room side -Y), origin at the centre of
    the opening on the floor; swing opens the leaf into the room (degrees);
    hand "right" hinges it on the +X edge."""
    return _group("PanelDoor", panel_door_parts(width, height, wall, swing, hand))


def preview():
    """Every piece side by side: cornice and skirting round a 3 x 2.5 m
    test room, then the French window, radiator and door (opened 30 deg)."""
    build_cornice((-150.0, -125.0, 150.0, 125.0), 330.0)
    build_skirting((-150.0, -125.0, 150.0, 125.0), [("s", -60.0, 60.0)])
    kit.place(build_french_window(), 300.0, 0.0)
    kit.place(build_radiator(), 450.0, 0.0)
    kit.place(build_panel_door(swing=30.0), 600.0, 0.0)
