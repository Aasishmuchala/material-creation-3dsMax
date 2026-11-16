"""MatForge benchmark 1 - a bright pre-war living room (runs inside 3ds Max).

The style of the user's first Pinterest reference, in an own composition:
white plaster walls under a crown cornice, a tall French window with a sheer
curtain over a column radiator, a panelled door open onto a sunlit room next
door, pale pine boards, a kilim, a black leather lounge chair on a satin
steel frame, a black steel console dressed with books, glass and a lamp, a
bird of paradise and a bushy plant in stoneware planters, a framed ink-wash
print. The pieces come from furn_bench_*.py and bench_arch.py; EVERY material
is made by MatForge (maxplugin.builder) from a forged Runway reference,
through bench_common.matforge().

Plan (Max cm, Z up): the room is x 0..500, y 0..640, ceiling 330; the camera
stands near the south end looking north-north-west. North and east walls are
exterior (40 cm), each with a French window; the west wall (20 cm) has the
door to the room next door (x -420..-20, y 300..640), whose south window
takes the afternoon sun. The sun never reaches the north window, so the main
room is lit by sky light alone, soft and even as in the reference.

Environment (set by run_bench.py):
  MF_APT_OUT      output folder
  MF_APT_QUALITY  "draft" | "preview" | "final"
  MF_APT_CAMS     comma list of camera keys (default: all in CAMS)
  MF_APT_SAVE     optional .max path to save the built scene
  MF_BENCH_PROBE  .json path: build the geometry only and dump the world
                  boxes of the placed pieces there (no materials, no renders)
"""
import importlib
import math
import os
import random
import sys
import time

from pymxs import runtime as rt

HERE = os.path.join(r"C:\Users\aasis\matforge", "tools", "apartment")
if HERE not in sys.path:
    sys.path.insert(0, HERE)
_fresh = "bench_common" not in sys.modules
import bench_common as B  # noqa: E402
if not _fresh:
    importlib.reload(B)          # a Max session that ran a benchmark before

A, kit, builder, log = B.A, B.kit, B.builder, B.log
import bench_arch  # noqa: E402  (after B: bound to the kit A reloaded)
import furn_bench_chair  # noqa: E402
import furn_bench_console  # noqa: E402
import furn_bench_floor  # noqa: E402
import furn_bench_plants  # noqa: E402

for _m in (bench_arch, furn_bench_chair, furn_bench_console, furn_bench_floor, furn_bench_plants):
    importlib.reload(_m)

H = 330.0                       # ceiling height, cm (pre-war)

# ------------------------------------------------------------ MatForge materials
# Keys the benchmark pieces use that the apartment maps elsewhere, and the new
# forged references (white plaster, pine, kilim, black leather, voile,
# stoneware, strelitzia and rubber-plant leaves, waxed canvas).
# (lab material id, metal[, class])
A.MATS.update({
    "wall_paint": ("white_plaster", None), "ceiling": ("white_plaster", None),
    # old flat-sawn pine with bold grain and knots, soaped: an oiled floor's
    # broad sheen (the rift-sawn photo's pinstripes averaged to flat colour
    # and the lacquer streaked the window across the boards like laminate)
    "planks_pine": ("pine_flatsawn", None, "wood_floor_oiled"), "subfloor": ("black_plastic", None),
    # the reference's rug is a heathered hand-woven wool with a few soft
    # cream motifs; the kilim photo came out crisp and saturated
    "rug": ("melange_rug", None), "leather": ("black_leather", None),
    # see-through voile (the sheer class alone, translucency only, rendered
    # an opaque white sheet; the lamp shade keeps that class)
    "curtain": ("sheer_voile", None, "fabric_voile"),
    # dark waxy leaves photographed on grey (the first photos, exposed for a
    # white backdrop, rendered the blades neon lime at 4-5x a real leaf)
    "pot_matte": ("matte_stoneware", None), "leaf_card": ("strelitzia_dark", None),
    "leaf_card_small": ("rubber_dark", None),
    # flat waxed canvas, no fibre sheen (the creased photo read as cork)
    "canvas_bag": ("waxed_canvas_flat", None),
    # brushed satin stainless for the chair frame (satin_stainless's 0.2
    # roughness map mirrored the rug like chrome)
    "metal_steel": ("brushed_steel", "stainless_steel"),
    # the rug's plain-weave end bands, selvedge cords and warp fringe: undyed
    # cotton (on white bedding cotton the fringe was a bright comb)
    "rug_band": ("ecru_cotton", None), "rug_fringe": ("ecru_cotton", None),
})
kit.MAT_KEYS.setdefault("rug_band", "flat-weave rug's plain-weave end bands and selvedge")
kit.MAT_KEYS.setdefault("rug_fringe", "flat-weave rug's knotted warp fringe")

# ------------------------------------------------------------ plan (Max cm)
ROOM = (0.0, 0.0, 500.0, 640.0)            # x0, y0, x1, y1 of the main room's wall faces
NEXT = (-420.0, 300.0, -20.0, 640.0)       # the room next door
EXT_T, INT_T = 40.0, 20.0                  # exterior / interior wall thickness
WIN_W, WIN_H, WIN_SILL = 150.0, 280.0, 1.0  # French windows (frame), standing on a 1 cm threshold
WIN_IN = 6.0                               # frame face set back from the wall's outer face
N_WIN_X = 310.0                            # centre of the north window
E_WIN_Y = 430.0                            # centre of the east window
S_WIN_X = -250.0                           # centre of the window next door (its south wall)
DOOR_Y, DOOR_W, DOOR_H = 545.0, 90.0, 240.0  # leaf; the structural opening is 5.6 / 3.6 cm larger
DOOR_SWING = 95.0                          # open into the room next door
TOP = H + 15.0                             # walls run up into the ceiling slab


def door_opening():
    """The door's structural opening, open down to the wall base: the boards
    run through it (a plaster breast topping out at z 0 showed in the board
    joints and fought with the board tops)."""
    hw = (DOOR_W + 5.6) / 2.0
    return DOOR_Y - hw, DOOR_Y + hw, -3.0, DOOR_H + 3.6


