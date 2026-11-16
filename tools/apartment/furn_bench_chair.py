"""Mid-century lounge chair for the MatForge benchmark living room (bright white
pre-war apartment): a slim satin-steel flat-bar frame carrying two loose black
leather cushions.

  build_lounge_chair(width=70, depth=78, height=72, seat_h=38, arm_h=56, ...)
      W 70 x D 78 x H 72 cm, seat 38 cm. Built at the local origin (centre of the
      footprint, FRONT facing -Y, floor at z = 0) and returned as kit.group(...).

Frame ("metal_steel", own UVs with U along every bar so the satin brushing follows
it): two side frames, each ONE continuous 4 x 1 cm flat bar bent the easy way (the
4 cm face across X, so the arm is a flat 4 cm rest and the frame reads as a 1 cm line
from the side). From the eased top of the reclined back post it runs down the post,
bends forward into the floor runner (inner radius 3.5 cm), up the front leg (5.5),
back along the arm (4.5), and the arm's end is welded to the post. Four cross bars on
edge join the side frames: the front seat rail between the front legs, and the rear
seat rail, lumbar rail and top rail between the posts. Every bar edge carries a 2 mm
radius (with support loops so the flats shade dead flat), every joint a ground
fillet weld. Rubber glides lift the runners 3 mm off the boards. Four leather straps
screwed to the inner faces of the seat rails carry the seat cushion.

Cushions ("leather", own UVs: top / bottom panels and a wrapped boxing strip with
the UV seams on the welts, like the hides are cut): plump welted box cushions (seat
12 cm thick) with leather piping on both seams and 5 cm plan corners. The faces dome
from the welts (seat crown 2.8 cm, back 3.5 cm and 1.2 cm on its back face) with no
kink where the rolled edges (2.5 cm) meet them, so a window highlight rolls right
over; the show seams are pulled in 1.3 cm at mid-span and the boxing strips bulge
9 mm. Broad soft creases (3-6 mm deep, 2-2.6 cm wide) where the leather bunches: two
folds over the seat's front edge with a ridge between them, one out of each front
corner, one down each boxing, a long diagonal fold out of the back cushion's foot
and a fold across it. The seat has a sat-in hollow and a sagging front edge and is
squashed flat under the back cushion's foot. The back cushion leans at back_angle
(100 deg) to the seat: its back face is flattened against the lumbar and top rails
(bulging between them), its foot rests on the seat cushion, its top curls back over
the top rail and it sits a hair askew. kit.soften adds a fine Noise in Max.

All geometry is pure Python: lounge_chair_layout() gives the key dimensions,
lounge_chair_parts() the _MD meshes (testable without 3ds Max); build_lounge_chair()
only turns those parts into nodes.
"""
import math

import kit
import furn_living as fl
from furn_living import (_MD, _Grid2, _Rand, _add, _cross, _dot, _fillet2d, _mul, _norm, _slab, _smax,
                         _smooth, _sub)

LEATHER = 35.0                      # cm per UV unit on the leather (hide grain)
STEEL = 25.0                        # cm per UV unit on the steel; U runs along each bar
RUBBER = 20.0
SUPPORT = 0.03                      # support-loop offset (cm): shading gradients stay in 0.3 mm
LEATHER_NOISE = (16.0, 0.07, 0.09)  # Max Noise on the cushions (scale, xy, z strength)
CUSHION_STEP = 0.85                 # cm between cushion cage lines (creases need ~1 cm)


class Part(object):
    """One node to build. mode 'uv': hard, own UVs (tile = cm per UV unit), TurboSmooth
    `smooth`; 'box': hard, box-mapped at `tile`; 'soft': own UVs, built in its own frame
    (axes rows, origin) with Noise `noise` (kit.soften)."""
    __slots__ = ("name", "md", "mat", "tile", "mode", "axes", "origin", "noise", "seed", "smooth")

    def __init__(self, name, md, mat, tile, mode, axes=None, origin=None, noise=None, seed=0, smooth=0):
        self.name, self.md, self.mat, self.tile, self.mode = name, md, mat, tile, mode
        self.axes, self.origin, self.noise, self.seed, self.smooth = axes, origin, noise, seed, smooth

    def __repr__(self):
        return "Part(%s, %s, %d verts, %d faces)" % (self.name, self.mat, len(self.md.v), len(self.md.f))


# ===================================================================== flat bar
def _rr_section(w, t, r, k=4, s=SUPPORT):
    """Closed CCW rounded rectangle: a across (width w), b through (thickness t), corner
    radius r in k segments, support points s in from both ends of every straight side.
    Returns [(a, b, na, nb)] with the outward 2-D normal of each point."""
    ea, eb = 0.5 * w - r, 0.5 * t - r
    cs = ((ea, -eb, -90.0), (ea, eb, 0.0), (-ea, eb, 90.0), (-ea, -eb, 180.0))
    out = []
    for ci, (ca, cb, a0) in enumerate(cs):
        for i in range(k + 1):
            ang = math.radians(a0 + 90.0 * i / k)
            c, sn = math.cos(ang), math.sin(ang)
            out.append((ca + r * c, cb + r * sn, c, sn))
        side = math.radians(a0 + 90.0)
        na, nb = math.cos(side), math.sin(side)
        nca, ncb, na0 = cs[(ci + 1) % 4]
        p0 = out[-1][:2]
        p1 = (nca + r * math.cos(math.radians(na0)), ncb + r * math.sin(math.radians(na0)))
        ln = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        if ln > 3.0 * s:
            dx, dy = (p1[0] - p0[0]) / ln, (p1[1] - p0[1]) / ln
            out.append((p0[0] + dx * s, p0[1] + dy * s, na, nb))
            out.append((p1[0] - dx * s, p1[1] - dy * s, na, nb))
    return out


