"""MatForge Max-side builder for Corona — wires generated maps into a finished
CoronaPhysicalMtl with the same contract as the V-Ray builder (builder.py).

Runs INSIDE 3ds Max (pymxs). Every Corona property write goes through the
candidate lists in corona_props.py (ALL UNVERIFIED, see docs/VERIFY_CORONA.md)
and builder.py's _set_first, so a wrong name is a logged MISS, never fatal.
builder.py helpers are reached by module attribute at call time
(_vb._set_first, _vb.LOG, ...) so importlib.reload(builder) never leaves a
stale binding here.

Deliberate choices (parity with the V-Ray builder):
  * normal + roughness + height + opacity load at gamma 1.0 (data, not color)
  * roughness map plugs straight in with roughnessMode = roughness (no invert)
  * AO map is generated but NOT wired (GI already occludes)
  * foliage: translucency + cutout opacity on the material itself, NO wrapper
    (CoronaPhysicalMtl is two-sided)
  * glass: thin mode per recipe, absorption from matphys (one pane thickness)
  * named metals: Complex IOR n,k from matphys; fallback base = F0, edge = g
  * displacement lives IN the material (no modifier on assign)
"""
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import matphys  # noqa: E402
from core.recipes import get_recipe  # noqa: E402
from maxplugin import builder as _vb  # noqa: E402
from maxplugin.corona_props import (CORONA_BITMAP, CORONA_MTL,  # noqa: E402
                                    CORONA_NORMAL, ENUM_ASSUMPTIONS)

# Decision 5: albedo kept at 30 % over the F0 swatch so scratches survive.
METAL_ALBEDO_BLEND = 0.30


def _set(mat, key, value, what=""):
    return _vb._set_first(mat, CORONA_MTL[key], value, what or key)


def _swatch(rgb_linear):
    # Max stores colour parameters scene-linear (picker gamma is display
    # only): same linear write as builder._swatch, fog and absorption
    return _vb._swatch(rgb_linear)


def _mm_per_scene_unit():
    try:
        units = _vb._mm_to_scene_units(1.0)
        return 1.0 / units if units else 1.0
    except Exception:
        return 1.0


class _TexFactory(object):
    """Bitmap loader for one material build.

    Default = builder.py's Bitmaptexture + openBitMap(gamma=1.0) path (proven
    on Max 2026). use_corona_bitmap switches to CoronaBitmap (gamma 1.0 for
    data maps, 2.2 for albedo; VERIFY). One CoronaUvwRandomizer is shared by
    every map of the material so albedo/roughness/normal stay aligned.
    """

    def __init__(self, use_corona_bitmap=False, uvw_randomizer=False):
        self.corona = bool(use_corona_bitmap)
        self.uvw = bool(uvw_randomizer)
        self._rnd = None
        if self.uvw and not self.corona:
            _vb._log("  uvw randomizer needs CoronaBitmap "
                     "(use_corona_bitmap); ignored")
            self.uvw = False

    def __call__(self, path, linear=False):
        if not self.corona:
            return _vb._bitmap_tex(path, linear=linear)
        rt = _vb.rt
        tex = rt.CoronaBitmap()
        _vb._set_first(tex, CORONA_BITMAP["filename"], path,
                       "CoronaBitmap filename")
        _vb._set_first(tex, CORONA_BITMAP["gamma"], 1.0 if linear else 2.2,
                       "CoronaBitmap gamma")
        if self.uvw:
            if self._rnd is None:
                self._rnd = rt.CoronaUvwRandomizer()
            _vb._set_first(tex, CORONA_BITMAP["uvw"], self._rnd,
                           "uvw randomizer slot")
        return tex


