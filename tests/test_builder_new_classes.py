"""Plugin-side material classes and features added from the apartment renders
and the Pinterest-grade reference study: lacquered floor boards, solid glass
objects, sheer two-sided fabric, boucle with loop relief, velvet sheen in the
fibre's own hue with crushed-pile mottling, and per-board tint variants. Run
off-Max through the mock pymxs runtime."""
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.dirname(os.path.abspath(__file__))
for p in (REPO, TESTS):
    if p not in sys.path:
        sys.path.insert(0, p)

import mock_pymxs  # noqa: E402
from core.recipes import CLASS_GROUPS, RECIPES  # noqa: E402

MAPS = {k: "C:/fake/%s.png" % k for k in ("albedo", "roughness", "normal", "height", "ao")}
EMERALD = (0.005, 0.056, 0.027)          # velvet_sofa's measured linear albedo mean


def _unit(c):
    return tuple(round(x, 4) for x in c.as_unit())


@pytest.mark.parametrize("key", ["wood_floor", "wood_floor_oiled", "glass_object", "fabric_sheer", "fabric_voile",
                                 "boucle", "foliage_thick", "canvas_waxed", "stone_honed", "ceramic_matte"])
def test_new_classes_are_registered_and_listed(key):
    assert key in RECIPES
    assert any(key in keys for _, keys in CLASS_GROUPS)


def test_glass_object_refracts_as_solid_glass():
    b, _ = mock_pymxs.install()
    mat = b.build_material(MAPS, "Vase", "glass_object")
    assert mat.props.get("refraction_thinWalled") is not True
    assert _unit(mat.props["refraction"]) == (1.0, 1.0, 1.0)     # absorption is fog, not a tint
    fog = _unit(mat.props["refraction_fogColor"])
    assert min(fog) > 0.97 and max(fog) - min(fog) < 0.01        # low-iron: near neutral
    assert mat.props["refraction_affectShadows"] is True


def test_pane_glass_stays_thin_walled():
    b, _ = mock_pymxs.install()
    mat = b.build_material(MAPS, "Pane", "glass_clear")
    assert mat.props["refraction_thinWalled"] is True


def test_sheer_fabric_glows_in_its_own_colour():
    b, _ = mock_pymxs.install()
    mat = b.build_material(MAPS, "Curtain", "fabric_sheer")
    assert mat.cls == "VRay2SidedMtl"
    assert _unit(mat.props["translucency"]) == pytest.approx((0.45, 0.45, 0.45), abs=1e-3)
    assert mat.props["mult_by_front_diffuse"] is True


def test_voile_lets_the_window_show_through():
    """A voile is an open weave: part of the light goes straight through the
    gaps (thin-walled, unbent, sharp, casting light) while the threads glow
    through the two-sided wrap. With translucency alone it was an opaque
    white sheet. A lamp shade's denser cloth (fabric_sheer) stays opaque."""
    assert any("fabric_voile" in keys for _, keys in CLASS_GROUPS)
    b, _ = mock_pymxs.install()
    front = b.build_material(MAPS, "Curtain", "fabric_voile").props["frontMtl"]
    see = RECIPES["fabric_voile"]["see_through"]
    assert 0.3 <= see <= 0.75
    assert _unit(front.props["refraction"]) == pytest.approx((see, see, see), abs=3e-3)
    assert front.props["refraction_thinWalled"] is True
    assert front.props["refraction_glossiness"] > 0.85           # a glossiness: near 1 is a clear view
    assert front.props["refraction_affectShadows"] is True
    for key in ("fabric_sheer", "fabric"):                       # shades and cloth: no see-through
        mat = b.build_material(MAPS, "Shade", key)
        front = mat.props.get("frontMtl", mat)
        assert "refraction" not in front.props, key


