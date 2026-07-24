"""Swatch 2 -- verify the PHYSICS of the NEW material classes. Each sphere uses
the same neutral albedo (+normal) with NO roughness map, so the recipe's
base_roughness governs the gloss purely -> you see each class's intended
behavior: mirror chrome, glossy ceramic, matte rubber, velvet sheen, frosted vs
clear refraction, metallic car paint, self-lit emissive. Run via 3dsmaxbatch.
Row L->R: chrome, ceramic, car_paint, glass_frosted, gemstone, rubber, velvet, emissive.
"""
import os
import sys
import traceback

_REPO = r"C:\Users\aasis\matforge"
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

RESULT = os.path.join(_REPO, "render_swatch2_result.txt")
OUT_IMG = os.path.join(_REPO, "render_swatch2.png")
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


try:
    import importlib
    from maxplugin import builder
    importlib.reload(builder)
    from pymxs import runtime as rt

    out("MatForge SWATCH2 -- new-class physics")
    rt.resetMaxFile(rt.Name("noPrompt"))

    vray_cls = None
    for c in rt.RendererClass.classes:
        n = str(c)
        if "V_Ray" in n and "GPU" not in n and "RT" not in n:
            vray_cls = c
            break
    rt.renderers.production = vray_cls()

    hdr = rt.VRayBitmap() if hasattr(rt, "VRayBitmap") else rt.Bitmaptexture()
    for p in ("HDRIMapName", "fileName", "filename"):
        if rt.isProperty(hdr, rt.Name(p)):
            setattr(hdr, p, HDRI)
            break
    dome = rt.VRayLight(); dome.type = 1; dome.multiplier = 1.5
    for p in ("texmap", "domeTexmap"):
        if rt.isProperty(dome, rt.Name(p)):
            setattr(dome, p, hdr); break
    for p in ("texmap_on", "useDomeTex"):
        if rt.isProperty(dome, rt.Name(p)):
            setattr(dome, p, True); break

    key = rt.Omnilight(pos=rt.Point3(300, -300, 350)); key.multiplier = 2.0
    try:
        key.affectSpecular = False
        key.castShadows = True
        key.shadowGenerator = rt.VRayShadow()
    except Exception:
        pass
    fill = rt.Omnilight(pos=rt.Point3(-320, -340, 220)); fill.multiplier = 0.4
    try:
        fill.affectSpecular = False
    except Exception:
        pass
    try:
        soft = rt.VRayLight(); soft.type = 0
        for p, v in [("u_size", 1600.0), ("v_size", 500.0),
                     ("size0", 1600.0), ("size1", 500.0)]:
            if rt.isProperty(soft, rt.Name(p)):
                setattr(soft, p, v)
        soft.multiplier = 3.0; soft.pos = rt.Point3(0, -120, 560)
        rt.rotate(soft, rt.angleaxis(180, rt.Point3(1, 0, 0)))
    except Exception:
        pass

    ground = rt.Plane(width=4000, length=4000, pos=rt.Point3(0, 0, 0))
    gm = rt.VRayMtl(); gm.diffuse = rt.Color(128, 128, 128)
    for p, v in [("brdf_useRoughness", True), ("reflection_glossiness", 0.7)]:
        if rt.isProperty(gm, rt.Name(p)):
            setattr(gm, p, v)
    try:
        gm.reflection = rt.Color(18, 18, 18)
    except Exception:
        pass
    ground.material = gm

    # neutral albedo + normal only (NO roughness map -> base_roughness rules)
    src = os.path.join(SM, "Real_Marble_maps")
    base_maps = {"albedo": os.path.join(src, "albedo.png"),
                 "normal": os.path.join(src, "normal.png")}

    classes = ["metal_chrome", "ceramic_glazed", "car_paint", "glass_frosted",
               "gemstone", "rubber", "velvet", "emissive"]
    R = 50
    span = 150
    x0 = -(len(classes) - 1) * span / 2.0
    for i, mclass in enumerate(classes):
        s = rt.Sphere(radius=R, segs=64, pos=rt.Point3(x0 + i * span, 0, R))
        s.name = mclass
        try:
            s.mapcoords = True
        except Exception:
            pass
        s.material = builder.build_material(dict(base_maps), mclass, mclass)
        out("built %s" % mclass)

    focus = rt.Point3(0, 0, R)
    cam = rt.targetCamera(pos=rt.Point3(0, -1050, 240),
                          target=rt.targetObject(pos=focus))
    try:
        cam.fov = 52.0
    except Exception:
        pass

    out("rendering 2200x360...")
    rt.render(camera=cam, outputwidth=2200, outputheight=360,
              outputfile=OUT_IMG, vfb=False, quiet=True)
    ok = os.path.isfile(OUT_IMG) and os.path.getsize(OUT_IMG) > 5000
    out("RENDER_OK" if ok else "RENDER_FAIL")
except Exception:
    out("RENDER_FAIL -- exception:")
    out(traceback.format_exc())
finally:
    _flush()
