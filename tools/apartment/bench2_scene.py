"""MatForge benchmark 2 - a moody contemporary living room (runs inside 3ds Max).

The style of the user's second Pinterest reference, in an own composition:
a burnished copper Venetian-plaster feature wall between a plasterboard
bulkhead (track spots in its slot) and a grey microcement pier, a long low
beige chenille sofa with pill arms, a black marble pebble coffee table on
bronze pedestals with books, a stone bowl, a glass bottle with a twisted
branch and a brass ribbon, a charcoal loop-pile rug on polished white marble
tiles, a branch chandelier of clear glass globes, a taupe lacquered credenza
with three abstract sculptures, an olive tree on a walnut stand. The pieces
come from furn_bench2_*.py and bench2_arch.py; EVERY material is made by
MatForge from a forged Runway reference (bench_common.matforge()).

Plan (Max cm, Z up): the room is x 0..620, y 0..640, ceiling 290; the camera
stands at the coffee table's near side looking straight at the feature wall
(north). Daylight comes in through two tall east windows out of frame (the
sun is round the back of the building); the chandelier's six filament bulbs
and three track spots light it warm.

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
import bench2_arch  # noqa: E402  (after B: bound to the kit A reloaded)
import furn_bench2_decor  # noqa: E402
import furn_bench2_lights  # noqa: E402
import furn_bench2_sofa  # noqa: E402
import furn_bench2_tables  # noqa: E402

for _m in (bench2_arch, furn_bench2_decor, furn_bench2_lights, furn_bench2_sofa, furn_bench2_tables):
    importlib.reload(_m)

H = 290.0                       # ceiling height, cm

# ------------------------------------------------------------ MatForge materials
# the pieces' keys -> forged references (lab material id, metal[, class])
A.MATS.update({
    "copper_plaster": ("copper_plaster", None), "microcement": ("grey_microcement", None),
    "chenille": ("beige_chenille", None), "nero_marquina": ("nero_marquina", None),
    "rug": ("grey_loop_rug", None), "lacquer_taupe": ("taupe_lacquer", None),
    "olive_card": ("olive_sprig", None),
    # a woody trunk and twigs (the green stalk material made the olive a sapling)
    "stem": ("tree_bark", None),
    # the pebble table's pedestals: the brass photo with the named metal
    # "bronze" came out polished gold (bronze's F0 is as bright as brass's)
    "bronze": ("dark_bronze", None),
    # one polished slab photo, each tile its own window into it (no grout in it)
    "marble_floor": ("calacatta_table", None),
})

# ------------------------------------------------------------ plan (Max cm)
ROOM = (0.0, 0.0, 620.0, 640.0)
EXT_T, INT_T = 40.0, 20.0
TOP = H + 15.0
SK_TOP = 8.15                    # the shadow-gap reveal: wall plaster stops here (bench2_arch)
REVEAL = 1.5                     # reveal depth behind the wall face
PIER = (500.0, 590.0, 620.0, 640.0)        # microcement pier in the north-east corner
PANEL_X = (80.0, 500.0)                    # copper panel between the bulkhead and the pier
BULK_W = 80.0                              # bulkhead along the west wall
E_WINS = ((100.0, 280.0), (330.0, 510.0))  # east windows (y spans), floor to 260
WIN_TOP = 260.0


def wall_with_reveal(name, axis, c_face, c_back, a0, a1, openings=()):
    """A wall from the shadow-gap reveal up (SK_TOP), and its foot set back
    behind the reveal profile's web below it (at exactly REVEAL the foot's
    face lay on the web's and the two fought in the render)."""
    sgn = 1.0 if c_back > c_face else -1.0
    back = bench2_arch.SK_D + bench2_arch.SK_T + 0.05
    B.wall(name, axis, *sorted((c_face, c_back)), a0, a1, TOP, openings, base=SK_TOP)
    B.wall(name + "Foot", axis, *sorted((c_face + sgn * back, c_back)), a0, a1, SK_TOP + 0.5,
           [(b0, b1, z0, z1) for b0, b1, z0, z1 in openings if z0 <= 0.0], base=-3.0)


