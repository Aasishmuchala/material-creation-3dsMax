"""Architecture for the quiet-luxury benchmark-3 living room (MatForge, V-Ray, 3ds Max 2026).

Four pieces, each generated as pure-Python cages (furn_living._MD) by *_layout / *_profile /
*_md / *_parts functions that run without Max (tests/test_bench3_arch_geom.py) and handed to
Max by thin build_* wrappers. Parts are (node name, material key, _MD, tile cm, TurboSmooth
iterations); tile None means the cage carries its own UVs on EVERY face, which the scene must
keep (kit.part maptype None - the wrappers register them so). No piece uses TurboSmooth (it
would melt 1 mm eases): every node gets a Smooth modifier (auto 40 deg), every visible edge is
a real fillet in steps of 22.5-30 deg, and the flats beside a fillet are bordered by a support
ring 0.3 mm off it, so a board face or a tile top shades dead flat instead of bowing.

  build_slat_panel(width, height, seed=0, pilaster_every=0, to_ceiling=True, pilaster_w=24,
                   tile=120)
        Fluted oak wall panelling. Footprint x = -width/2 .. width/2, y = -2.4 .. 0 (+0.1 into
        the wall), z = 0 .. height; origin: bottom centre ON the wall face (y = 0), front -Y.
        Solid oak boards 9 cm wide, 2.4 cm thick, standing on the floor, every edge (ends too)
        eased 1 mm, with 1.5 cm grooves between them; a dark backing (metal_black, y = -1.4 ..
        +0.1) fills the grooves to 1 cm under the board faces. The layout is symmetric about
        x = 0 (a board or a groove on the centre line, whichever leaves the fuller end boards);
        the two end boards are ripped (>= 3.75 cm) or, where the remainder is too small to rip
        a board from, made wider, so the panel finishes at +-width/2 with a board and the
        backing never shows at its ends. pilaster_every=N > 0 adds a flat oak "pilaster" board
        pilaster_w (24) cm wide after every N slats (a pilaster or the middle of a bay on the
        centre line), with the same grooves either side. Own UVs ("oak_slat", `tile` = 120 cm
        of wall per UV unit): the grain runs up V on the faces and on the groove walls (those
        are unfolded off the face, so the figure wraps the eased arris), and every board is
        its own random window into the texture (its origin at least 0.06 UV from every other
        board's - eased to 0.5/sqrt(n) past 69 boards - and mirrored in U and/or V), so no
        two boards match. to_ceiling: the backing runs
        1 mm up into the ceiling (a floor-to-ceiling panel); False stops it 0.5 mm under the
        board tops. It runs 1 mm into the floor either way.
  build_limestone_floor(rect_cm, seed=0, tile=90, gap=0.2, lippage=0.02)
        Honed limestone tiles 90 x 90 x 2 cm in a straight grid over rect_cm (scene cm), set
        out from the room's centre lines (a joint or a tile centre on each, whichever leaves
        the bigger cuts: never less than half a tile at the walls), 2 mm open joints (1 mm
        off the walls) over a dark subfloor (metal_black, z = -2.6 .. -1.4), 1 mm rounded
        edges, sub-millimetre lippage (tops within 0.32 mm under z = 0). Every tile is its own
        UV window into the 180 cm texture repeat ("stone_floor", own UVs: a full tile is a
        0.5 x 0.5 window at a random offset, turned / mirrored by one of the 8 symmetries of
        the square). Top at z = 0, already in place: leave the group at the origin.
  build_flush_skirting(rect_cm, openings=(), height=6, gap=1, recess=1)
        Slim flush skirting in paint_white round the wall faces rect_cm: a 6 cm face flush
        with the wall plaster (u = 0) on the floor (its foot 1.3 cm under the floor surface),
        1 mm arris on top, then a 1 x 1 cm shadow line (0.5 mm filleted inner corners) up to
        a 2 mm plaster-stop nose with a 1 mm arris. Mitred at the room corners, stopped square
        (closed ends) at openings [(side, a0, a1)] as bench_arch.skirting_md. Everything lies
        at or behind the wall faces (u <= 0). THE SCENE must stop its wall plaster at
        z = FS_TOP (7.2: it bears on the profile's top) and set the wall's foot back FS_BACK
        (1.2 cm) behind the face below that, as bench2_scene.wall_with_reveal does with its
        SK_TOP / REVEAL. Already in place: leave the group at the origin.
  build_slot_diffuser(length=140, width=9, frame_key="metal_steel")
        Recessed 2-slot linear air-conditioning diffuser hanging from z = 0 at the ceiling.
        Face length x width (140 x 9) at z = -0.25 .. 0 (the satin frame stands 2.5 mm under
        the ceiling, 1 mm into it): 1.5 cm borders round two 2.4 cm slots either side of a
        1 cm divider, all flush, 1 mm / 0.8 mm arrises; 1.2 mm webs line the slots 2 cm up
        (frame and divider in frame_key: "paint_white" gives a powder-coated white frame);
        a curved deflector blade (metal_steel, 0.8 mm, rounded edges) in each slot, lower edge
        5 mm above the face, tilted 30 deg to throw the air to the front (-Y); a black plenum
        box (metal_black) over the slots up to z = 12.05. THE SCENE must open the ceiling at
        slot_diffuser_hole(length, width) (local x0, x1, y0, y1: 137.8 x 6.8 cm for the
        default, inside the flange), or the slots would show the ceiling's underside instead
        of the black plenum. Origin: centre of the face on the ceiling plane: kit.place it at
        the ceiling height.

Materials: oak_slat (declared here), metal_black (slat backing, subfloor, plenum),
stone_floor (declared here), paint_white (skirting), metal_steel (diffuser frame and blades).
"""
import math

