"""Top-quality headless render — PATINA materials under real HDRI lighting.
Run via 3dsmaxbatch. Writes render_hq.png.
"""
import os
import sys
import traceback

_REPO = r"C:\Users\aasis\matforge"
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

RESULT = os.path.join(_REPO, "render_hq_result.txt")
OUT_IMG = os.path.join(_REPO, "render_hq.png")
SM = os.path.join(_REPO, "sample_maps")
HDRI = os.path.join(SM, "studio_neutral.hdr")
_lines = []


def out(s):
    _lines.append(str(s))
    try:
        print(s)
    except Exception:
        pass


def _flush():
    try:
        with open(RESULT, "w", encoding="utf-8") as f:
            f.write("\n".join(_lines) + "\n")
    except Exception:
        pass


def maps_from(folder):
    d = os.path.join(SM, folder)
    keys = ("albedo", "roughness", "normal", "height", "ao", "metalness",
            "opacity")
    return {k: os.path.join(d, k + ".png")
            for k in keys if os.path.isfile(os.path.join(d, k + ".png"))}


try:
    import importlib

    from maxplugin import builder
    importlib.reload(builder)
    from pymxs import runtime as rt

    out("MatForge RENDER HQ — PATINA materials + HDRI")
    rt.resetMaxFile(rt.Name("noPrompt"))

    vray_cls = None
    for c in rt.RendererClass.classes:
        n = str(c)
        if "V_Ray" in n and "GPU" not in n and "RT" not in n:
            vray_cls = c
            break
    rt.renderers.production = vray_cls()
    out("renderer: %s" % str(rt.classOf(rt.renderers.production)))

    # --- HDRI dome light = image-based lighting + reflections + background ---
    hdr = rt.VRayBitmap() if hasattr(rt, "VRayBitmap") else rt.Bitmaptexture()
    for p in ("HDRIMapName", "fileName", "filename"):
        if rt.isProperty(hdr, rt.Name(p)):
            setattr(hdr, p, HDRI)
            break
    dome = rt.VRayLight()
    dome.type = 1                     # 1 = Dome
    dome.multiplier = 1.3
    for p in ("texmap", "domeTexmap"):
        if rt.isProperty(dome, rt.Name(p)):
            setattr(dome, p, hdr)
            break
    for p in ("texmap_on", "useDomeTex"):
        if rt.isProperty(dome, rt.Name(p)):
            setattr(dome, p, True)
            break
    # soft neutral front fill so the camera-facing faces aren't in shadow
    fill = rt.Omnilight(pos=rt.Point3(0, -520, 360))
    fill.multiplier = 0.55
    fill2 = rt.Omnilight(pos=rt.Point3(320, -300, 300))
    fill2.multiplier = 0.4
    out("HDRI dome: %s (hdr exists: %s)"
        % (str(rt.classOf(dome)), os.path.isfile(HDRI)))

    # --- geometry: wood floor + 4 boxes, each a PATINA material ---
    ground = rt.Plane(width=2000, length=2000, pos=rt.Point3(0, 0, 0))
    ground.name = "Floor"
    ground.material = builder.build_material(maps_from("Patina_Wood_maps"),
                                             "HQ_Floor", "wood_interior")

    specs = [
        (-180, "wood_interior", "Patina_Wood_maps", "HQ_Wood"),
        (-60, "metal_brushed", "Patina_Metal_maps", "HQ_Metal"),
        (60, "marble", "Patina_Marble_maps", "HQ_Marble"),
        (180, "glass_clear", "Patina_Wood_maps", "HQ_Glass"),
    ]
    misses = []
    for x, mclass, folder, name in specs:
        b = rt.Box(width=100, length=100, height=100, pos=rt.Point3(x, 0, 0))
        b.name = name
        b.material = builder.build_material(maps_from(folder), name, mclass)
        misses += [name + ": " + l for l in builder.LOG if "MISS" in l]
    out("built floor + %d PATINA boxes" % len(specs))
    if misses:
        out("PROPERTY MISSES:")
        for m in misses:
            out("  " + m)

    # --- camera ---
    tgt = rt.targetObject(pos=rt.Point3(0, 0, 55))
    cam = rt.targetCamera(pos=rt.Point3(0, -620, 230), target=tgt)
    try:
        cam.fov = 52.0
    except Exception:
        pass

    out("rendering 1600x1000 with V-Ray + HDRI...")
    rt.render(camera=cam, outputwidth=1600, outputheight=1000,
              outputfile=OUT_IMG, vfb=False, quiet=True)
    ok = os.path.isfile(OUT_IMG) and os.path.getsize(OUT_IMG) > 5000
    out("RENDER_OK" if ok else "RENDER_FAIL")
except Exception:
    out("RENDER_FAIL — exception:")
    out(traceback.format_exc())
finally:
    _flush()
