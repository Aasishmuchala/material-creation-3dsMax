"""Shared scaffolding for the MatForge benchmark scenes (runs inside 3ds Max).

The apartment scene imported as a library (its MatForge material table and
apply_materials, white balance on a wall patch, exposure probes, log), a
matforge() with the plugin's own stochastic-tiling rule, box and wall
helpers, piece placement with per-piece material remaps, and the portrait
render loop. Each bench<N>_scene.py fills in its room, pieces, light and
cameras and calls run(main).
"""
import importlib
import json
import os
import sys
import time
import traceback

from pymxs import runtime as rt

ROOT = r"C:\Users\aasis\matforge"
HERE = os.path.join(ROOT, "tools", "apartment")
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

# the apartment scene as a library: materials, exposure, white balance, log
os.environ["MF_APT_LIBRARY"] = "1"
_fresh = "apartment_scene" not in sys.modules
import apartment_scene as A  # noqa: E402
if not _fresh:
    importlib.reload(A)
os.environ.pop("MF_APT_LIBRARY", None)

import kit  # noqa: E402  (the module A reloaded: one MAT_KEYS, one PARTS)

builder = A.builder
log = A.log
QUALITY = A.QUALITY


# scene keys whose maps hold a regular structure the forge's pattern check
# does not flag (it looks for broad stripes and checks): a rug's fine ribs
# would jog at every stochastic tile seam
PATTERN_KEYS = set()


def matforge(key):
    """A.matforge with the plugin's own stochastic-tiling rule: only a map
    that tiles and carries no pattern (builder.build_from_manifest). The
    apartment's version tiled every seamless map stochastically, which would
    scramble a kilim's diamond rows."""
    if key in A._MAT_CACHE:
        return A._MAT_CACHE[key]
    lab_id, metal = A.MATS[key][:2]
    with open(os.path.join(A.MAPS, lab_id, "manifest.json"), encoding="utf-8") as fh:
        mf = json.load(fh)
    mclass = A.MATS[key][2] if len(A.MATS[key]) > 2 else mf["class"]
    mf = dict(mf, **{"class": mclass})
    mat = builder.build_material(mf["maps"], "MF_" + key, mclass, metal=metal or mf.get("metal"),
                                 tint=mf.get("transmission_tint"),
                                 anti_tile=(mf.get("seamless", True) and not mf.get("pattern", False)
                                            and key not in PATTERN_KEYS),
                                 roughness_base=mf.get("roughness_base"))
    misses = [l for l in builder.LOG if "MISS" in l]
    if misses:
        log("material %s: %s" % (key, "; ".join(misses)))
    A._MAT_CACHE[key] = mat
    A._MANIFEST[key] = mf
    return mat


A.matforge = matforge           # apply_materials and white_balance look it up in A


def quiet_emitters(keys=("emissive_warm",)):
    """Self-illuminated materials that glow for the eye only: filament coils,
    spot lenses, a hidden LED strip. VRayLights carry their light; emitting
    into GI from a few mm2 at LED-panel luminance sprayed fireflies over
    benchmark 2's whole preview (brute-force GI only finds such emitters by
    chance). Call after apply_materials."""
    for key in keys:
        mat = A._MAT_CACHE.get(key)
        if mat is None:
            continue
        front = getattr(mat, "frontMtl", None) if rt.isProperty(mat, rt.Name("frontMtl")) else None
        m = front if front is not None else mat
        if kit.setp(m, "selfIllumination_gi", False):
            log("material %s: glow without GI emission" % key)


# ------------------------------------------------------------ geometry
def box(name, x0, x1, y0, y1, z0, z1, key, tile=150.0):
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    n = rt.Box(width=x1 - x0, length=y1 - y0, height=z1 - z0,
               pos=rt.Point3((x0 + x1) / 2.0, (y0 + y1) / 2.0, z0), mapcoords=True)
    n.name = name
    return A.finish(n, key, tile)


