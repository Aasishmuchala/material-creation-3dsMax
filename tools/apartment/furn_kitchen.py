"""Kitchen + dining furniture for the MatForge test apartment (Japandi / warm Scandinavian).

Pieces (centimetres, Z up, FRONT facing -Y, built at the local origin, base on z = 0):
  build_kitchen_run(length=260, sink_at=65, cook_at=225, shelf="auto")
        footprint length x 62 x ~148; back face at y = +31 (wall side), worktop top z = 91
  build_fridge()                 70 x 70 x 200
  build_dining_table()           150 x 90 x 75
  build_dining_chair()           46 x 52 x 80, seat 46
  build_pendant_lamp(drop=80, ceiling=270)
        hangs from a ceiling at z = ceiling (rose on the ceiling, shade top at
        ceiling - drop), so it is placed at z = 0 like every other piece
  build_table_decor()            ~57 x 29 x 25, sits on z = 0 (place it at the table top, 75)

Geometry is generated procedurally in Python (rounded boxes with support loops,
lathes, swept tubes, ring-profile slabs) and emitted as Editable Meshes: big flat
faces shade dead flat, every edge carries a real radius, and nothing relies on
ChamferBox smoothing.  Wooden members are emitted with their local Z axis along
the grain and the fridge doors with local X vertical, so the scene's real-world
box UVW map (oak grain along V, steel brushing along U) runs the grain along each
board, rail and leg and brushes the fridge doors vertically.

preview() builds every piece side by side; set MF_KITCHEN_PREVIEW to
run | run290 | fridge | table | chair | dining | pendant | decor to frame a single piece
(run290 = the run with the arguments apartment_scene.py passes).
"""
import math
import os

from pymxs import runtime as rt

import kit

S = 0.03                      # support-loop offset (cm): confines smoothing gradients to 0.3 mm

# local axes (x, y, z) in piece space: local Z along the grain of the member
GRAIN = {"x": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
         "y": ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
         "z": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))}
BRUSH_VERTICAL = ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0))   # local X up


# ===================================================================== vector helpers
def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def _mul(a, s):
    return tuple(x * s for x in a)


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _len(a):
    return math.sqrt(_dot(a, a))


def _unit(a):
    n = _len(a)
    return _mul(a, 1.0 / n) if n > 1e-12 else tuple(a)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


# ===================================================================== mesh data
class MD(object):
    """Triangle mesh under construction, in piece coordinates (cm)."""

    def __init__(self):
        self.v = []
        self.f = []
        self.ev = []           # edge visibility bits per face (1: ab, 2: bc, 4: ca)
        self.sg = []           # smoothing-group bitmask per face

    def vert(self, p):
        self.v.append((float(p[0]), float(p[1]), float(p[2])))
        return len(self.v) - 1

    def tri(self, a, b, c, sg=1, ev=7):
        self.f.append((a, b, c))
        self.ev.append(ev)
        self.sg.append(sg)

    def quad(self, a, b, c, d, sg=1):
        """CCW quad seen from outside; the a-c diagonal is hidden (TurboSmooth sees quads)."""
        self.f.append((a, b, c))
        self.ev.append(3)
        self.sg.append(sg)
        self.f.append((a, c, d))
        self.ev.append(6)
        self.sg.append(sg)

    def merge(self, other):
        off = len(self.v)
        self.v.extend(other.v)
        self.f.extend((a + off, b + off, c + off) for a, b, c in other.f)
        self.ev.extend(other.ev)
        self.sg.extend(other.sg)
        return self

    def move(self, dx=0.0, dy=0.0, dz=0.0):
        self.v = [(x + dx, y + dy, z + dz) for x, y, z in self.v]
        return self

    def rot(self, deg, axis=(0.0, 0.0, 1.0), about=(0.0, 0.0, 0.0)):
        k = _unit(axis)
        a = math.radians(deg)
        c, s = math.cos(a), math.sin(a)
        out = []
        for p in self.v:
            q = _sub(p, about)
            kq = _cross(k, q)
            d = _dot(k, q) * (1.0 - c)
            out.append(_add(about, (q[0] * c + kq[0] * s + k[0] * d,
                                    q[1] * c + kq[1] * s + k[1] * d,
                                    q[2] * c + kq[2] * s + k[2] * d)))
        self.v = out
        return self

    def scale(self, sx, sy, sz, about=(0.0, 0.0, 0.0)):
        ox, oy, oz = about
        self.v = [(ox + (x - ox) * sx, oy + (y - oy) * sy, oz + (z - oz) * sz) for x, y, z in self.v]
        return self


def _fmt(p):
    return "[%.4f,%.4f,%.4f]" % (p[0], p[1], p[2])


def emit(md, name, mat, tile=None, axes=None, maptype=4):
    """Create an Editable Mesh node from md and register it with kit.part().
    axes: piece-space directions of the node's local X, Y, Z (UVW box map follows them)."""
    ax, ay, az = axes or GRAIN["z"]
    xs = [p[0] for p in md.v]
    ys = [p[1] for p in md.v]
    zs = [p[2] for p in md.v]
    piv = ((min(xs) + max(xs)) * 0.5, (min(ys) + max(ys)) * 0.5, min(zs))
    loc = []
    for p in md.v:
        d = _sub(p, piv)
        loc.append((_dot(d, ax), _dot(d, ay), _dot(d, az)))
    ms = ('(mfk_m = mesh name:"%s" vertices:#(%s) faces:#(%s)\n'
          'mfk_sg = #(%s)\nmfk_ev = #(%s)\n'
          'for i = 1 to mfk_m.numfaces do (setFaceSmoothGroup mfk_m i mfk_sg[i]; '
          'setEdgeVis mfk_m i 1 (bit.get mfk_ev[i] 1); setEdgeVis mfk_m i 2 (bit.get mfk_ev[i] 2); '
          'setEdgeVis mfk_m i 3 (bit.get mfk_ev[i] 3))\n'
          'update mfk_m\n'
          'mfk_m.transform = matrix3 %s %s %s %s\n'
          'mfk_m)') % (name,
                       ",".join(_fmt(p) for p in loc),
                       ",".join("[%d,%d,%d]" % (a + 1, b + 1, c + 1) for a, b, c in md.f),
                       ",".join(str(g) for g in md.sg),
                       ",".join(str(e) for e in md.ev),
                       _fmt(ax), _fmt(ay), _fmt(az), _fmt(piv))
    node = rt.execute(ms)
    kit.part(node, mat, tile, maptype)
    return node


# ===================================================================== profile helpers
def _fillet_poly(pts, radii, seg_deg=15.0):
    """Round the interior corners of a 2D/3D polyline with tangent arcs (radius per point)."""
    if not isinstance(radii, (list, tuple)):
        radii = [radii] * len(pts)
    out = [tuple(pts[0])]
    for i in range(1, len(pts) - 1):
        r = radii[i]
        p0, p1, p2 = pts[i - 1], pts[i], pts[i + 1]
        if r <= 0:
            out.append(tuple(p1))
            continue
        d1 = _unit(_sub(p0, p1))
        d2 = _unit(_sub(p2, p1))
        ang = math.acos(max(-1.0, min(1.0, _dot(d1, d2))))
        if ang < 1e-4 or ang > math.pi - 1e-4:
            out.append(tuple(p1))
            continue
        t = r / math.tan(ang / 2.0)
        tmax = 0.49 * min(_len(_sub(p0, p1)), _len(_sub(p2, p1)))
        if t > tmax:
            t = tmax
            r = t * math.tan(ang / 2.0)
        a = _add(p1, _mul(d1, t))
        b = _add(p1, _mul(d2, t))
        c = _add(p1, _mul(_unit(_add(d1, d2)), r / math.sin(ang / 2.0)))
        va = _unit(_sub(a, c))
        vb = _unit(_sub(b, c))
        om = math.acos(max(-1.0, min(1.0, _dot(va, vb))))
        n = max(2, int(math.ceil(math.degrees(om) / seg_deg)))
        for k in range(n + 1):
            tt = k / float(n)
            if om < 1e-6:
                w0, w1 = 1.0 - tt, tt
            else:
                w0 = math.sin((1.0 - tt) * om) / math.sin(om)
                w1 = math.sin(tt * om) / math.sin(om)
            out.append(_add(c, _mul(_add(_mul(va, w0), _mul(vb, w1)), r)))
    out.append(tuple(pts[-1]))
    return out


def _supported(pts, s=S, min_len=1.2):
    """Insert collinear support points next to both ends of every long segment
    (short segments belong to sampled curves, which shade smoothly without them)."""
    out = [tuple(pts[0])]
    for i in range(1, len(pts)):
        a, b = pts[i - 1], pts[i]
        L = _len(_sub(b, a))
        if L > min_len and L > 4.0 * s:
            d = _mul(_sub(b, a), 1.0 / L)
            out.append(_add(a, _mul(d, s)))
            out.append(_sub(b, _mul(d, s)))
        out.append(tuple(b))
    return out


