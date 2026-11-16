"""MatForge benchmark 3 - a quiet-luxury living room (runs inside 3ds Max).

The style of the user's third Pinterest reference, in an own composition: a
long curved cream boucle sofa, two-tier pebble coffee tables in polished
green onyx on bronze legs, a turned walnut side table and a brass tray
table, a slate-blue velvet pouf, a striped knit lounge chair, a large
hand-tufted wool tapestry (an original artwork) over the sofa, fluted oak
slat panelling, a yellow-flowering tree in a brass pot, a pale ribbed rug on
honed limestone, and a double-ring alabaster pendant glowing under an oval
coved ceiling coffer. The pieces come from furn_bench3_*.py and
bench3_arch.py; EVERY material is made by MatForge from a forged Runway
reference (bench_common.matforge()).

Plan (Max cm, Z up): the room is x 0..700, y 0..640, ceiling 300 (the
coffer rises 18 cm above it); the camera stands at the room's south side
looking north at the tapestry and the oak panels. Daylight comes in through
two tall east windows out of frame; the pendant's rings and the coffer's
cove light it warm.

Environment: as bench1_scene.py (MF_APT_OUT, MF_APT_QUALITY, MF_APT_CAMS,
MF_APT_SAVE, MF_BENCH_PROBE).
"""
import importlib
import math
import os
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

A, kit, log = B.A, B.kit, B.log
import bench3_arch  # noqa: E402  (after B: bound to the kit A reloaded)
import furn_bench3_decor  # noqa: E402
import furn_bench3_lights  # noqa: E402
import furn_bench3_sofa  # noqa: E402
import furn_bench3_tables  # noqa: E402

for _m in (bench3_arch, furn_bench3_decor, furn_bench3_lights, furn_bench3_sofa, furn_bench3_tables):
    importlib.reload(_m)
# both rings level: from a 125 cm eye the inner ring hung 18 cm higher lined
# its front up with the outer ring's and the two read as one ring with a U
# inside it (ring_specs reads this at call time; the lines follow)
furn_bench3_lights.RING_RISE = 0.0

H = 300.0                       # ceiling height, cm (the coffer rises 18 above it)

# ------------------------------------------------------------ MatForge materials
A.MATS.update({
    # dark bronze legs: the brass photo with the named metal "bronze" came
    # out polished gold (bronze's F0 is as bright as brass's)
    "onyx": ("green_onyx", None), "bronze": ("dark_bronze", None),
    # glowing from the light inside the rings, its veins showing through
    "alabaster": ("alabaster", None, "stone_backlit"),
    "tapestry": ("tapestry_art", None),
    # a woody trunk and twigs for the flowering tree
    "stem": ("tree_bark", None),
    "blossom_card": ("yellow_blossom", None), "slate_velvet": ("slate_velvet", None),
    "knit_stripe": ("knit_stripe", None), "rug": ("striped_rug", None),
    # honey oak for the panelling (the pale oak_board read as white paint)
    "oak_slat": ("oak_honey", None), "stone_floor": ("limestone_floor", None),
})
# the rug's 6 mm ribs run straight across: stochastic tiling would jog them
B.PATTERN_KEYS.add("rug")

# ------------------------------------------------------------ plan (Max cm)
ROOM = (0.0, 0.0, 700.0, 640.0)
EXT_T, INT_T = 40.0, 20.0
TOP = H + 15.0
E_WINS = ((120.0, 320.0), (380.0, 580.0))      # east windows (y spans), floor to 260
WIN_TOP = 260.0
COFFER = (330.0, 380.0, 420.0, 300.0, 18.0)     # centre x, y, a, b, depth
TAPESTRY = (295.0, 62.0, 300.0, 230.0)          # centre x, bottom z (top 8 under the ceiling), width, height
SLATS = (470.0, 700.0)                          # oak panelling across the north wall


def wall_with_reveal(name, axis, c_face, c_back, a0, a1, openings=()):
    """A wall from the flush skirting's top (FS_TOP) up, its foot set back
    behind the skirting below (as bench3_arch asks). The feet run on past
    both ends into the neighbouring walls, or the set-back feet would leave
    a slot to the outside at every corner."""
    sgn = 1.0 if c_back > c_face else -1.0
    back = bench3_arch.FS_BACK + 0.05
    B.wall(name, axis, *sorted((c_face, c_back)), a0, a1, TOP, openings, base=bench3_arch.FS_TOP)
    B.wall(name + "Foot", axis, *sorted((c_face + sgn * back, c_back)), a0 - EXT_T, a1 + EXT_T,
           bench3_arch.FS_TOP + 0.5, [(b0, b1, z0, z1) for b0, b1, z0, z1 in openings if z0 <= 0.0], base=-3.0)


