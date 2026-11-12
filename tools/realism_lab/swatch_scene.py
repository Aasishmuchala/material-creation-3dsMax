"""Close-up studio swatch of every forged MatForge material (runs inside 3ds Max).

The lab's hero shots show many materials on a small prop across a room: a
brass ball twenty pixels wide says nothing about the brass. Here every
material gets the same shot: a ball on a slab, both in the material at its
real-world scale, on a neutral grey sweep under one soft key light, a strip
light for the highlights and a dim white dome. The frame is 1.5 tiles wide
(40-120 cm), so a 20 cm weave and a 180 cm stone slab both fill it; cut-outs
(leaves) stand as one card. One camera exposure for all, metered once on the
grey sweep, so the swatches compare: a leaf four times too bright shows.

Environment: MF_SWATCH_OUT (folder), MF_SWATCH_IDS (comma list, default all),
MF_SWATCH_SIZE (pixels, default 440), MF_SWATCH_TIME (minutes each, 0.5).
"""
import json
import os
import sys
import time
import traceback

from pymxs import runtime as rt

ROOT = r"C:\Users\aasis\matforge"
for p in (ROOT, os.path.join(ROOT, "tools", "apartment"), os.path.join(ROOT, "tools", "realism_lab")):
    if p not in sys.path:
        sys.path.insert(0, p)
import bench_common as B  # noqa: E402
import lab_materials as LM  # noqa: E402

A, kit, builder = B.A, B.kit, B.builder
OUT = os.environ.get("MF_SWATCH_OUT", os.path.join(ROOT, "tools", "realism_lab", "out", "swatches"))
SIZE = int(os.environ.get("MF_SWATCH_SIZE", "440"))
MINUTES = float(os.environ.get("MF_SWATCH_TIME", "0.5"))
GREY = 0.22                      # the sweep's albedo (linear)
LOG = []


def log(msg):
    LOG.append(msg)
    with open(os.path.join(OUT, "_swatch_log.json"), "w", encoding="utf-8") as fh:
        json.dump({"log": LOG}, fh, indent=1)


def grey_mtl():
    m = rt.VRayMtl()
    m.name = "SweepGrey"
    v = 255.0 * GREY ** (1.0 / 2.2)
    m.diffuse = rt.Color(v, v, v)
    kit.setp(m, "reflection", rt.Color(0, 0, 0))
    return m


def _aim(node, pos, d):
    """Turn a light so its emitting side (local -Z) points along d, at pos."""
    m = rt.matrixFromNormal(rt.Point3(-d[0], -d[1], -d[2]))
    m.row4 = rt.Point3(*pos)
    node.transform = m


def build(mid, f):
    """The set at scale f (1 = a 110 cm frame): sweep, slab, ball or card,
    lights, camera. Returns (camera, [nodes that take the material], card?)."""
    rt.delete(rt.objects)
    cls, _hero, _cam, tile, _prompt, extra = LM.MATERIALS[mid]
    cutout = extra.get("maptype", 4) is None and tile is None
    sweep = rt.Plane(width=3000.0 * f, length=3000.0 * f, pos=rt.Point3(0, 0, 0))
    sweep.material = grey_mtl()
    back = rt.Box(width=3000.0 * f, length=2.0, height=1500.0 * f, pos=rt.Point3(0, 260.0 * f, 0))
    back.material = sweep.material
    nodes = []
    if cutout:
        card = rt.Plane(width=90.0 * f, length=90.0 * f, lengthsegs=1, widthsegs=1, mapcoords=True)
        card.rotation = rt.EulerAngles(72.0, 0.0, 0.0)          # leaning back, facing the camera
        card.pos = rt.Point3(0, 10.0 * f, 44.0 * f)
        nodes.append(card)
    else:
        slab = kit.cbox(100.0 * f, 100.0 * f, 3.0 * f, 0.5 * f, 0.0, 0.0, 0.0, segs=3)
        ball = rt.Sphere(radius=21.0 * f, segs=72, pos=rt.Point3(-10.0 * f, 8.0 * f, 24.0 * f))
        nodes += [slab, ball]
        for n in nodes:
            u = rt.Uvwmap()
            u.maptype = 4
            u.length = u.width = u.height = float(tile or 100.0)
            rt.addModifier(n, u)
    key = rt.VRayLight()                                         # the soft key, high on the left
    key.type = 0
    key.size0, key.size1 = 90.0 * f, 70.0 * f
    _aim(key, (-170.0 * f, -90.0 * f, 190.0 * f), (170.0, 90.0, -175.0))
    kit.setp(key, "multiplier", 18.0)
    kit.setp(key, "invisible", True)
    strip = rt.VRayLight()                                       # a strip for the highlights, behind right
    strip.type = 0
    strip.size0, strip.size1 = 12.0 * f, 110.0 * f
    _aim(strip, (150.0 * f, 120.0 * f, 130.0 * f), (-150.0, -120.0, -115.0))
    kit.setp(strip, "multiplier", 30.0)
    kit.setp(strip, "invisible", True)
    dome = rt.VRayLight()
    dome.type = 1
    kit.setp(dome, "multiplier", 0.35)
    kit.setp(dome, "invisible", True)
    cam = rt.VRayPhysicalCamera(pos=rt.Point3(0.0, -235.0 * f, 150.0 * f),
                                target=rt.Targetobject(pos=rt.Point3(0.0, 0.0, 14.0 * f)))
    cam.film_width = 36.0
    cam.focal_length = 88.0
    cam.f_number = 8.0
    cam.ISO = 200.0
    cam.shutter_speed = SHUTTER[0]
    kit.setp(cam, "whiteBalance_preset", 0)
    cam.white_balance = rt.Color(255, 255, 255)
    return cam, nodes, cutout