def _rr_pts(hx, hy, rad, k, s=S, sup=(True, True, True, True)):
    """CCW rounded-rectangle ring: half sizes hx, hy, corner radius rad, k segments per corner.
    sup: support points on the (right, top, left, bottom) straight sides."""
    ex, ey = hx - rad, hy - rad
    centres = ((ex, -ey, -90.0), (ex, ey, 0.0), (-ex, ey, 90.0), (-ex, -ey, 180.0))
    pts = []
    for ci, (cx, cy, a0) in enumerate(centres):
        for i in range(k + 1):
            a = math.radians(a0 + 90.0 * i / k)
            pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
        if sup[ci]:
            nx, ny, na = centres[(ci + 1) % 4]
            a = math.radians(na)
            nxt = (nx + rad * math.cos(a), ny + rad * math.sin(a))
            end = pts[-1]
            L = math.hypot(nxt[0] - end[0], nxt[1] - end[1])
            d = ((nxt[0] - end[0]) / L, (nxt[1] - end[1]) / L)
            pts.append((end[0] + d[0] * s, end[1] + d[1] * s))
            pts.append((nxt[0] - d[0] * s, nxt[1] - d[1] * s))
    return pts


def _rrect2d(w, h, r, k=3):
    sx, sy = w - 2.0 * r > 4.0 * S, h - 2.0 * r > 4.0 * S
    return _rr_pts(w / 2.0, h / 2.0, r, k, S, (sy, sx, sy, sx))


def _rr_ring(hx, hy, rad, k, nx, ny):
    """CCW rounded rectangle with k segments per corner and the straight sides split into
    nx (along X) / ny (along Y) segments, so rings of any size share one vertex count
    (soft goods need vertices along the sides for their irregularity)."""
    ex, ey = hx - rad, hy - rad
    corners = ((ex, -ey, -90.0), (ex, ey, 0.0), (-ex, ey, 90.0), (-ex, -ey, 180.0))
    pts = []
    for ci, (cx, cy, a0) in enumerate(corners):
        for i in range(k + 1):
            a = math.radians(a0 + 90.0 * i / k)
            pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
        nc = corners[(ci + 1) % 4]
        a = math.radians(nc[2])
        p0, p1 = pts[-1], (nc[0] + rad * math.cos(a), nc[1] + rad * math.sin(a))
        n = ny if ci in (0, 2) else nx
        for j in range(1, n):
            t = j / float(n)
            pts.append((p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t))
    return pts


# ===================================================================== primitives
def _strip(md, ra, rb, sg=1):
    n = len(ra)
    for j in range(n):
        j2 = (j + 1) % n
        md.quad(ra[j], ra[j2], rb[j2], rb[j], sg)


def _fan_start(md, c, ring, sg=2):
    n = len(ring)
    for j in range(n):
        md.tri(c, ring[(j + 1) % n], ring[j], sg)


def _fan_end(md, c, ring, sg=2):
    n = len(ring)
    for j in range(n):
        md.tri(ring[j], ring[(j + 1) % n], c, sg)


def lathe(profile, segs=48, x=0.0, y=0.0, z=0.0, sg=1):
    """Revolve an (r, z) profile about Z. r = 0 points become single-vertex poles."""
    md = MD()
    rings = []
    for r, zz in profile:
        if r < 1e-4:
            rings.append([md.vert((x, y, z + zz))])
        else:
            rings.append([md.vert((x + r * math.cos(2.0 * math.pi * j / segs),
                                   y + r * math.sin(2.0 * math.pi * j / segs), z + zz))
                          for j in range(segs)])
    for i in range(len(rings) - 1):
        a, b = rings[i], rings[i + 1]
        if len(a) == 1 and len(b) == 1:
            continue
        if len(a) == 1:
            for j in range(segs):
                md.tri(a[0], b[(j + 1) % segs], b[j], sg)
        elif len(b) == 1:
            for j in range(segs):
                md.tri(a[j], a[(j + 1) % segs], b[0], sg)
        else:
            _strip(md, a, b, sg)
    return md


def slab(cx, cy, prof, k=3, rho=0.3, cap0=True, cap1=True):
    """Ring-profile solid: each (o, z) profile point is a rounded rectangle of half size
    (cx + o, cy + o) and corner radius max(o, rho); flat fan caps close the ends."""
    omin = min(o for o, _ in prof)
    lx = 2.0 * (cx + omin - max(omin, rho))
    ly = 2.0 * (cy + omin - max(omin, rho))
    sx, sy = lx > 4.0 * S, ly > 4.0 * S
    sup = (sy, sx, sy, sx)
    md = MD()
    rings = []
    for o, z in prof:
        rad = max(o, rho)
        rings.append([md.vert((px, py, z)) for px, py in _rr_pts(cx + o, cy + o, rad, k, S, sup)])
    for i in range(len(rings) - 1):
        _strip(md, rings[i], rings[i + 1])
    if cap0:
        _fan_start(md, md.vert((0.0, 0.0, prof[0][1])), rings[0])
    if cap1:
        _fan_end(md, md.vert((0.0, 0.0, prof[-1][1])), rings[-1])
    return md


def rbox(w, d, h, r, k=2, rc=None, x=0.0, y=0.0, z=0.0, kc=None):
    """Rounded box w (X) x d (Y) x h (Z): edge radius r, plan corner radius rc, base at z."""
    rc = r if rc is None else rc
    rc = max(rc, r + 2.5 * S)
    cx, cy = w / 2.0 - rc, d / 2.0 - rc
    inner = -0.5 * min(cx, cy)
    prof = [(inner, 0.0), (rc - r - S, 0.0)]
    prof += [(rc - r + r * math.cos(math.radians(-90.0 + 90.0 * i / k)),
              r + r * math.sin(math.radians(-90.0 + 90.0 * i / k))) for i in range(k + 1)]
    if h - 2.0 * r > 4.0 * S:
        prof += [(rc, r + S), (rc, h - r - S)]
    prof += [(rc - r + r * math.cos(math.radians(90.0 * i / k)),
              h - r + r * math.sin(math.radians(90.0 * i / k))) for i in range(k + 1)]
    prof += [(rc - r - S, h), (inner, h)]
    rho = min(max(0.01, 0.5 * (rc - r)), 0.25 * min(cx, cy))
    md = slab(cx, cy, prof, k=kc or k, rho=rho)
    return md.move(x, y, z)


def sweep_loop(path, scale=1.0, sides=8, up=(0.0, 0.0, 1.0)):
    """Tube along a closed planar loop (piping / welts): wrapped tangents, no seam."""
    path = [tuple(float(c) for c in p) for p in path]
    n = len(path)
    prof = [(math.cos(2.0 * math.pi * j / sides), math.sin(2.0 * math.pi * j / sides)) for j in range(sides)]
    md = MD()
    rings = []
    for i in range(n):
        t = _unit(_add(_unit(_sub(path[i], path[i - 1])), _unit(_sub(path[(i + 1) % n], path[i]))))
        nv = _unit(_sub(up, _mul(t, _dot(up, t))))
        bv = _cross(t, nv)
        rings.append([md.vert(_add(path[i], _add(_mul(nv, u * scale), _mul(bv, v * scale)))) for u, v in prof])
    for i in range(n):
        _strip(md, rings[i], rings[(i + 1) % n])
    return md


