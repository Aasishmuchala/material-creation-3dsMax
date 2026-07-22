"""Ultra-photoreal archviz vignette — wood floor + marble feature wall + a
rounded plinth with a brushed-metal vessel and a glass sphere. 4K PATINA
materials, HDRI + a dramatic raking key, real DOF. Run via 3dsmaxbatch.
Writes render_scene.png.
"""
import os
import sys
import traceback

_REPO = r"C:\Users\aasis\matforge"
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

RESULT = os.path.join(_REPO, "render_scene_result.txt")
OUT_IMG = os.path.join(_REPO, "render_scene.png")
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

    def set_first(o, names, v):
        for n in names:
            if rt.isProperty(o, rt.Name(n)):
                setattr(o, n, v)
                return True
        return False

    def uvw(node, tile, maptype=4):
        try:
            m = rt.Uvwmap()
            m.maptype = maptype
            for p in ("length", "width", "height"):
                if rt.isProperty(m, rt.Name(p)):
                    setattr(m, p, tile)
            rt.addModifier(node, m)
        except Exception as e:
            out("uvw skipped on %s: %s" % (node.name, e))

    out("MatForge SCENE render (4K materials)")
    rt.resetMaxFile(rt.Name("noPrompt"))

    vray_cls = None
    for c in rt.RendererClass.classes:
        n = str(c)
        if "V_Ray" in n and "GPU" not in n and "RT" not in n:
            vray_cls = c
            break
    rt.renderers.production = vray_cls()
    out("renderer: %s" % str(rt.classOf(rt.renderers.production)))

    # 4K folders if present, else fall back to 2K
    def folder(base4k, base2k):
        return base4k if os.path.isdir(os.path.join(SM, base4k)) else base2k
    F_WOOD = folder("Wood4K_maps", "Patina_Wood_maps")
    F_MARBLE = folder("Marble4K_maps", "Patina_Marble_maps")
    F_METAL = folder("Metal4K_maps", "Patina_Metal_maps")
    out("materials: %s / %s / %s" % (F_WOOD, F_MARBLE, F_METAL))

    # --- lighting: HDRI dome (fill+reflections) + raking directional key ---
    hdr = rt.VRayBitmap() if hasattr(rt, "VRayBitmap") else rt.Bitmaptexture()
    set_first(hdr, ["HDRIMapName", "fileName", "filename"], HDRI)
    dome = rt.VRayLight()
    dome.type = 1
    dome.multiplier = 4.5             # bright interior fill (was far too dim)
    set_first(dome, ["texmap", "domeTexmap"], hdr)
    set_first(dome, ["texmap_on", "useDomeTex"], True)

    key = rt.targetDirectionalLight(pos=rt.Point3(-750, -450, 950),
                                    target=rt.targetObject(
                                        pos=rt.Point3(60, 220, 60)))
    key.rgb = rt.color(255, 252, 246)   # near-neutral so white marble reads white
    key.multiplier = 2.6
    # soft front fill so the camera side isn't in shadow
    ffill = rt.Omnilight(pos=rt.Point3(120, -650, 320))
    ffill.multiplier = 0.9
    try:
        key.castShadows = True
        key.shadowGenerator = rt.VRayShadow()
        set_first(key, ["vraySoftShadows", "shadowSoftness"], True)
    except Exception as e:
        out("key shadow: %s" % e)

    # --- materials ---
    floor_mat = builder.build_material(maps_from(F_WOOD), "S_Wood",
                                       "wood_interior")
    # lacquer shine: brdf_useRoughness is ON so glossiness=ROUGHNESS; remove the
    # matte roughness map and set LOW roughness (polished).
    try:
        setattr(floor_mat, "texmap_reflectionGlossiness", None)
    except Exception:
        pass
    set_first(floor_mat, ["reflection_glossiness"], 0.06)
    # richer colour
    try:
        cc = rt.Color_Correction()
        cc.map = floor_mat.texmap_diffuse
        set_first(cc, ["saturation"], 22.0)
        set_first(cc, ["gammaRGB"], 1.1)
        floor_mat.texmap_diffuse = cc
    except Exception as e:
        out("cc: %s" % e)

    marble_mat = builder.build_material(maps_from(F_MARBLE), "S_Marble",
                                        "marble")
    metal_mat = builder.build_material(maps_from(F_METAL), "S_Metal",
                                       "metal_brushed")
    # For a metal the albedo IS the reflection tint. The blue-plate PATINA
    # albedo was far too dark (-> black sphere). Replace it with a light
    # neutral steel tint; keep the brushed roughness/normal for the finish.
    try:
        setattr(metal_mat, "texmap_diffuse", None)
    except Exception:
        pass
    set_first(metal_mat, ["diffuse"], rt.color(208, 210, 214))
    set_first(metal_mat, ["reflection_metalness"], 1.0)
    glass_mat = builder.build_material(maps_from(F_WOOD), "S_Glass",
                                       "glass_clear")

    # --- geometry ---
    floor = rt.Plane(width=4000, length=4000, pos=rt.Point3(0, 0, 0),
                     widthsegs=1, lengthsegs=1)
    floor.name = "Floor"
    floor.material = floor_mat
    uvw(floor, 900)

    wall = rt.Box(width=4000, length=40, height=2000, pos=rt.Point3(0, 620, 0))
    wall.name = "MarbleWall"
    wall.material = marble_mat
    uvw(wall, 1400)

    plinth = rt.ChamferBox(length=320, width=460, height=95, fillet=10,
                           filletSegs=3, pos=rt.Point3(30, 300, 0))
    plinth.name = "Plinth"
    plinth.material = marble_mat
    uvw(plinth, 500)

    # smooth polished-steel sphere hero (Sphere segs is reliable, unlike the
    # ChamferCyl sides which rendered faceted)
    steel = rt.Sphere(radius=82, segs=72, pos=rt.Point3(-90, 300, 95 + 82))
    steel.name = "SteelBall"
    steel.material = metal_mat

    ball = rt.Sphere(radius=60, segs=72, pos=rt.Point3(95, 300, 95 + 60))
    ball.name = "GlassBall"
    ball.material = glass_mat

    msphere = rt.Sphere(radius=50, segs=72, pos=rt.Point3(255, 120, 50))
    msphere.name = "MarbleBall"
    msphere.material = marble_mat

    out("scene built: floor, wall, plinth, vase, glass + marble spheres")

    # --- camera with DOF (physical, exposure off) ---
    focus = rt.Point3(-80, 300, 150)
    cam = None
    made_dof = False
    try:
        if hasattr(rt, "VRayPhysicalCamera"):
            cam = rt.VRayPhysicalCamera(target=rt.targetObject(pos=focus))
            cam.pos = rt.Point3(380, -540, 210)
            set_first(cam, ["f_number"], 4.0)
            for p in ("use_dof", "dof_on", "depthOfField"):
                if rt.isProperty(cam, rt.Name(p)):
                    setattr(cam, p, True)
                    made_dof = True
            set_first(cam, ["exposure", "vignetting"], False)
            set_first(cam, ["exposure_mode"], 0)
    except Exception as e:
        out("phys cam: %s" % e)
        cam = None
    if cam is None:
        cam = rt.targetCamera(pos=rt.Point3(380, -540, 210),
                              target=rt.targetObject(pos=focus))
        set_first(cam, ["fov"], 50.0)
    out("camera: %s (dof=%s)" % (str(rt.classOf(cam)), made_dof))

    out("rendering 1920x1200...")
    rt.render(camera=cam, outputwidth=1920, outputheight=1200,
              outputfile=OUT_IMG, vfb=False, quiet=True)
    ok = os.path.isfile(OUT_IMG) and os.path.getsize(OUT_IMG) > 5000
    out("RENDER_OK" if ok else "RENDER_FAIL")
except Exception:
    out("RENDER_FAIL — exception:")
    out(traceback.format_exc())
finally:
    _flush()
