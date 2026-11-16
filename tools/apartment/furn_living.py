"""Living-room furniture (Japandi / warm Scandinavian) for the MatForge test apartment.

Pieces, each built at the local origin with its FRONT facing -Y and its base
on z = 0 (centimetres, Z up), every visible node registered through
kit.part(...) and returned as kit.group(...):

  build_sofa()          3-seat sofa 220 x 95 x 82, seat 44 (+ scatter cushions, throw)
  build_armchair()      tub lounge chair 80 x 85 x 78, seat 42 (boucle)
  build_coffee_table()  walnut + brushed brass, 110 x 60 x 38, lower shelf
  build_tv_console()    walnut, 160 x 40 x 48, four inset doors, black legs
  build_tv()            55-inch TV 123 x 71 x 2.5 (+ rear housing) on a slim pedestal stand
  build_floor_lamp()    brass stem and base, linen drum shade, 160 high
  build_side_table()    marble disc 45 on a brass pedestal, 52 high
  build_decor_books()   four hardbacks, ceramic bowl, pillar candle
  build_decor_vase()    glass bud vase with three leafy branches
  build_plant()         monstera in a 35 x 38 terracotta pot on a saucer

Soft goods are quad cages generated here in Python (ring-stacked rounded
slabs with Coons-patch caps and self-fabric piping, knife-edge scatter
cushions, a swept tub shell with half-revolved arm ends) and finished with
kit.soften (Noise + TurboSmooth). Hard goods use ChamferBoxes and quad
revolves with real fillets, so no edge is razor-sharp.

preview() lays every piece out side by side. For close-up checks the
environment variables MF_LIVING_ONLY (comma list of: sofa, armchair, coffee,
coffeeset, console, tv, lamp, side, books, vase, plant) and MF_LIVING_ROT (degrees about
Z) narrow the preview; MF_LIVING_STATS=<path> writes per-piece face counts.
"""
import json
import math
import os

from pymxs import runtime as rt

import kit

# real-world size of one texture repeat (cm)
FAB = 11.0          # upholstery linen at ~14 threads/cm (25 cm gave hessian-scale weave)
OAK = 100.0
WALNUT = 110.0
METAL = 25.0
STONE = 120.0


# ======================================================================= maths
def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    ln = math.sqrt(_dot(a, a))
    return (a[0] / ln, a[1] / ln, a[2] / ln) if ln > 1e-12 else (0.0, 0.0, 1.0)


def _smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def _smin(a, b, k=0.4):
    """Smooth minimum (blend width k): soft 'pressed against' contacts."""
    m = min(a, b)
    return m - k * math.log1p(math.exp(-abs(a - b) / k))


def _smax(a, b, k=0.4):
    return -_smin(-a, -b, k)


def _bez(p0, p1, p2, p3, t):
    u = 1.0 - t
    return tuple(u * u * u * p0[i] + 3 * u * u * t * p1[i] + 3 * u * t * t * p2[i] + t * t * t * p3[i]
                 for i in range(3))


def _rot_axis(v, axis, ang):
    """Rotate vector v about unit axis by ang (radians), Rodrigues."""
    c, s = math.cos(ang), math.sin(ang)
    k = axis
    kv = _cross(k, v)
    kd = _dot(k, v)
    return tuple(v[i] * c + kv[i] * s + k[i] * kd * (1.0 - c) for i in range(3))


# ================================================================== mesh cage
class _MD(object):
    """Python-side cage: vertex list + polygon list (0-based indices)."""

    def __init__(self):
        self.v = []
        self.f = []
        self.fuv = []          # per face: None (box-projected at build) or (u, v) per corner

    def add(self, p):
        self.v.append((float(p[0]), float(p[1]), float(p[2])))
        return len(self.v) - 1

    def face(self, idx, uv=None):
        out, ouv = [], []
        for k, i in enumerate(idx):
            if not out or out[-1] != i:
                out.append(i)
                ouv.append(uv[k] if uv else None)
        while len(out) > 1 and out[0] == out[-1]:
            out.pop()
            ouv.pop()
        if len(out) >= 3:
            self.f.append(tuple(out))
            self.fuv.append(tuple(ouv) if uv else None)

    def merge(self, other):
        off = len(self.v)
        self.v.extend(other.v)
        self.f.extend(tuple(i + off for i in fc) for fc in other.f)
        self.fuv.extend(other.fuv if len(other.fuv) == len(other.f) else [None] * len(other.f))
        return off

    def map(self, fn):
        self.v = [fn(p) for p in self.v]
        return self


def _build(md, name, uv_tile=None):
    """Editable Poly from a cage. Polygons are fan-split with hidden interior
    edges, so convertToPoly rebuilds the quads / n-gons TurboSmooth needs.
    With uv_tile (cm per repeat) the cage UVs are written to map channel 1
    (faces without UVs are box-projected at the same scale)."""
    use_uv = uv_tile is not None
    tris, codes, tvf, tv, tvi = [], [], [], [], {}

    def tvert(vi, u, v):
        key = (vi, round(u, 5), round(v, 5))
        if key not in tvi:
            tvi[key] = len(tv)
            tv.append((u, v))
        return tvi[key]

    for fi, fc in enumerate(md.f):
        n = len(fc)
        if use_uv:
            fu = md.fuv[fi] if fi < len(md.fuv) else None
            if fu is None:
                P = [md.v[i] for i in fc]
                nx = ny = nz = 0.0
                for k in range(n):
                    a, b = P[k], P[(k + 1) % n]
                    nx += (a[1] - b[1]) * (a[2] + b[2])
                    ny += (a[2] - b[2]) * (a[0] + b[0])
                    nz += (a[0] - b[0]) * (a[1] + b[1])
                ax = max(range(3), key=lambda i: abs((nx, ny, nz)[i]))
                fu = [((q[1], q[2]), (q[0], q[2]), (q[0], q[1]))[ax] for q in P]
                fu = [(a / uv_tile, b / uv_tile) for a, b in fu]
            ti = [tvert(fc[k], fu[k][0], fu[k][1]) for k in range(n)]
        for k in range(1, n - 1):
            tris.append((fc[0], fc[k], fc[k + 1]))
            if use_uv:
                tvf.append((ti[0], ti[k], ti[k + 1]))
            c = 0
            if k > 1:
                c |= 1
            if k < n - 2:
                c |= 4
            codes.append(c)
    vs = ",".join("[%.4f,%.4f,%.4f]" % p for p in md.v)
    fs = ",".join("[%d,%d,%d]" % (a + 1, b + 1, c + 1) for a, b, c in tris)
    hs = ",".join(str(c) for c in codes)
    uvs = ""
    if use_uv:
        uvs = ('setNumTVerts mfm %d\nmft = #(%s)\nfor i = 1 to mft.count do setTVert mfm i mft[i]\n'
               'buildTVFaces mfm\nmfq = #(%s)\nfor f = 1 to mfm.numfaces do setTVFace mfm f mfq[f]\n') % (
            len(tv), ",".join("[%.5f,%.5f,0]" % t for t in tv),
            ",".join("[%d,%d,%d]" % (a + 1, b + 1, c + 1) for a, b, c in tvf))
    ms = ('(mfm = mesh name:"%s" vertices:#(%s) faces:#(%s)\n'
          'mfh = #(%s)\n'
          'for f = 1 to mfm.numfaces do (\n'
          '  mfc = mfh[f]\n'
          '  if (bit.and mfc 1) != 0 do setEdgeVis mfm f 1 false\n'
          '  if (bit.and mfc 4) != 0 do setEdgeVis mfm f 3 false\n'
          '  setFaceSmoothGroup mfm f 1)\n'
          '%s'
          'update mfm\nconvertToPoly mfm\nmfm)') % (name, vs, fs, hs, uvs)
    return rt.execute(ms)


def _soft(md, name, mat, noise=None, seed=0, smooth=1, tile=FAB, own_uv=False):
    """own_uv: the cage carries real-scale UVs (1 unit = `tile` cm), so the
    scene must not box-map it (maptype None)."""
    node = _build(md, name, tile if own_uv else None)
    kit.soften(node, noise, smooth, seed)
    return kit.part(node, mat, None, None) if own_uv else kit.part(node, mat, tile)


def _soft_framed(md, name, mat, noise, seed, axes, origin, tile=FAB, own_uv=False, maptype=4, smooth=1):
    """Like _soft, but the node gets its own transform (rows of `axes` = local
    X, Y, Z in parent space, `origin` = pivot) so the scene's UVW box gizmo and
    the Noise gizmo align with a tilted cushion instead of the parent frame."""
    loc = _MD()
    loc.f, loc.fuv = md.f, md.fuv
    loc.v = [(_dot(_sub(v, origin), axes[0]), _dot(_sub(v, origin), axes[1]), _dot(_sub(v, origin), axes[2]))
             for v in md.v]
    node = _build(loc, name, tile if own_uv else None)
    node.transform = rt.Matrix3(rt.Point3(*axes[0]), rt.Point3(*axes[1]), rt.Point3(*axes[2]),
                                rt.Point3(*origin))
    kit.soften(node, noise, smooth, seed)
    return kit.part(node, mat, None, None) if own_uv else kit.part(node, mat, tile, maptype)


def _hard(md, name, mat, tile, smooth=1):
    node = _build(md, name)
    if smooth:
        kit.soften(node, None, smooth)
    return kit.part(node, mat, tile)


# ============================================================ 2-D profile tools
def _fillet2d(pts, radii, closed=False, step=math.radians(30.0)):
    """Replace polyline corners by tangent circular arcs of the given radii."""
    n = len(pts)
    out = []
    for i in range(n):
        p = pts[i]
        r = radii[i]
        if r <= 0.0 or (not closed and (i == 0 or i == n - 1)):
            out.append(p)
            continue
        a = pts[i - 1]
        c = pts[(i + 1) % n]
        l1 = math.hypot(p[0] - a[0], p[1] - a[1])
        l2 = math.hypot(c[0] - p[0], c[1] - p[1])
        if l1 < 1e-9 or l2 < 1e-9:
            out.append(p)
            continue
        d1 = ((p[0] - a[0]) / l1, (p[1] - a[1]) / l1)
        d2 = ((c[0] - p[0]) / l2, (c[1] - p[1]) / l2)
        cr = d1[0] * d2[1] - d1[1] * d2[0]
        turn = math.acos(max(-1.0, min(1.0, d1[0] * d2[0] + d1[1] * d2[1])))
        if turn < 1e-3:
            out.append(p)
            continue
        tl = r * math.tan(turn / 2.0)
        lim = 0.5 * min(l1, l2)
        if tl > lim:
            tl = lim
            r = tl / math.tan(turn / 2.0)
        sgn = 1.0 if cr > 0 else -1.0
        t1 = (p[0] - d1[0] * tl, p[1] - d1[1] * tl)
        cen = (t1[0] - d1[1] * sgn * r, t1[1] + d1[0] * sgn * r)
        a0 = math.atan2(t1[1] - cen[1], t1[0] - cen[0])
        k = max(2, int(math.ceil(turn / step)))
        for j in range(k + 1):
            ang = a0 + sgn * turn * j / k
            out.append((cen[0] + r * math.cos(ang), cen[1] + r * math.sin(ang)))
    return out