def sweep(path, scale=1.0, profile=None, sides=16, up=(0.0, 0.0, 1.0), fil0=0.0, fil1=0.0,
          cap0=True, cap1=True, sg=1, nfil=4, support=True, support_min=2.0):
    """Sweep a closed 2D profile (default unit circle, scaled per path point) along a path.
    fil0/fil1 round the ends with a fillet of that size; caps are flat fans.  Support
    rings go next to both ends of straight segments longer than support_min."""
    path = [tuple(float(c) for c in p) for p in path]
    n = len(path)
    sc = [float(s) for s in scale] if isinstance(scale, (list, tuple)) else [float(scale)] * n
    prof = profile or [(math.cos(2.0 * math.pi * j / sides), math.sin(2.0 * math.pi * j / sides))
                       for j in range(sides)]
    reff = min(math.hypot(u, v) for u, v in prof)
    if fil0 > 0:
        path, sc = _trim_start(path, sc, fil0)
    if fil1 > 0:
        rp, rs = _trim_start(path[::-1], sc[::-1], fil1)
        path, sc = rp[::-1], rs[::-1]
    n = len(path)
    if support:
        p2, s2 = [path[0]], [sc[0]]
        for i in range(1, n):
            a, b = path[i - 1], path[i]
            L = _len(_sub(b, a))
            if L > 4.0 * S and (L > support_min or (fil0 > 0 and i == 1) or (fil1 > 0 and i == n - 1)):
                dv = _mul(_sub(b, a), 1.0 / L)
                p2.append(_add(a, _mul(dv, S)))
                s2.append(sc[i - 1] + (sc[i] - sc[i - 1]) * S / L)
                p2.append(_sub(b, _mul(dv, S)))
                s2.append(sc[i] - (sc[i] - sc[i - 1]) * S / L)
            p2.append(b)
            s2.append(sc[i])
        path, sc, n = p2, s2, len(p2)
    T = []
    for i in range(n):
        if i == 0:
            t = _sub(path[1], path[0])
        elif i == n - 1:
            t = _sub(path[-1], path[-2])
        else:
            t = _add(_unit(_sub(path[i], path[i - 1])), _unit(_sub(path[i + 1], path[i])))
        T.append(_unit(t))
    u0 = tuple(up)
    if abs(_dot(_unit(u0), T[0])) > 0.98:
        u0 = (1.0, 0.0, 0.0) if abs(T[0][0]) < 0.9 else (0.0, 1.0, 0.0)
    nn = _unit(_sub(u0, _mul(T[0], _dot(u0, T[0]))))
    N, B = [], []
    for i in range(n):
        if i:
            nn = _unit(_sub(nn, _mul(T[i], _dot(nn, T[i]))))
        N.append(nn)
        B.append(_cross(T[i], nn))
    md = MD()

    def ring(p, nv, bv, s):
        return [md.vert(_add(p, _add(_mul(nv, u * s), _mul(bv, v * s)))) for u, v in prof]

    rings = []
    c0, c1 = path[0], path[-1]
    if fil0 > 0:
        c0 = _sub(path[0], _mul(T[0], fil0))
        for kk in range(nfil, 0, -1):
            th = 0.5 * math.pi * kk / nfil
            p = _sub(path[0], _mul(T[0], fil0 * math.sin(th)))
            rings.append(ring(p, N[0], B[0], sc[0] - fil0 * (1.0 - math.cos(th)) / reff))
    for i in range(n):
        rings.append(ring(path[i], N[i], B[i], sc[i]))
    if fil1 > 0:
        c1 = _add(path[-1], _mul(T[-1], fil1))
        for kk in range(1, nfil + 1):
            th = 0.5 * math.pi * kk / nfil
            p = _add(path[-1], _mul(T[-1], fil1 * math.sin(th)))
            rings.append(ring(p, N[-1], B[-1], sc[-1] - fil1 * (1.0 - math.cos(th)) / reff))
    for i in range(len(rings) - 1):
        _strip(md, rings[i], rings[i + 1], sg)
    if cap0:
        _fan_start(md, md.vert(c0), rings[0])
    if cap1:
        _fan_end(md, md.vert(c1), rings[-1])
    return md


def _trim_start(path, sc, d):
    """Cut arc length d off the start of a polyline (interpolating the per-point scale)."""
    acc = 0.0
    for i in range(1, len(path)):
        L = _len(_sub(path[i], path[i - 1]))
        if acc + L >= d and L > 1e-9:
            t = (d - acc) / L
            p = tuple(a + (b - a) * t for a, b in zip(path[i - 1], path[i]))
            s = sc[i - 1] + (sc[i] - sc[i - 1]) * t
            rest_p, rest_s = path[i:], sc[i:]
            if len(rest_p) > 1 and _len(_sub(rest_p[0], p)) < 0.05:
                rest_p, rest_s = rest_p[1:], rest_s[1:]
            return [p] + list(rest_p), [s] + list(rest_s)
        acc += L
    return list(path[-2:]), list(sc[-2:])


def _vessel(outer, t, base_t, floor_r=0.5, n_rim=6):
    """Closed lathe profile of a thick-walled vessel from its outer (r, z) curve.
    outer runs from the bottom centre (r = 0) out and up to the rim; the inner wall is
    the outer offset inward by t, the inner floor sits at z = base_t."""
    outer = [tuple(p) for p in outer]

    def tangent(i):
        a = outer[max(i - 1, 0)]
        b = outer[min(i + 1, len(outer) - 1)]
        return _unit(_sub(b, a))

    inner = []
    for i, p in enumerate(outer):
        if p[1] < base_t + floor_r + 0.3 or p[0] < t:
            continue
        tg = tangent(i)
        inner.append((p[0] - t * tg[1], p[1] + t * tg[0]))
    top_o = outer[-1]
    top_i = inner[-1]
    c = _mul(_add(top_o, top_i), 0.5)
    e = _sub(top_o, c)
    te = tangent(len(outer) - 1)
    rim = []
    for k in range(1, n_rim):
        ph = math.pi * k / n_rim
        rim.append(_add(c, _add(_mul(e, math.cos(ph)), _mul(te, 0.5 * t * math.sin(ph)))))
    low = inner[0]
    floor = _fillet_poly([inner[1] if len(inner) > 1 else low, low, (low[0], base_t), (0.0, base_t)],
                         [0.0, 0.0, floor_r, 0.0])
    prof = outer + rim + list(reversed(inner))[:-1] + floor[1:]
    return _supported(prof, min_len=1.5)


def _bowl_outer(R, H, foot_r, foot_h, foot_w=0.5, recess=0.35, amax=72.0, n=16, seg_deg=20.0):
    """Outer curve of a glazed bowl: recessed base, foot ring, curved wall to the rim."""
    pts = [(0.0, recess), (foot_r - foot_w, recess), (foot_r - foot_w, 0.0), (foot_r, 0.0), (foot_r, foot_h)]
    am = math.radians(amax)
    for i in range(1, n + 1):
        a = am * i / n
        pts.append((foot_r + (R - foot_r) * math.sin(a) / math.sin(am),
                    foot_h + (H - foot_h) * (1.0 - math.cos(a)) / (1.0 - math.cos(am))))
    radii = [0.0, 0.12, 0.1, 0.1, 0.3] + [0.0] * n
    return _fillet_poly(pts, radii, seg_deg=seg_deg)


def _units(L, sink_at, cook_at, end_t):
    """Split the run into base units: [(kind, u0, u1)] with u measured from the left end."""
    a0, a1 = end_t, L - end_t

    def span(c, w):
        u0 = max(a0, min(c - w / 2.0, a1 - w))
        return u0, u0 + w

    sink = ("sink",) + span(sink_at, 80.0)
    cook = ("cook",) + span(cook_at, 60.0)
    if sink[2] > cook[1] and sink[1] < cook[2]:
        sink = ("sink",) + span(sink_at, 60.0)
    fixed = sorted([sink, cook], key=lambda t: t[1])

    def fill(a, b, dw=None):
        out, tail = [], None
        if dw == "start" and b - a >= 60.0:
            out.append(("dishwasher", a, a + 60.0))
            a += 60.0
        elif dw == "end" and b - a >= 60.0:
            tail = ("dishwasher", b - 60.0, b)
            b -= 60.0
        w = b - a
        if w >= 0.5:
            if w < 12.0:
                out.append(("filler", a, b))
            elif w < 30.0:
                out.append(("pullout", a, b))
            elif w <= 65.0:
                out.append(("door", a, b))
            else:
                n = int(math.ceil(w / 60.0))
                out += [("door", a + w * i / n, a + w * (i + 1) / n) for i in range(n)]
        if tail:
            out.append(tail)
        return out

    spans = [(a0, fixed[0][1]), (fixed[0][2], fixed[1][1]), (fixed[1][2], a1)]
    dws = [None, None, None]
    si = 0 if fixed[0][0] == "sink" else 1
    if spans[si + 1][1] - spans[si + 1][0] >= 60.0:
        dws[si + 1] = "start"
    elif spans[si][1] - spans[si][0] >= 60.0:
        dws[si] = "end"
    units = []
    for i in range(3):
        units += fill(spans[i][0], spans[i][1], dws[i])
        if i < 2:
            units.append(fixed[i])
    return units


# ===================================================================== kitchen parts
FRONT_RECESS = 0.6                    # depth of the shaker panel behind the frame face


def _shaker_stile(W, H, frame=4.5):
    """Stile width of a slim-shaker front W x H, or None for a slab (shallow drawer, or too
    narrow to keep a 5 cm panel between stiles of at least 3 cm)."""
    stile = min(frame, (W - 5.0) / 2.0)
    return None if H < 20.0 or stile < 3.0 else stile


def _front(x0, x1, z0, z1, y_face, t=1.9, frame=4.5, recess=FRONT_RECESS, r=0.15):
    """Slim-shaker painted front (stiles, rails, recessed panel); shallow ones are slabs and
    narrow ones keep the style with slimmer stiles."""
    W, H = x1 - x0, z1 - z0
    xc, yc = (x0 + x1) / 2.0, y_face + t / 2.0
    stile = _shaker_stile(W, H, frame)
    if stile is None:
        return rbox(W, t, H, r, x=xc, y=yc, z=z0)
    md = MD()
    md.merge(rbox(stile, t, H, r, x=x0 + stile / 2.0, y=yc, z=z0))
    md.merge(rbox(stile, t, H, r, x=x1 - stile / 2.0, y=yc, z=z0))
    md.merge(rbox(W - 2.0 * stile, t, frame, r, x=xc, y=yc, z=z0))
    md.merge(rbox(W - 2.0 * stile, t, frame, r, x=xc, y=yc, z=z1 - frame))
    pt = t - recess
    md.merge(rbox(W - 2.0 * stile, pt, H - 2.0 * frame, r, k=1, x=xc, y=y_face + recess + pt / 2.0, z=z0 + frame))
    return md