def _wire_metal(mat, maps, recipe, metal, tex):
    """metalness_mode -> Complex IOR n,k (named metal) or F0/edge fallback."""
    if "metalness" in maps:
        _set(mat, "metalness_mode", ENUM_ASSUMPTIONS["metalness_mode"],
             "metalness mode (map-driven)")
        _set(mat, "metalness_texmap", tex(maps["metalness"], linear=True),
             "metalness map slot")
        if metal:
            _vb._log(f"  metal '{metal}' ignored: metalness map drives "
                     "the metal mask")
        return
    m = recipe.get("metalness") or 0.0
    if m < 0.5:
        if m > 0.0:
            _vb._log(f"  metalness {m} < 0.5 written as dielectric "
                     "(Corona metalness is binary without a map)")
        if metal:
            _vb._log(f"  metal '{metal}' ignored: class is dielectric")
        return
    _set(mat, "metalness_mode", ENUM_ASSUMPTIONS["metalness_mode"],
         "metalness mode")
    if not metal or m < 1.0:
        if metal:
            _vb._log(f"  metal '{metal}' ignored: recipe metalness {m} < 1.0")
        return  # unnamed metal: the albedo map drives the tint
    # F0 mode (Decision 5): measured n,k, never guessed from pixels
    nk = matphys.metal_nk(metal)
    if _set(mat, "complex_ior_on", True, "complex IOR toggle"):
        _set(mat, "complex_ior_n", _vb._color([c[0] for c in nk]),
             "complex IOR n")
        _set(mat, "complex_ior_k", _vb._color([c[1] for c in nk]),
             "complex IOR k")
    else:
        _vb._log("  complex IOR unavailable; base = F0, edge = Gulbrandsen g")
        _set(mat, "base_color", _swatch(matphys.metal_f0(metal)),
             "metal F0 base colour")
        _set(mat, "edge_color", _swatch(matphys.metal_edge_tint(metal)),
             "metal edge colour")
    if "albedo" in maps:
        used = _set(mat, "base_texmap_amount", METAL_ALBEDO_BLEND,
                    "metal albedo blend")
        if used:
            _vb._log(f"  {used} = {METAL_ALBEDO_BLEND} (scale VERIFY: 0-1 "
                     "vs 0-100)")