def _zipper(inner, outer):
    """Triangles between two closed loops that are star-shaped from the
    origin, both counter-clockwise: walk both by angle, always advancing the
    one whose next vertex comes first."""
    ang = lambda p: math.atan2(p[1], p[0]) % (2.0 * math.pi)
    i0 = min(range(len(inner)), key=lambda k: ang(inner[k]))
    o0 = min(range(len(outer)), key=lambda k: ang(outer[k]))
    inner = inner[i0:] + inner[:i0]
    outer = outer[o0:] + outer[:o0]
    ni, no = len(inner), len(outer)
    tris, i, o = [], 0, 0
    while i < ni or o < no:
        ai = ang(inner[(i + 1) % ni]) + (2.0 * math.pi if i + 1 >= ni else 0.0)
        ao = ang(outer[(o + 1) % no]) + (2.0 * math.pi if o + 1 >= no else 0.0)
        if o >= no or (i < ni and ai <= ao):
            tris.append((("i", i % ni), ("i", (i + 1) % ni), ("o", o % no)))
            i += 1
        else:
            tris.append((("i", i % ni), ("o", (o + 1) % no), ("o", o % no)))
            o += 1
    return inner, outer, tris


def ceiling_with_hole(rect, centre, outline, z0, z1):
    """The main ceiling slab over rect with the coffer's oval cut out of it
    (outline: the coffer's outer edge, counter-clockwise round centre), as a
    closed mesh: underside, top and the four outer sides (the coffer's own
    outer face closes the oval)."""
    cx, cy = centre
    x0, y0, x1, y1 = rect
    rect_loop = [(x1 - cx, y0 - cy), (x1 - cx, y1 - cy), (x0 - cx, y1 - cy), (x0 - cx, y0 - cy)]
    # the rectangle densified so the zipper meets it in step with the oval
    outer = []
    for k in range(4):
        a, b = rect_loop[k], rect_loop[(k + 1) % 4]
        for j in range(24):
            t = j / 24.0
            outer.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    inner = [(x - cx, y - cy) for x, y in outline]
    inner, outer, tris = _zipper(inner, outer)
    verts = []
    for z in (z0, z1):
        verts += [(cx + x, cy + y, z) for x, y in inner] + [(cx + x, cy + y, z) for x, y in outer]
    ni, no = len(inner), len(outer)
    idx = lambda lvl, s, k: lvl * (ni + no) + (k if s == "i" else ni + k)
    faces = []
    for t in tris:                                 # each zipper triangle turns clockwise seen from above
        a, b, c = (idx(0, s, k) for s, k in t)
        faces.append((a, b, c))                    # underside faces down
        a, b, c = (idx(1, s, k) for s, k in t)
        faces.append((a, c, b))                    # top faces up
    for k in range(no):                            # outer sides
        a, b = idx(0, "o", k), idx(0, "o", (k + 1) % no)
        c, d = idx(1, "o", (k + 1) % no), idx(1, "o", k)
        faces += [(a, b, c), (a, c, d)]
    node = rt.execute('(m = mesh name:"Ceiling" vertices:#(%s) faces:#(%s)\nupdate m\nm)' % (
        ",".join("[%.3f,%.3f,%.3f]" % v for v in verts),
        ",".join("[%d,%d,%d]" % (a + 1, b + 1, c + 1) for a, b, c in faces)))
    # the coffer brings its own band of flat ceiling in wall_paint: the slab
    # must match it or the band shows as a ring
    return A.finish(node, "wall_paint", 150.0)


def build_shell():
    x0, y0, x1, y1 = ROOM
    wins = [(a, b, 0.0, WIN_TOP) for a, b in E_WINS]
    wall_with_reveal("WallN", "x", y1, y1 + EXT_T, x0 - INT_T, x1 + EXT_T)
    wall_with_reveal("WallE", "y", x1, x1 + EXT_T, y0 - INT_T, y1, wins)
    wall_with_reveal("WallS", "x", y0, y0 - INT_T, x0 - INT_T, x1)
    wall_with_reveal("WallW", "y", x0, x0 - INT_T, y0, y1)
    for k, (a, b) in enumerate(E_WINS):
        xf = x1 + EXT_T - 8.0
        for (ya, yb, za, zb) in ((a, a + 5.0, 0.0, WIN_TOP), (b - 5.0, b, 0.0, WIN_TOP),
                                 (a, b, WIN_TOP - 5.0, WIN_TOP), (a, b, 0.0, 4.0),
                                 ((a + b) / 2.0 - 2.0, (a + b) / 2.0 + 2.0, 4.0, WIN_TOP - 5.0)):
            B.box("EWinFrame_%d" % k, xf - 3.0, xf + 3.0, ya, yb, za, zb, "metal_black", 25.0)
        B.box("EWinGlass_%d" % k, xf - 0.3, xf + 0.3, a + 5.0, b - 5.0, 4.0, WIN_TOP - 5.0, "glass", 100.0)
        B.box("EWinFoot_%d" % k, x1 - 0.1, xf - 3.0, a, b, -3.0, 0.0, "stone_floor", 90.0)
    g = rt.Plane(width=8000, length=8000, pos=rt.Point3(350, 320, -15))
    g.name = "Ground_Far"
    A.finish(g, "ground", 150)


