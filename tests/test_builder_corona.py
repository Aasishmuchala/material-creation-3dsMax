"""Corona builder wiring tests — run OFF-Max via the mock pymxs runtime.

Parity with test_builder_logic.py for CoronaPhysicalMtl. Physics values are
read from matphys (never hard-coded F0s), so the tests hold whatever dataset
the tables were sampled from.
"""
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.dirname(os.path.abspath(__file__))
for p in (REPO, TESTS):
    if p not in sys.path:
        sys.path.insert(0, p)

import matphys  # noqa: E402
import mock_pymxs  # noqa: E402
from core.recipes import RECIPES  # noqa: E402

MAPS = {k: "C:/fake/%s.png" % k
        for k in ("albedo", "roughness", "normal", "height", "ao")}
FOLIAGE_MAPS = dict(MAPS, opacity="C:/fake/opacity.png")


def _install(**kw):
    kw.setdefault("renderer", "corona")
    b, rt = mock_pymxs.install(**kw)
    import maxplugin.builder_corona as bc
    return bc, b, rt


def _maps_for(mclass):
    return FOLIAGE_MAPS if RECIPES[mclass].get("opacity") else MAPS


def _misses(b):
    return [l for l in b.LOG if "MISS" in l]


def _close(a, b, tol=1e-3):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


# ---------- every class builds cleanly ----------

@pytest.mark.parametrize("mclass", list(RECIPES))
def test_every_class_builds_corona_without_miss(mclass):
    bc, b, rt = _install()
    mat = bc.build_material(_maps_for(mclass), "C_" + mclass, mclass)
    assert str(rt.classOf(mat)) == "CoronaPhysicalMtl"
    assert mat.props["name"] == "C_" + mclass
    assert not _misses(b), "unexpected MISS for %s: %s" % (mclass, _misses(b))


# ---------- glass ----------

def test_glass_clear_absorption_mm_scene():
    bc, b, rt = _install()
    p = bc.build_material(MAPS, "Glazing", "glass_clear").props
    assert p["refractionAmount"] == 1.0
    assert p["useThinMode"] is True
    assert p["baseIor"] == 1.52
    assert _close(p["volumetricAbsorptionColor"].as_unit(),
                  (0.907, 0.970, 0.970), 0.003)
    assert abs(p["volumetricAbsorptionDistance"] - 6.0) < 1e-9
    assert "opacityTexmap" not in p
    assert "displacementTexmap" not in p


def test_glass_clear_absorption_cm_scene():
    bc, b, rt = _install(system_unit="cm")
    p = bc.build_material(MAPS, "Glazing", "glass_clear").props
    assert abs(p["volumetricAbsorptionDistance"] - 0.6) < 1e-9
    assert _close(p["volumetricAbsorptionColor"].as_unit(),
                  (0.907, 0.970, 0.970), 0.003)


def test_frosted_uses_base_roughness_only():
    bc, b, rt = _install()
    p = bc.build_material(MAPS, "Etched", "glass_frosted").props
    assert p["baseRoughness"] == RECIPES["glass_frosted"]["base_roughness"]
    assert p["refractionAmount"] == 1.0


def test_gemstone_keeps_recipe_fog_as_absorption():
    bc, b, rt = _install()
    p = bc.build_material(MAPS, "Gem", "gemstone").props
    assert p["baseIor"] == 1.80
    assert p["useThinMode"] is False
    assert _close(p["volumetricAbsorptionColor"].as_unit(),
                  RECIPES["gemstone"]["refraction"]["fog_color"], 1e-9)
    assert abs(p["volumetricAbsorptionDistance"] - 10.0) < 1e-9


def test_water_uses_matphys_ior():
    bc, b, rt = _install()
    p = bc.build_material(MAPS, "Pool", "water").props
    assert p["baseIor"] == matphys.glass_ior("water")
    assert abs(p["volumetricAbsorptionDistance"] - 1000.0) < 1e-6


# ---------- foliage ----------

def test_foliage_not_wrapped_translucent_cutout():
    bc, b, rt = _install()
    mat = bc.build_material(FOLIAGE_MAPS, "Leaf", "foliage")
    assert str(rt.classOf(mat)) == "CoronaPhysicalMtl"
    p = mat.props
    assert p["translucencyFraction"] == 0.40
    assert isinstance(p["translucencyColor"], mock_pymxs.MockColor)
    assert "opacityTexmap" in p
    assert p["opacityTexmap"].props["bitmap"].gamma == 1.0
    assert p["opacityCutout"] is True
    assert "refractionAmount" not in p
    assert "useThinMode" not in p


# ---------- metals ----------

