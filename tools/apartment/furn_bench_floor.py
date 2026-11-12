"""Pine floorboards for the MatForge benchmark living room (3ds Max 2026, V-Ray 7).

A drop-in for bench1_scene.build_pine_floor. That floor laid every board
21 cm wide, its top one flat quad at z = 0, every gap 2 mm: the north
window's reflection ran as one unbroken streak across many boards and the
floor read as laminate. Here, as in an old pine floor that has shrunk and
cupped:

  * every row has its own width, 17-25 cm (the last row ripped to fit);
  * every board edge stands back from its seam by its own half-gap of
    0.5-2 mm, so the gaps run 1-4 mm and change at every end joint;
  * every board top is 6 strips across its width, cupped (its long edges
    0.6-1.0 mm above its middle, the profile averaging the board's height),
    raised or sunk by up to 0.4 mm and rolled by up to 0.1 deg about its
    long axis. The strips share smoothing group 1, so the cup shades as one
    curve while the eased edges stay crisp; the edges' feet ride with the
    top, the bottom stays flat on the subfloor.

Kept from today's floor: boards along Y with staggered ends (the first board
of a row 40-300 cm long, then 180-420 cm), each board its own window into the
pine photo (60 x 90 cm of floor per repeat, grain along V, turned end for end
at random), one material ID per board, 2-6 (bench1_scene.PINE_TINTS[1:] via
builder.build_variants), 2 mm eased edges, sides 2.2 cm down to the black
subfloor (the dark void in the gaps). Those draws come from
random.Random(seed) in today's order and the variation has a stream of its
own, so pine_floor_mesh(..., **LEGACY) lays today's floor exactly - except a
ripped stub too thin to keep a top (under 0.65 cm), which joins its neighbour.

  build_pine_floor(name, x0, x1, y0, y1, seed, **variation)
        the boards over x0..x1, y0..y1 (scene cm), their tops at z = 0
        (+1.3 / -0.8 mm), as one mesh FloorPine_<name> (material key
        planks_pine, its own UVs, so finished with no UVW map) and the box
        Subfloor_<name> (z -2.6..-2.2); returns the mesh node, as
        bench1_scene.build_pine_floor does. variation: pine_floor_mesh
        keywords (**LEGACY for today's floor).

The mesh comes from the pure-Python pine_floor_mesh(...) - vertices, faces,
face material IDs, UVs, smoothing groups and the board layout - so it is
testable without 3ds Max (tests/test_bench_floor_geom.py); build_pine_floor
only hands it to Max.
"""
import math
import random
from collections import namedtuple

from pymxs import runtime as rt

# ------------------------------------------------------------ kept from today's floor
PINE_U_CM, PINE_V_CM = 60.0, 90.0      # cm of floor per photo repeat across / along the grain
N_TINTS = 5                            # face IDs 2..6 (bench1_scene.PINE_TINTS; ID 1, the base, unused)
EASE = 0.2                             # cm: the 45-degree eased edge
DEPTH = 2.2                            # cm: board sides down to the subfloor's top
FIRST_L = (40.0, 300.0)                # cm: the first board of a row (staggers the joints)
NEXT_L = (180.0, 420.0)                # cm: the boards after it

# ------------------------------------------------------------ the variation
WIDTHS = (17.0, 25.0)                  # cm, per row
HALF_GAP = (0.05, 0.2)                 # cm, per board edge: how far it stands back from its seam
STRIPS = 6                             # strips across a board top
CUP = (0.06, 0.10)                     # cm: the top's long edges above its middle
LIFT = 0.04                            # cm: +- per board
TILT = 0.1                             # deg: +- per board, rolled about its long axis
MIN_RIP = 8.0                          # cm: a ripped last row / last board under this joins its neighbour

# today's floor exactly: 21 cm rows, 2 mm gaps, flat tops, ripped stubs kept
LEGACY = dict(widths=(21.0, 21.0), half_gap=(0.1, 0.1), strips=1, cup=(0.0, 0.0), lift=0.0, tilt=0.0,
              min_rip=0.0)

