"""Physics-backed rules: R018 metal F0, RuleConfig defaults from matphys, V-Ray fog fix."""
import pytest

from material_inspector.core import colour
from material_inspector.core.model import ColorSpace, Finding, MaterialRecord, Renderer, SlotRole, TextureRef
from material_inspector.core.physics import matphys
from material_inspector.core.rules import (DEFAULT_CONFIG, RuleConfig, glass_without_absorption,
                                           inspect_material, metal_from_name)
from material_inspector.max_adapter.fixes import FixApplier
from material_inspector.max_adapter.scene import SceneReader
from tests.fakert import Color, FakeRT, Node
from tests.test_rules import ids, mat


def r018(m):
    return [f for f in inspect_material(m) if f.rule_id == "R018"]


def test_shim_exposes_shared_package():
    assert matphys.metal_f0 is not None
    assert colour.scale_to_luminance is matphys.colour.scale_to_luminance


def test_named_metal_at_measured_f0_passes():
    # swatches are stored scene-linear: the measured F0 itself is the right value
    m = mat(name="Brushed_Gold", base_color=matphys.metal_f0("gold"), metalness=1.0)
    assert r018(m) == []


@pytest.mark.parametrize("key", sorted(matphys.METALS))
def test_matforge_linear_f0_is_clean_for_every_metal(key):
    # what the builders write (linear F0) must not trip R011 or R018
    tok = {"stainless_steel": "Stainless", "aluminium": "Aluminium"}.get(key, key.title())
    m = mat(name=tok + "_Part", base_color=matphys.metal_f0(key), metalness=1.0)
    assert not {"R011", "R018"} & set(ids(inspect_material(m)))


def test_display_encoded_chrome_is_flagged():
    # the old (wrong) display-encoded chrome swatch, 0.556 -> 0.771, is now off-F0
    enc = matphys.rgb_to_srgb(matphys.metal_f0("chrome"))
    assert len(r018(mat(name="Chrome_Tap", base_color=enc, metalness=1.0))) == 1


def test_unnamed_gold_like_metal_still_clean():
    # same fixture as test_rules.test_gold_like_metal_passes: no metal token in the name
    assert ids(inspect_material(mat(base_color=(1.0, 0.87, 0.64), metalness=1.0))) == []


def test_wrong_gold_colour_warns_with_f0_fix():
    f = r018(mat(name="Gold_Trim", base_color=(0.9, 0.9, 0.2), metalness=1.0))
    assert len(f) == 1 and f[0].severity.value == "warning"
    assert "Gold" in f[0].message
    fx = f[0].fix
    assert fx.kind == "set_param" and fx.target == "base_color"
    for a, b in zip(fx.value, matphys.metal_f0("gold")):   # fix writes linear F0
        assert abs(a - b) < 1e-6


def test_painted_steel_is_not_metal():
    assert r018(mat(name="Steel_Painted", base_color=(0.2, 0.3, 0.8), metalness=0.0)) == []


def test_complex_ior_skips_r018():
    assert r018(mat(name="Gold_Trim", base_color=(0.9, 0.9, 0.2), metalness=1.0, complex_ior=True)) == []


def _corona_rail(complex_ior):
    m = Node("CoronaPhysicalMtl", "Chrome_Rail", baseColor=Color(60, 60, 60), baseRoughness=0.1,
             metalnessMode=1, useComplexIor=complex_ior)
    return SceneReader(FakeRT([m])).materials()[0]


def test_corona_complex_ior_read_from_scene_skips_r011_r018():
    rec = _corona_rail(True)
    assert rec.params["complex_ior"] is True
    assert not {"R011", "R018"} & set(ids(inspect_material(rec)))


def test_corona_without_complex_ior_grey_chrome_flagged():
    rec = _corona_rail(False)
    assert rec.params["complex_ior"] is False
    found = set(ids(inspect_material(rec)))
    assert {"R011", "R018"} <= found


def test_textured_metal_skips_r018():
    tex = [TextureRef(SlotRole.BASE_COLOR, "gold_albedo.png", ColorSpace.SRGB)]
    assert r018(mat(name="Gold_Trim", base_color=(0.9, 0.9, 0.2), metalness=1.0, textures=tex)) == []


@pytest.mark.parametrize("renderer", [Renderer.VRAY, Renderer.CORONA, Renderer.OPENPBR])
def test_r018_is_renderer_neutral(renderer):
    m = MaterialRecord("Copper_Pipe", renderer, "X", params={"base_color": (0.5, 0.5, 0.5), "metalness": 1.0})
    assert [f.rule_id for f in inspect_material(m)].count("R018") == 1


@pytest.mark.parametrize("name,key", [("Alu_Panel", "aluminium"), ("brushed-aluminum", "aluminium"),
                                      ("Inox Sink", "stainless_steel"), ("ChromiumTap", None),
                                      ("chromium tap", "chrome"), ("value_grey", None),
                                      ("Gold_Steel", "gold")])
def test_metal_token_matching(name, key):
    assert metal_from_name(name) == key


def test_every_token_targets_a_known_metal():
    from material_inspector.core.rules import METAL_TOKENS
    assert set(METAL_TOKENS.values()) <= set(matphys.METALS)


def test_config_defaults_flow_from_matphys():
    cfg = RuleConfig()
    assert cfg.soda_lime_absorption == (0.85, 0.95, 0.95)
    assert cfg.albedo_ceiling == 240.0 == matphys.ALBEDO_CEILING
    assert cfg.albedo_floor_error == matphys.ALBEDO_FLOOR_ERROR
    assert cfg.albedo_floor_strict == matphys.ALBEDO_FLOOR_STRICT
    assert cfg.bright_whitelist == tuple(matphys.BRIGHT_WHITELIST)
    assert cfg.metal_f0_tolerance == 0.10


def test_vray_fog_fix_uses_matphys_conversion():
    glass = Node("VRayMtl", "Bottle", refraction_fogColor=Color(255, 255, 255), refraction_fogMult=1.0)
    rt = FakeRT([glass])
    rt.units.SystemType = "#centimeters"
    rec = MaterialRecord("Bottle", Renderer.VRAY, "VRayMtl", handle=glass,
                         params={"refraction_amount": 1.0, "absorption_color": (1.0, 1.0, 1.0)})
    f = glass_without_absorption(rec, DEFAULT_CONFIG)[0]
    assert FixApplier(rt).apply(f, rec).ok
    c = glass._props["refraction_fogColor"]
    sigma = matphys.glass_sigma_mm("soda_lime")
    fog, mult = matphys.to_vray_fog(sigma, 10.0, 10.0)
    for got, want, exp in zip((c.r, c.g, c.b), fog, (0.85, 0.95, 0.95)):
        assert abs(got / 255.0 - want) < 1e-3 and abs(want - exp) < 2e-3
    assert abs(glass._props["refraction_fogMult"] - mult) < 1e-9 and abs(mult - 1.0) < 1e-9