def _supported(pts, s=0.05, min_len=1.2):
    """Insert support points s from both ends of every segment longer than min_len (the
    straight runs of a filleted path), so their rings stay square to the bar."""
    out = [tuple(pts[0])]
    for i in range(1, len(pts)):
        a, b = pts[i - 1], pts[i]
        ln = math.sqrt(sum((b[k] - a[k]) ** 2 for k in range(len(a))))
        if ln > min_len:
            out.append(tuple(a[k] + (b[k] - a[k]) * s / ln for k in range(len(a))))
            out.append(tuple(b[k] - (b[k] - a[k]) * s / ln for k in range(len(a))))
        out.append(tuple(b))
    return out


def _sweep_md(path, avec, sec, uv_tile=None, end0="flat", end1="flat", r_end=0.15, k_end=3):
    """Sweep a closed CCW section [(a, b, na, nb)] along a 3-D polyline. avec: the
    section's a-axis (a vector, or one per point); b = T x a. Ends: 'flat' n-gon cap,
    'round' (eased: a quarter round of r_end, then a support ring and a flat cap) or
    None (open). uv_tile: U = length along the path, V = round the section."""
    n = len(path)
    seg = [_norm(_sub(path[i + 1], path[i])) for i in range(n - 1)]
    tan = [seg[0]] + [_norm(_add(seg[i - 1], seg[i])) for i in range(1, n - 1)] + [seg[-1]]
    S = [0.0]
    for i in range(n - 1):
        d = _sub(path[i + 1], path[i])
        S.append(S[-1] + math.sqrt(_dot(d, d)))
    frames = []
    for i in range(n):
        a = avec[i] if isinstance(avec, list) else avec
        a = _norm(_sub(a, _mul(tan[i], _dot(a, tan[i]))))
        frames.append((path[i], a, _cross(tan[i], a), 0.0, S[i]))

    def eased(i, kind, sign):
        if kind != "round":
            return []
        c, a, b, _d, s0 = frames[i]
        t = _mul(tan[i], sign)
        out = []
        for j in range(1, k_end + 1):
            ph = 0.5 * math.pi * j / k_end
            off = r_end * math.sin(ph)
            out.append((_add(c, _mul(t, off)), a, b, r_end * (1.0 - math.cos(ph)), s0 + sign * off))
        out.append((_add(c, _mul(t, r_end)), a, b, r_end + SUPPORT, s0 + sign * r_end))
        return out

    ring_defs = list(reversed(eased(0, end0, -1.0))) + frames + eased(n - 1, end1, 1.0)
    m = len(sec)
    per = [0.0]
    for j in range(m):
        p0, p1 = sec[j], sec[(j + 1) % m]
        per.append(per[-1] + math.hypot(p1[0] - p0[0], p1[1] - p0[1]))
    md = _MD()
    rings = []
    for (c, a, b, d, s) in ring_defs:
        ring = [md.add(_add(c, _add(_mul(a, pa - na * d), _mul(b, pb - nb * d)))) for (pa, pb, na, nb) in sec]
        rings.append((ring, s))
    for k in range(len(rings) - 1):
        r0, s0 = rings[k]
        r1, s1 = rings[k + 1]
        for j in range(m):
            j2 = (j + 1) % m
            uv = None
            if uv_tile:
                t_ = float(uv_tile)
                uv = ((s0 / t_, per[j] / t_), (s0 / t_, per[j + 1] / t_),
                      (s1 / t_, per[j + 1] / t_), (s1 / t_, per[j] / t_))
            md.face((r0[j], r0[j2], r1[j2], r1[j]), uv)
    # caps start at a 45-degree corner point: _build fans from the first vertex, and a
    # fan from a point on a straight side makes zero-area slivers with random normals
    j0 = max(range(m), key=lambda j: abs(sec[j][2] * sec[j][3]))
    if end0:
        r0 = rings[0][0][j0:] + rings[0][0][:j0]
        md.face([r0[0]] + r0[:0:-1])                 # faces -T
    if end1:
        md.face(rings[-1][0][j0:] + rings[-1][0][:j0])   # faces +T
    return md


def _newell(pts):
    n = [0.0, 0.0, 0.0]
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    return tuple(n)


def _extrude_md(prof, axis, half, s=0.01):
    """Closed prism: the planar polygon prof (star-shaped from prof[0]) swept from -half
    to +half along the unit axis, with support rings s in from both ends so the
    flat end caps do not bend the shading of the sides."""
    if _dot(_newell(prof), axis) < 0.0:
        prof = [prof[0]] + prof[:0:-1]
    md = _MD()
    rings = [[md.add(_add(p, _mul(axis, t))) for p in prof] for t in (-half, s - half, half - s, half)]
    m = len(prof)
    for r0, r1 in zip(rings[:-1], rings[1:]):
        for j in range(m):
            j2 = (j + 1) % m
            md.face((r0[j], r0[j2], r1[j2], r1[j]))
    md.face([rings[0][0]] + rings[0][:0:-1])
    md.face(rings[-1])
    return md