def test_corona_voile_lets_the_window_show_through():
    mock_pymxs.install()
    import maxplugin.builder_corona as bc
    mat = bc.build_material(MAPS, "Curtain", "fabric_voile")
    assert mat.props["refractionAmount"] == pytest.approx(RECIPES["fabric_voile"]["see_through"])
    assert mat.props["useThinMode"] is True
    shade = bc.build_material(MAPS, "Shade", "fabric_sheer")
    assert "refractionAmount" not in shade.props


def test_thick_leaves_pass_less_light_and_oiled_boards_sheen_softly():
    """Banana and rubber-plant blades: a thick waxy blade passes far less
    light than a thin leaf (at 0.40 a north window lit them lime from
    behind) and keeps its cut-out. Oiled boards: a broad glancing sheen, not
    the lacquer's crisp window streaks."""
    b, _ = mock_pymxs.install()
    maps = dict(MAPS, opacity="C:/fake/opacity.png")
    thick = b.build_material(maps, "Banana", "foliage_thick")
    thin = b.build_material(maps, "Olive", "foliage")
    assert thick.cls == thin.cls == "VRay2SidedMtl"
    assert max(_unit(thick.props["translucency"])) < 0.5 * max(_unit(thin.props["translucency"]))
    assert "texmap_opacity" in thick.props["frontMtl"].props
    oiled = RECIPES["wood_floor_oiled"]["coat"]
    lacquer = RECIPES["wood_floor"]["coat"]
    assert oiled["amount"] < lacquer["amount"] and oiled["glossiness"] < lacquer["glossiness"]


def test_foliage_wrap_is_unchanged():
    b, _ = mock_pymxs.install()
    mat = b.build_material(dict(MAPS, opacity="C:/fake/opacity.png"), "Leaf", "foliage")
    assert mat.cls == "VRay2SidedMtl"
    assert "mult_by_front_diffuse" not in mat.props


def _light_hue(mean, lum=0.28, desat=0.35):
    k = lum / (0.2126 * mean[0] + 0.7152 * mean[1] + 0.0722 * mean[2])
    return tuple(min(0.9, (1 - desat) * k * c + desat * lum) for c in mean)


def test_velvet_sheen_takes_the_fibre_hue_and_mottles():
    b, _ = mock_pymxs.install()
    mat = b.build_material(MAPS, "Velvet", "velvet", albedo_mean=EMERALD)
    want = _light_hue(EMERALD)
    # a mint well above the body colour (R 0.005, G 0.056), not a whitish film
    assert want[1] > want[2] > want[0] > 10 * EMERALD[0] and 0.25 < want[1] < 0.45
    assert _unit(mat.props["sheen_color"]) == pytest.approx(want, abs=2e-3)
    nz = mat.props["texmap_sheen"]
    assert nz.cls == "Noise" and nz.props["type"] == 1
    assert nz.props["size"] == pytest.approx(250.0)            # 25 cm in a mm scene
    assert _unit(nz.props["color1"]) == pytest.approx(tuple(0.75 * c for c in want), abs=2e-3)
    assert _unit(nz.props["color2"]) == pytest.approx(tuple(1.25 * c for c in want), abs=2e-3)
    assert mat.props["sheen_glossiness"] == pytest.approx(1.0 - RECIPES["velvet"]["sheen"]["glossiness"])


def test_velvet_falls_back_to_the_recipe_colour_when_the_albedo_cannot_be_read():
    b, _ = mock_pymxs.install()
    mat = b.build_material(dict(MAPS, sheen="C:/fake/sheen.png"), "Velvet", "velvet")
    assert _unit(mat.props["sheen_color"]) == pytest.approx((0.7, 0.7, 0.7), abs=2e-3)
    assert mat.props["texmap_sheen"].cls != "Noise"          # the forged sheen map instead