# The reference is lit from behind its subject: the window at the back and
# the doorway. An east window at the chair's depth, out of frame right, lit
# the chair, plants, console and print head-on and the white room bounced it
# back from the left and behind the camera: the final read flat (frame p5/p95
# 0.14/0.53 against 0.01/0.90), the floor with no falloff toward the camera.
EAST_WINDOW = False


def build_shell():
    """Walls with their openings, ceilings, thresholds, outside ground."""
    x0, y0, x1, y1 = ROOM
    nx0, ny0, nx1, ny1 = NEXT
    win = lambda c: (c - WIN_W / 2.0, c + WIN_W / 2.0, 0.0, WIN_SILL + WIN_H)
    # north wall: both rooms, the main room's French window
    B.wall("WallN", "x", y1, y1 + EXT_T, nx0 - EXT_T, x1 + EXT_T, TOP, [win(N_WIN_X)])
    B.wall("WallE", "y", x1, x1 + EXT_T, y0 - INT_T, y1, TOP, [win(E_WIN_Y)] if EAST_WINDOW else [])
    B.wall("WallS", "x", y0 - INT_T, y0, x0 - INT_T, x1, TOP)
    B.wall("WallW", "y", x0 - INT_T, x0, y0, y1, TOP, [door_opening()])
    # the room next door: south wall (exterior, its window) and west wall
    B.wall("NextS", "x", ny0 - EXT_T, ny0, nx0 - EXT_T, x0 - INT_T, TOP, [win(S_WIN_X)])
    B.wall("NextW", "y", nx0 - EXT_T, nx0, ny0, ny1, TOP)
    for name, (a0, b0, a1, b1) in (("Ceiling_main", ROOM), ("Ceiling_next", NEXT)):
        B.box(name, a0, a1, b0, b1, H, TOP, "ceiling")
    # timber thresholds in the window reveals, the frames stand on them
    B.box("Threshold_N", N_WIN_X - WIN_W / 2.0, N_WIN_X + WIN_W / 2.0, y1, y1 + EXT_T - WIN_IN, -2.0, WIN_SILL,
          "paint_white", 60.0)
    if EAST_WINDOW:
        B.box("Threshold_E", x1, x1 + EXT_T - WIN_IN, E_WIN_Y - WIN_W / 2.0, E_WIN_Y + WIN_W / 2.0, -2.0,
              WIN_SILL, "paint_white", 60.0)
    B.box("Threshold_S", S_WIN_X - WIN_W / 2.0, S_WIN_X + WIN_W / 2.0, ny0 - EXT_T + WIN_IN, ny0, -2.0, WIN_SILL,
          "paint_white", 60.0)
    # a raised ground floor (bel etage): the street lies 1.5 m down, as the
    # street-level backdrop photo beyond shows it
    g = rt.Plane(width=8000, length=8000, pos=rt.Point3(250, 300, -150))
    g.name = "Ground_Far"
    A.finish(g, "ground", 150)
    # (A GI-only "sunlit facade" box across the street was tried here to
    # brighten the north window: it added 10 % to the back wall and shadowed
    # the whole north sky, which is the window's real light. Removed.)


# ------------------------------------------------------------ pine boards
# The pine photo is one continuous board face 60 cm across (the lab prompt's
# frame), grain along V. Each board takes its own window of it: 21 cm of
# the photo's width at a random offset, the grain stretched 1.5x along the
# board so a 2-4 m board does not repeat its knots every 60 cm, turned end
# for end at random. Real pine floors shrink: 2 mm gaps, 2 mm eased edges, a
# dark void below.
PINE_W = 21.0
PINE_U_CM, PINE_V_CM = 60.0, 90.0          # cm of floor per photo repeat across / along the grain
# every board its own shade (brightness %, saturation %, hue deg). The
# soaped flat-sawn pine photo is a pale honey (albedo lum 0.50, r/g 1.46,
# b/g 0.64), already the hue of the reference's aged boards but brighter
# (they read 0.18 in the shaded foreground against a 0.47 wall: an albedo
# near 0.35). So each board sits 16-30 % darker, loses 4-14 % of its
# saturation and leans a degree or two toward yellow, by its own amount:
# real boards differ. ID 1 (the untouched base) is left unused
# (at -4..-14 % saturation the preview's boards read a saturated yellow
# beside the reference's greyed honey: about a third of the colour goes)
# (the final at -26..-36 % still read as fresh yellow pine with boards of
# very different tone beside the reference's aged, greyed, even floor:
# nearly half the colour goes and the boards sit closer together)
PINE_TINTS = ((0.0, 0.0, 0.0), (-12.0, -46.0, 1.0), (-16.0, -42.0, 2.0), (-9.0, -50.0, 0.0), (-18.0, -44.0, 1.5),
              (-8.0, -40.0, 2.5))