def test_chrome_complex_ior():
    bc, b, rt = _install()
    p = bc.build_material(MAPS, "Chrome", "metal_chrome").props
    nk = matphys.metal_nk("chrome")
    assert p["metalnessMode"] == 1
    assert p["useComplexIor"] is True
    assert _close(p["complexIorN"].as_unit(), [c[0] for c in nk], 1e-6)
    assert _close(p["complexIorK"].as_unit(), [c[1] for c in nk], 1e-6)
    assert p["baseTexmapAmount"] == 0.30
    assert "baseTexmap" in p
    assert not _misses(b)


def test_chrome_fallback_without_complex_ior():
    bc, b, rt = _install(drop={"useComplexIor"})
    p = bc.build_material(MAPS, "Chrome", "metal_chrome").props
    assert _close(p["baseColor"].as_unit(), matphys.metal_f0("chrome"))
    assert _close(p["edgeColor"].as_unit(),
                  matphys.metal_edge_tint("chrome"))
    assert "complexIorN" not in p
    miss = _misses(b)
    assert len(miss) == 1 and "complex IOR" in miss[0], miss


@pytest.mark.parametrize("gamma", [True, False])
def test_fallback_swatch_linear_regardless_of_gamma(gamma):
    bc, b, rt = _install(drop={"useComplexIor"}, gamma=gamma)
    p = bc.build_material(MAPS, "Gold", "metal_brushed", metal="gold").props
    assert _close(p["baseColor"].as_unit(), matphys.metal_f0("gold"))


def test_unnamed_metal_uses_base_map_only():
    bc, b, rt = _install()
    p = bc.build_material(MAPS, "Steel", "metal_brushed").props
    assert p["metalnessMode"] == 1
    assert p["baseAnisotropy"] == 0.55
    assert "useComplexIor" not in p
    assert "baseTexmapAmount" not in p
    assert "baseColor" not in p
    assert not _misses(b)


def test_metalness_map_wins_over_named_metal():
    bc, b, rt = _install()
    maps = dict(MAPS, metalness="C:/fake/metalness.png")
    p = bc.build_material(maps, "Patina", "metal_brushed", metal="gold").props
    assert p["metalnessMode"] == 1
    assert p["metalnessTexmap"].props["bitmap"].gamma == 1.0
    assert "useComplexIor" not in p
    assert "baseTexmapAmount" not in p


def test_unknown_metal_raises():
    bc, b, rt = _install()
    with pytest.raises(ValueError):
        bc.build_material(MAPS, "X", "metal_brushed", metal="unobtainium")


def test_dielectric_has_no_metalness_mode():
    bc, b, rt = _install()
    p = bc.build_material(MAPS, "Powder", "metal_painted").props
    assert "metalnessMode" not in p
    assert p["clearcoatAmount"] == 0.35


# ---------- SSS ----------

def test_marble_sss_mm_scene():
    bc, b, rt = _install()
    p = bc.build_material(MAPS, "Carrara", "marble").props
    assert p["volumetricMode"] == 1
    assert abs(p["sssRadius"] - 2.0) < 1e-9
    assert p["sssAmount"] == 0.15
    assert isinstance(p["sssScatterColor"], mock_pymxs.MockColor)
    assert "refractionAmount" not in p


def test_wax_sss_radius_converts_units():
    bc, b, rt = _install(system_unit="cm")
    p = bc.build_material(MAPS, "Candle", "wax").props
    assert abs(p["sssRadius"] - 0.5) < 1e-9
    assert p["sssAmount"] == 0.50


# ---------- displacement ----------

def test_stone_displacement_in_material_mm():
    bc, b, rt = _install()
    p = bc.build_material(MAPS, "Paver", "stone").props
    assert p["displacementTexmap"].props["bitmap"].gamma == 1.0
    assert p["displacementMaximum"] == 3.0
    assert p["displacementMinimum"] == 0.0


def test_stone_displacement_inch_scene():
    bc, b, rt = _install(system_unit="in")
    p = bc.build_material(MAPS, "Paver", "stone").props
    assert abs(p["displacementMaximum"] - 3.0 / 25.4) < 1e-6


def test_no_displacement_without_height_map():
    bc, b, rt = _install()
    maps = {k: v for k, v in MAPS.items() if k != "height"}
    p = bc.build_material(maps, "Paver", "stone").props
    assert "displacementTexmap" not in p
    assert not _misses(b)


def test_assign_adds_no_modifier():
    nodes = mock_pymxs.make_scene_nodes(2)
    bc, b, rt = _install(selection=nodes)
    mat = bc.build_material(MAPS, "Paver", "stone")
    n = bc.assign_to_selection(mat, "stone", height_map="C:/fake/height.png")
    assert n == 2
    for node in nodes:
        assert node.props["material"] is mat
        assert node.modifiers == []
    assert rt.added_modifiers == []
    assert any("displacement lives in the material" in l for l in b.LOG)