def _resample_closed(pts, count, beta=3.0):
    """Resample a closed polyline to `count` points, denser where it turns."""
    n = len(pts)
    turn = []
    for i in range(n):
        a, p, c = pts[i - 1], pts[i], pts[(i + 1) % n]
        d1 = (p[0] - a[0], p[1] - a[1])
        d2 = (c[0] - p[0], c[1] - p[1])
        l1, l2 = math.hypot(*d1), math.hypot(*d2)
        if l1 < 1e-9 or l2 < 1e-9:
            turn.append(0.0)
            continue
        turn.append(math.acos(max(-1.0, min(1.0, (d1[0] * d2[0] + d1[1] * d2[1]) / (l1 * l2)))))
    cum = [0.0]
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1])
                   + beta * 0.5 * (turn[i] + turn[(i + 1) % n]))
    total = cum[-1]
    out = []
    seg = 0
    for k in range(count):
        target = total * k / count
        while seg < n - 1 and cum[seg + 1] < target:
            seg += 1
        a, b = pts[seg], pts[(seg + 1) % n]
        span = cum[seg + 1] - cum[seg]
        t = (target - cum[seg]) / span if span > 1e-12 else 0.0
        out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out


# =============================================================== generators
def _revolve_md(profile, segs=48, closed=False, x=0.0, y=0.0, z=0.0, phase=0.0):
    """Quad revolve of an (r, z) profile about Z. Traverse the profile
    counter-clockwise around the material (r right, z up) for outward
    normals; r == 0 points become poles."""
    md = _MD()
    rings = []
    for (r, zz) in profile:
        if r < 1e-4:
            rings.append([md.add((x, y, z + zz))] * segs)
        else:
            rings.append([md.add((x + r * math.cos(phase + 2 * math.pi * j / segs),
                                  y + r * math.sin(phase + 2 * math.pi * j / segs), z + zz))
                          for j in range(segs)])
    nr = len(rings)
    for k in range(nr if closed else nr - 1):
        ra, rb = rings[k], rings[(k + 1) % nr]
        for j in range(segs):
            j2 = (j + 1) % segs
            md.face((ra[j], ra[j2], rb[j2], rb[j]))
    return md


def _tube_md(path, radius, sides=8, closed=False, normals=None, caps=True):
    """Tube swept along a 3-D polyline (parallel-transport frames, or the
    given normals). radius may be a float or a per-point list."""
    md = _MD()
    n = len(path)
    tang = []
    for i in range(n):
        if closed:
            a, b = path[i - 1], path[(i + 1) % n]
        else:
            a, b = path[max(i - 1, 0)], path[min(i + 1, n - 1)]
        tang.append(_norm(_sub(b, a)))
    nrm = []
    if normals:
        for i in range(n):
            q = normals[i]
            nrm.append(_norm(_sub(q, _mul(tang[i], _dot(q, tang[i])))))
    else:
        ref = (0.0, 0.0, 1.0) if abs(tang[0][2]) < 0.9 else (1.0, 0.0, 0.0)
        q = _norm(_sub(ref, _mul(tang[0], _dot(ref, tang[0]))))
        for i in range(n):
            q = _norm(_sub(q, _mul(tang[i], _dot(q, tang[i]))))
            nrm.append(q)
    rad = list(radius) if isinstance(radius, (list, tuple)) else [radius] * n
    for i in range(n):
        bi = _cross(tang[i], nrm[i])
        for s in range(sides):
            a = 2.0 * math.pi * s / sides
            ca, sa = math.cos(a), math.sin(a)
            md.add(tuple(path[i][k] + rad[i] * (ca * nrm[i][k] + sa * bi[k]) for k in range(3)))
    for i in range(n if closed else n - 1):
        i2 = (i + 1) % n
        for s in range(sides):
            s2 = (s + 1) % sides
            md.face((i * sides + s, i * sides + s2, i2 * sides + s2, i2 * sides + s))
    if caps and not closed:
        c0 = md.add(path[0])
        c1 = md.add(path[-1])
        last = (n - 1) * sides
        for s in range(sides):
            s2 = (s + 1) % sides
            md.face((c0, s2, s))
            md.face((c1, last + s, last + s2))
    return md


def _alloc(seg, la1, ls, la2, amin=2):
    if ls <= 1e-6:
        n1 = seg // 2
        return n1, 0, seg - n1
    tot = la1 + ls + la2
    n1 = max(amin, int(round(seg * la1 / tot)))
    n2 = max(amin, int(round(seg * la2 / tot)))
    while seg - n1 - n2 < 1 and (n1 > 1 or n2 > 1):
        if n1 >= n2:
            n1 -= 1
        else:
            n2 -= 1
    return n1, seg - n1 - n2, n2


