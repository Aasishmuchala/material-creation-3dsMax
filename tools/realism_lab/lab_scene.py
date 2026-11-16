"""MatForge realism lab — Max side (run through 3dsmaxbatch, see lab.py render).

Models a daylit living room (floor, walls with a window, ceiling, a three-seat
sofa, coffee table, rug, floor lamp, planter and table props), lights it with
V-Ray sun + sky through a portal, and renders each job: one MatForge material
built by maxplugin.builder, put on its hero objects at real-world scale, framed
by the matching camera.

Environment:
  MF_LAB_JOBS   path to a jobs JSON written by lab.py
  MF_LAB_OUT    folder for renders + per-job JSON
  MF_LAB_ONLY   optional comma list of job ids (manual runs; lab.py clears it)
  MF_LAB_FAST   "1" -> small, quick renders (layout checks)
  MF_LAB_SIZE   "WxH" render size (lab.py sets it; default 1280x800, fast 640x400)
"""
import json
import math
import os
import sys
import time
import traceback

from pymxs import runtime as rt

ROOT = os.environ.get("MATFORGE_ROOT") or r"C:\Users\aasis\matforge"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import importlib  # noqa: E402

# maxplugin.builder is imported in the try at the bottom: a builder that does
# not import then writes a fatal _summary.json instead of killing the run
# before its first log line.


def _size(spec, default):
    try:
        w, h = (int(v) for v in spec.lower().split("x"))
        return w, h
    except ValueError:
        return default


JOBS = os.environ.get("MF_LAB_JOBS", "")
OUT = os.environ.get("MF_LAB_OUT", os.path.join(ROOT, "tools", "realism_lab", "out", "renders"))
ONLY = [s for s in os.environ.get("MF_LAB_ONLY", "").split(",") if s]
FAST = os.environ.get("MF_LAB_FAST") == "1"
SIZE = _size(os.environ.get("MF_LAB_SIZE", ""), (640, 400) if FAST else (1280, 800))
DENOISE = os.environ.get("MF_LAB_DENOISE", "vray_mild")
os.makedirs(OUT, exist_ok=True)
LOG = []


def log(msg):
    LOG.append(str(msg))
    try:
        print("[lab] " + str(msg))
    except Exception:
        pass
    # rewritten on every line so a Max crash still leaves the job it died on
    try:
        with open(os.path.join(OUT, "_lab_log.json"), "w", encoding="utf-8") as fh:
            json.dump({"log": LOG, "running": True}, fh, indent=1)
    except OSError:
        pass


def mx(code):
    """Run a MAXScript snippet (used where pymxs ergonomics are awkward)."""
    return rt.execute(code)


def setp(obj, name, value):
    try:
        if rt.isProperty(obj, rt.Name(name)):
            setattr(obj, name, value)
            return True
    except Exception as exc:
        log("set %s failed: %s" % (name, exc))
    return False


def col(r, g, b):
    """0-1 linear-ish floats -> Max colour."""
    return rt.Color(r * 255.0, g * 255.0, b * 255.0)


# ---------------------------------------------------------------- materials
def plain_mtl(name, diffuse, rough=0.5, refl=1.0, metal=0.0, ior=1.5, sheen=None,
              refract=None, coat=None):
    m = rt.VRayMtl()
    m.name = name
    m.diffuse = col(*diffuse)
    m.reflection = col(refl, refl, refl)
    m.brdf_useRoughness = True
    m.reflection_glossiness = rough
    m.reflection_metalness = metal
    m.refraction_ior = ior
    if sheen:
        m.sheen_color = col(*sheen[0])
        m.sheen_glossiness = sheen[1]
    if refract:
        m.refraction = col(1, 1, 1)
        m.refraction_ior = refract
        m.refraction_affectShadows = True
    if coat:
        m.coat_amount = coat
        m.coat_glossiness = 0.05
    return m