def test_assign_empty_selection_is_safe():
    bc, b, rt = _install(selection=[])
    mat = bc.build_material(MAPS, "X", "stone")
    assert bc.assign_to_selection(mat, "stone") == 0


# ---------- normal / colour management ----------

def test_normal_via_corona_normal_linear():
    bc, b, rt = _install()
    p = bc.build_material(MAPS, "X", "generic").props
    nrm = p["baseBumpTexmap"]
    assert str(rt.classOf(nrm)) == "CoronaNormal"
    assert nrm.props["flipGreen"] is False
    assert nrm.props["addGamma"] is False
    assert nrm.props["normalMap"].props["bitmap"].gamma == 1.0
    assert abs(p["baseBumpMapAmount"] - 0.30) < 1e-9   # 30 % / 100


def test_albedo_not_gamma_forced_roughness_linear():
    bc, b, rt = _install()
    p = bc.build_material(MAPS, "X", "generic").props
    base = p["baseTexmap"]
    assert "filename" in base.props and "bitmap" not in base.props
    assert p["baseRoughnessTexmap"].props["bitmap"].gamma == 1.0
    assert p["roughnessMode"] == 0
    assert p["baseRoughness"] == RECIPES["generic"]["base_roughness"]


# ---------- class extras ----------

def test_fabric_sheen_and_leather_clearcoat():
    bc, b, rt = _install()
    fab = bc.build_material(MAPS, "Linen", "fabric").props
    assert fab["sheenAmount"] == 1.0
    assert isinstance(fab["sheenColor"], mock_pymxs.MockColor)
    assert abs(fab["sheenRoughness"] - (1 - 0.55)) < 1e-9
    bc, b, rt = _install()
    lea = bc.build_material(MAPS, "Hide", "leather").props
    assert lea["clearcoatAmount"] == 0.15
    assert abs(lea["clearcoatRoughness"] - (1 - 0.80)) < 1e-9
    assert lea["clearcoatIor"] == 1.5
    assert "sheenColor" in lea


def test_emissive_self_illum():
    bc, b, rt = _install()
    p = bc.build_material(MAPS, "LED", "emissive").props
    assert p["selfIllumLevel"] == 3.0
    assert p["selfIllumColor"].as_unit() == (1.0, 1.0, 1.0)
    assert "bitmap" not in p["selfIllumTexmap"].props   # sRGB albedo


# ---------- opt-in CoronaBitmap / UVW randomizer ----------

def test_corona_bitmap_gamma():
    bc, b, rt = _install()
    p = bc.build_material(MAPS, "X", "generic", use_corona_bitmap=True).props
    rough = p["baseRoughnessTexmap"]
    albedo = p["baseTexmap"]
    assert str(rt.classOf(rough)) == "CoronaBitmap"
    assert rough.props["gamma"] == 1.0
    assert rough.props["filename"] == MAPS["roughness"]
    assert str(rt.classOf(albedo)) == "CoronaBitmap"
    assert albedo.props["gamma"] == 2.2
    assert p["baseBumpTexmap"].props["normalMap"].props["gamma"] == 1.0
    assert "uvwRandomizer" not in rough.props
    assert not _misses(b)


def test_uvw_randomizer_shared_across_maps():
    bc, b, rt = _install()
    p = bc.build_material(MAPS, "X", "generic", use_corona_bitmap=True,
                          uvw_randomizer=True).props
    rnd = p["baseTexmap"].props["uvwRandomizer"]
    assert str(rt.classOf(rnd)) == "CoronaUvwRandomizer"
    assert p["baseRoughnessTexmap"].props["uvwRandomizer"] is rnd
    assert not _misses(b)


def test_uvw_randomizer_ignored_without_corona_bitmap():
    bc, b, rt = _install()
    p = bc.build_material(MAPS, "X", "generic", uvw_randomizer=True).props
    assert str(rt.classOf(p["baseTexmap"])) == "Bitmaptexture"
    assert any("uvw randomizer needs CoronaBitmap" in l for l in b.LOG)


# ---------- defensive fallback ----------

def test_dropped_property_logs_miss_but_still_builds():
    bc, b, rt = _install(drop={"useThinMode"})
    mat = bc.build_material(MAPS, "Glazing", "glass_clear")
    assert str(rt.classOf(mat)) == "CoronaPhysicalMtl"
    assert "refractionAmount" in mat.props
    assert any("thin mode" in l for l in _misses(b))


def test_reload_rebinds_to_fresh_runtime():
    """install() twice: the Corona builder must use the NEW runtime/LOG."""
    bc, b1, rt1 = _install()
    bc, b2, rt2 = _install(system_unit="cm")
    p = bc.build_material(MAPS, "Paver", "stone").props
    assert abs(p["displacementMaximum"] - 0.3) < 1e-9
    assert b2.LOG and b2.LOG[0].startswith("building 'Paver'")
