"""Bathroom fixtures for the Japandi apartment test scene (3ds Max 2026 + V-Ray 7, pymxs).

Conventions (kit.py): centimetres, Z up, each build_*() builds at the local origin with its
FRONT facing -Y and the floor at z = 0, registers every visible node through kit.part() and
returns kit.group().  The XY footprint is centred on the origin, so wall-hung pieces have
their wall contact plane at y = +depth/2 (the shower also has a side wall at x = -45 for
hand="left", x = +45 for hand="right").

Ceramics, soft goods and frames are generalised revolves / lofts: rings of points
(superellipse, D-shaped, rounded-rectangle or spiral cross-sections) stitched into an
Editable Mesh whose quad diagonals are hidden, so TurboSmooth subdivides real quads.
Hard goods are ChamferBox / ChamferCyl with real fillets.

Close-up details worth knowing about: the WC pan stands on a silicone bead (paint_white), its
lid hangs on chrome hinge barrels on deck plinths, and the flush plate is a framed plate with
two crowned buttons in shadow gaps; the mixer has a turned spout collar, a recessed aerator and a
tapered lever paddle; the rail towel is folded in thirds (selvedge step on its right edge, flat
hems and dobby bands thinner than the pile); the rolled hand towel winds unevenly from a tight
core curl with its hem set down at the front.

Preview helpers: MF_BATH_ONLY="toilet,vanity,mirror,shower,rail,decor" previews a subset,
MF_BATH_STACK=1 hangs the mirror above the vanity.
"""
import math
import os

from pymxs import runtime as rt

import kit

TAU = 2.0 * math.pi


# =============================================================================
# mesh helpers
# =============================================================================
def _mesh(name, verts, quads=(), tris=(), sgs=None):
    """Editable Mesh from quads (CCW seen from outside) + tris. Quad diagonals are hidden so
    TurboSmooth / Edit Poly see quads. sgs: smoothing group per face (quads count twice)."""
    faces = []
    for a, b, c, d in quads:
        faces.append((a, b, c))
        faces.append((a, c, d))
    faces.extend(tris)
    vs = ",".join("[%.4f,%.4f,%.4f]" % (v[0], v[1], v[2]) for v in verts)
    fs = ",".join("[%d,%d,%d]" % (f[0] + 1, f[1] + 1, f[2] + 1) for f in faces)
    if sgs:
        sg = ("sgl = #(%s)\nfor f = 1 to m.numfaces do setFaceSmoothGroup m f sgl[f]\n"
              % ",".join(str(int(s)) for s in sgs))
    else:
        sg = "for f = 1 to m.numfaces do setFaceSmoothGroup m f 1\n"
    ms = ('(m = mesh name:"%s" vertices:#(%s) faces:#(%s)\n%s'
          "for q = 1 to %d do (setEdgeVis m (2*q-1) 3 false; setEdgeVis m (2*q) 1 false)\n"
          "update m\nm)" % (name, vs, fs, sg, len(quads)))
    return rt.execute(ms)


def _centroid(ring):
    n = float(len(ring))
    return (sum(p[0] for p in ring) / n, sum(p[1] for p in ring) / n, sum(p[2] for p in ring) / n)


def _loft(name, rings, wrap=False, cap0=False, cap1=False, flip=False, sg=None):
    """Stitch equal-length closed rings into quads (a generalised revolve). wrap joins the last
    ring back to the first (swept tube); cap0 / cap1 fan the first / last ring to its centroid
    (or to the point given). sg = (quad_sg, cap0_sg, cap1_sg)."""
    n = len(rings[0])
    nr = len(rings)
    verts = [p for r in rings for p in r]
    quads = []
    for i in range(nr if wrap else nr - 1):
        i2 = (i + 1) % nr
        for j in range(n):
            j2 = (j + 1) % n
            quads.append((i * n + j, i * n + j2, i2 * n + j2, i2 * n + j))
    t0, t1 = [], []
    if cap0:
        verts.append(cap0 if isinstance(cap0, tuple) else _centroid(rings[0]))
        c = len(verts) - 1
        t0 = [(c, (j + 1) % n, j) for j in range(n)]
    if cap1:
        verts.append(cap1 if isinstance(cap1, tuple) else _centroid(rings[-1]))
        c = len(verts) - 1
        b = (nr - 1) * n
        t1 = [(c, b + j, b + (j + 1) % n) for j in range(n)]
    if flip:
        quads = [(a, d, cc, b) for a, b, cc, d in quads]
        t0 = [(a, cc, b) for a, b, cc in t0]
        t1 = [(a, cc, b) for a, b, cc in t1]
    sgs = None
    if sg:
        sgs = [sg[0]] * (2 * len(quads)) + [sg[1]] * len(t0) + [sg[2]] * len(t1)
    return _mesh(name, verts, quads, t0 + t1, sgs)


def _ts(node, it=1):
    t = rt.TurboSmooth()
    t.iterations = it
    rt.addModifier(node, t)
    return node


# ---- ring generators ---------------------------------------------------------
def _se(t, a, b, n):
    c, s = math.cos(t), math.sin(t)
    return (a * math.copysign(abs(c) ** (2.0 / n), c), b * math.copysign(abs(s) ** (2.0 / n), s))


def _oval(a, b, n, z, segs=64, cx=0.0, cy=0.0):
    return [(cx + x, cy + y, z) for x, y in (_se(TAU * j / segs, a, b, n) for j in range(segs))]


def _circle(r, z, segs=48, cx=0.0, cy=0.0):
    return [(cx + r * math.cos(TAU * j / segs), cy + r * math.sin(TAU * j / segs), z) for j in range(segs)]


NF, NS, NC, NB = 36, 4, 6, 8      # D-ring samples: front arc, side, corner, back edge (64 total)


def _dring(a, cy, bf, bb, rc, nf, z, cx=0.0):
    """CCW plan outline of a WC pan / seat: an egg-shaped front (half superellipse, exponent nf,
    reaching bf from the widest line y = cy toward -Y) and a flat back (straight sides, corner
    arcs of radius rc, back edge at y = cy + bb). Same sampling for every ring -> clean lofts."""
    rc = min(rc, a - 0.05, bb - 0.05)
    pts = []
    yc = cy + bb - rc
    for k in range(NS):
        pts.append((cx + a, cy + (yc - cy) * k / NS))
    for k in range(NC):
        t = 0.5 * math.pi * k / NC
        pts.append((cx + a - rc + rc * math.cos(t), yc + rc * math.sin(t)))
    for k in range(NB):
        pts.append((cx + (a - rc) * (1.0 - 2.0 * k / NB), cy + bb))
    for k in range(NC):
        t = 0.5 * math.pi * (1.0 + float(k) / NC)
        pts.append((cx - (a - rc) + rc * math.cos(t), yc + rc * math.sin(t)))
    for k in range(NS):
        pts.append((cx - a, yc + (cy - yc) * k / NS))
    for k in range(NF):
        x, y = _se(math.pi + math.pi * k / NF, a, bf, nf)
        pts.append((cx + x, cy + y))
    return [(x, y, z) for x, y in pts]


