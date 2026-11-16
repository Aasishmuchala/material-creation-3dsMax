"""MatForge Max-side builder — wires generated maps into a finished VRayMtl.

Runs INSIDE 3ds Max (pymxs). All V-Ray parameter writes go through
defensive candidate lists because property names drift between V-Ray
builds; every miss is logged, never fatal (same pattern as MaxOptimizer /
lightmatch-max).

Deliberate choices baked in:
  * normal + roughness + height load at gamma 1.0 (data, not color)
  * roughness map plugs straight in with brdf_useRoughness=ON (no invert)
  * AO map is generated but NOT wired — V-Ray GI already occludes;
    baked AO double-darkens
  * foliage: clip-mode opacity, VRay2SidedMtl wrap, no refraction
  * glass: thin-walled, fog clamped near-white
"""
import json
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import contextlib  # noqa: E402

import matphys  # noqa: E402
from core.recipes import RECIPES, get_recipe  # noqa: E402

import pymxs  # noqa: E402
from pymxs import runtime as rt  # noqa: E402

LOG = []

# tag stamped on every MatForge-created VRayDisplacementMod so re-assign can
# find and replace its own modifier instead of stacking a new one each run.
_DISP_TAG = "MatForge_Displace"


def _mm_to_scene_units(mm):
    """Convert a millimeter value to the scene's SYSTEM units.

    Displacement amount (and future real-world scale) is interpreted in scene
    system units, which may be mm/cm/m/inches. Writing a raw mm number gives
    wrong-magnitude geometry in any non-mm scene. rt.units.decodeValue returns
    the value already expressed in system units.
    """
    try:
        return float(rt.units.decodeValue(f"{float(mm)}mm"))
    except Exception as e:
        _log(f"  unit conversion failed ({e}); assuming scene units == mm")
        return float(mm)


def _undo_ctx(label):
    """pymxs undo transaction if available, else a no-op (mock/off-Max)."""
    try:
        return pymxs.undo(True, label)
    except Exception:
        return contextlib.nullcontext()


def _log(msg):
    LOG.append(msg)
    print("[MatForge] " + msg)


def _set_first(obj, candidates, value, what=""):
    """Set the first existing property from candidates. Log misses."""
    for name in candidates:
        if rt.isProperty(obj, rt.Name(name)):
            try:
                setattr(obj, name, value)
                return name
            except Exception as e:  # wrong type etc. — try next candidate
                _log(f"  set {name} failed ({e}); trying next")
    _log(f"  MISS: no property for {what or candidates[0]} "
         f"(tried {', '.join(candidates)})")
    return None


def _color_raw(rgb):
    """Unclamped 0-1 -> 0-255 Color. Only for values that are not colours
    (Corona Complex IOR n,k, written raw x255; VERIFY_CORONA type/scale)."""
    return rt.Color(rgb[0] * 255.0, rgb[1] * 255.0, rgb[2] * 255.0)


def _color(rgb):
    """0-1 RGB -> Color, each channel clamped to [0, 1] (NaN -> 0). A bad
    table value is logged instead of reaching the swatch out of range."""
    vals = []
    for c in rgb[:3]:
        c = float(c)
        vals.append(0.0 if c != c else min(max(c, 0.0), 1.0))
    if vals != [float(c) for c in rgb[:3]]:
        _log(f"  colour {tuple(rgb[:3])} clamped to "
             f"({vals[0]:.4f}, {vals[1]:.4f}, {vals[2]:.4f})")
    return _color_raw(vals)


def _swatch(rgb_linear):
    """Linear RGB -> swatch colour, written as-is.

    3ds Max stores colour parameters scene-linear; gamma "Affect Color
    Selectors" / OCIO only changes how the picker displays them. So F0, edge
    tint, fog and absorption are all written linear (never display-encoded).
    """
    return _color(tuple(rgb_linear))


def _has_class(name):
    """True when a MAXScript class exists. hasattr() is useless on pymxs
    (missing names come back as an `undefined` wrapper), so ask MAXScript."""
    try:
        return bool(rt.execute("(%s != undefined)" % name))
    except Exception:
        return False


def _mm_per_scene_unit():
    """Millimetres in one scene system unit (inverse of _mm_to_scene_units)."""
    try:
        per_mm = _mm_to_scene_units(1.0)
        return 1.0 / per_mm if per_mm > 0 else 1.0
    except Exception:
        return 1.0


def _data_color_space():
    """Name of the OCIO 'data' (raw) colour space when 3ds Max colour
    management runs in an OCIO mode, else None (legacy gamma pipeline)."""
    try:
        cpm = rt.ColorPipelineMgr
        mode = str(cpm.Mode)
    except Exception:
        return None                    # Max < 2024: gamma pipeline only
    if "OCIO" not in mode:
        return None
    try:
        name = str(cpm.DataColorSpace or "")
    except Exception:
        name = ""
    return name or "Raw"


# Stochastic tiling for "stationary" classes: the fraction of each UV tile
# cross-faded into its neighbours. Wider hides the repeat better but softens
# detail inside the blend band.
ANTI_TILE_BLEND = 0.15


def _anti_tile_uvw():
    """One VRayUVWRandomizer for every map of a stationary material, or None.

    Under real-world box mapping one UV tile is one texture repeat, so random
    by UV tile gives each repeat its own random offset and tile_blend fades
    it into its neighbours: V-Ray's stochastic tiling. A linen sofa or a rug
    then stops showing the same slubs and marks on a grid. Random by node
    handle as well, or identical parts (a sofa's two seat cushions) repeat
    one layout and the grid just moves to the cushion pitch. One node's maps
    stay aligned because they share this randomizer, but separate objects
    under one continuous mapping now meet with a jump. Not by element, which
    would cut one object into unrelated patches. Offsets only: rotating or
    flipping the lookup would turn the tangent-space normal map against its
    tangent frame (V-Ray's default rotation range is 0-360).
    """
    if not _has_class("VRayUVWRandomizer"):
        _log("  VRayUVWRandomizer not available; maps tile plainly")
        return None
    u = rt.VRayUVWRandomizer()
    _set_first(u, ["mode_by_uv_tile"], True, "random by UV tile")
    _set_first(u, ["mode_by_node_handle"], True, "random by node")
    _set_first(u, ["tile_blend"], ANTI_TILE_BLEND, "tile blend")
    for prop, value in (("variance_u_min", 0.0), ("variance_u_max", 1.0),
                        ("variance_v_min", 0.0), ("variance_v_max", 1.0),
                        ("variance_rot_min", 0.0), ("variance_rot_max", 0.0)):
        _set_first(u, [prop], value, prop)
    return u