def build_pine_floor(name, x0, x1, y0, y1, seed):
    """Boards along Y over x0..x1, y0..y1 (cm), top face at z = 0."""
    rnd = random.Random(seed)
    c, g = 0.2, 0.1                            # cm: eased edge, half the gap
    verts, tvs, faces, ids = [], [], [], []
    x = x0
    while x < x1 - 1e-6:
        xb = min(x + PINE_W, x1)
        y = y0
        L = rnd.uniform(40.0, 300.0)           # the first board in each row staggers the joints
        while y < y1 - 1e-6:
            yb = min(y + L, y1)
            u0 = rnd.uniform(0.0, 1.0)
            u1 = u0 + (xb - x) / PINE_U_CM
            v0 = rnd.uniform(0.0, 1.0)
            v1 = v0 + (yb - y) / PINE_V_CM
            if rnd.random() < 0.5:
                u0, u1, v0, v1 = u1, u0, v1, v0
            du = c / PINE_U_CM * (1.0 if u1 > u0 else -1.0)
            dv = c / PINE_V_CM * (1.0 if v1 > v0 else -1.0)
            X0, X1, Y0, Y1 = x + g, xb - g, y + g, yb - g
            base = len(verts)
            verts += [(X0 + c, Y0 + c, 0.0), (X1 - c, Y0 + c, 0.0), (X1 - c, Y1 - c, 0.0), (X0 + c, Y1 - c, 0.0),
                      (X0, Y0, -c), (X1, Y0, -c), (X1, Y1, -c), (X0, Y1, -c),
                      (X0, Y0, -2.2), (X1, Y0, -2.2), (X1, Y1, -2.2), (X0, Y1, -2.2)]
            uv_out = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
            tvs += [(u0 + du, v0 + dv), (u1 - du, v0 + dv), (u1 - du, v1 - dv), (u0 + du, v1 - dv)]
            tvs += uv_out + uv_out
            t, m, b = base, base + 4, base + 8
            n0 = len(faces)
            A._quad(faces, t, t + 1, t + 2, t + 3, verts, (0, 0, 1))
            for i, out in ((0, (0, -1, 1)), (1, (1, 0, 1)), (2, (0, 1, 1)), (3, (-1, 0, 1))):
                i2 = (i + 1) % 4
                A._quad(faces, t + i, t + i2, m + i2, m + i, verts, out)                    # eased edge
                A._quad(faces, m + i, m + i2, b + i2, b + i, verts, (out[0], out[1], 0))    # side
            A._quad(faces, b, b + 3, b + 2, b + 1, verts, (0, 0, -1))
            ids += [2 + rnd.randrange(len(PINE_TINTS) - 1)] * (len(faces) - n0)
            y = yb
            L = rnd.uniform(180.0, 420.0)
        x = xb
    fmt = lambda pts: ",".join("[%.3f,%.3f,%.3f]" % tuple(p) for p in pts)
    node = rt.execute(
        '(m = mesh name:"FloorPine_%s" vertices:#(%s) faces:#(%s) tverts:#(%s)\n'
        'buildTVFaces m\nids = #(%s)\n'
        'for f = 1 to m.numfaces do (setTVFace m f (getFace m f); setFaceMatID m f ids[f]; '
        'setFaceSmoothGroup m f 0)\nupdate m\nm)'
        % (name, fmt(verts), ",".join("[%d,%d,%d]" % (a + 1, b_ + 1, c_ + 1) for a, b_, c_ in faces),
           ",".join("[%.5f,%.5f,0]" % tv for tv in tvs), ",".join(str(i) for i in ids)))
    A.finish(node, "planks_pine", None, None)
    B.box("Subfloor_" + name, x0, x1, y0, y1, -2.6, -2.2, "subfloor", 100.0)
    return node


def build_architecture():
    x0, y0, x1, y1 = ROOM
    nx0, ny0, nx1, ny1 = NEXT
    build_shell()
    # old boards: 17-25 cm rows, each cupped, a hair off level and its own
    # gap, so the window's sheen breaks board by board (the flat 21 cm rows
    # of build_pine_floor below carried it across as one streak: laminate)
    furn_bench_floor.build_pine_floor("main", x0 - INT_T, x1, y0, y1, 23)
    furn_bench_floor.build_pine_floor("next", nx0, nx1, ny0, ny1, 41)
    B.put("cornice", bench_arch.build_cornice, rect_cm=ROOM, ceiling_z=H)
    B.put("cornice_next", bench_arch.build_cornice, rect_cm=NEXT, ceiling_z=H)
    arch = (DOOR_W + 24.6) / 2.0               # door architraves (both faces)
    openings = [("w", DOOR_Y - arch, DOOR_Y + arch), ("n", N_WIN_X - WIN_W / 2.0, N_WIN_X + WIN_W / 2.0)]
    if EAST_WINDOW:
        openings.append(("e", E_WIN_Y - WIN_W / 2.0, E_WIN_Y + WIN_W / 2.0))
    B.put("skirting", bench_arch.build_skirting, rect_cm=ROOM, openings=openings)
    B.put("skirting_next", bench_arch.build_skirting, rect_cm=NEXT,
          openings=[("e", DOOR_Y - arch, DOOR_Y + arch), ("s", S_WIN_X - WIN_W / 2.0, S_WIN_X + WIN_W / 2.0)])
    # French windows near the outer face of their walls (deep plaster reveals
    # inside), room side -Y turned to face each room
    fw = dict(width=WIN_W, height=WIN_H, sill_z=WIN_SILL)
    B.put("window_n", bench_arch.build_french_window, N_WIN_X, y1 + EXT_T - WIN_IN - 3.5, 0.0, 0.0, **fw)
    if EAST_WINDOW:
        B.put("window_e", bench_arch.build_french_window, x1 + EXT_T - WIN_IN - 3.5, E_WIN_Y, 0.0, -90.0, **fw)
    B.put("window_s", bench_arch.build_french_window, S_WIN_X, ny0 - EXT_T + WIN_IN + 3.5, 0.0, 180.0, **fw)
    # the door: its room side (-Y) faces the room next door, so the leaf opens
    # away from the camera; hung on the south jamb so it folds back out of the
    # view through the doorway (on the north jamb it hid every sun patch)
    B.put("door", bench_arch.build_panel_door, x0 - INT_T / 2.0, DOOR_Y, 0.0, -90.0,
          width=DOOR_W, height=DOOR_H, wall=INT_T, swing=DOOR_SWING, hand="right")
    # column radiator on the north wall right of the window, 5 cm off the wall
    B.put("radiator", bench_arch.build_radiator, 440.0, y1 - 9.25, 0.0, 0.0, width=80.0, height=60.0)
    B.put("railing", build_railing, N_WIN_X, y1 + EXT_T + 8.0)     # 8 cm off the wall's outer face
    build_curtain()


def build_railing():
    """Juliet balcony rail for the north window, built round its own origin
    (the rail's centre line on the floor): white painted flat-bar rails,
    square balusters every 11 cm, brackets back to the wall (-Y)."""
    half = WIN_W / 2.0 + 8.0
    parts = []

    def add(n):
        parts.append(kit.part(n, "paint_white", 30.0))

    add(kit.cbox(2.0 * half, 4.0, 1.2, 0.25, 0.0, 0.0, 98.8))                # handrail
    add(kit.cbox(2.0 * half, 1.2, 4.0, 0.25, 0.0, 0.0, 6.0))                 # bottom rail
    n = int((2.0 * half - 4.0) / 11.0)
    for k in range(n + 1):
        add(kit.cbox(1.2, 1.2, 89.0, 0.15, -half + 2.0 + k * (2.0 * half - 4.0) / n, 0.0, 10.0))
    for bx in (-half + 1.0, half - 1.0):
        for bz in (12.0, 92.0):
            add(kit.cbox(1.6, 8.0, 3.0, 0.2, bx, -4.0, bz))                  # bracket to the wall
    return kit.group("Railing", parts)