from pymxs import runtime as rt

import furn_living as FL
import kit
from bench_arch import (_merge, _opening_span, _perim_point, _profile, _rbox_md, _rect, _sweep,
                        _volume, _xyz)          # _volume: re-exported for the tests
from furn_living import _MD, _Rand, _dihedral

# new material keys for the benchmark-3 room (runtime only; kit.py is not edited)
kit.MAT_KEYS.setdefault("oak_slat", "light oak veneer slats (own UVs, grain along V)")
kit.MAT_KEYS.setdefault("stone_floor", "light honed limestone floor tiles (own UVs, 180 cm repeat)")

EPS = 0.1               # buried faces run 1 mm into wall / ceiling / floor
SUPPORT = 0.03          # support rings 0.3 mm off every fillet: the flats shade dead flat
METAL = 25.0            # box-map repeats (cm)
PAINT = 120.0
SUBFLOOR = 100.0


# ===================================================================== helpers
def _bbox(md):
    xs, ys, zs = zip(*md.v)
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def _stations(lo, hi, r, s, k):
    """Lattice stations along one axis of an eased box: (coordinate on the inner box, normal
    component). From the lo face round its fillet in k steps to the 45-degree line (the rest
    of the quarter round belongs to the neighbouring face), a support station s inside the
    fillet, and the same mirrored at hi."""
    a, b = lo + r, hi - r
    if b - a <= 2.0 * s + 1e-6:
        raise ValueError("box %.3f cm is too thin for a %.2f cm ease" % (hi - lo, r))
    ws = [1.0 if m == k else math.tan(0.25 * math.pi * m / k) for m in range(k, 0, -1)]
    st = [(a, -w) for w in ws] + [(a, 0.0)]
    if s > 0.0:
        st += [(a + s, 0.0), (b - s, 0.0)]
    st += [(b, 0.0)] + [(b, w) for w in reversed(ws)]
    return st


def _eased_box_md(x0, x1, y0, y1, z0, z1, r=0.1, uvf=None, s=SUPPORT, k=2):
    """Closed box with all 12 edges rounded r (sphere-octant corners), as a cube lattice:
    every vertex is an inner-box point plus r times a unit normal, so the fillets are exact
    quarter rounds in 2k steps of 45/k deg. Support stations s inside each fillet keep the
    six flats dead flat under smoothing. uvf(axis, sign, (x, y, z)) -> (u, v) gives every
    face corner a UV (axis 0/1/2 = the cube face's normal axis x/y/z, sign -1/+1 its side);
    without it the faces carry none. Wound outward."""
    S = (_stations(x0, x1, r, s, k), _stations(y0, y1, r, s, k), _stations(z0, z1, r, s, k))
    n = [len(a) for a in S]
    md = _MD()
    idx = {}

    def vert(t):
        i = idx.get(t)
        if i is None:
            d = [S[a][t[a]][1] for a in range(3)]
            ln = math.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2])
            i = idx[t] = md.add(tuple(S[a][t[a]][0] + r * d[a] / ln for a in range(3)))
        return i

    for a in range(3):
        b, c = (a + 1) % 3, (a + 2) % 3
        for side, sgn in ((0, -1), (n[a] - 1, 1)):
            for j in range(n[b] - 1):
                for q in range(n[c] - 1):
                    quad = []
                    for jj, qq in ((j, q), (j + 1, q), (j + 1, q + 1), (j, q + 1)):
                        t = [0, 0, 0]
                        t[a], t[b], t[c] = side, jj, qq
                        quad.append(vert(tuple(t)))
                    if sgn < 0:                     # (b, c) quads face +a; the low side is turned
                        quad.reverse()
                    md.face(quad, [uvf(a, sgn, md.v[i]) for i in quad] if uvf else None)
    return md