def wall(name, axis, c0, c1, a0, a1, top, openings=(), base=-3.0, key="wall_paint"):
    """A wall slab running along `axis` ('x': across y c0..c1, 'y': across x
    c0..c1) from a0 to a1, up to `top`, minus openings [(b0, b1, z0, z1)]
    along it: piers between them, a lintel above each and a breast below.
    It starts below the floor (base) so no sky leaks in along its foot."""
    runs, cur = [], a0
    for b0, b1, z0, z1 in sorted(openings):
        if b0 > cur:
            runs.append((cur, b0, base, top))
        if z0 > base:
            runs.append((b0, b1, base, z0))
        if z1 < top:
            runs.append((b0, b1, z1, top))
        cur = b1
    if a1 > cur:
        runs.append((cur, a1, base, top))
    for k, (a, b, za, zb) in enumerate(runs):
        if axis == "x":
            box("%s_%d" % (name, k), a, b, c0, c1, za, zb, key)
        else:
            box("%s_%d" % (name, k), c0, c1, a, b, za, zb, key)


# ------------------------------------------------------------ placing pieces
PLACED = []      # (label, group dummy, [nodes])


def put(label, fn, x=0.0, y=0.0, z=0.0, rot=0.0, remap=None, scale=1.0, **kw):
    """Build a kit piece, place it and hand its parts to the material pass;
    remap swaps material keys for this piece only ({module key: scene key});
    scale grows it about its own origin (a bigger specimen of a plant)."""
    start = len(kit.PARTS)
    try:
        g = fn(**kw)
        kit.place(g, x, y, z, rot)
        if scale != 1.0:
            g.scale = rt.Point3(scale, scale, scale)
    except Exception:
        log("piece %s failed: %s" % (label, traceback.format_exc().splitlines()[-1]))
        return None
    nodes = []
    for node, key, tile, maptype in kit.PARTS[start:]:
        A.finish(node, (remap or {}).get(key, key), tile or 100.0, maptype)
        nodes.append(node)
    PLACED.append((label, g, nodes))
    return g


def dump_layout(path):
    """World AABB of every placed piece, for a probe run."""
    items = []
    for label, g, nodes in PLACED:
        lo, hi = [1e9] * 3, [-1e9] * 3
        for n in nodes:
            for k, (a, b) in enumerate(zip((n.min.x, n.min.y, n.min.z), (n.max.x, n.max.y, n.max.z))):
                lo[k] = min(lo[k], float(a))
                hi[k] = max(hi[k], float(b))
        items.append({"label": label, "min": [round(v, 1) for v in lo], "max": [round(v, 1) for v in hi],
                      "nodes": len(nodes)})
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"items": items, "log": A.LOG}, fh, indent=1)


# ------------------------------------------------------------ cameras, exposure, render
PROBE = (200, 240)               # probe size: a scene sets it to its frame's aspect


def _quick(cam, tag, key, i):
    p = os.path.join(A.OUT, "_%s_%s_%d_%d.png" % (tag, key, i, int(time.time())))
    rt.render(camera=cam, outputwidth=PROBE[0], outputheight=PROBE[1], outputfile=p, vfb=False, quiet=True)
    return p


A._quick = _quick                # white_balance renders its probes through it


def camera(key, spec):
    """V-Ray physical camera from spec = ((x, y, z), (tx, ty, tz), focal mm):
    36 mm film across the frame's width, f/8, ISO 200, auto vertical tilt."""
    (x, y, z), (tx, ty, tz), f = spec
    cam = rt.VRayPhysicalCamera(pos=rt.Point3(x, y, z), target=rt.Targetobject(pos=rt.Point3(tx, ty, tz)))
    cam.name = "Cam_" + key
    cam.film_width = 36.0
    cam.focal_length = float(f)
    cam.f_number = 8.0
    cam.ISO = 200.0
    cam.shutter_speed = 60.0
    kit.setp(cam, "lens_tilt_auto", True)
    kit.setp(cam, "whiteBalance_preset", 4)
    return cam


