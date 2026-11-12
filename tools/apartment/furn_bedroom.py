"""Bedroom furniture for the MatForge test apartment (Japandi / warm Scandinavian).

Every piece is modelled in pymxs from primitives, lathed / swept quad meshes and
procedurally shaped soft bodies (no external assets). Each build_*() builds its piece
at the local origin with its FRONT facing -Y, its base on z = 0 and its footprint
centred on X/Y, registers every visible node with kit.part() and returns kit.group().

  build_bed(width=160, length=200)     oak frame on tapered legs, channel-upholstered
                                       headboard (120 high), mattress (top 55) + fitted
                                       sheet, linen duvet with a turned-down fold that
                                       drapes over the mattress and the oak rails at the
                                       sides and foot, folded velvet throw whose ends hang
                                       in soft pipe folds, 2 sleeping pillows + 2 cushions
  build_nightstand()                   45 x 38 x 50 oak, one drawer (3 mm gaps), brass knob
  build_table_lamp()                   45 high: ceramic gourd base, linen drum shade,
                                       brass fittings, warm bulb
  build_wardrobe(length=230, depth=60, height=220)
                                       painted hinged doors (round(length / 55)), 3 mm
                                       gaps, tall brass bar handles, 8 cm recessed plinth
  build_bench()                        120 x 40 x 45 end-of-bed bench, piped upholstered
                                       seat on an oak frame with an H-stretcher
  build_bedroom_rug(w=170, l=240)      1.5 cm wool rug (w along X, l along Y), rolled bound
                                       edges, slight irregular lie

Placement: the bed frame is (width + 10) x (length + 15.2) with the headboard's back at
y = +(length + 15.2) / 2. The duvet hangs over the rails and ends 4-9 cm down their outer
faces; its folds and gathered foot corners spill up to ~9 cm past the frame sides and ~6 cm
past the foot. Wardrobe handles stand 3.9 cm proud of the doors; the knob 2.6 cm proud of
the nightstand front.

preview() lays every piece out side by side. Set MF_BEDROOM_PIECE to one of bed, bed150,
nightstand, lamp, wardrobe, wardrobe130, wardrobe260, bench, rug or vignette to preview a
single piece / a furnished arrangement instead.
"""
import bisect
import math
import os
import random

from pymxs import runtime as rt

import kit

# ====================================================================== small maths
def _sstep(e0, e1, x):
    """Hermite smoothstep from e0 to e1 (e0 > e1 gives the falling version)."""
    if e0 == e1:
        return 1.0 if x >= e1 else 0.0
    t = (x - e0) / (e1 - e0)
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return t * t * (3.0 - 2.0 * t)


def _floor(v, lo, k):
    """Soft max(v, lo): never below lo, C1 blend of half-width k (contact flattening)."""
    d = v - lo
    if d >= k:
        return v
    if d <= -k:
        return lo
    return lo + (d + k) * (d + k) / (4.0 * k)


def _ceil(v, hi, k):
    return -_floor(-v, -hi, k)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    ln = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / ln, a[1] / ln, a[2] / ln)


class _Noise(object):
    """Smooth band-limited noise: a sum of random plane waves, std ~0.5, |v| < ~1."""

    def __init__(self, seed, n=7, wl=(20.0, 60.0), dims=2):
        rnd = random.Random(seed)
        self.w = []
        s2 = 0.0
        for _ in range(n):
            lam = rnd.uniform(wl[0], wl[1])
            k = 2.0 * math.pi / lam
            if dims == 1:
                d = (1.0, 0.0, 0.0)
            elif dims == 2:
                a = rnd.uniform(0.0, 2.0 * math.pi)
                d = (math.cos(a), math.sin(a), 0.0)
            else:
                zz = rnd.uniform(-1.0, 1.0)
                a = rnd.uniform(0.0, 2.0 * math.pi)
                r = math.sqrt(1.0 - zz * zz)
                d = (r * math.cos(a), r * math.sin(a), zz)
            amp = lam / wl[1]
            self.w.append((d[0] * k, d[1] * k, d[2] * k, rnd.uniform(0.0, 2.0 * math.pi), amp))
            s2 += amp * amp
        self.norm = 0.5 / math.sqrt(s2 / 2.0)

    def __call__(self, x, y=0.0, z=0.0):
        return self.norm * sum(a * math.sin(kx * x + ky * y + kz * z + ph)
                               for kx, ky, kz, ph, a in self.w)


def _march(a, b, step):
    """Samples from a to b (both included) with a position-dependent step."""
    out = [a]
    x = a
    while True:
        st = step(x)
        if x + st >= b - 0.4 * st:
            break
        x += st
        out.append(x)
    out.append(b)
    return out


def _pieces(breaks, step):
    out = []
    for a, b in zip(breaks[:-1], breaks[1:]):
        if b - a < 1e-6:
            continue
        seg = _march(a, b, step)
        out.extend(seg if not out else seg[1:])
    return out


# ====================================================================== mesh helpers
_MS_READY = [False]


def _ms_init():
    if _MS_READY[0]:
        return
    rt.execute('fn mfb_cut_below o z = (local del = #{}\n'
               'for f = 1 to (polyop.getNumFaces o) do if (polyop.getFaceCenter o f).z < z do append del f\n'
               'polyop.deleteFaces o del delIsoVerts:true\n o)')
    _MS_READY[0] = True


def _mesh(name, verts, quads=(), tris=(), smooth=True):
    """Editable Poly from Python geometry: verts [(x, y, z)], 0-based quads (a, b, c, d)
    counter-clockwise seen from outside (normals out), optional tris."""
    vs = ",".join("[%.3f,%.3f,%.3f]" % v for v in verts)
    fl = ["[%d,%d,%d],[%d,%d,%d]" % (a + 1, b + 1, c + 1, a + 1, c + 1, d + 1) for a, b, c, d in quads]
    fl.extend("[%d,%d,%d]" % (a + 1, b + 1, c + 1) for a, b, c in tris)
    src = ('(local m = mesh name:"%s" vertices:#(%s) faces:#(%s)\n'
           'for i = 1 to %d do (setEdgeVis m (2*i-1) 3 false; setEdgeVis m (2*i) 1 false)\n'
           'for f = 1 to m.numfaces do setFaceSmoothGroup m f %d\n'
           'update m\nconvertToPoly m\nm)' % (name, vs, ",".join(fl), len(quads), 1 if smooth else 0))
    return rt.execute(src)


def _grid(nu, nv, base=0, flip=False):
    out = []
    for i in range(nu - 1):
        for j in range(nv - 1):
            a = base + i * nv + j
            q = (a, a + nv, a + nv + 1, a + 1)
            out.append((q[0], q[3], q[2], q[1]) if flip else q)
    return out


def _border(nu, nv):
    """Border of an nu x nv grid, counter-clockwise about the top normal."""
    return ([(i, 0) for i in range(nu)] + [(nu - 1, j) for j in range(1, nv)] +
            [(i, nv - 1) for i in range(nu - 2, -1, -1)] + [(0, j) for j in range(nv - 2, 0, -1)])


def _shell_mesh(name, top, bot, rims=(), shared=False):
    """Closed soft body from a top grid (outer side, i ~ +u, j ~ +v), a bottom grid and
    optional rim loops between their borders; shared=True stitches the bottom straight
    onto the top border (a sewn lens seam, e.g. pillows)."""
    nu, nv = len(top), len(top[0])
    verts = [top[i][j] for i in range(nu) for j in range(nv)]
    quads = _grid(nu, nv)
    border = _border(nu, nv)
    L = len(border)
    if shared:
        idx = {}
        for (i, j) in border:
            idx[(i, j)] = i * nv + j
        for i in range(1, nu - 1):
            for j in range(1, nv - 1):
                idx[(i, j)] = len(verts)
                verts.append(bot[i][j])
        for i in range(nu - 1):
            for j in range(nv - 1):
                a, b, c, d = idx[(i, j)], idx[(i + 1, j)], idx[(i + 1, j + 1)], idx[(i, j + 1)]
                quads.append((a, d, c, b))
        return _mesh(name, verts, quads)
    loops = [[i * nv + j for (i, j) in border]]
    for ring in rims:
        b0 = len(verts)
        verts.extend(ring)
        loops.append(list(range(b0, b0 + L)))
    b0 = len(verts)
    verts.extend(bot[i][j] for i in range(nu) for j in range(nv))
    quads.extend(_grid(nu, nv, b0, flip=True))
    loops.append([b0 + i * nv + j for (i, j) in border])
    for A, B in zip(loops[:-1], loops[1:]):
        for k in range(L):
            k1 = (k + 1) % L
            quads.append((A[k], B[k], B[k1], A[k1]))
    return _mesh(name, verts, quads)


def _relax(grid, irange, jrange, passes, lam):
    """Laplacian smoothing of grid points (i in irange, j in jrange); border points only
    move along their border line."""
    nu, nv = len(grid), len(grid[0])
    for _ in range(passes):
        new = {}
        for i in irange:
            for j in jrange:
                if i in (0, nu - 1) and j in (0, nv - 1):
                    continue
                if j in (0, nv - 1):
                    nb = [grid[i - 1][j], grid[i + 1][j]]
                elif i in (0, nu - 1):
                    nb = [grid[i][j - 1], grid[i][j + 1]]
                else:
                    nb = [grid[i - 1][j], grid[i + 1][j], grid[i][j - 1], grid[i][j + 1]]
                p = grid[i][j]
                a = [sum(q[k] for q in nb) / len(nb) for k in range(3)]
                new[(i, j)] = (p[0] + lam * (a[0] - p[0]), p[1] + lam * (a[1] - p[1]), p[2] + lam * (a[2] - p[2]))
        for (i, j), p in new.items():
            grid[i][j] = p


def _rim_ring(top, bot, push, f=0.5):
    """Rim loop between the borders of two grids at fraction f (0 top .. 1 bottom), bulged
    outward by push * thickness * sin(pi f) (a rounded hem / welt-less edge)."""
    nu, nv = len(top), len(top[0])
    ring = []
    bulge = push * math.sin(math.pi * f)
    for (i, j) in _border(nu, nv):
        a, b = top[i][j], bot[i][j]
        ii, jj = min(max(i, 1), nu - 2), min(max(j, 1), nv - 2)
        ai, bi = top[ii][jj], bot[ii][jj]
        m = (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f)
        c = ((ai[0] + bi[0]) * 0.5, (ai[1] + bi[1]) * 0.5, (ai[2] + bi[2]) * 0.5)
        mm = ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5, (a[2] + b[2]) * 0.5)
        o = _norm(_sub(mm, c))
        th = math.sqrt(_dot(_sub(a, b), _sub(a, b))) * bulge
        ring.append((m[0] + o[0] * th, m[1] + o[1] * th, m[2] + o[2] * th))
    return ring