def _perimeter_sweep(rect_cm, prof, openings=()):
    """A section swept round the wall faces rect_cm (u > 0 into the room, u < 0 into the
    walls), mitred at the corners, stopped square with closed ends at openings [(side, a0,
    a1)] (bench_arch._opening_span); each run its own closed shell, all in one mesh."""
    x0, y0, x1, y1 = _rect(rect_cm)
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


# ================================================================== slat panel
SLAT_W = 9.0            # board width
SLAT_T = 2.4            # board thickness: faces at y = -2.4, backs on the wall
GROOVE_W = 1.5          # groove between boards
GROOVE_D = 1.0          # groove depth: the backing's face 1 cm under the board faces
SLAT_EASE = 0.1         # every board edge eased 1 mm
PIL_W = 24.0            # flat pilaster board
END_MIN = 3.75          # narrowest ripped end board
OAK_TILE = 120.0        # cm of wall per oak_slat UV unit
WIN_SEP = 0.06          # every board's UV window this far (on the torus) from all the others
BACK_INSET = 0.3        # the backing stops 3 mm inside the end boards' outer sides


def slat_layout(width, pilaster_every=0, pilaster_w=PIL_W):
    """Boards across x = -width/2 .. width/2, left to right: [(x0, x1, kind)], kind "slat" or
    "pilaster", GROOVE_W gaps between neighbours, symmetric about x = 0. With
    pilaster_every = N > 0 a pilaster follows every N slats. Two set-outs are tried - a
    board (slat, or pilaster) or a groove (the middle of a bay) on the centre line - and the
    one whose end boards come closest to a full board is kept; the end boards are ripped down
    to the panel edge, or widened by up to a groove plus END_MIN where less than that would
    be left over."""
    W, N, pw, g = float(width), int(pilaster_every), float(pilaster_w), GROOVE_W
    if N < 0:
        raise ValueError("pilaster_every must be >= 0, not %r" % pilaster_every)
    if W < 30.0:
        raise ValueError("slat panel too narrow: %r cm" % width)
    if N and not SLAT_W < pw <= 120.0:
        raise ValueError("pilaster width %r out of range" % pilaster_w)
    half = 0.5 * W
    period = ["pilaster"] + ["slat"] * N if N else ["slat"]
    wid = {"slat": SLAT_W, "pilaster": pw}
    if N == 0:
        cands = [(0, 1), (None, 0)]                    # a slat / a groove on the centre line
    elif N % 2:
        cands = [(0, 1), ((N + 1) // 2, (N + 1) // 2 + 1)]   # a pilaster / the bay's middle slat
    else:
        cands = [(0, 1), (None, N // 2 + 1)]           # a pilaster / the bay's middle groove
    best = None
    for centre, first in cands:
        if centre is None:
            cursor, mid = 0.5 * g, []
        else:
            wc = wid[period[centre]]
            cursor, mid = 0.5 * wc + g, [(-0.5 * wc, 0.5 * wc, period[centre])]
        if half - cursor < END_MIN - 1e-9:
            continue
        right, m = [], first
        while True:
            kind = period[m % len(period)]
            w, r = wid[kind], half - cursor
            if r >= w + g + END_MIN - 1e-9:
                right.append((cursor, cursor + w, kind))
                cursor += w + g
                m += 1
                continue
            right.append((cursor, half, kind))         # ripped (r < w) or widened end board
            break
        e, w = half - right[-1][0], wid[right[-1][2]]
        score = e / w if e <= w else w / e
        if best is None or score > best[0] + 1e-9:
            best = (score, [(-b, -a, k) for a, b, k in reversed(right)] + mid + right)
    if best is None:
        raise ValueError("slat panel %r cm too narrow for its pilasters" % width)
    return best[1]


def window_sep(count, sep=WIN_SEP):
    """Least distance between two boards' window origins: `sep`, eased down for very long
    panels (0.5 / sqrt(count)) so the discs never fill more than a fifth of the torus."""
    return min(float(sep), 0.5 / math.sqrt(max(int(count), 1)))


def board_windows(count, seed=0, sep=WIN_SEP):
    """[(u0, v0, fu, fv)] for `count` boards: random window origins on the unit torus, each
    at least window_sep(count, sep) from every earlier one (rejection sampling, deterministic),
    and random mirroring of U and V (fu, fv = +-1; the grain stays along V)."""
    rnd = _Rand(seed * 977 + 31)
    sep = window_sep(count, sep)
    out = []
    for _ in range(int(count)):
        for _try in range(400):
            u0, v0 = rnd.uniform(0.0, 1.0), rnd.uniform(0.0, 1.0)
            if all(math.hypot(min(abs(u0 - a), 1.0 - abs(u0 - a)), min(abs(v0 - b), 1.0 - abs(v0 - b))) >= sep
                   for a, b, _fu, _fv in out):
                break
        fu = -1.0 if rnd.uniform(0.0, 1.0) < 0.5 else 1.0
        fv = -1.0 if rnd.uniform(0.0, 1.0) < 0.5 else 1.0
        out.append((u0, v0, fu, fv))
    return out


def _board_uv(x0, x1, win, tile):
    """uvf for _eased_box_md: one board's window (u0, v0, fu, fv) into the oak texture, the
    grain up V; the sides (groove walls) are unfolded off the face (u runs on round the
    arris), the ends take the plan."""
    u0, v0, fu, fv = win
    xc, yf = 0.5 * (x0 + x1), -SLAT_T

    def uvf(axis, sgn, p):
        x, y, z = p
        if axis == 0:
            s = (x1 - xc) + (y - yf) if sgn > 0 else (x0 - xc) - (y - yf)
            return (u0 + fu * s / tile, v0 + fv * z / tile)
        if axis == 1:
            return (u0 + fu * (x - xc) / tile, v0 + fv * z / tile)
        return (u0 + fu * (x - xc) / tile, v0 + fv * (y - yf) / tile)
    return uvf


def slat_panel_parts(width, height, seed=0, pilaster_every=0, to_ceiling=True, pilaster_w=PIL_W,
                     tile=OAK_TILE):
    """[(name, key, md, tile, smooth)] of the slat panel (see build_slat_panel): the slats and
    the pilasters (own UVs, tile None) and the backing."""
    W, H, T = float(width), float(height), float(tile)
    if not 30.0 <= H <= 600.0:
        raise ValueError("slat panel height %r out of range" % height)
    if T < 20.0:
        raise ValueError("oak texture repeat %r too small" % tile)
    boards = slat_layout(W, pilaster_every, pilaster_w)
    slats, pils = _MD(), _MD()
    for (x0, x1, kind), win in zip(boards, board_windows(len(boards), seed)):
        md = _eased_box_md(x0, x1, -SLAT_T, 0.0, 0.0, H, SLAT_EASE, _board_uv(x0, x1, win, T))
        (slats if kind == "slat" else pils).merge(md)
    z1 = H + EPS if to_ceiling else H - 0.05
    backing = _rbox_md(-0.5 * W + BACK_INSET, 0.5 * W - BACK_INSET, -(SLAT_T - GROOVE_D), EPS, -EPS, z1, 0.05)
    parts = [("SlatPanel_Boards", "oak_slat", slats, None, 0)]
    if pils.f:
        parts.append(("SlatPanel_Pilasters", "oak_slat", pils, None, 0))
    parts.append(("SlatPanel_Backing", "metal_black", backing, METAL, 0))
    return parts


# ============================================================ limestone floor
LS_TILE = 90.0          # square tile
LS_GAP = 0.2            # open joints (1 mm off the walls)
LS_T = 2.0              # tile thickness, top at z = 0
LS_EASE = 0.1           # 1 mm rounded tile edges
LS_LIP = 0.02           # lippage scale: tops between -0.032 and 0
LS_REPEAT = 180.0       # cm of floor per stone_floor UV unit: a full tile is a 0.5 x 0.5 window
SUB_TOP, SUB_BOT = -1.4, -2.6      # dark subfloor under the open joints


def _setout(lo, hi, pitch):
    """Joints strictly inside lo..hi of a grid of `pitch` set out from the centre line: a
    joint or a tile centre on it, whichever leaves the bigger (equal) cuts at both ends - so
    never less than half a tile, where the span is longer than one."""
    c = 0.5 * (lo + hi)
    cut = None
    for base in (c, c + 0.5 * pitch):
        k = (base - lo) % pitch
        if k < 1e-6 or k > pitch - 1e-6:
            k = pitch
        if cut is None or k > cut + 1e-9:
            cut = k
    out, i = [], 0
    while lo + cut + i * pitch < hi - 1e-6:
        out.append(lo + cut + i * pitch)
        i += 1
    return out


def limestone_layout(rect_cm, seed=0, tile=LS_TILE):
    """Cells of the straight-grid limestone floor over rect_cm: [dict(row, col, x0, x1, y0, y1
    (cell, joints on its edges), ox, oy (origin of the full tile it is cut from), u0, v0 (UV
    window origin), sym (one of the 8 symmetries of the square, furn_living._dihedral), dz,
    gx, gy (lippage plane))], row by row from (x0, y0)."""
    X0, Y0, X1, Y1 = _rect(rect_cm)
    T = float(tile)
    if not 30.0 <= T <= 200.0:
        raise ValueError("tile size %r out of range" % tile)
    xs = [X0] + _setout(X0, X1, T) + [X1]
    ys = [Y0] + _setout(Y0, Y1, T) + [Y1]
    rnd = _Rand(seed * 6151 + 29)
    cells = []
    for r in range(len(ys) - 1):
        for c in range(len(xs) - 1):
            x0, x1, y0, y1 = xs[c], xs[c + 1], ys[r], ys[r + 1]
            cells.append(dict(row=r, col=c, x0=x0, x1=x1, y0=y0, y1=y1,
                              ox=x0 if c > 0 else x1 - T, oy=y0 if r > 0 else y1 - T,
                              u0=rnd.uniform(0.0, 1.0), v0=rnd.uniform(0.0, 1.0),
                              sym=min(7, int(rnd.uniform(0.0, 8.0))),
                              dz=rnd.uniform(0.6, 1.0), gx=rnd.uniform(-1.0, 1.0), gy=rnd.uniform(-1.0, 1.0)))
    return cells


def _tile_uv(cell, T, rep):
    def uv(x, y):
        s, t = _dihedral(((x - cell["ox"]) / T, (y - cell["oy"]) / T), cell["sym"])
        return (cell["u0"] + s * T / rep, cell["v0"] + t * T / rep)
    return uv


def limestone_floor_parts(rect_cm, seed=0, tile=LS_TILE, gap=LS_GAP, lippage=LS_LIP, repeat=LS_REPEAT):
    """[(name, key, md, tile, smooth)]: the tiles (one mesh, own UVs on every face: tile
    None) and the dark subfloor. Each tile stands in its cell with gap/2 all round (also at
    the walls), its top on a plane up to 1.6 x lippage under z = 0, a support ring 0.3 mm in
    from a 1 mm quarter-round ease (3 steps), a second one 0.3 mm down the side, 2 cm thick.
    The top, the support strip and the ease take the tile's window of the `repeat` cm
    texture; the sides (in the joint) are mapped along the joint."""
    g, lip, T, rep = float(gap), float(lippage), float(tile), float(repeat)
    if not 0.1 <= g <= 1.0 or not 0.0 <= lip <= 0.1 or rep < T:
        raise ValueError("gap / lippage / repeat out of range")
    e, s = LS_EASE, SUPPORT
    rings = ([(e + s, 0.0)]
             + [(e * (1.0 - math.sin(math.radians(a))), e * (1.0 - math.cos(math.radians(a))))
                for a in (0.0, 30.0, 60.0, 90.0)]
             + [(0.0, e + s)])                       # (inset, drop) round the top edge
    md = _MD()
    for cell in limestone_layout(rect_cm, seed, T):
        x0, x1 = cell["x0"] + 0.5 * g, cell["x1"] - 0.5 * g
        y0, y1 = cell["y0"] + 0.5 * g, cell["y1"] - 0.5 * g
        xc, yc, hx, hy = 0.5 * (x0 + x1), 0.5 * (y0 + y1), 0.5 * (x1 - x0), 0.5 * (y1 - y0)
        dz = -lip * cell["dz"]
        gx, gy = 0.3 * lip * cell["gx"] / hx, 0.3 * lip * cell["gy"] / hy
        uv = _tile_uv(cell, T, rep)

        def top(x, y, dz=dz, gx=gx, gy=gy, xc=xc, yc=yc):
            return dz + gx * (x - xc) + gy * (y - yc)

        def side_uv(p, i, cell=cell):
            return (cell["u0"] + (p[1] if i % 2 else p[0]) / rep, cell["v0"] + p[2] / rep)

        R = []
        for inset, drop in rings:
            q = [(x0 + inset, y0 + inset), (x1 - inset, y0 + inset), (x1 - inset, y1 - inset),
                 (x0 + inset, y1 - inset)]
            R.append([md.add((x, y, top(x, y) - drop)) for x, y in q])
        R.append([md.add((x, y, -LS_T)) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))])
        md.face(tuple(R[0]), [uv(md.v[i][0], md.v[i][1]) for i in R[0]])
        for k in range(len(R) - 1):
            for i in range(4):
                i2 = (i + 1) % 4
                f = (R[k][i], R[k + 1][i], R[k + 1][i2], R[k][i2])
                if k < 4:                              # top support strip and the ease
                    md.face(f, [uv(md.v[j][0], md.v[j][1]) for j in f])
                else:                                  # down the side, in the joint
                    md.face(f, [side_uv(md.v[j], i) for j in f])
        bot = (R[-1][0], R[-1][3], R[-1][2], R[-1][1])
        md.face(bot, [uv(md.v[i][0], md.v[i][1]) for i in bot])
    X0, Y0, X1, Y1 = _rect(rect_cm)
    sub = _rbox_md(X0, X1, Y0, Y1, SUB_BOT, SUB_TOP, 0.05)
    return [("LimestoneFloor_Tiles", "stone_floor", md, None, 0),
            ("LimestoneFloor_Subfloor", "metal_black", sub, SUBFLOOR, 0)]


# ============================================================== flush skirting
FS_H = 6.0              # white face, floor to its top arris
FS_GAP = 1.0            # shadow line height
FS_RECESS = 1.0         # shadow line depth behind the wall face
FS_NOSE = 0.2           # plaster-stop nose above the shadow line
FS_FOOT = 1.3           # the face runs this far under the floor surface (clear of the subfloor's edge)
FS_TOP = FS_H + FS_GAP + FS_NOSE            # 7.2: the wall plaster starts here
FS_BACK = FS_RECESS + FS_NOSE               # 1.2: the wall's foot must sit this far back


def flush_skirting_profile(height=FS_H, gap=FS_GAP, recess=FS_RECESS):
    """Closed (u, z) section, u off the wall face (u <= 0 runs into the wall): the face flush
    with the plaster from under the floor up to a 1 mm top arris, the shadow line `recess`
    deep and `gap` high (0.5 mm fillets in its inner corners), the plaster-stop nose (1 mm
    arris) and the top the plaster bears on; back and foot buried."""
    h, gp, rc = float(height), float(gap), float(recess)
    if not 3.0 <= h <= 15.0 or not 0.5 <= gp <= 2.5 or not 0.5 <= rc <= 2.5:
        raise ValueError("flush skirting %r high, shadow %r x %r is out of range" % (height, gap, recess))
    top, back = h + gp + FS_NOSE, rc + FS_NOSE
    return _profile([
        (0.0, -FS_FOOT, 0.0),           # foot, under the floor surface
        (0.0, h, 0.1),                  # top arris of the white face
        (-rc, h, 0.05),                 # shadow line: floor / back (internal)
        (-rc, h + gp, 0.05),            # back / soffit (internal)
        (0.0, h + gp, 0.1),             # plaster-stop nose arris
        (0.0, top, 0.0),                # the plaster starts here
        (-back, top, 0.0),
        (-back, -FS_FOOT, 0.0),
    ])


def flush_skirting_md(rect_cm, openings=(), height=FS_H, gap=FS_GAP, recess=FS_RECESS):
    """The flush skirting round the wall faces rect_cm (scene cm), mitred at the corners and
    stopped square (closed ends) at openings [(side, a0, a1)]."""
    return _perimeter_sweep(rect_cm, flush_skirting_profile(height, gap, recess), openings)


def flush_skirting_parts(rect_cm, openings=(), height=FS_H, gap=FS_GAP, recess=FS_RECESS):
    return [("FlushSkirting", "paint_white", flush_skirting_md(rect_cm, openings, height, gap, recess), PAINT, 0)]


# ================================================================ slot diffuser
DF_LEN, DF_W = 140.0, 9.0
DF_FLANGE = 1.5         # face border on all four sides
DF_MULLION = 1.0        # divider between the two slots
DF_FACE = 0.25          # the face hangs 2.5 mm under the ceiling plane
DF_WEB = 0.12           # 1.2 mm webs lining the slots
DF_THROAT = 2.0         # webs and divider reach 2 cm up
DF_PLENUM = 12.0        # top of the plenum walls above the ceiling plane
DF_SHEET = 0.1          # plenum sheet
DF_CLEAR = 0.05         # plenum walls 0.5 mm clear of the webs
DF_FIN = (1.8, 0.08, 0.12, 30.0)       # blade chord, thickness, camber, tilt from vertical (deg)
DF_FIN_LIFT = 0.5       # blade's lower edge above the face
DF_HOLE_CLEAR = 0.2     # ceiling opening round the plenum


def _diffuser_dims(length, width):
    """(L, W, a, b, slot): a, b = half length / width of the frame opening (the webs' outer
    faces), slot = clear width of one slot."""
    L, W = float(length), float(width)
    if not 40.0 <= L <= 400.0 or not 7.5 <= W <= 16.0:
        raise ValueError("slot diffuser %r x %r is out of range" % (length, width))
    a, b = 0.5 * L - DF_FLANGE, 0.5 * W - DF_FLANGE
    return L, W, a, b, b - DF_WEB - 0.5 * DF_MULLION


def diffuser_frame_profile():
    """Closed (u, z) section of the frame, u from the opening's edge into the opening, z up
    from the ceiling plane: the 1.5 cm border 2.5 mm under the ceiling (1 mm arris outside,
    0.8 mm at the slot lip), the web lining the slot 2 cm up, the top 1 mm into the ceiling."""
    return _profile([
        (-DF_FLANGE, EPS, 0.0),
        (-DF_FLANGE, -DF_FACE, 0.1),
        (DF_WEB, -DF_FACE, 0.08),
        (DF_WEB, DF_THROAT, 0.03),
        (0.0, DF_THROAT, 0.03),
        (0.0, EPS, 0.03),
    ])


def fin_section(chord=DF_FIN[0], thick=DF_FIN[1], camber=DF_FIN[2], tilt=DF_FIN[3], n=8, k=8):
    """Closed counter-clockwise (y, z) section of a deflector blade about (0, 0): a curved
    blade (parabolic camber) `thick` thick with fully rounded edges (k steps of 180/k deg),
    its chord tilted `tilt` deg from vertical with the lower edge towards -Y (it throws the
    air to the front)."""
    hl, h, t = 0.5 * chord, float(camber), 0.5 * thick

    def frame(s):
        tx, ty = hl, -2.0 * h * s
        ln = math.hypot(tx, ty)
        return (s * hl, h * (1.0 - s * s)), (tx / ln, ty / ln), (-ty / ln, tx / ln)

    S = [-1.0 + 2.0 * i / n for i in range(n + 1)]
    pts = []
    for s in S:                                          # lower face, s = -1 .. 1
        p, _tg, nm = frame(s)
        pts.append((p[0] - t * nm[0], p[1] - t * nm[1]))
    for s, th0 in ((1.0, -0.5 * math.pi), (-1.0, 0.5 * math.pi)):
        p, tg, nm = frame(s)
        arc = [(p[0] + t * (math.cos(th0 + math.pi * m / k) * tg[0] + math.sin(th0 + math.pi * m / k) * nm[0]),
                p[1] + t * (math.cos(th0 + math.pi * m / k) * tg[1] + math.sin(th0 + math.pi * m / k) * nm[1]))
               for m in range(1, k)]
        if s > 0.0:                                      # round edge at the top, then the upper face
            pts += arc
            for s2 in reversed(S):
                q, _tg, nm2 = frame(s2)
                pts.append((q[0] + t * nm2[0], q[1] + t * nm2[1]))
        else:                                            # round edge at the bottom
            pts += arc
    sa, ca = math.sin(math.radians(tilt)), math.cos(math.radians(tilt))
    return [(a * sa - b * ca, a * ca + b * sa) for a, b in pts]


def slot_diffuser_hole(length=DF_LEN, width=DF_W):
    """(x0, x1, y0, y1): the opening the ceiling needs at the diffuser (local cm): 2 mm clear
    of the plenum, its edges hidden more than 1 cm behind the frame's border."""
    _L, _W, a, b, _slot = _diffuser_dims(length, width)
    m = DF_CLEAR + DF_SHEET + 0.05 + DF_HOLE_CLEAR
    return (-(a + m), a + m, -(b + m), b + m)


def slot_diffuser_parts(length=DF_LEN, width=DF_W, frame_key="metal_steel"):
    """[(name, key, md, tile, smooth)] of the slot diffuser (see build_slot_diffuser)."""
    L, W, a, b, slot = _diffuser_dims(length, width)
    if frame_key not in kit.MAT_KEYS:
        raise KeyError("unknown material key %r" % frame_key)
    outline = [(-a, -b), (a, -b), (a, b), (-a, b)]
    frame = [_sweep(outline, diffuser_frame_profile(), _xyz, closed=True)]
    ai = a - DF_WEB                                      # the end webs' inner faces
    frame.append(_rbox_md(-ai - 0.05, ai + 0.05, -0.5 * DF_MULLION, 0.5 * DF_MULLION, -DF_FACE, DF_THROAT, 0.08))
    sec = fin_section()
    zmin = min(z for _y, z in sec)
    zc = -DF_FACE + DF_FIN_LIFT - zmin
    if zc + max(z for _y, z in sec) > DF_THROAT - 0.05 or max(abs(y) for y, _z in sec) > 0.5 * slot - 0.1:
        raise ValueError("deflector blade does not fit the slot")
    fins = []
    for sy in (-1.0, 1.0):
        yc = sy * (0.5 * DF_MULLION + 0.5 * slot)
        fins.append(_sweep([(-ai - 0.05, yc), (ai + 0.05, yc)], [(y, z + zc) for y, z in sec], _xyz))
    ia, ib = a + DF_CLEAR, b + DF_CLEAR
    plenum = [_sweep([(-ia, -ib), (ia, -ib), (ia, ib), (-ia, ib)],
                     [(0.0, 0.05), (0.0, DF_PLENUM), (-DF_SHEET, DF_PLENUM), (-DF_SHEET, 0.05)], _xyz, closed=True)]
    oa, ob = ia + DF_SHEET + 0.05, ib + DF_SHEET + 0.05
    plenum.append(_rbox_md(-oa, oa, -ob, ob, DF_PLENUM - 0.1, DF_PLENUM + 0.05, 0.03))
    return [("SlotDiffuser_Frame", frame_key, _merge(frame), METAL, 0),
            ("SlotDiffuser_Fins", "metal_steel", _merge(fins), METAL, 0),
            ("SlotDiffuser_Plenum", "metal_black", _merge(plenum), METAL, 0)]


# ================================================================ Max wrappers
_UV_SCALE = {"oak_slat": OAK_TILE, "stone_floor": LS_REPEAT}


def _autosmooth(node, deg=40.0):
    """Smooth modifier, auto at deg: fillets shade smooth, flats and mitres stay crisp
    (_build puts every face in smoothing group 1)."""
    try:
        sm = rt.Smooth()
        kit.setp(sm, "autoSmooth", True)
        kit.setp(sm, "threshold", float(deg))
        rt.addModifier(node, sm)
    except Exception:
        pass
    return node


def _nodes(parts):
    """Max nodes for (name, key, md, tile, smooth) parts; tile None: the cage's own UVs (on
    every face) are written to map channel 1 and kept (maptype None)."""
    nodes = []
    for name, key, md, tile, smooth in parts:
        node = FL._build(md, name, _UV_SCALE.get(key, 100.0) if tile is None else None)
        _autosmooth(node)
        if smooth:
            kit.soften(node, None, smooth)
        nodes.append(kit.part(node, key, None, None) if tile is None else kit.part(node, key, tile))
    return nodes


def build_slat_panel(width, height, seed=0, pilaster_every=0, to_ceiling=True, pilaster_w=PIL_W,
                     tile=OAK_TILE):
    """Fluted oak slat panel width x height (see the module doc); origin bottom centre on the
    wall face, boards in front (-Y): kit.place it on the wall with its front to the room."""
    return kit.group("SlatPanel", _nodes(slat_panel_parts(width, height, seed, pilaster_every, to_ceiling,
                                                          pilaster_w, tile)))


def build_limestone_floor(rect_cm, seed=0, tile=LS_TILE, gap=LS_GAP, lippage=LS_LIP):
    """90 x 90 limestone tiles over rect_cm, top at z = 0; already in place (leave the group at
    the origin)."""
    return kit.group("LimestoneFloor", _nodes(limestone_floor_parts(rect_cm, seed, tile, gap, lippage)))


def build_flush_skirting(rect_cm, openings=(), height=FS_H, gap=FS_GAP, recess=FS_RECESS):
    """Flush skirting with a shadow line round the wall faces rect_cm, stopped at openings;
    already in place. The scene's plaster stops at FS_TOP, its foot set back FS_BACK."""
    return kit.group("FlushSkirting", _nodes(flush_skirting_parts(rect_cm, openings, height, gap, recess)))


def build_slot_diffuser(length=DF_LEN, width=DF_W, frame_key="metal_steel"):
    """Recessed 2-slot linear diffuser hanging from z = 0 (the ceiling plane), throwing to -Y;
    the ceiling needs the opening slot_diffuser_hole(length, width)."""
    return kit.group("SlotDiffuser", _nodes(slot_diffuser_parts(length, width, frame_key)))


def preview():
    """Every piece in a 5 x 4 m test room with a 280 cm ceiling: the limestone floor and the
    flush skirting round it (stopped at a door and behind the panel), the slat panel with
    pilasters on the north wall, the diffuser on the ceiling in front of it."""
    room = (-250.0, -200.0, 250.0, 200.0)
    build_limestone_floor(room, seed=1)
    build_flush_skirting(room, [("s", -60.0, 60.0), ("n", -160.0, 160.0)])
    kit.place(build_slat_panel(320.0, 280.0, seed=2, pilaster_every=6), 0.0, 200.0, 0.0, 0.0)
    kit.place(build_slot_diffuser(), 0.0, 150.0, 280.0, 0.0)
