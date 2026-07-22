"""Headless render check #2 — each box uses REAL (CC0 Poly Haven) reference
textures run through MatForge, so wood looks like wood, marble like marble.
Run via 3dsmaxbatch. Writes render_check2.png.
"""
import os
import sys
import traceback

_REPO = r"C:\Users\aasis\matforge"
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

RESULT = os.path.join(_REPO, "render_check2_result.txt")
OUT_IMG = os.path.join(_REPO, "render_check2.png")
SM = os.path.join(_REPO, "sample_maps")
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
    return {k: os.path.join(d, k + ".png")
            for k in ("albedo", "roughness", "normal", "height", "ao")}


try:
    import importlib

    from maxplugin import builder
    importlib.reload(builder)
    from pymxs import runtime as rt

    out("MatForge RENDER CHECK #2 — real CC0 references")
    rt.resetMaxFile(rt.Name("noPrompt"))

    vray_cls = None
    for c in rt.RendererClass.classes:
        n = str(c)
        if "V_Ray" in n and "GPU" not in n and "RT" not in n:
            vray_cls = c
            break
    rt.renderers.production = vray_cls()
    out("renderer: %s" % str(rt.classOf(rt.renderers.production)))

    # lighting: dome (IBL fill + reflections) + key — toned down for a
    # balanced exposure (last pass was blown out)
    rt.environmentColor = rt.color(200, 206, 216)
    try:
        dome = rt.VRayLight()
        dome.type = 1
        dome.multiplier = 1.15
        dome.color = rt.color(255, 255, 255)
    except Exception as e:
        out("dome failed: %s" % e)
    key = rt.Omnilight(pos=rt.Point3(400, -350, 650))
    key.multiplier = 1.6
    try:
        key.castShadows = True
    except Exception:
        pass
    fill = rt.Omnilight(pos=rt.Point3(-400, -200, 350))
    fill.multiplier = 0.6

    # ground = the fal-generated light-oak wood, as an interior floor
    ground = rt.Plane(width=1600, length=1600, pos=rt.Point3(0, 0, 0))
    ground.name = "Ground_Wood"
    ground.material = builder.build_material(maps_from("Fal_Wood_maps"),
                                             "Floor_Wood", "wood_interior")

    # each box: its own real reference + matching class
    specs = [
        (-180, "wood_interior", "Fal_Wood_maps", "Box_FalWood"),
        (-60, "metal_brushed", "Real_Metal_maps", "Box_Metal"),
        (60, "marble", "Real_Marble_maps", "Box_Marble"),
        (180, "glass_clear", "Fal_Wood_maps", "Box_Glass"),
    ]
    for x, mclass, folder, name in specs:
        b = rt.Box(width=100, length=100, height=100, pos=rt.Point3(x, 0, 0))
        b.name = name
        b.material = builder.build_material(maps_from(folder), name, mclass)
    out("built: marble floor + %d boxes (%s)"
        % (len(specs), ", ".join(s[1] for s in specs)))

    tgt = rt.targetObject(pos=rt.Point3(0, 0, 55))
    cam = rt.targetCamera(pos=rt.Point3(0, -640, 250), target=tgt)
    try:
        cam.fov = 55.0
    except Exception:
        pass

    out("rendering 900x560 with V-Ray...")
    rt.render(camera=cam, outputwidth=900, outputheight=560,
              outputfile=OUT_IMG, vfb=False, quiet=True)
    ok = os.path.isfile(OUT_IMG) and os.path.getsize(OUT_IMG) > 2000
    out("RENDER_OK" if ok else "RENDER_FAIL")
except Exception:
    out("RENDER_FAIL — exception:")
    out(traceback.format_exc())
finally:
    _flush()