def _lathe(name, prof, origin=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0), segs=32, closed=False):
    """Quad lathe of an (r, h) profile ordered counter-clockwise in the (r, h) half plane
    (solid on the left when walking it); r == 0 makes a pole, closed joins last to first."""
    ax = _norm(axis)
    helper = (0.0, 0.0, 1.0) if abs(ax[2]) < 0.9 else (1.0, 0.0, 0.0)
    e1 = _norm(_cross(helper, ax))
    e2 = _cross(ax, e1)
    cs = [(math.cos(2.0 * math.pi * j / segs), math.sin(2.0 * math.pi * j / segs)) for j in range(segs)]
    verts, rows = [], []
    for r, h in prof:
        c = (origin[0] + ax[0] * h, origin[1] + ax[1] * h, origin[2] + ax[2] * h)
        if r <= 1e-6:
            rows.append([len(verts)])
            verts.append(c)
            continue
        row = []
        for ca, sa in cs:
            row.append(len(verts))
            verts.append((c[0] + (e1[0] * ca + e2[0] * sa) * r,
                          c[1] + (e1[1] * ca + e2[1] * sa) * r,
                          c[2] + (e1[2] * ca + e2[2] * sa) * r))
        rows.append(row)
    quads, tris = [], []
    pairs = list(zip(rows[:-1], rows[1:]))
    if closed:
        pairs.append((rows[-1], rows[0]))
    for A, B in pairs:
        if len(A) == 1 and len(B) == 1:
            continue
        for j in range(segs):
            j1 = (j + 1) % segs
            if len(A) == 1:
                tris.append((A[0], B[j1], B[j]))
            elif len(B) == 1:
                tris.append((A[j], A[j1], B[0]))
            else:
                quads.append((A[j], A[j1], B[j1], B[j]))
    return _mesh(name, verts, quads, tris)


def _sweep(name, rings, closed=False, caps=True, push=0.0):
    """Skin consecutive closed rings (each counter-clockwise about the sweep direction)."""
    verts, idx = [], []
    for ring in rings:
        idx.append(list(range(len(verts), len(verts) + len(ring))))
        verts.extend(ring)
    m = len(rings[0])
    quads, tris = [], []
    pairs = list(zip(idx[:-1], idx[1:]))
    if closed:
        pairs.append((idx[-1], idx[0]))
    for A, B in pairs:
        for j in range(m):
            j1 = (j + 1) % m
            quads.append((A[j], A[j1], B[j1], B[j]))
    if caps and not closed:
        for k in (0, -1):
            ring = rings[k]
            c = tuple(sum(p[i] for p in ring) / m for i in range(3))
            nb = rings[1] if k == 0 else rings[-2]
            cn = tuple(sum(p[i] for p in nb) / m for i in range(3))
            o = _norm(_sub(c, cn))
            ci = len(verts)
            verts.append((c[0] + o[0] * push, c[1] + o[1] * push, c[2] + o[2] * push))
            R = idx[k]
            for j in range(m):
                j1 = (j + 1) % m
                tris.append((ci, R[j1], R[j]) if k == 0 else (R[j], R[j1], ci))
    return _mesh(name, verts, quads, tris)


def _tube(name, path, r, sides=8, closed=False, caps=True):
    """Circular tube along a 3D polyline (parallel-transport frames)."""
    n = len(path)
    tans = []
    for i in range(n):
        if closed:
            a, b = path[i - 1], path[(i + 1) % n]
        else:
            a, b = path[max(i - 1, 0)], path[min(i + 1, n - 1)]
        tans.append(_norm(_sub(b, a)))
    t0 = tans[0]
    helper = (0.0, 0.0, 1.0) if abs(t0[2]) < 0.9 else (1.0, 0.0, 0.0)
    N = _norm(_cross(_cross(t0, helper), t0))
    rings = []
    for i in range(n):
        t = tans[i]
        d = _dot(N, t)
        N = _norm((N[0] - t[0] * d, N[1] - t[1] * d, N[2] - t[2] * d))
        B = _cross(t, N)
        ring = []
        for j in range(sides):
            a = 2.0 * math.pi * j / sides
            ca, sa = math.cos(a), math.sin(a)
            ring.append(tuple(path[i][k] + (N[k] * ca + B[k] * sa) * r for k in range(3)))
        rings.append(ring)
    return _sweep(name, rings, closed=closed, caps=caps, push=0.6 * r)


def _rrect_path(hw, hd, rc, z, step=5.0, arc_n=5):
    """Closed rounded-rectangle polyline (counter-clockwise from above) centred at 0,0."""
    pts = []
    corners = [((hw - rc, -hd + rc), -90.0), ((hw - rc, hd - rc), 0.0),
               ((-hw + rc, hd - rc), 90.0), ((-hw + rc, -hd + rc), 180.0)]
    for k, ((cx, cy), a0) in enumerate(corners):
        for i in range(arc_n + 1):
            a = math.radians(a0 + 90.0 * i / arc_n)
            pts.append((cx + rc * math.cos(a), cy + rc * math.sin(a), z))
        (nx, ny), _ = corners[(k + 1) % 4]
        a1 = math.radians(a0 + 90.0)
        sx, sy = cx + rc * math.cos(a1), cy + rc * math.sin(a1)
        ex, ey = nx + rc * math.cos(a1), ny + rc * math.sin(a1)
        ln = math.hypot(ex - sx, ey - sy)
        nseg = max(1, int(round(ln / step)))
        for i in range(1, nseg):
            f = float(i) / nseg
            pts.append((sx + (ex - sx) * f, sy + (ey - sy) * f, z))
    return pts


def _cb(w, l, h, fillet, x=0.0, y=0.0, z=0.0, fs=2, ws=1, ls=1, hs=1):
    """ChamferBox centred on x, y with its base at z (fillet clamped to the part)."""
    fillet = min(fillet, 0.49 * min(w, l, h))
    return rt.ChamferBox(width=w, length=l, height=h, fillet=fillet, Fillet_Segments=fs,
                         Width_Segments=ws, Length_Segments=ls, Height_Segments=hs,
                         pos=rt.Point3(x, y, z), mapcoords=True)


def _leg(x, y, h, top, bottom, fillet=0.45, z=0.0):
    """Square leg tapering from `top` (at z + h) to `bottom` (at z). Taper scales about the
    box's base, so the box is built at the foot size and grown to the top size."""
    n = _cb(bottom, bottom, h, fillet, x, y, z, fs=2)
    kit.taper(n, top / bottom - 1.0)
    return n


def _leg_w(h, top, bottom, zz):
    """Width of such a leg at height zz above its foot."""
    return bottom + (top - bottom) * zz / h


def _deform(node, fn):
    """Convert to Editable Poly and move every vertex with fn(x, y, z) -> (x, y, z)."""
    rt.convertToPoly(node)
    bits = rt.execute("#{1..%d}" % rt.polyop.getNumVerts(node))
    pts = rt.polyop.getVerts(node, bits)
    arr = rt.execute("#(" + ",".join("[%.4f,%.4f,%.4f]" % fn(p.x, p.y, p.z) for p in pts) + ")")
    rt.polyop.setVert(node, bits, arr)
    return node


def _cut_below(node, zcut):
    _ms_init()
    rt.convertToPoly(node)
    rt.mfb_cut_below(node, zcut)
    return node


# ====================================================================== soft goods
def _creases(rnd, W, D, n, depth):
    """Random soft creases (centre, direction, half length, width, depth) on a W x D face."""
    out = []
    for _ in range(n):
        a = rnd.uniform(0.0, math.pi)
        out.append((rnd.uniform(-0.36, 0.36) * W, rnd.uniform(-0.32, 0.32) * D, math.cos(a), math.sin(a),
                    rnd.uniform(0.18, 0.4) * min(W, D), rnd.uniform(2.2, 3.6),
                    depth * rnd.uniform(0.5, 1.0) * (1.0 if rnd.random() < 0.75 else -0.7)))
    return out


def _crease_at(x, y, creases):
    r = 0.0
    for cx, cy, ux, uy, ln, sg, dep in creases:
        dx, dy = x - cx, y - cy
        a = dx * ux + dy * uy
        if abs(a) > ln:
            continue
        c = -dx * uy + dy * ux
        if abs(c) > 3.0 * sg:
            continue
        r += dep * math.exp(-(c / sg) ** 2) * (1.0 - (a / ln) ** 2) ** 2
    return r


def _spread(n, alpha=0.55):
    """n samples on [-1, 1], denser toward the ends (alpha 0 = uniform, 1 = sine)."""
    out = []
    for i in range(n):
        t = -1.0 + 2.0 * i / (n - 1)
        out.append((1.0 - alpha) * t + alpha * math.sin(0.5 * math.pi * t))
    return out


def _pillow(W, D, H, seed, nu=17, nv=13, pinch=(0.05, 0.07), ex=(3.2, 2.6), seam=0.7, wrinkle=0.35, crease=0.6,
            seam_t=0.55):
    """Stuffed pillow / cushion in local coords (x across W, y across D, n thickness):
    concave pulled-in edges, pinched dog-ear corners, a sewn edge of 2 * seam_t body
    around n = 0 (closed with _seam_mesh), soft corner tension wrinkles, a few creases
    across each face and an uneven fill. Returns (top, bottom) grids."""
    rnd = random.Random(seed)
    nz = _Noise(seed, 6, (0.7, 1.9))
    cr_t = _creases(rnd, W, D, 4, crease)
    cr_b = _creases(rnd, W, D, 3, crease)
    us = _spread(nu)
    vs = _spread(nv)
    wr = []
    for cu in (-1.0, 1.0):
        for cv in (-1.0, 1.0):
            base = math.atan2(-cv * D, -cu * W)
            for off in (-0.32, 0.0, 0.3):
                wr.append((cu, cv, base + off + rnd.uniform(-0.1, 0.1),
                           wrinkle * rnd.uniform(0.55, 1.15), rnd.uniform(0.55, 0.95)))
    top, bot = [], []
    for u in us:
        rowt, rowb = [], []
        for v in vs:
            x = 0.5 * W * u * (1.0 - pinch[0] * (1.0 - v * v))
            y = 0.5 * D * v * (1.0 - pinch[1] * (1.0 - u * u))
            g = (max(0.0, 1.0 - abs(u) ** ex[0]) ** seam) * (max(0.0, 1.0 - abs(v) ** ex[1]) ** seam)
            lo = 0.5 * H * g * (1.0 + 0.15 * nz(u * 2.0, v * 2.0))
            dent = 0.0
            for cu, cv, a, dep, reach in wr:
                ru, rv = (u - cu) * 0.5 * W, (v - cv) * 0.5 * D
                al = ru * math.cos(a) + rv * math.sin(a)
                ac = -ru * math.sin(a) + rv * math.cos(a)
                lim = reach * 0.5 * min(W, D)
                if al <= 0.0 or al > lim:
                    continue
                wid = 0.9 + 1.6 * al / lim
                dent += dep * math.exp(-(ac / wid) ** 2) * _sstep(0.0, 0.18 * lim, al) * (1.0 - _sstep(0.45 * lim, lim, al))
            edge = _sstep(0.0, 0.25, g)
            dt = min(dent + _crease_at(x, y, cr_t) * edge, 0.45 * lo)
            db = min(dent + _crease_at(x, y, cr_b) * edge, 0.45 * lo)
            sew = seam_t * (1.0 - _sstep(0.0, 0.3, g))     # the sewn edge keeps a little body
            rowt.append((x, y, lo - dt + sew))
            rowb.append((x, y, -lo + db - sew))
        top.append(rowt)
        bot.append(rowb)
    return top, bot


