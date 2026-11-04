"""MAXScript property names per material / texmap class.

STATUS: VRayMtl / VRayNormalMap names marked "MatForge-verified" are the same
candidates MatForge's builder writes, and MatForge's headless smoke test reported
0 property misses on 3ds Max 2026 + V-Ray 7.30 (2026-07-22, see the MatForge repo
README). Everything else, including ALL Corona names, is still UNVERIFIED.
These names come from public V-Ray / Corona / 3ds Max
MAXScript documentation and community scripts, not from the current official
V-Ray 7 and Corona 13–14 references (unreachable while writing). Phase 0 task:
run ``tools/dump_props.ms`` in 3ds Max on one VRayMtl, CoronaPhysicalMtl,
VRayBitmap, CoronaBitmap, Bitmaptexture, VRayNormalMap, CoronaNormal and paste
the output into tests/fixtures/props_dump.txt, then correct this table.

Each entry lists candidate names in priority order; the scene walker uses the
first one that ``isProperty`` reports, and records which name it used so a
wrong table shows up in the report instead of silently returning defaults.
"""
from __future__ import annotations

from ..core.model import Renderer, SlotRole  # noqa: F401  (SlotRole re-exported for fixes)

# ---------------------------------------------------------------- materials
MATERIAL_CLASSES = {
    "VRayMtl": Renderer.VRAY,
    "CoronaPhysicalMtl": Renderer.CORONA,
    "CoronaLegacyMtl": Renderer.CORONA,
    "CoronaMtl": Renderer.CORONA,          # old name of the legacy material
    # OpenPBR class names are UNVERIFIED (3ds Max 2026/2027); see docs/VERIFY.md
    "OpenPBRMaterial": Renderer.OPENPBR,
    "OpenPBR_Material": Renderer.OPENPBR,
    "OpenPBRSurfaceMaterial": Renderer.OPENPBR,
}
LEGACY_CLASSES = {"CoronaLegacyMtl", "CoronaMtl"}

# canonical param -> candidate property names
PARAMS = {
    "VRayMtl": {  # MatForge-verified: use_roughness, metalness, refraction_ior, fog colour/mult, thin_walled
        "base_color": ["diffuse"],
        "glossiness": ["reflection_glossiness"],
        "use_roughness": ["brdf_useRoughness", "option_useRoughness"],
        "brdf": ["brdf_type"],
        "metalness": ["reflection_metalness"],
        "ior": ["reflection_ior"],
        "refraction_color": ["refraction"],
        "refraction_ior": ["refraction_ior"],
        "absorption_color": ["refraction_fogColor", "refraction_fog_color"],
        "absorption_mult": ["refraction_fogMult", "refraction_fogMultiplier"],
        "thin_walled": ["refraction_thinWalled", "thin_walled"],
    },
    "CoronaPhysicalMtl": {
        "base_color": ["baseColor", "basecolor"],
        "roughness": ["baseRoughness"],
        "metalness_mode": ["metalnessMode"],
        "ior": ["baseIor"],
        "refraction_amount": ["refractionAmount"],
        "absorption_color": ["volumetricAbsorptionColor", "absorptionColor"],
        "absorption_distance": ["volumetricAbsorptionDistance", "absorptionDistance"],
        "thin_walled": ["useThinMode", "thinMode"],
        # same candidates MatForge's builder_corona writes (corona_props "complex_ior_on")
        "complex_ior": ["useComplexIor", "complexIorEnabled", "metalComplexIor"],
    },
    "CoronaLegacyMtl": {
        "base_color": ["colorDiffuse"],
        "glossiness": ["reflectGlossiness"],
        "ior": ["fresnelIor"],
        "refraction_ior": ["ior"],
        "absorption_color": ["absorptionColor"],
        "absorption_distance": ["absorptionDistance"],
    },
}
PARAMS["CoronaMtl"] = PARAMS["CoronaLegacyMtl"]
PARAMS["OpenPBRMaterial"] = {   # ALL UNVERIFIED
    "base_color": ["base_color", "baseColor"],
    "roughness": ["specular_roughness", "roughness"],
    "metalness": ["base_metalness", "metalness", "metallic"],
    "ior": ["specular_ior", "ior"],
    "refraction_amount": ["transmission_weight", "transmission"],
    "absorption_color": ["transmission_color"],
    "absorption_distance": ["transmission_depth"],
    "thin_walled": ["geometry_thin_walled", "thin_walled"],
}
PARAMS["OpenPBR_Material"] = PARAMS["OpenPBRMaterial"]
PARAMS["OpenPBRSurfaceMaterial"] = PARAMS["OpenPBRMaterial"]

#: VRayMtl brdf_type integer -> name (V-Ray docs: 0 Phong, 1 Blinn, 2 Ward, 3 GGX). UNVERIFIED
VRAY_BRDF = {0: "phong", 1: "blinn", 2: "ward", 3: "ggx"}
VRAY_BRDF_REV = {v: k for k, v in VRAY_BRDF.items()}