def _bar_handle(cx, cz, length, vertical, y_face, r=0.6, post_r=0.42, standoff=2.4, y_mount=None):
    """Slim round bar pull on two posts, projecting from a front whose face is at y_face (-Y).
    y_mount: face the posts screw into when that is not y_face (a recessed shaker panel);
    the posts run 3 mm into it so they never stop short in mid-air."""
    md = MD()
    y_post = (y_face if y_mount is None else y_mount) + 0.3
    half = length / 2.0
    post = half - 2.0 if length > 10.0 else half * 0.6
    yb = y_face - standoff - r + 0.2
    if vertical:
        path = [(cx, yb, cz - half), (cx, yb, cz + half)]
        posts = [(cx, cz - post), (cx, cz + post)]
    else:
        path = [(cx - half, yb, cz), (cx + half, yb, cz)]
        posts = [(cx - post, cz), (cx + post, cz)]
    md.merge(sweep(path, r, sides=18, fil0=0.22, fil1=0.22))
    for px, pz in posts:
        md.merge(sweep([(px, y_post, pz), (px, yb, pz)], post_r, sides=14, cap0=False, cap1=False))
    return md


def _worktop(L, y0, y1, z0, t, holes, ease=0.2, name="KR_Worktop"):
    """Marble slab: SplineShape outline + rounded-rect cut-outs, Bevel for the eased edges."""
    X0 = -L / 2.0
    outline = [(x + X0 + L / 2.0, y + (y0 + y1) / 2.0) for x, y in
               _rr_pts(L / 2.0, (y1 - y0) / 2.0, 0.3, 4, sup=(False,) * 4)]
    splines = [outline]
    for hx, hy, w, d, rad in holes:
        pts = [(hx + px, hy + py) for px, py in _rr_pts(w / 2.0, d / 2.0, rad, 6, sup=(False,) * 4)]
        splines.append(list(reversed(pts)))
    ms = ['mfk_s = SplineShape name:"%s"' % name]
    for i, pts in enumerate(splines):
        ms.append("addNewSpline mfk_s")
        ms.append("for p in #(%s) do addKnot mfk_s %d #corner #line p"
                  % (",".join("[%.4f,%.4f,0]" % p for p in pts), i + 1))
        ms.append("close mfk_s %d" % (i + 1))
    ms += ["updateShape mfk_s", "mfk_b = Bevel()",
           "mfk_b.Starting_Outline = %f" % -ease,
           "mfk_b.Level_1_Height = %f" % ease, "mfk_b.Level_1_Outline = %f" % ease,
           "mfk_b.Use_Level_2 = true", "mfk_b.Level_2_Height = %f" % (t - 2.0 * ease),
           "mfk_b.Level_2_Outline = 0.0",
           "mfk_b.Use_Level_3 = true", "mfk_b.Level_3_Height = %f" % ease,
           "mfk_b.Level_3_Outline = %f" % -ease,
           "mfk_b.Smooth_Levels = false",
           "addModifier mfk_s mfk_b", "convertToMesh mfk_s",
           "mfk_s.pos = [0,0,%f]" % z0, "mfk_s"]
    node = rt.execute("(\n" + "\n".join(ms) + "\n)")
    # 200 cm, the same scale as the window sills cut from this marble: 140 showed
    # the same veins twice on a 290 run, and the run length made the veins 2.4x
    # the sill's; at 200 the hob covers most of the partial second repeat
    kit.part(node, "stone_worktop", 200.0)
    return node


def _sink_bowl(xc, yc, z_rim, W=50.0, D=40.0, H=20.0, R=1.5):
    """Undermount satin bowl: flange glued under the worktop, rounded rim, R15 corners."""
    cx, cy = W / 2.0 - R, D / 2.0 - R
    top = z_rim - 0.02
    pts = [(R + 2.5, top), (R, top), (R, top - H), (-cy + 2.0, top - H)]
    prof = _supported(_fillet_poly(pts, [0.0, 0.3, 1.5, 0.0], seg_deg=15.0))
    md = slab(cx, cy, prof, k=6, rho=0.3, cap0=False, cap1=True).move(xc, yc, 0.0)
    node = emit(md, "KR_SinkBowl", "metal_steel", 25)
    sh = rt.Shell()
    kit.setp(sh, "innerAmount", 0.1)
    kit.setp(sh, "outerAmount", 0.0)
    rt.addModifier(node, sh)
    strainer = _supported(_fillet_poly(
        [(0.0, 0.0), (5.7, 0.0), (5.7, 0.16), (4.6, 0.3), (4.3, 0.3), (4.1, 0.2), (1.2, 0.2),
         (1.1, 0.9), (0.0, 1.0)], [0, 0.05, 0.1, 0.4, 0.06, 0.06, 0.08, 0.35, 0], seg_deg=30.0))
    sn = emit(lathe(strainer, 32, xc, yc, top - H), "KR_SinkStrainer", "metal_chrome", 20)
    return [node, sn]


def _tap(xt, yt, z0):
    """Chrome single-lever gooseneck mixer standing on the worktop at (xt, yt, z0)."""
    md = MD()
    body = _supported(_fillet_poly([(0.0, 0.0), (2.9, 0.0), (2.9, 0.7), (2.2, 0.7), (2.2, 15.8), (0.0, 15.8)],
                                   [0, 0.12, 0.3, 0.15, 0.6, 0], seg_deg=12.0))
    md.merge(lathe(body, 32))
    R, top = 10.5, 25.0
    path = [(0.0, 0.0, 15.0), (0.0, 0.0, top)]
    for i in range(1, 33):
        a = math.pi * i / 32.0
        path.append((0.0, -R + R * math.cos(a), top + R * math.sin(a)))
    path.append((0.0, -2.0 * R, 21.6))
    md.merge(sweep(path, 1.1, sides=20, up=(1.0, 0.0, 0.0), cap0=False, cap1=False))
    aer = _supported(_fillet_poly([(0.95, 19.62), (1.06, 19.45), (1.25, 19.45), (1.25, 21.9), (0.0, 21.9)],
                                  [0, 0.0, 0.12, 0.05, 0]))
    md.merge(lathe(aer, 32, 0.0, -2.0 * R, 0.0))
    md.merge(sweep([(1.6, 0.0, 11.0), (3.7, 0.0, 11.0)], 1.05, sides=24, fil1=0.35, cap0=False))
    md.merge(sweep([(3.05, 0.0, 11.3), (3.15, 0.0, 15.0), (3.45, 0.0, 19.4)], [0.56, 0.5, 0.42],
                   sides=16, fil1=0.4, cap0=False))
    md.move(xt, yt, z0)
    n1 = emit(md, "KR_Tap", "metal_chrome", 20)
    ins = lathe([(0.0, 19.6), (0.98, 19.6), (0.98, 19.66), (0.0, 19.66)], 24, xt, yt - 2.0 * R, z0)
    n2 = emit(ins, "KR_TapAerator", "plastic_black", 10)
    return [n1, n2]


def _hob(xc, yc, z_top):
    nodes = []
    nodes.append(emit(rbox(60.0, 52.0, 0.6, 0.12, k=2, rc=0.4, x=xc, y=yc, z=z_top - 0.6),
                      "KR_HobGlass", "stone_dark", 60))
    nodes.append(emit(rbox(60.25, 52.25, 1.15, 0.1, x=xc, y=yc, z=z_top - 1.75), "KR_HobGasket", "rubber", 20))
    nodes.append(emit(rbox(56.0, 49.0, 5.0, 0.3, x=xc, y=yc, z=z_top - 6.75), "KR_HobHousing", "plastic_black", 30))
    rings = MD()
    for dx, dy, rr in ((-14.5, 11.5, 10.5), (-14.5, -10.5, 9.0), (15.5, 12.0, 8.0), (15.5, -10.0, 9.0)):
        prof = [(rr - 0.22, 0.0), (rr, 0.0), (rr, 0.02), (rr - 0.22, 0.02), (rr - 0.22, 0.0)]
        rings.merge(lathe(prof, 48, xc + dx, yc + dy, z_top))
    for i in range(4):                                   # touch-control markers
        rings.merge(lathe([(0.32, 0.0), (0.45, 0.0), (0.45, 0.02), (0.32, 0.02), (0.32, 0.0)],
                          20, xc - 6.0 + 4.0 * i, yc - 22.6, z_top))
    rings.merge(sweep([(xc - 5.5, yc - 20.9, z_top + 0.012), (xc + 5.5, yc - 20.9, z_top + 0.012)], 1.0,
                      profile=_rrect2d(0.024, 0.16, 0.01, k=1), support=False))
    nodes.append(emit(rings, "KR_HobMarkings", "metal_steel", 20))
    return nodes