def _slab(A, B, z0, z1, radii, p=12, q=8, rb=(2.0, 2.0), rt_=(3.0, 3.0), mb=2, ms=2, mt=3,
          cx=0.0, cy=0.0, crown=0.0, crown_b=0.0, bulge=0.0, expo=2.0, scale_b=None,
          piping=(), pipe_r=0.42, pipe_sides=4, deform=None, amin=2, uv_tile=None):
    """Rounded slab cage: plan = rounded rectangle (half extents A, B, corner
    radii [(rx, ry)] FL, FR, BR, BL - elliptical corners allowed, so D-shapes
    and stadiums work), vertical profile = bottom arc (rb = horizontal,
    vertical radius), straight side, top arc (rt_). Caps are Coons patches of
    the end rings; crown puffs the caps, bulge pushes the sides out mid-span.
    piping adds self-fabric welts at the 45-degree point of the 'top' and/or
    'bottom' arcs as extra elements of the same cage. uv_tile writes
    upholstery UVs at that scale: planar top / bottom panels, a wrapped
    boxing strip, UV seams on the 45-degree (piping) lines."""
    if not isinstance(radii, (list, tuple)):
        radii = [(float(radii), float(radii))] * 4
    cen = [(-A + radii[0][0], -B + radii[0][1]), (A - radii[1][0], -B + radii[1][1]),
           (A - radii[2][0], B - radii[2][1]), (-A + radii[3][0], B - radii[3][1])]
    base = [math.pi, 1.5 * math.pi, 0.0, 0.5 * math.pi]

    def half_arc(ci):
        rx, ry = radii[ci]
        return 0.25 * math.pi * math.sqrt(0.5 * (rx * rx + ry * ry))

    straight = [cen[1][0] - cen[0][0], cen[2][1] - cen[1][1], cen[2][0] - cen[3][0], cen[3][1] - cen[0][1]]
    desc = []
    for k in range(4):
        seg = p if k % 2 == 0 else q
        c1, c2 = k, (k + 1) % 4
        n1, ns, n2 = _alloc(seg, half_arc(c1), max(0.0, straight[k]), half_arc(c2), amin)
        a1 = base[c1] + 0.25 * math.pi
        for j in range(n1):
            desc.append(("a", c1, a1 + 0.25 * math.pi * j / n1))
        for j in range(ns):
            desc.append(("l", k, j / float(ns)))
        for j in range(n2):
            desc.append(("a", c2, base[c2] + 0.25 * math.pi * j / n2))
    N = len(desc)

    def ev(d, delta):
        if d[0] == "a":
            ci, th = d[1], d[2]
            rx = max(radii[ci][0] - delta, 0.02)
            ry = max(radii[ci][1] - delta, 0.02)
            c, s = math.cos(th), math.sin(th)
            nx, ny = c / rx, s / ry
            ln = math.hypot(nx, ny)
            return cen[ci][0] + rx * c, cen[ci][1] + ry * s, nx / ln, ny / ln, 0.0
        k, t = d[1], d[2]
        g = math.sin(math.pi * t) ** 2
        if k == 0:
            return cen[0][0] + (cen[1][0] - cen[0][0]) * t, -B + delta, 0.0, -1.0, g
        if k == 1:
            return A - delta, cen[1][1] + (cen[2][1] - cen[1][1]) * t, 1.0, 0.0, g
        if k == 2:
            return cen[2][0] + (cen[3][0] - cen[2][0]) * t, B - delta, 0.0, 1.0, g
        return -A + delta, cen[3][1] + (cen[0][1] - cen[3][1]) * t, -1.0, 0.0, g

    def se(v):
        return math.copysign(abs(v) ** (2.0 / expo), v)

    H = z1 - z0
    rhb, rvb = rb
    rht, rvt = rt_
    rings = []
    for j in range(mb + 1):
        ph = 0.5 * math.pi * j / mb
        rings.append((rhb * (1.0 - se(math.sin(ph))), z0 + rvb * (1.0 - se(math.cos(ph)))))
    zs0, zs1 = z0 + rvb, z1 - rvt
    for j in range(1, ms):
        rings.append((0.0, zs0 + (zs1 - zs0) * j / ms))
    for j in range(mt + 1):
        ph = 0.5 * math.pi * j / mt
        rings.append((rht * (1.0 - se(math.cos(ph))), zs1 + rvt * se(math.sin(ph))))

    def ring_pts(delta, z):
        w = (z - z0) / H
        wb = math.sin(math.pi * w) if 0.0 < w < 1.0 else 0.0
        sc = 1.0 if scale_b is None else scale_b + (1.0 - scale_b) * w
        out = []
        for d in desc:
            x, y, nx, ny, g = ev(d, delta)
            b = bulge * wb * g
            out.append((cx + x * sc + nx * b, cy + y * sc + ny * b, z, nx, ny))
        return out

    md = _MD()
    for (delta, z) in rings:
        for (x, y, zz, nx, ny) in ring_pts(delta, z):
            md.add((x, y, zz))
    R = len(rings)
    kb, kt = mb // 2, mb + ms + mt // 2           # boxing-strip seams (45-degree rings)
    if uv_tile:
        base_pts = [ev(d, 0.0) for d in desc]
        U = [0.0]
        for i in range(N):
            a, b = base_pts[i], base_pts[(i + 1) % N]
            U.append(U[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        V = [0.0]
        for k in range(1, R):
            V.append(V[-1] + math.hypot(rings[k][0] - rings[k - 1][0], rings[k][1] - rings[k - 1][1]))

    def planar(idx, flip=False):
        return [((-1.0 if flip else 1.0) * (md.v[i][0] - cx) / uv_tile, (md.v[i][1] - cy) / uv_tile)
                for i in idx]

    for k in range(R - 1):
        for i in range(N):
            i2 = (i + 1) % N
            idx = (k * N + i, k * N + i2, (k + 1) * N + i2, (k + 1) * N + i)
            uv = None
            if uv_tile:
                if kb <= k < kt:
                    t = uv_tile
                    uv = ((U[i] / t, V[k] / t), (U[i + 1] / t, V[k] / t),
                          (U[i + 1] / t, V[k + 1] / t), (U[i] / t, V[k + 1] / t))
                else:
                    uv = planar(idx, k < kb)
            md.face(idx, uv)

    def cap(ri, zc, amt, top):
        ring = [ri * N + i for i in range(N)]
        G = [[None] * (q + 1) for _ in range(p + 1)]
        for i in range(p + 1):
            G[i][0] = ring[i % N]
        for j in range(q + 1):
            G[p][j] = ring[(p + j) % N]
        for i in range(p + 1):
            G[p - i][q] = ring[(p + q + i) % N]
        for j in range(q + 1):
            G[0][q - j] = ring[(2 * p + q + j) % N]
        V = md.v
        P00, P10, P01, P11 = V[G[0][0]], V[G[p][0]], V[G[0][q]], V[G[p][q]]
        for i in range(1, p):
            u = i / float(p)
            for j in range(1, q):
                v = j / float(q)
                c0, c1, d0, d1 = V[G[i][0]], V[G[i][q]], V[G[0][j]], V[G[p][j]]
                xy = []
                for a in (0, 1):
                    xy.append((1 - v) * c0[a] + v * c1[a] + (1 - u) * d0[a] + u * d1[a]
                              - ((1 - u) * (1 - v) * P00[a] + u * (1 - v) * P10[a]
                                 + (1 - u) * v * P01[a] + u * v * P11[a]))
                lift = amt * 16.0 * u * (1 - u) * v * (1 - v)
                G[i][j] = md.add((xy[0], xy[1], zc + (lift if top else -lift)))
        for i in range(p):
            for j in range(q):
                a, b, c, d = G[i][j], G[i + 1][j], G[i + 1][j + 1], G[i][j + 1]
                idx = (a, b, c, d) if top else (a, d, c, b)
                md.face(idx, planar(idx, not top) if uv_tile else None)

    cap(0, z0, crown_b, False)
    cap(R - 1, z1, crown, True)

    for seam in piping:
        ph = 0.25 * math.pi
        if seam == "top":
            delta, z = rht * (1.0 - se(math.cos(ph))), zs1 + rvt * se(math.sin(ph))
            nh, nv = math.cos(ph) / rht, math.sin(ph) / rvt
        else:
            delta, z = rhb * (1.0 - se(math.sin(ph))), z0 + rvb * (1.0 - se(math.cos(ph)))
            nh, nv = math.cos(ph) / rhb, -math.sin(ph) / rvb
        path, nrms = [], []
        for (x, y, zz, nx, ny) in ring_pts(delta, z):
            nn = _norm((nx * nh, ny * nh, nv))
            path.append((x + nn[0] * 0.1, y + nn[1] * 0.1, zz + nn[2] * 0.1))
            nrms.append(nn)
        md.merge(_tube_md(path, pipe_r, pipe_sides, closed=True, normals=nrms))

    if deform:
        md.map(deform)
    return md


def _dihedral(uv, k):
    """One of the 8 symmetries of the unit square (k = 0..7) applied to (u, v)."""
    u, v = uv
    if k & 4:
        u = 1.0 - u
    for _ in range(k & 3):
        u, v = 1.0 - v, u
    return (u, v)


def _pillow_md(w, h, t, n=28, pinch=0.09, flat=2.0, puff=0.8, piping=False, pipe_r=0.4, dent=0.0,
               ear=1.2, wrinkle=0.9, settle=0.1, bow=0.6, seed=0, uv_var=(0, 5)):
    """Knife-edge scatter cushion lying in XY (faces +-Z), centred on 0. The
    cage is dense enough to need no TurboSmooth, so the detail survives: a
    plump superelliptic section that pinches into a thin seam lip, pulled-in
    mid-edges and soft dog-eared corners, tension wrinkles fanning out of each
    corner, the filling settled towards -Y (the edge it stands on), a slight
    bow, an optional 'karate chop' dent and self piping sitting on the seam.
    Own UVs: one repeat per face, each face turned / mirrored by uv_var
    (_dihedral codes) so no two faces show the velvet map the same way."""
    A, B = w / 2.0, h / 2.0
    rnd = _Rand(seed * 7 + 5)
    md = _MD()
    S = []
    for i in range(n + 1):
        s = -1.0 + 2.0 * i / n
        S.append(math.copysign(abs(s) ** 0.75, s))      # denser towards the seam

    def prof(s):
        a = abs(s)
        return max(0.0, 1.0 - a ** flat) ** puff * _smooth((1.0 - a) / 0.07)

    corners = []
    for cu in (-1.0, 1.0):
        for cv in (-1.0, 1.0):
            corners.append((cu, cv, rnd.uniform(0.0, 6.283), rnd.uniform(0.0, 6.283),
                            wrinkle * rnd.uniform(0.6, 1.25), rnd.uniform(4.3, 5.8)))

    def wrink(x, y, top):
        tot = 0.0
        for cu, cv, ph_t, ph_b, amp, freq in corners:
            dx, dy = x - cu * A, y - cv * B
            r = math.hypot(dx, dy)
            if r < 1e-6 or r > 22.0:
                continue
            gx, gy = -cu * 0.70711, -cv * 0.70711            # inward diagonal
            phi = math.atan2(dx * gy - dy * gx, dx * gx + dy * gy)
            env = _smooth(r / 4.5) * math.exp(-r / 8.0) * max(0.0, math.cos(phi))
            tot += amp * env * math.sin(freq * phi + (ph_t if top else ph_b))
        return tot

    top, bot, puv, nuv = {}, {}, {}, {}
    for i in range(n + 1):
        u = S[i]
        for j in range(n + 1):
            v = S[j]
            x = A * u * (1.0 - pinch * (1.0 - v * v) * u * u)
            y = B * v * (1.0 - pinch * (1.0 - u * u) * v * v)
            e = ear * (abs(u) * abs(v)) ** 8                   # round the dog-ear tips
            x -= math.copysign(0.70711 * e, u)
            y -= math.copysign(0.70711 * e, v)
            hz = 0.5 * t * prof(u) * prof(v) * (1.0 - settle * v)
            if dent:                                    # 'karate chop' crease at the top edge
                fd = math.exp(-(u / 0.22) ** 2) * _smooth((v - 0.2) / 0.8)
                y -= dent * fd * B * 0.16
                hz *= 1.0 - 0.3 * fd * dent
            zb = -bow * (y / B) ** 2
            puv[(i, j)] = _dihedral((0.5 + x / (2.0 * A), 0.5 + y / (2.0 * B)), uv_var[0])
            nuv[(i, j)] = _dihedral((0.5 - x / (2.0 * A), 0.5 + y / (2.0 * B)), uv_var[1])
            if i in (0, n) or j in (0, n):
                top[(i, j)] = bot[(i, j)] = md.add((x, y, zb))
            else:
                fade = min(1.0, hz / 0.9)
                top[(i, j)] = md.add((x, y, zb + hz + fade * wrink(x, y, True)))
                bot[(i, j)] = md.add((x, y, zb - hz - fade * wrink(x, y, False)))
    for i in range(n):
        for j in range(n):
            a, b, c, d = (i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)
            md.face((top[a], top[b], top[c], top[d]), (puv[a], puv[b], puv[c], puv[d]))
            md.face((bot[a], bot[d], bot[c], bot[b]), (nuv[a], nuv[d], nuv[c], nuv[b]))
    if piping:
        ring = ([(i, 0) for i in range(n)] + [(n, j) for j in range(n)]
                + [(n - i, n) for i in range(n)] + [(0, n - j) for j in range(n)])
        pts = [md.v[top[k]] for k in ring]
        m = len(pts)
        nrms = []
        for i in range(m):
            a, b = pts[i - 1], pts[(i + 1) % m]
            nrms.append(_norm((b[1] - a[1], -(b[0] - a[0]), 0.0)))
        md.merge(_tube_md(pts, pipe_r, 8, closed=True, normals=nrms))
    return md


class _Grid2(object):
    """Bucketed point lookup on two axes (contact queries between soft goods)."""

    def __init__(self, ax0, ax1, cell=3.0):
        self.a0, self.a1, self.cell = ax0, ax1, cell
        self.b = {}

    def add(self, pts):
        c = self.cell
        for p in pts:
            key = (int(math.floor(p[self.a0] / c)), int(math.floor(p[self.a1] / c)))
            self.b.setdefault(key, []).append(p)
        return self

    def near(self, a, b, rad):
        c = self.cell
        out = []
        for i in range(int(math.floor((a - rad) / c)), int(math.floor((a + rad) / c)) + 1):
            for j in range(int(math.floor((b - rad) / c)), int(math.floor((b + rad) / c)) + 1):
                for p in self.b.get((i, j), ()):
                    if (p[self.a0] - a) ** 2 + (p[self.a1] - b) ** 2 <= rad * rad:
                        out.append(p)
        return out


# ============================================================ shared parts
def _leg_round(x, y, z0, z1, r_top, r_bot, mat, tile, name, sides=16, smooth=1):
    """Tapered round leg with eased foot and top."""
    prof = _fillet2d([(0.0, z0), (r_bot, z0), (r_top, z1), (0.0, z1)],
                     [0.0, min(0.35, r_bot * 0.3), min(0.3, r_top * 0.2), 0.0], step=math.radians(22.5))
    return _hard(_revolve_md(prof, sides, x=x, y=y), name, mat, tile, smooth)


def _disc(x, y, z0, z1, r, mat, tile, name, edge=0.15, sides=24, smooth=1):
    prof = _fillet2d([(0.0, z0), (r, z0), (r, z1), (0.0, z1)], [0.0, edge, edge, 0.0],
                     step=math.radians(30.0 if smooth else 18.0))
    return _hard(_revolve_md(prof, sides, x=x, y=y), name, mat, tile, smooth)


def _orient(node, x, y, z, deg):
    """Rotate a primitive about its own pivot, then put the pivot at (x, y, z)."""
    if deg:
        kit.rotate(node, deg)
    node.pos = rt.Point3(x, y, z)
    return node


# ======================================================================= sofa
def _lean_pillow(md, xc, yaw, lean, roll, seat_top, back_front, sink=1.3, press=0.6):
    th = math.radians(90.0 - lean)
    ro, ya = math.radians(roll), math.radians(yaw)
    c1, s1 = math.cos(th), math.sin(th)
    c2, s2 = math.cos(ro), math.sin(ro)
    c3, s3 = math.cos(ya), math.sin(ya)

    def rot(p):
        x, y, z = p
        y, z = y * c1 - z * s1, y * s1 + z * c1
        x, z = x * c2 + z * s2, -x * s2 + z * c2
        x, y = x * c3 - y * s3, x * s3 + y * c3
        return (x + xc, y, z)

    md.map(rot)
    org = [xc, 0.0, 0.0]
    for _ in range(3):
        zmin = min(v[2] for v in md.v)
        dz = max(seat_top(v[0], v[1]) - sink - v[2] for v in md.v if v[2] < zmin + 5.0)
        md.map(lambda p, dz=dz: (p[0], p[1], p[2] + dz))
        org[2] += dz
        best = None
        for v in md.v:
            yf = back_front(v[0], v[2])
            if yf is None:
                continue
            d = yf + press - v[1]
            if best is None or d < best:
                best = d
        if best is not None:
            md.map(lambda p, dy=best: (p[0], p[1] + dy, p[2]))
            org[1] += best
    axes = [rot((1.0, 0.0, 0.0)), rot((0.0, 1.0, 0.0)), rot((0.0, 0.0, 1.0))]
    axes = [(a[0] - xc, a[1], a[2]) for a in axes]
    return axes, tuple(org)


def _throw(seat_top, y0=-35.0, y1=13.0, ns=24, nt=20):
    """Linen throw folded lengthwise and draped over the right arm: it follows
    the arm section (inner face, rounded top, outer face) 0.6 cm proud, then
    hangs free on the outside in irregular gravity folds that deepen and
    slant towards a wavy, slightly skewed hem with drooping corners and
    flared edges; on the inside it runs down into the crevice and out onto
    the seat cushion. Shell gives it cloth thickness; own UVs."""
    off = 0.6
    ym, hw = 0.5 * (y0 + y1), 0.5 * (y1 - y0)

    def bul(z, y):
        if not 14.0 < z < 60.0:
            return 0.0
        return 0.6 * math.sin(math.pi * (z - 14.0) / 46.0) * math.sin(math.pi * (y + 38.5) / 70.5) ** 2

    def folds(y, drop):
        """0..1 fold profile across the hanging part: three irregular
        harmonics whose phases drift with the drop, so the folds slant."""
        th = 2 * math.pi * (y - y0) / 14.0 + 0.03 * drop + 0.9 * math.sin(y / 7.0)
        f = (0.6 * math.sin(th) + 0.3 * math.sin(1.69 * th + 1.7 + 0.05 * drop)
             + 0.1 * math.sin(2.75 * th + 0.4 - 0.04 * drop))
        return max(0.0, 0.5 + 0.5 * f)

    md = _MD()
    rows = []
    for j in range(nt + 1):
        y = y0 + (y1 - y0) * j / nt
        e = (y - ym) / hw
        # the hem rides up over each fold crest, sags at the corners and is a little skewed
        hem = (23.5 + 0.45 * math.sin(2 * math.pi * y / 17.0 + 1.1) + 0.3 * math.sin(y / 4.3)
               + 1.1 * (folds(y, 28.0) - 0.5) - 1.4 * e - 2.6 * e ** 6)
        pts = []
        for x in range(80, 88):                                   # lying on the seat
            pts.append((float(x), seat_top(float(x), y) + 0.45, 0.0, 1.0))
        zs = pts[-1][1]
        xi = 92.0 - bul(48.0, y) - off
        for k in range(1, 5):                                      # over the cushion/arm crevice
            t = k / 5.0
            pts.append((88.0 + (xi - 88.0) * (1 - (1 - t) ** 2), zs + (48.0 - zs) * t * t, -t, 1.0 - t))
        for z in (49.5, 51.0):
            pts.append((92.0 - bul(z, y) - off, z, -1.0, 0.0))
        for k in range(7):                                         # inner top arc
            ph = 0.5 * math.pi * k / 6.0
            nx, nz = -math.cos(ph) / 7.5, math.sin(ph) / 8.0
            ln = math.hypot(nx, nz)
            pts.append((92.0 + 7.5 * (1 - math.cos(ph)) + off * nx / ln, 52.0 + 8.0 * math.sin(ph) + off * nz / ln,
                        nx / ln, nz / ln))
        pts.append((101.0, 60.0 + off, 0.0, 1.0))
        for k in range(6, -1, -1):                                 # outer top arc
            ph = 0.5 * math.pi * k / 6.0
            nx, nz = math.cos(ph) / 7.5, math.sin(ph) / 8.0
            ln = math.hypot(nx, nz)
            pts.append((110.0 - 7.5 * (1 - math.cos(ph)) + off * nx / ln, 52.0 + 8.0 * math.sin(ph) + off * nz / ln,
                        nx / ln, nz / ln))
        z = 50.0
        while z > hem:                                             # hanging down the outside
            pts.append((110.0 + bul(z, y) + off, z, 1.0, 0.0))
            z -= 2.0
        pts.append((110.0 + bul(hem, y) + off, hem, 1.0, 0.0))
        cum = [0.0]
        for a, b in zip(pts, pts[1:]):
            cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        row = []
        seg = 0
        for i in range(ns + 1):
            target = cum[-1] * i / ns
            while seg < len(pts) - 2 and cum[seg + 1] < target:
                seg += 1
            a, b = pts[seg], pts[seg + 1]
            t = (target - cum[seg]) / max(cum[seg + 1] - cum[seg], 1e-9)
            x = a[0] + (b[0] - a[0]) * t
            zz = a[1] + (b[1] - a[1]) * t
            nx, nz = a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t
            yy = y
            if nx > 0.3:                       # hanging free on the outside
                drop = max(0.0, 52.0 - zz)
                g = _smooth(drop / 26.0)
                flare = math.exp(-((y - y0) / 3.5) ** 2) * 1.0 + math.exp(-((y - y1) / 3.5) ** 2) * 1.6
                # stands off the arm below the shoulder, then folds that deepen downwards
                x += nx * (0.9 * _smooth(drop / 30.0) + 4.3 * g * (0.1 + 0.9 * folds(y, drop) ** 1.4)
                           + 1.1 * g * flare)
                yy = ym + (y - ym) * (1.0 - 0.07 * g)        # folds gather the width
            elif nx < -0.3:                    # tucked down the inside of the arm
                drop = max(0.0, 50.0 - zz)
                wave = 0.5 + 0.5 * math.sin(2 * math.pi * y / 11.0 + 0.8 * math.sin(y / 6.5) + 0.04 * zz)
                x += nx * 1.1 * _smooth(drop / 14.0) * wave
            elif nz > 0.5:                     # loose ripples where it lies over the arm top
                rip = 0.5 + 0.5 * math.sin(2 * math.pi * y / 9.0 + 0.25 * x)
                x += nx * 0.3 * rip
                zz += nz * 0.3 * rip
            row.append((md.add((x, yy, zz)), target))
        rows.append(row)
    # a heavier, looser weave than the sofa's upholstery linen (same map at a
    # 1.5x repeat), so the throw reads as a separate textile
    tt = 1.5 * FAB
    for j in range(nt):
        for i in range(ns):
            a, b = rows[j][i], rows[j][i + 1]
            c, d = rows[j + 1][i + 1], rows[j + 1][i]
            yv0 = (y0 + (y1 - y0) * j / nt) / tt
            yv1 = (y0 + (y1 - y0) * (j + 1) / nt) / tt
            md.face((a[0], b[0], c[0], d[0]),
                    ((a[1] / tt, yv0), (b[1] / tt, yv0), (c[1] / tt, yv1), (d[1] / tt, yv1)))
    node = _build(md, "Sofa_Throw", tt)
    sh = rt.Shell()
    kit.setp(sh, "outerAmount", 0.5)
    kit.setp(sh, "innerAmount", 0.0)
    rt.addModifier(node, sh)
    kit.soften(node, (14.0, 0.25, 0.25), 1, 91)
    return kit.part(node, "bedding", None, None)     # cotton: in linen it vanished into the sofa


def build_sofa():
    """3-seat sofa W 220 x D 95 x H 82, seat height 44: low rounded arms,
    bullnose back frame, piped seat and back cushions, recessed oak plinth on
    four tapered oak legs, three scatter cushions leaning against the back
    (and each other), a linen throw draped over the right arm."""
    nodes = []
    for x in (-97.0, 97.0):
        for y in (-34.5, 34.5):
            nodes.append(_leg_round(x, y, 0.0, 11.0, 2.3, 1.5, "wood_light", OAK, "Sofa_Leg", 28, 0))
    plinth = _slab(105.0, 42.5, 11.0, 14.0, 6.0, p=10, q=6, rb=(0.4, 0.4), rt_=(0.4, 0.4),
                   mb=1, ms=1, mt=1)
    nodes.append(_hard(plinth, "Sofa_Plinth", "wood_light", OAK))

    deck = _slab(93.0, 40.75, 14.0, 28.0, 3.0, p=10, q=6, rb=(2.0, 2.0), rt_=(2.5, 2.5),
                 mb=2, ms=2, mt=2, cy=-6.75, bulge=0.5)
    nodes.append(_soft(deck, "Sofa_Deck", "upholstery", (40.0, 0.25, 0.2), 11))
    for s in (-1, 1):
        arm = _slab(9.0, 44.25, 14.0, 60.0, 9.0, p=4, q=12, rb=(2.2, 2.2), rt_=(7.5, 8.0),
                    mb=2, ms=3, mt=4, cx=s * 101.0, cy=-3.25, bulge=0.6)
        nodes.append(_soft(arm, "Sofa_Arm", "upholstery", (35.0, 0.3, 0.3), 21 + s))
    back = _slab(110.0, 7.0, 14.0, 82.0, 7.0, p=18, q=4, rb=(2.0, 2.0), rt_=(6.5, 7.0),
                 mb=2, ms=4, mt=4, cy=40.5, bulge=0.5)
    nodes.append(_soft(back, "Sofa_BackFrame", "upholstery", (45.0, 0.35, 0.3), 31))

    # ---- seat cushions (piped box cushions, crowned, pressed into their neighbours)
    seat_mds = []
    for s in (-1, 1):
        def seat_def(pt, s=s):
            x, y, z = pt
            wt = max(0.0, (z - 28.0) / 15.6) ** 2
            z -= 1.6 * _smooth((y + 3.0) / 10.0) * wt          # squashed under the back cushion
            # the filling crowns the middle: the front corners sit a little lower
            z -= 0.7 * min(1.0, abs(x - s * 45.975) / 45.8) ** 6 * _smooth((-y - 30.0) / 18.0) * wt
            # sat-in: a broad 2.2 cm hollow on one seat, a lighter one on the other
            # (at 0.7 cm the cushions read as a pristine CG primitive)
            if s < 0:
                z -= 2.2 * math.exp(-((x + 50.0) ** 2 + (y + 22.0) ** 2) / 650.0) * wt
                x = _smax(_smin(x, -0.12, 0.35), -91.1, 0.35)
            else:
                z -= 1.1 * math.exp(-((x - 38.0) ** 2 + (y + 26.0) ** 2) / 520.0) * wt
                x = _smin(_smax(x, 0.12, 0.35), 91.1, 0.35)
            y = _smin(y, 7.8, 0.4)
            return (x, y, z)
        md = _slab(45.825, 27.75, 28.0, 43.6, 5.0, p=12, q=8, rb=(2.4, 2.4), rt_=(3.2, 3.2),
                   mb=2, ms=2, mt=4, cx=s * 45.975, cy=-20.75 - 0.25 * s, crown=1.1 + 0.15 * s,
                   bulge=1.0, piping=("top", "bottom"), pipe_r=0.42, deform=seat_def, uv_tile=FAB)
        seat_mds.append(md)
        nodes.append(_soft(md, "Sofa_SeatCushion", "upholstery", (22.0, 0.6, 0.6), 51 + s, own_uv=True))

    # ---- back cushions: built lying down, stood up, tilted 9 deg, settled on the deck
    tilt = math.radians(9.0)
    ct, st = math.cos(tilt), math.sin(tilt)
    back_mds = []
    for s in (-1, 1):
        def sag(pt, cx=s * 45.975):
            x, y, z = pt
            y -= 2.0 * max(0.0, 1.0 - ((x - cx) / 45.8) ** 2) * _smooth((y - 12.0) / 13.0)
            return (x, y, z)
        # softer top corners than bottom ones: the filling rounds the top of a loose back cushion
        md = _slab(45.825, 25.0, 0.0, 17.0, [(5.0, 5.0), (5.0, 5.0), (8.0, 8.0), (8.0, 8.0)], p=12, q=8,
                   rb=(3.0, 3.0), rt_=(3.8, 3.8), mb=2, ms=2, mt=4, cx=s * 45.975, cy=0.0, crown=3.0,
                   crown_b=0.8, bulge=1.2, piping=("top",), pipe_r=0.42, deform=sag, uv_tile=FAB)

        def stand(pt):
            x, y, z = pt
            Y, Z = 8.5 - z, y + 25.0
            return (x, Y * ct + Z * st, -Y * st + Z * ct)
        md.map(stand)
        dz = 28.0 + 8.5 * st
        dy = 33.2 - max(v[1] for v in md.v)
        md.map(lambda pt, dy=dy, dz=dz: (pt[0], pt[1] + dy, pt[2] + dz))
        y_rb = 8.5 * ct + dy

        def settle(pt, s=s, y_rb=y_rb):
            x, y, z = pt
            zb = 28.0 + (y_rb - y) * math.tan(tilt)
            w = math.exp(-max(z - zb, 0.0) / 5.0)
            z -= w * (zb - 28.0)
            y -= (3.4 if s < 0 else 2.4) * max(0.0, (z - 28.0) / 50.0) ** 3   # top flops forward
            if s < 0:
                x = _smax(_smin(x, -0.12, 0.35), -91.1, 0.35)
            else:
                x = _smin(_smax(x, 0.12, 0.35), 91.1, 0.35)
            return (x, y, _smax(z, 28.0, 0.3))
        md.map(settle)
        back_mds.append(md)
        ax = [(1.0, 0.0, 0.0), (0.0, st, ct), (0.0, -ct, st)]        # slab X, Y (height), Z (front)
        org = (s * 45.975, 8.5 * ct + 25.0 * st + dy, -8.5 * st + 25.0 * ct + dz)
        nodes.append(_soft_framed(md, "Sofa_BackCushion", "upholstery", (21.0, 0.7, 0.65), 61 + s, ax, org,
                                  own_uv=True))

    # ---- scatter cushions leaning on the back cushions (and on each other)
    seat_grid = _Grid2(0, 1).add([v for md in seat_mds for v in md.v])
    lean_grid = _Grid2(0, 2).add([v for md in back_mds for v in md.v])

    def seat_top(x, y):
        pts = seat_grid.near(x, y, 4.0)
        return max(p[2] for p in pts) if pts else 43.6

    def back_front(x, z):
        pts = lean_grid.near(x, z, 4.5)
        return min(p[1] for p in pts) if pts else None

    specs = [  # mat, size, thick, x, yaw, lean, roll, seed, piping, chop, uv variants (front, back)
        # chop dents 2-2.4 cm: at 0.4-1 cm the cushions read as stiff identical panels
        ("cushion", 44.0, 16.0, -63.0, 8.0, 27.0, -3.0, 71, False, 1.8, (1, 6)),
        ("velvet", 40.0, 14.0, -36.0, -14.0, 19.0, 4.0, 72, True, 0.0, (3, 4)),
        ("cushion", 46.0, 15.0, 55.0, -6.0, 28.0, 2.5, 73, False, 1.1, (6, 2)),
    ]
    for mat, size, thick, xc, yaw, lean, roll, seed, pipe, chop, uvv in specs:
        # each its own pinch, loft, wrinkling and corner ears: one V-chopped
        # slab three times read as cut-outs
        pinch, puff, wrinkle, ear = {71: (0.07, 0.9, 1.4, 1.0), 72: (0.11, 1.15, 0.9, 1.5),
                                     73: (0.09, 0.7, 1.6, 1.15)}[seed]
        md = _pillow_md(size, size, thick, pinch=pinch, puff=puff, wrinkle=wrinkle, ear=ear,
                        piping=pipe, pipe_r=0.4, dent=chop, seed=seed, uv_var=uvv)
        axes, org = _lean_pillow(md, xc, yaw, lean, roll, seat_top, back_front)
        lean_grid.add(md.v)
        # own UVs, one repeat per 46 cm face: at a 20-30 cm repeat the velvet
        # map's crushed-pile blotches repeat visibly across a face (and the
        # earlier version of the map printed a frame); each face is turned /
        # mirrored differently, so the blotches never sit in the same place twice
        nodes.append(_soft_framed(md, "Sofa_Scatter_" + mat, mat, (12.0, 0.6, 0.7), seed, axes, org,
                                  tile=46.0, own_uv=True, smooth=0))
    nodes.append(_throw(seat_top))
    return kit.group("Sofa", nodes)


# ================================================================== armchair
def _shell_section(y, k, count, yf, yb, zb):
    """Closed (n, z) section of the tub shell; n points away from the seat."""
    f = max(0.0, min(1.0, (y - yf) / (yb - yf)))
    zt = 57.0 + 21.0 * f * f
    n_out = 7.5
    n_in_b = -7.5 - 7.0 * k
    zk = 31.0
    n_in_t = n_in_b + k * (zt - zk) * math.tan(math.radians(15.0))
    r_top = min(6.6, 0.47 * (n_out - n_in_t))
    n_mid = 0.5 * (n_out + n_in_b)
    poly = [(n_mid, zb), (n_out, zb), (n_out, zt), (n_in_t, zt), (n_in_b, zk), (n_in_b, zb)]
    dense = _fillet2d(poly, [0.0, 3.0, r_top, r_top, 9.0, 3.0], closed=True)
    return _resample_closed(dense, count, 4.0)


def _shell_md():
    """Continuous back + arms: a varying section swept along a U (two straight
    arms and a semicircular back), each arm end closed by revolving the outer
    half-section 180 degrees (a true rounded nose)."""
    K = 36
    R, yo, yf, zb = 32.5, 2.5, -35.0, 9.0
    st = []
    n_arm, n_arc = 14, 36
    for i in range(n_arm):
        st.append((-R, yf + (yo - yf) * i / n_arm, -1.0, 0.0, 0.0))
    for i in range(n_arc + 1):
        phi = math.pi * (1.0 - i / float(n_arc))
        k = math.sin(phi) ** 1.5 if 0.0 < phi < math.pi else 0.0
        st.append((R * math.cos(phi), yo + R * math.sin(phi), math.cos(phi), math.sin(phi), k))
    for i in range(1, n_arm + 1):
        st.append((R, yo + (yf - yo) * i / n_arm, 1.0, 0.0, 0.0))
    md = _MD()
    rings, secs = [], []
    for (x, y, nx, ny, k) in st:
        sec = _shell_section(y, k, K, yf, yo + R, zb)
        secs.append(sec)
        rings.append([md.add((x + n * nx, y + n * ny, z)) for (n, z) in sec])
    S = len(rings)
    for a in range(S - 1):
        for i in range(K):
            i2 = (i + 1) % K
            md.face((rings[a][i], rings[a][i2], rings[a + 1][i2], rings[a + 1][i]))
    half, M = K // 2, 8
    for end in (0, S - 1):
        x, y, nx, ny, _k = st[end]
        sec, ring = secs[end], rings[end]
        ty = 1.0 if end == 0 else -1.0          # path tangent (y) at this end
        sgn = -1.0 if end == 0 else 1.0          # nose grows along -T (start) / +T (end)
        mer = [[ring[i] for i in range(half + 1)]]
        for j in range(1, M):
            al = math.pi * j / M
            ca, sa = math.cos(al), math.sin(al)
            row = [ring[0]]
            for i in range(1, half):
                n, z = sec[i]
                row.append(md.add((x + n * ca * nx, y + n * (ca * ny + sgn * sa * ty), z)))
            row.append(ring[half])
            mer.append(row)
        mer.append([ring[(K - i) % K] for i in range(half + 1)])
        for j in range(M):
            for i in range(half):
                a, b = mer[j][i], mer[j][i + 1]
                c, d = mer[j + 1][i + 1], mer[j + 1][i]
                md.face((a, b, c, d) if end == S - 1 else (a, d, c, b))
    return md


def build_armchair():
    """Lounge tub chair W 80 x D 85 x H 78, seat 42: one continuous boucle shell
    (reclined lumbar back flowing into low arms with rounded noses), D-shaped
    crowned seat cushion on an upholstered platform, short tapered oak legs."""
    nodes = []
    for (x, y) in ((-32.5, -33.0), (32.5, -33.0), (-23.0, 21.8), (23.0, 21.8)):
        nodes.append(_leg_round(x, y, 0.0, 9.0, 2.3, 1.6, "wood_light", OAK, "Armchair_Leg"))
    nodes.append(_soft(_shell_md(), "Armchair_Shell", "upholstery_alt", (30.0, 0.3, 0.3), 81))
    d_back = [(5.0, 5.0), (5.0, 5.0), (25.8, 18.25), (25.8, 18.25)]
    plat = _slab(25.8, 29.5, 9.0, 27.5, d_back, p=12, q=10, rb=(2.5, 2.5), rt_=(3.0, 3.0),
                 mb=2, ms=2, mt=2, cy=-8.5, bulge=0.5)
    nodes.append(_soft(plat, "Armchair_Platform", "upholstery_alt", (30.0, 0.25, 0.2), 82))

    def cush_def(pt):
        x, y, z = pt
        wt = max(0.0, (z - 27.5) / 14.5) ** 2
        z -= 0.6 * math.exp(-((x - 2.0) ** 2 + (y + 13.0) ** 2) / 300.0) * wt      # sat-in, a little off centre
        z -= 0.8 * min(1.0, abs(x) / 25.9) ** 4 * _smooth((-y - 22.0) / 12.0) * wt   # softer front corners
        return (x + 0.3, y, z)
    c_back = [(6.0, 6.0), (6.0, 6.0), (25.9, 18.6), (25.9, 18.6)]
    cush = _slab(25.9, 30.65, 27.5, 42.0, c_back, p=12, q=10, rb=(3.0, 3.0), rt_=(5.0, 4.6),
                 mb=2, ms=2, mt=3, cy=-9.35, crown=1.6, bulge=0.9, deform=cush_def)
    nodes.append(_soft(cush, "Armchair_SeatCushion", "upholstery_alt", (22.0, 0.4, 0.45), 83))
    return kit.group("Armchair", nodes)


# ============================================================== coffee table
def build_coffee_table():
    """W 110 x D 60 x H 38: 3 cm walnut top with eased edges, walnut lower
    shelf the legs pass through (clamped by brass collars), tapered
    brushed-brass legs on mounting plates, rubber glides."""
    nodes = []
    top = kit.cbox(110.0, 60.0, 3.0, 0.6, 0.0, 0.0, 35.0, segs=4)
    top.name = "Coffee_Top"
    nodes.append(kit.part(top, "wood_dark", WALNUT))
    shelf = kit.cbox(102.0, 52.0, 1.8, 0.45, 0.0, 0.0, 10.0, segs=3)
    shelf.name = "Coffee_Shelf"
    nodes.append(kit.part(shelf, "wood_dark", WALNUT))
    for x in (-48.0, 48.0):
        for y in (-23.0, 23.0):
            nodes.append(_leg_round(x, y, 0.35, 34.6, 1.25, 0.85, "metal_brass", METAL, "Coffee_Leg", 32, 0))
            nodes.append(_disc(x, y, 34.6, 35.0, 3.0, "metal_brass", METAL, "Coffee_LegPlate", 0.1, 40, 0))
            nodes.append(_disc(x, y, 0.0, 0.35, 0.8, "rubber", 20.0, "Coffee_Glide", 0.08, 20, 0))
            # brass collars clamp the shelf where the legs pass through it
            for z0, z1 in ((9.15, 10.0), (11.8, 12.65)):
                rl = 0.85 + 0.4 * (z0 - 0.35) / 34.25
                nodes.append(_disc(x, y, z0, z1, rl + 0.42, "metal_brass", METAL, "Coffee_Collar", 0.12, 32, 0))
    return kit.group("CoffeeTable", nodes)


# ================================================================ TV console
def _bar_handle(x, y_face, z, length=10.0, standoff=2.2, r=0.45, name="Console_Handle"):
    md = _MD()
    yb = y_face - standoff
    md.merge(_tube_md([(x, yb, z - length / 2.0 + i * length / 8.0) for i in range(9)], r, 10))
    for dz in (-3.4, 3.4):
        md.merge(_tube_md([(x, y_face + 0.3, z + dz), (x, yb, z + dz)], 0.3, 8))
    return _hard(md, name, "metal_black", METAL)


def build_tv_console():
    """W 160 x D 40 x H 48 walnut carcass: four inset doors with 3 mm gaps
    and a centre divider, slim black bar pulls, tapered black square legs on
    mounting plates."""
    W, D, zb, zt, t, gap = 160.0, 40.0, 14.0, 48.0, 1.8, 0.3
    nodes = []
    inner_h = zt - zb - 2 * t

    def wal(n, name):
        n.name = name
        nodes.append(kit.part(n, "wood_dark", WALNUT))

    wal(kit.cbox(W, D, t, 0.25, 0.0, 0.0, zt - t, segs=3), "Console_Top")
    wal(kit.cbox(W, D, t, 0.25, 0.0, 0.0, zb, segs=3), "Console_Bottom")
    for sx in (-1, 1):
        wal(kit.cbox(t, D, inner_h, 0.2, sx * (W / 2 - t / 2), 0.0, zb + t), "Console_Side")
    wal(kit.cbox(t, D - 0.8, inner_h, 0.2, 0.0, -0.4, zb + t), "Console_Divider")
    wal(kit.cbox(W - 2 * t, 0.8, inner_h, 0.1, 0.0, D / 2 - 0.4, zb + t), "Console_Back")
    open_w = (W - 3 * t) / 2.0
    door_w = (open_w - 3 * gap) / 2.0
    door_h = inner_h - 2 * gap
    zc = zb + t + gap + door_h / 2.0
    for comp in (-1, 1):
        x0 = -W / 2 + t if comp < 0 else t / 2
        for k in range(2):
            dx0 = x0 + gap + k * (door_w + gap)
            wal(kit.cbox(door_w, t, door_h, 0.2, dx0 + door_w / 2.0, -D / 2 + t / 2, zb + t + gap, segs=3),
                "Console_Door")
            hx = dx0 + door_w - 3.0 if k == 0 else dx0 + 3.0
            nodes.append(_bar_handle(hx, -D / 2, zc))
    for x in (-72.0, 72.0):
        for y in (-15.0, 15.0):
            leg = _slab(1.2, 1.2, 0.0, 13.6, 0.45, p=4, q=4, rb=(0.15, 0.15), rt_=(0.15, 0.15),
                        mb=1, ms=2, mt=1, cx=x, cy=y, scale_b=0.7, amin=1)
            nodes.append(_hard(leg, "Console_Leg", "metal_black", METAL))
            pl = kit.cbox(5.0, 5.0, 0.4, 0.12, x, y, 13.6, segs=2)
            pl.name = "Console_LegPlate"
            nodes.append(kit.part(pl, "metal_black", METAL))
    return kit.group("TVConsole", nodes)


def build_tv():
    """55-inch TV 123 x 71 x 2.5: black-glass screen inset in a 7 mm bezel on
    a plastic body with the electronics housing on its lower back, slim
    pedestal stand (plate + neck) standing on z = 0."""
    nodes = []
    base = kit.cbox(46.0, 22.0, 1.0, 0.45, 0.0, 1.5, 0.0, segs=3)
    base.name = "TV_StandBase"
    nodes.append(kit.part(base, "metal_black", METAL))
    neck = kit.cbox(7.0, 1.8, 19.0, 0.5, 0.0, 3.1, 1.0, segs=3)
    neck.name = "TV_StandNeck"
    nodes.append(kit.part(neck, "metal_black", METAL))
    body = kit.cbox(123.0, 2.5, 71.0, 0.35, 0.0, 0.0, 6.0, segs=3)
    body.name = "TV_Body"
    # black_plastic is a seamless matte swatch with a 15 cm repeat (the first
    # reference was a whole moulded tray, which forced a 10 km projection)
    nodes.append(kit.part(body, "plastic_black", 15.0))
    # the electronics housing on the lower back (a 55-inch panel is 2.5 cm thin
    # only above it); the stand neck plugs into its underside
    rear = kit.cbox(92.0, 3.2, 40.0, 1.0, 0.0, 2.55, 12.0, segs=4)
    rear.name = "TV_RearHousing"
    nodes.append(kit.part(rear, "plastic_black", 15.0))
    scr = kit.cbox(121.6, 0.14, 69.6, 0.04, 0.0, -1.28, 6.7, segs=1)
    scr.name = "TV_Screen"
    nodes.append(kit.part(scr, "screen", 125.0))
    return kit.group("TV", nodes)


# ================================================================ floor lamp
def build_floor_lamp():
    """160 cm floor lamp: domed brass base on a rubber pad, brass stem with a
    foot collar, washer + socket, warm globe bulb, linen drum shade (rolled
    top and bottom edges, lapped seam at the back) on a three-spoke brass
    spider with wire rims."""
    nodes = []
    pad = _fillet2d([(0.0, 0.0), (14.2, 0.0), (14.2, 0.3), (0.0, 0.3)], [0, 0.1, 0.05, 0])
    nodes.append(_hard(_revolve_md(pad, 40), "Lamp_Pad", "rubber", 20.0))
    base = _fillet2d([(0.0, 0.3), (14.6, 0.3), (15.0, 1.0), (15.0, 1.7), (12.0, 2.3), (2.4, 2.8), (0.0, 2.85)],
                     [0, 0.25, 0.4, 0.6, 2.0, 1.5, 0])
    nodes.append(_hard(_revolve_md(base, 48), "Lamp_Base", "metal_brass", METAL))
    stem = _fillet2d([(0.0, 2.6), (1.7, 2.6), (1.7, 5.2), (1.05, 6.0), (1.05, 127.5), (0.0, 127.5)],
                     [0, 0.1, 0.3, 0.4, 0.2, 0])
    nodes.append(_hard(_revolve_md(stem, 20), "Lamp_Stem", "metal_brass", METAL))
    nodes.append(_disc(0.0, 0.0, 127.4, 128.2, 2.6, "metal_brass", METAL, "Lamp_Washer", 0.12, 24))
    sock = _fillet2d([(0.0, 128.2), (1.9, 128.2), (1.9, 134.5), (1.6, 135.0), (1.6, 136.2), (0.0, 136.2)],
                     [0, 0.1, 0.2, 0.2, 0.1, 0])
    nodes.append(_hard(_revolve_md(sock, 20), "Lamp_Socket", "metal_brass", METAL))
    bulb = [(0.0, 135.9), (1.35, 135.9), (1.35, 137.1)]
    a0 = math.asin(1.35 / 4.5)
    for i in range(1, 13):
        a = -math.pi / 2 + a0 + (math.pi - a0) * i / 12.0
        bulb.append((4.5 * math.cos(a), 141.4 + 4.5 * math.sin(a)))
    bulb[-1] = (0.0, 145.9)
    nodes.append(_hard(_revolve_md(bulb, 24), "Lamp_Bulb", "emissive_warm", 20.0))
    shade = _fillet2d([(22.0, 124.0), (22.0, 160.0), (21.6, 160.0), (21.6, 124.0)],
                      [0.15, 0.15, 0.15, 0.15], closed=True)
    smd = _revolve_md(shade, 56, closed=True)
    for zr in (124.3, 159.7):                  # fabric rolled over the top and bottom rings
        circ = [(21.93 * math.cos(2 * math.pi * i / 56), 21.93 * math.sin(2 * math.pi * i / 56), zr)
                for i in range(56)]
        smd.merge(_tube_md(circ, 0.3, 6, closed=True, normals=[(c[0], c[1], 0.0) for c in circ]))
    nodes.append(_hard(smd, "Lamp_Shade", "shade", FAB))
    # the lapped vertical seam of the shade fabric, turned towards the back
    seam = kit.cbox(1.3, 0.12, 34.8, 0.05, 0.0, 0.0, 0.0, segs=2)
    seam.name = "Lamp_ShadeSeam"
    a = math.radians(105.0)
    nodes.append(kit.part(_orient(seam, 21.98 * math.cos(a), 21.98 * math.sin(a), 124.6, 15.0), "shade", FAB))
    wire = _MD()
    for zr in (124.5, 159.5):
        circ = [(21.35 * math.cos(2 * math.pi * i / 48), 21.35 * math.sin(2 * math.pi * i / 48), zr)
                for i in range(48)]
        wire.merge(_tube_md(circ, 0.22, 6, closed=True,
                            normals=[(c[0], c[1], 0.0) for c in circ]))
    for i in range(3):
        a = 2 * math.pi * i / 3 + 0.5
        p0 = (2.3 * math.cos(a), 2.3 * math.sin(a), 127.8)
        p1 = (21.3 * math.cos(a), 21.3 * math.sin(a), 124.6)
        wire.merge(_tube_md([p0, _add(_mul(p0, 0.5), _mul(p1, 0.5)), p1], 0.2, 6))
    nodes.append(_hard(wire, "Lamp_Spider", "metal_brass", METAL))
    return kit.group("FloorLamp", nodes)


# ================================================================ side table
def build_side_table():
    """Round side table D 45 x H 52: 2.6 cm Calacatta disc with eased edges on
    a brass pedestal (domed base, slim column, flared head plate)."""
    nodes = []
    top = _fillet2d([(0.0, 49.4), (22.5, 49.4), (22.5, 52.0), (0.0, 52.0)], [0, 0.3, 0.5, 0])
    nodes.append(_hard(_revolve_md(top, 56), "Side_Top", "stone_worktop", STONE))
    ped = _fillet2d([(0.0, 0.0), (16.0, 0.0), (16.0, 1.5), (2.0, 2.6), (2.0, 47.0), (7.5, 48.8),
                     (7.5, 49.4), (0.0, 49.4)],
                    [0, 0.4, 0.5, 1.2, 2.5, 0.3, 0.15, 0])
    nodes.append(_hard(_revolve_md(ped, 36), "Side_Pedestal", "metal_brass", METAL))
    return kit.group("SideTable", nodes)


# ===================================================================== decor
def _book(W, D, T, cx, cy, z, deg, name="Book", cover="paper"):
    """Hardback: two boards and a rounded spine (paper-covered) wrapped
    around a recessed page block. The page block uses the matte off-white
    'bedding' cotton: 'paper' resolves to kraft board in the scene, which
    made the page edges brown like the covers."""
    parts = []
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))

    def put(node, ox, oy, oz, mat=cover):
        _orient(node, cx + ox * c - oy * s, cy + ox * s + oy * c, z + oz, deg)
        node.name = name
        parts.append(kit.part(node, mat, 30.0))

    put(kit.cbox(W - 0.3, D, 0.25, 0.08, 0, 0, 0, segs=2), 0.15, 0.0, 0.0)
    put(kit.cbox(W - 0.3, D, 0.25, 0.08, 0, 0, 0, segs=2), 0.15, 0.0, T - 0.25)
    # rounded spine (the cover wraps the backed page block) proud of the boards
    put(kit.cbox(0.8, D + 0.04, T, min(0.38, 0.3 * T), 0, 0, 0, segs=4), -W / 2.0 + 0.4, 0.0, 0.0)
    put(kit.cbox(W - 0.7, D - 0.6, T - 0.5, 0.05, 0, 0, 0, segs=1), 0.1, 0.0, 0.25, "bedding")
    return parts


