"""CoronaPhysicalMtl / CoronaNormal / CoronaBitmap MAXScript property names.

STATUS: ALL UNVERIFIED against Corona 14/15. Names come from public Corona
MAXScript docs and community scripts; none has been read off a live
`showProperties (CoronaPhysicalMtl())` yet. The FIRST candidate of every list
is the name the mock runtime (tests/mock_pymxs.py) answers to, and the name the
Inspector's props table (inspector/material_inspector/max_adapter/props.py)
expects first. Candidates may be appended after the first; never reorder or
remove. Every key here has a row in docs/VERIFY_CORONA.md.
"""

CORONA_MTL = {
    "base_color": ["baseColor", "basecolor", "colorBase"],
    "base_texmap": ["baseTexmap", "texmapBase"],
    # 0-1 or 0-100? VERIFY; builder writes 0.30 then logs the value written
    "base_texmap_amount": ["baseTexmapAmount", "baseMapAmount"],
    "roughness_mode": ["roughnessMode", "glossinessMode"],   # 0 = roughness VERIFY
    "roughness": ["baseRoughness", "roughness"],
    "roughness_texmap": ["baseRoughnessTexmap", "roughnessTexmap"],
    "ior": ["baseIor", "ior"],
    "metalness_mode": ["metalnessMode", "metalMode"],        # 1 = metal VERIFY
    "metalness_texmap": ["metalnessTexmap", "metalnessModeTexmap"],
    "complex_ior_on": ["useComplexIor", "complexIorEnabled", "metalComplexIor"],
    # written as rt.Color via _color(n_rgb)  VERIFY type/scale
    "complex_ior_n": ["complexIorN", "iorN", "metalN"],
    "complex_ior_k": ["complexIorK", "iorK", "metalK"],
    "edge_color": ["edgeColor", "metalEdgeColor", "baseEdgeColor"],
    "anisotropy": ["baseAnisotropy", "anisotropy"],
    "refraction_amount": ["refractionAmount", "refractAmount"],
    "thin_mode": ["useThinMode", "thinMode", "refractionThin"],
    "absorption_color": ["volumetricAbsorptionColor", "absorptionColor"],
    "absorption_distance": ["volumetricAbsorptionDistance",
                            "absorptionDistance"],
    "sss_mode": ["volumetricMode", "sssMode", "scatteringMode"],  # 1 VERIFY
    "sss_amount": ["sssAmount"],
    "sss_radius": ["sssRadius"],
    "sss_color": ["sssScatterColor", "sssColor"],
    "translucency_fraction": ["translucencyFraction", "translucencyAmount"],
    "translucency_color": ["translucencyColor"],
    "clearcoat_amount": ["clearcoatAmount"],
    "clearcoat_roughness": ["clearcoatRoughness"],
    "clearcoat_ior": ["clearcoatIor"],
    "sheen_amount": ["sheenAmount"],
    "sheen_color": ["sheenColor"],
    "sheen_roughness": ["sheenRoughness"],
    "opacity_texmap": ["opacityTexmap"],
    "opacity_cutout": ["opacityCutout", "opacityClip"],
    "bump_texmap": ["baseBumpTexmap", "bumpTexmap"],
    # recipe bump_amount / 100  VERIFY scale
    "bump_amount": ["baseBumpMapAmount", "bumpAmount"],
    "displacement_texmap": ["displacementTexmap"],
    "displacement_min": ["displacementMinimum", "displacementMin"],
    "displacement_max": ["displacementMaximum", "displacementMax"],
    "self_illum_level": ["selfIllumLevel"],
    "self_illum_color": ["selfIllumColor"],
    "self_illum_texmap": ["selfIllumTexmap"],
}

CORONA_NORMAL = {
    "input": ["normalMap", "normal_map"],
    "flip_green": ["flipGreen", "flipgreen", "flip_green"],
    "add_gamma": ["addGamma"],
}

CORONA_BITMAP = {
    "filename": ["filename", "fileName"],
    "gamma": ["gamma"],
    "uvw": ["uvwRandomizer", "uvw", "mapping"],
}

# Names confirmed on a live Corona build (empty until the Windows session).
VERIFIED = frozenset()

# Integer enum values the builder writes; each is a VERIFY row.
ENUM_ASSUMPTIONS = {"roughness_mode": 0, "metalness_mode": 1, "sss_mode": 1}