def _weld_md(o, d1, d2, axis, half, r, sink=0.04, n=6):
    """Ground fillet weld in the concave corner at o between two faces meeting along
    `axis`: d1, d2 run along the faces away from the corner. The fillet (radius r) is
    tangent to both faces and dips 0.3 mm into them at its edges (short lips), so under
    one smoothing group its edges shade like the faces they blend into; its flanks are
    sunk `sink` into the parts."""
    th = math.acos(max(-1.0, min(1.0, _dot(d1, d2))))
    bis = _norm(_add(d1, d2))
    tl = r / math.tan(0.5 * th)
    cen = _add(o, _mul(bis, r / math.sin(0.5 * th)))
    t1, t2 = _add(o, _mul(d1, tl)), _add(o, _mul(d2, tl))
    v1, v2 = _norm(_sub(t1, cen)), _norm(_sub(t2, cen))
    om = math.acos(max(-1.0, min(1.0, _dot(v1, v2))))

    def arc(f):
        w0 = math.sin((1.0 - f) * om) / math.sin(om)
        w1 = math.sin(f * om) / math.sin(om)
        return _add(cen, _mul(_add(_mul(v1, w0), _mul(v2, w1)), r))

    fs = [0.0, 0.01] + [j / float(n) for j in range(1, n)] + [0.99, 1.0]
    # v1, v2 point from the fillet centre through the tangent points, i.e. into the parts
    prof = [_sub(o, _mul(bis, sink)), _add(t1, _mul(v1, 0.03))]
    prof += [arc(f) for f in fs]
    prof.append(_add(t2, _mul(v2, 0.03)))
    return _extrude_md(prof, axis, half)


# ===================================================================== layout
def lounge_chair_layout(width=70.0, depth=78.0, height=72.0, seat_h=38.0, arm_h=56.0, bar_w=4.0, bar_t=1.0,
                        seat_t=12.0, back_t=10.0, back_angle=100.0, seat_tilt=4.0, glide=0.3, **_unused):
    """Key dimensions (cm) and frames of the chair, all derived from the arguments.
    The back leans back_angle - 90 + seat_tilt degrees from vertical (the seat plane
    itself tilts seat_tilt back), so the seat-to-back angle is back_angle."""
    L = dict(width=float(width), depth=float(depth), height=float(height), seat_h=float(seat_h),
             arm_h=float(arm_h), bar_w=float(bar_w), bar_t=float(bar_t), seat_t=float(seat_t),
             back_t=float(back_t), back_angle=float(back_angle), seat_tilt=float(seat_tilt),
             glide=float(glide), edge_r=0.2)
    t = math.radians(seat_tilt)
    beta = math.radians(back_angle - 90.0 + seat_tilt)
    sb, cb, tb = math.sin(beta), math.cos(beta), math.tan(beta)
    ct, st, tt = math.cos(t), math.sin(t), math.tan(t)
    xo = 0.5 * width
    xc, xi = xo - 0.5 * bar_w, xo - bar_w
    zr = glide + 0.5 * bar_t                      # runner centreline
    yf = -0.5 * depth + 0.5 * bar_t               # front leg centreline
    za = arm_h - 0.5 * bar_t                      # arm centreline
    post_top = height - 6.5
    y0 = 0.5 * depth - 0.5 * bar_t * cb           # post top (its rear corner at y = depth / 2)
    z0 = post_top - 0.5 * bar_t * sb
    y1 = y0 - (z0 - zr) * tb                      # post / runner virtual corner

    def yc(z):                                    # post centreline at height z
        return y1 + (z - zr) * tb

    def y_plane(z):                               # front face of the posts and back rails
        return yc(z) - 0.5 * bar_t / cb

    u = (0.0, sb, cb)                             # up the back
    nf = (0.0, -cb, sb)                           # out of the back plane, towards the sitter
    pc = (0.0, y1, zr)                            # a point on the post centreline plane
    R1, R2, R3 = 4.0, 6.0, 5.0                    # centreline bend radii: rear foot, front foot, arm
    pts = [(y0, z0), (y1, zr), (yf, zr), (yf, za), (yc(za), za)]
    d1 = _norm((0.0, y1 - y0, zr - z0))
    d2 = (0.0, -1.0, 0.0)
    th1 = math.acos(max(-1.0, min(1.0, _dot(d1, d2))))
    runner = (yf + R2, y1 - R1 * math.tan(0.5 * th1))   # straight floor contact (y range)

    # seat cushion: front seam 6 mm behind the frame front, top front seam at seat_h,
    # bottom on the support plane (front rail top, strap tops), rear 3 mm off the back plane;
    # its sides 1.1 cm in from the side frames, room for the boxing's ~6 mm bulge
    y_sf = -0.5 * depth + 0.6
    z_sb = seat_h - seat_t * ct

    def z_sp(y):
        return z_sb - (y - y_sf) * tt

    y_rb = y_plane(z_sp(0.0)) - 0.3
    for _ in range(6):
        y_rb = y_plane(z_sp(y_rb)) - 0.3
    sA = xi - 1.1
    sB = (y_rb - y_sf) / (2.0 * ct)
    s_org = (0.0, y_sf + sB * ct, z_sb - sB * st)
    s_axes = ((1.0, 0.0, 0.0), (0.0, ct, -st), (0.0, st, ct))

    # cross bars (centres); the post rails lie in the post plane, their width up the post
    front_rail = (0.0, yf, z_sp(yf + 0.5 * bar_t) - 0.02 - 0.5 * bar_w)
    zc = 21.0
    for _ in range(8):                            # rear seat rail: front-top edge on the support plane
        ey = yc(zc) + 0.5 * bar_w * sb - 0.5 * bar_t * cb
        ez = zc + 0.5 * bar_w * cb + 0.5 * bar_t * sb
        zc -= (ez - (z_sp(ey) - 0.02)) / (1.0 + tt * tb)
    rear_rail = (0.0, yc(zc), zc)
    zl = seat_h + 5.0
    lumbar_rail = (0.0, yc(zl), zl)
    top_rail = (0.0, y0 - (1.0 + 0.5 * bar_w) * sb, z0 - (1.0 + 0.5 * bar_w) * cb)

    L.update(beta=beta, tilt=t, xo=xo, xc=xc, xi=xi, zr=zr, yf=yf, za=za, post_top=post_top, y0=y0, z0=z0,
             y1=y1, yc=yc, y_plane=y_plane, u=u, nf=nf, pc=pc, frame_pts=pts, frame_radii=[0.0, R1, R2, R3, 0.0],
             runner=runner, glide_y=(runner[0] + 3.2, runner[1] - 3.2), y_sf=y_sf, z_sb=z_sb, z_sp=z_sp,
             seat_A=sA, seat_B=sB, seat_origin=s_org, seat_axes=s_axes, back_A=xi - 1.4,
             front_rail=front_rail, rear_rail=rear_rail, lumbar_rail=lumbar_rail, top_rail=top_rail,
             back_gap=0.25)
    return L


