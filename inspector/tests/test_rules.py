import pytest

from material_inspector.core.colour import srgb_luminance_8bit
from material_inspector.core.model import (ColorSpace, MaterialRecord, Renderer, Severity, SlotRole,
                                           TextureRef)
from material_inspector.core.rules import filename_says, inspect_material


def mat(**params):
    textures = params.pop("textures", [])
    renderer = params.pop("renderer", Renderer.VRAY)
    name = params.pop("name", "m")
    return MaterialRecord(name, renderer, "VRayMtl" if renderer == Renderer.VRAY else "CoronaPhysicalMtl",
                          params=params, textures=textures)


def ids(findings, severity=None):
    return sorted(f.rule_id for f in findings if severity is None or f.severity == severity)


def test_clean_material_has_no_findings():
    m = mat(base_color=(0.6, 0.5, 0.4), metalness=0.0, ior=1.5, brdf="ggx", use_roughness=True, roughness=0.4)
    assert ids(inspect_material(m)) == []


@pytest.mark.parametrize("role", [SlotRole.ROUGHNESS, SlotRole.METALNESS, SlotRole.NORMAL,
                                  SlotRole.BUMP, SlotRole.DISPLACEMENT, SlotRole.OPACITY])
def test_data_map_loaded_srgb_is_error_with_fix(role):
    m = mat(textures=[TextureRef(role, "x_map.png", ColorSpace.SRGB, "Bitmaptexture", "bm1")])
    f = [x for x in inspect_material(m) if x.rule_id == "R001"]
    assert f and f[0].severity == Severity.ERROR and f[0].fix.value == "linear"


def test_colour_map_loaded_linear_warns_but_not_for_exr():
    png = mat(textures=[TextureRef(SlotRole.BASE_COLOR, "albedo.png", ColorSpace.LINEAR)])
    exr = mat(textures=[TextureRef(SlotRole.BASE_COLOR, "albedo.exr", ColorSpace.LINEAR)])
    assert "R002" in ids(inspect_material(png))
    assert "R002" not in ids(inspect_material(exr))


def test_unknown_colour_space_is_reported_not_guessed():
    m = mat(textures=[TextureRef(SlotRole.ROUGHNESS, "r.png", ColorSpace.UNKNOWN)])
    f = [x for x in inspect_material(m) if x.rule_id == "R003"]
    assert f and f[0].severity == Severity.INFO and f[0].fix is None


def test_missing_file():
    m = mat(textures=[TextureRef(SlotRole.BASE_COLOR, "gone.png", ColorSpace.SRGB, file_exists=False)])
    assert "R004" in ids(inspect_material(m), Severity.ERROR)


def test_gloss_map_in_roughness_slot_vray_offers_toggle():
    m = mat(use_roughness=True,
            textures=[TextureRef(SlotRole.ROUGHNESS, "Oak_Glossiness_4K.png", ColorSpace.LINEAR)])
    f = [x for x in inspect_material(m) if x.rule_id == "R005"][0]
    assert f.severity == Severity.ERROR and f.fix.kind == "toggle_use_roughness"


def test_rough_map_in_gloss_slot_corona_offers_invert():
    m = mat(renderer=Renderer.CORONA,
            textures=[TextureRef(SlotRole.GLOSSINESS, "tile_rough.jpg", ColorSpace.LINEAR)])
    f = [x for x in inspect_material(m) if x.rule_id == "R005"][0]
    assert f.fix.kind == "invert_map"


def test_correct_roughness_name_not_flagged():
    m = mat(textures=[TextureRef(SlotRole.ROUGHNESS, "Wood049_2K_Roughness.png", ColorSpace.LINEAR)])
    assert "R005" not in ids(inspect_material(m))


def test_normal_map_straight_into_bump():
    m = mat(textures=[TextureRef(SlotRole.BUMP, "brick_NormalGL.png", ColorSpace.LINEAR, via_normal_node=False)])
    assert "R006" in ids(inspect_material(m), Severity.ERROR)