def test_sheen_from_albedo_lifts_to_the_luminance_and_desaturates():
    b, _ = mock_pymxs.install()
    sh = b.sheen_from_albedo(EMERALD, 0.45, 0.5)
    lum = 0.2126 * sh[0] + 0.7152 * sh[1] + 0.0722 * sh[2]
    assert lum == pytest.approx(0.45, abs=0.01)
    assert b.sheen_from_albedo(EMERALD, 0.45, 1.0) == pytest.approx((0.45, 0.45, 0.45))
    assert max(b.sheen_from_albedo((0.9, 0.05, 0.01), 0.45, 0.0)) == pytest.approx(0.9)   # capped


def test_velvet_albedo_is_pulled_back_into_gamut():
    b, _ = mock_pymxs.install()
    mat = b.build_material(MAPS, "Velvet", "velvet", albedo_mean=EMERALD)
    nap = mat.props["texmap_diffuse"]
    cc = nap.props["map1"]                  # face on: the corrected albedo
    assert cc.cls == "ColorCorrection"
    assert cc.props["saturation"] < 0 and cc.props["brightness"] > 0
    lin = b.build_material(MAPS, "Linen", "fabric")
    assert lin.props["texmap_diffuse"].cls != "ColorCorrection"     # only where the recipe asks


def test_velvet_is_lighter_seen_across_the_pile():
    """Soft frontal light leaves the sheen lobe nothing to answer and velvet
    rendered as flat felt: the albedo now sits in a view falloff, itself face
    on and a lifted fibre colour at grazing view, squared (nested twice)."""
    b, _ = mock_pymxs.install()
    mat = b.build_material(MAPS, "Velvet", "velvet", albedo_mean=EMERALD)
    outer = mat.props["texmap_diffuse"]
    assert outer.cls == "Falloff" and outer.props["type"] == 1
    inner = outer.props["map2"]
    assert inner.cls == "Falloff" and inner.props["map1"] is outer.props["map1"]
    side = _unit(inner.props["color2"])
    lum = lambda c: 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    assert lum(side) == pytest.approx(min(0.6, 3.5 * lum(EMERALD)), rel=0.02)
    assert side[1] > side[2] > side[0]                      # still emerald
    assert any("pile nap" in line for line in b.LOG)
    lin = b.build_material(MAPS, "Linen", "fabric")
    assert lin.props["texmap_diffuse"].cls != "Falloff"     # a flat weave has no nap


def test_linen_keeps_its_recipe_sheen():
    b, _ = mock_pymxs.install()
    mat = b.build_material(MAPS, "Linen", "fabric", albedo_mean=(0.5, 0.4, 0.3))
    assert _unit(mat.props["sheen_color"]) == pytest.approx((0.85, 0.85, 0.85), abs=2e-3)


def test_corona_velvet_sheen_takes_the_fibre_hue(monkeypatch):
    b, _ = mock_pymxs.install()
    import maxplugin.builder_corona as bc
    monkeypatch.setattr(bc._vb, "_albedo_mean", lambda path: EMERALD)
    mat = bc.build_material(MAPS, "Velvet", "velvet")
    want = _light_hue(EMERALD)
    sheen = [v for k, v in mat.props.items() if k.lower().startswith("sheencolor")]
    assert sheen and _unit(sheen[0]) == pytest.approx(want, abs=2e-3)


def test_wood_floor_is_lacquered():
    b, _ = mock_pymxs.install()
    mat = b.build_material(MAPS, "Boards", "wood_floor")
    assert mat.props["coat_amount"] == pytest.approx(0.75)
    assert RECIPES["wood_floor"]["displacement_mm"] == 0.0     # bevels are geometry


def test_boucle_gets_loop_relief():
    nodes = mock_pymxs.make_scene_nodes(1)
    b, rt = mock_pymxs.install(selection=nodes)
    mat = b.build_material(MAPS, "Boucle", "boucle")
    b.assign_to_selection(mat, "boucle", height_map=MAPS["height"])
    mods = [m for _, m in rt.added_modifiers if m.cls == "VRayDisplacementMod"]
    assert len(mods) == 1 and mods[0].props["amount"] == pytest.approx(3.5)