# ===================================================================== frame
def _side_frame_md(L, xc):
    """One continuous flat bar: post top -> post -> runner -> front leg -> arm -> post,
    with the two fillet welds where the arm meets the post."""
    path2 = _fillet2d(L["frame_pts"], L["frame_radii"], step=math.radians(5.0))
    path = [(xc, y, z) for (y, z) in _supported(path2)]
    sec = _rr_section(L["bar_w"], L["bar_t"], L["edge_r"])
    md = _sweep_md(path, (1.0, 0.0, 0.0), sec, STEEL, end0="round", end1="flat", r_end=0.15)
    half = 0.5 * L["bar_w"] - L["edge_r"]
    for sz, r in ((1.0, 0.45), (-1.0, 0.35)):
        z = L["za"] + sz * 0.5 * L["bar_t"]
        o = (xc, L["y_plane"](z), z)
        md.merge(_weld_md(o, (0.0, -1.0, 0.0), _mul(L["u"], sz), (1.0, 0.0, 0.0), half, r))
    return md


def _rail_md(L, centre, wdir):
    """Cross bar on edge (its 4 cm width along wdir) between the side frames, ends 3 mm
    into them, ground fillet welds where its edges meet their inner faces."""
    xe = L["xi"] + 0.3
    path = _supported([(-xe, centre[1], centre[2]), (xe, centre[1], centre[2])])
    sec = _rr_section(L["bar_w"], L["bar_t"], L["edge_r"])
    md = _sweep_md(path, wdir, sec, STEEL)
    thick = _norm(_cross((1.0, 0.0, 0.0), wdir))
    hw = 0.5 * L["bar_w"]
    for sx in (-1.0, 1.0):
        for sw in (-1.0, 1.0):
            o = (sx * L["xi"], centre[1] + sw * hw * wdir[1], centre[2] + sw * hw * wdir[2])
            md.merge(_weld_md(o, (-sx, 0.0, 0.0), _mul(wdir, sw), thick, 0.5 * L["bar_t"] - L["edge_r"], 0.3))
    return md


def frame_md(L):
    """Both side frames and the four cross bars (one 'metal_steel' mesh, own UVs)."""
    md = _MD()
    for sx in (-1.0, 1.0):
        md.merge(_side_frame_md(L, sx * L["xc"]))
    md.merge(_rail_md(L, L["front_rail"], (0.0, 0.0, 1.0)))
    for key in ("rear_rail", "lumbar_rail", "top_rail"):
        md.merge(_rail_md(L, L[key], L["u"]))
    return md


def glides_md(L):
    """3 mm rubber glides under both ends of each runner's floor contact."""
    md = _MD()
    for sx in (-1.0, 1.0):
        for yg in L["glide_y"]:
            md.merge(_slab(0.5 * L["bar_w"] - 0.25, 2.5, 0.0, L["glide"] + 0.03, 0.8, p=6, q=6,
                           rb=(0.08, 0.08), rt_=(0.05, 0.05), mb=1, ms=1, mt=1, cx=sx * L["xc"], cy=yg, amin=1))
    return md