def white_balance(cam, key, steps=5, start=(1.0, 1.0, 1.0)):
    """A.white_balance with more feedback steps and a starting guess: a room
    lit through soda-lime glass starts far off (benchmark 1's wall read r/g
    0.71 under D65), and A's three 2/3-power steps stopped short (r/g 1.02
    against 1.06, b/g 0.97 against 0.92 in the render)."""
    box, mkey, (warm_r, warm_b) = A.WB_PATCH[key]
    matforge(mkey)
    alb = A.mean_rgb(A._MANIFEST[mkey]["maps"]["albedo"], rows=32, cols=32)
    want = [warm_r * alb[0] / alb[1], 1.0, warm_b * alb[2] / alb[1]]
    kit.setp(cam, "whiteBalance_preset", 0)            # custom
    wb, done = list(start), 0
    for i in range(steps + 3):
        if done == steps:
            break
        cam.white_balance = rt.Color(*[255.0 * c for c in wb])
        m = A.mean_rgb(_quick(cam, "wb", key, i), box)
        lum = 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]
        if not 0.06 < lum < 0.6:
            cam.shutter_speed = max(0.25, min(4000.0, float(cam.shutter_speed) * max(lum, 1e-4) / 0.2))
            log("white balance %s: patch %.3f, shutter -> 1/%.0f" % (key, lum, float(cam.shutter_speed)))
            continue
        done += 1
        got = [c / max(m[1], 1e-6) for c in m]
        if abs(got[0] - want[0]) < 0.008 and abs(got[2] - want[2]) < 0.008:
            log("white balance %s: wall r/g %.3f b/g %.3f - on target" % (key, got[0], got[2]))
            break
        wb = [w * (g / t) ** 0.67 for w, g, t in zip(wb, got, want)]
        top = max(wb)
        wb = [c / top for c in wb]
        log("white balance %s: wall r/g %.3f b/g %.3f (want %.3f %.3f) -> %s" % (
            key, got[0], got[2], want[0], want[2], [round(c, 3) for c in wb]))
    cam.white_balance = rt.Color(*[255.0 * c for c in wb])


MIN_SHUTTER = 4.0    # 1/s: the slowest shutter the exposure loop uses before raising the ISO
WB_START = {}    # key -> starting white balance (a scene's last converged value)


def expose(cam, key, patch_exposure):
    """Expose the scene's A.WB_PATCH[key] wall patch to patch_exposure (its
    luminance in the saved image, linear), white balance on it there, then
    expose again. Balancing first, on a patch metered at 0.06, missed: V-Ray's
    colour mapping (Reinhard, burn 0.4) pulls bright channels together, so a
    wall balanced to r/g 1.07, b/g 0.91 came out 1.02 / 0.97 at 0.42."""
    r = rt.renderers.production
    keep = (r.progressive_noise_threshold, r.progressive_max_render_time)
    r.progressive_noise_threshold, r.progressive_max_render_time = 0.1, 0.2
    patch = A.WB_PATCH[key][0]

    def meter(tag, n):
        """Up to n probes, until the patch is within 3 % of its aim. Reinhard
        flattens the response toward white (twice the light is far less than
        twice the value), so a plain ratio crept up on a dim room (0.27,
        0.29, ... for an aim of 0.48): the step is the ratio to the power 1.6
        once the patch is past the toe of the curve."""
        for i in range(n):
            r_, g_, b_ = A.mean_rgb(_quick(cam, tag, key, i), patch)
            m = max(0.2126 * r_ + 0.7152 * g_ + 0.0722 * b_, 1e-4)
            if abs(m / patch_exposure - 1.0) < 0.03:
                log("exposure %s: wall %.3f - on target at 1/%.2f s" % (key, m, float(cam.shutter_speed)))
                return
            step = (m / patch_exposure) ** (1.6 if m > 0.15 else 1.0)
            # exposure = ISO / shutter (1/s): the shutter down to 1/4 s, then
            # the ISO, as a photographer on a tripod would. Past ISO 3200 the
            # room is not dim but unlit (a blocked window: the patch then
            # only creeps up on whatever is exposure-compensated, the self-lit
            # backdrop or a lamp's glow), which is a scene fault to fix
            ev = float(cam.ISO) / float(cam.shutter_speed) / step
            if ev <= 200.0 / MIN_SHUTTER:
                cam.ISO, cam.shutter_speed = 200.0, min(4000.0, 200.0 / ev)
            else:
                cam.shutter_speed, cam.ISO = MIN_SHUTTER, min(3200.0, ev * MIN_SHUTTER)
                if ev * MIN_SHUTTER > 3200.0:
                    log("exposure %s: the scene is all but unlit (ISO past 3200): check its windows and lights" % key)
            log("exposure %s: wall %.3f -> 1/%.1f s, ISO %.0f" % (key, m, float(cam.shutter_speed), float(cam.ISO)))

    kit.setp(cam, "whiteBalance_preset", 0)
    start = WB_START.get(key, (1.0, 1.0, 1.0))
    cam.white_balance = rt.Color(*[255.0 * c for c in start])
    meter("pre", 5)
    white_balance(cam, key, start=start)
    meter("exp", 4)
    r.progressive_noise_threshold, r.progressive_max_render_time = keep