def _rrect(hw, hh, r, nc=8, ns=3):
    """CCW rounded rectangle (2D, u right / w up), starting at the bottom of the right side."""
    r = max(0.02, min(r, hw - 0.01, hh - 0.01))
    cx, cy = hw - r, hh - r
    pts = []

    def side(p0, p1):
        for k in range(ns):
            f = float(k) / ns
            pts.append((p0[0] + (p1[0] - p0[0]) * f, p0[1] + (p1[1] - p0[1]) * f))

    def arc(ox, oy, a0):
        for k in range(nc):
            t = a0 + 0.5 * math.pi * k / nc
            pts.append((ox + r * math.cos(t), oy + r * math.sin(t)))

    side((hw, -cy), (hw, cy))
    arc(cx, cy, 0.0)
    side((cx, hh), (-cx, hh))
    arc(-cx, cy, 0.5 * math.pi)
    side((-hw, cy), (-hw, -cy))
    arc(-cx, -cy, math.pi)
    side((-cx, -hh), (cx, -hh))
    arc(cx, -cy, 1.5 * math.pi)
    return pts


def _blend(r1, r2, t, z=None):
    return [(p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t,
             (p[2] + (q[2] - p[2]) * t) if z is None else z) for p, q in zip(r1, r2)]


def _toward(ring, c, d=None, f=None, z=None):
    """Move each point toward centre c (xy) by distance d, or scale its offset by f."""
    out = []
    for p in ring:
        vx, vy = p[0] - c[0], p[1] - c[1]
        if f is None:
            ln = math.hypot(vx, vy)
            k = max(ln - d, 0.0) / ln if ln > 1e-9 else 0.0
        else:
            k = f
        out.append((c[0] + vx * k, c[1] + vy * k, p[2] if z is None else z))
    return out


def _between(inner, outer, prof, z0):
    """Cross-section rings between two outlines. prof = [(anchor, d, h)]: anchor 'i' -> d cm
    from the inner outline toward the outer, 'o' -> d cm from the outer one, 'f' -> fraction."""
    rings = []
    for anchor, d, h in prof:
        ring = []
        for p, q in zip(inner, outer):
            w = math.hypot(q[0] - p[0], q[1] - p[1]) or 1.0
            t = d / w if anchor == "i" else (1.0 - d / w if anchor == "o" else d)
            ring.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t, z0 + h))
        rings.append(ring)
    return rings


def _lathe(name, prof, segs=48, cx=0.0, cy=0.0, z0=0.0):
    """Revolve [(r, z)] about a vertical axis; r == 0 at either end becomes a pole cap.
    List the profile bottom -> outside -> rim -> inside so normals face out of the material."""
    cap0 = prof[0][0] <= 1e-6
    cap1 = prof[-1][0] <= 1e-6
    body = prof[(1 if cap0 else 0):(len(prof) - 1 if cap1 else len(prof))]
    rings = [_circle(r, z0 + z, segs, cx, cy) for r, z in body]
    return _loft(name, rings, cap0=(cx, cy, z0 + prof[0][1]) if cap0 else False,
                 cap1=(cx, cy, z0 + prof[-1][1]) if cap1 else False)