FloorMesh = namedtuple("FloorMesh", "verts faces ids tvs smooth boards")
# a board: row index; cell (x0, x1, y0, y1) between its seam lines; box (X0, X1, Y0, Y1) its
# footprint (the cell less its half-gaps); uv (u0, u1, v0, v1) its window into the photo as
# drawn (u1 < u0 and v1 < v0 when turned end for end); mat its face ID; lift cm, tilt deg,
# cup cm; verts, faces: (first, count) in the FloorMesh lists
Board = namedtuple("Board", "row cell box uv mat lift tilt cup verts faces")


# ================================================================== helpers
def _quad(faces, a, b, c, d, verts, out):
    """Two triangles a-b-c, a-c-d (0-based vertex ids) wound to face `out`
    (apartment_scene._quad, copied: that module only loads inside Max)."""
    pa, pb, pc = verts[a], verts[b], verts[c]
    u = [pb[i] - pa[i] for i in range(3)]
    v = [pc[i] - pa[i] for i in range(3)]
    n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    if n[0] * out[0] + n[1] * out[1] + n[2] * out[2] >= 0.0:
        faces += [(a, b, c), (a, c, d)]
    else:
        faces += [(a, c, b), (a, d, c)]


def _ring(first, last, extra, j, n):
    """Vertex ids of one edge of a board, station 0..n: its corners (today's
    12-vertex box) and between them the extra stations, six vertices each."""
    return [first] + [extra + 6 * (k - 1) + j for k in range(1, n)] + [last]


def _row_seams(x0, x1, widths, rnd, rip):
    """Seam lines x0 .. x1 between the rows: each row's width drawn from
    `widths`, the last row ripped to fit. A ripped row narrower than rip
    joins the row before it - one board if that is no wider than widths[1],
    else two equal ones."""
    xs = [x0]
    while xs[-1] < x1 - 1e-6:
        xs.append(min(xs[-1] + rnd.uniform(*widths), x1))
    if len(xs) > 2 and xs[-1] - xs[-2] < rip:
        rest = xs[-1] - xs[-3]
        del xs[-2]
        if rest > widths[1]:
            xs.insert(-1, xs[-2] + 0.5 * rest)
    return xs