def build_decor_books(variant=0):
    """Coffee-table vignette: four stacked hardbacks with a glazed ceramic
    bowl on top and a pillar candle beside them. variant=1 (the sideboard):
    three books of other sizes in linen, leather and kraft covers beside a
    terracotta bottle, so the two vignettes in one frame are not copies."""
    if variant == 1:
        return _decor_books_alt()
    nodes = []
    z = 0.0
    # covers differ (linen, a printed jacket, kraft, leather): four identical
    # cream slabs read as blank dummies
    for (W, D, T, deg, dx, dy, cover) in ((30.0, 23.0, 2.4, -3.0, 0.0, 0.0, "linen"),
                                         (27.0, 20.5, 3.4, 4.0, 0.8, -0.6, "art_paper"),
                                         (25.0, 18.5, 1.8, -2.0, -0.6, 0.5, "paper"),
                                         (21.5, 15.5, 2.8, 7.0, 0.4, -0.3, "leather")):
        nodes.extend(_book(W, D, T, dx, dy, z, deg, cover=cover))
        z += T
    bowl = _fillet2d([(0.0, 0.35), (3.4, 0.35), (3.6, 0.0), (4.5, 0.0), (4.8, 0.6), (6.9, 2.0),
                      (7.6, 5.6), (7.2, 5.8), (6.6, 2.3), (4.3, 1.0), (0.0, 0.85)],
                     [0, 0.15, 0.12, 0.15, 0.5, 3.0, 0.2, 0.2, 2.8, 1.5, 0])
    nodes.append(_hard(_revolve_md(bowl, 36, x=0.6, y=0.0, z=z), "Decor_Bowl", "ceramic_white", 30.0))
    cx, cy = 20.5, -3.0
    cand = _fillet2d([(0.0, 0.0), (3.5, 0.0), (3.5, 9.0), (3.1, 9.05), (1.0, 8.6), (0.0, 8.5)],
                     [0, 0.15, 0.35, 0.1, 0.8, 0])
    nodes.append(_hard(_revolve_md(cand, 28, x=cx, y=cy), "Decor_Candle", "wax", 15.0))
    wick = _tube_md([(cx, cy, 8.3), (cx + 0.05, cy, 8.9), (cx + 0.18, cy + 0.04, 9.45)], 0.07, 6)
    nodes.append(_hard(wick, "Decor_Wick", "plastic_black", 30.0, smooth=0))
    return kit.group("DecorBooks", nodes)