def straps_md(L, n=4, w=5.0, t=0.35):
    """Seat straps: screwed to the inner faces of the front and rear seat rails, their
    tops on the cushion's support plane, 3 cm turned down each rail."""
    md = _MD()
    if n <= 0:
        return md
    beta, tilt = L["beta"], L["tilt"]
    sb, cb, tt = math.sin(beta), math.cos(beta), math.tan(tilt)
    ys = L["yf"] + 0.5 * L["bar_t"] + 0.5 * t
    a0 = L["z_sb"] + L["y_sf"] * tt - 0.02 - 0.5 * t      # strap centreline z = a0 - tt * y
    c = 0.5 * L["bar_t"] + 0.5 * t
    y1, zr = L["pc"][1], L["pc"][2]
    yr = (cb * y1 + sb * (a0 - zr) - c) / (cb + sb * tt)
    fc, rc = (ys, a0 - tt * ys), (yr, a0 - tt * yr)
    pts = [(fc[0], fc[1] - 3.0), fc, rc, (rc[0] - 3.0 * sb, rc[1] - 3.0 * cb)]
    path2 = _supported(_fillet2d(pts, [0.0, 0.35, 0.35, 0.0], step=math.radians(10.0)))
    sec = _rr_section(w, t, 0.12, k=3)
    pitch = 2.0 * L["xi"] / n
    for k in range(n):
        x = (k - 0.5 * (n - 1)) * pitch
        md.merge(_sweep_md([(x, y, z) for (y, z) in path2], (1.0, 0.0, 0.0), sec, LEATHER,
                           end0="round", end1="round", r_end=0.08, k_end=2))
    return md


# ===================================================================== cushions
def _crease_sum(lst, a, b):
    """Soft creases in a 2-D surface chart: each (a0, b0, a1, b1, depth, sigma) is a
    Gaussian groove (depth > 0) or ridge (depth < 0) along the segment, fading out over
    the last 30 % at either end."""
    tot = 0.0
    for a0, b0, a1, b1, dep, sg in lst:
        da, db = a1 - a0, b1 - b0
        t = ((a - a0) * da + (b - b0) * db) / (da * da + db * db)
        if t <= 0.0 or t >= 1.0:
            continue
        ea, eb = a0 + t * da - a, b0 + t * db - b
        q = (ea * ea + eb * eb) / (sg * sg)
        if q > 9.0:
            continue
        tot += dep * math.exp(-q) * _smooth(t / 0.3) * _smooth((1.0 - t) / 0.3)
    return tot


class _CushionShape(object):
    """Deformation of a welted box cushion built by _slab(A, B, 0, T, ...) in its local
    frame (the 'top' cap at z = T is the show face, -Y the edge that faces the room):
    domed panels, the show seam pulled in at mid-span by the crown (pin; pin_y0 on the
    -Y seam, default pin), soft creases in surface charts and extra(x, y, z) -> (dx, dy, dz).

    The dome is zero on the welt lines (45 degrees round the rolled edges, where the
    piping sits) and rises from there, over the inner half of the roll and on into the
    panel, so the roll runs into the dome without a kink.

    Crease charts: 'top' (x, y) on the show face; 'front' (x, s) unfolded over the -Y
    edge, s = (y + B) + (z - T) (< 0 down the boxing); 'side+' / 'side-' (y, s) over
    the +-X edges. Creases displace along the normal of the undeformed cushion."""

    def __init__(self, A, B, T, rc, rb, rt, crown, crown_b, pin, creases=(), extra=None, pin_y0=None):
        self.A, self.B, self.T, self.rc, self.rb, self.rt = A, B, T, rc, rb, rt
        self.crown, self.crown_b, self.pin, self.extra = crown, crown_b, pin, extra
        self.pin_y0 = pin if pin_y0 is None else pin_y0
        self.charts = {}
        for c in creases:
            self.charts.setdefault(c[0], []).append(tuple(c[1:]))

    def dome(self, x, y, top=True):
        """Lift of the show face (top) or drop of the bottom face at plan point (x, y):
        zero on and outside the welt line, crown (crown_b) in the middle."""
        w = 0.2929 * (self.rt if top else self.rb)          # welt inset: r (1 - cos 45)
        sx = min(1.0, abs(x) / (self.A - w))
        sy = min(1.0, abs(y) / (self.B - w))
        return (self.crown if top else self.crown_b) * (1.0 - sx ** 2.6) * (1.0 - sy ** 2.6)

    def normal(self, x, y, z):
        A, B, T, r = self.A, self.B, self.T, self.rt
        qx = max(-(A - r), min(A - r, x))
        qy = max(-(B - r), min(B - r, y))
        qz = max(r, min(T - r, z))
        n = (x - qx, y - qy, z - qz)
        ln = math.sqrt(_dot(n, n))
        if ln < 1e-6:
            return (0.0, 0.0, 1.0 if z > 0.5 * T else -1.0)
        return (n[0] / ln, n[1] / ln, n[2] / ln)

    def crease(self, x, y, z):
        A, B, T, rt = self.A, self.B, self.T, self.rt
        tot = 0.0
        for chart, lst in self.charts.items():
            if chart == "top":
                w, a, b = _smooth((z - (T - rt)) / rt), x, y
            elif chart == "front":
                w = (1.0 - _smooth((y + B - 13.0) / 4.0)) * _smooth((z - (T - 8.5)) / 2.5)
                a, b = x, (y + B) + (z - T)
            else:
                sx = 1.0 if chart == "side+" else -1.0
                w = _smooth((sx * x - (A - 12.0)) / 3.0) * _smooth((z - (T - 9.0)) / 2.5)
                a, b = y, (A - sx * x) + (z - T)
            if w > 0.0:
                tot += w * _crease_sum(lst, a, b)
        return tot

    def __call__(self, p):
        x, y, z = p
        A, B, T = self.A, self.B, self.T
        dz = self.dome(x, y) if z > 0.5 * T else -self.dome(x, y, False)
        hz = _smooth((z - 0.15 * T) / (0.85 * T))
        mx = max(0.0, 1.0 - (x / (A - self.rc)) ** 2) ** 2
        my = max(0.0, 1.0 - (y / (B - self.rc)) ** 2) ** 2
        pin_y = self.pin if y > 0.0 else self.pin_y0
        dx = -math.copysign(self.pin * my * _smooth((abs(x) - (A - 9.0)) / 9.0) * hz, x)
        dy = -math.copysign(pin_y * mx * _smooth((abs(y) - (B - 9.0)) / 9.0) * hz, y)
        if self.extra is not None:
            ex = self.extra(x, y, z)
            dx, dy, dz = dx + ex[0], dy + ex[1], dz + ex[2]
        if self.charts:
            c = self.crease(x, y, z)
            if c:
                n = self.normal(x, y, z)
                dx, dy, dz = dx - c * n[0], dy - c * n[1], dz - c * n[2]
        return (x + dx, y + dy, z + dz)