def _material_uvw(mat):
    """The UVW randomizer a stationary material's maps share, else None."""
    try:
        if not rt.isProperty(mat, rt.Name("texmap_diffuse")):
            return None
        tex = mat.texmap_diffuse
        for _ in range(4):                  # through a nap falloff / colour correction
            if tex is None or rt.isProperty(tex, rt.Name("mapSource")):
                break
            inner = next((n for n in ("map1", "map") if rt.isProperty(tex, rt.Name(n))), None)
            tex = getattr(tex, inner) if inner else None
        if tex is None or not rt.isProperty(tex, rt.Name("mapSource")):
            return None
        return tex.mapSource
    except Exception:
        return None


def _bitmap_tex(path, linear=False, uvw=None):
    """Load a map into a Bitmaptexture with deterministic color management.

    Data maps (normal, roughness, height, opacity) MUST be raw. Under OCIO
    colour management (the 3ds Max 2024+ default) the gamma keyword is
    ignored and file rules decode every 8-bit PNG as sRGB: verified on Max
    2026.2, a 50 % grey data map read 0.216 instead of 0.502, which made
    roughness ~2.5x glossier and bent normal maps. So under OCIO the map is
    opened in the config's data colour space (colorSpace: keyword, verified
    to read 0.502); the legacy gamma pipeline keeps gamma 1.0. Albedo
    (linear=False) follows the scene's input rules so sRGB decodes normally.

    With a UVW randomizer (`uvw`) the map is a VRayBitmap instead, the only
    bitmap that takes one. Both of its colour settings are written, so no
    build default or render setting decides; the enums are from pb2vrayhdri.h
    in the V-Ray 7.30.02 SDK:
      * color_space, the transfer function: 0 none, 1 gamma, 2 sRGB, 3 from
        3ds Max, 4 auto (default). Measured on Max 2026.2 (50 % grey PNG
        rendered self-lit to a float EXR, OCIO too): 0 reads 0.502, 2 0.216.
      * rgbColorSpace, the primaries: 0 default (raw or guessed from the file
        name, by a render setting), 1 sRGB, 2 ACEScg, 3 raw. Grey cannot
        show it, but a normal map taken as sRGB under an ACEScg rendering
        space is converted: flat (0.5, 0.5, 1) becomes (0.524, 0.507,
        0.935), tilted 3.2 degrees, and weave relief is lit off-axis.
    So data maps are raw (0, 3) and colour maps sRGB (2, 1).
    """
    if uvw is not None:
        tex = rt.VRayBitmap()
        _set_first(tex, ["HDRIMapName", "fileName"], path, "bitmap filename")
        _set_first(tex, ["color_space"], 0 if linear else 2,
                   "transfer function (0 none, 2 sRGB)")
        _set_first(tex, ["rgbColorSpace"], 3 if linear else 1,
                   "RGB primaries (3 raw, 1 sRGB)")
        _set_first(tex, ["mapSource"], uvw, "UVW randomizer")
        return tex
    tex = rt.Bitmaptexture()
    if linear:
        cs = _data_color_space()
        try:
            if cs:
                tex.bitmap = rt.openBitMap(path, colorSpace=cs)
            else:
                tex.bitmap = rt.openBitMap(path, gamma=1.0)
            return tex
        except Exception as e:  # very old builds without the keyword
            _log(f"  openBitMap(raw) failed ({e}); filename fallback")
            # the data map now loads with the default input decode: a
            # MISS so forge_max surfaces it in the UI note
            _log(f"  MISS: raw colour space / gamma 1.0 not applied to "
                 f"{os.path.basename(path)} (data map decoded as colour)")
    # albedo, or linear fallback: inherit default input gamma
    _set_first(tex, ["filename", "fileName"], path, "bitmap filename")
    return tex


def sheen_from_albedo(mean_rgb, lum, desat=0.5, cap=0.9):
    """Sheen colour in the fibre's own hue: the albedo's linear mean scaled to
    luminance `lum`, then moved `desat` of the way to the grey of that
    luminance, each channel capped. Velvet's grazing sheen is light and less
    saturated than its body colour."""
    r, g, b = (max(1e-6, float(c)) for c in mean_rgb)
    k = lum / max(1e-6, 0.2126 * r + 0.7152 * g + 0.0722 * b)
    return tuple(min(cap, (1.0 - desat) * k * c + desat * lum) for c in (r, g, b))