def _seam_mesh(name, grids, floor=None, back=None, push=0.45):
    """Close a posed pillow: a slightly beaded seam ring joins its two faces; the bead is
    kept clear of the support plane / back plane it rests against."""
    ring = _rim_ring(grids[0], grids[1], push, 0.5)
    if floor is not None:
        ring = [(x, y, max(z, floor)) for x, y, z in ring]
    if back is not None:
        ring = [(x, min(y, back), z) for x, y, z in ring]
    return _shell_mesh(name, grids[0], grids[1], rims=[ring])


def _front_field(points, cell=2.5):
    f = {}
    for x, y, z in points:
        k = (int(math.floor(x / cell)), int(math.floor(z / cell)))
        if k not in f or y < f[k]:
            f[k] = y
    return f


def _field_at(f, x, z, cell=2.5):
    i, j = int(math.floor(x / cell)), int(math.floor(z / cell))
    best = None
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            v = f.get((i + di, j + dj))
            if v is not None and (best is None or v < best):
                best = v
    return best


def _lean(grids, D, th0, th1, yaw, x0, floor, pen_floor, back=None, field=None, pen_back=1.5, k=1.2, flop=0.0):
    """Pose a pillow leaning backwards (+Y): its local y runs up the slope, bent from th0
    (at the bottom edge) to th1 degrees, the top `flop` degrees tipping forward again; it
    rests on z = floor and against the plane y = back (or a front field of other pillows).
    Contacts are flattened, never crossed."""
    t0, t1, fl = math.radians(th0), math.radians(th1), math.radians(flop)

    def theta(f):
        return t0 + (t1 - t0) * f - fl * _sstep(0.6, 1.0, f)

    nst = 120
    tab = [(0.0, 0.0)]
    Y = Z = 0.0
    for i in range(nst):
        th = theta((i + 0.5) / nst)
        Y += D / nst * math.cos(th)
        Z += D / nst * math.sin(th)
        tab.append((Y, Z))

    def bend(p):
        x, yl, n = p
        f = min(max((yl + 0.5 * D) / D, 0.0), 1.0)
        i = min(int(f * nst), nst - 1)
        w = f * nst - i
        Yc = tab[i][0] + (tab[i + 1][0] - tab[i][0]) * w
        Zc = tab[i][1] + (tab[i + 1][1] - tab[i][1]) * w
        th = theta(f)
        return (x, Yc - n * math.sin(th), Zc + n * math.cos(th))

    gs = [[[bend(p) for p in row] for row in g] for g in grids]
    pts = [p for g in gs for row in g for p in row]
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    ca, sa = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    gs = [[[(cx + (p[0] - cx) * ca - (p[1] - cy) * sa + x0,
             cy + (p[0] - cx) * sa + (p[1] - cy) * ca, p[2]) for p in row] for row in g] for g in gs]
    pts = [p for g in gs for row in g for p in row]
    dz = floor - pen_floor - min(p[2] for p in pts)
    if field is None:
        dy = back + pen_back - max(p[1] for p in pts)
    else:
        pen = [p[1] - _field_at(field, p[0], p[2] + dz) for p in pts
               if _field_at(field, p[0], p[2] + dz) is not None]
        dy = pen_back - max(pen) if pen else 0.0

    def place(p):
        x, y, z = p[0], p[1] + dy, _floor(p[2] + dz, floor, k)
        if field is None:
            y = _ceil(y, back, k)
        else:
            fy = _field_at(field, x, z)
            if fy is not None:
                y = _ceil(y, fy - 0.1, k)
        return (x, y, z)

    return [[[place(p) for p in row] for row in g] for g in gs]