def _shelf(x0, x1, z_bottom, y_wall, tile_face):
    """Oak open shelf on brushed-brass flat-bar brackets with a few bowls and jars."""
    nodes = []
    Lsh = x1 - x0
    depth, t = 24.0, 3.0
    board = rbox(Lsh, depth, t, 0.3, k=3, x=(x0 + x1) / 2.0, y=y_wall - depth / 2.0, z=z_bottom)
    nodes.append(emit(board, "KR_Shelf", "wood_light", 110, axes=GRAIN["x"]))
    br = MD()
    yb = tile_face - 0.2
    for bx in ((x0 + 10.0, x1 - 10.0) if Lsh >= 45.0 else ((x0 + x1) / 2.0,)):
        path = _fillet_poly([(bx, yb, z_bottom - 12.0), (bx, yb, z_bottom - 0.2), (bx, yb - 20.0, z_bottom - 0.2)],
                            [0, 0.6, 0], seg_deg=10.0)
        br.merge(sweep(path, 1.0, profile=_rrect2d(2.0, 0.4, 0.12), up=(1.0, 0.0, 0.0), fil0=0.12, fil1=0.12))
        for zz in (z_bottom - 9.5, z_bottom - 4.0):
            scr = lathe([(0.0, 0.0), (0.42, 0.0), (0.4, 0.06), (0.28, 0.15), (0.0, 0.18)], 20)
            scr.rot(90.0, (1.0, 0.0, 0.0)).move(bx, yb - 0.2, zz)
            br.merge(scr)
    nodes.append(emit(br, "KR_ShelfBrackets", "metal_brass", 20))
    # ---- items on the shelf, left to right
    ztop = z_bottom + t
    yc = y_wall - depth / 2.0 + 0.5
    cur = x0 + 3.0
    ceramic, glass, lids = MD(), MD(), MD()
    bowl = _vessel(_bowl_outer(8.0, 6.2, 3.1, 0.7, n=9, seg_deg=30.0), 0.42, 1.05)
    if cur + 16.0 <= x1 - 2.0:
        zoff = ztop
        # nested bowls, each resting a few mm off-centre in the one below (a hand-made stack)
        for s, ox, oy in ((1.0, 0.0, 0.0), (0.84, 0.35, -0.2), (0.69, 0.1, 0.3)):
            m = lathe(bowl, 24)
            m.scale(s, s, s)
            ceramic.merge(m.move(cur + 8.0 + ox, yc + oy, zoff))
            zoff += 1.05 * s
        cur += 16.0 + 1.8
    for jr, jh in ((5.0, 16.0), (4.4, 10.5)):
        if cur + 2 * jr > x1 - 2.0:
            break
        jx = cur + jr
        jar = _supported(_fillet_poly([(0.0, 0.0), (jr, 0.0), (jr, jh), (jr - 0.32, jh), (jr - 0.32, 0.7), (0.0, 0.7)],
                                      [0, 0.45, 0.15, 0.15, 0.5, 0], seg_deg=30.0), min_len=0.6)
        glass.merge(lathe(jar, 36, jx, yc, ztop))
        ri = jr - 0.32 - 0.06
        lid = _supported(_fillet_poly([(0.0, jh - 1.3), (ri, jh - 1.3), (ri, jh), (jr + 0.15, jh),
                                       (jr + 0.15, jh + 1.9), (0.0, jh + 1.9)], [0, 0.1, 0.05, 0.1, 0.35, 0],
                                      seg_deg=30.0), min_len=0.6)
        lids.merge(lathe(lid, 32, jx, yc, ztop))
        cur += 2 * jr + 1.8
    if ceramic.f:
        nodes.append(emit(ceramic, "KR_ShelfBowls", "ceramic_white", 30))
    if glass.f:
        nodes.append(emit(glass, "KR_ShelfJars", "glass", 50))
        nodes.append(emit(lids, "KR_ShelfJarLids", "wood_light", 110))
    return nodes


def build_kitchen_run(length=260, sink_at=65, cook_at=225, shelf="auto"):
    """Straight run of 60-deep base units on a 10 cm recessed plinth, sage slim-shaker
    fronts with 3 mm gaps, brass bar pulls, 2 cm Calacatta worktop (top z = 91) with an
    undermount satin bowl + chrome gooseneck at sink_at and a flush black glass hob at
    cook_at (both centre, cm from the left end), and an oak shelf 40 cm above the worktop.
    shelf: "auto" (left of the tap), None, or (u0, u1) cm from the left end."""
    L = float(length)
    X0 = -L / 2.0
    Z_PL, Z_WT, WT_T = 10.0, 89.0, 2.0
    Z_TOP = Z_WT + WT_T
    Y_BACK, Y_FACE, T_FR, END_T = 31.0, -29.0, 1.9, 1.9
    FZ0, FZ1 = Z_PL + 0.3, Z_WT - 0.3
    nodes = []
    # ---- carcass shell: end panels, plinth, bottom, back (hidden box behind the fronts)
    shell = MD()
    for sgn in (-1.0, 1.0):
        shell.merge(rbox(END_T, Y_BACK - Y_FACE, Z_WT, 0.2, x=sgn * (L / 2.0 - END_T / 2.0),
                         y=(Y_BACK + Y_FACE) / 2.0, z=0.0))
    iw = L - 2.0 * END_T
    shell.merge(rbox(iw - 0.02, 1.6, Z_PL - 0.5, 0.15, x=0.0, y=-22.2, z=0.5))
    shell.merge(rbox(iw - 0.02, 30.4 - (Y_FACE + T_FR), 1.8, 0.1, x=0.0, y=(30.4 + Y_FACE + T_FR) / 2.0, z=Z_PL))
    shell.merge(rbox(iw - 0.02, 0.6, Z_WT - Z_PL - 0.02, 0.1, x=0.0, y=30.7, z=Z_PL))
    nodes.append(emit(shell, "KR_Carcass", "paint_sage", 100))
    nodes.append(emit(rbox(iw - 0.1, 0.7, 0.5, 0.2, x=0.0, y=-22.7, z=0.0), "KR_PlinthSeal", "rubber", 20))
    # ---- fronts + handles
    a0, a1 = END_T, L - END_T
    fronts, pulls = MD(), MD()

    def fx(u0, u1):
        g0 = 0.3 if abs(u0 - a0) < 1e-6 else 0.15
        g1 = 0.3 if abs(u1 - a1) < 1e-6 else 0.15
        return X0 + u0 + g0, X0 + u1 - g1

    def hlen(w):
        return max(12.8, min(32.0, round(0.54 * w / 3.2) * 3.2))

    def on_panel(w, h):
        """Mounting face for a pull centred on a front: its recessed panel when it is a shaker."""
        return None if _shaker_stile(w, h) is None else Y_FACE + FRONT_RECESS

    for kind, u0, u1 in _units(L, sink_at, cook_at, END_T):
        x0, x1 = fx(u0, u1)
        if kind == "sink":
            xm = X0 + (u0 + u1) / 2.0
            for dx0, dx1, hx in ((x0, xm - 0.15, xm - 0.15 - 2.25), (xm + 0.15, x1, xm + 0.15 + 2.25)):
                fronts.merge(_front(dx0, dx1, FZ0, FZ1, Y_FACE))
                pulls.merge(_bar_handle(hx, FZ1 - 4.0 - 10.0, 20.0, True, Y_FACE))
        elif kind == "cook":
            zs = [(FZ1 - 17.8, FZ1), (FZ0 + 30.3, FZ1 - 18.1), (FZ0, FZ0 + 30.0)]
            for z0, z1 in zs:
                fronts.merge(_front(x0, x1, z0, z1, Y_FACE))
                pulls.merge(_bar_handle((x0 + x1) / 2.0, (z0 + z1) / 2.0, hlen(x1 - x0), False, Y_FACE,
                                        y_mount=on_panel(x1 - x0, z1 - z0)))
        elif kind == "door":
            fronts.merge(_front(x0, x1, FZ0, FZ1, Y_FACE))
            right_half = (u0 + u1) / 2.0 > L / 2.0
            hx = x0 + 2.25 if right_half else x1 - 2.25
            pulls.merge(_bar_handle(hx, FZ1 - 4.0 - 10.0, 20.0, True, Y_FACE))
        elif kind in ("dishwasher", "pullout"):
            fronts.merge(_front(x0, x1, FZ0, FZ1, Y_FACE))
            if x1 - x0 < 20.0:              # narrow pull-out: a horizontal bar would overhang it
                pulls.merge(_bar_handle((x0 + x1) / 2.0, FZ1 - 4.0 - 10.0, 20.0, True, Y_FACE,
                                        y_mount=on_panel(x1 - x0, FZ1 - FZ0)))
            else:
                pulls.merge(_bar_handle((x0 + x1) / 2.0, FZ1 - 2.25, min(hlen(x1 - x0), x1 - x0 - 6.0),
                                        False, Y_FACE))
        else:                                                  # filler
            fronts.merge(rbox(x1 - x0, T_FR, FZ1 - FZ0, 0.15, x=(x0 + x1) / 2.0, y=Y_FACE + T_FR / 2.0, z=FZ0))
    nodes.append(emit(fronts, "KR_Fronts", "paint_sage", 100))
    nodes.append(emit(pulls, "KR_Handles", "metal_brass", 20))
    # ---- worktop with sink + hob cut-outs
    xs, ys = X0 + sink_at, -4.0
    xh, yh = X0 + cook_at, 0.0
    nodes.append(_worktop(L, -31.0, Y_BACK, Z_WT, WT_T,
                          [(xs, ys, 50.4, 40.4, 1.7), (xh, yh, 60.4, 52.4, 0.6)]))
    nodes += _sink_bowl(xs, ys, Z_WT)
    nodes += _tap(xs, 22.5, Z_TOP)
    nodes += _hob(xh, yh, Z_TOP)
    # ---- open shelf 40 cm above the worktop (kept clear of the tap and the hob)
    if shelf == "auto":
        if sink_at - 12.0 - 3.0 >= 40.0:
            shelf = (3.0, min(sink_at - 12.0, 123.0))
        elif cook_at - 40.0 - (sink_at + 14.0) >= 40.0:
            m = (sink_at + 14.0 + cook_at - 40.0) / 2.0
            half = min(60.0, (cook_at - 40.0 - sink_at - 14.0) / 2.0)
            shelf = (m - half, m + half)
        else:
            shelf = None
    if shelf:
        nodes += _shelf(X0 + shelf[0], X0 + shelf[1], Z_TOP + 40.0, Y_BACK, Y_BACK - 0.6)
    return kit.group("KitchenRun", nodes)