def diag_probes(cam, key, variants, minutes=0.25):
    """MF_BENCH_DIAG: one quick probe per (name, toggle) with toggle(False)
    applied (None: the scene as it is), then undone with toggle(True); each
    logs the WB patch's luminance. To find what lights, darkens or speckles
    a scene by switching one suspect off at a time."""
    r = rt.renderers.production
    keep = (r.progressive_noise_threshold, r.progressive_max_render_time)
    r.progressive_noise_threshold, r.progressive_max_render_time = 0.05, minutes
    for name, toggle in variants:
        if toggle:
            toggle(False)
        p = _quick(cam, "diag_" + name, key, 0)
        rgb = A.mean_rgb(p, A.WB_PATCH[key][0])
        log("diag %s: patch %.3f" % (name, 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]))
        if toggle:
            toggle(True)
    r.progressive_noise_threshold, r.progressive_max_render_time = keep


def show_nodes(pred):
    """toggle(on) for diag_probes: the nodes pred(node) picks, renderable or not."""
    def toggle(on):
        for n in rt.objects:
            if pred(n):
                n.renderable = on
    return toggle


def render_views(cams, size, patch_exposure, before=None):
    """Expose and render every camera in MF_APT_CAMS (default: all in cams)
    to A.OUT/<key>.png. before(key, cam), if given, runs after exposure (a
    scene switching lamps for one view)."""
    keys = [k for k in os.environ.get("MF_APT_CAMS", "").split(",") if k] or list(cams)
    w, h = size
    for key in keys:
        try:
            bd = rt.getNodeByName("Backdrop")
            if bd is not None and bd.material is not None:
                bd.material.multiplier = 5.0   # the metering baseline
            cam = camera(key, cams[key])
            expose(cam, key, patch_exposure)
            A.set_backdrop(cam)
            if before:
                before(key, cam)
            log("render %s started" % key)
            t1 = time.time()
            out = os.path.join(A.OUT, "%s.png" % key)
            rt.render(camera=cam, outputwidth=w, outputheight=h, outputfile=out, vfb=False, quiet=True)
            log("render %s %.0fs -> %s" % (key, time.time() - t1, out))
        except Exception:
            log("render %s failed: %s" % (key, traceback.format_exc()))


def start():
    """Fresh scene in centimetres with the apartment's V-Ray settings."""
    rt.resetMaxFile(rt.Name("noPrompt"))
    rt.units.SystemType = rt.Name("centimeters")
    rt.units.DisplayType = rt.Name("metric")
    rt.units.MetricType = rt.Name("centimeters")
    A.setup_renderer()
    kit.PARTS.clear()
    del PLACED[:]


def save_if_asked():
    save = os.environ.get("MF_APT_SAVE")
    if save:
        rt.saveMaxFile(save, quiet=True)
        log("saved " + save)


def run(main):
    """Run a scene's main(), always leaving a final log (fatal or not)."""
    t0 = time.time()
    try:
        main()
        with open(os.path.join(A.OUT, "_apartment_log.json"), "w", encoding="utf-8") as fh:
            json.dump({"log": A.LOG, "seconds": round(time.time() - t0)}, fh, indent=1)
    except Exception:
        A.LOG.append(traceback.format_exc())
        with open(os.path.join(A.OUT, "_apartment_log.json"), "w", encoding="utf-8") as fh:
            json.dump({"fatal": traceback.format_exc(), "log": A.LOG}, fh, indent=1)