class _Duvet(object):
    """Linen duvet draped over the sheet-covered mattress (rounded box: flat top z_top,
    sides x = +-x_side, foot face y = y_foot, 4.3 cm edge radius) and over the oak rails.

    Sheet coordinates: s across (= plan x on the top), t from the foot hem toward the head.
    Beyond the flat top the cloth follows an analytic cross-section: it rolls over the
    mattress edge, hangs down the mattress side, swings out over the rounded outer top edge
    of the rail (its only contact there) and hangs a few cm down the rail's outer face, so
    no hem hovers just above the frame and no light slit is left open between mattress and
    rail. The head part is turned down (a 180 degree fold, flatter where it runs down the
    sides) and lies back on itself. Displacements: irregular skirt folds that are pinched at
    the rail contact and grow toward an uneven hem, gathered foot corners with a dropped
    dog-ear, loft variation and soft top creases; the band under the throw is pressed flat.
    rail = (x of the side rails' outer faces, y of the foot rail's outer face, rail top z,
    rail edge fillet)."""

    def __init__(self, x_side, y_foot, z_top, y_fold, band, seed, rail, below=6.0):
        self.rail = rail
        rs = 4.3
        self.rb = rs + 0.05
        self.z0 = z_top + 0.05
        self.xin = x_side - rs
        self.yin = y_foot + rs
        self.arc = 0.5 * math.pi * self.rb
        self.Dx = rail[0] - self.xin
        self.Dy = self.yin - rail[1]
        self._pc = {}
        self.dcx = self._prof(self.Dx, 0.0)[4]       # cloth length from the top edge to the rail contact
        self.dcy = self._prof(self.Dy, 0.0)[4]
        self.ds = self.dcx + below
        self.hm, self.he = 4.6, 1.3
        self.rf = self.hm + 0.8
        self.fb = 30.0
        self.S = self.xin + self.ds
        self.t0 = self.ds
        self.tf = self.t0 + (y_fold - self.yin)
        self.tn = self.tf + math.pi * self.rf
        self.T = self.tn + self.fb
        self.band = band
        self.band_d = self.dcx - 6.0              # the throw's hanging ends stop about here
        self.yref = y_fold
        self.nl = _Noise(seed, 8, (24.0, 80.0))
        self.nl2 = _Noise(seed + 9, 7, (20.0, 55.0))
        self.nph = _Noise(seed + 1, 5, (35.0, 110.0), dims=1)
        self.nam = _Noise(seed + 2, 5, (25.0, 70.0), dims=1)
        self.nhem = _Noise(seed + 4, 5, (22.0, 70.0), dims=1)
        self.nhem2 = _Noise(seed + 5, 5, (13.0, 26.0), dims=1)     # >= 4 samples per wave on a 3.3 cm grid
        self.nd = [_Noise(seed + 30 + k, 6, (16.0, 44.0), dims=3) for k in range(3)]
        rnd = random.Random(seed + 3)
        self.ridges = [self._ridge_spec(rnd, self.yin + 8.0, y_fold - 8.0) for _ in range(18)]
        self.ridges2 = [self._ridge_spec(rnd, y_fold - self.fb + 4.0, y_fold - 3.0, 0.6) for _ in range(3)]
        # narrow wrinkles (1-2 cm wide, 8-28 cm long, 0.4-1.1 cm high) on top of
        # the broad ridges: the broad ones alone were too gentle to catch the
        # light, and the duvet read as a smooth foam slab
        self.wrinkles = [self._wrinkle_spec(rnd, self.yin + 4.0, y_fold - 4.0) for _ in range(46)]

    # ------------------------------------------------------------ cross-section of the drop
    def _path_k(self, k):
        """Inner-face cross-section (r outward from the edge-roll centre, z) for a rail whose
        outer face is D = k / 4 cm out: polyline, cumulative length, outward normals and the
        length to the rail contact."""
        p = self._pc.get(k)
        if p is not None:
            return p
        D = k / 4.0
        rb, z0 = self.rb, self.z0
        pts = [(rb * math.sin(0.5 * math.pi * i / 12.0), z0 - rb * (1.0 - math.cos(0.5 * math.pi * i / 12.0)))
               for i in range(13)]
        zt, fil = self.rail[2], self.rail[3]
        rho = fil + 0.35                       # the cloth rides just clear of the rounded rail edge
        cx, cz = D - fil, zt - fil
        ph = math.radians(62.0)                # it meets the edge sloping 62 degrees
        T = (cx + rho * math.sin(ph), cz + rho * math.cos(ph))
        tg = (math.cos(ph), -math.sin(ph))
        S = pts[-1]
        H = S[1] - T[1]
        P1 = (S[0], S[1] - 0.5 * H)
        P2 = (T[0] - 0.3 * H * tg[0], T[1] - 0.3 * H * tg[1])
        for i in range(1, 25):
            u = i / 24.0
            a, b, c, e = (1 - u) ** 3, 3 * (1 - u) ** 2 * u, 3 * (1 - u) * u * u, u ** 3
            pts.append((a * S[0] + b * P1[0] + c * P2[0] + e * T[0], a * S[1] + b * P1[1] + c * P2[1] + e * T[1]))
        ic = len(pts) - 1
        for i in range(1, 7):
            q = ph + (0.5 * math.pi - ph) * i / 6.0
            pts.append((cx + rho * math.sin(q), cz + rho * math.cos(q)))
        pts.append((cx + rho, cz - 80.0))
        L = [0.0]
        for (r0, h0), (r1, h1) in zip(pts[:-1], pts[1:]):
            L.append(L[-1] + math.hypot(r1 - r0, h1 - h0))
        ns = []
        for i in range(len(pts)):
            a, b = pts[max(i - 1, 0)], pts[min(i + 1, len(pts) - 1)]
            dr, dz = b[0] - a[0], b[1] - a[1]
            ln = math.hypot(dr, dz) or 1.0
            ns.append((-dz / ln, dr / ln))
        p = (L, pts, ns, L[ic])
        self._pc[k] = p
        return p

    @staticmethod
    def _eval(p, d):
        L, pts, ns, dc = p
        i = bisect.bisect_right(L, d) - 1
        i = max(0, min(i, len(L) - 2))
        f = (d - L[i]) / (L[i + 1] - L[i])
        f = max(f, 0.0)
        (r0, z0), (r1, z1) = pts[i], pts[i + 1]
        (a0, b0), (a1, b1) = ns[i], ns[i + 1]
        fn = min(f, 1.0)
        nr, nz = a0 + (a1 - a0) * fn, b0 + (b1 - b0) * fn
        ln = math.hypot(nr, nz) or 1.0
        return r0 + (r1 - r0) * f, z0 + (z1 - z0) * f, nr / ln, nz / ln, dc

    def _prof(self, D, d):
        """(r, z, n_r, n_z, contact length) at cloth length d for rail distance D."""
        f = D * 4.0
        k = int(math.floor(f))
        a = f - k
        r0, z0, nr0, nz0, c0 = self._eval(self._path_k(k), d)
        if a < 1e-4:
            return r0, z0, nr0, nz0, c0
        r1, z1, nr1, nz1, c1 = self._eval(self._path_k(k + 1), d)
        nr, nz = nr0 + (nr1 - nr0) * a, nz0 + (nz1 - nz0) * a
        ln = math.hypot(nr, nz) or 1.0
        return r0 + (r1 - r0) * a, z0 + (z1 - z0) * a, nr / ln, nz / ln, c0 + (c1 - c0) * a

    def jitter(self, p):
        """Small 3-D waviness of the whole cover (in place of a Noise modifier, so the throw
        can lie on exactly the same surface)."""
        x, y, z = p
        return (x + 0.2 * self.nd[0](x, y, z), y + 0.2 * self.nd[1](x, y, z), z + 0.26 * self.nd[2](x, y, z))

    def rf_at(self, d):
        """Radius of the turned-down fold: rounder on the top, flatter down the sides."""
        return self.rf * (1.0 - 0.42 * _sstep(0.0, self.arc, d))

    def _ridge_spec(self, rnd, y0, y1, scale=1.0):
        """A soft crease / ridge in the cover: centre, direction, half length, width, height.
        Most run diagonally in from the long edges, as when a duvet is pulled straight."""
        side = rnd.choice((-1.0, 1.0))
        cx = side * rnd.uniform(0.25, 0.95) * self.xin
        cy = rnd.uniform(y0, max(y0 + 1.0, y1))
        a = rnd.uniform(15.0, 60.0) * (1.0 if rnd.random() < 0.5 else -1.0) + (90.0 if rnd.random() < 0.25 else 0.0)
        ang = math.radians(a)
        # 1.2-2.6 cm: at 0.55-1.35 the creases vanished at viewing distance and
        # the duvet read as a tidy inflated slab
        amp = (1.0 if rnd.random() < 0.7 else -0.6) * rnd.uniform(1.2, 2.6) * scale
        return (cx, cy, math.cos(ang), math.sin(ang), rnd.uniform(25.0, 70.0), rnd.uniform(4.0, 8.0), amp)

    def _wrinkle_spec(self, rnd, y0, y1):
        cx = rnd.uniform(-0.98, 0.98) * self.xin
        cy = rnd.uniform(y0, max(y0 + 1.0, y1))
        a = math.radians(rnd.uniform(0.0, 180.0))
        amp = (1.0 if rnd.random() < 0.65 else -0.8) * rnd.uniform(0.4, 1.1)
        return (cx, cy, math.cos(a), math.sin(a), rnd.uniform(8.0, 28.0), rnd.uniform(0.9, 1.9), amp)

    @staticmethod
    def _ridge(x, y, ridges):
        r = 0.0
        for cx, cy, ux, uy, ln, sg, amp in ridges:
            dx, dy = x - cx, y - cy
            a = dx * ux + dy * uy
            if abs(a) > ln:
                continue
            c = -dx * uy + dy * ux
            if abs(c) > 3.0 * sg:
                continue
            r += amp * math.exp(-(c / sg) ** 2) * (1.0 - (a / ln) ** 2) ** 2
        return r

    def band_mask(self, s, y):
        """1 under the (askew) throw band, fading out over 7 cm."""
        if not self.band:
            return 0.0
        b0, b1, skew = self.band
        yy = y - s * skew
        return _sstep(b0 - 7.0, b0, yy) * (1.0 - _sstep(b1, b1 + 7.0, yy))

    def support(self, s, t):
        """Unfolded base point P, outward normal N, cloth length d beyond the flat top, zone
        (0 top, 1 side/foot, 2 corner), corner angle, perimeter coordinate e and the cloth
        length to the rail contact there."""
        xin, yin = self.xin, self.yin
        dx = abs(s) - xin
        sx = 1.0 if s >= 0.0 else -1.0
        dy = self.t0 - t
        y = yin + (t - self.t0)
        C = 8.0
        base_e = self.yref - yin
        if dx > 0.0 and dy > 0.0:
            # the square corner of the sheet maps smoothly (elliptical grid mapping) onto the
            # quarter disc hanging round the corner: no crease along the diagonal; the corner
            # tip has a little more cloth, so it drops lower (dog-ear)
            gx, gy = min(dx / self.ds, 1.0), min(dy / self.ds, 1.0)
            u = gx * math.sqrt(1.0 - 0.5 * gy * gy)
            v = gy * math.sqrt(1.0 - 0.5 * gx * gx)
            rr = math.hypot(u, v)
            d = self.ds * rr * (1.0 + 0.1 * (2.0 * gx * gy) ** 2)
            nx, ny = sx * u / rr, -v / rr
            qx, qy = sx * xin, yin
            th = math.atan2(v, u)
            zone = 2
            D = min(self.Dx / max(abs(nx), 1e-6), self.Dy / max(abs(ny), 1e-6))
            if sx > 0:
                e = base_e + th * C
            else:
                e = base_e + 0.5 * math.pi * C + 2.0 * xin + (0.5 * math.pi - th) * C
        elif dx > 0.0:
            d, nx, ny, qx, qy, th, zone, D = dx, sx, 0.0, sx * xin, y, 0.0, 1, self.Dx
            e = (self.yref - y) if sx > 0 else base_e + math.pi * C + 2.0 * xin + (y - yin)
        elif dy > 0.0:
            d, nx, ny, qx, qy, th, zone, D = dy, 0.0, -1.0, s, yin, 0.5 * math.pi, 1, self.Dy
            e = base_e + 0.5 * math.pi * C + (xin - s)
        else:
            return (s, y, self.z0), (0.0, 0.0, 1.0), 0.0, 0, 0.0, 0.0, self.dcx
        d += (1.6 * self.nhem(e) + 0.6 * self.nhem2(e)) * _sstep(self.dcx, self.ds, d)   # uneven hem
        r, z, nr, nz, dc = self._prof(D, d)
        return (qx + nx * r, qy + ny * r, z), (nx * nr, ny * nr, nz), d, zone, th, e, dc

    def drape(self, s, d, zone, th, e, y, dc):
        """Outward displacement of the skirt: soft low undulations above the rail, pinched at
        the rail contact, irregular folds growing below it, a little flare to the hem."""
        a0 = 0.35 * self.arc
        if d <= a0:
            return 0.0
        up = _sstep(a0, dc - 6.0, d) * (1.0 - _sstep(dc - 6.0, dc - 0.5, d))
        lo = _sstep(dc + 0.3, dc + 5.0, d)
        mod = 0.55 + 0.9 * (0.5 + 0.5 * self.nam(e))
        f = (0.62 * math.sin(2.0 * math.pi * e / 23.0 + 2.6 * self.nph(e)) +
             0.38 * math.sin(2.0 * math.pi * e / 37.0 + 1.3 + 2.2 * self.nph(e + 40.0)))
        w = (0.9 * up + 2.3 * lo) * mod * (0.5 + 0.5 * f) ** 1.3
        flare = 0.8 * _sstep(dc, self.ds + 3.0, d) ** 1.5
        if zone == 2:      # excess cloth gathers into one soft bulge with a shallow fold
            c = math.sin(2.0 * th) ** 2
            w += c * (0.3 * up + lo * (0.9 + 0.6 * (0.5 + 0.5 * math.cos(3.0 * th + 0.4))))
        m = self.band_mask(s, y) * (1.0 - _sstep(self.band_d, self.band_d + 5.0, d))
        return flare + w * (1.0 - m)

    def thick(self, s, t, P, zone, layer, d=0.0, dc=None):
        bd = min(self.S - abs(s), t, self.T - t)
        h = self.he + (self.hm - self.he) * _sstep(0.0, 9.0, bd)
        if d > 0.0:          # the fill thins where the cover rolls over the edge and hangs
            h *= 1.0 - 0.27 * _sstep(0.0, self.arc, d)
            if dc is not None:
                h *= 1.0 - 0.3 * math.exp(-((d - dc) / 3.5) ** 2)     # pressed over the rail edge
        x, y, z = P
        m = self.band_mask(s, y) if layer == 0 else 0.0
        nz = (self.nl if layer == 0 else self.nl2)(x, y + 0.6 * z)
        r = 0.0
        if zone == 0:
            r = self._ridge(x, y, self.ridges if layer == 0 else self.ridges2) * _sstep(0.0, 6.0, bd)
            if layer == 0:
                r += self._ridge(x, y, self.wrinkles) * _sstep(0.0, 4.0, bd)
        return h * (1.0 + 0.28 * nz * (1.0 - m)) * (1.0 - 0.14 * m) + r * (1.0 - m)

    def outer(self, s, t):
        """Lower layer: outer point, base point and support normal."""
        P, N, d, zone, th, e, dc = self.support(s, t)
        w = self.drape(s, d, zone, th, e, P[1], dc)
        B = (P[0] + N[0] * w, P[1] + N[1] * w, P[2] + N[2] * w)
        h = self.thick(s, t, P, zone, 0, d, dc)
        if t > self.tf - 12.0:      # ease into the fold's inner radius
            h = min(h, self.rf_at(d) - 0.35 + 0.3 * (self.tf - t))
        return (B[0] + N[0] * h, B[1] + N[1] * h, B[2] + N[2] * h), B, N

    def point(self, s, t):
        """(outer, base) point of the duvet at sheet coords (s, t), all three regions."""
        if t <= self.tf:
            O, B, N = self.outer(s, t)
            return O, B
        if t < self.tn:
            P, N, d, zone, th, e, dc = self.support(s, self.tf)
            w = self.drape(s, d, zone, th, e, P[1], dc)
            rf = self.rf_at(d)
            phi = math.pi * (t - self.tf) / (self.tn - self.tf)
            sp, cp = math.sin(phi), math.cos(phi)
            rr = w + rf * (1.0 - cp)
            B = (P[0] + N[0] * rr, P[1] + N[1] * rr + rf * sp, P[2] + N[2] * rr)
            off = (N[0] * cp, N[1] * cp - sp, N[2] * cp)
            h = min(self.thick(s, t, P, zone, 0, d, dc), rf - 0.35)   # inner side of the fold stays open
            return (B[0] + off[0] * h, B[1] + off[1] * h, B[2] + off[2] * h), B
        # down the sides the flap is pulled into a trapezoid: its free edge slants toward the fold
        sq = max(0.55, 1.0 - 0.3 * max(0.0, abs(s) - self.xin) / self.fb)
        tp = self.tf - (t - self.tn) * sq
        bl = _sstep(0.0, 12.0, self.tf - tp)
        kk = 1.0 - 0.08 * _sstep(0.0, 22.0, self.tf - tp)     # the turned-down flap hangs a little shorter
        sc = s
        if abs(s) > self.xin:
            sc = math.copysign(self.xin + (abs(s) - self.xin) * kk, s)
        P, N, d, zone, th, e, dc = self.support(sc, tp)
        w = self.drape(sc, d, zone, th, e, P[1], dc)
        rf = self.rf_at(d)
        hl = self.thick(sc, tp, P, zone, 0, d, dc)
        hu = ((1.0 - bl) * min(self.thick(s, t, P, zone, 0, d, dc), rf - 0.35) +
              bl * self.thick(s, t, P, zone, 1, d, dc))
        infl = (1.0 - bl) * 2.0 * rf + bl * (hl + 0.3 + hu)
        B = (P[0] + N[0] * (w + infl), P[1] + N[1] * (w + infl), P[2] + N[2] * (w + infl))
        return (B[0] - N[0] * hu, B[1] - N[1] * hu, B[2] - N[2] * hu), B

    def s_samples(self):
        xin, arc, dc = self.xin, self.arc, self.dcx

        def step(x):
            if x < xin - 8.0:
                return 1.1                          # the narrow wrinkles need it (was 3.3)
            if x < xin:
                return 1.1
            if x < xin + arc:
                return 0.85
            if abs(x - (xin + dc)) < 2.5:
                return 0.7
            return 1.55

        half = _pieces([0.0, xin - 8.0, xin, xin + arc, xin + dc - 2.5, xin + dc + 2.5, self.S], step)
        return [-v for v in reversed(half[1:])] + half

    def t_samples(self):
        edges = []
        if self.band:
            sk = abs(self.band[2]) * self.S
            for b in self.band[:2]:
                tb = self.t0 + (b - self.yin)
                edges.append((tb - sk - 7.0, tb + sk + 7.0))
        tc = self.t0 - self.dcy

        def step(t):
            if t < self.t0 - self.arc:
                return 0.7 if abs(t - tc) < 2.5 else 1.55
            if t < self.t0:
                return 0.85
            if self.tf <= t < self.tn:
                return math.pi * self.rf / 14.0
            if t >= self.tn:
                return 1.1 if t > self.T - 5.0 else 1.1
            if t < self.t0 + 6.0 or t > self.tf - 8.0:
                return 2.2
            for a, b in edges:
                if a < t < b:
                    return 2.4
            return 3.3

        return _pieces([0.0, max(0.0, tc - 2.5), tc + 2.5, self.t0 - self.arc, self.t0, self.tf, self.tn, self.T],
                       step)

    def clear(self, p):
        """Safety net: no point of the cover may end up inside an oak rail."""
        xo, yo, zt = self.rail[0], self.rail[1], self.rail[2]
        x, y, z = p
        if z < zt + 0.2:
            ax = abs(x)
            if ax < xo + 0.15 and y > yo - 0.15 and (ax > xo - 8.0 or y < yo + 8.0):
                if xo + 0.15 - ax < y - (yo - 0.15):
                    x = math.copysign(xo + 0.15, x)
                else:
                    y = yo - 0.15
        return (x, y, z)

    def build(self, name):
        ss, ts, top, bot = self.grids()
        return _shell_mesh(name, top, bot, rims=[_rim_ring(top, bot, 0.42, 0.3), _rim_ring(top, bot, 0.42, 0.7)])

    def grids(self):
        """Sample positions and the outer / base grids, corners relaxed, rails kept clear."""
        ss, ts = self.s_samples(), self.t_samples()
        top, bot = [], []
        for s in ss:
            rt_, rb_ = [], []
            for t in ts:
                O, B = self.point(s, t)
                rt_.append(O)
                rb_.append(B)
            top.append(rt_)
            bot.append(rb_)
        # relax the gathered foot corners a little so their folds stay rounded
        ii = [i for i, s in enumerate(ss) if abs(s) > self.xin + 0.3 * self.arc]
        jj = [j for j, t in enumerate(ts) if t < self.t0 - 0.3 * self.arc]
        for g in (top, bot):
            _relax(g, ii, jj, 3, 0.45)
        for i in range(len(ss)):
            for j in range(len(ts)):
                top[i][j] = self.clear(self.jitter(top[i][j]))
                bot[i][j] = self.clear(self.jitter(bot[i][j]))
        return ss, ts, top, bot