def _segs(length):
    return max(8, int(round(length / CUSHION_STEP)))


def _xf(p, org, axes):
    return tuple(org[k] + p[0] * axes[0][k] + p[1] * axes[1][k] + p[2] * axes[2][k] for k in range(3))


def _seat_creases(A, B, yb, seed):
    rnd = _Rand(seed * 13 + 3)

    def j(a):
        return rnd.uniform(-a, a)

    cr = []
    # two broad folds where the leather bunches over the front edge, running front to
    # back off the boxing onto the panel, and the soft ridge gathered between them
    for xk, dep in ((-11.0, 0.55), (9.5, 0.45)):
        x0 = xk + j(1.5)
        cr.append(("front", x0, -5.5 + j(0.8), x0 + 2.0 + j(1.5), 11.0 + j(1.5), dep * (1.0 + j(0.1)),
                   2.4 + j(0.2)))
    cr.append(("front", -1.0 + j(1.0), -4.0, -0.5 + j(1.5), 8.0, -0.3, 2.2))
    # a broad tension wrinkle fanning out of each front corner over the top panel
    for sx in (-1.0, 1.0):
        a = math.radians(47.0 + j(6.0))
        ln = 10.0 + j(1.5)
        x0, y0 = sx * (A - 3.0), -B + 3.0
        cr.append(("top", x0, y0, x0 - sx * ln * math.cos(a), y0 + ln * math.sin(a), 0.3 + j(0.04), 2.0))
    # one wrinkle down each side boxing, near the front corner
    for side in ("side+", "side-"):
        y0 = -B + 8.0 + j(1.5)
        cr.append((side, y0, -9.0, y0 - 2.5 + j(1.0), 3.0, 0.34 + j(0.04), 2.0))
    # leather gathered in front of the back cushion's foot: a long low ridge
    cr.append(("top", -22.0, yb - 4.6, 21.0, yb - 4.0, -0.3, 2.4))
    return cr


def _back_creases(A, B, seed):
    rnd = _Rand(seed * 17 + 11)

    def j(a):
        return rnd.uniform(-a, a)

    cr = []
    # a long diagonal fold out of the foot, where the leather bunches as the cushion sits:
    # it leaves the foot seam at xf, rising ~52 degrees to the right; the segment starts
    # 8 cm under the seam so the fold is near full depth where it leaves the foot
    xf, run = -12.0 + j(2.0), 0.78 + j(0.08)          # run: cm across per cm up
    cr.append(("top", xf - 8.0 * run, -B - 8.0, xf + 22.0 * run, -B + 22.0 + j(1.5), 0.45 + j(0.04), 2.4))
    # a broad fold across the front face just above the foot, beside the diagonal one
    cr.append(("top", -3.0 + j(2.0), -B + 7.5 + j(1.0), 19.0 + j(2.0), -B + 6.0 + j(1.0), 0.4, 2.3))
    # bunching over the foot edge: soft folds running a few cm up the front face
    for xk in (-3.0, 14.0):
        x0 = xk + j(2.0)
        cr.append(("front", x0, -3.5, x0 + j(2.5), 9.0 + j(2.0), 0.32 + j(0.03), 2.0))
    # wrinkles out of the top corners
    for sx in (-1.0, 1.0):
        a = math.radians(50.0 + j(8.0))
        x0, y0 = sx * (A - 3.0), B - 3.0
        cr.append(("top", x0, y0, x0 - sx * 9.0 * math.cos(a), y0 - 9.0 * math.sin(a), 0.3, 2.0))
    # one down each side boxing near the foot
    for side in ("side+", "side-"):
        y0 = -B + 7.0 + j(1.5)
        cr.append((side, y0, -7.5, y0 + 1.5 + j(1.0), 2.5, 0.3, 2.0))
    return cr


def _box_cushion(A, B, T, rc, rb, rt, bulge, q=None):
    """Welted box cushion cage (_slab): ~0.85 cm grid, leather piping (r 3 mm) on both
    seams, own leather UVs."""
    return _slab(A, B, 0.0, T, rc, p=_segs(2.0 * A), q=q or _segs(2.0 * B), rb=(rb, rb), rt_=(rt, rt), mb=4,
                 ms=6, mt=5, bulge=bulge, piping=("top", "bottom"), pipe_r=0.3, pipe_sides=8, uv_tile=LEATHER)