def _decor_books_alt():
    nodes = []
    z = 0.0
    for (W, D, T, deg, dx, dy, cover) in ((33.0, 25.0, 3.2, 3.0, 0.0, 0.0, "linen"),
                                         (28.5, 21.5, 2.1, -6.0, -0.8, 0.5, "leather"),
                                         (24.0, 17.0, 3.7, 2.0, 0.6, -0.4, "paper")):
        nodes.extend(_book(W, D, T, dx, dy, z, deg, cover=cover))
        z += T
    bottle = _fillet2d([(0.0, 0.0), (3.9, 0.0), (4.7, 0.7), (5.3, 4.5), (5.0, 8.5), (3.3, 12.5),
                        (1.5, 15.0), (1.3, 17.5), (1.75, 17.9), (1.35, 18.2), (0.0, 18.2)],
                       [0, 0.3, 1.2, 2.5, 2.5, 2.0, 0.8, 0.3, 0.2, 0.1, 0])
    nodes.append(_hard(_revolve_md(bottle, 36, x=27.0, y=-2.0), "Decor_Bottle", "plant_pot", 20.0))
    return kit.group("DecorBooksAlt", nodes)


def _mug_nodes(x=0.0, y=0.0, z=0.0, yaw=0.0):
    """Glazed stoneware mug, 8.4 cm across, 9.6 cm tall, with a looped handle."""
    prof = _fillet2d([(0.0, 0.3), (3.6, 0.3), (3.8, 0.0), (4.0, 0.0), (4.2, 0.45), (4.2, 9.35), (4.05, 9.6),
                      (3.86, 9.4), (3.86, 0.95), (3.5, 0.7), (0.0, 0.7)],
                     [0, 0.12, 0.1, 0.12, 0.5, 0.2, 0.12, 0.2, 0.4, 0.3, 0])
    out = [_hard(_revolve_md(prof, 40, x=x, y=y, z=z), "Decor_Mug", "ceramic_white", 20.0)]
    c, s_ = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    loop = [(4.0, 7.7), (5.5, 7.9), (6.7, 6.9), (6.9, 4.9), (6.0, 3.3), (4.0, 2.8)]
    path = [(x + r * c, y + r * s_, z + h) for r, h in loop]
    out.append(_hard(_tube_md(path, 0.48, 10), "Decor_MugHandle", "ceramic_white", 20.0))
    return out