# ================================================================== the boards
def pine_floor_mesh(x0, x1, y0, y1, seed, widths=WIDTHS, half_gap=HALF_GAP, strips=STRIPS, cup=CUP,
                    lift=LIFT, tilt=TILT, min_rip=MIN_RIP, n_tints=N_TINTS):
    """The boards over x0..x1, y0..y1 (cm), running along Y, as a FloorMesh:
    verts [(x, y, z)], faces [(a, b, c)] (0-based), ids [material ID per
    face], tvs [(u, v)] one per vertex (the map faces repeat the mesh faces),
    smooth [smoothing group per face], boards [Board]. widths, half_gap, cup:
    (lo, hi) cm; lift (cm) and tilt (deg): +- bounds; strips across each top;
    min_rip: the shortest ripped piece (see _row_seams), for rows and for the
    last board of a row alike."""
    if x1 - x0 <= 0.0 or y1 - y0 <= 0.0:
        raise ValueError("empty floor %r" % ((x0, x1, y0, y1),))
    n = int(strips)
    if n < 1:
        raise ValueError("strips must be 1 or more, not %r" % (strips,))
    rnd = random.Random(seed)                  # today's draws, in today's order
    var = random.Random(7919 * seed + 101)     # the variation's own, so today's sequence stays intact
    c = EASE
    # a ripped piece must keep a top between its eased edges and half-gaps
    rip = max(min_rip, 2.0 * (half_gap[1] + c) + 0.05)
    verts, faces, ids, tvs, smooth, boards = [], [], [], [], [], []
    xs = _row_seams(x0, x1, widths, var, rip)
    for row, (x, xb) in enumerate(zip(xs, xs[1:])):
        y = y0
        L = rnd.uniform(*FIRST_L)              # the first board in each row staggers the joints
        while y < y1 - 1e-6:
            yb = min(y + L, y1)
            if y1 - yb < rip:                  # no stub at the far wall: this board runs on to it
                yb = y1
            # its own window into the photo: the photo's width across the board at a random
            # offset, the grain along it (90 cm a repeat), turned end for end at random
            u0 = rnd.uniform(0.0, 1.0)
            u1 = u0 + (xb - x) / PINE_U_CM
            v0 = rnd.uniform(0.0, 1.0)
            v1 = v0 + (yb - y) / PINE_V_CM
            if rnd.random() < 0.5:
                u0, u1, v0, v1 = u1, u0, v1, v0
            mat = 2 + rnd.randrange(n_tints)
            hl, hr, hf, hb = [var.uniform(*half_gap) for _ in range(4)]
            X0, X1, Y0, Y1 = x + hl, xb - hr, y + hf, yb - hb
            if X1 - X0 <= 2.0 * c or Y1 - Y0 <= 2.0 * c:
                raise ValueError("floor %r too small for a board" % ((x0, x1, y0, y1),))
            dz, roll, cupb = var.uniform(-lift, lift), var.uniform(-tilt, tilt), var.uniform(*cup)
            # n + 1 stations across the board, -X to +X: on the top (between the eased edges)
            # and at the edges' feet, each lifted by the board's lift, roll and cup (a parabola
            # averaging zero across the top). The feet ride with the top, so the eased edges
            # stay 45 degrees; the bottom stays flat on the subfloor.
            k_t, xc = math.tan(math.radians(roll)), 0.5 * (X0 + X1)
            xt = [X0 + c] + [X0 + c + (X1 - X0 - 2.0 * c) * k / n for k in range(1, n)] + [X1 - c]
            xm = [X0] + [X0 + (X1 - X0) * k / n for k in range(1, n)] + [X1]
            d = [dz + k_t * (xt[k] - xc) + cupb * ((2.0 * k / n - 1.0) ** 2 - 1.0 / 3.0) for k in range(n + 1)]
            du = c / PINE_U_CM * (1.0 if u1 > u0 else -1.0)
            dv = c / PINE_V_CM * (1.0 if v1 > v0 else -1.0)
            ut = [u0 + du] + [u0 + du + (u1 - u0 - 2.0 * du) * k / n for k in range(1, n)] + [u1 - du]
            um = [u0] + [u0 + (u1 - u0) * k / n for k in range(1, n)] + [u1]
            # today's 12 vertices first (top, edge feet, bottom; -Y +X / +Y corners), then the
            # stations between the corners
            base = len(verts)
            verts += [(xt[0], Y0 + c, d[0]), (xt[n], Y0 + c, d[n]), (xt[n], Y1 - c, d[n]), (xt[0], Y1 - c, d[0]),
                      (X0, Y0, d[0] - c), (X1, Y0, d[n] - c), (X1, Y1, d[n] - c), (X0, Y1, d[0] - c),
                      (X0, Y0, -DEPTH), (X1, Y0, -DEPTH), (X1, Y1, -DEPTH), (X0, Y1, -DEPTH)]
            uv_out = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
            tvs += [(ut[0], v0 + dv), (ut[n], v0 + dv), (ut[n], v1 - dv), (ut[0], v1 - dv)] + uv_out + uv_out
            for k in range(1, n):
                verts += [(xt[k], Y0 + c, d[k]), (xt[k], Y1 - c, d[k]), (xm[k], Y0, d[k] - c),
                          (xm[k], Y1, d[k] - c), (xm[k], Y0, -DEPTH), (xm[k], Y1, -DEPTH)]
                tvs += [(ut[k], v0 + dv), (ut[k], v1 - dv), (um[k], v0), (um[k], v1), (um[k], v0), (um[k], v1)]
            t, m, b, e = base, base + 4, base + 8, base + 12
            tf, tb = _ring(t, t + 1, e, 0, n), _ring(t + 3, t + 2, e, 1, n)
            mf, mb = _ring(m, m + 1, e, 2, n), _ring(m + 3, m + 2, e, 3, n)
            bf, bb = _ring(b, b + 1, e, 4, n), _ring(b + 3, b + 2, e, 5, n)
            n0 = len(faces)
            for k in range(n):                 # the top, in strips
                _quad(faces, tf[k], tf[k + 1], tb[k + 1], tb[k], verts, (0, 0, 1))
            # round the board as today: eased edge, then side, on the -Y end, +X, +Y end, -X
            for k in range(n):
                _quad(faces, tf[k], tf[k + 1], mf[k + 1], mf[k], verts, (0, -1, 1))
            for k in range(n):
                _quad(faces, mf[k], mf[k + 1], bf[k + 1], bf[k], verts, (0, -1, 0))
            _quad(faces, tf[n], tb[n], mb[n], mf[n], verts, (1, 0, 1))
            _quad(faces, mf[n], mb[n], bb[n], bf[n], verts, (1, 0, 0))
            for k in range(n, 0, -1):
                _quad(faces, tb[k], tb[k - 1], mb[k - 1], mb[k], verts, (0, 1, 1))
            for k in range(n, 0, -1):
                _quad(faces, mb[k], mb[k - 1], bb[k - 1], bb[k], verts, (0, 1, 0))
            _quad(faces, tb[0], tf[0], mf[0], mb[0], verts, (-1, 0, 1))
            _quad(faces, mb[0], mf[0], bf[0], bb[0], verts, (-1, 0, 0))
            for k in range(n):                 # the bottom, on the subfloor
                _quad(faces, bf[k], bb[k], bb[k + 1], bf[k + 1], verts, (0, 0, -1))
            nf = len(faces) - n0
            ids += [mat] * nf
            # one flat quad (today's top) keeps today's group 0
            smooth += [1 if n > 1 else 0] * (2 * n) + [0] * (nf - 2 * n)
            boards.append(Board(row, (x, xb, y, yb), (X0, X1, Y0, Y1), (u0, u1, v0, v1), mat, dz, roll, cupb,
                                (base, len(verts) - base), (n0, nf)))
            y = yb
            L = rnd.uniform(*NEXT_L)
    return FloorMesh(verts, faces, ids, tvs, smooth, boards)


