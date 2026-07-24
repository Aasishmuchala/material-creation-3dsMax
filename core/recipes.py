"""Material recipe table — the deterministic heart of MatForge.

Every value here is a physical constant or a studio-standard convention,
never an AI guess. Class recipes drive both map derivation (core/maps.py)
and V-Ray wiring (maxplugin/builder.py).

Units:
  * ior           dimensionless
  * bump_amount   VRayMtl bump *percentage*, 0-100 scale (V-Ray default 30,
                  ~100 = full strength). NOT a 0-1 multiplier — 0.3 would be
                  ~0.3% bump, i.e. effectively flat. Verified against Chaos
                  docs / forum ("Default value of bumps", default 30).
  * displacement_mm  world-unit height fed to the VRayDisplacementMod .amount
                     (applied per-object on assign, not via the material's
                     displacement percentage). 0 = no displacement.
Colors are 0-1 RGB floats.
"""

RESOLUTIONS = {"2k": 2048, "4k": 4096, "8k": 8192}

# Fresnel IOR for dielectrics is ~1.5 across the board; refraction IOR only
# matters for transmissive classes. Metals use metalness=1 + reflect color.
RECIPES = {
    "wood_interior": {
        "label": "Wood (interior / lacquered)",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.45, "roughness_variation": 0.20,
        "bump_amount": 30.0, "displacement_mm": 0.8,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": {"amount": 0.25, "glossiness": 0.92},
        "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "wood_exterior": {
        "label": "Wood (exterior / weathered)",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.65, "roughness_variation": 0.30,
        "bump_amount": 45.0, "displacement_mm": 1.5,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "concrete": {
        "label": "Concrete / plaster",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.75, "roughness_variation": 0.15,
        "bump_amount": 40.0, "displacement_mm": 2.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "stone": {
        "label": "Stone / paver / brick",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.70, "roughness_variation": 0.20,
        "bump_amount": 50.0, "displacement_mm": 3.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "marble": {
        "label": "Marble / polished stone",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.12, "roughness_variation": 0.08,
        "bump_amount": 10.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        # thin translucency sells marble; wired as VRayMtl translucency
        "translucency": {"color": (0.93, 0.91, 0.88), "amount": 0.15},
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "metal_brushed": {
        "label": "Metal (brushed / raw)",
        "ior": 1.5, "metalness": 1.0,
        "base_roughness": 0.35, "roughness_variation": 0.15,
        "bump_amount": 20.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "anisotropy": 0.55,
        "coat": None, "sheen": None, "self_illum": False,
        # albedo map drives the tint for metals
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "metal_painted": {
        "label": "Metal (painted / powder-coated)",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.40, "roughness_variation": 0.10,
        "bump_amount": 15.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": {"amount": 0.35, "glossiness": 0.90},
        "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "glass_clear": {
        "label": "Glass (clear / glazing)",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.02, "roughness_variation": 0.02,
        "bump_amount": 4.0, "displacement_mm": 0.0,
        # fog is deliberately near-white with a tiny multiplier — the
        # saturated-fog trap turns glass into opaque paint.
        "refraction": {"ior": 1.52, "thin_walled": True,
                       "fog_color": (0.98, 1.0, 0.985), "fog_mult": 0.05,
                       "affect_shadows": True},
        "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "fabric": {
        "label": "Fabric / linen / upholstery",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.85, "roughness_variation": 0.10,
        "bump_amount": 35.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "sheen": {"color": (0.85, 0.85, 0.85), "glossiness": 0.55},
        "coat": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "leather": {
        "label": "Leather",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.50, "roughness_variation": 0.20,
        "bump_amount": 40.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": {"amount": 0.15, "glossiness": 0.80},
        "sheen": {"color": (0.6, 0.6, 0.6), "glossiness": 0.45},
        "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "paint_wall": {
        "label": "Painted wall",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.70, "roughness_variation": 0.08,
        "bump_amount": 12.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "foliage": {
        "label": "Foliage / leaves",
        "ior": 1.45, "metalness": 0.0,
        "base_roughness": 0.35, "roughness_variation": 0.20,
        "bump_amount": 25.0, "displacement_mm": 0.0,
        # NO refraction — thin-surface translucency via VRay2SidedMtl.
        "refraction": None,
        "two_sided": {"translucency": (0.55, 0.68, 0.38), "amount": 0.40},
        # clip-mode opacity: binary cutout, several-x faster than smooth
        "opacity": True,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },

    # ---- STONE / MASONRY ----
    "granite": {
        "label": "Granite / terrazzo (polished)",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.18, "roughness_variation": 0.10,
        "bump_amount": 12.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "concrete_polished": {
        "label": "Concrete (polished / microcement)",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.30, "roughness_variation": 0.12,
        "bump_amount": 15.0, "displacement_mm": 0.3,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "terracotta": {
        "label": "Terracotta / clay / unglazed brick",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.62, "roughness_variation": 0.18,
        "bump_amount": 45.0, "displacement_mm": 1.5,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },

    # ---- CERAMIC / GLASS / TRANSMISSIVE ----
    "ceramic_glazed": {
        "label": "Ceramic / porcelain (glazed tile)",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.08, "roughness_variation": 0.05,
        "bump_amount": 6.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": {"amount": 0.40, "glossiness": 0.97},
        "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "glass_frosted": {
        "label": "Glass (frosted / etched)",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.30, "roughness_variation": 0.05,
        "bump_amount": 6.0, "displacement_mm": 0.0,
        "refraction": {"ior": 1.52, "thin_walled": True,
                       "fog_color": (0.98, 1.0, 0.99), "fog_mult": 0.04,
                       "affect_shadows": True, "glossiness": 0.60},
        "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "gemstone": {
        "label": "Gemstone / crystal",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.02, "roughness_variation": 0.02,
        "bump_amount": 2.0, "displacement_mm": 0.0,
        "refraction": {"ior": 1.80, "thin_walled": False,
                       "fog_color": (0.97, 0.99, 1.0), "fog_mult": 0.06,
                       "affect_shadows": True},
        "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "water": {
        "label": "Water / liquid",
        "ior": 1.33, "metalness": 0.0,
        "base_roughness": 0.02, "roughness_variation": 0.02,
        "bump_amount": 8.0, "displacement_mm": 0.0,
        "refraction": {"ior": 1.33, "thin_walled": False,
                       "fog_color": (0.96, 0.99, 1.0), "fog_mult": 0.02,
                       "affect_shadows": True},
        "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },

    # ---- METAL ----
    "metal_chrome": {
        "label": "Metal (chrome / mirror polished)",
        "ior": 1.5, "metalness": 1.0,
        "base_roughness": 0.03, "roughness_variation": 0.02,
        "bump_amount": 4.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "metal_satin": {
        "label": "Metal (satin / stainless steel)",
        "ior": 1.5, "metalness": 1.0,
        "base_roughness": 0.20, "roughness_variation": 0.08,
        "bump_amount": 8.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "metal_rust": {
        "label": "Metal (rusted / corten steel)",
        "ior": 1.5, "metalness": 0.25,
        "base_roughness": 0.65, "roughness_variation": 0.25,
        "bump_amount": 40.0, "displacement_mm": 0.5,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "car_paint": {
        "label": "Car paint (metallic + clearcoat)",
        "ior": 1.5, "metalness": 0.85,
        "base_roughness": 0.30, "roughness_variation": 0.05,
        "bump_amount": 3.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": {"amount": 0.70, "glossiness": 0.98},
        "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },

    # ---- PLASTIC / RUBBER ----
    "plastic_glossy": {
        "label": "Plastic (glossy)",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.12, "roughness_variation": 0.05,
        "bump_amount": 6.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "plastic_matte": {
        "label": "Plastic (matte)",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.55, "roughness_variation": 0.08,
        "bump_amount": 8.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "rubber": {
        "label": "Rubber",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.80, "roughness_variation": 0.08,
        "bump_amount": 20.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },

    # ---- SOFT / TEXTILE ----
    "velvet": {
        "label": "Velvet",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.90, "roughness_variation": 0.05,
        "bump_amount": 15.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "sheen": {"color": (0.70, 0.70, 0.70), "glossiness": 0.30},
        "coat": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "carpet": {
        "label": "Carpet / rug",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.92, "roughness_variation": 0.10,
        "bump_amount": 55.0, "displacement_mm": 1.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "sheen": {"color": (0.50, 0.50, 0.50), "glossiness": 0.40},
        "coat": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },

    # ---- MISC ARCHITECTURAL / ORGANIC / SPECIAL ----
    "paper": {
        "label": "Paper / cardboard",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.72, "roughness_variation": 0.10,
        "bump_amount": 10.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "cork": {
        "label": "Cork",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.68, "roughness_variation": 0.15,
        "bump_amount": 35.0, "displacement_mm": 0.5,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "asphalt": {
        "label": "Asphalt / tarmac",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.82, "roughness_variation": 0.12,
        "bump_amount": 45.0, "displacement_mm": 1.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "sand": {
        "label": "Sand / gravel / soil",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.90, "roughness_variation": 0.15,
        "bump_amount": 60.0, "displacement_mm": 2.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "wax": {
        "label": "Wax / candle / soap (SSS)",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.35, "roughness_variation": 0.10,
        "bump_amount": 10.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "translucency": {"color": (0.95, 0.90, 0.80), "amount": 0.50},
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "emissive": {
        "label": "Emissive / LED panel",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.50, "roughness_variation": 0.10,
        "bump_amount": 0.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None,
        "self_illum": {"multiplier": 3.0},
        "reflect_color": (1.0, 1.0, 1.0),
    },

    "generic": {
        "label": "Generic dielectric",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.55, "roughness_variation": 0.20,
        "bump_amount": 30.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
}

# Physical reference constants kept alongside for future classes / validation.
IOR_TABLE = {
    "water": 1.33, "ice": 1.31, "glass_window": 1.52, "glass_crystal": 1.62,
    "acrylic": 1.49, "diamond": 2.42, "sapphire": 1.77, "olive_oil": 1.47,
}

METAL_TINTS = {
    "gold": (1.00, 0.78, 0.34), "silver": (0.97, 0.96, 0.91),
    "copper": (0.95, 0.64, 0.54), "aluminum": (0.91, 0.92, 0.92),
    "iron": (0.56, 0.57, 0.58),
}


def get_recipe(mclass):
    if mclass not in RECIPES:
        raise KeyError(
            f"Unknown material class '{mclass}'. Valid: {', '.join(RECIPES)}")
    return RECIPES[mclass]


def class_choices():
    """(key, label) pairs in stable order for UI dropdowns."""
    return [(k, v["label"]) for k, v in RECIPES.items()]