def build_mug(yaw=0.0):
    """A mug left on a table: a lived-in touch (spotless, empty surfaces read as CG)."""
    return kit.group("Mug", _mug_nodes(yaw=yaw))


def _drink_glass_nodes(x=0.0, y=0.0, z=0.0):
    """Plain tumbler, 7 cm across, 9.5 cm tall, 2.5 mm wall, thick base."""
    prof = _fillet2d([(0.0, 0.0), (3.2, 0.0), (3.4, 0.25), (3.5, 9.4), (3.38, 9.5), (3.25, 9.4), (3.16, 1.05),
                      (2.9, 0.8), (0.0, 0.8)],
                     [0, 0.25, 0.2, 0.1, 0.08, 0.1, 0.3, 0.3, 0])
    return [_hard(_revolve_md(prof, 48, x=x, y=y, z=z), "Drink_Glass", "glass_solid", 20.0)]


def build_bedside_props(book=True, glass=True, seed=0):
    """Things left on a nightstand around its lamp: a paperback angled at the
    front left, a tumbler at the front right (lamp base clear by 5 mm)."""
    nodes = []
    if book:
        nodes.extend(_book(18.0, 12.0, 2.2, -12.0, -10.0, 0.0, -15.0 + 6.0 * seed, cover="linen" if seed else "leather"))
    if glass:
        nodes.extend(_drink_glass_nodes(13.0, -10.0, 0.0))
    return kit.group("BedsideProps", nodes)