CURTAIN_PLANE = 24.0     # cm off the wall: clear of the radiator (its front is 13.5 cm out)
RAIL_Z = 303.0


def build_curtain():
    """One sheer voile panel drawn to the right of the north window, on rings
    from a slim black rail on wall brackets just under the cornice."""
    y1 = ROOM[3]
    rail_y = y1 - CURTAIN_PLANE                # the rings hang straight over the panel
    x_lo, x_hi = N_WIN_X - WIN_W / 2.0 - 25.0, ROOM[2] - 4.0
    parts = []
    w = 112.0                                  # gathered width (about 2.3x fullness of the voile)
    # three quarters of it over the window's right half, so the window lights
    # it from behind and its frame shows through (at x 390 only 51 of its
    # 112 cm hung over glass: a flat grey 0.42-0.50 against the reference's
    # glowing 0.79)
    x = N_WIN_X + WIN_W / 2.0 - 30.0
    # a sheer hangs unevenly: folds 6-24 cm wide, some merging into one deep
    # fold, wandering toward the hem, which fans 8 cm toward the window and
    # breaks on the boards; the heading dips between its nine rings. One
    # cloth layer (no Shell): the voile's see-through is per surface
    cur = A._pleated_curtain("Curtain", w, RAIL_Z - 3.2, depth=4.0, seed=5, shell=False,
                             fold_w=(6.0, 24.0), merge=0.2, amp=(0.3, 1.7), sway=5.0, drift=-8.0,
                             rings=9, floor_break=2.5)
    cur.pos = rt.Point3(x, y1 - CURTAIN_PLANE, 0.0)
    u = rt.Uvwmap()
    u.maptype = 0
    kit.setp(u, "axis", 1)                     # planar, facing the room
    u.length = u.width = u.height = 22.0       # fine voile weave with its slubs
    rt.addModifier(cur, u)
    A.finish(cur, "curtain", None, None)
    parts.append(cur)
    for k in range(9):                         # rings hanging on the rail: inner top on its top
        ring = rt.Torus(radius1=2.3, radius2=0.28, segs=20, sides=8)
        kit.rotate(ring, 90.0, (0, 1, 0))
        ring.pos = rt.Point3(x - w / 2.0 + 3.0 + k * (w - 6.0) / 8.0, rail_y, RAIL_Z - 0.92)
        A.finish(ring, "metal_black", None, None)
        parts.append(ring)
    rail = kit.cyl(1.1, x_hi - x_lo, 0.0, 0.0, 0.0, sides=20)
    kit.rotate(rail, 90.0, (0, 1, 0))
    rail.pos = rt.Point3(x_lo, rail_y, RAIL_Z)
    A.finish(rail, "metal_black", None, None)
    parts.append(rail)
    for bx in (x_lo + 6.0, (x_lo + x_hi) / 2.0, x_hi - 6.0):          # wall brackets
        br = kit.cbox(1.6, y1 - rail_y, 2.4, 0.3, bx, (y1 + rail_y) / 2.0, RAIL_Z - 1.2, segs=1)
        A.finish(br, "metal_black", None, None)
        parts.append(br)
    for ex in (x_lo - 2.2, x_hi + 0.2):                                 # end caps
        cap = kit.cyl(1.5, 2.0, 0.0, 0.0, 0.0, sides=20)
        kit.rotate(cap, 90.0, (0, 1, 0))
        cap.pos = rt.Point3(ex, rail_y, RAIL_Z)
        A.finish(cap, "metal_black", None, None)
        parts.append(cap)
    kit.group("Curtain_N", parts)


# ------------------------------------------------------------ art
def _quad_mesh(name, w, h, uv):
    """A w x h card facing -Y, centred on the origin, (u0, u1, v0, v1) UVs."""
    u0, u1, v0, v1 = uv
    return rt.execute(
        '(m = mesh name:"%s" vertices:#([%.3f,0,%.3f],[%.3f,0,%.3f],[%.3f,0,%.3f],[%.3f,0,%.3f]) '
        'faces:#([1,2,3],[1,3,4]) tverts:#([%.4f,%.4f,0],[%.4f,%.4f,0],[%.4f,%.4f,0],[%.4f,%.4f,0])\n'
        'buildTVFaces m\nfor f = 1 to 2 do setTVFace m f (getFace m f)\nupdate m\nm)'
        % (name, -w / 2.0, -h / 2.0, w / 2.0, -h / 2.0, w / 2.0, h / 2.0, -w / 2.0, h / 2.0,
           u0, v0, u1, v0, u1, v1, u0, v1))


def build_print(pw=56.0, ph=80.0):
    """A framed paper print, centred on its own origin with its back on
    y = 0 and its face to -Y: the ink-wash sheet (its own art_paper map, the
    middle 70 % of the square sheet) on a white mat behind 2 mm glass in a
    slim oak frame."""
    mat, m, depth = 7.0, 2.2, 3.2              # mat margin, moulding width and depth
    iw, ih = pw + 2.0 * mat, ph + 2.0 * mat
    parts = []

    def add(n, key, tile=None):
        parts.append(kit.part(n, key, tile, None if tile is None else 4))

    add(kit.box(iw, 0.4, ih, 0.0, -0.6, -ih / 2.0), "bedding", 30.0)          # mat board
    sheet = _quad_mesh("Print_Sheet", pw, ph, (0.15, 0.85, 0.0, 1.0))
    sheet.pos = rt.Point3(0.0, -0.83, 0.0)
    add(sheet, "art_paper")
    add(kit.box(iw, 0.2, ih, 0.0, -1.9, -ih / 2.0), "glass_solid", 30.0)      # glass
    ow = iw + 2.0 * m
    for w, h, px, pz in ((ow, m, 0.0, ih / 2.0), (ow, m, 0.0, -ih / 2.0 - m),
                         (m, ih, -(iw + m) / 2.0, -ih / 2.0), (m, ih, (iw + m) / 2.0, -ih / 2.0)):
        add(kit.cbox(w, depth, h, 0.25, px, -depth / 2.0, pz, segs=2), "wood_light", 60.0)
    return kit.group("Print", parts)


