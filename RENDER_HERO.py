"""Hero render — PATINA materials shown properly: wood as a large floor
(grazing light reveals grain), marble/metal/glass as spheres (curvature +
reflection/refraction, no sharp-cube tell), strong key for form, and depth of
field for a photographic look. Run via 3dsmaxbatch. Writes render_hero.png.
"""
import os
import sys
import traceback

_REPO = r"C:\Users\aasis\matforge"
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

RESULT = os.path.join(_REPO, "render_hero_result.txt")
OUT_IMG = os.path.join(_REPO, "render_hero.png")
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

    out("MatForge HERO render")
    rt.resetMaxFile(rt.Name("noPrompt"))

    vray_cls = None
    for c in rt.RendererClass.classes:
        n = str(c)
        if "V_Ray" in n and "GPU" not in n and "RT" not in n:
            vray_cls = c
            break
    rt.renderers.production = vray_cls()
    out("renderer: %s" % str(rt.classOf(rt.renderers.production)))

    # --- HDRI dome (fill + the environment metal/glass reflect & refract) ---
    hdr = rt.VRayBitmap() if hasattr(rt, "VRayBitmap") else rt.Bitmaptexture()
    for p in ("HDRIMapName", "fileName", "filename"):
        if rt.isProperty(hdr, rt.Name(p)):
            setattr(hdr, p, HDRI)
            break
    dome = rt.VRayLight()
    dome.type = 1
    dome.multiplier = 1.5
    for p in ("texmap", "domeTexmap"):
        if rt.isProperty(dome, rt.Name(p)):
            setattr(dome, p, hdr)
            break
    for p in ("texmap_on", "useDomeTex"):
        if rt.isProperty(dome, rt.Name(p)):
            setattr(dome, p, True)
            break

    # --- strong grazing key (form + shadows) + soft front fill ---
    key = rt.Omnilight(pos=rt.Point3(320, -260, 210))
    key.multiplier = 2.6
    try:
        key.castShadows = True
        key.shadowGenerator = rt.VRayShadow()
    except Exception as e:
        out("key shadow setup: %s" % e)
    fill = rt.Omnilight(pos=rt.Point3(-260, -360, 260))
    fill.multiplier = 0.5

    # --- wood floor (its best form: big surface, grazing light shows grain) ---
    ground = rt.Plane(width=2400, length=2400, pos=rt.Point3(0, 0, 0),
                      widthsegs=1, lengthsegs=1)
    ground.name = "WoodFloor"
    wood_maps = maps_from("Patina_Wood_maps")
    fmat = builder.build_material(wood_maps, "Hero_Wood", "wood_interior")

    # --- lookdev: make it a lacquered, richly-coloured oak floor ---
    # 1) COLOUR CORRECTION on the albedo: warmer + more saturated
    try:
        cc = rt.Color_Correction()
        cc.map = fmat.texmap_diffuse
        for p, v in [("saturation", 28.0), ("gammaRGB", 1.12),
                     ("hueShift", 4.0)]:
            if rt.isProperty(cc, rt.Name(p)):
                setattr(cc, p, v)
        fmat.texmap_diffuse = cc
    except Exception as e:
        out("colour-correction skipped: %s" % e)
    # 2) SHINE: glossy clear lacquer — disable the matte roughness map, set a
    #    glossy base reflection, and a bright clear coat on top
    # SHINE (fixed): the builder set brdf_useRoughness=ON, so
    # reflection_glossiness is a ROUGHNESS value (0 = mirror, 1 = matte).
    # Remove PATINA's matte roughness MAP (it was overriding the scalar and
    # keeping the floor flat) and set a low roughness for a polished lacquer.
    try:
        setattr(fmat, "texmap_reflectionGlossiness", None)
    except Exception as e:
        out("clear roughness map: %s" % e)
    for p, v in [("reflection_glossiness", 0.06), ("reflection_metalness", 0.0),
                 ("coat_amount", 0.0)]:
        if rt.isProperty(fmat, rt.Name(p)):
            setattr(fmat, p, v)
    ground.material = fmat
    # 3) subtle grain relief from the height map (kept low so the polished
    #    reflection stays clean)
    try:
        dmod = rt.VRayDisplacementMod()
        dmod.name = "MatForge_Displace"
        if rt.isProperty(dmod, rt.Name("type")):
            dmod.type = 0
        dmod.texmap = builder._bitmap_tex(wood_maps["height"], linear=True)
        dmod.amount = 0.5
        rt.addModifier(ground, dmod)
    except Exception as e:
        out("floor displacement skipped: %s" % e)

    # --- big bright soft box straight overhead so the polished floor shows a
    #     broad reflected sheen (the 'shine') ---
    try:
        soft = rt.VRayLight()
        soft.type = 0                 # plane
        for p, v in [("u_size", 700.0), ("v_size", 500.0), ("size0", 700.0),
                     ("size1", 500.0)]:
            if rt.isProperty(soft, rt.Name(p)):
                setattr(soft, p, v)
        soft.multiplier = 4.5
        soft.pos = rt.Point3(0, -60, 560)
        rt.rotate(soft, rt.angleaxis(180, rt.Point3(1, 0, 0)))  # face down
        out("soft box added")
    except Exception as e:
        out("soft box skipped: %s" % e)

    # --- material spheres: marble / metal / glass (curvature-friendly) ---
    specs = [
        (-120, "marble", "Patina_Marble_maps", "Ball_Marble"),
        (0, "metal_brushed", "Patina_Metal_maps", "Ball_Metal"),
        (120, "glass_clear", "Patina_Marble_maps", "Ball_Glass"),
    ]
    R = 48
    for x, mclass, folder, name in specs:
        s = rt.Sphere(radius=R, segs=64, pos=rt.Point3(x, 0, R))
        s.name = name
        s.material = builder.build_material(maps_from(folder), name, mclass)
    out("built wood floor + %d material spheres" % len(specs))

    # --- camera with depth of field (photographic) ---
    focus_pt = rt.Point3(0, 0, R)
    cam = None
    made_dof = False
    try:  # prefer a V-Ray physical camera for real DOF + exposure
        if hasattr(rt, "VRayPhysicalCamera"):
            cam = rt.VRayPhysicalCamera(target=rt.targetObject(pos=focus_pt))
            cam.pos = rt.Point3(210, -430, 150)
            for p, v in [("f_number", 3.2), ("specify_focus", False)]:
                if rt.isProperty(cam, rt.Name(p)):
                    setattr(cam, p, v)
            for p in ("use_dof", "dof_on", "depthOfField"):
                if rt.isProperty(cam, rt.Name(p)):
                    setattr(cam, p, True)
                    made_dof = True
            # turn OFF physical exposure — render at the (well-exposed) light
            # levels instead of the camera's dark real-world exposure default;
            # DOF still comes from f_number/aperture.
            for p in ("exposure", "vignetting"):
                if rt.isProperty(cam, rt.Name(p)):
                    setattr(cam, p, False)
            for p in ("exposure_mode",):
                if rt.isProperty(cam, rt.Name(p)):
                    setattr(cam, p, 0)
    except Exception as e:
        out("physical cam failed (%s)" % e)
        cam = None
    if cam is None:  # fallback: standard target camera, no DOF
        cam = rt.targetCamera(pos=rt.Point3(210, -430, 150),
                              target=rt.targetObject(pos=focus_pt))
        try:
            cam.fov = 48.0
        except Exception:
            pass
    out("camera: %s (dof=%s)" % (str(rt.classOf(cam)), made_dof))

    out("rendering 1600x1000...")
    rt.render(camera=cam, outputwidth=1600, outputheight=1000,
              outputfile=OUT_IMG, vfb=False, quiet=True)
    ok = os.path.isfile(OUT_IMG) and os.path.getsize(OUT_IMG) > 5000
    out("RENDER_OK" if ok else "RENDER_FAIL")
except Exception:
    out("RENDER_FAIL — exception:")
    out(traceback.format_exc())
finally:
    _flush()