# ================================================================ Max wrapper
def _maxscript(name, fm):
    """MAXScript making the mesh FloorPine_<name>: one map vertex per vertex
    (the map faces repeat the mesh faces), a material ID and a smoothing
    group per face."""
    return ('(pfm = mesh name:"FloorPine_%s" vertices:#(%s) faces:#(%s) tverts:#(%s)\n'
            'buildTVFaces pfm\npfi = #(%s)\npfs = #(%s)\n'
            'for f = 1 to pfm.numfaces do (setTVFace pfm f (getFace pfm f); setFaceMatID pfm f pfi[f]; '
            'setFaceSmoothGroup pfm f pfs[f])\nupdate pfm\npfm)'
            % (name, ",".join("[%.4f,%.4f,%.4f]" % p for p in fm.verts),
               ",".join("[%d,%d,%d]" % (a + 1, b + 1, c + 1) for a, b, c in fm.faces),
               ",".join("[%.5f,%.5f,0]" % tv for tv in fm.tvs), ",".join(str(i) for i in fm.ids),
               ",".join(str(s) for s in fm.smooth)))


def build_pine_floor(name, x0, x1, y0, y1, seed, **variation):
    """Boards along Y over x0..x1, y0..y1 (cm), their tops at z = 0 (+1.3 /
    -0.8 mm), and the black subfloor under them; returns the board mesh.
    variation: pine_floor_mesh keywords (**LEGACY: today's floor)."""
    import bench_common as B   # the scene's own, loaded by it inside Max: A.finish, box
    node = rt.execute(_maxscript(name, pine_floor_mesh(x0, x1, y0, y1, seed, **variation)))
    B.A.finish(node, "planks_pine", None, None)
    B.box("Subfloor_" + name, x0, x1, y0, y1, -2.6, -DEPTH, "subfloor", 100.0)
    return node