# ------------------------------------------------------------ furniture and dressing
RUG_T = 0.7              # flat-weave thickness, cm
RUG_BAND = 5.5           # plain-weave band across each end


def _rug_lift(w, l, seed=7):
    """z(x, y) of the rug's underside: it lies flat except for a few low
    2-3 mm waves 60-120 cm long (lift only, a rug cannot sink into the
    boards) and one corner curled up 1.3 cm over its last 15 cm."""
    rnd = random.Random(seed)
    waves = [(rnd.uniform(60.0, 120.0), rnd.uniform(0.0, math.pi), rnd.uniform(0.0, 2.0 * math.pi),
              rnd.uniform(0.08, 0.14)) for _ in range(4)]

    def lift(x, y):
        z = 0.0
        for lam, ang, ph, amp in waves:
            z += amp * (0.5 + 0.5 * math.sin(2.0 * math.pi * (x * math.cos(ang) + y * math.sin(ang)) / lam + ph)) ** 3
        d = math.hypot(x - w / 2.0, y + l / 2.0)           # the near right corner (toward the camera)
        if d < 15.0:
            z += 1.3 * (1.0 - d / 15.0) ** 2
        return min(z, 1.6)
    return lift


def _rug_edge(l, seed=3):
    """x offset of a long edge along y: hand-woven edges wander +-3 mm."""
    rnd = random.Random(seed)
    terms = [(rnd.uniform(35.0, 90.0), rnd.uniform(0.0, 2.0 * math.pi), rnd.uniform(0.08, 0.14)) for _ in range(3)]
    return lambda y: sum(amp * math.sin(2.0 * math.pi * y / lam + ph) for lam, ph, amp in terms)


def _slab_cage(xs_at, ys, lift, t, nx):
    """(verts, faces) of a closed slab over rows ys: row j spans
    xs_at(ys[j]) = (x0, x1) in nx quads, its underside at lift(x, y), its top
    t above; 0-based triangles, outward normals."""
    verts, faces = [], []
    ny = len(ys) - 1
    for top in (0, 1):
        for y in ys:
            x0, x1 = xs_at(y)
            for i in range(nx + 1):
                x = x0 + (x1 - x0) * i / nx
                verts.append((x, y, lift(x, y) + (t if top else 0.0)))
    row = nx + 1
    half = (ny + 1) * row
    for j in range(ny):
        for i in range(nx):
            a = j * row + i
            b, c, d = a + 1, a + row, a + row + 1
            faces += [(a, c, b), (b, c, d)]                                  # underside faces down
            a, b, c, d = a + half, b + half, c + half, d + half
            faces += [(a, b, c), (b, d, c)]                                  # top faces up
    rim = ([((j + 1) * row, j * row) for j in range(ny)] +                   # -x edge
           [(ny * row + i + 1, ny * row + i) for i in range(nx)] +           # +y end
           [(j * row + nx, (j + 1) * row + nx) for j in range(ny)] +         # +x edge
           [(i, i + 1) for i in range(nx)])                                  # -y end
    for a, b in rim:
        faces += [(a, b, a + half), (b, b + half, a + half)]
    return verts, faces


def _slab_mesh(name, xs_at, ys, lift, t, nx):
    verts, faces = _slab_cage(xs_at, ys, lift, t, nx)
    return rt.execute(
        '(m = mesh name:"%s" vertices:#(%s) faces:#(%s)\n'
        'for f = 1 to m.numfaces do setFaceSmoothGroup m f 1\nupdate m\nm)'
        % (name, ",".join("[%.3f,%.3f,%.3f]" % v for v in verts),
           ",".join("[%d,%d,%d]" % (a + 1, b + 1, c + 1) for a, b, c in faces)))


def build_kilim(w=200.0, l=300.0):
    """Hand-woven flat-weave rug, 7 mm thick, centred on its origin: the
    field (its weave relief from MatForge displacement, box-mapped at the
    photo's 120 cm, the yarn streaks along U: across the room as the camera
    sees it) between a 5.5 cm plain-weave band at each end, overcast selvedge
    cords along both long edges, and a knotted warp fringe. It lies as a rug
    does: a few low waves, edges that wander 3 mm, one corner curled (a dead
    flat box with ruler edges and a comb of fringe read as a decal)."""
    lift = _rug_lift(w, l)
    left, right = _rug_edge(l, 3), _rug_edge(l, 4)
    xs_at = lambda y: (-w / 2.0 + left(y), w / 2.0 + right(y))
    yb = l / 2.0 - RUG_BAND
    step = 5.0               # a 5 cm cage: ~5 k vertices, a modest MAXScript literal
    ny = int(2.0 * yb / step)
    ys = [-yb + k * (2.0 * yb) / ny for k in range(ny + 1)]
    nodes = []
    field = _slab_mesh("Kilim", xs_at, ys, lift, RUG_T, int(w / step))
    # the photo at 200 cm, not its 120: three soft motifs across the rug, each
    # ~45 cm, as the reference's (at 120 a dozen read as polka dots) and a
    # chunkier hand-spun yarn
    nodes.append(kit.part(field, "rug", 200.0))
    for tag, y0, y1 in (("S", -l / 2.0, -yb), ("N", yb, l / 2.0)):
        band = _slab_mesh("Kilim_Band" + tag, xs_at, [y0, (y0 + y1) / 2.0, y1], lift, RUG_T - 0.1, int(w / step))
        nodes.append(kit.part(band, "rug_band", 15.0))
    cords = []
    for edge, sgn in ((left, -1.0), (right, 1.0)):
        pts = []
        for k in range(101):
            y = -l / 2.0 + l * k / 100.0
            x = sgn * w / 2.0 + edge(y)
            pts.append((x, y, lift(x, y) + RUG_T * 0.5))
        cords.append((pts, 0.42))
    nodes.append(kit.part(_tube_mesh("Kilim_Selvedge", cords, sides=6), "rug_band", 15.0))
    for tag, end in (("S", -1.0), ("N", 1.0)):
        fr = _tube_mesh("Kilim_Fringe" + tag, fringe_paths(w, l, end, lift), sides=4)
        nodes.append(kit.part(fr, "rug_fringe", 15.0))
    return kit.group("Kilim_G", nodes)