def _back_foot_estimate(L, seat_top):
    """Front-bottom seam point F of the back cushion (x = 0) resting on the seat."""
    u, nf, pc = L["u"], L["nf"], L["pc"]
    base = _add(pc, _mul(nf, 0.5 * L["bar_t"] + L["back_gap"] + L["back_t"]))
    s = 30.0
    for _ in range(8):
        F = _add(base, _mul(u, s))
        st = seat_top(F[1])
        s += (st - 0.4 - F[2]) / u[2]
    return _add(base, _mul(u, s))


def seat_cushion_md(L, back_foot_y, creases=True, seed=0):
    """Seat cushion in chair space. back_foot_y: chair-space y of the back cushion's
    foot (front seam), so the seat is squashed flat under it. Returns
    (md, top_vertex_ids)."""
    A, B, T = L["seat_A"], L["seat_B"], L["seat_t"]
    rc, rb, rt = 5.0, 1.3, 2.5
    org, axes = L["seat_origin"], L["seat_axes"]
    ct, st = math.cos(L["tilt"]), math.sin(L["tilt"])
    yb = (back_foot_y - org[1]) * ct - (L["z_sp"](back_foot_y) + T - org[2]) * st
    xs, ys = 2.5, 4.0

    def extra(x, y, z):
        hz = _smooth((z - 0.3 * T) / (0.6 * T))
        if hz <= 0.0:
            return (0.0, 0.0, 0.0)
        dz = -0.9 * math.exp(-((x - xs) / 13.0) ** 2 - ((y - ys) / 11.0) ** 2)            # sat in
        dz -= 0.35 * max(0.0, 1.0 - (x / (A - rc)) ** 2) ** 2 * _smooth((-y - (B - 9.0)) / 9.0)   # front sags
        # under the back cushion's foot the dome is pressed out, 7 mm below the top seam,
        # rising again over the 5 cm in front of it
        under = _smooth((y - (yb - 5.0)) / 5.0) * (1.0 - _smooth((abs(x) - (A - 5.0)) / 4.0))
        dz -= under * (0.7 + shape.dome(x, y))
        return (0.0, 0.0, dz * hz)

    shape = _CushionShape(A, B, T, rc, rb, rt, crown=2.8, crown_b=0.0, pin=1.3,
                          creases=_seat_creases(A, B, yb, seed) if creases else (), extra=extra)
    md = _box_cushion(A, B, T, rc, rb, rt, 0.9)
    md.map(shape)
    top = [i for i, v in enumerate(md.v) if v[2] > T - 1.2]          # top panel, top welt
    md.map(lambda p: _xf(p, org, axes))
    return md, top


def back_cushion_md(L, seat_top_xy, foot, B, creases=True, seed=0, q=None):
    """Back cushion of height 2B in chair space, its foot seam F at `foot` (x = 0).
    seat_top_xy(x, y) -> z of the seat cushion's top there (None off the seat).
    q: cage lines up the cushion (default from the nominal back height, so the mesh
    topology does not depend on the fitted height). Returns (md, axes, origin)."""
    A, T = L["back_A"], L["back_t"]
    if q is None:
        q = _segs(1.15 * (L["height"] - L["seat_h"]))
    rc, rb, rt = 5.0, 1.3, 2.5
    beta, tilt = L["beta"], L["tilt"]
    sb, cb = math.sin(beta), math.cos(beta)
    u, nf, pc = L["u"], L["nf"], L["pc"]
    shear = T * (sb - cb * math.tan(tilt))        # the foot squares up onto the seat

    def extra(x, y, z):
        d = shear * (1.0 - z / T) * (1.0 - _smooth((y + B) / 10.0))
        hz = _smooth((z - 0.3 * T) / (0.6 * T))
        lum = -0.45 * hz * math.exp(-(x / 16.0) ** 2 - ((y + B - 14.0) / 8.0) ** 2)     # where a back rests
        return (0.0, d * cb, d * sb + lum)

    # the foot seam is barely pulled in (pin_y0): the cushion's weight keeps it on the seat
    shape = _CushionShape(A, B, T, rc, rb, rt, crown=3.5, crown_b=1.2, pin=1.3,
                          creases=_back_creases(A, B, seed) if creases else (), extra=extra, pin_y0=0.4)
    md = _box_cushion(A, B, T, rc, rb, rt, 0.9, q=q)
    orig = list(md.v)
    md.map(shape)
    gam = math.radians(0.5) * (1.0 if seed % 2 == 0 else -1.0)      # sits a hair askew
    cg, sg = math.cos(gam), math.sin(gam)
    axes = ((1.0, 0.0, 0.0), u, nf)
    org = _add(_sub(foot, _mul(nf, T)), _mul(u, B))
    org = (org[0] + 0.2 * (1.0 if seed % 2 == 0 else -1.0), org[1], org[2])
    half_w = 0.5 * L["bar_w"]
    rails = [L["lumbar_rail"], L["top_rail"]]
    e_top = _add(_add(L["top_rail"], _mul(u, half_w)), _mul(nf, 0.5 * L["bar_t"]))
    out = []
    for p0, p in zip(orig, md.v):
        x, y, z = p
        q = _xf((x * cg - y * sg, x * sg + y * cg, z), org, axes)
        # back face flattened against the lumbar and top rails
        wl = 1.0 - _smooth((p0[2] - 1.5) / 2.0)
        if wl > 0.0:
            for c in rails:
                d = _dot(_sub(q, pc), nf) - 0.5 * L["bar_t"]
                if d >= 0.6:
                    break
                wb = 1.0 - _smooth((abs(_dot(_sub(q, c), u)) - half_w) / 1.2)
                if wb > 0.0:
                    q = _add(q, _mul(nf, (_smax(d, 0.0, 0.12) - d) * wb * wl))
        # the top curls back a little over the top rail
        s_top = _dot(_sub(q, e_top), u)
        if s_top > 0.0:
            q = _sub(q, _mul(nf, 0.6 * min(1.2, s_top / 8.0) ** 2))
        # the foot settles onto the seat cushion: squashed flat on it, pressed 1-2 mm in
        if p0[1] < -B + 9.0:
            st_ = seat_top_xy(q[0], q[1])
            if st_ is not None:
                h = q[2] - st_
                if h < 2.0:
                    q = (q[0], q[1], st_ + _smax(h, -0.12, 0.15))
        out.append(q)
    md.v = out
    return md, axes, org