SHUTTER = [8.0]


def meter():
    """One exposure for every swatch: the grey sweep's lower left corner to
    its own albedo (so a 0.22 grey reads 0.22 and a white reads white)."""
    r = rt.renderers.production
    keep = (r.progressive_noise_threshold, r.progressive_max_render_time)
    r.progressive_noise_threshold, r.progressive_max_render_time = 0.1, 0.15
    cam, nodes, _ = build("white_paint_wall", 1.0)
    rt.delete(nodes)
    for i in range(5):
        p = os.path.join(OUT, "_meter_%d.png" % i)
        cam.shutter_speed = SHUTTER[0]
        rt.render(camera=cam, outputwidth=160, outputheight=160, outputfile=p, vfb=False, quiet=True)
        m = max(sum(c * w for c, w in zip(A.mean_rgb(p, (0.05, 0.75, 0.3, 0.95)), (0.2126, 0.7152, 0.0722))), 1e-4)
        log("meter: sweep %.3f at 1/%.1f s" % (m, SHUTTER[0]))
        if abs(m / GREY - 1.0) < 0.04:
            break
        SHUTTER[0] = max(B.MIN_SHUTTER, min(4000.0, SHUTTER[0] * (m / GREY) ** 1.3))
    r.progressive_noise_threshold, r.progressive_max_render_time = keep


def main():
    os.makedirs(OUT, exist_ok=True)
    B.start()
    r = rt.renderers.production
    r.progressive_noise_threshold = 0.02
    r.progressive_max_render_time = MINUTES
    ids = [i for i in os.environ.get("MF_SWATCH_IDS", "").split(",") if i] or sorted(LM.MATERIALS)
    meter()
    for mid in ids:
        t0 = time.time()
        try:
            if not os.path.isfile(os.path.join(A.MAPS, mid, "manifest.json")):
                log("skip %s: no maps" % mid)
                continue
            cls, _hero, _cam, tile, _prompt, extra = LM.MATERIALS[mid]
            f = min(120.0, max(40.0, 1.5 * float(tile or 40.0))) / 110.0
            cam, nodes, cutout = build(mid, f)
            A.MATS[mid] = (mid, extra.get("metal"))
            kit.MAT_KEYS.setdefault(mid, "lab material")
            A._MAT_CACHE.pop(mid, None)
            mat = B.matforge(mid)
            mf = A._MANIFEST[mid]
            rt.select(nodes)
            if not cutout and float(builder.get_recipe(mf["class"]).get("displacement_mm", 0) or 0) > 0:
                builder.assign_to_selection(mat, mf["class"], height_map=mf["maps"].get("height"))
            else:
                for n in nodes:
                    n.material = mat
            rt.clearSelection()
            out = os.path.join(OUT, mid + ".png")
            rt.render(camera=cam, outputwidth=SIZE, outputheight=SIZE, outputfile=out, vfb=False, quiet=True)
            log("%s (%s) %.0fs" % (mid, mf["class"], time.time() - t0))
        except Exception:
            log("FAILED %s: %s" % (mid, traceback.format_exc().splitlines()[-1]))
    log("done")


try:
    main()
except Exception:
    os.makedirs(OUT, exist_ok=True)
    log("FAILED: " + traceback.format_exc())