def fringe_paths(w, l, end, lift, seed=11):
    """Warp fringe at one short end (end -1: -Y, +1: +Y) of a w x l rug
    centred on the origin: a knot every 3-4 cm, five to seven strands from
    each, 7-11 cm long, fanning up to a third of a radian round the bundle's
    own lean, leaving the band at mid-thickness and lying on the floor;
    about one bundle in seven is flipped back onto the rug. [(points,
    radius)] for _tube_mesh."""
    rnd = random.Random(seed + (0 if end < 0 else 1))
    out = []
    y0 = end * l / 2.0
    x = -w / 2.0 + rnd.uniform(1.0, 2.0)
    while x < w / 2.0 - 1.0:
        zr = lift(x, y0)
        out.append(([(x, y0 - end * 0.3, zr + 0.45), (x, y0 + end * 0.9, zr + 0.34)], 0.28))      # the knot
        back = rnd.random() < 0.15
        lean = rnd.uniform(-0.25, 0.25)
        for _ in range(rnd.randint(5, 7)):
            L = rnd.uniform(7.0, 11.0)
            ang = lean + rnd.uniform(-0.3, 0.3)
            bend = rnd.uniform(-1.2, 1.2)
            r = rnd.uniform(0.06, 0.07)
            pts = []
            for j in range(8):
                t = j / 7.0
                px = x + (0.9 + t * L) * math.sin(ang) + bend * t * t
                if back:                # up over the knot and back onto the band and the field
                    py = y0 + end * (0.9 - t * L * math.cos(ang))
                    hump = 0.5 * math.sin(math.pi * min(1.0, t * 4.0)) if t < 0.25 else 0.0
                    pz = lift(px, py) + RUG_T + r + hump if end * (py - y0) < 0.0 else zr + 0.4 + hump
                else:
                    py = y0 + end * (0.9 + t * L) * math.cos(ang)
                    pz = max(r, (zr + 0.34) * max(0.0, 1.0 - 2.5 * t) ** 2 + r)
                pts.append((px, py, pz))
            out.append((pts, r))
        x += rnd.uniform(3.0, 4.0)
    return out


def _tube_mesh(name, paths, sides=4):
    """Thin tubes along 3-D polylines [(points, radius)] as one smoothed mesh
    (open ends: they are a millimetre across)."""
    verts, faces = [], []
    for pts, r in paths:
        base = len(verts)
        for i, p in enumerate(pts):
            a, b = pts[max(0, i - 1)], pts[min(len(pts) - 1, i + 1)]
            t = [b[k] - a[k] for k in range(3)]
            tl = math.sqrt(sum(c * c for c in t)) or 1.0
            t = [c / tl for c in t]
            up = (0.0, 0.0, 1.0) if abs(t[2]) < 0.9 else (1.0, 0.0, 0.0)
            n1 = [t[1] * up[2] - t[2] * up[1], t[2] * up[0] - t[0] * up[2], t[0] * up[1] - t[1] * up[0]]
            nl = math.sqrt(sum(c * c for c in n1)) or 1.0
            n1 = [c / nl for c in n1]
            n2 = [t[1] * n1[2] - t[2] * n1[1], t[2] * n1[0] - t[0] * n1[2], t[0] * n1[1] - t[1] * n1[0]]
            for s in range(sides):
                th = 2.0 * math.pi * s / sides
                c, sn = math.cos(th) * r, math.sin(th) * r
                verts.append(tuple(p[k] + c * n1[k] + sn * n2[k] for k in range(3)))
        for i in range(len(pts) - 1):
            for s in range(sides):
                a = base + i * sides + s
                b = base + i * sides + (s + 1) % sides
                faces += [(a, b, b + sides), (a, b + sides, a + sides)]
    return rt.execute(
        '(m = mesh name:"%s" vertices:#(%s) faces:#(%s)\n'
        'for f = 1 to m.numfaces do setFaceSmoothGroup m f 1\nupdate m\nm)'
        % (name, ",".join("[%.3f,%.3f,%.3f]" % v for v in verts),
           ",".join("[%d,%d,%d]" % (a + 1, b + 1, c + 1) for a, b, c in faces)))