def _albedo_mean(path, rows=32, cols=32):
    """Linear mean RGB of an sRGB-encoded albedo map, sampled on a grid in
    Max. None when it cannot be read."""
    def lin(v):
        v = float(v) / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    try:
        cs = _data_color_space()
        bm = rt.openBitMap(path, colorSpace=cs) if cs else rt.openBitMap(path, gamma=1.0)
        w, h = int(bm.width), int(bm.height)
        acc, n = [0.0, 0.0, 0.0], 0
        for y in range(0, h, max(1, h // rows)):
            for px in list(rt.getPixels(bm, rt.Point2(0, y), w))[::max(1, w // cols)]:
                acc[0] += lin(px.r)
                acc[1] += lin(px.g)
                acc[2] += lin(px.b)
                n += 1
        rt.close(bm)
        return tuple(a / n for a in acc) if n else None
    except Exception as exc:
        _log(f"albedo mean unreadable ({exc}); recipe sheen colour kept")
        return None


def _mottle_tex(rgb, amount, size_cm):
    """Fractal noise between rgb x (1 - amount) and rgb x (1 + amount), blotches
    about size_cm across: crushed pile catching the light unevenly."""
    nz = rt.Noise()
    _set_first(nz, ["type"], 1, "mottle fractal")
    _set_first(nz, ["size"], size_cm * 10.0 / _mm_per_scene_unit(), "mottle size")
    _set_first(nz, ["color1"], _color(tuple(c * (1.0 - amount) for c in rgb)), "mottle low")
    _set_first(nz, ["color2"], _color(tuple(min(1.0, c * (1.0 + amount)) for c in rgb)), "mottle high")
    return nz


def nap_side_colour(mean_rgb, nap):
    """The colour a pile turns at grazing view: the albedo's mean lifted
    `gain` times (to at most `max_lum`) and a little desaturated."""
    lum = 0.2126 * mean_rgb[0] + 0.7152 * mean_rgb[1] + 0.0722 * mean_rgb[2]
    return sheen_from_albedo(mean_rgb, min(float(nap.get("max_lum", 0.6)), float(nap["gain"]) * lum),
                             float(nap.get("desat", 0.25)))


def _nap_falloff(albedo_tex, side_rgb, power=2):
    """The albedo seen through a view falloff: itself face on, `side_rgb` at
    grazing view, rising as (1 - cos)^power (Perpendicular / Parallel
    falloffs nested `power` deep).

    A pile is dark where you look down the fibres and light where you look
    across them, whatever the light does; the sheen lobe alone only answers
    light that grazes, and velvet under soft frontal light rendered as flat
    felt. Linear (power 1) washed a seat seen at 25 degrees to 60 % of the
    side colour; squared keeps the body colour and leaves a soft rim.
    """
    tex = albedo_tex
    for _ in range(max(1, int(power))):
        fo = rt.Falloff()
        _set_first(fo, ["type"], 1, "nap falloff perpendicular/parallel")
        _set_first(fo, ["map1"], albedo_tex, "nap front map")
        if tex is albedo_tex:
            _set_first(fo, ["color2"], _color(side_rgb), "nap side colour")
        else:
            _set_first(fo, ["map2"], tex, "nap side (nested)")
        tex = fo
    return tex


def roughness_blend(forged, target, tol=0.015):
    """(map amount 0-1, scalar) that take a roughness map forged round
    `forged` to a mean of `target` through V-Ray's map-amount blend
    (map x amount + scalar x (1 - amount)): downwards the map is scaled
    toward 0, upwards toward 1, so its variation shrinks in proportion and
    nothing clips. (1.0, target) when they already agree."""
    forged, target = float(forged), min(max(float(target), 0.0), 1.0)
    if abs(forged - target) <= tol or not 0.0 < forged < 1.0:
        return 1.0, target
    if target < forged:
        return target / forged, 0.0
    return (1.0 - target) / (1.0 - forged), 1.0


def build_variants(mat, tints):
    """A Multi/Sub of `mat` and tinted copies, one per (brightness %,
    saturation %, hue shift deg) in `tints` (the first should be (0, 0, 0)):
    the albedo goes through a Color Correction map in each copy. Faces pick a
    variant by material ID, so separate boards or tiles differ the way real
    ones do. Returns `mat` itself when it has no albedo map to tint."""
    base = getattr(mat, "texmap_diffuse", None) if rt.isProperty(mat, rt.Name("texmap_diffuse")) else None
    if base is None:
        _log("variants: no albedo map to tint")
        return mat
    mm = rt.MultiMaterial(numsubs=len(tints))
    mm.name = str(mat.name) + "_variants"
    for i, (bri, sat, hue) in enumerate(tints):
        m = mat
        if i:
            m = rt.copy(mat)
            m.name = "%s_v%d" % (mat.name, i)
            cc = rt.ColorCorrection()
            _set_first(cc, ["map"], base, "variant source")
            _set_first(cc, ["brightness"], float(bri), "variant brightness")
            _set_first(cc, ["saturation"], float(sat), "variant saturation")
            _set_first(cc, ["hueShift"], float(hue), "variant hue")
            m.texmap_diffuse = cc
        rt.setSubMtl(mm, i + 1, m)
    return mm


def build_material(maps, name, mclass, metal=None, tint=None, anti_tile=True, albedo_mean=None,
                   roughness_base=None):
    """maps: dict map_name -> file path. Returns the top-level material.

    metal: optional matphys.METALS key; defaults to the recipe's named metal.
    tint: optional transmittance (linear RGB, one recipe thickness) for
    refractive classes, from the photo (manifest "transmission_tint").
    anti_tile: stochastic tiling for the recipe's "stationary" classes. Pass
    False when the maps do not tile (made with seamless off): the random
    wrapped offsets would put the photo's edges inside every repeat.
    albedo_mean: the albedo's linear mean RGB, for recipes whose sheen comes
    from it; read off the map in Max when not given.
    roughness_base: the recipe roughness the roughness map was forged round
    (manifest "roughness_base"). Where the recipe has moved since, the map is
    rescaled to the recipe's value instead of silently overriding it.
    """
    recipe = get_recipe(mclass)
    metal = metal or recipe.get("metal")
    if metal and metal not in matphys.METALS:
        raise ValueError("unknown metal '%s' (known: %s)"
                         % (metal, ", ".join(matphys.METALS)))
    # F0 mode: named metal + scalar full metalness (no metalness map)
    f0_mode = bool(metal and "metalness" not in maps
                   and recipe.get("metalness", 0) >= 1.0)
    LOG.clear()
    _log(f"building '{name}' as {mclass}")

    mat = rt.VRayMtl()
    mat.name = name
    uvw = _anti_tile_uvw() if anti_tile and recipe.get("stationary") else None
    if uvw is not None:
        _log("  stochastic tiling: random offset per UV tile, blend %.2f"
             % ANTI_TILE_BLEND)

    # --- diffuse ---
    if "albedo" in maps:
        alb = _bitmap_tex(maps["albedo"], linear=False, uvw=uvw)
        acc = recipe.get("albedo_cc")
        if acc:
            # pull an out-of-gamut photo albedo back (saturation/brightness %)
            cc = rt.ColorCorrection()
            _set_first(cc, ["map"], alb, "albedo correction source")
            _set_first(cc, ["saturation"], float(acc.get("saturation", 0.0)), "albedo saturation")
            _set_first(cc, ["brightness"], float(acc.get("brightness", 0.0)), "albedo brightness")
            alb = cc
        nap = recipe.get("nap")
        if nap:
            albedo_mean = albedo_mean or _albedo_mean(maps["albedo"])
            if albedo_mean:
                side = nap_side_colour(albedo_mean, nap)
                alb = _nap_falloff(alb, side, nap.get("power", 2))
                _log("  pile nap: lighter at grazing view %s" % (tuple(round(c, 3) for c in side),))
        _set_first(mat, ["texmap_diffuse"], alb, "albedo map slot")
    if f0_mode:
        # measured F0 as the swatch; albedo map kept at 30 % so scratches /
        # patina survive without re-tinting
        _set_first(mat, ["diffuse"], _swatch(matphys.metal_f0(metal)),
                   "metal F0 base colour")
        if "albedo" in maps:
            _set_first(mat, ["texmap_diffuse_multiplier"], 30.0,
                       "metal albedo blend 30%")

    # --- reflection: Fresnel on, roughness-mode, map plugged directly ---
    if f0_mode:
        _set_first(mat, ["reflection"],
                   _swatch(matphys.metal_edge_tint(metal)), "metal edge tint")
    else:
        _set_first(mat, ["reflection"], _color(recipe["reflect_color"]),
                   "reflect color")
    _set_first(mat, ["reflection_fresnel", "brdf_fresnel"], True, "fresnel")
    rough_mode = _set_first(mat, ["brdf_useRoughness", "useRoughness"], True,
                            "roughness mode")
    if "roughness" in maps:
        rough_tex = _bitmap_tex(maps["roughness"], linear=True, uvw=uvw)
        _set_first(mat, ["texmap_reflectionGlossiness",
                         "texmap_reflection_glossiness"], rough_tex,
                   "roughness map slot")
    _set_first(mat, ["reflection_glossiness"], recipe["base_roughness"],
               "base roughness value")
    if "roughness" in maps and roughness_base is not None:
        # The map was baked round the recipe roughness of its forge day and
        # replaces the scalar, so a later recipe change never reached a
        # material until it was re-forged (a leather stayed at the 0.60 the
        # recipe itself calls rubber). V-Ray blends map and scalar by the
        # slot's amount: that rescales the map to today's recipe value.
        amount, scalar = roughness_blend(roughness_base, recipe["base_roughness"])
        if amount < 1.0:
            if _set_first(mat, ["texmap_reflectionGlossiness_multiplier"],
                          amount * 100.0, "roughness map amount"):
                _set_first(mat, ["reflection_glossiness"], scalar,
                           "roughness blend value")
                _log("  roughness map forged at %.2f rescaled to the recipe's %.2f"
                     % (roughness_base, recipe["base_roughness"]))

    # Metalness: prefer a per-pixel map (PATINA supplies one) — the correct
    # PBR way to mask metal vs. dielectric — over the recipe's scalar.
    if "metalness" in maps:
        _set_first(mat, ["reflection_metalness", "metalness"], 1.0,
                   "metalness (map-driven)")
        _set_first(mat, ["texmap_metalness", "texmap_reflectionMetalness",
                         "texmap_metalness_on"],
                   _bitmap_tex(maps["metalness"], linear=True, uvw=uvw),
                   "metalness map slot")
    elif recipe.get("metalness"):
        _set_first(mat, ["reflection_metalness", "metalness"],
                   recipe["metalness"], "metalness")
    if recipe.get("anisotropy"):
        _set_first(mat, ["anisotropy", "reflection_anisotropy"],
                   recipe["anisotropy"], "anisotropy")

    # --- IOR ---
    # Lock reflection IOR to refraction IOR (V-Ray default) so setting
    # refraction_ior drives the Fresnel reflection IOR too — one dielectric
    # IOR governs both, which is physically correct.
    _set_first(mat, ["reflection_lockIOR", "reflection_lock_ior",
                     "lockIOR"], True, "lock reflection IOR")
    _set_first(mat, ["refraction_ior", "refractionIOR"], recipe["ior"], "IOR")

    # --- refraction block (glass etc.) ---
    refr = recipe.get("refraction")
    if refr:
        _set_first(mat, ["refraction"], _color((1.0, 1.0, 1.0)),
                   "refract color")
        r_ior = refr["ior"]
        thickness = float(refr.get("thickness_mm") or 10.0)
        if refr.get("glass"):
            # measured glass: IOR + absorption from matphys (one source)
            g = refr["glass"]
            r_ior = matphys.glass_ior(g)
            sigma = matphys.glass_sigma_mm(g)
        else:
            # no named glass (gemstone): the recipe fog colour is the
            # transmittance of one thickness_mm pane, same as Corona
            sigma = matphys.sigma_from_transmittance(refr["fog_color"],
                                                     thickness)
        if tint:
            # the photo's body colour (amethyst, green bottle glass) adds to
            # the material's own absorption over the same thickness
            extra = matphys.sigma_from_transmittance(matphys.body_tint(tint), thickness)
            sigma = tuple(a + b for a, b in zip(sigma, extra))
            _log("  transmission tint from the photo: %s" % (tuple(tint),))
        _set_first(mat, ["refraction_ior", "refractionIOR"], r_ior,
                   "refraction IOR")
        # Fog: V-Ray measures T(d) = fog_color ** (d_cm / fog_depth) with
        # unit scaling on (cm), so the colour is one pane's transmittance and
        # the depth is that pane's thickness in cm, right in any scene units.
        # (The old fog multiplier maths was per scene unit while V-Ray read
        # it per cm: 10x too clear in mm scenes, 100x too dark in m scenes.)
        units_cm = _set_first(mat, ["refraction_fogUnitsScale_on"], True,
                              "fog units in cm")
        if units_cm and rt.isProperty(mat, rt.Name("refraction_fogDepth")):
            _set_first(mat, ["refraction_fogColor"],
                       _swatch(matphys.transmittance(sigma, thickness)),
                       "fog color")
            _set_first(mat, ["refraction_fogDepth"], thickness / 10.0,
                       "fog depth (cm)")
        else:   # older builds: multiplier per scene unit
            fog_color, fog_mult = matphys.to_vray_fog(sigma, thickness,
                                                      _mm_per_scene_unit())
            _set_first(mat, ["refraction_fogColor", "refraction_fog_color",
                             "fogColor"], _color(fog_color), "fog color")
            _set_first(mat, ["refraction_fogMult", "refraction_fogMultiplier",
                             "refraction_fog_mult", "fogMult"],
                       fog_mult, "fog multiplier")
        _set_first(mat, ["refraction_affectShadows",
                         "refraction_affect_shadows", "affectShadows"],
                   refr.get("affect_shadows", True), "affect shadows")
        if refr.get("thin_walled"):
            _set_first(mat, ["refraction_thinWalled", "thin_walled",
                             "thinWalled"], True, "thin-walled")
            # Thin-walled refraction ignores fog, so pure white refraction
            # made every pane look like perfect CG glass. Tint the
            # transmission with one pane's measured transmittance instead
            # (clear float: the faint green of real glass).
            _set_first(mat, ["refraction"],
                       _swatch(matphys.transmittance(sigma, thickness)),
                       "thin-wall transmittance tint")
        # frosted/etched glass = rough refraction (glossiness is a roughness
        # value with brdf_useRoughness ON: higher = more diffuse transmission)
        if refr.get("glossiness") is not None:
            _set_first(mat, ["refraction_glossiness", "refractionGlossiness",
                             "refract_glossiness"], refr["glossiness"],
                       "refraction glossiness")

    # --- see-through weave (sheer curtains): straight through the gaps ---
    see = recipe.get("see_through")
    if see:
        _set_first(mat, ["refraction"], _swatch((see, see, see)),
                   "see-through weave (refract color)")
        _set_first(mat, ["refraction_thinWalled", "thin_walled", "thinWalled"],
                   True, "thin-walled: no bending")
        # refraction glossiness stays a glossiness whatever "use roughness"
        # says (that flips the reflection's only): 1 is a sharp view. At 0
        # the weave scattered everything and nothing showed through; a little
        # under 1 softens what lies behind, as a real voile does
        _set_first(mat, ["refraction_glossiness", "refractionGlossiness",
                         "refract_glossiness"], 0.92, "soft see-through")
        _set_first(mat, ["refraction_affectShadows",
                         "refraction_affect_shadows", "affectShadows"],
                   True, "daylight through the weave")

    # --- opacity (foliage): clip mode = binary cutout, fast ---
    if recipe.get("opacity") and "opacity" in maps:
        op_tex = _bitmap_tex(maps["opacity"], linear=True, uvw=uvw)
        _set_first(mat, ["texmap_opacity"], op_tex, "opacity map")
        # clip mode = binary cutout (int 1 across V-Ray builds); several
        # candidate names in case the enum property is spelled differently.
        # 2 = Stochastic, the V-Ray 7 default: filtered edges and, unlike
        # Clip (1), it keeps bump on the leaf.
        _set_first(mat, ["opacity_mode", "opacityMode", "option_opacityMode",
                         "brdf_opacityMode"], 2, "opacity stochastic mode")

    # --- bump via VRayNormalMap (gamma 1.0 handled in _bitmap_tex) ---
    if "normal" in maps:
        nrm = rt.VRayNormalMap()
        _set_first(nrm, ["normal_map", "normalMap"],
                   _bitmap_tex(maps["normal"], linear=True, uvw=uvw),
                   "normal map")
        _set_first(mat, ["texmap_bump"], nrm, "bump slot")
        _set_first(mat, ["texmap_bump_multiplier", "bump_multiplier",
                         "texmap_bump_amount"], recipe["bump_amount"],
                   "bump amount (1.0 = full strength)")

    # --- displacement is applied per-object via VRayDisplacementMod on
    # assign (world-unit .amount), NOT the material's percentage slot. See
    # assign_to_selection(). Wiring it here too would double-displace, and
    # the material slot's multiplier is a 0-100 percentage, not a mm height.

    # --- class extras: sheen / coat / translucency ---
    # Recipes state sheen and coat as GLOSSINESS (1 = mirror). With "Use
    # roughness" on, V-Ray 7 reads coat_glossiness and sheen_glossiness as
    # roughness too (verified on V-Ray 7.30: a 0.95 coat renders matte), so
    # they are written as 1 - glossiness, the same conversion Corona uses.
    def _gloss(g):
        return 1.0 - g if rough_mode else g

    sheen = recipe.get("sheen")
    if sheen:
        sheen_rgb = sheen["color"]
        mean = None
        if sheen.get("from_albedo") and "albedo" in maps:
            mean = albedo_mean or _albedo_mean(maps["albedo"])
            if mean:
                sheen_rgb = sheen_from_albedo(mean, sheen["from_albedo"], sheen.get("desat", 0.5))
                _log("  sheen from the albedo's hue: %s" % (tuple(round(c, 3) for c in sheen_rgb),))
        _set_first(mat, ["sheen_color"], _color(sheen_rgb), "sheen color")
        _set_first(mat, ["sheen_glossiness"], _gloss(sheen["glossiness"]),
                   "sheen gloss")
        if mean and sheen.get("mottle"):
            _set_first(mat, ["texmap_sheen"],
                       _mottle_tex(sheen_rgb, sheen["mottle"], sheen.get("mottle_cm", 25.0)),
                       "sheen mottle")
        elif "sheen" in maps and sheen.get("map", True):
            # fibre-coloured sheen (lifted albedo) instead of a grey film
            _set_first(mat, ["texmap_sheen"],
                       _bitmap_tex(maps["sheen"], linear=False, uvw=uvw),
                       "sheen map")
    coat = recipe.get("coat")
    if coat:
        _set_first(mat, ["coat_amount"], coat["amount"], "coat amount")
        _set_first(mat, ["coat_glossiness"], _gloss(coat["glossiness"]),
                   "coat gloss")
    transl = recipe.get("translucency")
    if transl:
        # V-Ray 7 SSS mode (translucency_on = 6, "SSS (wax)"): works with a
        # black refraction colour. translucency_color is the SSS colour,
        # translucency_amount the diffuse-to-SSS blend, refraction_fogColor
        # the per-channel scatter radius (as a fraction) and
        # refraction_fogDepth its scale in cm. Verified on V-Ray 7.30: the
        # old hard-wax mode (1) plus a 0.06 grey refraction rendered like
        # plain diffuse. The albedo map drives the SSS colour so veins and
        # pour lines stay visible through the glow.
        _set_first(mat, ["translucency_on", "translucency"], 6,
                   "translucency mode (SSS)")
        _set_first(mat, ["translucency_color"], _color(transl["color"]),
                   "SSS colour")
        _set_first(mat, ["translucency_amount"],
                   float(transl.get("sss_amount", 0.8)), "SSS amount")
        if "albedo" in maps:
            _set_first(mat, ["texmap_translucent"],
                       _bitmap_tex(maps["albedo"], linear=False, uvw=uvw),
                       "SSS colour map")
        _set_first(mat, ["refraction_fogUnitsScale_on"], True,
                   "scatter scale in cm")
        _set_first(mat, ["refraction_fogColor"],
                   _color(transl.get("sss_rgb", (1.0, 0.7, 0.5))),
                   "SSS per-channel radius")
        _set_first(mat, ["refraction_fogDepth"],
                   float(transl.get("sss_radius_mm", 5.0)) / 10.0,
                   "SSS radius scale (cm)")

    # --- self-illumination (emissive / LED panels) ---
    si = recipe.get("self_illum")
    if si:
        mult = si.get("multiplier", 1.0) if isinstance(si, dict) else 1.0
        # glow in the reference's own colours: drive self-illum by the albedo
        if "albedo" in maps:
            _set_first(mat, ["texmap_self_illumination",
                             "texmap_selfIllumination"],
                       _bitmap_tex(maps["albedo"], linear=False, uvw=uvw),
                       "self-illum map")
        _set_first(mat, ["selfIllumination", "self_illumination"],
                   _color((1.0, 1.0, 1.0)), "self-illum color")
        _set_first(mat, ["selfIllumination_multiplier",
                         "self_illumination_multiplier", "selfIllum_mult"],
                   mult, "self-illum multiplier")
        # Under a physical camera a raw multiplier of 3 is invisible at
        # daylight exposure (~1/700 s, verified in the realism lab); make it
        # relative to the camera exposure, and let the panel light the room.
        _set_first(mat, ["compensate_camera_exposure"], True,
                   "self-illum compensates camera exposure")
        _set_first(mat, ["selfIllumination_gi"], True, "self-illum emits GI")

    # --- foliage wrap: VRay2SidedMtl, NOT refraction ---
    two = recipe.get("two_sided")
    if two:
        wrap = rt.VRay2SidedMtl()
        wrap.name = name
        mat.name = name + "_front"
        _set_first(wrap, ["frontMtl", "frontMaterial"], mat, "2sided front")
        c = [x * two["amount"] for x in two["translucency"]]
        _set_first(wrap, ["translucency"], _color(c), "2sided translucency")
        if two.get("mult_front"):
            # the light coming through takes the cloth's own colour
            _set_first(wrap, ["mult_by_front_diffuse"], True, "2sided tint by front")
        return wrap
    return mat


def put_in_editor(mat, slot=None):
    """Drop the material onto a Compact-editor sphere (1-24) and open it.

    slot None -> the currently ACTIVE editor slot. This is deliberate and
    predictable: the artist's selected sphere receives the material. (The
    earlier "first free slot" heuristic was broken — default Compact slots
    are named "01 - Default"..., not "Material #", so it always fell back to
    slot 1 and silently overwrote it.) Pass an explicit slot to override.
    """
    n = int(rt.meditMaterials.count)
    if slot is None:
        try:
            slot = int(rt.medit.GetActiveMtlSlot())
        except Exception as e:
            _log(f"GetActiveMtlSlot failed ({e}); defaulting to slot 1")
            slot = 1
    slot = max(1, min(n, int(slot)))
    rt.meditMaterials[slot - 1] = mat  # pymxs collection index is 0-based
    try:
        rt.MatEditor.Open()
        rt.medit.SetActiveMtlSlot(slot, False)
    except Exception as e:
        _log(f"editor focus skipped: {e}")
    _log(f"placed '{mat.name}' in editor slot {slot}")
    return slot


def show_in_slate(mat):
    """Open the Slate Material Editor and add the material as a node tree, so
    the artist can SEE the wiring: the VRayMtl and its connected Bitmap /
    VRayNormalMap / roughness nodes (Slate auto-expands the graph on CreateNode).

    Slate (rt.sme) needs an interactive GUI -- it does not exist in 3dsmaxbatch
    -- so every call here is fully guarded and returns True/False. It NEVER
    raises, so a headless/older build just skips it. Reuses a dedicated
    'MatForge' view and offsets each tree so they don't stack.
    """
    sme = getattr(rt, "sme", None)
    if sme is None:
        _log("Slate (sme) API unavailable — skipped node view")
        return False
    try:
        sme.Open()
        view_idx = None
        try:                                   # reuse our own view if it exists
            for i in range(1, int(sme.GetNumViews()) + 1):
                if str(sme.GetView(i).name) == "MatForge":
                    view_idx = i
                    break
        except Exception:
            pass
        if view_idx is None:
            try:
                view_idx = int(sme.CreateView("MatForge"))
            except Exception:
                view_idx = int(getattr(sme, "activeView", 1) or 1)
        try:
            sme.activeView = view_idx
        except Exception:
            pass
        view = sme.GetView(view_idx)
        try:                                   # offset so trees don't overlap
            n = int(view.GetNumNodes())
        except Exception:
            n = 0
        pos = rt.Point2(float((n % 4) * 320), float((n // 4) * 60))
        view.CreateNode(mat, pos)              # Slate expands the full graph
        _log(f"opened '{mat.name}' in Slate (node view)")
        return True
    except Exception as e:
        _log(f"Slate node view skipped: {e}")
        return False


def assign_to_selection(mat, mclass, height_map=None):
    """Assign to selected nodes; add a WORKING VRayDisplacementMod where the
    recipe asks.

    Displacement in V-Ray is per-object, so this is where real surface
    displacement happens. The modifier needs THREE things to displace:
    its own height texmap, a world-unit amount, and a mapping type. A mod
    with no texmap (the earlier bug) displaces by nothing.
    """
    recipe = get_recipe(mclass)
    nodes = list(rt.selection)
    if not nodes:
        _log("assign requested but nothing selected")
        return 0
    wants_disp = (recipe.get("displacement_mm", 0) > 0
                  and height_map and hasattr(rt, "VRayDisplacementMod"))
    if recipe.get("displacement_mm", 0) > 0 and not height_map:
        _log("displacement requested but no height map path supplied — "
             "skipping displacement modifier")
    # convert the recipe's mm height to the scene's system units ONCE
    disp_amount = (_mm_to_scene_units(recipe["displacement_mm"])
                   if wants_disp else 0.0)
    # the height must follow the same randomized lookup as the bump and albedo
    uvw = _material_uvw(mat) if wants_disp else None
    for node in nodes:
        node.material = mat
        if wants_disp:
            try:
                _remove_matforge_disp(node)  # idempotent: no stacking on re-run
                dmod = rt.VRayDisplacementMod()
                dmod.name = _DISP_TAG
                if uvw is None:
                    # type 0 = 2D (texture-space) mapping: right for a plainly
                    # tiled height map; fast in V-Ray + Vantage.
                    _set_first(dmod, ["type"], 0, "displacement type (2D)")
                else:
                    # 2D mapping samples the map once over the 0-1 UV square
                    # and repeats it, so it cannot follow a randomizer that
                    # moves every tile's lookup: the relief would stay on the
                    # plain grid, out of register with the bump. 3D mapping
                    # (1) evaluates the texmap at each tessellated vertex.
                    _set_first(dmod, ["type"], 1, "displacement type (3D)")
                    # no cracks where box-map faces of different smoothing
                    # groups meet (chamfered cushions)
                    if rt.isProperty(dmod, rt.Name("keepContinuity")):
                        _set_first(dmod, ["keepContinuity"], True,
                                   "keep continuity")
                _set_first(dmod, ["texmap", "texmap_displacement",
                                  "displacement_map", "texture"],
                           _bitmap_tex(height_map, linear=True, uvw=uvw),
                           "displacement height map")
                _set_first(dmod, ["amount"], disp_amount,
                           "displacement amount (scene units)")
                # the height map is centred on 0.5, so shift by half the
                # amount: relief goes in and out instead of only up
                _set_first(dmod, ["shift"], -0.5 * disp_amount,
                           "displacement shift (centred)")
                rt.addModifier(node, dmod)
            except Exception as e:
                _log(f"displacement mod on {node.name} failed: {e}")
    _log(f"assigned to {len(nodes)} node(s)")
    return len(nodes)


def _remove_matforge_disp(node):
    """Delete any prior MatForge displacement modifier so re-assigning the
    same material doesn't stack (and double) displacement."""
    try:
        for m in list(getattr(node, "modifiers", [])):
            if str(getattr(m, "name", "")) == _DISP_TAG:
                rt.deleteModifier(node, m)
    except Exception as e:
        _log(f"  could not check existing displacement mods: {e}")


MAX_NAME_LEN = 120


def _validate_manifest(mf, base_dir=None):
    """Fail fast with a clear error on a malformed/future manifest, and
    confirm every referenced map file exists (else V-Ray wires black swatches
    with no obvious cause).

    Normalises mf in place: the name is capped at MAX_NAME_LEN characters and
    relative map paths are resolved against base_dir (the manifest's folder),
    never the process cwd (in Max, the install dir).
    """
    if not isinstance(mf, dict):
        raise ValueError("manifest must be a JSON object, got "
                         f"{type(mf).__name__}")
    for key in ("name", "class", "maps"):
        if key not in mf:
            raise ValueError(f"manifest missing required key '{key}'")
    name = mf["name"]
    if not isinstance(name, str) or not name.strip():
        raise ValueError("manifest 'name' must be a non-empty string, got "
                         f"{name!r}")
    if len(name) > MAX_NAME_LEN:
        _log(f"  material name capped at {MAX_NAME_LEN} characters")
        mf["name"] = name[:MAX_NAME_LEN]
    if not isinstance(mf["class"], str) or mf["class"] not in RECIPES:
        raise ValueError(f"manifest class {mf['class']!r} is not a known "
                         f"MatForge material class")
    metal = mf.get("metal")
    if metal is not None and not isinstance(metal, str):
        raise ValueError(f"manifest 'metal' must be a string or null, got "
                         f"{metal!r}")
    if metal and metal not in matphys.METALS:
        raise ValueError(f"manifest metal '{metal}' is not a known "
                         f"metal")
    for key in ("seamless", "pattern"):
        flag = mf.get(key, False)
        if not isinstance(flag, bool):
            raise ValueError(f"manifest '{key}' must be true or false, got "
                             f"{flag!r}")
    tint = mf.get("transmission_tint")
    if tint is not None and not (
            isinstance(tint, (list, tuple)) and len(tint) == 3
            and all(isinstance(c, (int, float)) and not isinstance(c, bool)
                    and 0.0 <= c <= 1.0 for c in tint)):
        # NaN (json reads it) would turn the absorption and the material black
        raise ValueError("manifest 'transmission_tint' must be three numbers "
                         f"in [0, 1], got {tint!r}")
    maps = mf["maps"]
    if not isinstance(maps, dict) or not all(
            isinstance(k, str) and isinstance(v, str)
            for k, v in maps.items()):
        raise ValueError("manifest 'maps' must be an object of "
                         "map name -> file path strings")
    if base_dir:
        mf["maps"] = maps = {
            k: (p if os.path.isabs(p)
                else os.path.normpath(os.path.join(base_dir, p)))
            for k, p in maps.items()}
    missing = [f"{k}={p}" for k, p in maps.items()
               if not os.path.isfile(p)]
    if missing:
        raise FileNotFoundError("manifest map file(s) not found: "
                                + ", ".join(missing))


def detect_renderer():
    """'vray' | 'corona' | None from the active renderer's class name."""
    try:
        cls = str(rt.classOf(rt.renderers.current)).lower()
    except Exception:
        return None
    if "v_ray" in cls or "vray" in cls:
        return "vray"
    if "corona" in cls:
        return "corona"
    return None


def resolve_renderer(choice="auto"):
    """Resolve auto|vray|corona|both to 'vray'|'corona'|'both' or raise."""
    if choice not in ("auto", "vray", "corona", "both"):
        raise ValueError("renderer must be auto|vray|corona|both")
    has_v = _has_class("VRayMtl")
    has_c = _has_class("CoronaPhysicalMtl")
    if choice == "auto":
        det = detect_renderer()
        if det == "vray" and has_v:
            return "vray"
        if det == "corona" and has_c:
            return "corona"
        if has_v:
            return "vray"
        if has_c:
            return "corona"
        raise RuntimeError("Neither V-Ray nor Corona material classes are "
                           "available")
    if choice in ("vray", "both") and not has_v:
        raise RuntimeError("V-Ray is not available in this session")
    if choice in ("corona", "both") and not has_c:
        raise RuntimeError("Corona is not available in this session")
    return choice


def build_from_manifest(manifest_path, slot=None, assign=False, slate=False,
                        renderer="auto", metal=None, corona_bitmap=False):
    with open(manifest_path, "r", encoding="utf-8") as f:
        mf = json.load(f)
    _validate_manifest(mf, os.path.dirname(os.path.abspath(manifest_path)))
    resolved = resolve_renderer(renderer)
    metal = metal or mf.get("metal")
    want_v = resolved in ("vray", "both")
    want_c = resolved in ("corona", "both")
    bc = None
    if want_c:
        from maxplugin import builder_corona as bc   # lazy: it imports builder
    built = []          # [{"renderer","material","slot"}] + live mats
    mats = {}
    vlog = []
    # one undo transaction: create + place + assign revert as a single Ctrl-Z
    with _undo_ctx("MatForge Create"):
        if want_v:
            # stochastic tiling only for maps that tile and carry no pattern
            # (random offsets would break a stripe or check at every
            # repeat); manifests from before "seamless" was recorded keep the
            # old default
            mats["vray"] = build_material(
                mf["maps"], mf["name"], mf["class"], metal=metal,
                tint=mf.get("transmission_tint"),
                anti_tile=mf.get("seamless", True) and not mf.get("pattern", False),
                roughness_base=mf.get("roughness_base"))
            s = put_in_editor(mats["vray"], slot)
            vlog = list(LOG)   # after placement: keep the slot line too
            built.append({"renderer": "vray",
                          "material": mats["vray"].name, "slot": s})
        if want_c:
            mats["corona"] = bc.build_material(
                mf["maps"], mf["name"], mf["class"], metal=metal,
                use_corona_bitmap=corona_bitmap,
                tint=mf.get("transmission_tint"))
            # builder_corona clears the shared LOG; keep the V-Ray lines first
            LOG[:] = vlog + list(LOG)
            cslot = slot
            if want_v:
                # next to the V-Ray sphere; one back when V-Ray took the last
                # slot (put_in_editor would clamp +1 onto the same slot)
                vslot = built[0]["slot"]
                n = int(rt.meditMaterials.count)
                cslot = vslot - 1 if vslot >= n else vslot + 1
            s = put_in_editor(mats["corona"], cslot)
            built.append({"renderer": "corona",
                          "material": mats["corona"].name, "slot": s})
        if assign:
            target = "vray"
            if resolved == "corona":
                target = "corona"
            elif resolved == "both" and detect_renderer() == "corona":
                target = "corona"
            height = mf["maps"].get("height")
            if target == "corona":
                bc.assign_to_selection(mats["corona"], mf["class"],
                                       height_map=height)
            else:
                assign_to_selection(mats["vray"], mf["class"],
                                    height_map=height)
    primary = built[0]
    # Slate view is opened OUTSIDE the undo block (opening an editor / laying
    # out nodes isn't part of the material-create undo transaction).
    slated = show_in_slate(mats[primary["renderer"]]) if slate else False
    return {"material": primary["material"], "slot": primary["slot"],
            "log": list(LOG), "slate": slated, "renderer": resolved,
            "materials": built}