def _sheet(name, mid, thick, xs, taper, disp=None, xform=None):
    """Cloth sheet swept along X. mid = cross-section mid-line [(y, z)] (open path);
    thick(i, x) = thickness at mid point i; taper(x) = side-edge thickness factor;
    disp(i, x) -> (dy, dz) or (dx, dy, dz) moves the mid-line (folds, skew); xform(x, y, z) ->
    final point. Each X ring is a closed loop (outer face, rounded tip, inner face, rounded tip);
    both X ends are closed with strips so the hems read as soft rounded edges after TurboSmooth."""
    m = len(mid)
    rings, nrm0 = [], None
    for x in xs:
        pts, dxs = [], []
        for i, (y, z) in enumerate(mid):
            d = disp(i, x) if disp else (0.0, 0.0)
            dx, dy, dz = d if len(d) == 3 else (0.0, d[0], d[1])
            pts.append((y + dy, z + dz))
            dxs.append(dx)
        nrm = []
        for i in range(m):
            a, b = pts[max(i - 1, 0)], pts[min(i + 1, m - 1)]
            ty, tz = b[0] - a[0], b[1] - a[1]
            ln = math.hypot(ty, tz) or 1.0
            nrm.append((-tz / ln, ty / ln))
        if nrm0 is None:
            nrm0 = nrm
        f = taper(x)
        th = [thick(i, x) * f * 0.5 for i in range(m)]
        outer = [(pts[i][0] + nrm[i][0] * th[i], pts[i][1] + nrm[i][1] * th[i]) for i in range(m)]
        inner = [(pts[i][0] - nrm[i][0] * th[i], pts[i][1] - nrm[i][1] * th[i]) for i in range(m)]

        def tip(i, j):
            ty, tz = pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]
            ln = math.hypot(ty, tz) or 1.0
            e = 0.85 * th[i]
            return (pts[i][0] + ty / ln * e, pts[i][1] + tz / ln * e)

        loop = outer + [tip(m - 1, m - 2)] + inner[::-1] + [tip(0, 1)]
        ldx = dxs + [dxs[-1]] + dxs[::-1] + [dxs[0]]
        ring = [(x + ddx, p[0], p[1]) for p, ddx in zip(loop, ldx)]
        if xform:
            ring = [xform(*p) for p in ring]
        rings.append(ring)
    L = 2 * m + 2
    nr = len(rings)
    verts = [p for r in rings for p in r]
    quads = []
    for i in range(nr - 1):
        for j in range(L):
            j2 = (j + 1) % L
            quads.append((i * L + j, i * L + j2, (i + 1) * L + j2, (i + 1) * L + j))

    def qn(q):
        a, b, c = verts[q[0]], verts[q[1]], verts[q[2]]
        u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        return (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])

    jm = m // 2
    n_ = qn(quads[jm])
    if n_[1] * nrm0[jm][0] + n_[2] * nrm0[jm][1] < 0:          # outer face must face outward
        quads = [(a, d, c, b) for a, b, c, d in quads]
    caps = []
    for ri, sign in ((0, -1.0), (nr - 1, 1.0)):
        b0 = ri * L
        cq = [(b0 + k, b0 + k + 1, b0 + 2 * m - k - 1, b0 + 2 * m - k) for k in range(m - 1)]
        ct = [(b0 + m - 1, b0 + m, b0 + m + 1), (b0 + 2 * m, b0 + 2 * m + 1, b0)]
        if qn(cq[m // 2])[0] * sign < 0:
            cq = [(a, d, c, b) for a, b, c, d in cq]
            ct = [(a, c, b) for a, b, c in ct]
        quads.extend(cq)
        caps.extend(ct)
    return _mesh(name, verts, quads, caps)


def _norm(v):
    ln = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    return (v[0] / ln, v[1] / ln, v[2] / ln)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _orient(node, axis, pos):
    """Point the node's local +Z along axis with its pivot at pos (right-handed frame)."""
    zz = _norm(axis)
    h = (0.0, 0.0, 1.0) if abs(zz[2]) < 0.9 else (1.0, 0.0, 0.0)
    xx = _norm(_cross(h, zz))
    yy = _cross(zz, xx)
    node.transform = rt.matrix3(rt.Point3(*xx), rt.Point3(*yy), rt.Point3(*zz), rt.Point3(*pos))
    return node


def _ccyl(r, h, fillet, p0, axis=(0.0, 0.0, 1.0), sides=32, fsegs=3, caps=1):
    """ChamferCyl of radius r and length h starting at p0 and running along axis."""
    c = rt.ChamferCyl(radius=r, height=h, fillet=min(fillet, r * 0.95, h * 0.49), sides=sides)
    kit.setp(c, "Fillet_Segments", fsegs)
    kit.setp(c, "cap_segments", caps)
    kit.setp(c, "Height_Segments", 1)
    kit.setp(c, "Smooth_On", True)
    kit.setp(c, "mapcoords", True)
    return _orient(c, axis, p0)


def _pins(centres, r, h, z_top, sides=8, name="pins"):
    """Many small downward pins (rain-head nozzles) as one mesh: prisms from z_top down by h."""
    verts, quads, tris = [], [], []
    for cx, cy in centres:
        b = len(verts)
        for j in range(sides):
            a = TAU * j / sides
            verts.append((cx + r * math.cos(a), cy + r * math.sin(a), z_top))
        for j in range(sides):
            a = TAU * j / sides
            verts.append((cx + 0.8 * r * math.cos(a), cy + 0.8 * r * math.sin(a), z_top - h))
        verts.append((cx, cy, z_top - h - 0.01))
        for j in range(sides):
            j2 = (j + 1) % sides
            quads.append((b + j, b + sides + j, b + sides + j2, b + j2))
            tris.append((b + 2 * sides, b + sides + j2, b + sides + j))
    return _mesh(name, verts, quads, tris)


def _bbox(nodes):
    lo, hi = [1e9] * 3, [-1e9] * 3
    for n in nodes:
        bb = rt.nodeGetBoundingBox(n, rt.matrix3(1))
        for i, v in enumerate((bb[0].x, bb[0].y, bb[0].z)):
            lo[i] = min(lo[i], v)
        for i, v in enumerate((bb[1].x, bb[1].y, bb[1].z)):
            hi[i] = max(hi[i], v)
    return lo, hi


def _finish(name, nodes):
    """Centre the XY footprint on the origin (floor stays at z = 0) and group."""
    lo, hi = _bbox(nodes)
    dx, dy = -(lo[0] + hi[0]) / 2.0, -(lo[1] + hi[1]) / 2.0
    for n in nodes:
        p = n.pos
        n.pos = rt.Point3(p.x + dx, p.y + dy, p.z)
    return kit.group(name, nodes)


# =============================================================================
# WC
# =============================================================================
def build_toilet(box_w=60.0, box_h=110.0, box_d=20.0):
    """Floor-standing back-to-wall WC: rimless pan 36 W x 55 D x 40 H, slim seat with a closed
    lid on chrome hinges, standing against a boxed concealed-cistern duct (painted, marble
    ledge) carrying a chrome dual-flush plate at 97 cm."""
    nodes = []
    Z = 40.0          # pan deck height
    CY = -21.0        # widest line of the pan, measured from the pan back (y = 0)

    # ---- pan: outer shell (z, half width, front reach from the back) ... a toe recess at the
    #      floor (the glaze turns under), then a full sculpted front that leans out to the rim
    shell = [(0.0, 15.95, 48.9), (0.3, 16.0, 49.05), (1.1, 16.2, 49.55), (3.6, 16.6, 50.55),
             (8.0, 17.02, 51.65), (14.5, 17.4, 52.8), (21.5, 17.7, 53.75), (28.5, 17.9, 54.45),
             (34.5, 18.0, 54.9), (37.3, 18.0, 55.0), (38.8, 17.87, 54.9), (39.6, 17.5, 54.55),
             (40.0, 16.9, 53.95)]
    rings = [_dring(a, CY, f + CY, -CY, 3.0, 2.6, z) for z, a, f in shell]

    def opening(d, z):
        return _dring(12.2 + d, -35.6, 15.8 + d, 15.0 + d, 9.6 + d, 2.35, z)

    top, inner_edge = rings[-1], opening(1.1, Z)
    rings += [_blend(top, inner_edge, t, Z) for t in (0.16, 0.5, 0.84)]          # flat deck
    rings += [inner_edge, opening(0.35, Z - 0.12), opening(0.0, Z - 0.65)]        # rounded lip
    bowl = [(37.6, 11.95, 15.45, 14.7, -35.5), (34.8, 11.3, 14.4, 14.0, -35.1),
            (31.5, 10.2, 12.5, 12.9, -34.2), (28.5, 8.9, 10.4, 11.5, -32.9),
            (26.0, 7.6, 8.5, 10.0, -31.6), (23.5, 6.2, 6.7, 8.2, -30.2),
            (21.0, 4.7, 5.0, 6.1, -28.9), (19.0, 3.2, 3.4, 4.1, -28.0)]
    rings += [_dring(a, cy, bf, bb, 0.88 * min(a, bb), 2.2, z) for z, a, bf, bb, cy in bowl]
    pan = _ts(_loft("WC_pan", rings, cap1=True), 1)
    nodes.append(kit.part(pan, "ceramic_white", 40))
    # sanitary silicone bead where the pan meets the floor: a finger-smoothed concave fillet
    # (3 mm out on the floor, 3 mm up the glaze) that kills the razor floor line
    z0, a0, f0 = shell[0]
    z1, a1, f1 = shell[1]
    bead = []
    for o, z in ((0.34, 0.0), (0.16, 0.05), (0.07, 0.13), (0.02, 0.23), (-0.04, 0.34)):
        t = z / z1
        a, f = a0 + (a1 - a0) * t, f0 + (f1 - f0) * t
        bead.append(_dring(a + o, CY, f + CY + o, -CY + o, 3.0 + o, 2.6, z))
    nodes.append(kit.part(_ts(_loft("WC_silicone", bead), 1), "paint_white", 30))

    # ---- slim seat (ring) on four rubber buffers
    seat_z = Z + 0.3
    s_out = _dring(16.75, CY, 53.8 + CY, 10.0, 4.5, 2.6, 0.0)        # back edge at y = -11
    s_in = _dring(11.0, -36.3, 14.5, 13.2, 9.6, 2.35, 0.0)
    prof = [("i", 0.0, 0.45), ("i", 0.0, 1.05), ("i", 0.12, 1.42), ("i", 0.5, 1.6),
            ("f", 0.5, 1.66), ("o", 0.5, 1.6), ("o", 0.12, 1.42), ("o", 0.0, 1.05),
            ("o", 0.0, 0.45), ("o", 0.12, 0.08), ("o", 0.5, 0.0), ("f", 0.5, 0.0),
            ("i", 0.5, 0.0), ("i", 0.12, 0.08)]
    seat = _ts(_loft("WC_seat", _between(s_in, s_out, prof, seat_z), wrap=True, flip=True), 1)
    nodes.append(kit.part(seat, "ceramic_white", 40))
    # buffers sit where both the seat ring and the flat deck are (the front pair used to hang
    # over the bowl opening)
    for bx, by in ((13.8, -26.0), (-13.8, -26.0), (13.6, -42.5), (-13.6, -42.5)):
        nodes.append(kit.part(_ccyl(0.6, 0.32, 0.1, (bx, by, Z - 0.02), sides=16), "rubber", 20))

    # ---- lid (closed), slightly crowned, resting on the seat
    lid_z = seat_z + 1.68
    c = _centroid(s_out)
    lid_prof = [("f", 0.45, 0.0), ("d", 1.2, 0.0), ("d", 0.3, 0.04), ("d", 0.05, 0.25),
                ("d", 0.0, 0.6), ("d", 0.0, 0.95), ("d", 0.15, 1.25), ("d", 0.6, 1.42),
                ("d", 1.6, 1.52), ("f", 0.55, 1.62), ("f", 0.25, 1.66), ("f", 0.1, 1.67)]
    lid_rings = []
    for kind, v, h in lid_prof:
        r = _toward(s_out, c, f=v) if kind == "f" else _toward(s_out, c, d=v)
        lid_rings.append([(p[0], p[1], lid_z + h) for p in r])
    lid = _ts(_loft("WC_lid", lid_rings, cap0=(c[0], c[1], lid_z), cap1=(c[0], c[1], lid_z + 1.675)), 1)
    nodes.append(kit.part(lid, "ceramic_white", 40))

    # ---- hinges: chrome barrels with their axis on the seat / lid joint, nestled 2 mm into the
    #      groove between the seat's top arris and the lid's bottom arris (so both read as hung
    #      on them), each standing on a rounded chrome plinth bolted to the deck
    hz = seat_z + 1.67
    for hx in (-8.0, 8.0):
        nodes.append(kit.part(_ccyl(1.15, 3.3, 0.42, (hx - 1.65, -10.05, hz), (1, 0, 0), sides=28),
                              "metal_chrome", 20))
        nodes.append(kit.part(kit.cbox(2.5, 2.2, hz - Z, 0.5, hx, -9.75, Z - 0.05, 3), "metal_chrome", 20))
        for sx in (-1.0, 1.0):                     # end caps: a hair proud, so the barrel reads turned
            nodes.append(kit.part(_ccyl(0.82, 0.12, 0.05, (hx + sx * 1.62, -10.05, hz), (sx, 0, 0), sides=24),
                                  "metal_chrome", 20))

    # ---- boxed concealed cistern + marble ledge + flush plate
    y0 = 0.05                                      # box front face (pan back is y = 0)
    nodes.append(kit.part(kit.cbox(box_w, box_d, box_h, 0.3, 0.0, y0 + box_d / 2.0, 0.0), "paint_white", 100))
    nodes.append(kit.part(kit.cbox(box_w, box_d + 1.2, 2.0, 0.2, 0.0, y0 + box_d / 2.0 - 0.6, box_h),
                          "stone_worktop", 120))
    pz = box_h - 13.0                              # plate centre height (97 cm)
    for n in _flush_plate(0.0, y0, pz):
        nodes.append(kit.part(n, "metal_chrome", 25))
    return _finish("WC_BackToWall", nodes)


def _flush_plate(cx, y_wall, cz, W=24.6, H=16.4):
    """Dual-flush plate (W x H, 8 mm proud): a slim frame with rounded arrises, a recessed back
    plate in its opening and two gently crowned buttons (big / small) set in with 1-2 mm
    shadow gaps, so the buttons read as separate parts and do not reflect like flat mirrors."""
    out = []
    bw = 0.9                                       # frame border
    hw, hh = W / 2.0 - bw / 2.0, H / 2.0 - bw / 2.0
    prof = [(0.45, 0.1), (0.45, 0.6), (0.3, 0.8), (-0.3, 0.8), (-0.45, 0.66), (-0.45, 0.1),
            (-0.35, 0.0), (0.35, 0.0)]
    rings = [[(cx + x, y_wall - v, cz + z) for x, z in _rrect(hw + u, hh + u, 0.75 + u, nc=6, ns=3)]
             for u, v in prof]
    out.append(_ts(_loft("WC_flush_frame", rings, wrap=True), 2))
    ow, oh = W / 2.0 - bw, H / 2.0 - bw            # opening half sizes
    out.append(kit.cbox(2 * ow - 0.04, 0.25, 2 * oh - 0.04, 0.05, cx, y_wall - 0.175, cz - oh + 0.02, 1))
    g, gm = 0.1, 0.18                              # edge / middle shadow gaps
    span = 2 * ow - 2 * g - gm
    big = span * 0.59
    for x0, w in ((cx - ow + g, big), (cx - ow + g + big + gm, span - big)):
        out.append(_button("WC_flush_button", x0 + w / 2.0, y_wall, cz, w / 2.0, oh - g, 0.3))
    return out


def _button(name, cx, y_wall, cz, a, b, r):
    """Push button: rounded-rectangle pillow standing on the back plate (depth 0.3) with a soft
    edge at 0.7-0.8 and a 1 mm crown. The crown height is a smooth function of the position
    (bi-quadratic dome), not of the ring index, so the face has no diagonal creases."""
    A, B, top, crown = a - 0.11, b - 0.11, 0.805, 0.1
    prof = [("d", 0.0, 0.3), ("d", 0.0, 0.7), ("d", 0.035, 0.77), ("d", 0.11, top),
            ("f", 0.86, 0), ("f", 0.64, 0), ("f", 0.4, 0), ("f", 0.16, 0)]
    rings = []
    for kind, v, depth in prof:
        if kind == "d":
            pts = _rrect(a - v, b - v, max(r - v, 0.05), nc=4, ns=4)
            rings.append([(cx + x, y_wall - depth, cz + z) for x, z in pts])
        else:
            pts = _rrect(A * v, B * v, max((r - 0.11) * v, 0.03), nc=4, ns=4)
            rings.append([(cx + x, y_wall - top - crown * max(0.0, 1.0 - (x / A) ** 2) * max(0.0, 1.0 - (z / B) ** 2),
                           cz + z) for x, z in pts])
    return _ts(_loft(name, rings, cap1=(cx, y_wall - top - crown, cz)), 1)


# =============================================================================
# vanity
# =============================================================================
def _vessel(name, cx, cy, z0, A=24.0, B=17.5, n=2.2, segs=72):
    """Oval vessel basin, rim 2A x 2B, 13 cm tall, 0.9 cm thin rim, broad foot on the counter,
    soft-tub walls (steep sides, generous bottom radius)."""
    prof = [(0.50, 0.0, 0.0), (0.60, 0.0, 0.0), (0.635, 0.0, 0.1), (0.66, 0.0, 0.38), (0.71, 0.0, 0.95),
            (0.79, 0.0, 2.0), (0.87, 0.0, 3.6), (0.925, 0.0, 5.4), (0.962, 0.0, 7.6), (0.985, 0.0, 9.9),
            (0.997, 0.0, 12.0), (1.0, 0.0, 12.75), (1.0, 0.18, 12.97), (1.0, 0.45, 13.02),
            (1.0, 0.72, 12.96), (1.0, 0.88, 12.72), (0.997, 0.9, 12.2), (0.982, 0.9, 10.0),
            (0.955, 0.9, 7.6), (0.91, 0.9, 5.3), (0.84, 0.9, 3.4), (0.74, 0.9, 2.0),
            (0.6, 0.9, 1.25), (0.42, 0.9, 1.0), (0.22, 0.9, 0.95)]
    rings = [_oval(max(A * s - d, 0.1), max(B * s - d, 0.1), n, z0 + z, segs, cx, cy) for s, d, z in prof]
    return _ts(_loft(name, rings, cap0=(cx, cy, z0), cap1=(cx, cy, z0 + 0.95)), 1)


def _deck_mixer(x, y, z0, reach=18.5, body_h=22.5):
    """Tall single-lever basin mixer for a vessel bowl (chrome): rosette, round body with a
    softly domed cap, a spout tube with a turned collar where it leaves the body and a recessed
    aerator, and a side lever (hub + tapered flat paddle, raised 16 degrees)."""
    out = [(_ccyl(2.5, 0.5, 0.15, (x, y, z0), sides=40), "metal_chrome"),
           (_ccyl(1.9, body_h, 0.32, (x, y, z0 + 0.45), sides=40), "metal_chrome")]
    top = z0 + 0.45 + body_h
    cap = _lathe("Mixer_cap", [(1.6, -0.06), (1.5, 0.12), (1.1, 0.25), (0.0, 0.3)], 40, x, y, top)
    out.append((_ts(cap, 1), "metal_chrome"))
    sz = top - 3.4
    out.append((_ccyl(1.05, reach + 1.0, 0.38, (x, y + 1.0, sz), (0, -1, 0), sides=28), "metal_chrome"))
    out.append((_ccyl(1.32, 1.05, 0.22, (x, y - 1.2, sz), (0, -1, 0), sides=32), "metal_chrome"))
    ya = y - reach + 1.5                           # aerator: chrome ring, steel mesh 0.7 mm up inside
    ring = _lathe("Mixer_aerator", [(0.5, -0.06), (0.5, -0.2), (0.56, -0.26), (0.72, -0.26),
                                    (0.76, -0.2), (0.76, 0.1)], 32, x, ya, sz - 0.9)
    out.append((_ts(ring, 1), "metal_chrome"))
    out.append((_ccyl(0.52, 0.05, 0.01, (x, ya, sz - 1.04), (0, 0, -1), sides=24, fsegs=1), "metal_steel"))
    out.append((_ccyl(1.1, 1.35, 0.22, (x + 1.3, y, top - 1.7), (1, 0, 0), sides=28), "metal_chrome"))
    ax = (math.cos(math.radians(16)), 0.0, math.sin(math.radians(16)))
    pad = kit.cbox(1.25, 0.5, 5.8, 0.22, 0.0, 0.0, 0.0, 3)
    kit.setp(pad, "heightsegs", 4)
    kit.taper(pad, -0.32)
    out.append((_orient(pad, ax, (x + 2.45, y, top - 1.7)), "metal_chrome"))
    return out


def build_vanity(width=80.0):
    """Wall-hung walnut vanity 80 x 46 x 48 (bottom at z = 37, top at 85) with one full-width
    drawer (3 mm reveals, recessed finger channel under the top), a 1.6 cm marble top, an oval
    vessel basin with chrome pop-up waste and a tall chrome deck mixer."""
    W, D = float(width), 46.0
    Z0, ZT, TT = 37.0, 85.0, 1.6
    zc = ZT - TT                       # carcass top / underside of the marble (83.4)
    hw, yf, yb = W / 2.0, -D / 2.0, D / 2.0
    y_face = yf + 0.6                  # drawer face (marble overhangs 6 mm)
    ft, st = 1.9, 1.8                  # drawer front / side panel thickness
    y_car = y_face + ft                # carcass front edge
    clen = yb - y_car
    cyc = (y_car + yb) / 2.0
    nodes = []
    for sx in (-1.0, 1.0):
        nodes.append(kit.part(kit.cbox(st, clen, zc - Z0, 0.15, sx * (hw - st / 2.0), cyc, Z0), "wood_dark", 110))
    nodes.append(kit.part(kit.cbox(W - 2 * st, clen, 1.8, 0.1, 0.0, cyc, Z0), "wood_dark", 110))
    ch = 3.2                           # finger-channel height under the top
    nodes.append(kit.part(kit.cbox(W - 2 * st, 1.8, ch + 0.3, 0.1, 0.0, y_car + 2.6 + 0.9, zc - ch - 0.3),
                          "wood_dark", 110))
    nodes.append(kit.part(kit.cbox(W - 0.6, ft, zc - ch - Z0, 0.25, 0.0, y_face + ft / 2.0, Z0), "wood_dark", 110))
    nodes.append(kit.part(kit.cbox(W, D, TT, 0.2, 0.0, 0.0, zc), "stone_worktop", 120))
    bx, by = 0.0, -3.0
    nodes.append(kit.part(_vessel("Vanity_basin", bx, by, ZT), "ceramic_white", 40))
    waste = _lathe("Vanity_waste", [(0.0, 0.0), (3.0, 0.0), (3.2, 0.12), (3.15, 0.3), (2.6, 0.42),
                                    (1.2, 0.5), (0.0, 0.52)], 40, bx, by, ZT + 0.93)
    nodes.append(kit.part(_ts(waste, 1), "metal_chrome", 20))
    for n, key in _deck_mixer(bx, 18.0, ZT):
        nodes.append(kit.part(n, key, 20))
    return _finish("Vanity_Walnut_%d" % int(W), nodes)


# =============================================================================
# mirror
# =============================================================================
def build_mirror(width=60.0, height=85.0, radius=14.0, centre_z=160.0):
    """Rounded-rectangle mirror 60 x 85 in a thin brushed-brass frame (1.0 cm face, 2.5 cm
    deep), hung with its centre at 160 cm."""
    hw, hh = width / 2.0, height / 2.0
    pw, ph, pr = hw - 0.5, hh - 0.5, radius - 0.5        # frame centre-line
    prof = [(0.5, 0.15), (0.5, 2.35), (0.35, 2.5), (-0.35, 2.5), (-0.5, 2.35), (-0.5, 0.15),
            (-0.35, 0.0), (0.35, 0.0)]
    rings = []
    for u, v in prof:
        rings.append([(x, -v, centre_z + z) for x, z in _rrect(pw + u, ph + u, pr + u, nc=10, ns=3)])
    frame = _ts(_loft("Mirror_frame", rings, wrap=True), 2)
    gw, gh, gr = pw - 0.5 + 0.2, ph - 0.5 + 0.2, pr - 0.5 + 0.2
    g_back = [(x, -1.4, centre_z + z) for x, z in _rrect(gw, gh, gr, nc=10, ns=3)]
    g_front = [(x, -1.8, centre_z + z) for x, z in _rrect(gw, gh, gr, nc=10, ns=3)]
    glass = _loft("Mirror_glass", [g_back, g_front], cap0=(0.0, -1.4, centre_z), cap1=(0.0, -1.8, centre_z),
                  sg=(4, 2, 1))
    return _finish("Mirror_Brass", [kit.part(frame, "metal_brass", 25), kit.part(glass, "mirror", 100)])


# =============================================================================
# shower
# =============================================================================
def build_shower(size=90.0, hand="left"):
    """Low 90 x 90 x 4 ceramic tray with a slot drain along the back wall, a frameless 10 mm
    walk-in screen (90 x 200) along the front edge in a chrome wall channel on the side wall
    with a stabiliser bar to the back wall, a 25 cm round rain head on a wall arm at 215 cm
    and a thermostatic mixer at 110 cm. Back wall y = +45, side wall x = -45 (hand="left")."""
    s = float(size)
    h = s / 2.0
    side = -1.0 if hand == "left" else 1.0         # x of the side wall carrying the channel
    nodes = []
    ys = h - 7.0                                   # slot drain centre line

    def O(d, z):                                   # true offsets of a 1.2 cm plan corner radius
        return [(u, w, z) for u, w in _rrect(h - d, h - d, max(1.2 - d, 0.3), nc=6, ns=4)]

    def S(d, z):
        return [(u, ys + w, z) for u, w in _rrect(h - 10.0 + d, 1.6 + d, max(1.5 + d, 0.1), nc=6, ns=4)]

    rings = [O(0, 0.0), O(0, 0.3), O(0, 3.3), O(0.08, 3.8), O(0.45, 4.0), O(1.2, 4.0)]
    a, b = O(1.2, 4.0), S(0.6, 3.72)
    rings += [_blend(a, b, 0.3, 3.93), _blend(a, b, 0.65, 3.84), _blend(a, b, 0.9, 3.76)]
    rings += [S(0.6, 3.72), S(0.15, 3.70), S(0.0, 3.6), S(0.0, 2.2)]
    nodes.append(kit.part(_ts(_loft("Shower_tray", rings), 1), "ceramic_white", 40))
    lr = [S(-0.04, 2.3), S(-0.04, 3.55), S(0.08, 3.66), S(0.08, 3.745), S(-0.2, 3.745),
          S(-0.24, 3.63), S(-0.24, 2.55), S(-0.6, 2.5)]
    nodes.append(kit.part(_ts(_loft("Shower_drain", lr, cap0=True, cap1=True), 1), "metal_steel", 25))
    sl = 2.0 * (h - 10.0)
    nodes.append(kit.part(kit.cbox(sl - 1.6, 1.9, 0.26, 0.06, 0.0, ys, 3.46, 2), "metal_steel", 25))
    nodes.append(kit.part(kit.cbox(sl - 4.0, 0.3, 0.96, 0.05, 0.0, ys, 2.5, 1), "metal_steel", 25))

    # ---- 10 mm glass panel on the tray, in a U wall channel
    gy, gz0, gh = -h + 3.5, 4.02, 200.0
    x_in = side * (h - 0.4)                        # glass edge inside the channel
    x_out = -side * (h - 0.6)                      # free end, on the flat of the tray (not its arris)
    nodes.append(kit.part(kit.cbox(abs(x_out - x_in), 1.0, gh, 0.12, (x_in + x_out) / 2.0, gy, gz0, 2),
                          "glass", 100))
    chz, chh = 4.0, gz0 + gh - 4.0
    nodes.append(kit.part(kit.cbox(0.3, 1.9, chh, 0.05, side * (h - 0.15), gy, chz, 1), "metal_chrome", 25))
    for fy in (gy - 0.8, gy + 0.8):
        nodes.append(kit.part(kit.cbox(2.2, 0.3, chh, 0.08, side * (h - 0.3 - 1.1), fy, chz, 2), "metal_chrome", 25))

    # ---- stabiliser bar: glass clamp near the free end -> back wall
    bx, bz = -side * (h - 7.0), 196.0
    nodes.append(kit.part(_ccyl(1.5, 1.1, 0.3, (bx, gy + 0.5, bz), (0, 1, 0), sides=28), "metal_chrome", 25))
    nodes.append(kit.part(_ccyl(1.5, 0.9, 0.3, (bx, gy - 0.5, bz), (0, -1, 0), sides=28), "metal_chrome", 25))
    nodes.append(kit.part(_ccyl(0.9, (h - 1.0) - (gy + 1.3) + 0.3, 0.2, (bx, gy + 1.3, bz), (0, 1, 0), sides=24),
                          "metal_chrome", 25))
    nodes.append(kit.part(_ccyl(2.3, 1.0, 0.3, (bx, h, bz), (0, -1, 0), sides=32), "metal_chrome", 25))

    # ---- rain head on a wall arm (face at 215 cm), centred over the tray
    az, hy = 219.0, 5.0
    nodes.append(kit.part(_ccyl(3.4, 1.4, 0.4, (0.0, h, az), (0, -1, 0), sides=40), "metal_chrome", 25))
    nodes.append(kit.part(_ccyl(1.05, (h - 1.4) - hy - 0.6, 0.15, (0.0, h - 1.3, az), (0, -1, 0), sides=28),
                          "metal_chrome", 25))
    nodes.append(kit.part(kit.sphere(1.4, 0.0, hy, az, segs=32), "metal_chrome", 25))
    nodes.append(kit.part(_ccyl(1.0, 2.4, 0.2, (0.0, hy, 215.85), sides=28), "metal_chrome", 25))
    nodes.append(kit.part(_ccyl(12.5, 0.9, 0.35, (0.0, hy, 215.0), sides=72, fsegs=3), "metal_chrome", 25))
    cen = []
    for rr, cnt in ((1.8, 6), (3.6, 12), (5.4, 18), (7.2, 24), (9.0, 30), (10.8, 36)):
        for k in range(cnt):
            t = TAU * (k + 0.5 * (cnt % 12 == 0)) / cnt
            cen.append((rr * math.cos(t), hy + rr * math.sin(t)))
    nodes.append(kit.part(_pins(cen, 0.2, 0.17, 215.05, name="Shower_nozzles"), "rubber", 20))

    # ---- thermostatic mixer at 110 cm on the back wall, toward the open (entry) side
    mx, mz = -side * 20.0, 110.0
    nodes.append(kit.part(_ccyl(8.0, 0.9, 0.3, (mx, h, mz), (0, -1, 0), sides=64), "metal_chrome", 25))
    for kz in (mz + 3.4, mz - 3.4):
        nodes.append(kit.part(_ccyl(2.3, 3.4, 0.55, (mx, h - 0.85, kz), (0, -1, 0), sides=40), "metal_chrome", 25))
        nodes.append(kit.part(kit.cbox(0.7, 0.6, 3.2, 0.2, mx, h - 0.85 - 3.4 - 0.2, kz - 1.6, 2), "metal_chrome", 25))
    return _finish("Shower_%d" % int(s), nodes)


# =============================================================================
# towel rail
# =============================================================================
def _fold(x, phases, terms):
    return sum(a * math.sin(TAU * x / wl + p) for (a, wl), p in zip(terms, phases))


def build_towel_rail(width=60.0, height=112.0):
    """Polished chrome wall rail (60 cm overall, bar at 112 cm) with a bath towel folded in half
    lengthwise and draped over it: front flap a little longer, soft vertical folds growing toward
    the hems, woven border bands, slightly wavy hems."""
    nodes = []
    px = width / 2.0 - 2.6                              # bracket centres
    by, bz, br = -7.0, float(height), 0.95              # bar axis / radius (wall at y = 0)
    for sx in (-1.0, 1.0):
        nodes.append(kit.part(_ccyl(2.6, 0.9, 0.3, (sx * px, 0.0, bz), (0, -1, 0), sides=40), "metal_chrome", 25))
        nodes.append(kit.part(_ccyl(1.1, 7.2, 0.45, (sx * px, -0.85, bz), (0, -1, 0), sides=28), "metal_chrome", 25))
    nodes.append(kit.part(_ccyl(br, 2.0 * px, 0.05, (-px, by, bz), (1, 0, 0), sides=32), "metal_chrome", 25))

    # Bath towel folded in thirds lengthwise (3 layers, 1.4 cm) and hung with a 34 cm front and
    # a 30 cm back flap. Seen from the front, the left side edge is a soft full-thickness fold and
    # on the right the top layer's selvedge lies 9 mm in from the edge (a visible step). Each
    # hem end carries a flat-woven hem (1.1 cm) and a dobby border band (2.6-6.4 cm from the
    # hem), both thinner than the pile; the hems hang almost straight (a heavy terry hem does not
    # flutter) with the corners drooping and curling slightly.
    T = 1.4
    rm = br + T / 2.0 + 0.02
    lf, lb = 34.0, 30.0
    mid, ss = [], []
    nf, na, nb = 18, 10, 17

    def flap_s(u, L):                                   # dense near the bar and near the hem
        return L * (0.3 * u + 0.7 * (u - math.sin(TAU * u) / TAU))

    extra = [lf - e for e in (0.5, 0.95, 1.25, 2.45, 2.75, 6.25, 6.55)]   # crisp hem / band edges
    svf = [flap_s(1.0 - float(k) / nf, lf) for k in range(nf)]
    svf = sorted(set([s for s in svf if all(abs(s - e) > 0.2 for e in extra)] + extra), reverse=True)
    for sv in svf:
        mid.append((by - rm - 1.1 * (sv / lf) ** 2, bz - sv))
        ss.append(sv)
    nf = len(svf)
    for k in range(na + 1):
        a = math.pi * (1.0 - float(k) / na)
        mid.append((by + rm * math.cos(a), bz + rm * math.sin(a)))
        ss.append(0.0)
    for k in range(1, nb + 1):
        u = float(k) / nb
        sv = flap_s(u, lb)
        mid.append((by + rm + 0.8 * (sv / lb) ** 2, bz - sv))
        ss.append(sv)
    m = len(mid)
    front = [i < nf for i in range(m)]
    nrm = []                                            # base mid-line normals (point away from the bar)
    for i in range(m):
        a, b = mid[max(i - 1, 0)], mid[min(i + 1, m - 1)]
        ln = math.hypot(b[0] - a[0], b[1] - a[1]) or 1.0
        nrm.append((-(b[1] - a[1]) / ln, (b[0] - a[0]) / ln))
    ph_f, ph_b = (0.4, 2.1, 4.0), (1.7, 5.2, 0.9)
    terms = ((0.75, 19.0), (0.4, 10.5), (0.1, 6.3))
    tw = 23.0
    x_sel = tw - 0.95                                   # top layer's selvedge (right side)

    def sel(x):
        t = min(1.0, max(0.0, (x - (x_sel - 0.12)) / 0.24))
        return t * t * (3.0 - 2.0 * t)

    def disp(i, x):
        sv = ss[i]
        st = sel(x) * T / 6.0                           # outer layer missing past the selvedge
        sy, sz = -nrm[i][0] * st, -nrm[i][1] * st
        if sv <= 0.0:
            return 0.0, sy, sz
        L = lf if front[i] else lb
        q = sv / L
        env = min(1.0, max(0.0, (sv - 1.2) / 9.0)) ** 1.3 * (0.3 + 0.7 * q)
        dy = env * _fold(x, ph_f if front[i] else ph_b, terms)
        cd = max(0.0, (abs(x) - (tw - 9.0)) / 9.0) ** 2             # corner zone
        dy += (-0.5 if front[i] else 0.3) * q ** 3 * cd              # corners curl out a little
        ph = (0.6, 2.2) if front[i] else (2.4, 4.1)
        dz = q ** 4 * (0.16 * math.sin(TAU * x / 23.0 + ph[0]) + 0.06 * math.sin(TAU * x / 8.5 + ph[1]))
        dz -= 0.5 * q ** 3 * cd * (1.0 if x > 0 else 0.7)           # heavier selvedge corners droop
        dx = (-0.35 if front[i] else 0.9) * q ** 1.5    # the two flaps never hang exactly square
        return dx, dy + sy, dz + sz

    def thick(i, x):
        sv = ss[i]
        L = lf if front[i] else lb
        e = L - sv                                      # distance from the hem
        if e < 1.1:
            t = T - 0.32                                # folded flat hem
        elif 2.6 < e < 6.4:
            t = T - 0.4                                 # flat-woven dobby border (no pile)
        else:
            t = T
        return t * (1.0 - sel(x) / 3.0)

    xs = [-tw, -tw + 0.25, -tw + 0.7, -tw + 1.5]
    k = int((2.0 * (tw - 2.5)) / 1.75)
    xs += [-tw + 2.5 + (2.0 * (tw - 2.5)) * j / k for j in range(k)]
    xs += [tw - 2.5, tw - 1.6, x_sel - 0.12, x_sel + 0.12, tw - 0.45, tw - 0.18, tw]

    def taper(x):                                       # fold edge full-bodied, selvedge edge flat
        e = tw - abs(x)
        if x < 0:
            return 0.8 if e < 0.1 else (0.94 if e < 0.4 else 1.0)
        return 0.62 if e < 0.1 else (0.8 if e < 0.3 else 1.0)

    towel = _sheet("Rail_towel", mid, thick, xs, taper, disp)
    kit.soften(towel, noise=(9.0, 0.18, 0.1), smooth=1, seed=7)
    pile = rt.Noisemodifier()                           # soft terry lumpiness at 2-3 cm scale
    kit.setp(pile, "seed", 11)
    kit.setp(pile, "scale", 2.4)
    kit.setp(pile, "strength", rt.Point3(0.06, 0.06, 0.05))
    kit.setp(pile, "fractal", False)
    rt.addModifier(towel, pile)
    nodes.append(kit.part(towel, "bedding", 25))
    return _finish("TowelRail_Chrome", nodes)


# =============================================================================
# decor
# =============================================================================
def _rotz(pts, cx, cy, deg):
    """Rotate (x, y, z) points about the vertical axis through (cx, cy)."""
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [(cx + (p[0] - cx) * c - (p[1] - cy) * s, cy + (p[0] - cx) * s + (p[1] - cy) * c, p[2]) for p in pts]


def _rolled_towel(name, cx, cy, length=22.0, pitch=0.53, turns=6.68, r0=0.4, rot=0.0):
    """Hand towel rolled into a spiral (axis along X, turned rot degrees about Z), slightly out of
    round and flattened by its own weight. A hand roll is never even: the layer spacing and
    thickness drift from turn to turn, the layers telescope a few mm at the ends, the core is a
    tight curl (no cardboard-tube hole), the outer turns bunch into soft lengthwise swells, the
    roll is a little fuller in the middle, and the free hem (0.68 of a turn: low on the front,
    the way a roll is set down) lies flat against the roll."""
    phi_end = TAU * turns
    n = int(turns * 14) + 1
    t0 = 0.8 * pitch
    mid, phis = [], []
    for k in range(n + 1):
        ph = phi_end * k / n
        r = (r0 + pitch * ph / TAU + 0.06 * math.sin(ph + 0.7) + 0.035 * math.sin(2.0 * ph + 1.9)
             + 0.03 * math.sin(0.43 * ph + 1.3))                       # uneven winding
        u = max(0.0, (ph - (phi_end - 0.35 * TAU)) / (0.35 * TAU))   # last third of a turn
        r -= 0.55 * (pitch - t0) * u * u                              # hem settles onto the roll
        mid.append((r * math.cos(ph), r * math.sin(ph)))
        phis.append(ph)
    zmin = min(p[1] for p in mid) - 0.5 * t0            # underside of the outer turn
    hl = length / 2.0
    xs = [-hl, -hl + 0.2, -hl + 0.6, -hl + 1.3] + [-hl + 2.0 + (length - 4.0) * j / 6.0 for j in range(7)] \
        + [hl - 1.3, hl - 0.6, hl - 0.2, hl]

    def thick(i, x):
        u = max(0.0, (phis[i] - (phi_end - 0.12 * TAU)) / (0.12 * TAU))
        return t0 * (1.0 - 0.45 * u) * (1.0 + 0.06 * math.sin(0.9 * phis[i] + 0.5))

    def taper(x):
        e = hl - abs(x)
        return 0.6 if e < 0.1 else (0.85 if e < 0.4 else (0.97 if e < 1.0 else 1.0))

    def disp(i, x):
        ph = phis[i]
        dx = 0.2 * math.sin(0.8 * ph + 0.6) + 0.09 * math.sin(2.3 * ph + 1.4)   # layers telescope
        w = (ph / phi_end) ** 2 * (0.08 * math.sin(TAU * x / 9.5 + 1.1) + 0.035 * math.sin(TAU * x / 4.3 + 0.3))
        return (dx, w * math.cos(ph), w * math.sin(ph))  # swells grow outward, layers stay nested

    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))

    def xform(x, y, z):
        f = 1.0 + 0.035 * (1.0 - (x / hl) ** 2)          # a little fuller in the middle
        y, z = y * f, (z - zmin) * 0.88 * f             # rest on z = 0, settle 12 %
        return (cx + x * c - y * s, cy + x * s + y * c, z)

    sheet = _sheet(name, mid, thick, xs, taper, disp, xform=xform)
    kit.soften(sheet, noise=(5.0, 0.18, 0.12), smooth=1, seed=3)
    lo = rt.nodeGetBoundingBox(sheet, rt.matrix3(1))[0]
    sheet.pos = rt.Point3(sheet.pos.x, sheet.pos.y, sheet.pos.z - lo.z - 0.04)   # weight presses it down
    return sheet