def build_shell():
    x0, y0, x1, y1 = ROOM
    px0, py0, px1, py1 = PIER
    wins = [(a, b, 0.0, WIN_TOP) for a, b in E_WINS]
    wall_with_reveal("WallN", "x", y1, y1 + EXT_T, x0 - INT_T, x1 + EXT_T)
    wall_with_reveal("WallE", "y", x1, x1 + EXT_T, y0 - INT_T, y1, wins)
    wall_with_reveal("WallS", "x", y0, y0 - INT_T, x0 - INT_T, x1)
    wall_with_reveal("WallW", "y", x0, x0 - INT_T, y0, y1)
    # the pier: microcement on its room faces, its own reveal at the foot
    B.box("Pier", px0, px1, py0, py1, SK_TOP, TOP, "microcement", 200.0)
    B.box("PierFoot", px0 + REVEAL, px1, py0 + REVEAL, py1, -3.0, SK_TOP + 0.5, "metal_black", 25.0)
    B.box("Ceiling", x0, x1, y0, y1, H, TOP, "ceiling")
    # slim black steel window frames with 6 mm glass, set near the outer face
    for k, (a, b) in enumerate(E_WINS):
        xf = x1 + EXT_T - 8.0
        for (ya, yb, za, zb) in ((a, a + 5.0, 0.0, WIN_TOP), (b - 5.0, b, 0.0, WIN_TOP),
                                 (a, b, WIN_TOP - 5.0, WIN_TOP), (a, b, 0.0, 4.0),
                                 ((a + b) / 2.0 - 2.0, (a + b) / 2.0 + 2.0, 4.0, WIN_TOP - 5.0)):
            B.box("EWinFrame_%d" % k, xf - 3.0, xf + 3.0, ya, yb, za, zb, "metal_black", 25.0)
        B.box("EWinGlass_%d" % k, xf - 0.3, xf + 0.3, a + 5.0, b - 5.0, 4.0, WIN_TOP - 5.0, "glass", 100.0)
        # the reveal floor: the skirting stops at the window and the wall's
        # foot starts behind it, which left a slit down into the void below
        B.box("EWinFoot_%d" % k, x1 - 0.1, xf - 3.0, a, b, -3.0, 0.0, "microcement", 100.0)
    g = rt.Plane(width=8000, length=8000, pos=rt.Point3(310, 320, -15))
    g.name = "Ground_Far"
    A.finish(g, "ground", 150)


def build_architecture():
    x0, y0, x1, y1 = ROOM
    build_shell()
    B.put("floor", bench2_arch.build_marble_floor, rect_cm=ROOM, seed=2)
    B.put("skirting", bench2_arch.build_shadow_skirting, rect_cm=ROOM,
          openings=[("e", a, b) for a, b in E_WINS])
    pw = PANEL_X[1] - PANEL_X[0]
    B.put("feature_wall", bench2_arch.build_feature_wall, (PANEL_X[0] + PANEL_X[1]) / 2.0, y1, 0.0, 0.0,
          width=pw, height=H, seed=3)
    # bulkhead along the west wall (its wall side is local +Y, turned to -X)
    B.put("bulkhead", bench2_arch.build_bulkhead, x0 + BULK_W / 2.0, (y0 + y1) / 2.0, H, 90.0,
          length=y1 - y0, width=BULK_W)
    # brass switch on the pier's face, at the light-switch height
    B.put("switch", bench2_arch.build_switch_plate, PIER[0] + 30.0, PIER[1], 0.0, 0.0, centre_z=105.0)


# ------------------------------------------------------------ furniture
CX = (PANEL_X[0] + PANEL_X[1]) / 2.0       # 290: everything centres on the panel
CREDENZA_Y = ROOM[3] - bench2_arch.FW_PROUD - 1.0 - 22.5
SOFA_Y = CREDENZA_Y - 22.5 - 8.0 - 50.0    # 8 cm behind its back to the credenza
TABLE = (CX + 8.0, 398.0, 6.0)             # x, y, rotation
CHANDELIER = (CX - 60.0, 468.0)
OLIVE = (CX + 180.0, 530.0)                # its stand clear of the rug, its crown of the pier


def build_rug(w=320.0, l=300.0):
    """Hand-loomed loop-pile rug, 1.2 cm thick, its loops from MatForge
    displacement (box-mapped at the reference's 60 cm). Long enough that the
    sofa's whole plinth stands on it (half on, it would rock)."""
    n = kit.cbox(w, l, 1.2, 0.4, 0.0, 0.0, 0.0, segs=2)
    n.name = "LoopRug"
    kit.part(n, "rug", 60.0)
    return kit.group("LoopRug_G", [n])