def _throw(duv, y_c, B, Hs, seed, name):
    """Velvet throw folded into a band (front edge folded, back edge showing the layer
    step) lying across the duvet at plan y_c and draping over both sides. Where it hangs
    it breaks into a few soft flutes, spreads a little and ends in an uneven, rounded hem
    (its outer corners hang lowest); it lies on the duvet's own (jittered) surface."""
    nzw = _Noise(seed, 5, (9.0, 30.0), dims=1)
    nze = _Noise(seed + 1, 5, (14.0, 45.0), dims=1)
    nzn = _Noise(seed + 2, 6, (7.0, 22.0))
    nzr = _Noise(seed + 3, 6, (9.0, 20.0))
    rnd = random.Random(seed + 4)
    flute = dict((sd, (rnd.uniform(19.0, 24.0), rnd.uniform(0.0, 2.0 * math.pi), rnd.uniform(3.2, 4.0),
                       rnd.uniform(8.5, 11.0), rnd.uniform(0.0, 2.0 * math.pi))) for sd in (-1, 1))
    R = 0.5 * Hs
    prof = [(-0.5 * B + R, 0.0), (-0.25 * B, 0.0), (0.0, 0.0), (0.25 * B, 0.0), (0.5 * B - 0.6, 0.0),
            (0.5 * B, 0.32 * Hs), (0.5 * B - 0.45, 0.5 * Hs), (0.5 * B - 2.5, 0.53 * Hs),
            (0.5 * B - 2.85, 0.82 * Hs), (0.5 * B - 3.3, Hs), (0.25 * B, Hs), (0.0, Hs),
            (-0.25 * B, Hs), (-0.5 * B + R, Hs), (-0.5 * B, R)]
    xin, arc = duv.xin, duv.arc
    smax = xin + duv.band_d
    s_end = smax - 1.5                     # the hem rounds off over the last 1.5 cm

    def step(x):
        ax = abs(x)
        if ax < xin - 6.0:
            return 4.5
        if ax < xin + arc + 1.0:
            return 1.3
        if ax > s_end - 0.3:
            return 0.38
        return 1.5

    ss = _pieces([-smax, -s_end, -xin - arc - 1.0, -xin + 6.0, xin - 6.0, xin + arc + 1.0, s_end, smax], step)
    skew = math.tan(math.radians(3.5))
    rings = []
    for s in ss:
        side = 1 if s > 0.0 else -1
        ax = abs(s)
        hang = _sstep(xin + 0.6 * arc, smax, ax)
        hf = _sstep(xin + 0.3 * arc, smax - 3.0, ax)          # the flutes form as soon as it tips over
        over = _sstep(xin - 4.0, xin + arc, ax)
        lam, ph0, famp, lam2, ph2 = flute[side]
        q = max(0.0, (ax - s_end) / (smax - s_end))
        close = 0.8 * (1.0 - math.sqrt(max(0.0, 1.0 - q * q)))     # rounds off, leaving a soft hem face
        ring = []
        for b, n in prof:
            # band slightly askew, edges wavering; where it hangs, the flutes take up width
            # lying fabric cannot waver sideways much: at 1.7 cm (and a 1.6 cm bow)
            # the band's edges read as a die-cut scallop
            bb = b * (1.0 + 0.02 * nze(s) - 0.08 * hf ** 1.5) + 0.35 * nze(s + 57.0)
            y = y_c + bb + s * skew + 0.5 * math.sin(0.5 * math.pi * s / smax)
            fb_ = 2.0 * b / B
            tw = 0.02 * side * (ax - xin)                     # the folds run slightly askew
            wave = (0.72 * (0.5 + 0.5 * math.sin(2.0 * math.pi * bb / lam + ph0 + tw)) +
                    0.28 * (0.5 + 0.5 * math.sin(2.0 * math.pi * bb / lam2 + ph2 - 1.5 * tw)))
            # uneven hem: the band's outer corners and the fold crests hang lowest
            ext = hang * hang * (3.6 * fb_ * fb_ + 1.6 * nze(0.8 * b + 13.0 * side) + 0.8 * (wave - 0.5))
            O, _, N = duv.outer(s + side * ext, duv.t0 + (y - duv.yin))
            O = duv.jitter(O)
            f = n / Hs
            nm = n + (0.5 * Hs - n) * close                                         # rounded hem
            fl = hf ** 1.4 * famp * wave ** 1.4                                     # heavy pipe folds
            nn = (0.22 + nm + 0.16 * max(0.0, nzw(s)) + 0.22 * nzn(s, bb) * f
                  + 0.5 * f * max(0.0, nzr(s, 0.35 * bb)) * (1.0 - hang)      # soft transverse ripples on top
                  + 0.3 * over * (0.5 + 0.5 * math.sin(0.55 * bb))           # rolling over the edge
                  + 0.4 * hang + fl)                                          # stands off a little, flutes
            ring.append((O[0] + N[0] * nn, O[1] + N[1] * nn, O[2] + N[2] * nn))
        rings.append(ring)
    return _sweep(name, rings, caps=True, push=0.25)


def _box_cushion(name, w, d, h, z0, crown, bulge, rc, seed):
    """Piped box cushion on z = z0 over a rounded-rectangle plan (w x d, corner radius rc):
    crowned top panel and flat bottom panel joined by a boxing strip that bulges out and is
    held in toward the sewn corners (smoothly, all the way round the corner arcs).
    Returns (mesh, seam_z_top, seam_z_bottom)."""
    nz = _Noise(seed, 6, (14.0, 50.0))
    A, Bh = 0.5 * w, 0.5 * d
    cx, cy = A - rc, Bh - rc
    xs = _pieces([-A, -(cx - 1.5), cx - 1.5, A], lambda x: 0.8 if abs(x) > cx - 1.6 else 5.0)
    ys = _pieces([-Bh, -(cy - 1.5), cy - 1.5, Bh], lambda y: 0.8 if abs(y) > cy - 1.6 else 3.4)

    def plan(X, Y):
        px, py = abs(X) - cx, abs(Y) - cy
        if px > 0.0 and py > 0.0:          # square -> quarter disc (elliptical grid mapping)
            gx, gy = px / rc, py / rc
            return (math.copysign(cx + rc * gx * math.sqrt(1.0 - 0.5 * gy * gy), X),
                    math.copysign(cy + rc * gy * math.sqrt(1.0 - 0.5 * gx * gx), Y))
        return X, Y

    top, bot = [], []
    for X in xs:
        rt_, rb_ = [], []
        for Y in ys:
            x, y = plan(X, Y)
            u, v = X / A, Y / Bh
            # crowned, slightly uneven, with two faint dips where people sit
            dip = 0.35 * (math.exp(-((x - 0.25 * w) / 14.0) ** 2) + math.exp(-((x + 0.25 * w) / 14.0) ** 2))
            c = ((crown * (1.0 - abs(u) ** 2.4) - dip) * (1.0 - abs(v) ** 2.0)
                 + 0.18 * nz(x, y) * (1.0 - abs(u) ** 6) * (1.0 - abs(v) ** 6))
            rt_.append((x, y, z0 + h + max(c, 0.0)))
            rb_.append((x, y, z0))
        top.append(rt_)
        bot.append(rb_)
    nu_, nv_ = len(top), len(top[0])
    rings = []
    for f, bl in ((0.18, 0.62 * bulge), (0.5, bulge), (0.82, 0.62 * bulge)):
        ring = []
        for (i, j) in _border(nu_, nv_):
            x, y, _ = top[i][j]
            px, py = abs(x) - cx, abs(y) - cy
            if px > 1e-6 and py > 1e-6:
                ln = math.hypot(px, py)
                ox, oy, dist = math.copysign(px / ln, x), math.copysign(py / ln, y), 0.0
            elif i in (0, nu_ - 1):
                ox, oy, dist = math.copysign(1.0, x), 0.0, max(0.0, cy - abs(y))
            else:
                ox, oy, dist = 0.0, math.copysign(1.0, y), max(0.0, cx - abs(x))
            cu = 1.0 - _sstep(0.0, 2.2 * rc, dist)        # held in at the sewn corners
            off = bl * (1.0 - 0.7 * cu)
            zz = z0 + (1.0 - f) * h
            ring.append((x + ox * off, y + oy * off, zz + 0.1 * nz(x + 31.0, y) * (1.0 - cu)))
        rings.append(ring)
    return _shell_mesh(name, top, bot, rims=rings), z0 + h, z0