# canonical slot role -> candidate texmap property names
SLOTS = {
    "VRayMtl": {
        SlotRole.BASE_COLOR: ["texmap_diffuse"],
        SlotRole.GLOSSINESS: ["texmap_reflectionGlossiness", "texmap_reflection_glossiness"],  # MatForge-verified; roughness when use_roughness
        SlotRole.METALNESS: ["texmap_metalness", "texmap_reflectionMetalness"],               # MatForge-verified
        SlotRole.REFLECTION_COLOR: ["texmap_reflection"],
        SlotRole.REFRACTION: ["texmap_refraction"],
        SlotRole.BUMP: ["texmap_bump"],
        SlotRole.DISPLACEMENT: ["texmap_displacement"],
        SlotRole.OPACITY: ["texmap_opacity"],
        SlotRole.IOR: ["texmap_reflectionIOR"],
        SlotRole.TRANSLUCENCY: ["texmap_translucent"],
        SlotRole.COAT: ["texmap_coat_amount"],
        SlotRole.SHEEN: ["texmap_sheen"],
    },
    "CoronaPhysicalMtl": {
        SlotRole.BASE_COLOR: ["baseTexmap"],
        SlotRole.ROUGHNESS: ["baseRoughnessTexmap"],
        SlotRole.METALNESS: ["metalnessTexmap"],
        SlotRole.BUMP: ["baseBumpTexmap", "bumpTexmap"],
        SlotRole.DISPLACEMENT: ["displacementTexmap"],
        SlotRole.OPACITY: ["opacityTexmap"],
        SlotRole.IOR: ["baseIorTexmap"],
        SlotRole.REFRACTION: ["refractionAmountTexmap"],
        SlotRole.COAT: ["clearcoatAmountTexmap"],
        SlotRole.SHEEN: ["sheenAmountTexmap"],
    },
    "CoronaLegacyMtl": {
        SlotRole.BASE_COLOR: ["texmapDiffuse"],
        SlotRole.GLOSSINESS: ["texmapReflectGlossiness"],
        SlotRole.BUMP: ["texmapBump"],
        SlotRole.OPACITY: ["texmapOpacity"],
        SlotRole.DISPLACEMENT: ["texmapDisplace"],
    },
}
SLOTS["CoronaMtl"] = SLOTS["CoronaLegacyMtl"]
SLOTS["OpenPBRMaterial"] = {   # ALL UNVERIFIED
    SlotRole.BASE_COLOR: ["base_color_map"],
    SlotRole.ROUGHNESS: ["specular_roughness_map", "roughness_map"],
    SlotRole.METALNESS: ["base_metalness_map", "metalness_map"],
    SlotRole.NORMAL: ["geometry_normal_map", "normal_map"],
    SlotRole.BUMP: ["bump_map"],
    SlotRole.DISPLACEMENT: ["displacement_map", "geometry_displacement_map"],
    SlotRole.OPACITY: ["geometry_opacity_map", "opacity_map", "cutout_map"],
    SlotRole.COAT: ["coat_weight_map"],
    SlotRole.SHEEN: ["fuzz_weight_map"],
    SlotRole.EMISSION: ["emission_color_map"],
}
SLOTS["OpenPBR_Material"] = SLOTS["OpenPBRMaterial"]
SLOTS["OpenPBRSurfaceMaterial"] = SLOTS["OpenPBRMaterial"]

#: Slots that ARE a normal-map input (no separate normal node needed). UNVERIFIED.
NORMAL_INPUT_SLOTS = {c: ["geometry_normal_map", "normal_map"]
                      for c in ("OpenPBRMaterial", "OpenPBR_Material", "OpenPBRSurfaceMaterial")}

# ---------------------------------------------------------------- texmaps
BITMAP_CLASSES = {
    "Bitmaptexture": {"path": ["filename", "fileName"],
                      # 3ds Max 2024+ OCIO colour space of the texture (string). UNVERIFIED.
                      # If absent, the walker falls back to the loaded bitmap's gamma
                      # (see BITMAP_GAMMA) — the path MatForge uses and verified.
                      "color_space": ["colorspace", "colorSpace"]},
    "VRayBitmap": {"path": ["HDRIMapName", "fileName", "filename"],
                   # int: 0 none/linear, 1 inverse gamma, 2 sRGB (VRayHDRI legacy). UNVERIFIED
                   "color_space": ["color_space", "colorSpace", "rgbColorSpace"]},
    "VRayHDRI": {"path": ["HDRIMapName"], "color_space": ["color_space"]},
    "CoronaBitmap": {"path": ["filename", "fileName"],
                     "color_space": ["colorSpace", "gamma"]},
}

#: Bitmaptexture colour handling MatForge verified on Max 2026: data maps are loaded
#: with ``tex.bitmap = openBitMap(path, gamma=1.0)``; colour maps inherit the default
#: input gamma. VRayBitmap's colour_space enum drifts between versions (MatForge note).
BITMAP_GAMMA = {"bitmap_prop": "bitmap", "gamma_prop": "gamma",
                "linear_max": 1.05, "srgb_min": 1.8}

NORMAL_CLASSES = {
    "VRayNormalMap": {"input": ["normal_map", "normalMap"], "flip_green": ["flip_green", "flipGreen"]},
    "CoronaNormal": {"input": ["normalMap", "normal_map"], "flip_green": ["flipgreen", "flipGreen"]},
    "Normal_Bump": {"input": ["normal_map", "normalMap"], "flip_green": ["flipgreen", "flipGreen"]},
}

#: Values meaning "linear / raw" and "sRGB" for each class's colour-space property.
#: Strings are compared case-insensitively. UNVERIFIED.
COLOR_SPACE_VALUES = {
    "Bitmaptexture": {"linear": ["raw", "linear", "scene-linear rec.709-srgb", "utility - raw",
                                 "linear rec.709 (srgb)"],
                      "srgb": ["srgb", "srgb - texture", "utility - srgb - texture", "srgb texture"]},
    "VRayBitmap": {"linear": [0, "none", "linear"], "srgb": [2, "srgb"]},
    "VRayHDRI": {"linear": [0], "srgb": [2]},
    "CoronaBitmap": {"linear": ["linear", 1.0], "srgb": ["srgb", 2.2]},
}

#: 3ds Max "Output" texmap used to invert a map. UNVERIFIED names.
OUTPUT_MAP = {"input": ["map1"], "settings": ["output"], "invert": ["invert"]}

MAX_TEXMAP_DEPTH = 8