def build_architecture():
    x0, y0, x1, y1 = ROOM
    build_shell()
    cx, cy, a, b, depth = COFFER
    start = len(kit.PARTS)
    g, outline = furn_bench3_lights.build_ceiling_coffer(a=a, b=b, depth=depth)
    kit.place(g, cx, cy, H, 0.0)
    nodes = []
    for node, key, tile, maptype in kit.PARTS[start:]:
        A.finish(node, key, tile or 100.0, maptype)
        nodes.append(node)
    B.PLACED.append(("coffer", g, nodes))
    ceiling_with_hole(ROOM, (cx, cy), [(cx + x, cy + y) for x, y in outline], H, TOP)
    B.put("floor", bench3_arch.build_limestone_floor, rect_cm=ROOM, seed=1)
    sx0, sx1 = SLATS
    # stopped at the floor-length windows and behind the oak panelling
    B.put("skirting", bench3_arch.build_flush_skirting, rect_cm=ROOM,
          openings=[("e", a_, b_) for a_, b_ in E_WINS] + [("n", sx0, sx1)])
    B.put("slats", bench3_arch.build_slat_panel, (sx0 + sx1) / 2.0, y1, 0.0, 0.0,
          width=sx1 - sx0, height=H, seed=2)
    tx, tz, tw, th = TAPESTRY
    B.put("tapestry", furn_bench3_decor.build_tapestry, tx, y1, tz, 0.0, width=tw, height=th, seed=0)


# ------------------------------------------------------------ furniture
RUG = (300.0, 435.0, 420.0, 350.0)       # centre x, y, width, length: under the whole sofa plinth


def build_rug():
    """Pale ribbed wool rug, 1 cm thick, its rib from MatForge displacement
    (box-mapped at the reference's 60 cm); the ribs run across the room."""
    n = kit.cbox(RUG[2], RUG[3], 1.0, 0.35, 0.0, 0.0, 0.0, segs=2)
    n.name = "StripedRug"
    kit.part(n, "rug", 60.0)
    return kit.group("StripedRug_G", [n])


def build_furniture():
    rz = 1.0                                   # the rug's top
    B.put("rug", build_rug, RUG[0], RUG[1], 0.0, 0.0)
    B.put("sofa", furn_bench3_sofa.build_curved_sofa, 300.0, 545.0, rz, 0.0, chord=340.0, depth=95.0, seed=0)
    B.put("onyx_tables", furn_bench3_tables.build_onyx_tables, 290.0, 400.0, rz, 0.0, seed=0)
    # inside the 28 mm view (x = 330 +- 0.643 (y - 150) across the frame):
    # the pouf cut by the left edge and the chair by the right, as the
    # reference's are; the chair turned to the tables; the tree's crown
    # 6.5 cm off the slats at this turn (checked by projecting the pieces)
    B.put("pouf", furn_bench3_decor.build_velvet_pouf, 215.0, 340.0, rz, 0.0, seed=0)
    B.put("walnut_table", furn_bench3_tables.build_walnut_side_table, 185.0, 435.0, rz, 0.0)
    B.put("brass_table", furn_bench3_tables.build_brass_tray_table, 530.0, 510.0, 0.0, 0.0)
    B.put("knit_chair", furn_bench3_decor.build_knit_lounge_chair, 445.0, 330.0, rz, -60.0, seed=0)
    # a fuller specimen (at its own size the crown read thin under the 3 m ceiling)
    B.put("tree", furn_bench3_decor.build_flowering_tree, 532.0, 578.0, 0.0, 60.0, seed=0, scale=1.2)


# ------------------------------------------------------------ light
RING_LIGHTS = []