def _channel(x0, x1, z0, z1, y_back, depth, seed, nu=7, nv=9):
    """One vertical upholstered channel: convex padded front, flat back on y_back."""
    nz = _Noise(seed, 5, (10.0, 40.0))
    us = [math.sin(0.5 * math.pi * (-1.0 + 2.0 * i / (nu - 1))) for i in range(nu)]
    vs = [math.sin(0.5 * math.pi * (-1.0 + 2.0 * j / (nv - 1))) for j in range(nv)]
    top, bot = [], []
    for u in us:
        rt_, rb_ = [], []
        for v in vs:
            x = x0 + 0.5 * (u + 1.0) * (x1 - x0)
            z = z0 + 0.5 * (v + 1.0) * (z1 - z0)
            n = depth * (1.0 - 0.5 * abs(u) ** 3) * (1.0 - 0.5 * abs(v) ** 10) * (1.0 + 0.03 * nz(x, z))
            rt_.append((x, y_back - n, z))
            rb_.append((x, y_back, z))
        top.append(rt_)
        bot.append(rb_)
    return top, bot


# ====================================================================== bed
def build_bed(width=160, length=200):
    """Upholstered Japandi bed for a width x length mattress (works for 140-180 widths)."""
    W, L = float(width), float(length)
    nodes = []

    def add(node, mat, tile, name):
        node.name = name
        nodes.append(kit.part(node, mat, tile))
        return node

    CLR, RT, HB_BACK, HB_CH = 1.2, 3.8, 5.0, 4.5
    Wf = W + 2.0 * (CLR + RT)
    Ltot = RT + CLR + L + CLR + HB_CH + HB_BACK
    y_back = 0.5 * Ltot
    y_bb = y_back - HB_BACK          # backboard front face (channels sit on it)
    y_hb = y_bb - HB_CH              # channel crown plane
    y_mh = y_hb - CLR                # mattress head end
    y_mf = y_mh - L                  # mattress foot end
    y_ff = -0.5 * Ltot               # frame foot face
    Z_R0, Z_R1 = 21.0, 36.0          # rails
    Z_M0, Z_M1 = 33.0, 55.0          # mattress
    Z_S = Z_M1 + 0.3                 # fitted-sheet top
    HB_TOP = 120.0
    seed = int(W * 7 + L)

    # ---------------------------------------------------------------- oak frame
    rl = y_bb - (y_ff + RT)
    ry = y_ff + RT + 0.5 * rl
    add(_cb(Wf, RT, Z_R1 - Z_R0, 0.6, 0.0, y_ff + 0.5 * RT, Z_R0), "wood_light", 110, "Bed_FootRail")
    for sx in (-1.0, 1.0):
        add(_cb(RT, rl, Z_R1 - Z_R0, 0.6, sx * (0.5 * Wf - 0.5 * RT), ry, Z_R0), "wood_light", 110, "Bed_SideRail")
        add(_cb(4.0, rl - 1.0, 3.0, 0.3, sx * (0.5 * Wf - RT - 2.0), ry, Z_M0 - 5.0, fs=1),
            "wood_light", 110, "Bed_Ledger")
        # corner legs, flush under the rail corners, tapering to the floor
        add(_leg(sx * (0.5 * Wf - 3.4), y_ff + 3.4, Z_R0, 5.6, 4.0), "wood_light", 110, "Bed_Leg")
        add(_leg(sx * (0.5 * Wf - 3.1), y_back - 0.5 * HB_BACK, Z_R0, 5.0, 3.8), "wood_light", 110, "Bed_Leg")
    n_sl = max(8, int(round(rl / 13.5)))
    pitch = (rl - 3.0) / n_sl
    for k in range(n_sl):
        add(_cb(Wf - 2.0 * RT - 0.4, 6.5, 2.0, 0.3, 0.0, y_ff + RT + 1.5 + pitch * (k + 0.5), Z_M0 - 2.0, fs=1),
            "wood_light", 110, "Bed_Slat")
    add(_cb(4.0, rl - 0.4, 8.0, 0.4, 0.0, ry, Z_M0 - 10.0, fs=1), "wood_light", 110, "Bed_CentreBeam")
    for f in (-0.25, 0.25):
        add(_leg(0.0, ry + f * rl, Z_M0 - 10.0, 4.0, 3.2), "wood_light", 110, "Bed_CentreLeg")

    # ---------------------------------------------------------------- headboard
    add(_cb(Wf, HB_BACK, HB_TOP - Z_R0, 1.5, 0.0, y_back - 0.5 * HB_BACK, Z_R0, fs=3),
        "upholstery", 30, "Bed_Headboard")
    n_ch = max(3, int(round(Wf / 42.0)))
    gap = 0.3
    cw = (Wf - gap * (n_ch - 1)) / n_ch
    for k in range(n_ch):
        x0 = -0.5 * Wf + k * (cw + gap)
        top, bot = _channel(x0, x0 + cw, Z_R1 + 2.0, HB_TOP - 1.0, y_bb, HB_CH, seed + 40 + k)
        ch = _shell_mesh("Bed_HeadboardChannel", top, bot, rims=[_rim_ring(top, bot, 0.3)])
        kit.soften(ch, noise=(22.0, 0.06, 0.1), smooth=1, seed=seed + k)
        add(ch, "upholstery", 30, "Bed_HeadboardChannel")

    # ---------------------------------------------------------------- mattress + fitted sheet
    y_mc = 0.5 * (y_mf + y_mh)
    add(_cb(W, L, Z_M1 - Z_M0, 4.0, 0.0, y_mc, Z_M0, fs=3), "bedding", 25, "Bed_Mattress")
    sheet = _cb(W + 0.6, L + 0.6, Z_M1 - Z_M0 + 0.6, 4.3, 0.0, y_mc, Z_M0 - 0.3, fs=3, ws=12, ls=26, hs=6)
    _cut_below(sheet, Z_M0 + 1.0)

    # ---------------------------------------------------------------- sleeping pillows
    Wp = min(75.0, 0.5 * (W - 10.0))
    pfront = []
    for k, sx in enumerate((-1.0, 1.0)):
        # finer grid (creases are 2-4 cm wide: 21 x 15 smoothed them away), deeper
        # creases and less loft: they read as moulded foam
        g = _pillow(Wp, 50.0, 17.0, seed + 11 + 7 * k, nu=35, nv=25, pinch=(0.08, 0.11), wrinkle=1.2, crease=1.6)
        g = _lean(g, 50.0, 46.0 + 3.0 * k, 84.0 - 2.0 * k, sx * 1.4, sx * (0.5 * Wp + 1.3) + 0.6 * k,
                  Z_S, 1.5, back=y_hb, pen_back=1.8, flop=16.0 + 4.0 * k)
        m = _seam_mesh("Bed_Pillow", g, floor=Z_S, back=y_hb)
        kit.soften(m, noise=(18.0, 0.22, 0.22), smooth=1, seed=seed + 5)
        add(m, "bedding", 25, "Bed_Pillow")
        pfront.extend(p for row in g[0] for p in row)
        pfront.extend(_rim_ring(g[0], g[1], 0.45, 0.5))      # the seam bead too

    # ---------------------------------------------------------------- scatter cushions
    Wc = 45.0 if W >= 155.0 else 42.0
    field = _front_field(pfront)
    cpts = []
    for k, sx in enumerate((-1.0, 1.0)):
        g = _pillow(Wc, Wc, 16.0, seed + 31 + 5 * k, nu=27, nv=27, pinch=(0.09, 0.09), ex=(2.6, 2.6),
                    wrinkle=0.9, crease=1.2)
        g = _lean(g, Wc, 40.0 + 5.0 * k, 60.0 + 3.0 * k, -sx * 3.5, sx * (0.5 * Wc + 1.2) - 1.0 * k,
                  Z_S, 1.0, field=field, pen_back=1.4)
        m = _seam_mesh("Bed_Cushion", g, floor=Z_S)
        kit.soften(m, noise=(18.0, 0.2, 0.2), smooth=1, seed=seed + 6)
        add(m, "cushion", 25, "Bed_Cushion")
        cpts.extend(p for gg in g for row in gg for p in row)

    # ---------------------------------------------------------------- duvet + throw
    low = [p[1] for p in cpts if p[2] < Z_S + 13.0]
    y_front = min(low) if low else y_hb - 60.0
    rf = 4.6 + 0.8
    y_fold = y_front - 1.2 - rf
    # the sheet-covered mattress sides plump out a few mm between the rounded edges where
    # the duvet leaves them bare (head end), with a slight unevenness along the length
    hx, nsh = 0.5 * W + 0.3, _Noise(seed + 15, 5, (25.0, 70.0), dims=1)

    def plump(x, y, z):
        if abs(x) < hx - 2.5 or z < Z_M0 + 1.0:
            return (x, y, z)
        u = min(max((z - (Z_M0 + 3.0)) / (Z_S - 4.3 - (Z_M0 + 3.0)), 0.0), 1.0)
        b = 0.42 * math.sin(math.pi * u) * (1.0 + 0.35 * nsh(y)) * _sstep(y_fold + 8.0, y_fold + 20.0, y)
        return (x + math.copysign(b, x), y, z)

    _deform(sheet, plump)
    kit.soften(sheet, noise=(22.0, 0.12, 0.1), smooth=0, seed=seed + 2)
    add(sheet, "bedding", 25, "Bed_FittedSheet")
    Bt, Ht = 48.0, 2.6
    y_c = y_mf + 4.0 + 33.0
    duv = _Duvet(0.5 * W + 0.3, y_mf - 0.3, Z_S, y_fold,
                 (y_c - 0.5 * Bt - 1.0, y_c + 0.5 * Bt + 1.0, math.tan(math.radians(3.5))), seed + 70,
                 rail=(0.5 * Wf, y_ff, Z_R1, 0.6))
    dv = duv.build("Bed_Duvet")
    # sampled at 0.6-3 cm, so the folds and creases are real geometry (no TurboSmooth); its
    # waviness is analytic (_Duvet.jitter) so the throw can follow it, the modifier noise is a whisper
    kit.soften(dv, noise=(30.0, 0.05, 0.05), smooth=0, seed=seed + 7)
    add(dv, "linen", 12, "Bed_Duvet")      # washed-linen weave, not 30 cm hessian slubs
    th = _throw(duv, y_c, Bt, Ht, seed + 90, "Bed_Throw")
    kit.soften(th, noise=(30.0, 0.05, 0.05), smooth=1, seed=seed + 7)
    add(th, "velvet", 25, "Bed_Throw")
    return kit.group("Bed", nodes)