def context_materials():
    return {
        "wall": plain_mtl("ctx_wall", (0.72, 0.71, 0.68), rough=0.55),
        "ceiling": plain_mtl("ctx_ceiling", (0.80, 0.80, 0.79), rough=0.6),
        "floor": plain_mtl("ctx_floor", (0.33, 0.24, 0.16), rough=0.38),
        "sofa": plain_mtl("ctx_sofa", (0.42, 0.41, 0.39), rough=0.85,
                          sheen=((0.25, 0.25, 0.25), 0.4)),
        "wood": plain_mtl("ctx_wood", (0.12, 0.07, 0.04), rough=0.35),
        "metal": plain_mtl("ctx_metal", (0.55, 0.55, 0.55), rough=0.25, metal=1.0),
        "glass": plain_mtl("ctx_glass", (0.0, 0.0, 0.0), rough=0.0, refract=1.52),
        "ceramic": plain_mtl("ctx_ceramic", (0.82, 0.81, 0.78), rough=0.12),
        "rug": plain_mtl("ctx_rug", (0.55, 0.52, 0.47), rough=0.9,
                         sheen=((0.2, 0.2, 0.2), 0.5)),
        "paper": plain_mtl("ctx_paper", (0.62, 0.58, 0.50), rough=0.7),
        "wax": plain_mtl("ctx_wax", (0.85, 0.82, 0.74), rough=0.4),
        "pot": plain_mtl("ctx_pot", (0.45, 0.25, 0.16), rough=0.7),
        "leaf": plain_mtl("ctx_leaf", (0.06, 0.16, 0.05), rough=0.4),
        "shade": plain_mtl("ctx_shade", (0.85, 0.83, 0.78), rough=0.9),
        "plastic": plain_mtl("ctx_plastic", (0.70, 0.12, 0.08), rough=0.15),
        "panel": plain_mtl("ctx_panel", (0.9, 0.9, 0.9), rough=0.5),
        "ground": plain_mtl("ctx_ground", (0.25, 0.24, 0.22), rough=0.9),
    }


# ---------------------------------------------------------------- geometry
GROUPS = {}       # group name -> [nodes]
CTX = {}          # node name -> context material key


def add(group, node, ctx):
    node.name = "%s_%d" % (group, len(GROUPS.get(group, [])) + 1)
    GROUPS.setdefault(group, []).append(node)
    CTX[str(node.name)] = ctx
    return node


def cbox(w, l, h, fillet, x, y, z, segs=3):
    # Fillet_Segments etc.: ChamferBox silently ignores filletSegs / widthsegs
    return rt.ChamferBox(width=w, length=l, height=h, fillet=fillet, Fillet_Segments=segs,
                         Width_Segments=1, Length_Segments=1, Height_Segments=1,
                         pos=rt.Point3(x, y, z), mapcoords=True)


def box(w, l, h, x, y, z):
    return rt.Box(width=w, length=l, height=h, pos=rt.Point3(x, y, z), mapcoords=True)


def revolve(name, pts, x, y, z, segs=48, shell=None, smooth=1):
    """Revolve an (r, z) profile around the Z axis into a mesh at (x, y, z).

    Faces wind so normals point away from the axis (and down/up on caps drawn
    outward/inward), so an open profile is a vessel and a closed one a solid.
    """
    verts = []
    for r, zz in pts:
        for j in range(segs):
            a = 2.0 * math.pi * j / segs
            verts.append((x + r * math.cos(a), y + r * math.sin(a), z + zz))
    faces = []
    for i in range(len(pts) - 1):
        for j in range(segs):
            a = i * segs + j + 1
            b = i * segs + (j + 1) % segs + 1
            c = (i + 1) * segs + j + 1
            d = (i + 1) * segs + (j + 1) % segs + 1
            faces.append((a, b, c))
            faces.append((b, d, c))
    vs = ",".join("[%.4f,%.4f,%.4f]" % v for v in verts)
    fs = ",".join("[%d,%d,%d]" % f for f in faces)
    node = mx('(m = mesh name:"%s" vertices:#(%s) faces:#(%s)\n'
              'for f = 1 to m.numfaces do setFaceSmoothGroup m f 1\nupdate m\nm)'
              % (name, vs, fs))
    if shell:
        sm = rt.Shell()
        setp(sm, "outerAmount", float(shell))
        setp(sm, "innerAmount", 0.0)
        rt.addModifier(node, sm)
    if smooth:
        ts = rt.TurboSmooth()
        ts.iterations = smooth
        rt.addModifier(node, ts)
    return node