def _soap_bar(name, cx, cy, z0, a=3.55, b=2.3, h=2.0, rot=0.0):
    """Soap bar: rounded-rectangle plan, soft shoulders and a slightly domed top."""
    prof = [(0.9, 0.0), (0.965, 0.12), (0.995, 0.42), (1.0, 0.8), (0.99, 1.25), (0.955, 1.6),
            (0.88, 1.82), (0.7, 1.95), (0.4, 2.0)]
    rings = [_rotz(_oval(a * f, b * f, 3.2, z0 + h * z / 2.0, 48, cx, cy), cx, cy, rot) for f, z in prof]
    return _ts(_loft(name, rings, cap0=(cx, cy, z0), cap1=(cx, cy, z0 + h * 1.01)), 1)


def build_bath_decor():
    """Countertop vignette: oval ceramic soap dish with a bar of soap, ceramic pump bottle with a
    chrome pump, heavy-based glass tumbler and a rolled hand towel (approx. 40 x 20 x 19)."""
    nodes = []
    # soap dish 14 x 10 x 2.1, set down a few degrees off square; the bar lies skewed in it
    dx, dy = -11.0, -7.0
    prof = [(0.62, 0.0, 0.0), (0.68, 0.0, 0.08), (0.72, 0.0, 0.35), (0.8, 0.0, 0.75), (0.9, 0.0, 1.3),
            (0.97, 0.0, 1.8), (1.0, 0.0, 2.05), (1.0, 0.2, 2.15), (1.0, 0.42, 2.12), (1.0, 0.55, 1.95),
            (0.97, 0.55, 1.6), (0.9, 0.55, 1.15), (0.8, 0.55, 0.78), (0.72, 0.55, 0.62), (0.5, 0.55, 0.6),
            (0.25, 0.55, 0.6)]
    rings = [_rotz(_oval(max(7.0 * s - d, 0.1), max(5.0 * s - d, 0.1), 2.6, z, 56, dx, dy), dx, dy, -4.0)
             for s, d, z in prof]
    dish = _ts(_loft("Decor_soapdish", rings, cap0=(dx, dy, 0.0), cap1=(dx, dy, 0.6)), 1)
    nodes.append(kit.part(dish, "ceramic_white", 30))
    nodes.append(kit.part(_soap_bar("Decor_soap", dx + 0.25, dy - 0.1, 0.6, rot=4.0), "wax", 15))
    # pump bottle
    px, py = -11.0, 4.5
    body = _lathe("Decor_pump_bottle", [(0.0, 0.0), (3.3, 0.0), (3.55, 0.1), (3.68, 0.35), (3.7, 0.8),
                                        (3.7, 10.6), (3.62, 11.6), (3.35, 12.4), (2.8, 13.05), (2.0, 13.45),
                                        (1.45, 13.6), (1.35, 13.75), (1.35, 14.4), (1.2, 14.5), (0.0, 14.5)],
                  48, px, py)
    nodes.append(kit.part(_ts(body, 1), "ceramic_white", 30))
    nodes.append(kit.part(_ccyl(1.65, 1.3, 0.3, (px, py, 14.2)), "metal_chrome", 20))
    nodes.append(kit.part(_ccyl(0.42, 1.8, 0.1, (px, py, 15.4), sides=16), "metal_chrome", 20))
    nodes.append(kit.part(_ccyl(1.3, 1.4, 0.5, (px, py, 17.0), sides=28), "metal_chrome", 20))
    na = (-math.sin(math.radians(28)), -math.cos(math.radians(28)), -0.08)   # nozzle turned off-axis
    nodes.append(kit.part(_ccyl(0.36, 2.9, 0.15, (px + 0.6 * na[0], py + 0.6 * na[1], 17.85), na, sides=16),
                          "metal_chrome", 20))
    # glass tumbler (thick base)
    tx, ty = 0.8, 3.6
    tum = _lathe("Decor_tumbler", [(0.0, 0.0), (3.1, 0.0), (3.45, 0.04), (3.6, 0.2), (3.62, 0.5),
                                   (3.72, 3.0), (3.82, 6.5), (3.9, 9.6), (3.89, 9.78), (3.8, 9.84),
                                   (3.7, 9.78), (3.66, 9.6), (3.58, 6.5), (3.48, 3.0), (3.36, 1.4),
                                   (3.1, 1.15), (2.0, 1.1), (0.0, 1.1)], 48, tx, ty)
    nodes.append(kit.part(_ts(tum, 1), "glass", 100))
    # rolled hand towel
    nodes.append(kit.part(_rolled_towel("Decor_towel_roll", 11.5, -6.0, rot=6.0), "bedding", 20))
    return _finish("Bath_Decor", nodes)