# ====================================================================== nightstand
def build_nightstand():
    """45 x 38 x 50 oak bedside table: slab top, one flush drawer with 3 mm gaps and a
    brass knob, open niche below, four tapered legs."""
    W, D, H = 45.0, 38.0, 50.0
    nodes = []

    def add(node, mat, tile, name):
        node.name = name
        nodes.append(kit.part(node, mat, tile))
        return node

    T, S, LEG, OV, G = 2.2, 1.8, 14.0, 0.6, 0.3
    cw, cd = W - 2.0 * OV, D - OV
    cy = -0.5 * D + OV + 0.5 * cd
    yf = -0.5 * D + OV                     # carcass front plane
    zt = H - T                             # underside of the top
    iw = cw - 2.0 * S                      # inner width
    z_div = zt - 14.0 - S                  # divider under the drawer opening
    add(_cb(W, D, T, 0.55, 0.0, 0.0, zt, fs=3), "wood_light", 110, "Nightstand_Top")
    for sx in (-1.0, 1.0):
        add(_cb(S, cd, zt - LEG, 0.3, sx * (0.5 * cw - 0.5 * S), cy, LEG), "wood_light", 110, "Nightstand_Side")
    add(_cb(iw, cd, S, 0.25, 0.0, cy, LEG), "wood_light", 110, "Nightstand_Bottom")
    add(_cb(iw, 1.0, zt - LEG - S, 0.2, 0.0, 0.5 * D - 0.5, LEG + S), "wood_light", 110, "Nightstand_Back")
    add(_cb(iw, cd - 1.0, S, 0.25, 0.0, cy - 0.5, z_div), "wood_light", 110, "Nightstand_Shelf")
    # drawer: flush front inside the opening with 3 mm all round + hidden box behind
    fw, fh = iw - 2.0 * G, (zt - (z_div + S)) - 2.0 * G
    fz = z_div + S + G
    add(_cb(fw, S, fh, 0.25, 0.0, yf + 0.5 * S, fz, fs=2), "wood_light", 110, "Nightstand_DrawerFront")
    add(_cb(fw - 1.6, cd - S - 2.5, fh - 1.4, 0.2, 0.0, yf + S + 0.5 * (cd - S - 2.5), z_div + S, fs=1),
        "wood_light", 110, "Nightstand_DrawerBox")          # runs on the shelf below it
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            add(_leg(sx * (0.5 * cw - 1.9), cy + sy * (0.5 * cd - 1.9), LEG, 3.2, 2.4, 0.35),
                "wood_light", 110, "Nightstand_Leg")
    # mushroom knob: thin rosette, waisted neck, flat-faced head with a rounded rim
    knob = _lathe("Nightstand_Knob", [(0.0, 0.0), (0.95, 0.0), (0.98, 0.08), (0.9, 0.18), (0.5, 0.26),
                                      (0.4, 0.55), (0.42, 1.2), (0.62, 1.45), (1.25, 1.62), (1.45, 1.8),
                                      (1.47, 2.1), (1.35, 2.38), (1.0, 2.52), (0.45, 2.57), (0.0, 2.58)],
                  origin=(0.0, yf, fz + 0.5 * fh), axis=(0.0, -1.0, 0.0), segs=24)
    kit.soften(knob, smooth=1)
    add(knob, "metal_brass", 25, "Nightstand_Knob")
    return kit.group("Nightstand", nodes)


# ====================================================================== table lamp
def build_table_lamp():
    """45 cm table lamp: glazed ceramic gourd base, brass collar/socket/spider, warm
    globe bulb, tapered linen drum shade with rolled rims."""
    nodes = []

    def add(node, mat, tile, name, smooth=1):
        if smooth:
            kit.soften(node, smooth=smooth)
        node.name = name
        nodes.append(kit.part(node, mat, tile))
        return node

    add(_lathe("Lamp_Base", [(0.0, 0.5), (4.3, 0.5), (4.75, 0.06), (4.9, 0.0), (5.9, 0.0), (6.25, 0.3),
                             (6.6, 1.2), (7.7, 3.4), (8.45, 6.6), (8.6, 9.6), (8.15, 13.0), (6.9, 16.3),
                             (5.0, 19.1), (3.35, 21.0), (2.6, 22.0), (2.45, 22.45), (2.05, 22.6),
                             (0.0, 22.6)], segs=40), "ceramic_white", 30, "Lamp_Base")
    add(_lathe("Lamp_Collar", [(0.0, 22.6), (1.75, 22.6), (1.85, 22.75), (1.85, 23.9), (1.7, 24.15),
                               (0.0, 24.15)], segs=24), "metal_brass", 25, "Lamp_Collar")
    add(_lathe("Lamp_Stem", [(0.0, 24.15), (0.45, 24.15), (0.5, 24.3), (0.5, 26.85), (0.45, 27.0),
                             (0.0, 27.0)], segs=16), "metal_brass", 25, "Lamp_Stem")
    add(_lathe("Lamp_Socket", [(0.0, 27.0), (1.45, 27.0), (1.65, 27.25), (1.65, 30.85), (1.5, 31.05),
                               (1.32, 31.12), (1.3, 31.9), (1.15, 32.1), (0.0, 32.1)], segs=24),
        "metal_brass", 25, "Lamp_Socket")
    add(_lathe("Lamp_Washer", [(1.42, 31.12), (2.75, 31.12), (2.75, 31.27), (1.42, 31.27)], segs=24,
               closed=True), "metal_brass", 25, "Lamp_Washer")
    a0 = math.asin(1.3 / 3.0)        # smooth globe on a short neck
    bulb = [(0.0, 32.1), (1.15, 32.1), (1.22, 32.45), (1.3, 32.9)]
    bulb += [(3.0 * math.sin(a0 + (math.pi - a0) * i / 16.0), 36.8 - 3.0 * math.cos(a0 + (math.pi - a0) * i / 16.0))
             for i in range(17)]
    bulb[-1] = (0.0, 39.8)
    add(_lathe("Lamp_Bulb", bulb, segs=32), "emissive_warm", 30, "Lamp_Bulb")
    shade = _lathe("Lamp_Shade", [(15.0, 24.75), (14.25, 34.9), (13.5, 44.75), (13.6, 44.9), (13.42, 45.0),
                                  (13.22, 44.88), (13.2, 44.7), (13.95, 34.9), (14.7, 24.8), (14.72, 24.6),
                                  (14.9, 24.5), (15.08, 24.6)], segs=72, closed=True)

    def seam(x, y, z):          # the glued overlap of the linen wrap, at the back
        a = math.atan2(y, x) - 0.5 * math.pi
        a = (a + math.pi) % (2.0 * math.pi) - math.pi
        r = math.hypot(x, y)
        f = 1.0 + 0.0045 * math.exp(-(a / 0.045) ** 2)
        return (x * f, y * f, z) if r > 0.0 else (x, y, z)

    _deform(shade, seam)
    add(shade, "shade", 25, "Lamp_Shade")
    ring = [(13.07 * math.cos(2 * math.pi * i / 48), 13.07 * math.sin(2 * math.pi * i / 48), 44.55)
            for i in range(48)]
    add(_tube("Lamp_SpiderRing", ring, 0.15, sides=6, closed=True), "metal_brass", 25, "Lamp_SpiderRing", 0)
    for k in range(3):
        a = math.radians(90.0 + 120.0 * k)
        ca, sa = math.cos(a), math.sin(a)
        path = [((2.6 + (12.95 - 2.6) * f) * ca, (2.6 + (12.95 - 2.6) * f) * sa, 31.2 + (44.5 - 31.2) * f)
                for f in (0.0, 0.5, 1.0)]
        add(_tube("Lamp_Spoke", path, 0.12, sides=6), "metal_brass", 25, "Lamp_Spoke", 0)
    return kit.group("TableLamp", nodes)


# ====================================================================== wardrobe
def _bar_handle(x, y_face, zc, length, standoff=3.2):
    """Tall brushed-brass bar pull on two round stand-offs."""
    yb = y_face - standoff
    bar = _lathe("Wardrobe_HandleBar", [(0.0, 0.0), (0.42, 0.0), (0.62, 0.12), (0.7, 0.45), (0.7, length - 0.45),
                                        (0.62, length - 0.12), (0.42, length), (0.0, length)],
                 origin=(x, yb, zc - 0.5 * length), segs=16)
    kit.soften(bar, smooth=1)
    out = [bar]
    for zp in (zc - 0.5 * length + 5.0, zc + 0.5 * length - 5.0):
        p = _lathe("Wardrobe_HandlePost", [(0.0, 0.0), (0.78, 0.0), (0.88, 0.1), (0.86, 0.32), (0.55, 0.5),
                                           (0.45, 0.8), (0.45, standoff), (0.0, standoff)],
                   origin=(x, y_face, zp), axis=(0.0, -1.0, 0.0), segs=12)
        kit.soften(p, smooth=1)
        out.append(p)
    return out


