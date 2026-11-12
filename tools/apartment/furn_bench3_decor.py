"""Wall tapestry, flowering tree, velvet pouf and knitted lounge chair for the MatForge
benchmark-3 living room (quiet luxury: cream boucle, green onyx, walnut, fluted oak,
alabaster; V-Ray in 3ds Max 2026 through pymxs). Original, generic designs.

Every piece is built round its own origin (kit.py conventions): centimetres, Z up, FRONT
facing -Y at rotation 0; every visible node goes through kit.part(...) and the piece comes
back as kit.group(...).

  build_tapestry(width=300, height=230, seed=0)
      hand-tufted wool wall tapestry width x height x 2.5 cm, hung flat: origin at its
      bottom centre, the back flat on y = 0 (the wall face), the face towards -Y;
      x -W/2 .. W/2, z 0 .. H, y about -3.2 .. 0. The outline is a soft rounded rectangle
      (each corner its own 6.5-9.5 cm radius) whose edges wave gently in and out (three
      periodic waves round the perimeter, calmer along the hanging top), the bottom hem
      sagging and the sides drawn in a little. The face undulates a few mm (soft vertical
      ripples of the hanging textile dying out under the top edge, over a fine tufting fbm).
      The edge is rolled: a 1.4 cm roll (its radius wavering +-4-9 %) from the flat back
      round the outside to a crest 3 mm proud of the face, easing back into it over 2.2 cm.
      Nodes: Tapestry_Face ("tapestry", in bands of at most NODE_FACES polygons, own 0-1
      UVs: the artwork photo once over the whole face inside the roll's crest, planar,
      u left -> right and v bottom -> top as seen from the front, unmirrored) and
      Tapestry_Edge ("tapestry" as well: the roll and the back on the same planar UVs
      clamped to the art's border, so the roll continues the pile beside it). No
      TurboSmooth (a 4 cm cage, smooth-shaded).
  build_flowering_tree(seed=0)
      yellow-flowering tree 145-155 tall with a loose, lopsided crown 82-98 cm across (mean
      of its two extents) in a 42 x 38 spun-brass pot ("metal_brass": a low 22 x 1.6 cm
      foot disc, a base rounding into a 4 mm wall that flares 4 cm out to a rolled bead
      rim) holding an irregular soil slab ("soil") 4.5 cm under the rim. A thin twisting
      trunk ("stem", 3.4-3.8 cm, flared at the soil, wound round by a helix, spiralling bark
      ridges) splits 18-48 cm above the rim into 3-5 main branches with secondaries and
      twigs, with 1-3 low branches off the trunk under the split; 130-170 blossom cards
      ("blossom_card", 14-20 cm square, the whole photo on 0-1 UVs) hang from the twigs by
      the sprig's cut end (BLOSSOM_CUT). Origin: the pot's centre on the floor.
  build_velvet_pouf(seed=0)
      slate-blue velvet pouf ("slate_velvet") 50 x 42: a 2.6 cm rounded bottom edge, the
      sides bulging 1.1 cm at mid height, a 1 cm self welt round the top seam and a top
      domed 2.2-2.7 cm. Seeded: slightly out of round, the welt line wavering a few mm,
      7-10 soft gathers under the welt, the dome's peak up to 1 cm off centre. Body with own
      UVs (VELVET cm per unit, the side band's seam at the back), welt box-mapped; both
      TurboSmoothed once. Origin: the centre of its base.
  build_knit_lounge_chair(seed=0)
      low lounge chair 80 x 85 x 75, seat 38: one organic shell under a knitted striped
      cover ("knit_stripe") - a squircle tub whose rim runs from a 75 cm back over 57 cm
      arms down to a 35.5 cm roll under the seat's front edge, its bottom rounded and tucked
      in over a black swivel base ("metal_black": 52 cm floor disc, 6.4 cm column, 26 cm
      plate under the shell at 14 cm) - and a plump knit seat cushion tucked into it
      (crowned, a sat-in hollow, a soft knit ripple). Own UVs at KNIT cm per unit with the
      stripes running round the chair: U round it (the seam up the back centre), V along
      the section (true length from 30 cm up the outer face, so the stripes are level all
      round the outside and follow the rim over the top); the cushion's top planar (stripes
      across the seat), its side band wrapped. Shell and cushion TurboSmoothed once.

Pure generators (no Max): tapestry_layout, tapestry_outline, tapestry_relief,
tapestry_section, tapestry_md, tapestry_parts; brass_pot_profile, brass_pot_md, pot_soil_md,
blossom_card_point, blossom_card_md, flowering_tree_geometry, flowering_tree_parts;
pouf_layout, pouf_profile, pouf_body_md, pouf_welt_md, velvet_pouf_parts; chair_layout,
chair_meridian, chair_inner_rho, chair_shell_md, chair_cushion_md, swivel_base_profile,
knit_chair_parts. A part is a (name, material key, furn_living._MD, tile cm, TurboSmooth
iterations) tuple: tile None - the cage carries a whole photo on 0-1 UVs (kept: kit.part
maptype None, no smoothing); every face carrying UVs - own UVs at `tile` cm per unit
(maptype None); otherwise box-mapped at `tile`. Tested off-Max in
tests/test_bench3_decor_geom.py; the build_* wrappers only turn the cages into nodes.

The scene must map the keys declared here - "tapestry" (one artwork photo over 0-1: no
tiling, no stochastic anti-tiling), "blossom_card" (the cut-out sprig photo with its
opacity), "knit_stripe" (stripes along U, KNIT = 40 cm per repeat) and "slate_velvet"
(VELVET = 40 cm) - and keep the UVs of maptype-None nodes. Hang the tapestry with
kit.place(group, x, wall_face_y, bottom_z, rot): its back lies on the wall face.
"""
import math
import random

import kit
import furn_living as fl
from furn_living import (_MD, _add, _bez, _cross, _dot, _fillet2d, _mul, _norm, _revolve_md, _rot_axis,
                         _smooth, _sub, _tube_md)

# Benchmark-3 keys: kit.MAT_KEYS predates them, so they are declared here at
# import (runtime only, kit.py is not edited); the scene maps them to MatForge
# materials.
kit.MAT_KEYS.setdefault("tapestry", "hand-tufted wool tapestry artwork: one photo over the face's 0-1 UVs")
kit.MAT_KEYS.setdefault("blossom_card", "yellow-flowering branch-tip cut-out cards, the whole photo on 0-1 UVs")
kit.MAT_KEYS.setdefault("slate_velvet", "slate-blue velvet")
kit.MAT_KEYS.setdefault("knit_stripe", "chunky grey / charcoal striped knit, the stripes along U")

TWO_PI = 2.0 * math.pi
BRASS = 25.0
SOIL = 30.0
STEM = 20.0
METAL = 25.0
VELVET = 40.0       # cm per UV unit on the velvet
KNIT = 40.0         # cm per UV unit on the striped knit
NODE_FACES = 1800   # polygons per own-UV node: keeps each MAXScript literal under ~300 KB


# ================================================================== helpers
def _xf(p, o, axes):
    """Local point -> parent space, for a frame with origin o and axes (X, Y, Z)."""
    X, Y, Z = axes
    return (o[0] + X[0] * p[0] + Y[0] * p[1] + Z[0] * p[2],
            o[1] + X[1] * p[0] + Y[1] * p[1] + Z[1] * p[2],
            o[2] + X[2] * p[0] + Y[2] * p[1] + Z[2] * p[2])


def _perp_frame(t):
    ref = (1.0, 0.0, 0.0) if abs(t[0]) < 0.9 else (0.0, 1.0, 0.0)
    e1 = _norm(_sub(ref, _mul(t, _dot(ref, t))))
    return e1, _cross(t, e1)


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


def _periodic(vals, a):
    """Periodic Catmull-Rom interpolation of vals (values at 0, 360 / n, ... degrees) at
    the angle a (radians)."""
    n = len(vals)
    x = (math.degrees(a) % 360.0) / 360.0 * n
    i = int(math.floor(x)) % n
    t = x - math.floor(x)
    p0, p1, p2, p3 = vals[(i - 1) % n], vals[i], vals[(i + 1) % n], vals[(i + 2) % n]
    return 0.5 * (2.0 * p1 + (p2 - p0) * t + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t * t
                  + (3.0 * p1 - p0 - 3.0 * p2 + p3) * t * t * t)


def _coons_grid(md, ring, p, q, place=None):
    """Vertex grid G[i][j] (i 0..p, j 0..q) filling a closed ring of 2p + 2q vertex indices
    (corners at 0, p, p + q, 2p + q): the boundary taken from the ring, the interior points
    by transfinite (Coons) interpolation of it, each passed through place(point, u, v)
    when given. Quads (G[i][j], G[i+1][j], G[i+1][j+1], G[i][j+1]) wind like the ring."""
    n = len(ring)
    if n != 2 * (p + q):
        raise ValueError("ring of %d points is not 2 (%d + %d)" % (n, p, q))
    G = [[None] * (q + 1) for _ in range(p + 1)]
    for i in range(p + 1):
        G[i][0] = ring[i % n]
    for j in range(q + 1):
        G[p][j] = ring[(p + j) % n]
    for i in range(p + 1):
        G[p - i][q] = ring[(p + q + i) % n]
    for j in range(q + 1):
        G[0][q - j] = ring[(2 * p + q + j) % n]
    V = md.v
    P00, P10, P01, P11 = V[G[0][0]], V[G[p][0]], V[G[0][q]], V[G[p][q]]
    for i in range(1, p):
        u = i / float(p)
        for j in range(1, q):
            v = j / float(q)
            c0, c1, d0, d1 = V[G[i][0]], V[G[i][q]], V[G[0][j]], V[G[p][j]]
            pt = tuple((1.0 - v) * c0[a] + v * c1[a] + (1.0 - u) * d0[a] + u * d1[a]
                       - ((1.0 - u) * (1.0 - v) * P00[a] + u * (1.0 - v) * P10[a]
                          + (1.0 - u) * v * P01[a] + u * v * P11[a]) for a in range(3))
            G[i][j] = md.add(place(pt, u, v) if place else pt)
    return G