def soften(node, noise=None, smooth=1):
    if noise:
        nm = rt.Noisemodifier()
        setp(nm, "scale", noise[0])
        setp(nm, "strength", rt.Point3(noise[1], noise[1], noise[2]))
        setp(nm, "fractal", True)
        rt.addModifier(node, nm)
    if smooth:
        ts = rt.TurboSmooth()
        ts.iterations = smooth
        rt.addModifier(node, ts)


def build_room():
    # interior: x -300..300, y -250..250, z 0..280 (cm)
    floor = rt.Plane(width=600, length=500, widthsegs=1, lengthsegs=1, pos=rt.Point3(0, 0, 0))
    add("floor", floor, "floor")
    add("ceiling", box(612, 512, 10, 0, 0, 280), "ceiling")
    add("wall", box(624, 12, 290, 0, 256, 0), "wall")          # back wall (behind sofa)
    add("wall_side", box(624, 12, 290, 0, -256, 0), "wall")    # front wall (behind camera)
    add("wall_side", box(12, 500, 290, 306, 0, 0), "wall")     # right wall
    # left wall with a 320 x 215 window opening (y -160..160, z 35..250)
    add("wall_side", box(12, 500, 35, -306, 0, 0), "wall")
    add("wall_side", box(12, 500, 40, -306, 0, 250), "wall")
    add("wall_side", box(12, 90, 215, -306, -205, 35), "wall")
    add("wall_side", box(12, 90, 215, -306, 205, 35), "wall")
    # window frame mullion (thin dark metal) for realistic light shapes
    add("frame", box(6, 4, 215, -302, 0, 35), "metal")
    add("frame", box(6, 320, 4, -302, 0, 140), "metal")


def build_sofa():
    cx, cy = 50, 195
    add("sofa_leg", rt.Cylinder(radius=1.8, height=10, sides=24, pos=rt.Point3(cx - 100, cy - 36, 0)), "wood")
    add("sofa_leg", rt.Cylinder(radius=1.8, height=10, sides=24, pos=rt.Point3(cx + 100, cy - 36, 0)), "wood")
    add("sofa_leg", rt.Cylinder(radius=1.8, height=10, sides=24, pos=rt.Point3(cx - 100, cy + 36, 0)), "wood")
    add("sofa_leg", rt.Cylinder(radius=1.8, height=10, sides=24, pos=rt.Point3(cx + 100, cy + 36, 0)), "wood")
    base = cbox(222, 92, 20, 3.0, cx, cy, 10)
    add("sofa", base, "sofa")
    backf = cbox(222, 16, 66, 4.0, cx, cy + 38, 10)
    add("sofa", backf, "sofa")
    for sx in (-1, 1):
        arm = cbox(20, 92, 56, 6.0, cx + sx * 101, cy, 10, segs=4)
        soften(arm, noise=(80, 0.4, 0.4))
        add("sofa", arm, "sofa")
        seat = cbox(91, 74, 19, 7.0, cx + sx * 45.5, cy - 7, 30, segs=4)
        soften(seat, noise=(55, 0.8, 1.2))
        add("sofa", seat, "sofa")
        back = cbox(91, 22, 44, 9.0, cx + sx * 45.5, cy + 22, 47, segs=4)
        soften(back, noise=(50, 0.9, 1.0))
        rt.rotate(back, rt.angleaxis(-9, rt.Point3(1, 0, 0)))
        add("sofa", back, "sofa")
    # a scatter cushion
    cush = cbox(45, 14, 42, 9.0, cx - 72, cy + 6, 47, segs=4)
    soften(cush, noise=(30, 1.2, 1.0))
    rt.rotate(cush, rt.angleaxis(14, rt.Point3(0, 0, 1)))
    rt.rotate(cush, rt.angleaxis(-12, rt.Point3(1, 0, 0)))
    add("cushion", cush, "sofa")