# ===================================================================== fridge
def build_fridge():
    """Freestanding fridge-freezer 70 x 70 x 200: brushed steel doors (fridge over freezer,
    1 cm gap), long steel bar handles, black rubber gaskets, louvred plinth grille."""
    nodes = []
    r_bar, standoff = 1.0, 2.0
    y_door_f = -35.0 + 2.0 * r_bar + standoff - 0.25        # -31.25
    t_door = 6.5
    y_door_b = y_door_f + t_door                             # -24.75
    y_cab_f = y_door_b + 0.8                                 # -23.95 (0.8 gasket)
    y_back = 35.0
    top = 199.0
    cab = rbox(70.0, y_back - y_cab_f, top - 1.6, 0.8, k=3, rc=1.2, y=(y_back + y_cab_f) / 2.0, z=1.6)
    nodes.append(emit(cab, "FR_Cabinet", "metal_steel", 25, axes=BRUSH_VERTICAL))
    dw = 69.6
    doors = MD()
    seals = MD()
    spans = ((80.5, top), (9.2, 79.5))
    for z0, z1 in spans:
        doors.merge(rbox(dw, t_door, z1 - z0, 1.1, k=4, rc=1.3, y=(y_door_f + y_door_b) / 2.0, z=z0))
        seals.merge(rbox(dw - 2.0, 0.9, z1 - z0 - 2.0, 0.3, k=2, rc=0.8, y=y_door_b + 0.4, z=z0 + 1.0))
    nodes.append(emit(doors, "FR_Doors", "metal_steel", 25, axes=BRUSH_VERTICAL))
    nodes.append(emit(seals, "FR_Gaskets", "rubber", 20))
    handles = MD()
    hx = -dw / 2.0 + 5.2
    yb = y_door_f - standoff - r_bar + 0.25
    for z0, z1 in ((86.5, 156.5), (37.0, 73.5)):
        handles.merge(sweep([(hx, yb, z0), (hx, yb, z1)], r_bar, sides=24, fil0=0.45, fil1=0.45))
        for zz in (z0 + 4.0, z1 - 4.0):
            handles.merge(sweep([(hx, y_door_f + 0.3, zz), (hx, yb, zz)], 0.75, sides=18, cap0=False, cap1=False))
            rose = lathe(_fillet_poly([(0.0, -0.1), (1.15, -0.1), (1.15, 0.25), (0.0, 0.35)], [0, 0.05, 0.18, 0]), 24)
            handles.merge(rose.rot(90.0, (1.0, 0.0, 0.0)).move(hx, y_door_f, zz))
    nodes.append(emit(handles, "FR_Handles", "metal_steel", 25, axes=BRUSH_VERTICAL))
    # plinth: black kick box, louvred grille, feet; hinge covers
    blk = MD()
    blk.merge(rbox(66.0, y_cab_f + 0.05 - (-29.8), 7.3, 0.3, y=(y_cab_f + 0.05 - 29.8) / 2.0, z=1.6))
    for i in range(6):
        blk.merge(rbox(62.0, 0.8, 0.55, 0.15, y=-30.15, z=2.45 + 1.05 * i))
    for xx in (-31.6, 31.6):
        blk.merge(rbox(1.2, 0.8, 7.0, 0.2, x=xx, y=-30.15, z=1.75))
    blk.merge(rbox(7.0, 8.0, 1.0, 0.3, x=31.3, y=-27.0, z=top))
    blk.merge(rbox(6.0, 6.0, 0.94, 0.2, x=31.6, y=-28.0, z=79.53))
    nodes.append(emit(blk, "FR_PlinthGrille", "plastic_black", 30))
    feet = MD()
    for fx_, fy_ in ((-30.0, -20.5), (30.0, -20.5), (-30.0, 31.0), (30.0, 31.0)):
        feet.merge(lathe(_fillet_poly([(0.0, 0.0), (1.7, 0.0), (1.5, 1.6), (0.0, 1.6)], [0, 0.2, 0.1, 0]), 20,
                         fx_, fy_, 0.0))
    nodes.append(emit(feet, "FR_Feet", "rubber", 20))
    return kit.group("Fridge", nodes)


# ===================================================================== dining table
def build_dining_table():
    """Solid oak table 150 x 90 x 75: 3 cm top (soft corners, bevelled underside, eased
    top edge), four round tapered legs joined by slim aprons."""
    nodes = []
    W, D, H, T = 150.0, 90.0, 75.0, 3.0
    rc = 2.0
    z0 = H - T
    pts = [(-20.0, z0), (rc - 1.6, z0), (rc, z0 + 1.1), (rc, H), (-20.0, H)]
    prof = _supported(_fillet_poly(pts, [0.0, 0.8, 0.35, 0.6, 0.0], seg_deg=12.0))
    nodes.append(emit(slab(W / 2.0 - rc, D / 2.0 - rc, prof, k=8, rho=0.3), "DT_Top", "wood_light", 110,
                      axes=GRAIN["x"]))
    lx, ly = 66.0, 36.0
    leg = _supported(_fillet_poly([(0.0, 0.0), (1.55, 0.0), (2.5, z0), (0.0, z0)], [0, 0.3, 0.15, 0], seg_deg=15.0))
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            nodes.append(emit(lathe(leg, 32, sx * lx, sy * ly, 0.0), "DT_Leg", "wood_light", 110))
    ap_h, ap_t = 7.0, 2.2
    for sy in (-1.0, 1.0):
        nodes.append(emit(rbox(2 * lx, ap_t, ap_h, 0.25, x=0.0, y=sy * ly, z=z0 - ap_h), "DT_Apron",
                          "wood_light", 110, axes=GRAIN["x"]))
    for sx in (-1.0, 1.0):
        nodes.append(emit(rbox(ap_t, 2 * ly - 0.1, ap_h, 0.25, x=sx * lx, y=0.0, z=z0 - ap_h), "DT_Apron",
                          "wood_light", 110, axes=GRAIN["y"]))
    return kit.group("DiningTable", nodes)


# ===================================================================== dining chair
def _catmull(pts, step=2.5):
    """Centripetal Catmull-Rom through pts (no overshoot with uneven spacing), sampled
    about every `step` cm; the ends leave straight toward their neighbours."""
    pts = [tuple(p) for p in pts]
    P = [_sub(_mul(pts[0], 2.0), pts[1])] + pts + [_sub(_mul(pts[-1], 2.0), pts[-2])]
    out = []

    def lerp(a, b, ta, tb, t):
        w = (t - ta) / (tb - ta)
        return tuple(x + (y - x) * w for x, y in zip(a, b))

    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        t0 = 0.0
        t1 = t0 + _len(_sub(p1, p0)) ** 0.5
        t2 = t1 + _len(_sub(p2, p1)) ** 0.5
        t3 = t2 + _len(_sub(p3, p2)) ** 0.5
        n = max(3, int(math.ceil(_len(_sub(p2, p1)) / step)))
        for k in range(n):
            t = t1 + (t2 - t1) * k / float(n)
            a1, a2, a3 = lerp(p0, p1, t0, t1, t), lerp(p1, p2, t1, t2, t), lerp(p2, p3, t2, t3, t)
            b1, b2 = lerp(a1, a2, t0, t2, t), lerp(a2, a3, t1, t3, t)
            out.append(lerp(b1, b2, t1, t2, t))
    out.append(pts[-1])
    return out