def _branch_md(k, phi, tip, c2, n_leaves, seed):
    """One branch from the vase bottom up through the neck, arcing out, with
    side twigs and small rounded leaves (solid geometry, 'stem' material)."""
    md = _MD()
    o = (math.cos(phi), math.sin(phi), 0.0)
    b0 = (o[0] * 2.0, o[1] * 2.0, 1.6)
    b1 = (o[0] * 0.75, o[1] * 0.75, 28.5)
    path = [_add(_mul(b0, 1 - t), _mul(b1, t)) for t in (0.0, 0.25, 0.5, 0.75)]
    c1 = (b1[0], b1[1], b1[2] + 14.0)
    up = [_bez(b1, c1, c2, tip, i / 20.0) for i in range(21)]
    wr = _Rand(seed + 7)
    wig = [(0.0, 0.0, 0.0)]
    for i in range(1, 21):
        a = wig[-1]
        wig.append((a[0] * 0.6 + wr.uniform(-0.9, 0.9), a[1] * 0.6 + wr.uniform(-0.9, 0.9), 0.0))
    up = [_add(pt, _mul(wg, min(1.0, i / 4.0))) for i, (pt, wg) in enumerate(zip(up, wig))]
    path += up
    nrad = len(path)
    rad = [0.36 - 0.24 * (i / float(nrad - 1)) ** 1.2 for i in range(nrad)]
    md.merge(_tube_md(path, rad, 6))
    rnd = _Rand(seed)

    def leaf(base, along, side, size):
        """Rounded leaf with a short drip tip, folded up along its midrib and
        curling back at the tip (16-triangle fan around the blade centre)."""
        e1 = _norm(_add(_mul(side, math.cos(0.6)), _mul(along, math.sin(0.6))))
        e2 = _norm(_sub(along, _mul(e1, _dot(along, e1))))
        e2 = _rot_axis(e2, e1, rnd.uniform(-0.5, 0.5))
        e3 = _cross(e1, e2)
        # each leaf its own size, width, fold along the vein, tip and wavy
        # margin: one fan shape repeated read as paper cut-outs
        size *= rnd.uniform(0.7, 1.3)
        a, b = size, size * rnd.uniform(0.5, 0.9)
        fold = rnd.uniform(0.06, 0.34)
        tip = rnd.uniform(0.1, 0.32)
        ovate = rnd.uniform(-0.12, 0.12)
        wph, wamp = rnd.uniform(0.0, 6.28), rnd.uniform(0.0, 0.05)
        cen = _add(base, _mul(e1, a + 0.2))
        ci = md.add(cen)
        ring = []
        n = 24
        for j in range(n):
            t = 2 * math.pi * j / n
            tt = min(t, 2 * math.pi - t)
            rr = (1.0 + ovate * math.cos(t) + tip * math.exp(-(tt / 0.3) ** 2)
                  + wamp * math.sin(5.0 * t + wph))
            lift = fold * size * abs(math.sin(t)) * rr - 0.12 * size * max(0.0, math.cos(t)) ** 3
            p = _add(cen, _add(_mul(e1, a * rr * math.cos(t)), _mul(e2, b * rr * math.sin(t))))
            ring.append(md.add(_add(p, _mul(e3, lift))))
        for j in range(n):
            md.face((ci, ring[j], ring[(j + 1) % n]))

    def tangent(pts, i):
        return _norm(_sub(pts[min(i + 1, len(pts) - 1)], pts[max(i - 1, 0)]))

    for j in range(n_leaves):
        i = 3 + int((len(up) - 4) * j / float(n_leaves))
        t_ = tangent(up, i)
        perp = _norm(_cross(t_, (0.0, 0.0, 1.0)))
        side = _rot_axis(perp, t_, (math.pi if j % 2 else 0.0) + rnd.uniform(-0.5, 0.5))
        leaf(up[i], t_, side, 1.9 - 0.6 * j / float(n_leaves) + rnd.uniform(-0.2, 0.2))
    for tw in (0.45, 0.7):
        i = int(len(up) * tw)
        t_ = tangent(up, i)
        perp = _norm(_cross(t_, (0.0, 0.0, 1.0)))
        side = _rot_axis(perp, t_, rnd.uniform(-0.6, 0.6) + (math.pi if tw > 0.5 else 0.0))
        d = _norm(_add(_mul(side, 0.8), _mul(t_, 0.7)))
        tp = [_add(up[i], _add(_mul(d, 9.0 * s), (0.0, 0.0, 2.0 * s * s))) for s in (0.0, 0.33, 0.66, 1.0)]
        md.merge(_tube_md(tp, [0.18, 0.15, 0.12, 0.09], 5))
        for s in (0.4, 0.75, 1.0):
            ti = tp[1] if s < 0.5 else tp[2] if s < 0.9 else tp[3]
            leaf(ti, d, _rot_axis(perp, d, rnd.uniform(-1.5, 1.5)), 1.5 - 0.3 * s)
    return md


class _Rand(object):
    """Tiny deterministic LCG so every build is identical."""

    def __init__(self, seed):
        self.s = (seed * 2654435761) % 4294967296 or 1

    def uniform(self, a, b):
        self.s = (1664525 * self.s + 1013904223) % 4294967296
        return a + (b - a) * self.s / 4294967296.0


def build_decor_vase():
    """Clear glass bud vase (thick base, belly, narrow neck, flared lip) with
    three bent leafy branches rising out of the neck."""
    nodes = []
    prof = _fillet2d([(0.0, 0.0), (4.6, 0.0), (6.8, 5.5), (6.6, 12.0), (3.2, 21.0), (2.4, 26.5), (2.75, 28.0),
                      (2.25, 28.0), (1.95, 26.5), (2.75, 21.0), (6.15, 12.0), (6.35, 5.5), (4.2, 1.1), (0.0, 1.1)],
                     [0, 0.5, 3.0, 4.0, 3.0, 1.0, 0.25, 0.2, 1.0, 3.0, 4.0, 3.0, 0.8, 0])
    nodes.append(_hard(_revolve_md(prof, 40), "Vase_Glass", "glass_solid", 30.0))
    # water up the belly, 0.3 mm inside the glass: the stems bend at the line
    water = _fillet2d([(0.0, 1.13), (4.17, 1.13), (6.32, 5.5), (6.12, 12.0), (5.36, 14.0), (0.0, 14.0)],
                      [0, 0.8, 3.0, 4.0, 0.1, 0])
    nodes.append(_hard(_revolve_md(water, 40), "Vase_Water", "water", 30.0))
    br = _MD()
    for k, (phi, tip, c2, nl) in enumerate((
            (math.radians(150), (-24.0, 7.0, 72.0), (-10.0, 4.0, 66.0), 11),
            (math.radians(30), (7.0, -3.0, 86.0), (3.0, -1.0, 70.0), 12),
            (math.radians(270), (27.0, 9.0, 60.0), (15.0, 6.0, 70.0), 10))):
        br.merge(_branch_md(k, phi, tip, c2, nl, 90 + k))
    nodes.append(_hard(br, "Vase_Branches", "twig", 20.0))
    return kit.group("DecorVase", nodes)


