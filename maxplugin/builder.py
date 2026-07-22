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


def _color(rgb):
    return rt.Color(rgb[0] * 255.0, rgb[1] * 255.0, rgb[2] * 255.0)


def _bitmap_tex(path, linear=False):
    """Load a map into a Bitmaptexture with deterministic color management.

    Data maps (normal, roughness, height, opacity) MUST be linear — we force
    input gamma 1.0 via openBitMap, which is correct in every pipeline
    (gamma-managed or OCIO/ACES). Albedo (linear=False) inherits the
    project's default input gamma so sRGB textures linearize correctly.

    Deliberately NOT using VRayBitmap here: its color_space enum values drift
    between builds, so guessing "linear" risks mis-tagging data maps as sRGB
    and silently corrupting the render. Bitmaptexture + explicit gamma is
    unambiguous.
    """
    tex = rt.Bitmaptexture()
    if linear:
        try:
            tex.bitmap = rt.openBitMap(path, gamma=1.0)
            return tex
        except Exception as e:  # very old builds without gamma kwarg
            _log(f"  openBitMap(gamma=1.0) failed ({e}); filename fallback")
    # albedo, or linear fallback: inherit default input gamma
    _set_first(tex, ["filename", "fileName"], path, "bitmap filename")
    return tex


def build_material(maps, name, mclass):
    """maps: dict map_name -> file path. Returns the top-level material."""
    recipe = get_recipe(mclass)
    LOG.clear()
    _log(f"building '{name}' as {mclass}")

    mat = rt.VRayMtl()
    mat.name = name

    # --- diffuse ---
    if "albedo" in maps:
        mat.texmap_diffuse = _bitmap_tex(maps["albedo"], linear=False)

    # --- reflection: Fresnel on, roughness-mode, map plugged directly ---
    _set_first(mat, ["reflection"], _color(recipe["reflect_color"]),
               "reflect color")
    _set_first(mat, ["reflection_fresnel", "brdf_fresnel"], True, "fresnel")
    _set_first(mat, ["brdf_useRoughness", "useRoughness"], True,
               "roughness mode")
    if "roughness" in maps:
        rough_tex = _bitmap_tex(maps["roughness"], linear=True)
        _set_first(mat, ["texmap_reflectionGlossiness",
                         "texmap_reflection_glossiness"], rough_tex,
                   "roughness map slot")
    _set_first(mat, ["reflection_glossiness"], recipe["base_roughness"],
               "base roughness value")

    # Metalness: prefer a per-pixel map (PATINA supplies one) — the correct
    # PBR way to mask metal vs. dielectric — over the recipe's scalar.
    if "metalness" in maps:
        _set_first(mat, ["reflection_metalness", "metalness"], 1.0,
                   "metalness (map-driven)")
        _set_first(mat, ["texmap_metalness", "texmap_reflectionMetalness",
                         "texmap_metalness_on"],
                   _bitmap_tex(maps["metalness"], linear=True),
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
        _set_first(mat, ["refraction_ior", "refractionIOR"], refr["ior"],
                   "refraction IOR")
        _set_first(mat, ["refraction_fogColor", "refraction_fog_color",
                         "fogColor"], _color(refr["fog_color"]), "fog color")
        _set_first(mat, ["refraction_fogMult", "refraction_fogMultiplier",
                         "refraction_fog_mult", "fogMult"],
                   refr["fog_mult"], "fog multiplier")
        _set_first(mat, ["refraction_affectShadows",
                         "refraction_affect_shadows", "affectShadows"],
                   refr.get("affect_shadows", True), "affect shadows")
        if refr.get("thin_walled"):
            _set_first(mat, ["refraction_thinWalled", "thin_walled",
                             "thinWalled"], True, "thin-walled")

    # --- opacity (foliage): clip mode = binary cutout, fast ---
    if recipe.get("opacity") and "opacity" in maps:
        op_tex = _bitmap_tex(maps["opacity"], linear=True)
        _set_first(mat, ["texmap_opacity"], op_tex, "opacity map")
        # clip mode = binary cutout (int 1 across V-Ray builds); several
        # candidate names in case the enum property is spelled differently.
        _set_first(mat, ["opacity_mode", "opacityMode", "option_opacityMode",
                         "brdf_opacityMode"], 1, "opacity clip mode")

    # --- bump via VRayNormalMap (gamma 1.0 handled in _bitmap_tex) ---
    if "normal" in maps:
        nrm = rt.VRayNormalMap()
        _set_first(nrm, ["normal_map", "normalMap"],
                   _bitmap_tex(maps["normal"], linear=True), "normal map")
        _set_first(mat, ["texmap_bump"], nrm, "bump slot")
        _set_first(mat, ["texmap_bump_multiplier", "bump_multiplier",
                         "texmap_bump_amount"], recipe["bump_amount"],
                   "bump amount (1.0 = full strength)")

    # --- displacement is applied per-object via VRayDisplacementMod on
    # assign (world-unit .amount), NOT the material's percentage slot. See
    # assign_to_selection(). Wiring it here too would double-displace, and
    # the material slot's multiplier is a 0-100 percentage, not a mm height.

    # --- class extras: sheen / coat / translucency ---
    sheen = recipe.get("sheen")
    if sheen:
        _set_first(mat, ["sheen_color"], _color(sheen["color"]), "sheen color")
        _set_first(mat, ["sheen_glossiness"], sheen["glossiness"],
                   "sheen gloss")
    coat = recipe.get("coat")
    if coat:
        _set_first(mat, ["coat_amount"], coat["amount"], "coat amount")
        _set_first(mat, ["coat_glossiness"], coat["glossiness"], "coat gloss")
    transl = recipe.get("translucency")
    if transl and not recipe.get("refraction"):
        # VRayMtl translucency (single-scatter SSS) only renders when the
        # material actually transmits light — with a black refraction colour
        # it is a silent no-op. Give translucent-but-not-glass materials
        # (e.g. marble) a small refraction so the effect is real, plus a fog
        # tint so the transmitted light picks up the material colour.
        _set_first(mat, ["refraction"], _color((0.06, 0.06, 0.06)),
                   "small refraction to activate translucency")
        _set_first(mat, ["refraction_fogColor", "refraction_fog_color"],
                   _color(transl["color"]), "translucency fog tint")
        # V-Ray 7 name is translucency_on (int enum: 1 = hard/wax model),
        # hidden from the UI and MAXScript-only. Verified live on V-Ray 7.30.
        _set_first(mat, ["translucency_on", "translucency"], 1,
                   "translucency mode")
        _set_first(mat, ["translucency_color"], _color(transl["color"]),
                   "translucency color")
    elif transl:
        _set_first(mat, ["translucency_on", "translucency"], 1,
                   "translucency mode")
        _set_first(mat, ["translucency_color"], _color(transl["color"]),
                   "translucency color")

    # --- foliage wrap: VRay2SidedMtl, NOT refraction ---
    two = recipe.get("two_sided")
    if two:
        wrap = rt.VRay2SidedMtl()
        wrap.name = name
        mat.name = name + "_front"
        _set_first(wrap, ["frontMtl", "frontMaterial"], mat, "2sided front")
        c = [x * two["amount"] for x in two["translucency"]]
        _set_first(wrap, ["translucency"], _color(c), "2sided translucency")
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
    for node in nodes:
        node.material = mat
        if wants_disp:
            try:
                _remove_matforge_disp(node)  # idempotent: no stacking on re-run
                dmod = rt.VRayDisplacementMod()
                dmod.name = _DISP_TAG
                # type 0 = 2D (texture-space) mapping — right for a tiling
                # height map on a surface; fast in V-Ray + Vantage.
                _set_first(dmod, ["type"], 0, "displacement type (2D)")
                _set_first(dmod, ["texmap", "texmap_displacement",
                                  "displacement_map", "texture"],
                           _bitmap_tex(height_map, linear=True),
                           "displacement height map")
                _set_first(dmod, ["amount"], disp_amount,
                           "displacement amount (scene units)")
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


def _validate_manifest(mf):
    """Fail fast with a clear error on a malformed/future manifest, and
    confirm every referenced map file exists (else V-Ray wires black swatches
    with no obvious cause)."""
    for key in ("name", "class", "maps"):
        if key not in mf:
            raise ValueError(f"manifest missing required key '{key}'")
    if mf["class"] not in RECIPES:
        raise ValueError(f"manifest class '{mf['class']}' is not a known "
                         f"MatForge material class")
    missing = [f"{k}={p}" for k, p in mf["maps"].items()
               if not os.path.isfile(p)]
    if missing:
        raise FileNotFoundError("manifest map file(s) not found: "
                                + ", ".join(missing))


def build_from_manifest(manifest_path, slot=None, assign=False):
    with open(manifest_path, "r", encoding="utf-8") as f:
        mf = json.load(f)
    _validate_manifest(mf)
    # one undo transaction: create + place + assign revert as a single Ctrl-Z
    with _undo_ctx("MatForge Create"):
        mat = build_material(mf["maps"], mf["name"], mf["class"])
        used_slot = put_in_editor(mat, slot)
        if assign:
            assign_to_selection(mat, mf["class"],
                                height_map=mf["maps"].get("height"))
    return {"material": mat.name, "slot": used_slot, "log": list(LOG)}