def build_furniture():
    tx, ty, trot = TABLE
    B.put("credenza", furn_bench2_decor.build_credenza, CX, CREDENZA_Y, 0.0, 0.0, length=300.0)
    # the sculptures on the credenza's left half, mirrored from the module's
    # suggestion (its right half)
    builders = {"sculpture_head": furn_bench2_decor.build_sculpture_head,
                "sculpture_arch": furn_bench2_decor.build_sculpture_arch,
                "sculpture_wire": furn_bench2_decor.build_sculpture_wire}
    for key, dx, dy, z, rot, kw in furn_bench2_decor.DRESSING:
        B.put(key, builders[key], CX - dx, CREDENZA_Y + dy, z, -rot, **kw)
    # x 120..440, y 280..580: under the sofa's whole plinth, clear of the olive's stand
    B.put("rug", build_rug, CX - 10.0, 430.0, 0.0, 0.0)
    B.put("sofa", furn_bench2_sofa.build_sofa, CX, SOFA_Y, 1.2, 0.0, width=270.0, seed=0)
    B.put("table", furn_bench2_tables.build_coffee_table, tx, ty, 1.2, trot, seed=0)
    B.put("dressing", furn_bench2_tables.build_table_dressing, tx, ty, 1.2, trot, seed=0)
    B.put("olive", furn_bench2_decor.build_olive_tree, OLIVE[0], OLIVE[1], 0.0, 30.0, seed=0)


# ------------------------------------------------------------ light
BULBS = []        # (VRayLight, world position)


def _aim(node, pos, d):
    """Turn a light so its local -Z (a disc light's emitting side) points
    along d, and put it at pos."""
    m = rt.matrixFromNormal(rt.Point3(-d[0], -d[1], -d[2]))
    m.row4 = rt.Point3(*pos)
    node.transform = m


# The six filament bulbs glow (their self-lit filaments) but carry no lights:
# with the lights on, the light cache sprayed fireflies over 1.2 % of the
# frame (0.05 % with them off) while 1300 lm added nothing measurable to a
# daylit room; bulb size, shadows, visibility, units, one bulb for six, the
# fixture and the marble made no difference, and brute-force GI instead of
# the cache traded the fireflies for noise the denoiser smeared into swirls.
BULB_LIGHTS = False


def build_chandelier_and_bulbs():
    """The chandelier from the ceiling, and a 2700 K sphere light (lm units)
    in each of its six filament bulbs."""
    start = len(kit.PARTS)
    try:
        g, bulbs = furn_bench2_lights.build_chandelier(drop=60.0, seed=0)
    except Exception as exc:
        log("piece chandelier failed: %s" % exc)
        return
    kit.place(g, CHANDELIER[0], CHANDELIER[1], H, 0.0)
    nodes = []
    for node, key, tile, maptype in kit.PARTS[start:]:
        A.finish(node, key, tile or 100.0, maptype)
        nodes.append(node)
    B.PLACED.append(("chandelier", g, nodes))
    for i, (bx, by, bz) in enumerate(bulbs if BULB_LIGHTS else ()):
        lt = rt.VRayLight()
        lt.name = "Bulb_%d" % i
        lt.type = 2                                   # sphere
        kit.setp(lt, "size0", 0.9)                    # inside the 2.2 cm bulb glass
        if not kit.setp(lt, "normalizeColor", 1):
            log("chandelier: no lm units on VRayLight")
        kit.setp(lt, "multiplier", 220.0)             # a 2 W decorative filament bulb
        kit.setp(lt, "color_mode", 1)
        kit.setp(lt, "color_temperature", 2400.0)
        kit.setp(lt, "invisible", True)               # the filament mesh shows instead
        # nor in reflections or refractions: V-Ray's GI caustics are on (the
        # mirror-polished floor's reflection carries much of the room's
        # bounce light), and a GI ray that found this 0.9 cm, 220 lm sphere
        # through the globe or in the marble was a firefly; the glowing
        # filament is what a mirror shows anyway
        kit.setp(lt, "affect_reflections", False)
        p = (CHANDELIER[0] + bx, CHANDELIER[1] + by, H + bz)
        lt.pos = rt.Point3(*p)
        # The bulb's own cap, socket, filament and envelope sit a centimetre
        # from a 220 lm point of light: lit by it they were thousands of times
        # brighter than the room, and every GI ray that chanced on them was a
        # firefly (1.2 % of the preview's pixels; 0.05 % with the bulbs off,
        # nothing else made a difference). They are left out of its light.
        near = [n for n in nodes if str(n.name) in ("Chandelier_Sockets", "Chandelier_BulbMetal",
                                                   "Chandelier_Filament", "Chandelier_BulbGlass")]
        try:
            lt.excludeList = rt.Array(*near)
        except Exception as exc:
            log("chandelier: bulb hardware not excluded from its light (%s)" % exc)
        BULBS.append((lt, p))
    log("chandelier: %d bulbs" % len(BULBS))