def build_material(maps, name, mclass, metal=None, use_corona_bitmap=False,
                   uvw_randomizer=False):
    """maps: dict map_name -> file path. Returns the CoronaPhysicalMtl."""
    recipe = get_recipe(mclass)
    metal = metal or recipe.get("metal")
    if metal and metal not in matphys.METALS:
        raise ValueError(f"metal '{metal}' is not a known metal")
    _vb.LOG.clear()
    _vb._log(f"building '{name}' as {mclass} (Corona)")
    rt = _vb.rt
    tex = _TexFactory(use_corona_bitmap, uvw_randomizer)

    mat = rt.CoronaPhysicalMtl()
    mat.name = name

    # --- base colour ---
    if "albedo" in maps:
        _set(mat, "base_texmap", tex(maps["albedo"], linear=False),
             "base colour map")

    # --- roughness: roughness mode, map plugged directly ---
    _set(mat, "roughness_mode", ENUM_ASSUMPTIONS["roughness_mode"],
         "roughness mode")
    _set(mat, "roughness", recipe["base_roughness"], "base roughness value")
    if "roughness" in maps:
        _set(mat, "roughness_texmap", tex(maps["roughness"], linear=True),
             "roughness map slot")

    # --- metalness ---
    _wire_metal(mat, maps, recipe, metal, tex)
    if recipe.get("anisotropy"):
        _set(mat, "anisotropy", recipe["anisotropy"], "anisotropy")

    # --- IOR (one dielectric IOR governs reflection + refraction) ---
    refr = recipe.get("refraction")
    ior = recipe["ior"]
    glass = refr.get("glass") if refr else None
    if refr:
        ior = matphys.glass_ior(glass) if glass else refr["ior"]
    _set(mat, "ior", ior, "IOR")

    # --- refraction block (glass etc.) ---
    if refr:
        _set(mat, "refraction_amount", 1.0, "refraction amount")
        _set(mat, "thin_mode", bool(refr.get("thin_walled")), "thin mode")
        thickness = float(refr.get("thickness_mm") or 10.0)
        mm_per_unit = _mm_per_scene_unit()
        if glass:
            colour, dist = matphys.to_corona_absorption(
                matphys.glass_sigma_mm(glass), thickness, mm_per_unit)
        else:
            # no named glass: the recipe fog colour is the transmittance of
            # one thickness_mm pane (same as the V-Ray path keeps it)
            colour = tuple(refr["fog_color"])
            dist = thickness / mm_per_unit
        _set(mat, "absorption_color", _vb._color(colour), "absorption colour")
        _set(mat, "absorption_distance", dist,
             "absorption distance (scene units)")
        if refr.get("glossiness") is not None:
            _vb._log("  frosted: Corona refraction shares base roughness")

    # --- opacity (foliage): cutout = binary clip, fast ---
    if recipe.get("opacity") and "opacity" in maps:
        _set(mat, "opacity_texmap", tex(maps["opacity"], linear=True),
             "opacity map")
        _set(mat, "opacity_cutout", True, "opacity cutout")

    # --- bump via CoronaNormal (bitmap linear, no added gamma) ---
    if "normal" in maps:
        nrm = rt.CoronaNormal()
        _vb._set_first(nrm, CORONA_NORMAL["input"],
                       tex(maps["normal"], linear=True), "normal map")
        _vb._set_first(nrm, CORONA_NORMAL["flip_green"], False,
                       "normal flip green")
        _vb._set_first(nrm, CORONA_NORMAL["add_gamma"], False,
                       "normal add gamma")
        _set(mat, "bump_texmap", nrm, "bump slot")
        _set(mat, "bump_amount", recipe["bump_amount"] / 100.0,
             "bump amount (recipe % / 100)")

    # --- displacement lives in the material (scene units) ---
    if recipe.get("displacement_mm", 0) > 0:
        if "height" in maps:
            _set(mat, "displacement_texmap", tex(maps["height"], linear=True),
                 "displacement map")
            _set(mat, "displacement_min", 0.0, "displacement minimum")
            _set(mat, "displacement_max",
                 _vb._mm_to_scene_units(recipe["displacement_mm"]),
                 "displacement maximum (scene units)")
        else:
            _vb._log("displacement requested but no height map — skipped")

    # --- class extras: sheen / coat / translucency ---
    sheen = recipe.get("sheen")
    if sheen:
        _set(mat, "sheen_amount", 1.0, "sheen amount")
        _set(mat, "sheen_color", _vb._color(sheen["color"]), "sheen colour")
        _set(mat, "sheen_roughness", 1.0 - sheen["glossiness"],
             "sheen roughness")
    coat = recipe.get("coat")
    if coat:
        _set(mat, "clearcoat_amount", coat["amount"], "clearcoat amount")
        _set(mat, "clearcoat_roughness", 1.0 - coat["glossiness"],
             "clearcoat roughness")
        _set(mat, "clearcoat_ior", 1.5, "clearcoat IOR")
    transl = recipe.get("translucency")
    if transl and not refr:
        # marble / wax: real volumetric SSS (no refraction trick needed)
        radius_mm = transl.get("sss_radius_mm")
        if radius_mm is None:
            radius_mm = 1.0
            _vb._log("  no sss_radius_mm in recipe; using 1.0 mm")
        _set(mat, "sss_mode", ENUM_ASSUMPTIONS["sss_mode"], "SSS mode")
        _set(mat, "sss_amount", transl["amount"], "SSS amount")
        _set(mat, "sss_color", _vb._color(transl["color"]), "SSS colour")
        _set(mat, "sss_radius", _vb._mm_to_scene_units(radius_mm),
             "SSS radius (scene units)")

    # --- self-illumination (emissive / LED panels) ---
    si = recipe.get("self_illum")
    if si:
        mult = si.get("multiplier", 1.0) if isinstance(si, dict) else 1.0
        if "albedo" in maps:
            _set(mat, "self_illum_texmap", tex(maps["albedo"], linear=False),
                 "self-illum map")
        _set(mat, "self_illum_color", _vb._color((1.0, 1.0, 1.0)),
             "self-illum colour")
        _set(mat, "self_illum_level", mult, "self-illum level")

    # --- foliage: thin translucency on the material itself, NO wrapper ---
    two = recipe.get("two_sided")
    if two:
        _set(mat, "translucency_fraction", two["amount"],
             "translucency fraction")
        _set(mat, "translucency_color", _vb._color(two["translucency"]),
             "translucency colour")
    return mat


def assign_to_selection(mat, mclass, height_map=None):
    """Assign to selected nodes. No modifier: Corona displacement is wired in
    the material by build_material (height_map kept for signature parity)."""
    get_recipe(mclass)  # same KeyError contract as the V-Ray builder
    nodes = list(_vb.rt.selection)
    if not nodes:
        _vb._log("assign requested but nothing selected")
        return 0
    for node in nodes:
        node.material = mat
    _vb._log("Corona displacement lives in the material")
    _vb._log(f"assigned to {len(nodes)} node(s)")
    return len(nodes)