def build_table_and_rug():
    add("rug", cbox(270, 185, 1.2, 0.5, 40, 85, 0, segs=2), "rug")
    tx, ty = 40, 60
    for dx in (-52, 52):
        for dy in (-26, 26):
            add("table_leg", rt.Cylinder(radius=1.4, height=38, sides=32,
                                         pos=rt.Point3(tx + dx, ty + dy, 1.2)), "metal")
    add("table_top", cbox(124, 64, 4.0, 0.8, tx, ty, 39.2, segs=3), "wood")


def build_props():
    z0 = 43.2
    # vase (clear glass) — revolved profile, 0.4 cm wall
    vase = revolve("vase_src", [(0.01, 0), (5.5, 0.2), (7.5, 6), (8.0, 14), (5.2, 24),
                                (3.2, 29), (3.6, 32)], 45, 72, z0, shell=0.4)
    add("vase", vase, "glass")
    # ceramic bowl
    bowl = revolve("bowl_src", [(0.01, 0), (4.5, 0.1), (9.0, 2.5), (11.5, 6.0),
                                (12.0, 7.0)], 68, 52, z0, shell=0.5)
    add("bowl", bowl, "ceramic")
    # metal spheres / objects
    add("metal_obj", rt.Sphere(radius=5.0, segs=64, pos=rt.Point3(90, 70, z0 + 5.0)), "metal")
    add("metal_obj", rt.Torus(radius1=4.5, radius2=1.2, segs=64, sides=32,
                              pos=rt.Point3(100, 50, z0 + 1.2)), "metal")
    # books
    add("book", cbox(24, 17, 2.6, 0.2, 22, 45, z0, segs=1), "paper")
    b2 = cbox(22, 15, 2.2, 0.2, 23, 45, z0 + 2.6, segs=1)
    rt.rotate(b2, rt.angleaxis(8, rt.Point3(0, 0, 1)))
    add("book", b2, "paper")
    # candle on the books
    add("candle", rt.Cylinder(radius=3.6, height=11, sides=48, heightsegs=1,
                              pos=rt.Point3(22, 45, z0 + 4.8)), "wax")
    # crystal / gem
    gem = rt.GeoSphere(radius=3.2, segs=2, baseType=1, smooth=False, pos=rt.Point3(48, 42, z0 + 2.6))
    add("gem", gem, "glass")
    # glass of water: tumbler + a water body that meets the inner wall
    tumbler = revolve("tumbler_src", [(0.01, 0), (3.6, 0), (4.0, 10.5)], 88, 40, z0, shell=0.25)
    add("tumbler", tumbler, "glass")
    water = revolve("water_src", [(0.01, 0.05), (3.6, 0.05), (3.886, 7.5), (0.01, 7.5)],
                    88, 40, z0, smooth=0)
    add("water", water, "glass")
    # glossy plastic tray + matte plastic box + rubber ball on the floor
    add("plastic_obj", cbox(30, 20, 2.0, 0.9, 68, 78, z0, segs=4), "plastic")
    add("plastic_matte", cbox(30, 22, 18, 2.0, 220, 40, 0, segs=4), "plastic")
    add("rubber_obj", rt.Sphere(radius=10, segs=64, pos=rt.Point3(-40, 10, 10)), "plastic")
    # floor lamp beside the sofa
    lx, ly = 205, 215
    add("lamp", rt.Cylinder(radius=16, height=2.0, sides=64, pos=rt.Point3(lx, ly, 0)), "metal")
    add("lamp", rt.Cylinder(radius=1.0, height=150, sides=24, pos=rt.Point3(lx, ly, 2)), "metal")
    shade = revolve("shade_src", [(22, 0), (15, 26)], lx, ly, 140, segs=64, shell=0.3)
    add("shade", shade, "shade")
    # planter by the window: terracotta pot + leaf cards
    px, py = -230, 200
    pot = revolve("pot_src", [(0.01, 0), (14, 0), (17, 34), (18, 36)], px, py, 0, shell=1.2)
    add("pot", pot, "pot")
    add("soil", rt.Cylinder(radius=16.0, height=1.0, sides=48, pos=rt.Point3(px, py, 31)), "ground")
    for i in range(9):
        ang = i * 40.0
        leaf = rt.Plane(width=26, length=34, widthsegs=6, lengthsegs=8,
                        pos=rt.Point3(px, py, 0), mapcoords=True)
        bend = rt.Bend()
        setp(bend, "BendAngle", 55.0)
        setp(bend, "BendAxis", 1)
        rt.addModifier(leaf, bend)
        h = 55 + (i % 3) * 18
        rt.rotate(leaf, rt.angleaxis(-60 + (i % 2) * 15, rt.Point3(1, 0, 0)))
        rt.rotate(leaf, rt.angleaxis(ang, rt.Point3(0, 0, 1)))
        leaf.pos = rt.Point3(px + 14 * math.cos(math.radians(ang + 90)),
                             py + 14 * math.sin(math.radians(ang + 90)), h)
        add("leaf", leaf, "leaf")
    for i in range(5):
        stem = rt.Cylinder(radius=0.5, height=60 + i * 9, sides=12, pos=rt.Point3(px, py, 30))
        rt.rotate(stem, rt.angleaxis(-14 - i * 3, rt.Point3(1, 0, 0)))
        rt.rotate(stem, rt.angleaxis(i * 72, rt.Point3(0, 0, 1)))
        add("stem", stem, "leaf")
    # LED panel on the back wall (emissive test)
    add("led_panel", cbox(90, 3, 50, 0.6, 50, 248, 150, segs=2), "panel")
    # corten planter (rust test) and teak bench outside the window, frosted glass panel
    add("corten", box(80, 30, 40, -160, -170, 0), "metal")
    add("frosted_panel", box(60, 1.2, 90, 150, -120, 0), "glass")


