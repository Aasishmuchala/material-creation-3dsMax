"""Swatch test -- prove the PLUGIN'S DEFAULT output (no hand-tuning).
Builds 3 materials with builder.build_material() exactly as the Create button
does, puts each on a sphere under a neutral studio HDR + soft box (so gloss/shine
reads), and renders render_swatch.png. Row L->R: wood, marble, painted-metal.
Run via 3dsmaxbatch.
"""
import os
import sys
import traceback

_REPO = r"C:\Users\aasis\matforge"
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

RESULT = os.path.join(_REPO, "render_swatch_result.txt")
OUT_IMG = os.path.join(_REPO, "render_swatch.png")
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
    keys = ("albedo", "roughness", "normal", "height", "ao", "metalness")
    return {k: os.path.join(d, k + ".png")
            for k in keys if os.path.isfile(os.path.join(d, k + ".png"))}


try:
    import importlib
    from maxplugin import builder
    importlib.reload(builder)
    from pymxs import runtime as rt

    out("MatForge SWATCH test (default wiring)")
    rt.resetMaxFile(rt.Name("noPrompt"))

    vray_cls = None
    for c in rt.RendererClass.classes:
        n = str(c)
        if "V_Ray" in n and "GPU" not in n and "RT" not in n:
            vray_cls = c
            break
    rt.renderers.production = vray_cls()
    out("renderer: %s" % str(rt.classOf(rt.renderers.production)))

    # HDRI dome (neutral fill + something for reflections to pick up)
    hdr = rt.VRayBitmap() if hasattr(rt, "VRayBitmap") else rt.Bitmaptexture()
    for p in ("HDRIMapName", "fileName", "filename"):
        if rt.isProperty(hdr, rt.Name(p)):
            setattr(hdr, p, HDRI)
            break
    dome = rt.VRayLight()
    dome.type = 1
    dome.multiplier = 1.4
    for p in ("texmap", "domeTexmap"):
        if rt.isProperty(dome, rt.Name(p)):
            setattr(dome, p, hdr)
            break
    for p in ("texmap_on", "useDomeTex"):
        if rt.isProperty(dome, rt.Name(p)):
            setattr(dome, p, True)
            break

    # Omni key+fill carry the DIFFUSE lighting/form/exposure, but with their
    # SPECULAR disabled -- a point light's specular is a fake pinpoint hotspot
    # that makes any glossy surface look plastic. The area soft box below
    # supplies the real, soft specular sheen.
    key = rt.Omnilight(pos=rt.Point3(260, -260, 300))
    key.multiplier = 2.0
    try:
        key.affectSpecular = False
        key.castShadows = True
        key.shadowGenerator = rt.VRayShadow()
    except Exception as e:
        out("key setup: %s" % e)
    fill = rt.Omnilight(pos=rt.Point3(-280, -300, 200))
    fill.multiplier = 0.4
    try:
        fill.affectSpecular = False
    except Exception:
        pass

    # AREA soft box overhead-front -> broad soft highlight (the honest "shine")
    try:
        soft = rt.VRayLight()
        soft.type = 0
        for p, v in [("u_size", 900.0), ("v_size", 450.0),
                     ("size0", 900.0), ("size1", 450.0)]:
            if rt.isProperty(soft, rt.Name(p)):
                setattr(soft, p, v)
        soft.multiplier = 3.0
        soft.pos = rt.Point3(0, -120, 520)
        rt.rotate(soft, rt.angleaxis(180, rt.Point3(1, 0, 0)))
    except Exception as e:
        out("soft box: %s" % e)

    # neutral mid-grey matte ground (doesn't tint the swatches)
    ground = rt.Plane(width=3000, length=3000, pos=rt.Point3(0, 0, 0))
    ground.name = "Ground"
    gm = rt.VRayMtl()
    gm.diffuse = rt.Color(122, 122, 122)
    for p, v in [("brdf_useRoughness", True), ("reflection_glossiness", 0.75)]:
        if rt.isProperty(gm, rt.Name(p)):
            setattr(gm, p, v)
    try:
        gm.reflection = rt.Color(20, 20, 20)
    except Exception:
        pass
    ground.material = gm

    # THE TEST: three plugin-default materials, correct class per reference
    specs = [
        (-150, "Real_Wood_maps",   "wood_interior",  "Wood"),
        (0,    "Real_Marble_maps", "marble",         "Marble"),
        (150,  "Real_Metal_maps",  "metal_painted",  "PaintedMetal"),
    ]
    R = 55
    for x, folder, mclass, name in specs:
        mp = maps_from(folder)
        if not mp.get("albedo"):
            out("MISSING maps: %s" % folder)
            continue
        s = rt.Sphere(radius=R, segs=64, pos=rt.Point3(x, 0, R))
        s.name = name
        try:
            s.mapcoords = True
        except Exception:
            pass
        s.material = builder.build_material(mp, name, mclass)
        out("built %-14s class=%s maps=%s" % (name, mclass, sorted(mp.keys())))

    # camera framing the row
    focus = rt.Point3(0, 0, R)
    cam = rt.targetCamera(pos=rt.Point3(0, -560, 150),
                          target=rt.targetObject(pos=focus))
    try:
        cam.fov = 46.0
    except Exception:
        pass

    out("rendering 1500x560...")
    rt.render(camera=cam, outputwidth=1500, outputheight=560,
              outputfile=OUT_IMG, vfb=False, quiet=True)
    ok = os.path.isfile(OUT_IMG) and os.path.getsize(OUT_IMG) > 5000
    out("RENDER_OK" if ok else "RENDER_FAIL")
except Exception:
    out("RENDER_FAIL -- exception:")
    out(traceback.format_exc())
finally:
    _flush()