def _quad(md, idx, uv=None):
    """Append a face as given (no dedupe), with its corner UVs or None."""
    md.f.append(tuple(idx))
    md.fuv.append(tuple(uv) if uv is not None else None)


def _submd(md, faces):
    """A new cage holding the given faces (indices into md.f) of md, with their UVs."""
    out = _MD()
    remap = {}
    for fi in faces:
        idx = []
        for i in md.f[fi]:
            if i not in remap:
                remap[i] = out.add(md.v[i])
            idx.append(remap[i])
        out.f.append(tuple(idx))
        out.fuv.append(md.fuv[fi] if fi < len(md.fuv) else None)
    return out


def _bands(md, faces, max_faces=NODE_FACES, axis=2):
    """The faces split into the fewest bands along axis (by face centroid, equal counts)
    holding at most max_faces each, as separate cages."""
    if not faces:
        return []
    nb = max(1, -(-len(faces) // max_faces))
    cen = {fi: sum(md.v[i][axis] for i in md.f[fi]) / len(md.f[fi]) for fi in faces}
    order = sorted(faces, key=lambda fi: cen[fi])
    size = -(-len(order) // nb)
    return [_submd(md, order[k:k + size]) for k in range(0, len(order), size)]


def _merge(mds):
    out = _MD()
    for m in mds:
        out.merge(m)
    return out


def _nodes(parts):
    """Max nodes for (name, mat, md, tile, smooth) parts. tile None: a cage carrying the
    whole photo on 0-1 UVs (cards, the tapestry face) - kept, no smoothing; every face with
    UVs: own UVs at `tile` cm per unit (kit.part maptype None), TurboSmooth `smooth`; else
    box-mapped at `tile` (furn_living._hard)."""
    out = []
    for name, mat, md, tile, smooth in parts:
        if tile is None:
            out.append(kit.part(fl._build(md, name, 1.0), mat, None, None))
        elif md.fuv and len(md.fuv) == len(md.f) and all(u is not None for u in md.fuv):
            node = fl._build(md, name, tile)
            if smooth:
                kit.soften(node, None, smooth)
            out.append(kit.part(node, mat, None, None))
        else:
            out.append(fl._hard(md, name, mat, tile, smooth))
    return out


# ================================================================= tapestry
TAP_T = 2.5          # tufted panel thickness
TAP_ROLL = 1.4       # radius of the rolled edge: it stands 3 mm proud of the face
TAP_BLEND = 2.2      # the roll's crest eases down into the face over this width
TAP_STEP = 4.0       # face grid spacing
TAP_ARC = 4          # cage points on each half of a corner round
TAP_CREST = 8        # station of the roll's crest: the photo starts there


def tapestry_layout(width=300.0, height=230.0, seed=0):
    """Seeded shape parameters of the tapestry (tapestry_outline, tapestry_relief)."""
    W, H = float(width), float(height)
    if W < 40.0 or H < 40.0:
        raise ValueError("tapestry too small: %r x %r" % (width, height))
    seed = int(seed or 0)
    rng = random.Random(9001 + 7919 * seed)
    uni = rng.uniform
    p = 2 * TAP_ARC + max(2, int(round((W - 12.0) / TAP_STEP)))
    q = 2 * TAP_ARC + max(2, int(round((H - 12.0) / TAP_STEP)))
    return {"W": W, "H": H, "T": TAP_T, "seed": seed, "p": p, "q": q,
            "radii": [uni(6.5, 9.5) for _ in range(4)],                      # BL, BR, TR, TL
            "waves": [(rng.randint(5, 8), uni(0.45, 0.8), uni(0.0, TWO_PI)),
                      (rng.randint(9, 14), uni(0.2, 0.4), uni(0.0, TWO_PI)),
                      (rng.randint(15, 22), uni(0.08, 0.16), uni(0.0, TWO_PI))],
            "sag": uni(0.4, 0.9), "waist": uni(0.3, 0.7), "calm_top": 0.55,
            "roll": [(rng.randint(3, 7), uni(0.04, 0.09), uni(0.0, TWO_PI))],
            "ripples": [(uni(0.12, 0.18), uni(55.0, 85.0), uni(0.0, TWO_PI)),
                        (uni(0.06, 0.1), uni(28.0, 40.0), uni(0.0, TWO_PI))],
            "wander": (uni(4.0, 8.0), uni(120.0, 200.0), uni(0.0, TWO_PI)),
            "grain": 0.25}


def tapestry_outline(lay):
    """Closed counter-clockwise outline [(x, z)] of the tapestry seen from the front:
    2p + 2q points from the bottom-left corner's 45-degree point along the bottom (p), up
    the right side (q), along the top (p) and down the left side (q), so the corner points
    sit at 0, p, p + q and 2p + q. A rounded rectangle (each corner its own 6.5-9.5 cm
    radius) whose edges wave gently in and out along their normals (three periodic waves
    round the perimeter, calmer along the top that hangs from its batten), the bottom hem
    sagging and the sides drawn in a little at mid height; then scaled to exactly
    x -W/2 .. W/2, z 0 .. H."""
    W, H, p, q = lay["W"], lay["H"], lay["p"], lay["q"]
    A, B = 0.5 * W, 0.5 * H
    r = lay["radii"]
    cen = [(-A + r[0], -B + r[0]), (A - r[1], -B + r[1]), (A - r[2], B - r[2]), (-A + r[3], B - r[3])]
    base = [math.pi, 1.5 * math.pi, 0.0, 0.5 * math.pi]
    raw = []

    def arc(c, a):
        raw.append((cen[c][0] + r[c] * math.cos(a), cen[c][1] + r[c] * math.sin(a), math.cos(a), math.sin(a)))

    for k in range(4):
        ns = (p if k % 2 == 0 else q) - 2 * TAP_ARC
        c1, c2 = k, (k + 1) % 4
        for j in range(TAP_ARC):
            arc(c1, base[c1] + 0.25 * math.pi * (1.0 + j / float(TAP_ARC)))
        a0 = base[c1] + 0.5 * math.pi
        nx, nz = round(math.cos(a0), 12), round(math.sin(a0), 12)
        s0 = (cen[c1][0] + r[c1] * nx, cen[c1][1] + r[c1] * nz)
        s1 = (cen[c2][0] + r[c2] * math.cos(base[c2]), cen[c2][1] + r[c2] * math.sin(base[c2]))
        for j in range(ns):
            t = j / float(ns)
            raw.append((s0[0] + (s1[0] - s0[0]) * t, s0[1] + (s1[1] - s0[1]) * t, nx, nz))
        for j in range(TAP_ARC):
            arc(c2, base[c2] + 0.25 * math.pi * j / float(TAP_ARC))
    n = len(raw)
    cum = [0.0]
    for i in range(n):
        a, b = raw[i], raw[(i + 1) % n]
        cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    per = cum[-1]
    pts = []
    for i, (x, z, nx, nz) in enumerate(raw):
        d = sum(a * math.sin(TWO_PI * m * cum[i] / per + ph) for m, a, ph in lay["waves"])
        d *= 1.0 - lay["calm_top"] * _smooth((z - (B - 40.0)) / 40.0)
        d += lay["sag"] * max(0.0, -nz) * math.sin(math.pi * (x + A) / W)
        d -= lay["waist"] * abs(nx) * math.sin(math.pi * (z + B) / H)
        pts.append((x + d * nx, z + d * nz))
    xs, zs = [pt[0] for pt in pts], [pt[1] for pt in pts]
    x0, x1, z0, z1 = min(xs), max(xs), min(zs), max(zs)
    return [(-A + (x - x0) * W / (x1 - x0), (z - z0) * H / (z1 - z0)) for x, z in pts]


def tapestry_relief(lay, x, z):
    """How far (cm) the tufted face stands proud of its nominal plane at (x, z): soft
    vertical ripples of the hanging textile (wandering a little, dying out towards the top
    edge held by its batten) over a fine fbm of the hand tufting - a few mm in all."""
    amp, lam, ph = lay["wander"]
    xw = x + amp * math.sin(TWO_PI * z / lam + ph)
    env = _smooth((lay["H"] - z) / 30.0)
    r = env * sum(a * math.sin(TWO_PI * xw / L + p_) for a, L, p_ in lay["ripples"])
    return r + lay["grain"] * (2.0 * _fbm(x / 22.0, z / 22.0, 4001 + lay["seed"]) - 1.0)


def tapestry_section(R, T=TAP_T, blend=TAP_BLEND):
    """(inset, depth) stations of the edge for a roll of radius R: from the back ring
    (depth 0, where the roll leaves the flat back) round the outside (inset 0) to its crest
    (depth 2R, station TAP_CREST), then easing down into the face (depth T) over `blend`."""
    st = []
    for a in (0.0, 22.5, 45.0, 67.5, 90.0):
        t = math.radians(a)
        st.append((R * (1.0 - math.sin(t)), R * (1.0 - math.cos(t))))
    for a in (22.5, 45.0, 67.5, 90.0):
        t = math.radians(a)
        st.append((R * (1.0 - math.cos(t)), R * (1.0 + math.sin(t))))
    for t in (1.0 / 3.0, 2.0 / 3.0, 1.0):
        st.append((R + blend * t, 2.0 * R + (T - 2.0 * R) * _smooth(t)))
    return st


def tapestry_md(width=300.0, height=230.0, seed=0):
    """(md, tags, lay): the whole tapestry as one closed cage and a tag per face - 'face'
    (the front inside the roll's crest, carrying the photo's 0-1 UVs, u left -> right and
    v bottom -> top over the extent of the face) or 'edge' (the rolled edge from its crest
    round the outside to the back, and the flat back on y = 0 fanned from its centre).
    The edge roll's radius wavers +-4-9 % along the outline (seeded)."""
    lay = tapestry_layout(width, height, seed)
    H, T = lay["H"], lay["T"]
    out = tapestry_outline(lay)
    n = len(out)
    cum = [0.0]
    for i in range(n):
        cum.append(cum[-1] + math.dist(out[i], out[(i + 1) % n]))
    per = cum[-1]
    secs = []
    for i in range(n):
        a, b = out[i - 1], out[(i + 1) % n]
        tx, tz = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(tx, tz)
        R = TAP_ROLL * (1.0 + sum(am * math.sin(TWO_PI * m * cum[i] / per + ph) for m, am, ph in lay["roll"]))
        secs.append((out[i], (-tz / ln, tx / ln), tapestry_section(R, T)))
    md = _MD()
    rings = []
    for k in range(len(secs[0][2])):
        ring = []
        for o, nin, st in secs:
            s, d = st[k]
            x, z = o[0] + s * nin[0], o[1] + s * nin[1]
            d += tapestry_relief(lay, x, z) * max(0.0, min(1.0, d / T))
            ring.append(md.add((x, -d, z)))
        rings.append(ring)
    tags = []
    for k in range(len(rings) - 1):
        ra, rb = rings[k], rings[k + 1]
        for i in range(n):
            i2 = (i + 1) % n
            _quad(md, (ra[i], ra[i2], rb[i2], rb[i]))
            tags.append("face" if k >= TAP_CREST else "edge")
    p, q = lay["p"], lay["q"]
    G = _coons_grid(md, rings[-1], p, q,
                    lambda pt, u, v: (pt[0], -(T + tapestry_relief(lay, pt[0], pt[2])), pt[2]))
    for i in range(p):
        for j in range(q):
            _quad(md, (G[i][j], G[i + 1][j], G[i + 1][j + 1], G[i][j + 1]))
            tags.append("face")
    c = md.add((0.0, 0.0, 0.5 * H))
    r0 = rings[0]
    for i in range(n):
        _quad(md, (c, r0[(i + 1) % n], r0[i]))
        tags.append("edge")
    fv = {i for f, t in zip(md.f, tags) if t == "face" for i in f}
    x0, x1 = min(md.v[i][0] for i in fv), max(md.v[i][0] for i in fv)
    z0, z1 = min(md.v[i][2] for i in fv), max(md.v[i][2] for i in fv)
    # the edge (roll and back) takes the same planar UVs clamped to the art's border, so
    # the roll carries on the pile colour beside it (box-mapped, it showed a dashed band of
    # unrelated slices of the artwork round the outline)
    md.fuv = [tuple((min(1.0, max(0.0, (md.v[i][0] - x0) / (x1 - x0))),
                     min(1.0, max(0.0, (md.v[i][2] - z0) / (z1 - z0)))) for i in f) for f in md.f]
    return md, tags, lay


def tapestry_parts(width=300.0, height=230.0, seed=0):
    """[(name, mat, md, tile, smooth)]: the tufted face ("tapestry", its own 0-1 UVs, in
    bands of at most NODE_FACES polygons) and the rolled edge with the back ("tapestry"
    too, on the face's UVs clamped to the art's border). No TurboSmooth: the cage is
    dense enough."""
    md, tags, _lay = tapestry_md(width, height, seed)
    face = [i for i, t in enumerate(tags) if t == "face"]
    edge = [i for i, t in enumerate(tags) if t == "edge"]
    parts = [("Tapestry_Face", "tapestry", band, None, 0) for band in _bands(md, face)]
    parts.append(("Tapestry_Edge", "tapestry", _submd(md, edge), None, 0))
    return parts


# ===================================================================== pouf
POUF_N = 64          # cage points round the pouf (its top and bottom panels: 16 x 16 Coons patches)


def pouf_layout(diameter=50.0, height=42.0, seed=0):
    """Seeded dimensions of the velvet pouf (pouf_profile, pouf_body_md, pouf_welt_md)."""
    D, H = float(diameter), float(height)
    if D < 25.0 or H < 20.0:
        raise ValueError("pouf too small: %r x %r" % (diameter, height))
    seed = int(seed or 0)
    rng = random.Random(4243 + 7919 * seed)
    uni = rng.uniform
    ca, cr = uni(0.0, TWO_PI), uni(0.3, 1.0)
    lay = {"R": 0.5 * D, "H": H, "seed": seed, "bulge": 1.1, "rb": 2.6, "rc": 2.2, "curl": math.radians(55.0),
           "dome": uni(2.2, 2.7), "dome_c": (cr * math.cos(ca), cr * math.sin(ca)),
           "round": [(2, uni(0.003, 0.006), uni(0.0, TWO_PI)), (3, uni(0.002, 0.004), uni(0.0, TWO_PI))],
           "seam_wave": [(2, uni(0.1, 0.2), uni(0.0, TWO_PI)), (3, uni(0.05, 0.12), uni(0.0, TWO_PI))],
           "pulls": (rng.randint(7, 10), uni(0.15, 0.25), uni(0.0, TWO_PI)),
           "welt_r": 0.5, "phi0": 0.5 * math.pi}
    lay["seam_z"] = H - lay["dome"]
    return lay


def pouf_profile(lay, phi):
    """[(r, z)] stations of the pouf's side at azimuth phi, from the rim of the flat bottom
    panel (z = 0) round a 2.6 cm bottom edge, up the side bulging 1.1 cm at mid height,
    over a 2.2 cm curl to the welt seam (55 degrees round it), where the domed top panel
    starts. Seeded: the radius 0.5-1 % out of round, the seam wavering a few mm, and the
    side drawn in under the welt in 7-10 soft gathers (0.15-0.25 cm)."""
    R, rb, rc, bulge, curl = lay["R"], lay["rb"], lay["rc"], lay["bulge"], lay["curl"]
    fr = 1.0 + sum(a * math.sin(m * phi + ph) for m, a, ph in lay["round"])
    zs = lay["seam_z"] + sum(a * math.sin(m * phi + ph) for m, a, ph in lay["seam_wave"])
    zc = zs - rc * math.sin(curl)
    m, amp, ph = lay["pulls"]
    pull = amp * (0.5 + 0.5 * math.sin(m * phi + ph))
    Rs = R - bulge
    st = []
    for a in (0.0, 30.0, 60.0, 90.0):
        t = math.radians(a)
        st.append((Rs - rb + rb * math.sin(t), rb - rb * math.cos(t)))
    for k in range(1, 9):
        t = k / 8.0
        st.append((Rs + bulge * math.sin(math.pi * t), rb + (zc - rb) * t))
    for k in range(1, 4):
        a = curl * k / 3.0
        st.append((Rs - rc + rc * math.cos(a), zc + rc * math.sin(a)))
    return [(r * fr - pull * _smooth((z - (zc - 6.0)) / 6.0), z) for r, z in st]


def pouf_body_md(lay):
    """Closed velvet body: the side band (rings of POUF_N points round the profile, the
    UV seam up the back), the flat bottom panel and the domed top panel (Coons patches of
    the end rings). The top rises `dome` (2.2-2.7 cm) from the welt seam to a point up to
    1 cm off centre, as 1 - rho^3 (flat in the middle, rounding down to the seam). Own UVs
    at VELVET cm per unit: the band wrapped (U round, V up the side), the panels planar."""
    N = POUF_N
    p = N // 4
    phis = [lay["phi0"] + TWO_PI * j / N for j in range(N)]
    profs = [pouf_profile(lay, ph) for ph in phis]
    K = len(profs[0])
    md = _MD()
    rings = [[md.add((profs[j][k][0] * math.cos(phis[j]), profs[j][k][0] * math.sin(phis[j]), profs[j][k][1]))
              for j in range(N)] for k in range(K)]
    t = VELVET
    U = [TWO_PI * lay["R"] * j / N / t for j in range(N + 1)]
    V = []
    for prof in profs:
        s = [0.0]
        for a, b in zip(prof, prof[1:]):
            s.append(s[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        V.append([c / t for c in s])
    for k in range(K - 1):
        for j in range(N):
            j2 = (j + 1) % N
            _quad(md, (rings[k][j], rings[k][j2], rings[k + 1][j2], rings[k + 1][j]),
                  ((U[j], V[j][k]), (U[j + 1], V[j2][k]), (U[j + 1], V[j2][k + 1]), (U[j], V[j][k + 1])))
    seam_r = [math.hypot(md.v[i][0], md.v[i][1]) for i in rings[-1]]
    cx, cy = lay["dome_c"]

    def ring_r(th):
        x = ((th - lay["phi0"]) % TWO_PI) / TWO_PI * N
        j = int(x) % N
        f = x - math.floor(x)
        return seam_r[j] * (1.0 - f) + seam_r[(j + 1) % N] * f

    def dome(pt, u, v):
        dx, dy = pt[0] - cx, pt[1] - cy
        th = math.atan2(dy, dx)
        edge = ring_r(th) - (cx * math.cos(th) + cy * math.sin(th))
        rho = min(1.0, math.hypot(dx, dy) / edge)
        return (pt[0], pt[1], pt[2] + lay["dome"] * (1.0 - rho ** 3))

    G = _coons_grid(md, rings[-1], p, p, dome)
    for i in range(p):
        for j in range(p):
            idx = (G[i][j], G[i + 1][j], G[i + 1][j + 1], G[i][j + 1])
            _quad(md, idx, [(md.v[a][0] / t, md.v[a][1] / t) for a in idx])
    G = _coons_grid(md, rings[0], p, p)
    for i in range(p):
        for j in range(p):
            idx = (G[i][j], G[i][j + 1], G[i + 1][j + 1], G[i + 1][j])
            _quad(md, idx, [(-md.v[a][0] / t, md.v[a][1] / t) for a in idx])
    return md


def pouf_welt_md(lay, n=96, sides=8):
    """Closed self-fabric welt (1 cm cord) round the top seam: a tube on the seam line,
    its centre 0.55 of its radius out along the bisector of the side band's and the top
    panel's outward normals, so it stands about 7 mm proud of the seam."""
    curl, r_w = lay["curl"], lay["welt_r"]
    path, nrms = [], []
    for k in range(n):
        ph = lay["phi0"] + TWO_PI * k / n
        r, z = pouf_profile(lay, ph)[-1]
        sl = 3.0 * lay["dome"] / r
        ln = math.hypot(sl, 1.0)
        br, bz = math.cos(curl) + sl / ln, math.sin(curl) + 1.0 / ln
        bl = math.hypot(br, bz)
        br, bz = br / bl, bz / bl
        rr, zz = r + br * 0.55 * r_w, z + bz * 0.55 * r_w
        path.append((rr * math.cos(ph), rr * math.sin(ph), zz))
        nrms.append((br * math.cos(ph), br * math.sin(ph), bz))
    return _tube_md(path, r_w, sides, closed=True, normals=nrms)


def velvet_pouf_parts(seed=0, diameter=50.0, height=42.0):
    """[(name, mat, md, tile, smooth)] of the pouf: the body (own UVs) and the welt
    (box-mapped), both "slate_velvet", both TurboSmoothed once."""
    lay = pouf_layout(diameter, height, seed)
    return [("VelvetPouf_Body", "slate_velvet", pouf_body_md(lay), VELVET, 1),
            ("VelvetPouf_Welt", "slate_velvet", pouf_welt_md(lay), VELVET, 1)]


# =========================================================== flowering tree
POT_D, POT_H = 42.0, 38.0       # brass pot: diameter over its rolled rim, height
POT_WALL = 0.4                  # spun brass wall
POT_FOOT = (11.0, 1.6)          # the low disc it stands on: radius, height
TREE_H = (145.0, 155.0)         # the highest sprig, cm above the floor
TREE_W = (82.0, 98.0)           # crown width (mean of its x and y extents)
# the sprig's cut end in the yellow_blossom photo (u, v), measured off its
# opacity map: the lowest opaque row is v 0.154 at u 0.497 (at the assumed
# v 0.05 every sprig would have hung 1.5-2 cm off its twig); the sprig spans
# u 0.37-0.66, v 0.15-0.80
BLOSSOM_CUT = (0.497, 0.154)
BLOSSOM_US = (0.0, BLOSSOM_CUT[0], 1.0)
BLOSSOM_VS = (0.0, BLOSSOM_CUT[1], 0.35, 0.55, 0.8, 1.0)
# probes on the visible sprig: cut end, tip, the flowers' far left / right, middle
BLOSSOM_PROBES = (BLOSSOM_CUT, (0.5, 0.79), (0.38, 0.6), (0.65, 0.6), (0.5, 0.5))
CARDS_PER_NODE = 25


def brass_pot_dims(diameter=POT_D, height=POT_H):
    """Key dimensions (cm) of the brass pot: rim radius R, height H, the wall's top (rw) and
    foot (rb) radii outside, the base and inner floor heights, the soil level."""
    R, H = 0.5 * float(diameter), float(height)
    zf = POT_FOOT[1]
    return {"R": R, "H": H, "wall": POT_WALL, "rw": R - 0.45, "rb": R - 4.0, "z_base": zf,
            "z_floor": zf + POT_WALL, "foot_r": POT_FOOT[0], "soil_z": H - 4.5}


def pot_inner_r(d, z):
    """Radius of the pot's inner wall at height z (its straight, flaring part)."""
    z0, z1 = d["z_floor"], d["H"] - 1.0
    r0, r1 = d["rb"] - d["wall"], d["rw"] - d["wall"]
    return r0 + (r1 - r0) * (z - z0) / (z1 - z0)


def brass_pot_profile(diameter=POT_D, height=POT_H):
    """(r, z) section of the spun-brass pot, counter-clockwise round the material: a low
    foot disc (22 cm across, 1.6 high, recessed underside on a 6 mm ring, 3 mm rounds), the bowl's
    base rounding (3.4 cm) into a 4 mm wall that flares 4 cm out to the rim, a rolled bead
    rim 0.85 cm across, the inner wall and a 5 cm fillet into the inner floor."""
    d = brass_pot_dims(diameter, height)
    R, H, t, rw, rb, fr, zf = d["R"], d["H"], d["wall"], d["rw"], d["rb"], d["foot_r"], d["z_base"]
    pts = [(0.0, 0.3), (fr - 2.2, 0.3), (fr - 1.6, 0.0), (fr, 0.0), (fr, zf), (rb, zf),
           (rw, H - 1.0), (R, H - 0.5), (R - 0.3, H), (rw - t - 0.05, H), (rw - t, H - 1.0),
           (rb - t, zf + t), (0.0, zf + t)]
    rad = [0.0, 0.25, 0.2, 0.3, 0.3, 3.4, 0.3, 0.4, 0.4, 0.2, 0.0, 5.0, 0.0]
    return _fillet2d(pts, rad, step=math.radians(15.0))


def brass_pot_md(diameter=POT_D, height=POT_H):
    return _revolve_md(brass_pot_profile(diameter, height), 56)


def pot_soil_md(d, mounds=(), seed=0, depth=3.0, n_ang=60, n_rad=10):
    """Closed slab of potting soil at d["soil_z"]: an irregular top (two octaves of clods)
    heaped by mounds [(x, y, height, radius)], its rim 1.5 mm into the flaring pot wall at
    every height (the side tapers with the wall), a flat underside `depth` lower."""
    zt = d["soil_z"]
    zb = zt - depth
    r_top, r_bot = pot_inner_r(d, zt) + 0.15, pot_inner_r(d, zb) + 0.15

    def top(x, y):
        z = zt + 0.4 * (_fbm(x / 5.0, y / 5.0, seed) - 0.5) + 0.15 * (_vnoise(x / 1.6, y / 1.6, seed + 7) - 0.5)
        for mx, my, mh, mr in mounds:
            z += mh * math.exp(-((x - mx) ** 2 + (y - my) ** 2) / (mr * mr))
        return z

    md = _MD()
    ct = md.add((0.0, 0.0, top(0.0, 0.0)))
    radii = [r_top * (k / float(n_rad)) ** 0.9 for k in range(1, n_rad)] + [r_top - 0.3, r_top]
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
    bot = [md.add((r_bot * math.cos(TWO_PI * j / n_ang), r_bot * math.sin(TWO_PI * j / n_ang), zb))
           for j in range(n_ang)]
    cb = md.add((0.0, 0.0, zb))
    for j in range(n_ang):
        j2 = (j + 1) % n_ang
        md.face((ct, rings[0][j], rings[0][j2]))
        for k in range(len(rings) - 1):
            md.face((rings[k][j], rings[k + 1][j], rings[k + 1][j2], rings[k][j2]))
        md.face((edge[j], side[j], side[j2], edge[j2]))
        md.face((side[j], bot[j], bot[j2], side[j2]))
        md.face((cb, bot[j2], bot[j]))
    return md


def blossom_card_point(u, v, size, droop=0.0, fold=0.0, twist=0.0):
    """Card-local point of photo (u, v) on a size x size card: origin on the sprig's cut
    end BLOSSOM_CUT, +Y up the sprig (V), +X = +U, +Z the photo's front (X x Y = Z, so the
    photo reads unmirrored from +Z). The sprig arcs towards -Z by `droop` radians over the
    card (constant curvature from the cut end), the card turns by up to `twist` radians
    about it towards the tip, and both halves rise to `fold` cm at the side edges (a V
    along the sprig, flat over the bare stalk)."""
    cu, cv = BLOSSOM_CUT
    x = (u - cu) * size
    s = (v - cv) * size
    S = (1.0 - cv) * size
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


def blossom_card_md(size, droop=0.0, fold=0.0, twist=0.0):
    """One blossom card in its own frame (blossom_card_point): a quad grid over
    BLOSSOM_US x BLOSSOM_VS, every corner carrying its photo (u, v) - the whole 0-1 square.
    The grid line u = 0.5 is the fold along the sprig, the row v = 0.05 holds the cut end."""
    md = _MD()
    rows = [[md.add(blossom_card_point(u, v, size, droop, fold, twist)) for u in BLOSSOM_US] for v in BLOSSOM_VS]
    for j in range(len(BLOSSOM_VS) - 1):
        for i in range(len(BLOSSOM_US) - 1):
            md.face((rows[j][i], rows[j][i + 1], rows[j + 1][i + 1], rows[j + 1][i]),
                    ((BLOSSOM_US[i], BLOSSOM_VS[j]), (BLOSSOM_US[i + 1], BLOSSOM_VS[j]),
                     (BLOSSOM_US[i + 1], BLOSSOM_VS[j + 1]), (BLOSSOM_US[i], BLOSSOM_VS[j + 1])))
    return md


class _PointGrid(object):
    """Bucketed 3-D points: distance to the nearest one (card spacing)."""

    def __init__(self, cell=8.0):
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


class _Branch(object):
    """A branch centre line with radii r0 (base) -> r1 (tip)."""

    def __init__(self, level, path, r0, r1, az, sides, root, expo=0.8):
        self.level, self.path, self.az, self.sides, self.root = level, list(path), az, sides, root
        self.r0, self.r1, self.expo = float(r0), float(r1), expo
        self.group = None           # set on a low branch off the trunk and everything it carries
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
    """Branch centre line from start in n equal steps, leaning lean0 -> lean1 off vertical
    towards azimuth az (over 90 degrees: below the horizontal), wandering sideways by a sine
    (amplitude, cycles, phase)."""
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


def _clamp_down(d, fallback, zmin=-0.45):
    """d, but pointing no further down than z = zmin (unit vectors)."""
    if d[2] >= zmin:
        return d
    h = math.hypot(d[0], d[1])
    hx, hy = (d[0] / h, d[1] / h) if h > 1e-6 else (fallback[0], fallback[1])
    hl = math.hypot(hx, hy) or 1.0
    c = math.sqrt(1.0 - zmin * zmin)
    return (hx / hl * c, hy / hl * c, zmin)


def _gnarl_md(path, radii, sides, mod=None, caps=True):
    """furn_living._tube_md (parallel-transport frames, same winding, capped) with the
    radius of ring i at frame angle a scaled by mod(i, a): twisting bark ridges."""
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


def _tree_trunk(base, top, r_base, r_top, soil_z, rng, n=24):
    """Centre line, radii and bark of the thin twisting trunk from `base` (in the soil) to
    the split point `top`: a cubic leaving the soil and reaching the split upright, wound
    round by a helix (2.5-4.5 cm, 0.8-1.3 turns, dying out at both ends), flared 30 % where
    it leaves the soil, closed by a low dome 2.3 cm above the split; three bark ridges
    spiralling round it."""
    h = top[2] - base[2]
    c1 = (base[0], base[1], base[2] + h / 3.0)
    c2 = (top[0], top[1], top[2] - h / 3.0)
    amp = rng.uniform(2.5, 4.5)
    turns = rng.uniform(0.8, 1.3) * (1.0 if rng.random() < 0.5 else -1.0)
    ph = rng.uniform(0.0, TWO_PI)
    path, radii = [], []
    for k in range(n + 1):
        t = k / float(n)
        p = _bez(base, c1, c2, top, t)
        env = math.sin(math.pi * t) ** 1.5
        a = TWO_PI * turns * t + ph
        path.append((p[0] + env * amp * math.cos(a), p[1] + env * amp * math.sin(a), p[2]))
        radii.append((r_base + (r_top - r_base) * t ** 0.8) * (1.0 + 0.3 * math.exp(-max(0.0, p[2] - soil_z) / 3.0)))
    for dz, f in ((1.0, 0.85), (1.8, 0.6), (2.3, 0.3)):
        path.append((top[0], top[1], top[2] + dz))
        radii.append(r_top * f)
    cum = [0.0]
    for a, b in zip(path, path[1:]):
        cum.append(cum[-1] + math.dist(a, b))
    q1, q2 = rng.uniform(0.0, TWO_PI), rng.uniform(0.0, TWO_PI)
    tw = rng.uniform(0.18, 0.3) * (1.0 if turns > 0.0 else -1.0)

    def mod(i, a):
        return 1.0 + 0.06 * math.sin(3.0 * a + tw * cum[i] + q1) + 0.03 * math.sin(5.0 * a - 0.6 * tw * cum[i] + q2)
    return path, radii, mod


def flowering_tree_geometry(seed=0):
    """Pure-Python flowering tree in its brass pot.

    The crown's skeleton is grown round the split point first: 3-5 main branches leaning
    20-38 degrees out (turning up towards their tips, 48-64 cm; one leads, 10 degrees
    steeper and 12 % longer, so the crown is loose and lopsided, not a lollipop), 3-5
    secondary branches on each from low down (50-85 degrees, longest near the base) with
    2-3 twigs each (40-100 degrees: some droop) and 1-2 twigs off each main's end, plus 1-3
    low branches (with their twigs) off the trunk 14-30 cm under the split, so the crown
    reaches down. 130-170 blossom cards are shared out over the flowering parts (twigs from
    0.15 of their length, secondaries and low branches from 0.3, mains from 0.55), one on
    every tip continuing it, the rest leaving their twig at 25-60 degrees in a golden-angle
    spiral, pushed outwards, a few hanging (never more than 27 degrees below the
    horizontal), facing up and out within +-45 degrees; each keeps the best of three draws
    (most room to the cards already placed). The skeleton is then scaled about the split
    point (directions, radii and cards kept) so the crown is target_w (82-98 cm) across,
    and the split raised or lowered so the highest sprig reaches target_h (145-155 cm), the
    split staying 18-48 cm above the rim (and the low branches 12 cm or more above the
    soil); the thin trunk leans to keep the crown over the pot, and each low branch (with
    everything on it) is moved onto the trunk's wandering centre line at its height.

    Returns a dict: trunk (_MD: trunk + mains, closed), twigs (one _MD per main: its
    secondaries, the low branches given to it and all their twigs, closed), cards (one _MD
    per card, own 0-1 UVs), specs (per card: size, attach point, level, terminal, axes,
    probes), soil, branches (world centre lines [{level, path, radii, root, low}], the trunk
    first), probes, height, crown (x, y extents), crown_centre, scale, split, target_h,
    target_w, n_cards, n_main, pot, trunk_base."""
    seed = int(seed or 0)
    rng = random.Random(6007 + 7919 * seed)

    def uni(a, b):
        return a + (b - a) * rng.random()

    def sign():
        return 1.0 if rng.random() < 0.5 else -1.0

    d = brass_pot_dims()
    target_h, target_w = uni(*TREE_H), uni(*TREE_W)

    # ---- skeleton round the split point (0, 0, 0), unscaled
    n_main = 3 + int(rng.random() * 3)
    az0 = uni(0.0, TWO_PI)
    lead = int(rng.random() * n_main)
    mains = []
    for k in range(n_main):
        az = az0 + TWO_PI * k / n_main + uni(-0.4, 0.4)
        lean = math.radians(uni(20.0, 38.0) - (10.0 if k == lead else 0.0))
        path = _bpath((0.0, 0.0, -2.0), uni(48.0, 64.0) * (1.12 if k == lead else 1.0), az, lean,
                      lean * uni(0.5, 0.75), (uni(0.05, 0.12), uni(1.0, 2.0), uni(0.0, TWO_PI)), 16)
        mains.append(_Branch(1, path, uni(1.0, 1.12), uni(0.26, 0.32), az, 10, k))
    branches = list(mains)

    def twig(parent, f, az, lmin, lmax, rmax):
        tl = math.radians(uni(40.0, 100.0))
        path = _bpath(parent.at(f), uni(lmin, lmax), az, tl, tl + math.radians(uni(-15.0, 12.0)),
                      (uni(0.02, 0.06), uni(0.8, 1.6), uni(0.0, TWO_PI)), 6)
        tw = _Branch(3, path, min(rmax, 0.7 * parent.radius_at(f)), 0.07, az, 5, parent.root)
        tw.group = parent.group
        return tw

    for m in mains:
        side = sign()
        for f in _spread(3 + int(rng.random() * 3), 0.12, 0.9, rng):
            az = m.az + side * uni(0.5, 1.5)
            side = -side
            lean = math.radians(uni(50.0, 85.0))
            path = _bpath(m.at(f), uni(16.0, 30.0) * (1.15 - 0.5 * f), az, lean, lean * uni(0.55, 0.85),
                          (uni(0.03, 0.08), uni(1.0, 2.0), uni(0.0, TWO_PI)), 9)
            sec = _Branch(2, path, min(0.55, 0.62 * m.radius_at(f)), 0.12, az, 7, m.root)
            branches.append(sec)
            tside = sign()
            for g in _spread(2 + int(rng.random() * 2.0), 0.3, 0.95, rng):
                branches.append(twig(sec, g, az + tside * uni(0.5, 1.3), 7.0, 13.0, 0.2))
                tside = -tside
        for g in _spread(1 + int(rng.random() * 1.8), 0.8, 0.96, rng):
            branches.append(twig(m, g, m.az + sign() * uni(0.6, 1.4), 8.0, 14.0, 0.22))
    # 1-3 low branches off the trunk 14-30 cm under the split, so the crown reaches down
    n_low = 1 + int(rng.random() * 2.5)
    lows = []
    for kk in range(n_low):
        az = az0 + TWO_PI * (kk + 0.5) / n_low + uni(-0.5, 0.5)
        lean = math.radians(uni(55.0, 75.0))
        path = _bpath((0.0, 0.0, -uni(14.0, 30.0)), uni(22.0, 34.0), az, lean, lean * uni(0.55, 0.8),
                      (uni(0.03, 0.08), uni(1.0, 2.0), uni(0.0, TWO_PI)), 10)
        low = _Branch(2, path, uni(0.55, 0.68), 0.12, az, 8, kk % n_main)
        low.group = kk
        lows.append(low)
        branches.append(low)
        tside = sign()
        for g in _spread(2 + int(rng.random() * 2.0), 0.3, 0.95, rng):
            branches.append(twig(low, g, az + tside * uni(0.5, 1.3), 7.0, 13.0, 0.2))
            tside = -tside

    # ---- cards: one on every tip, the rest shared out by the length of the flowering parts
    leafy = [(b, {1: 0.55, 2: 0.3, 3: 0.15}[b.level]) for b in branches]
    n_cards = int(uni(130.0, 171.0))
    spans = [(1.0 - f0) * b.length() for b, f0 in leafy]
    rest = n_cards - len(leafy)
    if rest < 0:
        raise ValueError("more branch tips than blossom cards")
    quota = [rest * s / sum(spans) for s in spans]
    counts = [1 + int(qq) for qq in quota]
    order = sorted(range(len(leafy)), key=lambda i: -(quota[i] - int(quota[i])))
    for i in order[:n_cards - sum(counts)]:
        counts[i] += 1
    golden = math.radians(137.5)
    grid = _PointGrid(8.0)
    cards = []
    for (b, f0), cnt in zip(leafy, counts):
        psi = uni(0.0, TWO_PI)
        fs = [1.0] + [f0 + (1.0 - f0) * 0.93 * (j + 0.5 + uni(-0.3, 0.3)) / (cnt - 1) for j in range(cnt - 1)]
        for j, f in enumerate(fs):
            terminal = j == 0
            size = uni(14.0, 20.0)
            droop, fold = math.radians(uni(6.0, 26.0)), uni(0.3, 1.2)
            twist = math.radians(uni(5.0, 20.0)) * sign()
            local = [blossom_card_point(u, v, size, droop, fold, twist) for u, v in BLOSSOM_PROBES]
            A = b.at(f)
            t = b.tangent(f)
            e1, e2 = _perp_frame(t)
            hr = math.hypot(A[0], A[1])
            out = (A[0] / hr, A[1] / hr, 0.0) if hr > 1.0 else (math.cos(b.az), math.sin(b.az), 0.0)
            psi += golden + uni(-0.3, 0.3)
            best = None
            for _c in range(3):
                if terminal:
                    jit = _add(_mul(e1, uni(-0.25, 0.25)), _mul(e2, uni(-0.25, 0.25)))
                    dd = _norm(_add(_add(t, jit), _mul(out, 0.15)))
                else:
                    ps = psi + uni(-0.6, 0.6)
                    gam = math.radians(uni(25.0, 60.0))
                    radial = _add(_mul(e1, math.cos(ps)), _mul(e2, math.sin(ps)))
                    dd = _add(_mul(t, math.cos(gam)), _mul(radial, math.sin(gam)))
                    dd = _norm(_add(_add(dd, _mul(out, 0.35)), (0.0, 0.0, uni(-0.3, 0.25))))
                dd = _clamp_down(dd, out)
                up_p = _sub((0.0, 0.0, 1.0), _mul(dd, dd[2]))
                out_p = _sub(out, _mul(dd, _dot(out, dd)))
                pref = _add(_mul(up_p, 0.75), _mul(out_p, 0.45))
                pref = _norm(pref) if _dot(pref, pref) > 1e-8 else _perp_frame(dd)[0]
                nn = _norm(_rot_axis(pref, dd, math.radians(uni(-45.0, 45.0))))
                axes = (_cross(dd, nn), dd, nn)
                pts = [_xf(pp, A, axes) for pp in local]
                score = min(grid.nearest(pp, 8.0) for pp in pts[1:])
                if best is None or score > best[0]:
                    best = (score, axes, pts)
            grid.add(best[2][1:])
            cards.append({"branch": b, "A": A, "axes": best[1], "size": size, "droop": droop, "fold": fold,
                          "twist": twist, "local": local, "terminal": terminal})

    # ---- one skeleton scale about the split point: the crown's width on target
    offs = [(c["A"], [_xf(pp, (0.0, 0.0, 0.0), c["axes"]) for pp in c["local"]]) for c in cards]

    def extents(k):
        xs = [k * A[0] + o[0] for A, os in offs for o in os]
        ys = [k * A[1] + o[1] for A, os in offs for o in os]
        return min(xs), max(xs), min(ys), max(ys)

    def width(k):
        x0, x1, y0, y1 = extents(k)
        return 0.5 * ((x1 - x0) + (y1 - y0))

    lo, hi = 0.7, 1.5
    if width(lo) >= target_w:
        k = lo
    elif width(hi) <= target_w:
        k = hi
    else:
        for _ in range(30):
            mid = 0.5 * (lo + hi)
            if width(mid) < target_w:
                lo = mid
            else:
                hi = mid
        k = 0.5 * (lo + hi)
    x0, x1, y0, y1 = extents(k)
    top_rel = max(max(k * A[2] + o[2] for A, os in offs for o in os), max(k * b.path[-1][2] for b in branches))
    low_h = max(-b.path[0][2] for b in lows)
    z_split = min(d["H"] + 48.0, max(d["H"] + 18.0, d["soil_z"] + 12.0 + k * low_h, target_h - top_rel))
    lean_r, lean_a = uni(0.0, 3.0), uni(0.0, TWO_PI)
    px = -0.3 * (x0 + x1) + lean_r * math.cos(lean_a)       # lean the trunk to balance the crown
    py = -0.3 * (y0 + y1) + lean_r * math.sin(lean_a)
    pr = math.hypot(px, py)
    if pr > 7.0:
        px, py = px * 7.0 / pr, py * 7.0 / pr
    P0 = (px, py, z_split)

    def world(p):
        return (P0[0] + k * p[0], P0[1] + k * p[1], P0[2] + k * p[2])

    # ---- meshes
    br, ba = uni(0.0, 2.0), uni(0.0, TWO_PI)
    base = (br * math.cos(ba), br * math.sin(ba), d["soil_z"] - 2.5)
    t_path, t_rad, t_mod = _tree_trunk(base, P0, uni(1.7, 1.9), uni(1.15, 1.3), d["soil_z"], rng)
    trunk = _gnarl_md(t_path, t_rad, 14, t_mod)
    shift = {}                                  # each low branch (and its twigs, cards) onto the trunk's line
    for low in lows:
        b0 = world(low.path[0])
        for a, b in zip(t_path, t_path[1:]):
            if a[2] <= b0[2] <= b[2]:
                f = (b0[2] - a[2]) / (b[2] - a[2]) if b[2] > a[2] else 0.0
                shift[low.group] = (a[0] + (b[0] - a[0]) * f - b0[0], a[1] + (b[1] - a[1]) * f - b0[1], 0.0)
                break
        else:
            raise ValueError("low branch below the trunk")
    world0 = world

    def world(p, b=None):
        q = world0(p)
        s = shift.get(getattr(b, "group", None))
        return _add(q, s) if s else q
    wbranches = [{"level": 0, "path": t_path, "radii": t_rad, "root": -1, "low": False}]
    for m in mains:
        ph1, ph2 = uni(0.0, TWO_PI), uni(0.0, TWO_PI)

        def mod(i, a, cum=m.cum, ph1=ph1, ph2=ph2):
            return 1.0 + 0.05 * math.sin(3.0 * a + 0.2 * cum[i] + ph1) + 0.03 * math.sin(2.0 * a - 0.1 * cum[i] + ph2)
        trunk.merge(_gnarl_md([world(p) for p in m.path], m.radii(), m.sides, mod))
    twigs = [_MD() for _ in mains]
    for b in branches:
        wp = [world(p, b) for p in b.path]
        if b.level >= 2:
            twigs[b.root].merge(_tube_md(wp, b.radii(), b.sides))
        wbranches.append({"level": b.level, "path": wp, "radii": b.radii(), "root": b.root,
                          "low": getattr(b, "group", None) is not None})
    card_mds, specs, probes = [], [], []
    for c in cards:
        A, axes = world(c["A"], c["branch"]), c["axes"]
        md = blossom_card_md(c["size"], c["droop"], c["fold"], c["twist"])
        md.map(lambda p, A=A, axes=axes: _xf(p, A, axes))
        card_mds.append(md)
        pr_ = [_xf(p, A, axes) for p in c["local"]]
        probes.extend(pr_)
        specs.append({"size": c["size"], "attach": A, "level": c["branch"].level, "terminal": c["terminal"],
                      "axes": axes, "probes": pr_})
    soil = pot_soil_md(d, [(base[0], base[1], 1.1, 5.0)], seed)
    tips = [world(b.path[-1], b) for b in branches]
    return {"trunk": trunk, "twigs": twigs, "cards": card_mds, "specs": specs, "soil": soil,
            "branches": wbranches, "probes": probes,
            "height": max(max(p[2] for p in probes), max(p[2] for p in tips)),
            "crown": (x1 - x0, y1 - y0), "crown_centre": (P0[0] + 0.5 * (x0 + x1), P0[1] + 0.5 * (y0 + y1)),
            "scale": k, "split": P0, "target_h": target_h, "target_w": target_w, "n_cards": len(cards),
            "n_main": n_main, "pot": d, "trunk_base": base}


def flowering_tree_parts(seed=0):
    """[(name, mat, md, tile, smooth)] of the flowering tree: the brass pot, its soil, the
    trunk with the main branches, one twig node per main branch, and the blossom cards in
    nodes of CARDS_PER_NODE (tile None: their own 0-1 UVs)."""
    g = flowering_tree_geometry(seed)
    parts = [("FlowerTree_Pot", "metal_brass", brass_pot_md(), BRASS, 1),
             ("FlowerTree_Soil", "soil", g["soil"], SOIL, 1),
             ("FlowerTree_Trunk", "stem", g["trunk"], STEM, 1)]
    parts += [("FlowerTree_Twigs", "stem", md, STEM, 1) for md in g["twigs"] if md.f]
    for i in range(0, len(g["cards"]), CARDS_PER_NODE):
        parts.append(("FlowerTree_Blossoms", "blossom_card", _merge(g["cards"][i:i + CARDS_PER_NODE]), None, 0))
    return parts


# ============================================================== lounge chair
CHAIR_W, CHAIR_D, CHAIR_H = 80.0, 85.0, 75.0
CHAIR_SEAT = 38.0          # top of the seat cushion's edge ring (its crown rises 1.6 above)
CHAIR_ZB = 13.9            # the shell's underside: 1 mm down round the swivel plate's top
CHAIR_DECK = 22.0          # top of the shell's seat pan = underside of the cushion
CHAIR_N = 56               # meridians round the shell
CUSHION_N = 48             # points round the seat cushion
# at 0, 45, ..., 315 degrees (0 = +X, 90 = the back, 270 = the front): rim height, rim
# thickness, recline of the inner face (how far its top stands behind its foot), and how far
# the outer face's top leans in from the plan outline
RIM_Z = (57.0, 65.0, 75.0, 65.0, 57.0, 53.0, 35.5, 53.0)
RIM_W = (12.5, 13.5, 14.5, 13.5, 12.5, 11.0, 10.0, 11.0)
RECLINE = (3.0, 8.0, 12.0, 8.0, 3.0, 1.0, 0.0, 1.0)
LEAN = (1.5, 1.8, 2.0, 1.8, 1.5, 1.2, 1.0, 1.2)
MER_SEG = (4, 1, 4, 1, 6, 4)   # sub-segments: underside, flank, outer face, rim top, inner face, pan
MER_ARC = (4, 3, 4, 4, 3)      # sub-arcs: bottom round, bulge, rim (outside), rim (inside), inner foot


def _fillet_path(pts, radii, seg_n, arc_n, share=0.45):
    """Open polyline pts with its interior corners rounded by tangent arcs of radii[i] (a
    corner takes at most `share` of each neighbouring segment, so a straight piece is left
    between neighbouring rounds), resampled to a fixed count: seg_n[k] steps along segment
    k, arc_n[i - 1] steps round corner i. The same counts give the same topology whatever
    the shape, so sections that vary can be lofted."""
    m = len(pts) - 1
    rounds = [None] * (m + 1)
    for i in range(1, m):
        a, p, c = pts[i - 1], pts[i], pts[i + 1]
        l1, l2 = math.hypot(p[0] - a[0], p[1] - a[1]), math.hypot(c[0] - p[0], c[1] - p[1])
        d1 = ((p[0] - a[0]) / l1, (p[1] - a[1]) / l1)
        d2 = ((c[0] - p[0]) / l2, (c[1] - p[1]) / l2)
        cr = d1[0] * d2[1] - d1[1] * d2[0]
        turn = math.acos(max(-1.0, min(1.0, d1[0] * d2[0] + d1[1] * d2[1])))
        if turn < 1e-6 or radii[i] <= 0.0:
            raise ValueError("corner %d has no turn or no radius" % i)
        tl = min(radii[i] * math.tan(0.5 * turn), share * min(l1, l2))
        r = tl / math.tan(0.5 * turn)
        sgn = 1.0 if cr > 0.0 else -1.0
        t1 = (p[0] - d1[0] * tl, p[1] - d1[1] * tl)
        t2 = (p[0] + d2[0] * tl, p[1] + d2[1] * tl)
        cen = (t1[0] - d1[1] * sgn * r, t1[1] + d1[0] * sgn * r)
        rounds[i] = (t1, t2, cen, r, math.atan2(t1[1] - cen[1], t1[0] - cen[0]), sgn * turn)
    out = [tuple(pts[0])]
    for k in range(m):
        s = pts[0] if k == 0 else rounds[k][1]
        e = pts[m] if k == m - 1 else rounds[k + 1][0]
        n = seg_n[k]
        for j in range(1, n + 1):
            out.append((s[0] + (e[0] - s[0]) * j / n, s[1] + (e[1] - s[1]) * j / n))
        if k < m - 1:
            _t1, _t2, cen, r, a0, sweep = rounds[k + 1]
            n = arc_n[k]
            for j in range(1, n + 1):
                a = a0 + sweep * j / n
                out.append((cen[0] + r * math.cos(a), cen[1] + r * math.sin(a)))
    return out


def _mer_index(corner, end):
    """Index in a chair meridian of the start ('in') or end ('out') of a corner's round."""
    i = 0
    for k in range(corner):
        i += MER_SEG[k]
        if k < corner - 1:
            i += MER_ARC[k]
    return i if end == "in" else i + MER_ARC[corner - 1]


MER_K = 1 + sum(MER_SEG) + sum(MER_ARC)            # points per meridian
MER_RIM = _mer_index(3, "out")                     # rim top, outer end of its flat (U reference ring)
MER_INNER = (_mer_index(4, "out"), _mer_index(5, "in"), _mer_index(5, "out"))   # inner face top, foot, pan


def chair_rho_out(phi, A=0.5 * CHAIR_W, B=0.5 * CHAIR_D, e=2.6):
    """Plan outline of the shell (a superellipse 80 x 85) as a radius at azimuth phi."""
    c, s = abs(math.cos(phi)), abs(math.sin(phi))
    return 1.0 / ((c / A) ** e + (s / B) ** e) ** (1.0 / e)


def chair_layout(seed=0):
    """Seeded parameters of the knitted lounge chair."""
    seed = int(seed or 0)
    rng = random.Random(3307 + 7919 * seed)
    uni = rng.uniform
    ha = uni(0.0, TWO_PI)
    return {"seed": seed, "z_b": CHAIR_ZB, "z_deck": CHAIR_DECK, "seat_h": CHAIR_SEAT, "tuck": 7.0,
            "rim_wob": [(3, uni(0.2, 0.4), uni(0.0, TWO_PI)), (5, uni(0.08, 0.18), uni(0.0, TWO_PI))],
            "belly": (uni(0.5, 0.8), uni(0.15, 0.3), uni(0.0, TWO_PI)),
            "crown": uni(1.4, 1.8), "hollow": (uni(-3.0, 3.0), uni(-12.0, -6.0), uni(0.5, 0.8)),
            "knit": uni(0.08, 0.14), "overlap": 0.5, "hollow_dir": ha}


def chair_meridian(lay, phi):
    """(rho, z) points (MER_K of them) of the shell's section at azimuth phi, counter-
    clockwise round the material from the underside's centre (z_b) out to a 9 cm round
    tucked 7 cm in, up the outer face (widest, on the plan outline, at 45 % of the rim
    height, leaning in towards the top), over the rim (a full round: two quarter rounds of
    about half the rim thickness), down the inner face (reclined at the back, the knit
    sagging into a 0.4-1.1 cm belly between the rim and the seat pan) round a 4.5 cm foot to
    the seat pan (z_deck) and its centre. The rim's height runs from 75 at the back over
    57 cm arms down to a 35.5 cm roll under the seat's front edge; on the arms it wavers by
    a few mm (seeded)."""
    rho_o = chair_rho_out(phi)
    wob = sum(a * math.sin(m * phi + ph) for m, a, ph in lay["rim_wob"]) * math.cos(phi) ** 2
    zt = _periodic(RIM_Z, phi) + wob
    w, rec, lean = _periodic(RIM_W, phi), _periodic(RECLINE, phi), _periodic(LEAN, phi)
    zb, zd, tuck = lay["z_b"], lay["z_deck"], lay["tuck"]
    zw = zb + 0.45 * (zt - zb)

    def build(dr):
        pts = [(0.0, zb), (rho_o - tuck, zb), (rho_o + dr, zw), (rho_o - lean, zt), (rho_o - lean - w, zt),
               (rho_o - lean - w - rec, zd), (0.0, zd)]
        return _fillet_path(pts, [0.0, 9.0, 18.0, 0.49 * w, 0.49 * w, 4.5, 0.0], MER_SEG, MER_ARC)

    dr = 0.0
    for _ in range(8):                      # the rounded bulge's widest point onto the outline
        err = rho_o - max(p[0] for p in build(dr))
        dr += err
        if abs(err) < 1e-5:
            break
    mer = build(dr)
    b0, b1, bph = lay["belly"]
    belly = b0 + b1 * math.sin(2.0 * phi + bph)
    i0, i1 = MER_INNER[0], MER_INNER[1]
    for i in range(i0 + 1, i1):
        r, z = mer[i]
        mer[i] = (r - belly * math.sin(math.pi * (i - i0) / float(i1 - i0)), z)
    return mer


def chair_inner_rho(mer, z):
    """Radius of the shell's inner face (the seat side of a meridian) at height z: down
    the inner face and round its foot to the seat pan; above the face's top its radius
    there, below the pan its radius at the pan."""
    span = mer[MER_INNER[0]:MER_INNER[2] + 1]
    if z >= span[0][1]:
        return span[0][0]
    for (r0, z0), (r1, z1) in zip(span, span[1:]):
        if z1 <= z <= z0:
            return r1 if z0 - z1 < 1e-9 else r0 + (r1 - r0) * (z - z0) / (z1 - z0)
    return span[-1][0]


def chair_shell_md(lay):
    """Closed knit-covered shell: CHAIR_N meridians lofted round the chair (poles at the
    underside's and the seat pan's centres, both hidden). Own UVs at KNIT cm per unit with
    the stripes running round the chair: U round it (by the rim's length, the seam up the
    back centre), V along the meridian (true length, measured from 30 cm up the outer face,
    so the stripes are level all round the outside and follow the rim over the top and down
    the inner faces)."""
    N = CHAIR_N
    phis = [0.5 * math.pi + TWO_PI * j / N for j in range(N)]
    mers = [chair_meridian(lay, ph) for ph in phis]
    K = len(mers[0])
    md = _MD()
    pole0 = md.add((0.0, 0.0, lay["z_b"]))
    pole1 = md.add((0.0, 0.0, lay["z_deck"]))
    M = []
    for ph, mer in zip(phis, mers):
        c, s = math.cos(ph), math.sin(ph)
        M.append([pole0] + [md.add((r * c, r * s, z)) for r, z in mer[1:-1]] + [pole1])
    t = KNIT
    U = [0.0]
    for j in range(N):
        a, b = md.v[M[j][MER_RIM]], md.v[M[(j + 1) % N][MER_RIM]]
        U.append(U[-1] + math.dist(a, b))
    U = [u / t for u in U]
    V = []
    for mer in mers:
        s = [0.0]
        for a, b in zip(mer, mer[1:]):
            s.append(s[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        ref = None
        for i in range(MER_RIM):
            (r0, z0), (r1, z1) = mer[i], mer[i + 1]
            if z0 <= 30.0 < z1:
                ref = s[i] + (s[i + 1] - s[i]) * (30.0 - z0) / (z1 - z0)
                break
        if ref is None:
            raise ValueError("outer face does not reach 30 cm")
        V.append([(c - ref) / t for c in s])
    for j in range(N):
        j2 = (j + 1) % N
        um = 0.5 * (U[j] + U[j + 1])
        for k in range(K - 1):
            a, b, c, d = M[j][k], M[j2][k], M[j2][k + 1], M[j][k + 1]
            uv = ((U[j], V[j][k]), (U[j + 1], V[j2][k]), (U[j + 1], V[j2][k + 1]), (U[j], V[j][k + 1]))
            if k == 0:
                _quad(md, (a, c, d), ((um, 0.5 * (V[j][0] + V[j2][0])), uv[2], uv[3]))
            elif k == K - 2:
                _quad(md, (a, b, c), (uv[0], uv[1], (um, 0.5 * (V[j][K - 1] + V[j2][K - 1]))))
            else:
                _quad(md, (a, b, c, d), uv)
    return md


def chair_cushion_md(lay):
    """Closed seat cushion filling the shell's seat well: rings of CUSHION_N points whose
    plan follows the shell's inner faces at every height, pressed `overlap` (5 mm) into them
    (the knit cushion tucked in), from the seat pan (1 mm down into it) round a 1.5 cm
    bottom edge, up the side, over a 4.5 x 4 cm top edge to the top ring at the seat height;
    the top a Coons patch crowned 1.4-1.8 cm with a seeded sat-in hollow and a soft knit
    ripple. At the front it rises 2.5 cm over the shell's front roll. Own UVs at KNIT cm per
    unit: the side band wrapped (U round it, the seam at the back, V up it), top and bottom
    planar (the stripes across the seat)."""
    Nc = CUSHION_N
    pc = Nc // 4
    phis = [math.radians(225.0) + TWO_PI * j / Nc for j in range(Nc)]
    mers = [chair_meridian(lay, ph) for ph in phis]
    z0, z1 = lay["z_deck"] - 0.1, lay["seat_h"]
    rbh = rbv = 1.5
    rth, rtv = 4.5, 4.0
    st = []
    for a in (0.0, 45.0, 90.0):
        t = math.radians(a)
        st.append((rbh * (1.0 - math.sin(t)), z0 + rbv * (1.0 - math.cos(t))))
    zs0, zs1 = z0 + rbv, z1 - rtv
    for k in range(1, 4):
        st.append((0.0, zs0 + (zs1 - zs0) * k / 4.0))
    for a in (0.0, 22.5, 45.0, 67.5, 90.0):
        t = math.radians(a)
        st.append((rth * (1.0 - math.cos(t)), zs1 + rtv * math.sin(t)))
    md = _MD()
    rings = []
    for inset, z in st:
        ring = []
        for ph, mer in zip(phis, mers):
            r = chair_inner_rho(mer, z) + lay["overlap"] - inset
            ring.append(md.add((r * math.cos(ph), r * math.sin(ph), z)))
        rings.append(ring)
    t = KNIT
    hx, hy, hd = lay["hollow"]
    cr = lay["crown"]
    kn = lay["knit"]
    seed = lay["seed"]

    def top(pt, u, v):
        x, y, z = pt
        z += cr * 16.0 * u * (1.0 - u) * v * (1.0 - v)
        z -= hd * math.exp(-((x - hx) ** 2 + (y - hy) ** 2) / 180.0)
        z += kn * (2.0 * _fbm(x / 9.0, y / 9.0, 777 + seed) - 1.0)
        return (x, y, z)

    G = _coons_grid(md, rings[-1], pc, pc, top)
    for i in range(pc):
        for j in range(pc):
            idx = (G[i][j], G[i + 1][j], G[i + 1][j + 1], G[i][j + 1])
            _quad(md, idx, [(md.v[a][0] / t, md.v[a][1] / t) for a in idx])
    G = _coons_grid(md, rings[0], pc, pc)
    for i in range(pc):
        for j in range(pc):
            idx = (G[i][j], G[i][j + 1], G[i + 1][j + 1], G[i + 1][j])
            _quad(md, idx, [(-md.v[a][0] / t, md.v[a][1] / t) for a in idx])
    mid = rings[len(rings) // 2]
    L = sum(math.dist(md.v[mid[j]], md.v[mid[(j + 1) % Nc]]) for j in range(Nc))
    Uc = [(((ph - 0.5 * math.pi) % TWO_PI) / TWO_PI) * L / t for ph in phis]
    Vs = [0.0]
    for a, b in zip(st, st[1:]):
        Vs.append(Vs[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    Vs = [v / t for v in Vs]
    for k in range(len(rings) - 1):
        for j in range(Nc):
            j2 = (j + 1) % Nc
            u0, u1 = Uc[j], Uc[j2]
            if u1 < u0:
                u1 += L / t
            _quad(md, (rings[k][j], rings[k][j2], rings[k + 1][j2], rings[k + 1][j]),
                  ((u0, Vs[k]), (u1, Vs[k]), (u1, Vs[k + 1]), (u0, Vs[k + 1])))
    return md


def swivel_base_profile():
    """(r, z) section of the black swivel base: a 52 cm floor disc 1.2-1.8 cm thick (its top
    a shallow cone up to the column, 2.5 / 5 mm rounds at the edge), a 6.4 cm column flared
    1.2 cm into the disc and 0.8 cm under the 26 cm swivel plate (1.2 cm thick, 3 mm
    rounds) whose top at 14 cm carries the shell."""
    pts = [(0.0, 0.0), (26.0, 0.0), (26.0, 1.2), (6.5, 1.72), (3.2, 1.85), (3.2, 12.8), (13.0, 12.8),
           (13.0, 14.0), (0.0, 14.0)]
    return _fillet2d(pts, [0.0, 0.25, 0.5, 0.0, 1.2, 0.8, 0.3, 0.3, 0.0], step=math.radians(15.0))


def knit_chair_parts(seed=0):
    """[(name, mat, md, tile, smooth)] of the lounge chair: the swivel base (metal_black,
    box-mapped), the shell and the seat cushion (knit_stripe, own UVs), each TurboSmoothed
    once."""
    lay = chair_layout(seed)
    return [("KnitChair_Base", "metal_black", _revolve_md(swivel_base_profile(), 48), METAL, 1),
            ("KnitChair_Shell", "knit_stripe", chair_shell_md(lay), KNIT, 1),
            ("KnitChair_Seat", "knit_stripe", chair_cushion_md(lay), KNIT, 1)]


# ========================================================= Max-facing wrappers
def build_tapestry(width=300.0, height=230.0, seed=0):
    """Hand-tufted wool wall tapestry width x height x 2.5 cm (see tapestry_md): origin at
    its bottom centre, back on y = 0 (the wall face), face towards -Y."""
    return kit.group("Tapestry", _nodes(tapestry_parts(width, height, seed)))


def build_flowering_tree(seed=0):
    """Yellow-flowering tree about 150 tall in a 42 x 38 brass pot on its low foot disc (see
    flowering_tree_geometry); origin at the pot's centre on the floor."""
    return kit.group("FloweringTree", _nodes(flowering_tree_parts(seed)))


def build_velvet_pouf(seed=0):
    """Slate-blue velvet pouf about 50 x 42: bulging sides, a domed top and a welted top
    edge (pouf_body_md, pouf_welt_md); origin at the centre of its base."""
    return kit.group("VelvetPouf", _nodes(velvet_pouf_parts(seed)))


def build_knit_lounge_chair(seed=0):
    """Low knitted lounge chair 80 x 85 x 75, seat 38, on a black swivel disc base
    (chair_shell_md, chair_cushion_md); front -Y, origin at the centre of its footprint."""
    return kit.group("KnitLoungeChair", _nodes(knit_chair_parts(seed)))


PIECES = {"tapestry": tapestry_parts, "flowering_tree": flowering_tree_parts, "velvet_pouf": velvet_pouf_parts,
          "knit_lounge_chair": knit_chair_parts}


def preview():
    """Every piece at the origin of a test room (run inside 3ds Max): the tapestry on a wall
    face at y = 120 with its bottom 60 cm up, the chair, the pouf and the tree in front."""
    nodes = [kit.place(build_tapestry(), 0.0, 120.0, 60.0, 0.0),
             kit.place(build_knit_lounge_chair(), -110.0, 0.0, 0.0, 20.0),
             kit.place(build_velvet_pouf(), 0.0, -20.0, 0.0, 0.0),
             kit.place(build_flowering_tree(), 120.0, 40.0, 0.0, 0.0)]
    return nodes