def build_dining_chair():
    """Oak frame chair 46 x 52 x 80 (seat 46): tapered round legs, raked back legs,
    curved crest rail tenoned between them, aprons, H-stretcher, crowned and piped
    leather drop-in seat."""
    nodes = []
    fx_, fy_ = 20.5, -22.3
    z_seat = 42.4                         # top of the aprons = underside of the seat pad
    wood = []
    # front legs (lathe, tapered)
    fl = _supported(_fillet_poly([(0.0, 0.0), (1.25, 0.0), (1.65, z_seat), (0.0, z_seat)], [0, 0.25, 0.1, 0]))
    for sx in (-1.0, 1.0):
        wood.append((lathe(fl, 28, sx * fx_, fy_, 0.0), "CH_FrontLeg", GRAIN["z"]))
    # rear legs: raked, swept with a taper
    key = [(21.0, 0.05), (19.0, z_seat), (19.7, 55.0), (21.6, 68.0), (23.3, 80.0)]    # tilted foot touches z = 0
    rad = [1.25, 1.65, 1.56, 1.42, 1.3]
    spl = _catmull([(0.0, y, z) for y, z in key], step=2.5)
    rr = []
    for p in spl:                         # radius by height (piecewise linear on the key heights)
        z = p[2]
        for i in range(len(key) - 1):
            if key[i][1] <= z <= key[i + 1][1] + 1e-6:
                t = (z - key[i][1]) / (key[i + 1][1] - key[i][1])
                rr.append(rad[i] + (rad[i + 1] - rad[i]) * t)
                break
        else:
            rr.append(rad[-1])

    def rear_y(z):
        for i in range(len(spl) - 1):
            if spl[i][2] <= z <= spl[i + 1][2]:
                t = (z - spl[i][2]) / max(1e-6, spl[i + 1][2] - spl[i][2])
                return spl[i][1] + (spl[i + 1][1] - spl[i][1]) * t
        return spl[-1][1]

    for sx in (-1.0, 1.0):
        path = [(sx * fx_, y, z) for _, y, z in spl]
        wood.append((sweep(path, rr, sides=24, fil0=0.2, fil1=1.0, support_min=8.0), "CH_RearLeg", GRAIN["z"]))
    # seat aprons
    ry = rear_y(z_seat - 2.7)
    ah, at = 5.4, 2.0
    wood.append((rbox(2 * fx_, at, ah, 0.25, x=0.0, y=fy_, z=z_seat - ah), "CH_Apron", GRAIN["x"]))
    wood.append((rbox(2 * fx_, at, ah, 0.25, x=0.0, y=ry, z=z_seat - ah), "CH_Apron", GRAIN["x"]))
    for sx in (-1.0, 1.0):
        wood.append((rbox(at, ry - fy_, ah, 0.25, x=sx * fx_, y=(ry + fy_) / 2.0, z=z_seat - ah), "CH_Apron",
                     GRAIN["y"]))
    # stretchers (side + H)
    zs = 15.0
    ys = rear_y(zs)
    for sx in (-1.0, 1.0):
        wood.append((sweep([(sx * fx_, fy_, zs), (sx * fx_, ys, zs)], 0.85, sides=16, cap0=False, cap1=False),
                     "CH_Stretcher", GRAIN["y"]))
    wood.append((sweep([(-fx_, (fy_ + ys) / 2.0, zs), (fx_, (fy_ + ys) / 2.0, zs)], 0.78, sides=16,
                       cap0=False, cap1=False), "CH_Stretcher", GRAIN["x"]))
    # curved crest rail tenoned between the rear legs (its ends are buried in them) and
    # sheared to their rake, so it lies in the plane of the back; the domed leg tops
    # finish just proud of it
    zr, rh = 75.4, 7.6
    yl = rear_y(zr)
    lean = (rear_y(zr + rh / 2.0) - rear_y(zr - rh / 2.0)) / rh
    sag = 2.3
    Rr = (fx_ * fx_ + sag * sag) / (2.0 * sag)
    cyr = yl + sag - Rr
    half = math.degrees(math.asin(fx_ / Rr))
    arc = []
    for i in range(25):
        a = math.radians(-half + 2.0 * half * i / 24.0)
        arc.append((Rr * math.sin(a), cyr + Rr * math.cos(a), zr))
    rail = sweep(arc, 1.0, profile=_rrect2d(rh, 2.0, 0.6, k=3))
    rail.v = [(x, y + (z - zr) * lean, z) for x, y, z in rail.v]
    wood.append((rail, "CH_BackRail", GRAIN["x"]))
    for md, name, axes in wood:
        nodes.append(emit(md, name, "wood_light", 110, axes=axes))
    nodes.append(_seat_pad(z_seat, fx_ + 2.3, -25.6, ry - 1.65 - 0.6))
    return kit.group("DiningChair", nodes)