def build_wardrobe(length=230, depth=60, height=220):
    """Satin-white hinged wardrobe: round(length / 55) slab doors with 3 mm gaps, tall
    brass bar handles at the meeting edges, 8 cm plinth recessed 5 cm."""
    L, D, H = float(length), float(depth), float(height)
    nodes = []

    def add(node, mat, tile, name):
        node.name = name
        nodes.append(kit.part(node, mat, tile))
        return node

    PL, T, DT, DG, G = 8.0, 1.9, 1.9, 0.1, 0.3
    cy0 = -0.5 * D + DT + DG            # carcass front plane
    cd = 0.5 * D - cy0
    cyc = cy0 + 0.5 * cd
    for sx in (-1.0, 1.0):
        add(_cb(T, cd, H - PL, 0.25, sx * (0.5 * L - 0.5 * T), cyc, PL), "paint_white", 100, "Wardrobe_Side")
    add(_cb(L - 2.0 * T, cd, T, 0.2, 0.0, cyc, H - T), "paint_white", 100, "Wardrobe_Top")
    add(_cb(L - 2.0 * T, cd, T, 0.2, 0.0, cyc, PL), "paint_white", 100, "Wardrobe_Bottom")
    add(_cb(L - 2.0 * T, 0.8, H - PL - 2.0 * T, 0.2, 0.0, 0.5 * D - 0.4, PL + T, fs=1), "paint_white", 100,
        "Wardrobe_Back")
    # recessed plinth: kick board 5 cm behind the door face, returns 1 cm in from the sides
    py0 = -0.5 * D + 5.0
    add(_cb(L - 2.0, 1.8, PL, 0.2, 0.0, py0 + 0.9, 0.0), "paint_white", 100, "Wardrobe_Plinth")
    rl = 0.5 * D - 1.0 - (py0 + 1.8)
    for sx in (-1.0, 1.0):
        add(_cb(1.8, rl, PL, 0.2, sx * (0.5 * L - 1.0 - 0.9), py0 + 1.8 + 0.5 * rl, 0.0, fs=1), "paint_white", 100,
            "Wardrobe_PlinthReturn")
    n = max(1, int(round(L / 55.0)))
    dw = (L - 0.2 - G * (n - 1)) / n
    dh = H - PL - 0.2
    xs = [-0.5 * L + 0.1 + k * (dw + G) for k in range(n)]
    for x0 in xs:
        add(_cb(dw, DT, dh, 0.25, x0 + 0.5 * dw, -0.5 * D + 0.5 * DT, PL + 0.1, fs=2), "paint_white", 100,
            "Wardrobe_Door")
    for k in range(2, n, 2):           # gables between door pairs, seen through the gaps
        add(_cb(T, cd - 0.8, H - PL - 2.0 * T, 0.2, xs[k] - 0.5 * G, cyc - 0.4, PL + T, fs=1), "paint_white", 100,
            "Wardrobe_Divider")
    lh = min(64.0, 0.3 * H)
    zc = min(108.0, 0.49 * H)
    for k in range(n):
        if k % 2 == 0 and k + 1 < n:
            hx = xs[k] + dw - 4.0            # left leaf of a pair: pull at its right edge
        else:
            hx = xs[k] + 4.0                 # right leaf / single door hinged on the right
        for p in _bar_handle(hx, -0.5 * D, zc, lh):
            add(p, "metal_brass", 25, p.name)
    return kit.group("Wardrobe", nodes)


# ====================================================================== bench
def build_bench():
    """End-of-bed bench 120 x 40 x 45: oak legs, aprons, H-stretcher and seat board with
    a crowned, double-piped upholstered seat pad."""
    W, D, H = 120.0, 40.0, 45.0
    nodes = []

    def add(node, mat, tile, name):
        node.name = name
        nodes.append(kit.part(node, mat, tile))
        return node

    LT, LB, ZL = 4.6, 3.4, 36.0
    lx, ly = 0.5 * W - 1.5 - 0.5 * LT, 0.5 * D - 1.5 - 0.5 * LT
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            add(_leg(sx * lx, sy * ly, ZL, LT, LB, 0.4), "wood_light", 110, "Bench_Leg")
    al = 2.0 * lx - _leg_w(ZL, LT, LB, ZL - 3.5) + 0.6        # aprons run 3 mm into the legs
    for sy in (-1.0, 1.0):
        add(_cb(al, 2.0, 7.0, 0.3, 0.0, sy * (ly + 0.5 * LT - 0.6 - 1.0), ZL - 7.0), "wood_light", 110, "Bench_Apron")
    sl = 2.0 * ly - _leg_w(ZL, LT, LB, ZL - 3.5) + 0.6
    ss_ = 2.0 * ly - _leg_w(ZL, LT, LB, 10.5) + 0.6             # stretchers too, at their height
    for sx in (-1.0, 1.0):
        add(_cb(2.0, sl, 7.0, 0.3, sx * (lx + 0.5 * LT - 0.6 - 1.0), 0.0, ZL - 7.0), "wood_light", 110, "Bench_Apron")
        add(_cb(2.2, ss_, 3.0, 0.3, sx * lx, 0.0, 9.0), "wood_light", 110, "Bench_Stretcher")
    add(_cb(2.0 * lx - 2.2 + 0.6, 2.2, 3.0, 0.3, 0.0, 0.0, 9.0), "wood_light", 110, "Bench_Stretcher")
    ZB = ZL + 1.8
    add(_cb(W, D, 1.8, 0.5, 0.0, 0.0, ZL, fs=3), "wood_light", 110, "Bench_SeatBoard")
    # seat pad: piped box cushion, crowned top, boxing that bulges, welts on both seams
    pw, pd, crown, wr = W - 2.0, D - 2.0, 1.0, 0.42
    pad, zt, zb = _box_cushion("Bench_SeatPad", pw, pd, H - ZB - crown, ZB, crown, 0.6, 4.0, 17)
    kit.soften(pad, noise=(20.0, 0.08, 0.08), smooth=1, seed=17)
    add(pad, "upholstery", 30, "Bench_SeatPad")
    for zw in (zt, zb + wr):
        wl = _tube("Bench_Welt", _rrect_path(0.5 * pw - 0.1, 0.5 * pd - 0.1, 3.9, zw, step=3.0, arc_n=8), wr,
                   sides=8, closed=True)
        add(wl, "upholstery", 30, "Bench_Welt")
    return kit.group("Bench", nodes)


# ====================================================================== rug
def build_bedroom_rug(w=170, l=240):
    """Wool rug, w along X and l along Y, 1.5 cm thick: the pile meets a rolled, bound edge
    (binding about 1.3 cm wide, a hair lower than the pile, with a faint groove where they
    meet), the edges waver slightly in plan and the rug lies a little irregularly (one low
    diagonal ripple, one corner lifting and curling). The bottom never goes below z = 0."""
    W, L, T = float(w), float(l), 1.5
    hw, hl = 0.5 * W, 0.5 * L
    xs = _pieces([-hw, -hw + 3.0, hw - 3.0, hw], lambda x: 0.45 if hw - abs(x) < 3.1 else 6.0)
    ys = _pieces([-hl, -hl + 3.0, hl - 3.0, hl], lambda y: 0.45 if hl - abs(y) < 3.1 else 6.0)
    nz = _Noise(23, 6, (40.0, 120.0), dims=1)
    npl = _Noise(29, 6, (25.0, 90.0))
    nbd = _Noise(31, 5, (15.0, 45.0), dims=1)
    rx0, ry0 = 0.18 * W, -0.12 * L
    ang = math.radians(62.0)
    ux, uy = math.cos(ang), math.sin(ang)

    def lift(x, y):
        c = -(x - rx0) * uy + (y - ry0) * ux
        a = (x - rx0) * ux + (y - ry0) * uy
        lf = 0.5 * math.exp(-(c / 12.0) ** 2) * max(0.0, 1.0 - (a / (0.45 * L)) ** 2) ** 2
        cu = _sstep(0.72, 1.0, x / hw) * _sstep(0.72, 1.0, -y / hl)
        return lf + 1.0 * cu ** 2.4

    top, bot = [], []
    for x in xs:
        rt_, rb_ = [], []
        for y in ys:
            e = min(hw - abs(x), hl - abs(y))                      # distance in from the edge
            along = y if hw - abs(x) < hl - abs(y) else x
            bind = 1.0 - _sstep(1.0, 1.6, e)                       # 1 on the binding
            zt = (T - 0.12 * bind * (1.0 - 0.35 * nbd(along))      # the binding sits a hair lower
                  - 0.07 * math.exp(-((e - 1.45) / 0.22) ** 2)     # faint groove where it meets the pile
                  - 0.18 * (1.0 - _sstep(0.0, 0.9, e))             # and rolls over the edge
                  + 0.05 * npl(x, y) * (1.0 - bind))
            xx = x + 0.35 * nz(y) * _sstep(0.85, 1.0, abs(x) / hw)
            yy = y + 0.35 * nz(x + 300.0) * _sstep(0.85, 1.0, abs(y) / hl)
            lf = lift(x, y)
            rt_.append((xx, yy, zt + lf))
            rb_.append((xx, yy, lf))
        top.append(rt_)
        bot.append(rb_)
    # rolled edge: rim loops on a half-round profile (the binding wraps round the edge)
    rims = [_rim_ring(top, bot, 0.36 * math.sqrt(math.sin(math.pi * f)) / math.sin(math.pi * f), f)
            for f in (0.12, 0.35, 0.65, 0.88)]
    rug = _shell_mesh("Rug", top, bot, rims=rims)
    rug.name = "Rug"
    # the top grid's faces come first: ID 1 there (the scene grows VRayFur pile
    # on it), 2 on the binding, rims and underside
    n_top = (len(xs) - 1) * (len(ys) - 1)
    rt.polyop.setFaceMatID(rug, rt.execute("#{%d..%d}" % (n_top + 1, rt.polyop.getNumFaces(rug))), 2)
    rt.polyop.setFaceMatID(rug, rt.execute("#{1..%d}" % n_top), 1)
    kit.part(rug, "rug", 60)
    return kit.group("BedroomRug", [rug])


# ====================================================================== preview
def _vignette():
    """Furnished arrangement for scale checks: the bed's feet sink 0.5 cm into the rug pile."""
    Ltot = 1.2 * 2 + 3.8 + 200.0 + 4.5 + 5.0
    Wf = 160.0 + 10.0
    kit.place(build_bedroom_rug(200, 300), 0.0, -60.0)
    kit.place(build_bed(160, 200), 0.0, 0.0, 1.0)
    for sx in (-1.0, 1.0):
        x = sx * (0.5 * Wf + 4.0 + 22.5)
        y = 0.5 * Ltot - 19.0
        kit.place(build_nightstand(), x, y)
        kit.place(build_table_lamp(), x + sx * 2.0, y + 3.0, 50.0)
    kit.place(build_bench(), 0.0, -0.5 * Ltot - 12.0 - 20.0, 1.0)
    kit.place(build_wardrobe(130, 55), 0.5 * Wf + 150.0, 0.5 * Ltot - 65.0 - 40.0, 0.0, -90.0)


def preview():
    piece = os.environ.get("MF_BEDROOM_PIECE", "").strip().lower()
    if piece == "bed":
        kit.place(build_bed(160, 200), 0.0, 0.0)
    elif piece == "bed150":
        kit.place(build_bed(150, 200), 0.0, 0.0)
    elif piece == "nightstand":
        kit.place(build_nightstand(), 0.0, 0.0)
    elif piece == "lamp":
        kit.place(build_table_lamp(), 0.0, 0.0)
    elif piece == "wardrobe":
        kit.place(build_wardrobe(), 0.0, 0.0)
    elif piece == "wardrobe130":
        kit.place(build_wardrobe(130, 55), 0.0, 0.0)
    elif piece == "wardrobe260":
        kit.place(build_wardrobe(260, 60), 0.0, 0.0)
    elif piece == "bench":
        kit.place(build_bench(), 0.0, 0.0)
    elif piece == "rug":
        kit.place(build_bedroom_rug(), 0.0, 0.0)
    elif piece == "vignette":
        _vignette()
    else:
        # back row: wardrobe | bed | nightstand + lamp ; front row: rug | bench
        kit.place(build_wardrobe(), -270.0, 60.0)
        kit.place(build_bed(160, 200), 0.0, 0.0)
        kit.place(build_nightstand(), 155.0, 70.0)
        kit.place(build_table_lamp(), 215.0, 70.0)
        kit.place(build_bedroom_rug(), -290.0, -250.0)
        kit.place(build_bench(), 0.0, -190.0)