def test_variants_tint_copies_and_keep_the_base_first():
    b, _ = mock_pymxs.install()
    mat = b.build_material(MAPS, "Boards", "wood_floor")
    tints = ((0, 0, 0), (-4, 3, 1), (3, -4, -1))
    mm = b.build_variants(mat, tints)
    subs = mm.props["subs"]
    assert mm.cls == "MultiMaterial" and len(subs) == 3 and subs[0] is mat
    src = mat.props["texmap_diffuse"]
    for sub, (bri, sat, hue) in zip(subs[1:], tints[1:]):
        cc = sub.props["texmap_diffuse"]
        assert cc.cls == "ColorCorrection" and cc.props["map"] is src
        assert (cc.props["brightness"], cc.props["saturation"], cc.props["hueShift"]) == (bri, sat, hue)
    assert mat.props["texmap_diffuse"] is src                  # the base itself untouched


def test_variants_leave_a_material_without_albedo_alone():
    b, _ = mock_pymxs.install()
    mat = b.build_material({"roughness": MAPS["roughness"]}, "Bare", "generic")
    assert b.build_variants(mat, ((0, 0, 0), (5, 0, 0))) is mat


def test_leather_sheen_is_a_faint_colour_not_the_cloth_map():
    """Leather has no fibre sheen: the forged sheen map (sqrt of the albedo)
    lifted black leather to grey, so the recipe's faint neutral colour is
    used and the map left out."""
    b, _ = mock_pymxs.install()
    mat = b.build_material(dict(MAPS, sheen="C:/fake/sheen.png"), "Hide", "leather")
    assert "texmap_sheen" not in mat.props
    assert max(_unit(mat.props["sheen_color"])) <= 0.1
    vel = b.build_material(dict(MAPS, sheen="C:/fake/sheen.png"), "Velvet", "velvet")
    assert "texmap_sheen" in vel.props                     # cloth keeps its map (or mottle)


def test_backlit_stone_glows_in_its_own_colours_through_sss():
    """Alabaster lamps and backlit onyx: SSS for the room light plus a soft
    self-illumination driven by the stone's albedo (veins show through), well
    under the LED panel's burn-out level."""
    assert any("stone_backlit" in keys for _, keys in CLASS_GROUPS)
    b, _ = mock_pymxs.install()
    mat = b.build_material(MAPS, "Alabaster", "stone_backlit")
    assert mat.props["translucency_on"] == 6
    assert mat.props["texmap_self_illumination"].cls in ("Bitmaptexture", "VRayBitmap")
    assert mat.props["selfIllumination_multiplier"] <= 1.5 < RECIPES["emissive"]["self_illum"]["multiplier"] + 1.0
    assert mat.props["compensate_camera_exposure"] is True


def test_a_stale_roughness_map_is_rescaled_to_the_recipe():
    """A roughness map replaces the scalar, so a material forged before a
    recipe change kept the old roughness for ever. With the forge-day value
    in the manifest the builder blends the map to today's recipe."""
    b, _ = mock_pymxs.install()
    want = RECIPES["leather"]["base_roughness"]
    for forged in (0.60, 0.20):
        amount, scalar = b.roughness_blend(forged, want)
        assert 0.0 < amount < 1.0 and scalar in (0.0, 1.0)
        assert forged * amount + scalar * (1.0 - amount) == pytest.approx(want)
        mat = b.build_material(MAPS, "Hide", "leather", roughness_base=forged)
        assert mat.props["texmap_reflectionGlossiness_multiplier"] == pytest.approx(amount * 100.0)
        assert mat.props["reflection_glossiness"] == scalar
    fresh = b.build_material(MAPS, "Hide", "leather", roughness_base=want)
    assert "texmap_reflectionGlossiness_multiplier" not in fresh.props
    assert fresh.props["reflection_glossiness"] == want
    legacy = b.build_material(MAPS, "Hide", "leather")              # manifests from before the field
    assert "texmap_reflectionGlossiness_multiplier" not in legacy.props