# =============================================================================
# preview
# =============================================================================
PIECES = (("shower", build_shower), ("toilet", build_toilet), ("vanity", build_vanity),
          ("mirror", build_mirror), ("rail", build_towel_rail), ("decor", build_bath_decor))


def _backdrop(x0, x1, y0, y1, z1, name):
    """Preview-only wall (not a kit part, so it is not framed or re-materialled)."""
    b = rt.Box(width=x1 - x0, length=y1 - y0, height=z1, pos=rt.Point3((x0 + x1) / 2.0, (y0 + y1) / 2.0, 0.0))
    b.name = name
    m = rt.VRayMtl()
    m.diffuse = rt.Color(196, 192, 186)
    m.brdf_useRoughness = True
    m.reflection = rt.Color(60, 60, 60)
    m.reflection_glossiness = 0.6
    b.material = m
    return b


def preview():
    only = [k.strip() for k in os.environ.get("MF_BATH_ONLY", "").split(",") if k.strip()]
    stack = os.environ.get("MF_BATH_STACK", "") == "1"
    wall_y, gap = 60.0, 35.0
    cursor, xs = 0.0, {}
    x_min, x_max = 1e9, -1e9
    for key, fn in PIECES:
        if only and key not in only:
            continue
        i0 = len(kit.PARTS)
        g = fn()
        lo, hi = _bbox([p[0] for p in kit.PARTS[i0:]])
        w, d = hi[0] - lo[0], hi[1] - lo[1]
        if stack and key == "mirror" and "vanity" in xs:
            cx = xs["vanity"]
        else:
            cx = cursor + w / 2.0
            cursor = cx + w / 2.0 + gap
        xs[key] = cx
        y = wall_y - 40.0 if key == "decor" else wall_y - d / 2.0
        kit.place(g, cx, y)
        x_min, x_max = min(x_min, cx - w / 2.0), max(x_max, cx + w / 2.0)
        if key == "shower":
            _backdrop(cx - w / 2.0 - 4.0, cx - w / 2.0, wall_y - d - 10.0, wall_y, 240.0, "prev_side_wall")
    _backdrop(x_min - 40.0, x_max + 40.0, wall_y, wall_y + 4.0, 245.0, "prev_back_wall")
