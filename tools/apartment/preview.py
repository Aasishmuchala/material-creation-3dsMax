"""Furniture preview harness (3dsmaxbatch). Renders one furniture module.

  MF_PREVIEW_MODULE  module name in tools/apartment (e.g. furn_living)
  MF_PREVIEW_OUT     output PNG path
  MF_PREVIEW_VIEW    optional "front" | "three_quarter" (default) | "top"
Each module exposes preview(), which builds and places its pieces side by side.
Materials are flat stand-ins per kit.MAT_KEYS so form and proportion read.
"""
import importlib
import json
import os
import sys
import traceback

from pymxs import runtime as rt

HERE = r"C:\Users\aasis\matforge\tools\apartment"
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import kit  # noqa: E402

importlib.reload(kit)

STAND_IN = {
    "upholstery": (0.62, 0.58, 0.52, 0.85), "upholstery_alt": (0.82, 0.79, 0.73, 0.9),
    "velvet": (0.08, 0.22, 0.16, 0.85), "leather": (0.42, 0.20, 0.09, 0.55),
    "cushion": (0.50, 0.34, 0.25, 0.85), "wood_dark": (0.16, 0.09, 0.05, 0.45),
    "wood_light": (0.55, 0.40, 0.26, 0.45), "metal_brass": (0.88, 0.75, 0.42, 0.25),
    "metal_black": (0.03, 0.03, 0.03, 0.45), "metal_steel": (0.62, 0.62, 0.62, 0.25),
    "metal_chrome": (0.80, 0.80, 0.80, 0.03), "glass": (0.9, 0.9, 0.9, 0.0),
    "glass_frosted": (0.9, 0.9, 0.9, 0.5), "ceramic_white": (0.85, 0.85, 0.83, 0.05),
    "stone_worktop": (0.86, 0.85, 0.83, 0.1), "stone_dark": (0.03, 0.03, 0.03, 0.08),
    "paint_white": (0.82, 0.81, 0.78, 0.35), "paint_sage": (0.42, 0.50, 0.42, 0.35),
    "bedding": (0.86, 0.86, 0.84, 0.9), "linen": (0.72, 0.68, 0.60, 0.9),
    "rug": (0.65, 0.60, 0.52, 0.95), "plant_leaf": (0.07, 0.25, 0.06, 0.4),
    "plant_pot": (0.55, 0.27, 0.15, 0.7), "plastic_black": (0.02, 0.02, 0.02, 0.3),
    "stem": (0.12, 0.28, 0.08, 0.5),
    "screen": (0.01, 0.01, 0.01, 0.02), "rubber": (0.02, 0.02, 0.02, 0.8),
    "paper": (0.75, 0.70, 0.60, 0.7), "wax": (0.88, 0.84, 0.74, 0.4),
    "emissive_warm": (1.0, 0.8, 0.55, 0.5), "mirror": (0.9, 0.9, 0.9, 0.0),
    "soil": (0.10, 0.07, 0.05, 0.95),
}


def mtl(key):
    r, g, b, rough = STAND_IN[key]
    m = rt.VRayMtl()
    m.name = "prev_" + key
    m.brdf_useRoughness = True
    m.diffuse = rt.Color(r * 255, g * 255, b * 255)
    m.reflection = rt.Color(255, 255, 255)
    m.reflection_glossiness = rough
    if key.startswith("metal") or key == "mirror":
        m.reflection_metalness = 1.0
    if key in ("glass", "glass_frosted"):
        m.refraction = rt.Color(255, 255, 255)
        m.refraction_ior = 1.52
        m.refraction_glossiness = 1.0 if key == "glass" else 0.5
        m.diffuse = rt.Color(0, 0, 0)
    if key == "emissive_warm":
        m.selfIllumination = rt.Color(255, 205, 140)
        m.compensate_camera_exposure = True
        m.selfIllumination_multiplier = 2.0
    return m


def main():
    out = os.environ.get("MF_PREVIEW_OUT", os.path.join(HERE, "preview.png"))
    modname = os.environ["MF_PREVIEW_MODULE"]
    view = os.environ.get("MF_PREVIEW_VIEW", "three_quarter")
    rt.resetMaxFile(rt.Name("noPrompt"))
    rt.units.SystemType = rt.Name("centimeters")
    vray = [c for c in rt.RendererClass.classes if "V_Ray" in str(c) and "GPU" not in str(c)][0]
    r = vray()
    rt.renderers.production = r
    r.imageSampler_type = 3
    r.progressive_max_render_time = 0.6
    r.progressive_noise_threshold = 0.03
    kit.PARTS.clear()
    mod = importlib.import_module(modname)
    importlib.reload(mod)
    mod.preview()
    mats = {}
    for node, key, tile, maptype in kit.PARTS:
        if key not in mats:
            mats[key] = mtl(key)
        node.material = mats[key]
    # bounding box of everything built
    lo = [1e9] * 3
    hi = [-1e9] * 3
    for node, *_ in kit.PARTS:
        bb = rt.nodeGetBoundingBox(node, rt.matrix3(1))
        for i, v in enumerate((bb[0].x, bb[0].y, bb[0].z)):
            lo[i] = min(lo[i], v)
        for i, v in enumerate((bb[1].x, bb[1].y, bb[1].z)):
            hi[i] = max(hi[i], v)
    cx, cy, cz = [(a + b) / 2 for a, b in zip(lo, hi)]
    span = max(hi[0] - lo[0], hi[1] - lo[1], (hi[2] - lo[2]) * 1.6, 60.0)
    floor = rt.Plane(width=span * 8, length=span * 8, pos=rt.Point3(cx, cy, 0))
    fm = rt.VRayMtl()
    fm.diffuse = rt.Color(150, 146, 140)
    fm.brdf_useRoughness = True
    fm.reflection = rt.Color(255, 255, 255)
    fm.reflection_glossiness = 0.6
    floor.material = fm
    wall = rt.Box(width=span * 8, length=5, height=span * 3, pos=rt.Point3(cx, hi[1] + span * 0.6, 0))
    wall.material = fm
    sun = rt.VRaySun(pos=rt.Point3(cx - span * 3, cy - span * 4, span * 4),
                     target=rt.Targetobject(pos=rt.Point3(cx, cy, 0)))
    dome = rt.VRayLight()
    dome.type = 1
    dome.texmap = rt.VRaySky()
    dome.multiplier = 1.0
    dome.invisible = True
    rt.environmentMap = rt.VRaySky()
    if view == "front":
        cpos = (cx, cy - span * 1.9, cz + span * 0.15)
    elif view == "top":
        cpos = (cx, cy - span * 0.6, cz + span * 2.2)
    else:
        cpos = (cx + span * 1.15, cy - span * 1.55, cz + span * 0.75)
    cam = rt.VRayPhysicalCamera(pos=rt.Point3(*cpos), target=rt.Targetobject(pos=rt.Point3(cx, cy, cz * 0.8)))
    cam.focal_length = 40
    cam.f_number = 8
    cam.ISO = 100
    cam.shutter_speed = 250
    rt.render(camera=cam, outputwidth=1280, outputheight=720, outputfile=out, vfb=False, quiet=True)
    with open(out + ".json", "w") as fh:
        json.dump({"parts": len(kit.PARTS), "bbox": [lo, hi],
                   "materials": sorted(set(k for _, k, _, _ in kit.PARTS))}, fh)


try:
    main()
except Exception:
    with open(os.environ.get("MF_PREVIEW_OUT", os.path.join(HERE, "preview.png")) + ".error.txt", "w") as fh:
        fh.write(traceback.format_exc())