def _seat_pad(z0, hx, y_front, y_back, rc=3.2, k=6, nx=10, ny=9):
    """Leather drop-in seat: the base sits flat on the aprons, the leather is tucked under
    a 6 mm bottom roll, the sides lean out to a ~1.6 cm rolled top edge carrying a piped
    welt, and the top is crowned ~0.9 cm.  Python-side irregularity (a gentle puff, a
    shallow sitting dip behind the centre, a little waviness in the side band) keeps it
    from reading as a moulding; soften() adds fine noise + TurboSmooth."""
    hy = (y_back - y_front) / 2.0
    cx, cy = hx - rc, hy - rc
    ze = z0 + 3.55                            # virtual corner of the top roll (edge top ~46.0)
    o_g, z_g = rc - 3.0, ze + 0.32            # last ring = boundary of the top grid
    dome = 0.6                                # crown of the top grid above z_g
    prof = _fillet_poly([(-14.0, z0), (rc - 0.3, z0), (rc + 0.4, ze), (o_g, z_g)],
                        [0.0, 0.6, 2.0, 0.0], seg_deg=15.0)

    def ring_rad(o):
        return o if o >= rc else max(0.05, min(rc, 0.45 * min(cx + o, cy + o)))

    def disp(px, py, o, z):
        wz = min(1.0, max(0.0, (z - z0 - 0.35) / (ze - z0 - 0.35)))
        wz = wz * wz * (3.0 - 2.0 * wz)                  # 0 on the base, 1 from the roll up
        wt = min(1.0, max(0.0, (rc - 1.2 - o) / 4.0))
        wt = wt * wt * (3.0 - 2.0 * wt)                  # 0 at the roll, 1 a few cm in
        n = (0.5 * math.sin(0.21 * px + 1.3) * math.sin(0.19 * py + 0.4)
             + 0.3 * math.sin(0.33 * px - 0.29 * py + 2.1)
             + 0.2 * math.sin(0.47 * px + 0.41 * py + 0.7))
        dip = math.exp(-((px - 1.2) ** 2 + (py - 2.5) ** 2) / (2.0 * 8.5 * 8.5))
        dz = wz * wt * (0.17 * n - 0.3 * dip)
        ws = wz * (1.0 - wt)
        gx, gy = px - max(-cx, min(cx, px)), py - max(-cy, min(cy, py))
        gl = math.hypot(gx, gy)
        if gl > 1e-6 and ws > 0.0:
            m = (0.06 * math.sin(0.9 * (px + py) + 0.3) + 0.04 * math.sin(1.7 * px - 1.1 * py)) * ws
            px, py = px + gx / gl * m, py + gy / gl * m
        return (px, py, z + dz)

    md = MD()
    rings = []
    for o, z in prof:
        rings.append([md.vert(disp(px, py, o, z)) for px, py in _rr_ring(cx + o, cy + o, ring_rad(o), k, nx, ny)])
    for i in range(len(rings) - 1):
        _strip(md, rings[i], rings[i + 1])
    _fan_start(md, md.vert((0.0, 0.0, prof[0][1])), rings[0])
    # top: an all-quad Coons-patch grid inside the last ring (no pole, no converging
    # rings, so the crowned leather shows no creases)
    NX, NY = nx + k, ny + k
    bnd = ([(i, 0) for i in range(NX)] + [(NX, j) for j in range(NY)]
           + [(i, NY) for i in range(NX, 0, -1)] + [(0, j) for j in range(NY, 0, -1)])
    ring2d = _rr_ring(cx + o_g, cy + o_g, ring_rad(o_g), k, nx, ny)
    gid, pos = {}, {}
    for r, vi in enumerate(rings[-1]):
        g = bnd[(r + NX - k // 2) % len(bnd)]
        gid[g], pos[g] = vi, ring2d[r]
    X, Y = cx + o_g, cy + o_g

    def bump(p):
        fx = max(0.0, 1.0 - (p[0] / X) ** 2)
        fy = max(0.0, 1.0 - (p[1] / Y) ** 2)
        return fx * fy

    def coons(i, j, val):
        u, v = i / float(NX), j / float(NY)
        return ((1 - v) * val[(i, 0)] + v * val[(i, NY)] + (1 - u) * val[(0, j)] + u * val[(NX, j)]
                - ((1 - u) * (1 - v) * val[(0, 0)] + u * (1 - v) * val[(NX, 0)]
                   + (1 - u) * v * val[(0, NY)] + u * v * val[(NX, NY)]))

    px_ = {g: p[0] for g, p in pos.items()}
    py_ = {g: p[1] for g, p in pos.items()}
    bb = {g: bump(p) for g, p in pos.items()}
    for i in range(1, NX):
        for j in range(1, NY):
            p = (coons(i, j, px_), coons(i, j, py_))
            b = bump(p) - coons(i, j, bb)
            o_eff = o_g - max(0.0, min(X - abs(p[0]), Y - abs(p[1])))
            gid[(i, j)] = md.vert(disp(p[0], p[1], o_eff, z_g + dome * b))
    for i in range(NX):
        for j in range(NY):
            md.quad(gid[(i, j)], gid[(i + 1, j)], gid[(i + 1, j + 1)], gid[(i, j + 1)])
    # piped welt where the tangent of the top roll passes 45 degrees
    best = None
    for (o1, z1), (o2, z2) in zip(prof[:-1], prof[1:]):
        ang = math.degrees(math.atan2(z2 - z1, o2 - o1))
        if best is None or abs(ang - 135.0) < abs(best[0] - 135.0):
            best = (ang, (o1 + o2) / 2.0, (z1 + z2) / 2.0)
    d, rw = 0.09, 0.27
    o_w, z_w = best[1] + 0.7071 * d, best[2] + 0.7071 * d
    path = [disp(px, py, o_w, z_w) for px, py in _rr_ring(cx + o_w, cy + o_w, ring_rad(o_w), k, nx, ny)]
    md.merge(sweep_loop(path, rw, sides=8))
    md.move(0.0, (y_back + y_front) / 2.0, 0.0)
    pn = emit(md, "CH_SeatPad", "leather", 35)
    kit.soften(pn, noise=(10.0, 0.05, 0.07), smooth=1, seed=7)
    return pn


# ===================================================================== pendant lamp
def build_pendant_lamp(drop=80, ceiling=270.0):
    """Matte black dome pendant (40 cm) on a black fabric cord from a ceiling rose.
    The rose sits on z = ceiling; drop = ceiling to the top of the shade."""
    nodes = []
    C = float(ceiling)
    z_top = C - float(drop)
    blk = MD()
    blk.merge(lathe(_supported(_fillet_poly([(0.0, C - 2.6), (5.5, C - 2.6), (5.5, C), (0.0, C)],
                                            [0, 0.5, 0.05, 0])), 48))
    blk.merge(lathe(_supported(_fillet_poly([(0.0, C - 4.2), (0.62, C - 4.2), (0.62, C - 2.55), (0.0, C - 2.55)],
                                            [0, 0.15, 0.0, 0])), 20))
    # dome: outer curve from the rim up to the neck
    Rr, Hd, rn = 20.0, 21.0, 3.2
    curve = []
    for i in range(25):
        a = 0.5 * math.pi * (1.0 - i / 24.0)            # 90deg at the rim -> 0 at the top
        curve.append((rn + (Rr - rn) * math.sin(a), z_top - Hd * (1.0 - math.cos(a))))
    t = 0.12
    inner = []
    for i in range(len(curve)):
        a = curve[max(i - 1, 0)]
        b = curve[min(i + 1, len(curve) - 1)]
        tg = _unit(_sub(b, a))
        inner.append((curve[i][0] - t * tg[1], curve[i][1] + t * tg[0]))
    rim_c = _mul(_add(curve[0], inner[0]), 0.5)
    e = _sub(curve[0], rim_c)
    rim = [_add(rim_c, _add(_mul(e, math.cos(math.pi * k / 6.0)), (0.0, -0.5 * t * math.sin(math.pi * k / 6.0))))
           for k in range(6, 0, -1)]
    outer_prof = rim + curve[1:] + [(rn - 0.2, z_top + 3.0), (0.0, z_top + 3.4)]
    outer_prof = _fillet_poly(outer_prof, [0.0] * (len(outer_prof) - 3) + [0.4, 0.5, 0.0], seg_deg=15.0)
    blk.merge(lathe(_supported(outer_prof, min_len=3.0), 64))
    # socket hanging inside the shade
    blk.merge(lathe(_supported(_fillet_poly([(0.0, z_top - 7.5), (1.9, z_top - 7.5), (1.9, z_top - 0.1),
                                             (0.0, z_top - 0.1)], [0, 0.25, 0.0, 0])), 32))
    nodes.append(emit(blk, "PL_ShadeOuter", "metal_black", 30))
    inner_prof = [(0.0, inner[-1][1])] + list(reversed(inner))
    nodes.append(emit(lathe(_supported(inner_prof, min_len=3.0), 64), "PL_ShadeInner", "paint_white", 60))
    cord = sweep([(0.0, 0.0, C - 4.0), (0.0, 0.0, z_top + 3.0)], 0.32, sides=12, cap0=False, cap1=False)
    nodes.append(emit(cord, "PL_Cord", "plastic_black", 20))
    # warm G95 globe bulb
    zb = z_top - 7.5
    bulb = [(0.0, zb + 0.3), (1.35, zb + 0.3), (1.35, zb - 1.6)]
    rg = 4.75
    cz = zb - 1.6 - math.sqrt(rg * rg - 1.35 * 1.35)
    a0 = math.degrees(math.atan2(1.35, zb - 1.6 - cz))
    for i in range(1, 25):
        a = math.radians(a0 + (180.0 - a0) * i / 24.0)
        bulb.append((rg * math.sin(a), cz + rg * math.cos(a)))
    bulb[-1] = (0.0, cz - rg)
    bulb = list(reversed(_fillet_poly(bulb, [0, 0.1, 0.6] + [0.0] * (len(bulb) - 3))))   # bottom pole up
    nodes.append(emit(lathe(_supported(bulb), 40), "PL_Bulb", "emissive_warm", None, maptype=None))
    return kit.group("PendantLamp", nodes)


# ===================================================================== table decor
def build_table_decor():
    """Ceramic fruit bowl + glass carafe and two tumblers, arranged for the table centre."""
    nodes = []
    bowl = _vessel(_bowl_outer(14.0, 8.5, 5.5, 0.9, foot_w=0.6, recess=0.4, amax=70.0), 0.55, 1.4, floor_r=1.5)
    nodes.append(emit(lathe(bowl, 56, -14.0, 2.5, 0.0), "TD_FruitBowl", "ceramic_white", 30))
    glass = MD()
    carafe_outer = _fillet_poly([(0.0, 0.05), (4.55, 0.0), (4.75, 13.5), (2.15, 19.0), (2.0, 23.6), (2.3, 25.0)],
                                [0.0, 0.6, 3.6, 2.4, 0.8, 0.0], seg_deg=8.0)
    glass.merge(lathe(_vessel(carafe_outer, 0.26, 0.75, floor_r=0.8, n_rim=6), 48, 15.0, 6.5, 0.0))
    tumbler_outer = _fillet_poly([(0.0, 0.07), (3.5, 0.0), (3.9, 9.0)], [0.0, 0.32, 0.0])
    tumbler = _vessel(tumbler_outer, 0.17, 0.95, floor_r=0.45, n_rim=6)
    for x, y in ((25.0, -4.0), (8.5, -8.5)):
        glass.merge(lathe(tumbler, 48, x, y, 0.0))
    nodes.append(emit(glass, "TD_Glassware", "glass", 50))
    return kit.group("TableDecor", nodes)


# ===================================================================== preview
def _stats(label):
    path = os.environ.get("MF_KITCHEN_STATS")
    if not path:
        return
    tot = 0
    lines = []
    for node, key, tile, maptype in kit.PARTS:
        n = int(rt.getPolygonCount(node)[0])
        tot += n
        lines.append("%-22s %-14s %7d" % (str(node.name), key, n))
    lines.append("TOTAL %s faces: %d  parts: %d" % (label, tot, len(kit.PARTS)))
    with open(path, "w") as fh:
        fh.write("\n".join(lines))


def preview():
    which = os.environ.get("MF_KITCHEN_PREVIEW", "all").lower()
    if which == "run":
        kit.place(build_kitchen_run(), 0, 0)
    elif which == "run290":                       # the configuration apartment_scene.py uses
        kit.place(build_kitchen_run(length=290, sink_at=142, cook_at=245, shelf=(0, 60)), 0, 0)
    elif which == "fridge":
        kit.place(build_fridge(), 0, 0)
    elif which == "table":
        kit.place(build_dining_table(), 0, 0)
        kit.place(build_table_decor(), 0, 0, 75.0)
    elif which == "chair":
        kit.place(build_dining_chair(), 0, 0)
    elif which == "pendant":
        kit.place(build_pendant_lamp(), 0, 0)
    elif which == "decor":
        kit.place(build_table_decor(), 0, 0)
    elif which == "dining":
        kit.place(build_dining_table(), 0, 0)
        kit.place(build_table_decor(), 0, 0, 75.0)
        # chair fronts face -Y at rot 0: north-side chairs keep 0, south-side chairs turn 180
        kit.place(build_dining_chair(), -35.0, 58.0, 0.0, 0.0)
        kit.place(build_dining_chair(), 35.0, 62.0, 0.0, -6.0)
        kit.place(build_dining_chair(), 35.0, -60.0, 0.0, 180.0)
        kit.place(build_dining_chair(), -35.0, -72.0, 0.0, 168.0)
    else:
        kit.place(build_kitchen_run(), 0, 0)
        kit.place(build_fridge(), 205.0, 0)
        kit.place(build_dining_table(), 375.0, 0)
        kit.place(build_table_decor(), 375.0, 0, 75.0)
        kit.place(build_dining_chair(), 505.0, 0)
        kit.place(build_pendant_lamp(), 585.0, 0)
    _stats(which)