def build_exterior():
    """Ground slab + kerb + bench used for exterior materials (asphalt, sand, teak)."""
    g = rt.Plane(width=3000, length=3000, widthsegs=1, lengthsegs=1, pos=rt.Point3(0, 1800, -0.5))
    add("ext_ground", g, "ground")
    add("ext_kerb", cbox(400, 25, 15, 1.5, 0, 700, -0.5, segs=2), "ground")
    add("ext_bench", cbox(180, 45, 5, 0.6, 60, 900, 42, segs=2), "wood")
    for dx in (-80, 80):
        add("ext_bench_leg", box(6, 40, 42, 60 + dx, 900, 0), "metal")


# ---------------------------------------------------------------- lighting
def setup_renderer():
    vray_cls = None
    for c in rt.RendererClass.classes:
        n = str(c)
        if "V_Ray" in n and "GPU" not in n and "RT" not in n:
            vray_cls = c
            break
    r = vray_cls()
    rt.renderers.production = r
    r.imageSampler_type = 3                      # progressive
    r.progressive_noise_threshold = 0.03 if FAST else 0.01
    # minutes; a safety net only: other Max sessions share the CPU, and a
    # tight cap would hand the denoiser frames that never reached threshold
    r.progressive_max_render_time = 0.4 if FAST else 6.0
    r.progressive_maxSamples = 200 if FAST else 400
    r.gi_on = True
    r.gi_primary_type = 2
    r.gi_secondary_type = 3
    # interiors: more light-cache paths, or flat walls go blotchy (seen at 1280 px)
    r.lightcache_subdivs = 1000 if FAST else 2000
    # glossy rays must not read the light cache: its blotches showed up in
    # the satin sheen of painted walls
    r.lightcache_useForGlossyRays = False
    r.colorMapping_type = 6                      # Reinhard
    r.colorMapping_darkMult = 1.0
    r.colorMapping_brightMult = 0.55             # burn: soft highlight roll-off
    r.colorMapping_gamma = 2.2
    r.system_frameStamp_on = False
    # 16-bit PNGs: denoised walls band in 8 bits; lab.py dithers them down
    rt.pngio.setType(rt.Name("true48"))
    rt.pngio.setAlpha(False)
    try:
        rem = rt.maxOps.GetCurRenderElementMgr()
        rem.RemoveAllRenderElements()
        den = rt.VRayDenoiser()
        den.mode = 2
        kind = DENOISE
        log("denoiser %s" % kind)
        if kind == "off":
            den = None
        elif kind == "oidn":
            setp(den, "denoising_engine", 2)
            setp(den, "oidn_prefilter", True)
        elif kind == "vray_default":
            setp(den, "denoising_engine", 0)
            setp(den, "preSet", 1)
        else:                                    # vray_mild
            setp(den, "denoising_engine", 0)
            setp(den, "preSet", 0)
            setp(den, "strength", 0.5)
            setp(den, "radius", 5.0)
        if den is not None:
            rem.AddRenderElement(den)
    except Exception as exc:
        log("denoiser setup failed: %s" % exc)
    return r