def lounge_chair_parts(width=70.0, depth=78.0, height=72.0, seat_h=38.0, arm_h=56.0, bar_w=4.0, bar_t=1.0,
                       seat_t=12.0, back_t=10.0, back_angle=100.0, seat_tilt=4.0, straps=4, creases=True,
                       seed=0):
    """Every part of the chair as pure-Python meshes (chair space, cm). Returns a list
    of Part (frame, glides, straps, seat cushion, back cushion)."""
    L = lounge_chair_layout(width, depth, height, seat_h, arm_h, bar_w, bar_t, seat_t, back_t, back_angle,
                            seat_tilt)
    parts = [Part("LoungeChair_Frame", frame_md(L), "metal_steel", STEEL, "uv"),
             Part("LoungeChair_Glides", glides_md(L), "rubber", RUBBER, "box", smooth=1)]
    if straps:
        parts.append(Part("LoungeChair_SeatStraps", straps_md(L, straps), "leather", LEATHER, "uv"))

    # the back cushion's foot, from the plain seat top (squashed 7 mm below the top seam there)
    ct = math.cos(L["tilt"])
    foot0 = _back_foot_estimate(L, lambda y: L["z_sp"](y) + L["seat_t"] * ct - 0.7)
    seat, top_ids = seat_cushion_md(L, foot0[1], creases, seed)
    grid = _Grid2(0, 1, 1.0).add([seat.v[i] for i in top_ids])

    def seat_top_xy(x, y, rad=0.9):
        pts = grid.near(x, y, rad) or grid.near(x, y, 2.0 * rad)
        return max(p[2] for p in pts) if pts else None

    def seat_top_y(y):
        z = seat_top_xy(0.0, y)
        return z if z is not None else L["z_sp"](y) + L["seat_t"] * ct

    foot = _back_foot_estimate(L, seat_top_y)
    cb = math.cos(L["beta"])
    B = max(5.0, 0.5 * (height - foot[2]) / cb)
    back, axes, org = back_cushion_md(L, seat_top_xy, foot, B, creases, seed)
    B += (height - max(v[2] for v in back.v)) / (2.0 * cb)            # land the top on `height`
    back, axes, org = back_cushion_md(L, seat_top_xy, foot, B, creases, seed)

    parts.append(Part("LoungeChair_SeatCushion", seat, "leather", LEATHER, "soft", axes=L["seat_axes"],
                      origin=L["seat_origin"], noise=LEATHER_NOISE, seed=41 + seed))
    parts.append(Part("LoungeChair_BackCushion", back, "leather", LEATHER, "soft", axes=axes, origin=org,
                      noise=LEATHER_NOISE, seed=42 + seed))
    return parts


# ===================================================================== 3ds Max
def _emit(p):
    if p.mode == "uv":
        node = fl._build(p.md, p.name, p.tile)
        if p.smooth:
            kit.soften(node, None, p.smooth)
        return kit.part(node, p.mat, None, None)
    if p.mode == "box":
        return fl._hard(p.md, p.name, p.mat, p.tile, p.smooth)
    return fl._soft_framed(p.md, p.name, p.mat, p.noise, p.seed, p.axes, p.origin, tile=p.tile, own_uv=True,
                           smooth=p.smooth)


def build_lounge_chair(width=70.0, depth=78.0, height=72.0, seat_h=38.0, arm_h=56.0, bar_w=4.0, bar_t=1.0,
                       seat_t=12.0, back_t=10.0, back_angle=100.0, seat_tilt=4.0, straps=4, creases=True,
                       seed=0):
    """Lounge chair W width x D depth x H height (defaults 70 x 78 x 72, seat 38, arms
    56): satin-steel flat-bar frame, black leather seat and back cushions (see the
    module docstring). Front faces -Y, base on z = 0, centred on the footprint."""
    parts = lounge_chair_parts(width, depth, height, seat_h, arm_h, bar_w, bar_t, seat_t, back_t, back_angle,
                               seat_tilt, straps, creases, seed)
    return kit.group("LoungeChair", [_emit(p) for p in parts])


def preview():
    """Build one chair at the origin (run inside 3ds Max)."""
    return build_lounge_chair()