def build_pendant_and_lights():
    """The ring pendant from the coffer's recess floor, a 2700 K sphere light
    every 6 points along each ring's centre line (the rings cast no shadow,
    so their own light reaches the room; they glow by their backlit-stone
    self-illumination), and small lights along the coffer's hidden LED."""
    cx, cy, a, b, depth = COFFER
    start = len(kit.PARTS)
    try:
        # drop 65: the outer ring's far arc clears the wall-ceiling line
        # (at 100 it hung across the top of the tapestry)
        g, lines = furn_bench3_lights.build_ring_pendant(drop=65.0, seed=0)
    except Exception as exc:
        log("piece pendant failed: %s" % exc)
        return
    kit.place(g, cx, cy, H + depth, 0.0)
    nodes = []
    for node, key, tile, maptype in kit.PARTS[start:]:
        A.finish(node, key, tile or 100.0, maptype)
        nodes.append(node)
        if key == "alabaster":
            node.castShadows = False
    B.PLACED.append(("pendant", g, nodes))
    for r, line in enumerate(lines):
        for k in range(0, len(line), 6):
            x, y, z = line[k]
            lt = rt.VRayLight()
            lt.name = "Ring%d_%d" % (r, k)
            lt.type = 2                                   # sphere
            kit.setp(lt, "size0", 2.0)
            kit.setp(lt, "normalizeColor", 1)
            kit.setp(lt, "multiplier", 70.0)              # ~1100 lm per ring
            kit.setp(lt, "color_mode", 1)
            kit.setp(lt, "color_temperature", 2700.0)
            kit.setp(lt, "invisible", True)
            lt.pos = rt.Point3(cx + x, cy + y, H + depth + z)
            RING_LIGHTS.append(lt)
    # 120 small lights, 9.7 cm apart on the 11.65 m loop (20 lm each, 2400
    # lm): at 29 cm the visible band of the cove scalloped (dip/peak 0.26)
    for k, (x, y, z) in enumerate(furn_bench3_lights.coffer_led_line(a, b, depth)):
        lt = rt.VRayLight()
        lt.name = "Cove_%d" % k
        lt.type = 2
        kit.setp(lt, "size0", 1.5)
        kit.setp(lt, "normalizeColor", 1)
        kit.setp(lt, "multiplier", 20.0)
        kit.setp(lt, "color_mode", 1)
        kit.setp(lt, "color_temperature", 3000.0)
        kit.setp(lt, "invisible", True)
        lt.pos = rt.Point3(cx + x, cy + y, H + z + 1.5)
    log("pendant: %d ring lights" % len(RING_LIGHTS))


def setup_lights():
    """Sky through the east windows (the sun round the back, low in the
    west), the rings and the cove."""
    sun = rt.VRaySun(pos=rt.Point3(-2600.0, 900.0, 1100.0), target=rt.Targetobject(pos=rt.Point3(350, 320, 0)))
    sun.name = "Sun"
    kit.setp(sun, "size_multiplier", 3.0)
    kit.setp(sun, "turbidity", 3.4)
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


# ------------------------------------------------------------ cameras, exposure
CAMS = {
    # from the room's south side, straight at the tapestry and the oak; the
    # target sits high so the auto tilt keeps the coffer and rings in frame
    # 28 mm: about 6.3 m of the north wall across the frame from 4.9 m back
    "bench3": ((330.0, 150.0, 125.0), (330.0, 640.0, 150.0), 28.0),
}
SIZE = {"final": (1440, 2160), "preview": (360, 540)}.get(B.QUALITY, (720, 1080))
B.PROBE = (200, 300)
# the plain white wall strip left of the tapestry, above the walnut table;
# the reference's whites read r/g 1.14, b/g 0.97 (ceiling 0.535, the boucle
# 0.55-0.62)
A.WB_PATCH["bench3"] = ((0.11, 0.42, 0.20, 0.52), "wall_paint", (1.14, 0.97))
PATCH_EXPOSURE = 0.45


def main():
    t0 = time.time()
    B.start()
    del RING_LIGHTS[:]
    build_architecture()
    A.build_backdrop()
    log("architecture built in %.0fs" % (time.time() - t0))
    build_furniture()
    build_pendant_and_lights()
    log("furniture built in %.0fs: %d nodes" % (time.time() - t0, len(rt.objects)))
    probe = os.environ.get("MF_BENCH_PROBE")
    if probe:
        B.dump_layout(probe)
        return
    A.apply_materials()
    # the rings' light comes from the lights inside them; their glow is for the eye
    B.quiet_emitters(("emissive_warm", "alabaster"))
    # the rings are lit from inside: at the recipe's soft glow they read as
    # grey stone under the coffer's cove
    ring = A._MAT_CACHE.get("alabaster")
    # (x2.6 burnt them to flat white in the full render: the veining went)
    if ring is not None and kit.setp(ring, "selfIllumination_multiplier", 1.5):
        log("alabaster rings: glow x1.5")
    setup_lights()
    log("scene built in %.0fs: %d nodes, %d MatForge materials" % (
        time.time() - t0, len(rt.objects), len(A._MAT_CACHE)))
    for label, g, nodes in B.PLACED:
        log("placed %s: %d nodes" % (label, len(nodes)))
    B.save_if_asked()
    B.render_views(CAMS, SIZE, PATCH_EXPOSURE)


B.run(main)