# track spots in the bulkhead's slot, each aimed at a target: (spot y,
# target point). Each sits with its adapter along the slot (turned 90 deg)
# and swivels on its stem towards its target
SPOTS = [(600.0, (CX - 52.0, CREDENZA_Y + 2.0, 85.0)),      # the head
         (515.0, (CX - 92.0, CREDENZA_Y + 2.5, 70.0)),      # the arch
         (430.0, (CX + 70.0, ROOM[3] - 4.0, 175.0))]        # the copper wall


def build_track_spots():
    slot_x = ROOM[0] + BULK_W / 2.0
    z0 = H - 25.0 + 5.0 - 0.1 - furn_bench2_lights.ADAPTER_UP     # adapter top just under the channel top
    rot = 90.0                                                    # the adapter's X along the slot (world Y)
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    for i, (sy, (tx, ty, tz)) in enumerate(SPOTS):
        d = (tx - slot_x, ty - sy, tz - z0)
        hor = math.hypot(d[0], d[1])
        tilt = math.degrees(math.atan2(hor, -d[2]))
        pan = math.degrees(math.atan2(d[0], -d[1])) - rot      # the tilt side (local -Y) onto d
        B.put("spot%d" % i, furn_bench2_lights.build_track_spot, slot_x, sy, z0, rot, tilt_deg=tilt, pan_deg=pan)
        (lx, ly, lz), (bx, by, bz) = furn_bench2_lights.track_spot_aim(tilt, pan)
        pos = (slot_x + lx * c - ly * s, sy + lx * s + ly * c, z0 + lz)
        beam = (bx * c - by * s, bx * s + by * c, bz)
        lt = rt.VRayLight()
        lt.name = "Spot_%d" % i
        lt.type = 4                                   # disc
        # the LED's own radius, just in front of it: a 2.2 cm disc sat half
        # inside the solid anti-glare baffle and lost half its light
        kit.setp(lt, "size0", furn_bench2_lights.BAFFLE_HOLE - 0.1)
        kit.setp(lt, "normalizeColor", 1)
        kit.setp(lt, "multiplier", 450.0)             # a 6 W LED spot
        kit.setp(lt, "color_mode", 1)
        kit.setp(lt, "color_temperature", 3000.0)
        if not (kit.setp(lt, "lightDistribution", 0.85) or kit.setp(lt, "directional", 0.85)):
            log("track spot: no directional setting on VRayLight")
        kit.setp(lt, "invisible", True)
        # out of reflections too, as the bulbs: the ceiling's GI rays met these
        # tiny 450 lm discs in the polished marble by chance (warm fireflies over
        # the upper frame); the LED face mesh shows in a mirror instead
        kit.setp(lt, "affect_reflections", False)
        _aim(lt, (pos[0] + 0.05 * beam[0], pos[1] + 0.05 * beam[1], pos[2] + 0.05 * beam[2]), beam)


def setup_lights():
    """Sky through the east windows (the sun is round the back of the
    building, low in the west), the chandelier's bulbs and the track spots."""
    sun = rt.VRaySun(pos=rt.Point3(-2600.0, 900.0, 1200.0), target=rt.Targetobject(pos=rt.Point3(310, 320, 0)))
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
    # straight at the feature wall from the coffee table's near side;
    # 36 mm film across the portrait frame's width
    "bench2": ((CX, 210.0, 110.0), (CX, 640.0, 90.0), 26.0),
}
SIZE = {"final": (1600, 1880), "preview": (400, 470)}.get(B.QUALITY, (800, 940))
B.PROBE = (200, 235)
# the ceiling over the sofa, right of the chandelier: the reference's
# ceiling reads warm (r/g 1.22, b/g 0.80) and dim (0.22 linear)
A.WB_PATCH["bench2"] = ((0.47, 0.05, 0.72, 0.14), "ceiling", (1.17, 0.85))
PATCH_EXPOSURE = 0.22