def _bezier(p0, p1, p2, p3, n=18):
    out = []
    for k in range(n + 1):
        t = k / float(n)
        a, b, c, d = (1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t * t * (1 - t), t ** 3
        out.append(tuple(a * p0[i] + b * p1[i] + c * p2[i] + d * p3[i] for i in range(3)))
    return out


def build_tote(seed=5, lean=3.0):
    """Waxed canvas tote standing on the floor, 36 x 40 x 11 cm: the
    scatter-cushion cage (furn_living._pillow_md: pinched seams, dog-eared
    corners, tension wrinkles, filling settled to one edge) stood up on its
    settled edge, leaning back `lean` degrees, with two strap handles - the
    front one flopped forward, the back one standing. Front -Y."""
    import furn_living as fl
    w, h, t = 36.0, 40.0, 11.0
    md = fl._pillow_md(w, h, t, pinch=0.12, puff=0.85, ear=1.0, wrinkle=1.3, settle=0.3, bow=0.8, seed=seed)
    tl = math.radians(lean)

    def tilt(p):                     # lean back about the bottom back edge (y = t / 2, z = 0)
        x, y, z = p
        dy = y - t / 2.0
        return (x, t / 2.0 + dy * math.cos(tl) + z * math.sin(tl), -dy * math.sin(tl) + z * math.cos(tl))

    v = [tilt((x, -z, y + h / 2.0)) for x, y, z in md.v]        # stood up on its -Y (settled) edge
    # set it down along its whole length: the stood-up seam bows, so set down
    # by its lowest point the middle rode up to 1.8 cm off the boards (a lit
    # wedge under the bag, no contact shadow). Each vertex drops by the
    # seam's height under it (the lowest point within 1-2 cm in x), fading
    # out 3-12 cm up the body; the lip squashes flat on the boards, sinking
    # half a millimetre
    z0 = min(p[2] for p in v)
    lo = {}
    for x, _y, z in v:
        k = int(math.floor(x))
        lo[k] = min(lo.get(k, z), z)

    def seam(x):
        k = int(math.floor(x))
        return min(lo[j] for j in (k - 1, k, k + 1) if j in lo)

    out = []
    for x, y, z in v:
        s = seam(x)
        d = z - s
        if d < 3.0:
            zz = 3.0 * (d / 3.0) ** 1.8
        else:
            zz = d + (s - z0) * min(1.0, (d - 3.0) / 9.0)
        out.append((x, y, zz - 0.05))
    md.v = out
    body = fl._build(md, "Tote_Body", 36.0)                     # the cage's own UVs: one repeat per face
    kit.soften(body, (10.0, 0.4, 0.5), 0, seed)                 # a little slack in the canvas
    kit.part(body, "canvas_bag", None, None)
    nodes = [body]

    def faces_at(x, z):
        """The body's front and back face y at (x, z), off the set-down cage:
        on each side of the bag's mid-plane the cage vertex nearest in z
        (near the seam the faces slope ~0.56 cm per cm, so a window min/max
        would pick a point lower down)."""
        near = [p for p in md.v if abs(p[0] - x) < 1.5 and abs(p[2] - z) < 2.5]
        if not near:
            return -2.0, 2.0
        mid = sum(p[1] for p in near) / len(near)
        fr = min((p for p in near if p[1] < mid), key=lambda p: abs(p[2] - z), default=None)
        bk = min((p for p in near if p[1] >= mid), key=lambda p: abs(p[2] - z), default=None)
        return (fr[1] if fr else -2.0), (bk[1] if bk else 2.0)

    # straps sewn on 7 cm under the top seam, where the bag is thick enough
    # to hold them (just under the seam it thins below 1 cm and bows): each
    # end 1 mm proud of its face, so at least 4.5 mm of the 5.5 mm strap sits
    # in the canvas through the Noise (ends set at fixed +-2 cm floated
    # 0.3-1.9 cm off it)
    ztop = max(p[2] for p in md.v)
    za = ztop - 7.0
    for name, back, peak, fwd in (("Tote_HandleFront", False, 10.0, -7.0), ("Tote_HandleBack", True, 16.0, -2.0)):
        ends = []
        for x in (-7.0, 7.0):
            yf, yb = faces_at(x, za)
            ends.append((x, yb + 0.1 if back else yf - 0.1, za))
        yc = 0.5 * (ends[0][1] + ends[1][1]) + fwd             # the arch leans forward by fwd
        path = _bezier(ends[0], (-8.5, yc, ztop + peak), (8.5, yc, ztop + peak), ends[1])
        hn = fl._build(fl._tube_md(path, 0.55, sides=6), name)
        nodes.append(kit.part(hn, "canvas_bag", 25.0))
    return kit.group("Tote", nodes)


def build_floor_book():
    parts = furn_bench_console.book_parts(29.0, 22.5, 1.9, cover="paper", name="FloorBook")
    return kit.group("FloorBook", furn_bench_console._nodes(parts))


def build_furniture():
    x0, y0, x1, y1 = ROOM
    # console against the west wall, front +X, dressed (the module's
    # arrangement): its back 4.5 cm off the wall, clear of the 2.5 cm skirting
    # (its back legs stood 1 cm in it) with room for the lamp cord behind
    B.put("console", furn_bench_console.preview, x=x0 + 22.0, y=380.0, rot=90.0)
    # the print centred over it and high enough that the lamp shade (top at
    # 129.5, right end of the console) passes below its frame (it cut through it)
    B.put("print", build_print, x0 + 0.05, 380.0, 180.0, 90.0, pw=56.0, ph=80.0)
    # a canvas tote set down in front of the console, its broad face turned
    # most of the way to the camera (side-on it read as a paper sliver)
    B.put("tote", build_tote, 62.0, 428.0, 0.0, 40.0)
    # kilim, and the chair on it turned to the console and the camera
    B.put("kilim", build_kilim, 268.0, 400.0, 0.0, 0.0)
    B.put("chair", furn_bench_chair.build_lounge_chair, 232.0, 440.0, 0.8, -55.0)
    B.put("floor_book", build_floor_book, 196.0, 352.0, 0.8, 24.0)
    # plants in the corner left of the window; the banana turned so its
    # visible blades stop 29 cm short of the back wall and clear the bushy
    # plant (at 18 deg they reached 12 cm from it; their cut-out card
    # margins still cross it, unseen)
    # (grown 15 %: at 1.8 m it read small under the 3.3 m ceiling)
    # the dark leaf photo: its blade runs v 0.046-0.943 (measured off its cut-out)
    B.put("banana", furn_bench_plants.build_banana_plant, 132.0, 572.0, 0.0, -30.0, seed=0, scale=1.15,
          uv_xf=furn_bench_plants.photo_fit(0.046, 0.943, 0.50))
    # its 12-25 cm leaves in the rubber-plant photo: shrunk banana leaves read
    # as a miniature banana (that photo's stalk starts at v 0.11 and its tip
    # is at 0.888, measured off its cut-out: photo_fit puts them on the
    # cards' attach point and blade end)
    B.put("bushy", furn_bench_plants.build_bushy_plant, 222.0, 590.0, 0.0, 0.0, scale=1.4,
          remap={"leaf_card": "leaf_card_small"}, seed=0,
          uv_xf=furn_bench_plants.photo_fit(0.112, 0.888, 0.506))


# ------------------------------------------------------------ light
# toward the sun: 27 deg west of south, 27 deg up. Ray-cast: the patches it
# throws through the next room's south window land on that room's north wall
# right where the doorway looks (x -100..-25); no sun crosses the doorway
# into the main room below ~31 deg west of south (the 40 cm reveal and the
# north pier stop it)
SUN_TO = (-0.40, -0.79, 0.46)


def setup_lights():
    """Afternoon sun, sky dome. The sun lands in the room next door through
    its south window; the main room's windows face north and east, so it is
    lit by the sky alone."""
    tx, ty = -230.0, 470.0
    sun = rt.VRaySun(pos=rt.Point3(tx + 3000.0 * SUN_TO[0], ty + 3000.0 * SUN_TO[1], 3000.0 * SUN_TO[2]),
                     target=rt.Targetobject(pos=rt.Point3(tx, ty, 0.0)))
    sun.name = "Sun"
    kit.setp(sun, "size_multiplier", 3.0)
    kit.setp(sun, "turbidity", 3.2)
    sky = rt.VRaySky()
    rt.environmentMap = sky
    rt.useEnvironmentMap = True
    dome = rt.VRayLight()
    dome.name = "SkyDome"
    dome.type = 1
    dome.texmap = rt.VRaySky()
    kit.setp(dome, "texmap_on", True)
    kit.setp(dome, "dome_adaptive", True)
    kit.setp(dome, "multiplier", 1.0)
    kit.setp(dome, "invisible", True)


def special_materials():
    """Per-board tints on the pine (MatForge build_variants on the forged
    albedo; the faces carry IDs 2-6), and the brushing on the steel."""
    for n in list(rt.objects):
        if str(n.name).startswith("FloorPine_") and n.material is not None:
            n.material = builder.build_variants(n.material, PINE_TINTS)
    log("pine boards: %d tint variants" % (len(PINE_TINTS) - 1))
    # the chair's bars carry U along each bar: the brushing follows the UVs
    # (V-Ray's default local axis cannot follow bars running every which way)
    steel = A._MAT_CACHE.get("metal_steel")
    if steel is not None and kit.setp(steel, "anisotropy_derivation", 1):
        log("steel: anisotropy along the UVs")


# ------------------------------------------------------------ cameras, exposure
CAMS = {
    # position (x, y, z), target (x, y, z) cm, focal mm (36 mm film across the
    # portrait frame's width); the target sits low so the auto vertical tilt
    # shifts the frame down: verticals straight, little ceiling. 24 mm from
    # (215, 120) read as a real-estate wide angle (74 deg across, the ceiling
    # a quarter of the frame, the near rug corner stretched 2.5x); 32 mm from
    # 75 cm further back holds the print, console, chair and curtain with
    # the console's near end cut by the frame, as in the reference
    "bench1": ((229.0, 46.0, 105.0), (115.0, 640.0, 65.0), 32.0),
}
SIZE = {"final": (1600, 1920), "preview": (400, 480)}.get(B.QUALITY, (800, 960))
B.PROBE = (200, 240)             # portrait probes (A's 320 x 200 would frame another view)
# the back wall's upper left at 32 mm: below the cornice (its foot at fy
# ~0.20), above the banana's top (fy ~0.30 at fx 0.51), right of the corner
# (fx 0.35), well left of the window jamb (fx 0.68)
# warmth as the reference's back wall reads (r/g 1.08, b/g 0.91); the
# preview's converged balance (metered at the final exposure) as the start:
# sky through the glass is cyan
A.WB_PATCH["bench1"] = ((0.37, 0.215, 0.47, 0.26), "wall_paint", (1.08, 0.91))
B.WB_START["bench1"] = (0.713, 0.931, 1.0)
# the reference's upper back wall reads 0.37-0.48 linear; the post's toe
# leaves the wall where the render puts it (the old S-curve added 7 %) and
# the exposure loop lands ~4 % under its aim
PATCH_EXPOSURE = 0.48
# the reference's windows are blown out to white, as a camera exposed for the
# room sees a daylit exterior; the apartment's cap (x30) kept the street as
# dim as the walls (x114 at 1/7 s)
A.BACKDROP_MAX = 150.0
A.BACKDROP_K = 800.0


def diag(key, cam):
    """MF_BENCH_DIAG: what lights the room, at a fixed daylight-interior exposure."""
    cam.ISO, cam.shutter_speed = 200.0, 8.0
    name = lambda *pre: B.show_nodes(lambda n: str(n.name).startswith(pre))
    both = lambda on: [name("Curtain")(on), name("Facade_Bounce")(on)]
    B.diag_probes(cam, key, [("base", None), ("no_curtain", name("Curtain")), ("no_facade", name("Facade_Bounce")),
                             ("no_backdrop", name("Backdrop")), ("no_curtain_facade", both),
                             ("no_glass", B.show_nodes(lambda n: "Glass" in str(n.name) or "glass" in str(n.name)))])


def main():
    t0 = time.time()
    B.start()
    build_architecture()
    bd = A.build_backdrop()
    # the photo is mirrored every 90 deg round the ring's centre and the north
    # window looked straight at a mirror line (79.7-92.7 deg): turned 45 deg
    # (24 of its 192 segments) the window sees the middle of a quarter
    if bd is not None:
        bd.pivot = rt.Point3(410.0, -490.0, 0.0)
        kit.rotate(bd, 45.0)
    log("architecture built in %.0fs" % (time.time() - t0))
    build_furniture()
    log("furniture built in %.0fs: %d nodes" % (time.time() - t0, len(rt.objects)))
    probe = os.environ.get("MF_BENCH_PROBE")
    if probe:
        B.dump_layout(probe)
        return
    A.apply_materials()
    special_materials()
    setup_lights()
    log("scene built in %.0fs: %d nodes, %d MatForge materials" % (
        time.time() - t0, len(rt.objects), len(A._MAT_CACHE)))
    for label, g, nodes in B.PLACED:
        log("placed %s: %d nodes" % (label, len(nodes)))
    B.save_if_asked()
    B.render_views(CAMS, SIZE, PATCH_EXPOSURE, before=diag if os.environ.get("MF_BENCH_DIAG") else None)


B.run(main)
