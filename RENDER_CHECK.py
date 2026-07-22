"""Headless render check — build MatForge materials, apply them to real
geometry, light it, render with V-Ray, save a PNG to look at.

Run via 3dsmaxbatch (no GUI). Every stage is wrapped + logged to
render_check_result.txt so a failure is diagnosable, and whatever renders is
saved to render_check.png.
"""
import os
import sys
import traceback

_REPO = r"C:\Users\aasis\matforge"
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

RESULT = os.path.join(_REPO, "render_check_result.txt")
OUT_IMG = os.path.join(_REPO, "render_check.png")
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


try:
    import importlib

    from maxplugin import builder
    importlib.reload(builder)
    from pymxs import runtime as rt

    SAMPLE = os.path.join(_REPO, "sample_maps", "Sample_Wood_maps")
    MAPS = {k: os.path.join(SAMPLE, k + ".png")
            for k in ("albedo", "roughness", "normal", "height", "ao")}

    out("MatForge RENDER CHECK")
    out("V-Ray present: %s" % hasattr(rt, "VRayMtl"))

    # --- reset to an empty scene ---
    rt.resetMaxFile(rt.Name("noPrompt"))

    # --- set V-Ray as the production renderer (CPU, not GPU) ---
    vray_cls = None
    for c in rt.RendererClass.classes:
        n = str(c)
        if "V_Ray" in n and "GPU" not in n and "RT" not in n:
            vray_cls = c
            break
    if vray_cls is None:
        out("SMOKE_FAIL: no V-Ray production renderer class found")
        raise SystemExit
    rt.renderers.production = vray_cls()
    out("renderer: %s" % str(rt.classOf(rt.renderers.production)))

    # --- lighting: a bright V-Ray dome for even IBL-style fill (also what
    # metals/glass reflect) + a strong key omni for a highlight & shadows ---
    rt.environmentColor = rt.color(240, 244, 250)  # bright background
    try:
        dome = rt.VRayLight()
        dome.type = 1                     # 1 = Dome
        dome.multiplier = 2.0
        dome.color = rt.color(255, 255, 255)
        out("dome light: %s" % str(rt.classOf(dome)))
    except Exception as e:
        out("dome light failed (%s) — falling back to omni fill" % e)
        f = rt.Omnilight(pos=rt.Point3(0, 0, 700))
        f.multiplier = 1.5
    key = rt.Omnilight(pos=rt.Point3(400, -350, 650))
    key.multiplier = 2.4
    try:
        key.castShadows = True
    except Exception:
        pass
    fill = rt.Omnilight(pos=rt.Point3(-400, -200, 350))
    fill.multiplier = 0.9

    # --- geometry: ground plane + a row of boxes ---
    ground = rt.Plane(width=1600, length=1600, pos=rt.Point3(0, 0, 0))
    ground.name = "Ground"
    ground.material = builder.build_material(MAPS, "MF_Concrete", "concrete")

    specs = [
        (-180, "wood_exterior", "MF_Wood"),
        (-60, "metal_brushed", "MF_Metal"),
        (60, "marble", "MF_Marble"),
        (180, "glass_clear", "MF_Glass"),
    ]
    boxes = []
    for x, mclass, name in specs:
        b = rt.Box(width=100, length=100, height=100,
                   pos=rt.Point3(x, 0, 0))
        b.name = name
        b.material = builder.build_material(MAPS, name, mclass)
        boxes.append(b)
    out("geometry: 1 ground + %d boxes (%s)"
        % (len(boxes), ", ".join(s[1] for s in specs)))

    # --- camera framing the row (explicit target object) ---
    tgt = rt.targetObject(pos=rt.Point3(0, 0, 55))
    cam = rt.targetCamera(pos=rt.Point3(0, -640, 250), target=tgt)
    try:
        cam.fov = 55.0
    except Exception:
        pass

    # --- render ---
    out("rendering 900x560 with V-Ray (headless)...")
    rt.render(camera=cam, outputwidth=900, outputheight=560,
              outputfile=OUT_IMG, vfb=False, quiet=True)
    ok = os.path.isfile(OUT_IMG) and os.path.getsize(OUT_IMG) > 2000
    out("render saved: %s (%s bytes)"
        % (ok, os.path.getsize(OUT_IMG) if os.path.isfile(OUT_IMG) else 0))
    out("RENDER_OK" if ok else "RENDER_FAIL: no output image")
except SystemExit:
    pass
except Exception:
    out("RENDER_FAIL — unhandled exception:")
    out(traceback.format_exc())
finally:
    _flush()