def diag(key, cam):
    """MF_BENCH_DIAG: quick probes with one suspect switched off at a time,
    to find what sprays the fireflies (count them in the _diag_* frames)."""
    r = rt.renderers.production
    keep = (r.progressive_noise_threshold, r.progressive_max_render_time)
    r.progressive_noise_threshold, r.progressive_max_render_time = 0.05, 0.3

    def lights(prefix, on):
        for n in rt.lights:
            if str(n.name).startswith(prefix):
                kit.setp(n, "on", on)

    def nodes(pred, on):
        for n in rt.objects:
            if pred(n):
                n.renderable = on

    def bulb_size(on):                       # off = the test: 3 cm bulbs
        for lt, _p in BULBS:
            kit.setp(lt, "size0", 0.9 if on else 3.0)

    def bulb_all_excluded(on):               # off = the test: the whole chandelier out of the bulbs' light
        chand = [n for n in rt.objects if str(n.name).startswith("Chandelier_")]
        near = [n for n in chand if str(n.name) in ("Chandelier_Sockets", "Chandelier_BulbMetal",
                                                    "Chandelier_Filament", "Chandelier_BulbGlass")]
        for lt, _p in BULBS:
            lt.excludeList = rt.Array(*(near if on else chand))

    def bulb_reflect(on):                    # off = the test: bulbs seen in reflections again
        for lt, _p in BULBS:
            kit.setp(lt, "affect_reflections", not on)

    def bulb_specular(on):                   # off = the test: no specular from the bulbs
        for lt, _p in BULBS:
            kit.setp(lt, "affect_specular", on)

    def bulb_visible(on):                    # off = the test: bulbs not invisible
        for lt, _p in BULBS:
            kit.setp(lt, "invisible", on)

    def bulb_units(on):                      # off = the test: default (image) units, dim
        for lt, _p in BULBS:
            kit.setp(lt, "normalizeColor", 1 if on else 0)
            kit.setp(lt, "multiplier", 220.0 if on else 30.0)

    def one_bulb(on):                        # off = the test: one bulb carries all six
        for k, (lt, _p) in enumerate(BULBS):
            kit.setp(lt, "on", on or k == 0)
            kit.setp(lt, "multiplier", 220.0 if on or k else 1320.0)

    def prob_lights(on):
        if not (kit.setp(r, "options_probabilisticLights", 2 if on else 0)
                or kit.setp(r, "options_probabilisticLights", on)):
            log("diag: no options_probabilisticLights")

    def light_cache(on):
        kit.setp(r, "gi_secondary_type", 3 if on else 2)

    def shadows(on):
        for lt, _p in BULBS:
            kit.setp(lt, "castShadows", on)

    log("diag: probabilistic lights = %s" % (getattr(r, "options_probabilisticLights", "?"),))
    variants = [("base", None), ("no_bulbs", lambda on: lights("Bulb_", on)), ("bulbs_visible", bulb_visible),
                ("bulbs_image_units", bulb_units), ("one_bulb", one_bulb), ("no_prob_lights", prob_lights),
                ("no_light_cache", light_cache), ("bulbs_no_shadow", shadows)]
    for name, toggle in variants:
        if toggle:
            toggle(False)
        B._quick(cam, "diag_" + name, key, 0)
        if toggle:
            toggle(True)
        log("diag %s done" % name)
    r.progressive_noise_threshold, r.progressive_max_render_time = keep


def main():
    t0 = time.time()
    B.start()
    del BULBS[:]
    build_architecture()
    A.build_backdrop()
    log("architecture built in %.0fs" % (time.time() - t0))
    build_furniture()
    build_chandelier_and_bulbs()
    build_track_spots()
    log("furniture built in %.0fs: %d nodes" % (time.time() - t0, len(rt.objects)))
    probe = os.environ.get("MF_BENCH_PROBE")
    if probe:
        B.dump_layout(probe)
        return
    A.apply_materials()
    B.quiet_emitters()
    setup_lights()
    log("scene built in %.0fs: %d nodes, %d MatForge materials" % (
        time.time() - t0, len(rt.objects), len(A._MAT_CACHE)))
    for label, g, nodes in B.PLACED:
        log("placed %s: %d nodes" % (label, len(nodes)))
    B.save_if_asked()
    B.render_views(CAMS, SIZE, PATCH_EXPOSURE, before=diag if os.environ.get("MF_BENCH_DIAG") else None)


B.run(main)