def setup_lights():
    sun = rt.VRaySun(pos=rt.Point3(-1600, -900, 1100),
                     target=rt.Targetobject(pos=rt.Point3(40, 120, 0)))
    sun.name = "Sun"
    setp(sun, "intensity_multiplier", 1.0)
    setp(sun, "size_multiplier", 2.0)
    setp(sun, "turbidity", 2.8)
    sky = rt.VRaySky()
    rt.environmentMap = sky
    rt.useEnvironmentMap = True
    # Chaos's interior-day setup: sun + a dome driven by the same sky, with
    # the Adaptive Dome Light learning which part of the dome matters (no
    # portals needed). Named WindowPortal so ext_mode() can still toggle it.
    dome = rt.VRayLight()
    dome.name = "WindowPortal"
    dome.type = 1
    setp(dome, "texmap", rt.VRaySky())
    setp(dome, "texmap_on", True)
    # VRayLight defaults to multiplier 30 (a plane-light value); a physical
    # sky texture must be used at 1 or the sky outshines the sun 30:1
    setp(dome, "multiplier", 1.0)
    setp(dome, "dome_adaptive", True)
    setp(dome, "invisible", True)
    dome.pos = rt.Point3(0, 0, 300)
    return sun, dome


def ext_mode(on):
    """Exterior mode hides the room so ground materials sit under open sky."""
    interior = [g for g in GROUPS if not g.startswith("ext_")]
    for g in interior:
        for n in GROUPS[g]:
            n.isHidden = on
    for g in GROUPS:
        if g.startswith("ext_"):
            for n in GROUPS[g]:
                n.isHidden = not on
    # the sky dome lights interiors and exteriors alike: keep it on


# ---------------------------------------------------------------- cameras
CAMS = {
    #            position              target           focal mm
    "wide":   ((-150, -235, 125),  (60, 140, 70),   24),
    "floor":  ((-120, -215, 48),   (70, 120, 2),    28),
    "wall":   ((40, -170, 135),    (50, 250, 125),  32),
    "sofa":   ((185, -60, 105),    (30, 190, 45),   38),
    "sofa_close": ((120, 70, 80),  (35, 195, 45),   55),
    "table":  ((130, -45, 92),     (50, 60, 42),    42),
    "props":  ((62, -45, 75),      (62, 58, 46),    40),
    "lamp":   ((120, 60, 120),     (205, 215, 120), 45),
    "plant":  ((-120, 40, 90),     (-230, 200, 60), 40),
    "rug":    ((150, -60, 70),     (40, 80, 0),     32),
    "ext":    ((-40, 450, 65),     (60, 950, 10),   35),
    "ext_bench": ((150, 760, 80),  (60, 900, 40),   40),
    "panel":  ((60, -60, 140),     (50, 248, 150),  40),
    "corten": ((-60, -60, 70),     (-160, -170, 20), 40),
    "frosted": ((80, -30, 70),     (150, -120, 45),  40),
    "gem":    ((66, 8, 58),        (48, 42, 46),    90),
    "matte":  ((165, -35, 42),     (220, 40, 9),    50),
}
_CAM_NODES = {}