@pytest.mark.parametrize("rgb,expect", [
    ((0.05, 0.05, 0.05), Severity.ERROR),     # ~13 sRGB
    ((0.17, 0.17, 0.17), Severity.WARNING),   # ~43 sRGB
    ((0.98, 0.98, 0.98), Severity.WARNING),   # ~250 sRGB
])
def test_albedo_range(rgb, expect):
    f = [x for x in inspect_material(mat(base_color=rgb, metalness=0.0)) if x.rule_id == "R010"]
    assert f and f[0].severity == expect
    fixed = f[0].fix.value
    lum = srgb_luminance_8bit(fixed)
    assert 49.0 <= lum <= 240.5


def test_albedo_fix_keeps_hue():
    f = [x for x in inspect_material(mat(base_color=(0.10, 0.02, 0.02))) if x.rule_id == "R010"][0]
    r, g, b = f.fix.value
    assert r > g * 2 and abs(g - b) < 1e-6


def test_snow_whitelisted():
    assert "R010" not in ids(inspect_material(mat(name="Fresh_Snow", base_color=(0.98, 0.98, 0.98))))


def test_textured_albedo_skips_swatch_rule():
    m = mat(base_color=(0.01, 0.01, 0.01), textures=[TextureRef(SlotRole.BASE_COLOR, "a.png", ColorSpace.SRGB)])
    assert "R010" not in ids(inspect_material(m))


def test_dark_metal_warns():
    assert "R011" in ids(inspect_material(mat(base_color=(0.3, 0.3, 0.3), metalness=1.0)))


def test_gold_like_metal_passes():
    # gold F0 ~ sRGB (255, 222, 163): blue channel below 180 must NOT be flagged
    assert ids(inspect_material(mat(base_color=(1.0, 0.87, 0.64), metalness=1.0))) == []


def test_half_metal():
    f = [x for x in inspect_material(mat(metalness=0.6)) if x.rule_id == "R012"][0]
    assert f.fix.value == 1.0


@pytest.mark.parametrize("ior,expect", [(0.9, Severity.ERROR), (3.5, Severity.ERROR),
                                        (2.4, Severity.WARNING), (1.52, None)])
def test_ior_tiers(ior, expect):
    f = [x for x in inspect_material(mat(ior=ior)) if x.rule_id == "R013"]
    assert (f[0].severity if f else None) == expect


def test_metal_ior_ignored():
    assert "R013" not in ids(inspect_material(mat(metalness=1.0, base_color=(0.9, 0.9, 0.9), ior=20.0)))


def test_glass_without_absorption_and_thin_walled_exempt():
    assert "R014" in ids(inspect_material(mat(refraction_amount=1.0, refraction_ior=1.52, absorption_color=(1, 1, 1))))
    assert "R014" not in ids(inspect_material(mat(refraction_amount=1.0, thin_walled=True)))
    assert "R014" not in ids(inspect_material(mat(refraction_amount=1.0, absorption_color=(0.85, 0.95, 0.95))))


def test_vray_non_ggx_and_perfect_mirror():
    found = ids(inspect_material(mat(brdf="blinn", use_roughness=False, glossiness=1.0)))
    assert "R015" in found and "R016" in found


def test_legacy_info():
    m = MaterialRecord("old", Renderer.CORONA, "CoronaLegacyMtl", params={"is_legacy": True})
    assert "R017" in ids(inspect_material(m), Severity.INFO)


def test_disabled_rules():
    m = mat(textures=[TextureRef(SlotRole.ROUGHNESS, "r.png", ColorSpace.SRGB)])
    assert "R001" not in ids(inspect_material(m, disabled=["R001"]))


def test_filename_tokens():
    assert filename_says("Metal_Plate_NormalGL.png", "normal")
    assert filename_says("a_gloss.tif", "gloss") and not filename_says("glossary.png", "rough")