# ===================================================================== plant
# Outline of the leaf in the monstera_leaf maps, as radii (in UV units) of 72
# rays (5-degree steps, 0 = +U, counter-clockwise) from the petiole attach
# point at UV (0.5, 0.245). Traced from the albedo AND opacity masks with the
# marginal slits and the basal sinus closed (the opacity map still cuts
# those): the card is trimmed to the leaf, so the light fringe where the
# opacity mask overshoots the leaf along its lower lobes is cut away and the
# flat-shaded preview reads as a leaf instead of a square.
_LEAF_UV0 = (0.5, 0.245)
_LEAF_RAD = [
    0.3623, 0.3799, 0.3926, 0.4023, 0.4277, 0.4502, 0.4639, 0.4834, 0.5098, 0.5352, 0.5557, 0.5420,
    0.5811, 0.6064, 0.6162, 0.6377, 0.6514, 0.6553, 0.6787, 0.6494, 0.6357, 0.6338, 0.6113, 0.5977,
    0.5830, 0.5635, 0.5371, 0.5117, 0.5068, 0.4902, 0.4639, 0.4434, 0.4277, 0.4160, 0.4004, 0.3779,
    0.3555, 0.3271, 0.3232, 0.3154, 0.3027, 0.2861, 0.2676, 0.2529, 0.2441, 0.2275, 0.2070, 0.1846,
    0.1543, 0.0850, 0.0811, 0.0791, 0.0781, 0.0771, 0.0762, 0.0771, 0.0781, 0.1094, 0.1416, 0.1641,
    0.1855, 0.2012, 0.2148, 0.2275, 0.2412, 0.2598, 0.2744, 0.2881, 0.2988, 0.3066, 0.3203, 0.3428,
]


def _leaf_md(L, mirror=False, rings=(0.1, 0.22, 0.36, 0.5, 0.64, 0.77, 0.89, 1.0)):
    """Leaf card trimmed to the leaf outline: a polar mesh around the petiole
    attach point (vertex 0) that keeps the plane's own 0-1 UVs (an L x L card
    centred on the origin, U along +X, V along +Y). mirror flips the geometry
    and the map together, so alternate leaves are not identical."""
    md = _MD()
    au, av = _LEAF_UV0
    sx = -1.0 if mirror else 1.0
    K = len(_LEAF_RAD)

    def put(u, v):
        return md.add((sx * (u - 0.5) * L, (v - 0.5) * L, 0.0)), (u, v)

    c, cuv = put(au, av)
    grid = []
    for f in rings:
        row = []
        for i in range(K):
            th = 2.0 * math.pi * i / K
            r = f * _LEAF_RAD[i]
            row.append(put(au + r * math.cos(th), av + r * math.sin(th)))
        grid.append(row)
    for i in range(K):
        a, b = grid[0][i], grid[0][(i + 1) % K]
        tri = [(c, cuv), a, b] if not mirror else [(c, cuv), b, a]
        md.face([t[0] for t in tri], [t[1] for t in tri])
    for k in range(len(rings) - 1):
        for i in range(K):
            i2 = (i + 1) % K
            q = [grid[k][i], grid[k + 1][i], grid[k + 1][i2], grid[k][i2]]
            if mirror:
                q.reverse()
            md.face([t[0] for t in q], [t[1] for t in q])
    return md


_LEAVES = [  # azimuth, attach z, attach r, card size, tilt (+ = down), droop, cup, twist, yaw
    (12, 104, 13, 38, -10, 32, 18, 8, 10),
    (80, 96, 18, 36, 4, 36, 20, -10, -12),
    (148, 108, 11, 33, -18, 26, 16, 6, 6),
    (205, 92, 20, 37, 10, 38, 20, 12, 14),
    (262, 100, 15, 35, -4, 32, 18, -8, -8),
    (322, 88, 21, 36, 14, 38, 20, 10, 12),
    (45, 74, 22, 31, 22, 40, 18, -6, -6),
    (115, 68, 23, 30, 26, 42, 16, 10, 10),
    (178, 72, 21, 31, 22, 40, 18, -10, -12),
    (238, 64, 24, 28, 30, 44, 16, 6, 8),
    (295, 70, 22, 30, 24, 40, 18, -12, -10),
]


def build_plant():
    """Monstera in a 35 x 38 terracotta pot (rolled collar, thick base) on a
    matching saucer, with a mounded soil top and 11 bent leaf cards (trimmed
    to the leaf outline) on curving petioles with a swollen knee under each
    blade."""
    nodes = []
    pot = _fillet2d([(0.0, 0.0), (12.8, 0.0), (16.0, 30.6), (17.5, 31.0), (17.5, 38.0), (16.1, 38.0),
                     (16.1, 33.0), (14.9, 30.5), (11.6, 1.3), (0.0, 1.3)],
                    [0, 0.6, 0.6, 0.4, 0.6, 0.5, 1.0, 1.0, 1.2, 0])
    nodes.append(_hard(_revolve_md(pot, 48), "Plant_Pot", "plant_pot", 40.0))
    soil = [(0.0, 33.4), (16.2, 33.4), (16.2, 34.0), (14.0, 34.25), (11.0, 34.45), (8.0, 34.6),
            (5.0, 34.7), (2.5, 34.75), (0.0, 34.8)]
    sn = _build(_revolve_md(soil, 40), "Plant_Soil")
    kit.soften(sn, (5.0, 0.15, 0.35), 1, 5)
    nodes.append(kit.part(sn, "soil", 30.0))
    stems = _MD()
    rnd = _Rand(17)
    for i, (az, z, r, L, tilt, droop, cup, twist, yaw) in enumerate(_LEAVES):
        th = math.radians(az)
        radial = (math.cos(th), math.sin(th), 0.0)
        A = (r * radial[0], r * radial[1], float(z))
        dth = th + math.radians(yaw)
        tl = math.radians(tilt)
        d = (math.cos(dth) * math.cos(tl), math.sin(dth) * math.cos(tl), -math.sin(tl))
        n = _norm(_sub((0.0, 0.0, 1.0), _mul(d, d[2])))
        n = _norm(_rot_axis(n, d, math.radians(twist)))
        w = _cross(d, n)
        leaf = _build(_leaf_md(L, mirror=(i % 2 == 1)), "Plant_Leaf", 1.0)
        kit.bend(leaf, float(cup), axis=0, direction=0.0)
        kit.bend(leaf, float(droop), axis=1, direction=-90.0)
        av = rt.getVert(rt.snapshotAsMesh(leaf), 1)                 # the petiole attach vertex
        a = (float(av.x), float(av.y), float(av.z))
        T = _sub(A, _add(_add(_mul(w, a[0]), _mul(d, a[1])), _mul(n, a[2])))
        leaf.transform = rt.Matrix3(rt.Point3(*w), rt.Point3(*d), rt.Point3(*n), rt.Point3(*T))
        nodes.append(kit.part(leaf, "plant_leaf", None, None))
        # petiole: up out of the soil, curving out to just under the leaf base
        ba = th + rnd.uniform(-0.5, 0.5)
        br = rnd.uniform(1.5, 4.5)
        p0 = (br * math.cos(ba), br * math.sin(ba), 33.6)
        p3 = _sub(A, _mul(n, 0.5))
        t_end = _norm((radial[0] * 0.55, radial[1] * 0.55, 1.0))
        p1 = (p0[0], p0[1], p0[2] + 0.45 * (p3[2] - p0[2]))
        p2 = _sub(p3, _mul(t_end, 0.35 * (p3[2] - p0[2])))
        path = [_bez(p0, p1, p2, p3, j / 18.0) for j in range(19)]
        # tapered petiole with the swollen geniculum (the 'knee') just under the blade
        stems.merge(_tube_md(path, [0.75 - 0.33 * j / 18.0 + 0.17 * math.exp(-((j - 16.6) / 1.3) ** 2)
                                    for j in range(19)], 7))
    nodes.append(_hard(stems, "Plant_Stems", "stem", 20.0))
    # matching terracotta saucer: the potted plant stands on its 1 cm floor
    for n in nodes:
        n.pos = rt.Point3(float(n.pos.x), float(n.pos.y), float(n.pos.z) + 1.0)
    sau = _fillet2d([(0.0, 0.0), (14.2, 0.0), (15.5, 3.3), (14.8, 3.3), (13.7, 1.0), (0.0, 1.0)],
                    [0, 0.5, 0.35, 0.3, 0.6, 0])
    nodes.append(_hard(_revolve_md(sau, 48), "Plant_Saucer", "plant_pot", 40.0))
    return kit.group("Plant", nodes)


# =================================================================== preview
_WIDTH = {"sofa": 220, "armchair": 80, "coffee": 110, "console": 160, "tv": 123, "lamp": 45,
          "side": 45, "books": 40, "vase": 55, "plant": 95, "coffeeset": 110}


def _build_key(key):
    return {"sofa": build_sofa, "armchair": build_armchair, "coffee": build_coffee_table,
            "console": build_tv_console, "tv": build_tv, "lamp": build_floor_lamp,
            "side": build_side_table, "books": build_decor_books, "vase": build_decor_vase,
            "plant": build_plant}[key]()


def preview():
    only = [s.strip().lower() for s in os.environ.get("MF_LIVING_ONLY", "").split(",") if s.strip()]
    rot = float(os.environ.get("MF_LIVING_ROT", "0") or 0.0)
    counts = {}

    def track(key, fn):
        start = len(kit.PARTS)
        g = fn()
        faces = 0
        for node, _k, _t, _m in kit.PARTS[start:]:
            try:
                faces += int(rt.getPolygonCount(node)[0])
            except Exception:
                pass
        counts[key] = counts.get(key, 0) + faces
        return g

    if not only:
        kit.place(track("sofa", build_sofa), -235.0, 70.0, 0.0, rot)
        kit.place(track("console", build_tv_console), 20.0, 80.0, 0.0, rot)
        kit.place(track("tv", build_tv), 20.0, 79.0, 48.0, rot)
        kit.place(track("lamp", build_floor_lamp), 175.0, 70.0, 0.0, rot)
        kit.place(track("armchair", build_armchair), -320.0, -70.0, 0.0, rot)
        kit.place(track("coffee", build_coffee_table), -180.0, -70.0, 0.0, rot)
        kit.place(track("books", build_decor_books), -205.0, -72.0, 38.0, 10.0 + rot)
        kit.place(track("vase", build_decor_vase), -145.0, -66.0, 38.0, rot)
        kit.place(track("side", build_side_table), -60.0, -70.0, 0.0, rot)
        kit.place(track("plant", build_plant), 60.0, -70.0, 0.0, 20.0 + rot)
    else:
        x = 0.0
        for key in only:
            w = _WIDTH[key]
            x += w / 2.0
            if key == "coffeeset":                       # table dressed as in the scene
                kit.place(track("coffee", build_coffee_table), x, 0.0, 0.0, rot)
                kit.place(track("books", build_decor_books), x - 30.0, -5.0, 38.0, 10.0 + rot)
                kit.place(track("vase", build_decor_vase), x + 35.0, 5.0, 38.0, rot)
            else:
                kit.place(track(key, lambda key=key: _build_key(key)), x, 0.0, 0.0, rot)
            if key == "console":
                kit.place(track("tv", build_tv), x, -1.0, 48.0, rot)
            x += w / 2.0 + 40.0
    path = os.environ.get("MF_LIVING_STATS")
    if path:
        with open(path, "w") as fh:
            json.dump(counts, fh, indent=1)