def camera(key):
    if key in _CAM_NODES:
        return _CAM_NODES[key]
    pos, tgt, focal = CAMS[key]
    cam = rt.VRayPhysicalCamera(pos=rt.Point3(*pos), target=rt.Targetobject(pos=rt.Point3(*tgt)))
    cam.name = "Cam_" + key
    setp(cam, "film_width", 36.0)
    setp(cam, "focal_length", float(focal))
    setp(cam, "exposure", 1)
    setp(cam, "ISO", 100.0)
    setp(cam, "f_number", 8.0)
    setp(cam, "shutter_speed", 30.0)
    setp(cam, "vignetting", False)
    setp(cam, "whiteBalance_preset", 4)
    _CAM_NODES[key] = cam
    return cam


# ---------------------------------------------------------------- jobs
def uvw(nodes, tile_cm, maptype=4):
    for n in nodes:
        try:
            for m in list(n.modifiers):
                if str(m.name) == "LabUVW":
                    rt.deleteModifier(n, m)
            u = rt.Uvwmap()
            u.name = "LabUVW"
            u.maptype = maptype
            u.length = tile_cm
            u.width = tile_cm
            u.height = tile_cm
            rt.addModifier(n, u)
        except Exception as exc:
            log("uvw on %s failed: %s" % (n.name, exc))


def apply_context(ctx_mats):
    for g, nodes in GROUPS.items():
        for n in nodes:
            n.material = ctx_mats[CTX[str(n.name)]]
            builder._remove_matforge_disp(n)


def render(cam, path, w, h):
    t0 = time.time()
    rt.render(camera=cam, outputwidth=w, outputheight=h, outputfile=path,
              vfb=False, quiet=True)
    return time.time() - t0


def lin_mean(path):
    """Mean linear luminance of an 8-bit sRGB render (for auto exposure)."""
    cs = builder._data_color_space()      # read the PNG's code values raw
    bm = rt.openBitMap(path, colorSpace=cs) if cs else rt.openBitMap(path, gamma=1.0)
    w, h = int(bm.width), int(bm.height)
    tot, n = 0.0, 0
    for yy in range(0, h, max(1, h // 24)):
        row = rt.getPixels(bm, rt.Point2(0, yy), w)
        for px in list(row)[::max(1, w // 32)]:
            for c, wt in ((px.r, 0.2126), (px.g, 0.7152), (px.b, 0.0722)):
                v = float(c) / 255.0
                v = v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
                tot += v * wt
            n += 1
    rt.close(bm)
    return tot / max(n, 1)


def calibrate(cam, key, target=0.15):
    """Two quick previews -> shutter speed that lands the base scene at `target`."""
    r = rt.renderers.production
    keep = (r.progressive_noise_threshold, r.progressive_max_render_time)
    r.progressive_noise_threshold, r.progressive_max_render_time = 0.08, 0.15
    for i in range(2):
        # a fresh file each pass: openBitMap returns Max's cached copy of a
        # path it has already loaded, which would freeze the measurement
        p = os.path.join(OUT, "_cal_%s_%d_%d.png" % (key, i, int(time.time())))
        render(cam, p, 320, 200)
        m = lin_mean(p)
        s = float(cam.shutter_speed)
        cam.shutter_speed = max(1.0, min(4000.0, s * m / target))
        log("calibrate %s: mean %.3f at 1/%.1f -> 1/%.1f" % (key, m, s, float(cam.shutter_speed)))
    r.progressive_noise_threshold, r.progressive_max_render_time = keep


def run():
    rt.resetMaxFile(rt.Name("noPrompt"))
    rt.units.SystemType = rt.Name("centimeters")
    rt.units.SystemScale = 1.0
    rt.units.DisplayType = rt.Name("metric")
    rt.units.MetricType = rt.Name("centimeters")
    setup_renderer()
    build_room()
    build_sofa()
    build_table_and_rug()
    build_props()
    build_exterior()
    setup_lights()
    ctx_mats = context_materials()
    apply_context(ctx_mats)
    ext_mode(False)
    log("scene built: %d groups, %d nodes" % (len(GROUPS), sum(len(v) for v in GROUPS.values())))

    jobs = []
    if JOBS and os.path.isfile(JOBS):
        with open(JOBS, encoding="utf-8") as fh:
            jobs = json.load(fh)
    if ONLY:
        jobs = [j for j in jobs if j["id"] in ONLY]
    w, h = SIZE
    calibrated = set()
    summary = []
    for job in jobs:
        # fast and size let lab.py --resume tell a layout check from a full render
        rec = {"id": job["id"], "ok": False, "fast": FAST, "size": [w, h]}
        t0 = time.time()
        log("job %s start" % job["id"])
        try:
            apply_context(ctx_mats)
            ext = job.get("cam", "").startswith("ext")
            ext_mode(ext)
            cam = camera(job["cam"])
            if job["cam"] not in calibrated and not job.get("no_cal"):
                calibrate(cam, job["cam"])
                calibrated.add(job["cam"])
            if job.get("manifest"):
                with open(job["manifest"], encoding="utf-8") as fh:
                    mf = json.load(fh)
                # maps forged without "Make it tile seamlessly" do not wrap:
                # no stochastic tiling for them
                mat = builder.build_material(mf["maps"], mf["name"], mf["class"],
                                             metal=job.get("metal"),
                                             tint=mf.get("transmission_tint"),
                                             anti_tile=mf.get("seamless", True),
                                             roughness_base=mf.get("roughness_base"))
                rec["builder_log"] = list(builder.LOG)
                heroes = []
                for g in job["hero"]:
                    heroes += GROUPS.get(g, [])
                if job.get("maptype", 4) is not None:     # None: keep the object's own UVs
                    uvw(heroes, float(job.get("tile_cm", 100.0)), job.get("maptype", 4))
                rt.select(heroes)
                builder.assign_to_selection(mat, mf["class"], height_map=mf["maps"].get("height"))
                rec["assign_log"] = list(builder.LOG[-3:])
            for extra in job.get("extra", []):
                mx(extra)
            path = os.path.join(OUT, job["id"] + ".png")
            t1 = time.time()
            rec["seconds"] = round(render(cam, path, w, h), 1)
            # the previous pass's PNG must not pass for this one's render
            rec["ok"] = os.path.isfile(path) and os.path.getmtime(path) >= t1 - 2.0
            if not rec["ok"]:
                rec["error"] = "render wrote no new " + path
            rec["path"] = path
            rec["shutter"] = float(cam.shutter_speed)
        except Exception:
            rec["error"] = traceback.format_exc()
        rec["total_seconds"] = round(time.time() - t0, 1)
        summary.append(rec)
        with open(os.path.join(OUT, job["id"] + ".json"), "w", encoding="utf-8") as fh:
            json.dump(rec, fh, indent=1)
        log("job %s ok=%s %.0fs" % (job["id"], rec["ok"], rec["total_seconds"]))
    with open(os.path.join(OUT, "_summary.json"), "w", encoding="utf-8") as fh:
        json.dump({"jobs": summary, "log": LOG}, fh, indent=1)


try:
    from maxplugin import builder  # noqa: E402
    importlib.reload(builder)
    run()
except Exception:
    LOG.append(traceback.format_exc())
    with open(os.path.join(OUT, "_summary.json"), "w", encoding="utf-8") as fh:
        json.dump({"fatal": traceback.format_exc(), "log": LOG}, fh, indent=1)
