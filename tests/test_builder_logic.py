"""Builder wiring-logic tests — run OFF-Max via the mock pymxs runtime.

These prove the class-correct wiring contract (patio wood != chair leather !=
glass != foliage) deterministically, without 3ds Max. They complement, not
replace, the in-Max MAX_SMOKE.py (which validates real V-Ray property names).
"""
import json
import os
import subprocess
import sys

import numpy as np
import pytest
from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.dirname(os.path.abspath(__file__))
for p in (REPO, TESTS):
    if p not in sys.path:
        sys.path.insert(0, p)

import mock_pymxs  # noqa: E402
from core.recipes import RECIPES  # noqa: E402


def _write_maps(tmp_path, keys=("albedo", "roughness", "normal", "height",
                                "ao")):
    """Write tiny real PNG map files; return {key: path}."""
    maps = {}
    for k in keys:
        p = tmp_path / f"{k}.png"
        Image.fromarray((np.zeros((8, 8, 3)) + 128).astype("uint8")).save(p)
        maps[k] = str(p)
    return maps

MAPS = {k: "C:/fake/%s.png" % k
        for k in ("albedo", "roughness", "normal", "height", "ao")}
FOLIAGE_MAPS = dict(MAPS, opacity="C:/fake/opacity.png")


def _maps_for(mclass):
    return FOLIAGE_MAPS if RECIPES[mclass].get("opacity") else MAPS


def _misses(builder):
    return [l for l in builder.LOG if "MISS" in l]


# ---------- per-class wiring ----------

def test_wood_exterior_wiring():
    b, rt = mock_pymxs.install()
    mat = b.build_material(MAPS, "Patio_Teak", "wood_exterior")
    assert str(rt.classOf(mat)) == "VRayMtl"
    p = mat.props
    assert p["reflection_fresnel"] is True
    assert p["brdf_useRoughness"] is True
    assert p["reflection_lockIOR"] is True
    assert p["refraction_ior"] == 1.5
    # displacement is NOT wired on the material — it is applied per-object via
    # VRayDisplacementMod on assign (see test_assign_adds_displacement)
    assert "texmap_displacement" not in p
    # wood is opaque and non-refractive
    assert "refraction" not in p          # no refraction COLOR
    assert "refraction_thinWalled" not in p
    assert "texmap_opacity" not in p
    assert not _misses(b)


def test_bump_multiplier_is_percentage_scale():
    """VRayMtl bump is a 0-100 percentage (default 30, ~100 = full), NOT a
    0-1 multiplier. Written value must land on that scale."""
    b, _ = mock_pymxs.install()
    mat = b.build_material(MAPS, "X", "stone")
    val = mat.props["texmap_bump_multiplier"]
    assert 1.0 <= val <= 200.0, f"bump {val} is off the 0-100 scale"


def test_glass_wiring():
    b, rt = mock_pymxs.install()
    mat = b.build_material(MAPS, "Glazing", "glass_clear")
    p = mat.props
    assert "refraction" in p                       # transparent
    assert p["refraction_ior"] == 1.52
    assert p["refraction_thinWalled"] is True
    fog = p["refraction_fogColor"].as_unit()
    assert min(fog) > 0.9, "fog must stay near-white (saturated-fog trap)"
    # fog in cm: colour = one pane's transmittance, depth = its thickness
    assert p["refraction_fogUnitsScale_on"] is True
    thick = RECIPES["glass_clear"]["refraction"]["thickness_mm"]
    assert p["refraction_fogDepth"] == pytest.approx(thick / 10.0)
    # thin-walled ignores fog, so the transmission itself carries the tint
    tint = p["refraction"].as_unit()
    assert 0.85 < min(tint) < 1.0 and tint[0] < tint[1]   # faint green
    assert "texmap_opacity" not in p               # glass is not cut out
    assert "texmap_displacement" not in p          # glass does not displace
    assert not _misses(b)


def test_foliage_is_two_sided_and_never_refracts():
    """THE critical rule: leaves = cut-out opacity + 2-sided, no refraction."""
    b, rt = mock_pymxs.install()
    wrap = b.build_material(FOLIAGE_MAPS, "Leaf", "foliage")
    assert "2Sided" in str(rt.classOf(wrap)), "foliage must be VRay2SidedMtl"
    front = wrap.props["frontMtl"]
    assert str(rt.classOf(front)) == "VRayMtl"
    # translucency on the wrapper is a colour, not a refraction
    assert isinstance(wrap.props["translucency"], mock_pymxs.MockColor)
    # front leaf material must NOT refract anywhere
    assert "refraction" not in front.props
    assert "refraction_thinWalled" not in front.props
    # cut-out opacity present; stochastic (2), the V-Ray 7 default, which
    # keeps bump where Clip (1) may drop it
    assert "texmap_opacity" in front.props
    assert front.props["opacity_mode"] == 2
    assert not _misses(b)


def test_metal_brushed_wiring():
    b, _ = mock_pymxs.install()
    mat = b.build_material(MAPS, "Steel", "metal_brushed")
    assert mat.props["reflection_metalness"] == 1.0
    assert mat.props["anisotropy"] == 0.55
    assert not _misses(b)


def test_patina_metalness_map_is_wired():
    """When a metalness map is present (PATINA backend), it drives metalness
    per-pixel and the scalar is set to 1.0 so the map passes through."""
    b, _ = mock_pymxs.install()
    maps = dict(MAPS, metalness="C:/fake/metalness.png")
    mat = b.build_material(maps, "PatinaWood", "wood_interior")
    assert "texmap_metalness" in mat.props, "metalness map not wired"
    assert mat.props["reflection_metalness"] == 1.0
    assert not _misses(b)


def test_metal_painted_has_no_metalness():
    b, _ = mock_pymxs.install()
    mat = b.build_material(MAPS, "Powder", "metal_painted")
    # powder-coat is dielectric-over-metal: metalness must stay off
    assert "reflection_metalness" not in mat.props
    assert mat.props["coat_amount"] == RECIPES["metal_painted"]["coat"]["amount"]      # a thin satin film


def test_marble_translucency():
    b, _ = mock_pymxs.install()
    mat = b.build_material(MAPS, "Carrara", "marble")
    p = mat.props
    tr = RECIPES["marble"]["translucency"]
    # V-Ray 7 SSS mode (6); verified on 7.30 to need no refraction colour,
    # while the old hard-wax mode (1) + 0.06 refraction rendered as diffuse
    assert p["translucency_on"] == 6
    assert isinstance(p["translucency_color"], mock_pymxs.MockColor)
    assert p["translucency_amount"] == tr["sss_amount"]
    assert "texmap_translucent" in p                       # veins through SSS
    assert p["refraction_fogDepth"] == pytest.approx(tr["sss_radius_mm"] / 10.0)
    assert p["refraction_fogUnitsScale_on"] is True
    assert "refraction" not in p                           # stays opaque


def test_fabric_sheen_and_leather_coat():
    b, _ = mock_pymxs.install()
    fab = b.build_material(MAPS, "Linen", "fabric")
    assert "sheen_color" in fab.props and "sheen_glossiness" in fab.props
    b, _ = mock_pymxs.install()
    lea = b.build_material(MAPS, "Hide", "leather")
    assert "coat_amount" in lea.props and "sheen_color" in lea.props


def test_coat_and_sheen_written_as_roughness_in_roughness_mode():
    """V-Ray 7.30 reads coat/sheen glossiness as roughness once Use roughness
    is on (a 0.95 coat renders matte), so recipe glossiness is inverted."""
    b, _ = mock_pymxs.install()
    lac = b.build_material(MAPS, "Lacquer", "wood_interior")
    coat = RECIPES["wood_interior"]["coat"]
    assert lac.props["brdf_useRoughness"] is True
    assert lac.props["coat_glossiness"] == pytest.approx(1.0 - coat["glossiness"])
    b, _ = mock_pymxs.install()
    vel = b.build_material(MAPS, "Velvet", "velvet")
    sheen = RECIPES["velvet"]["sheen"]
    assert vel.props["sheen_glossiness"] == pytest.approx(1.0 - sheen["glossiness"])


# ---------- color management ----------

def test_data_maps_load_linear_albedo_does_not():
    b, _ = mock_pymxs.install()
    mat = b.build_material(MAPS, "X", "generic")
    # albedo: filename set, NOT forced through a gamma-1.0 openBitMap
    diffuse = mat.props["texmap_diffuse"]
    assert "filename" in diffuse.props
    assert "bitmap" not in diffuse.props
    # roughness: forced linear (gamma 1.0)
    rough = mat.props["texmap_reflectionGlossiness"]
    assert rough.props["bitmap"].gamma == 1.0
    # normal map bitmap inside the VRayNormalMap: linear
    nrm = mat.props["texmap_bump"]
    assert nrm.props["normal_map"].props["bitmap"].gamma == 1.0


# ---------- stochastic tiling (stationary classes) ----------

ANTI_TILE = ("VRayMtl", "CoronaPhysicalMtl", "VRayUVWRandomizer")


def test_stationary_class_maps_share_one_uvw_randomizer():
    b, rt = mock_pymxs.install(classes=ANTI_TILE)
    mat = b.build_material(dict(MAPS, sheen="C:/fake/sheen.png"), "Linen", "fabric")
    alb = mat.props["texmap_diffuse"]
    rough = mat.props["texmap_reflectionGlossiness"]
    nrm = mat.props["texmap_bump"].props["normal_map"]
    sheen = mat.props["texmap_sheen"]
    rnd = alb.props["mapSource"]
    assert str(rt.classOf(rnd)) == "VRayUVWRandomizer"
    for tex in (alb, rough, nrm, sheen):
        assert str(rt.classOf(tex)) == "VRayBitmap"
        assert tex.props["mapSource"] is rnd           # maps stay aligned
    # transfer function (color_space): colour maps sRGB (2), data maps none (0),
    # measured on V-Ray 7.30. Primaries (rgbColorSpace, pb2vrayhdri.h): colour
    # maps sRGB (1), data maps raw (3), never the render-setting default (0)
    # that can put a normal map through sRGB -> ACEScg.
    assert alb.props["color_space"] == 2 and sheen.props["color_space"] == 2
    assert rough.props["color_space"] == 0 and nrm.props["color_space"] == 0
    assert alb.props["rgbColorSpace"] == 1 and sheen.props["rgbColorSpace"] == 1
    assert rough.props["rgbColorSpace"] == 3 and nrm.props["rgbColorSpace"] == 3
    assert alb.props["HDRIMapName"] == MAPS["albedo"]
    # random offset per UV tile and per node (matching cushions differ),
    # blended; never rotated (normal map frame), never per element
    assert rnd.props["mode_by_uv_tile"] is True
    assert rnd.props["mode_by_node_handle"] is True
    assert "mode_by_element" not in rnd.props
    assert 0.0 < rnd.props["tile_blend"] < 0.5
    assert rnd.props["variance_rot_min"] == 0.0 and rnd.props["variance_rot_max"] == 0.0
    assert rnd.props["variance_u_max"] == 1.0 and rnd.props["variance_v_max"] == 1.0
    assert not _misses(b)


def test_patterned_class_keeps_plain_bitmaps():
    """Planks, tiles and veins must line up with the geometry: no randomizer."""
    b, rt = mock_pymxs.install(classes=ANTI_TILE)
    mat = b.build_material(MAPS, "Oak", "wood_interior")
    assert str(rt.classOf(mat.props["texmap_diffuse"])) == "Bitmaptexture"


def test_anti_tile_off_and_missing_randomizer_fall_back():
    b, rt = mock_pymxs.install(classes=ANTI_TILE)
    mat = b.build_material(MAPS, "Linen", "fabric", anti_tile=False)
    assert str(rt.classOf(mat.props["texmap_diffuse"])) == "Bitmaptexture"
    b, rt = mock_pymxs.install()                       # V-Ray without the class
    mat = b.build_material(MAPS, "Linen", "fabric")
    assert str(rt.classOf(mat.props["texmap_diffuse"])) == "Bitmaptexture"
    assert any("VRayUVWRandomizer not available" in l for l in b.LOG)


def test_stationary_displacement_follows_the_randomizer():
    """2D displacement samples one UV tile and repeats it, so it cannot follow
    the per-tile random lookup: a randomized height needs 3D mapping (1)."""
    nodes = mock_pymxs.make_scene_nodes(1)
    b, rt = mock_pymxs.install(selection=nodes, classes=ANTI_TILE)
    mat = b.build_material(MAPS, "Rug", "carpet")
    b.assign_to_selection(mat, "carpet", height_map=MAPS["height"])
    dmod = nodes[0].modifiers[0].props
    disp = dmod["texmap"]
    assert str(rt.classOf(disp)) == "VRayBitmap"
    assert disp.props["mapSource"] is mat.props["texmap_diffuse"].props["mapSource"]
    assert disp.props["color_space"] == 0 and disp.props["rgbColorSpace"] == 3
    assert dmod["type"] == 1
    assert dmod["keepContinuity"] is True
    assert not _misses(b)


def test_plainly_tiled_displacement_stays_2d():
    """Without the randomizer (patterned class, anti_tile off) the height map
    tiles on the UV grid like the bump, so the fast 2D mapping (0) is right."""
    for mclass, anti in (("stone", True), ("carpet", False)):
        nodes = mock_pymxs.make_scene_nodes(1)
        b, rt = mock_pymxs.install(selection=nodes, classes=ANTI_TILE)
        mat = b.build_material(MAPS, "X", mclass, anti_tile=anti)
        b.assign_to_selection(mat, mclass, height_map=MAPS["height"])
        dmod = nodes[0].modifiers[0].props
        assert str(rt.classOf(dmod["texmap"])) == "Bitmaptexture", mclass
        assert dmod["type"] == 0, mclass
        assert "keepContinuity" not in dmod, mclass


def test_keep_continuity_is_optional():
    """A V-Ray build without keepContinuity still gets 3D displacement, and the
    missing nicety is not reported as a MISS."""
    nodes = mock_pymxs.make_scene_nodes(1)
    b, rt = mock_pymxs.install(selection=nodes, classes=ANTI_TILE,
                               drop={"keepContinuity"})
    mat = b.build_material(MAPS, "Rug", "carpet")
    b.assign_to_selection(mat, "carpet", height_map=MAPS["height"])
    assert nodes[0].modifiers[0].props["type"] == 1
    assert not _misses(b)


@pytest.mark.parametrize("mclass", [c for c in RECIPES if RECIPES[c].get("stationary")])
def test_stationary_classes_build_without_miss(mclass):
    b, rt = mock_pymxs.install(classes=ANTI_TILE)
    b.build_material(_maps_for(mclass), "T_" + mclass, mclass)
    assert not _misses(b), "unexpected property MISS for %s: %s" % (mclass, _misses(b))


# ---------- every class builds cleanly ----------

@pytest.mark.parametrize("mclass", list(RECIPES))
def test_every_class_builds_without_miss(mclass):
    b, rt = mock_pymxs.install()
    mat = b.build_material(_maps_for(mclass), "T_" + mclass, mclass)
    assert mat is not None
    assert not _misses(b), "unexpected property MISS for %s: %s" % (
        mclass, _misses(b))


# ---------- editor placement ----------

def test_put_in_editor_uses_active_slot():
    b, rt = mock_pymxs.install(active_slot=5)
    mat = b.build_material(MAPS, "X", "concrete")
    slot = b.put_in_editor(mat)
    assert slot == 5
    assert rt.meditMaterials[4] is mat          # 0-based index, 1-based slot
    assert rt.MatEditor.opened is True
    assert (5, False) in rt.medit.calls


def test_put_in_editor_explicit_slot_clamped():
    b, rt = mock_pymxs.install()
    mat = b.build_material(MAPS, "X", "concrete")
    assert b.put_in_editor(mat, slot=99) == 24   # clamped to slot count
    assert b.put_in_editor(mat, slot=0) == 1


# ---------- assignment + displacement ----------

def test_assign_adds_working_displacement_for_stone():
    nodes = mock_pymxs.make_scene_nodes(3)
    b, rt = mock_pymxs.install(selection=nodes)
    mat = b.build_material(MAPS, "Paver", "stone")
    n = b.assign_to_selection(mat, "stone", height_map="C:/fake/height.png")
    assert n == 3
    for node in nodes:
        assert node.props["material"] is mat
        assert len(node.modifiers) == 1          # VRayDisplacementMod added
        dmod = node.modifiers[0]
        # the modifier MUST carry the height map (else it displaces nothing)
        assert "texmap" in dmod.props
        assert dmod.props["amount"] == 3.0       # displacement_mm in units
    assert len(rt.added_modifiers) == 3


def test_assign_skips_displacement_without_height_map():
    nodes = mock_pymxs.make_scene_nodes(2)
    b, rt = mock_pymxs.install(selection=nodes)
    mat = b.build_material(MAPS, "Paver", "stone")
    # no height_map -> no broken empty modifier is added
    b.assign_to_selection(mat, "stone", height_map=None)
    for node in nodes:
        assert len(node.modifiers) == 0
    assert rt.added_modifiers == []


def test_assign_no_displacement_for_flat_metal():
    nodes = mock_pymxs.make_scene_nodes(2)
    b, rt = mock_pymxs.install(selection=nodes)
    mat = b.build_material(MAPS, "Steel", "metal_brushed")
    n = b.assign_to_selection(mat, "metal_brushed")
    assert n == 2
    for node in nodes:
        assert node.props["material"] is mat
        assert len(node.modifiers) == 0          # metal does not displace
    assert rt.added_modifiers == []


def test_assign_empty_selection_is_safe():
    b, rt = mock_pymxs.install(selection=[])
    mat = b.build_material(MAPS, "X", "stone")
    assert b.assign_to_selection(mat, "stone") == 0


def test_displacement_amount_converts_scene_units():
    """3mm displacement in an INCH scene must be written as ~0.118, not 3.0."""
    nodes = mock_pymxs.make_scene_nodes(1)
    b, rt = mock_pymxs.install(selection=nodes, system_unit="in")
    mat = b.build_material(MAPS, "Paver", "stone")
    b.assign_to_selection(mat, "stone", height_map="C:/fake/height.png")
    amount = nodes[0].modifiers[0].props["amount"]
    assert abs(amount - 3.0 / 25.4) < 1e-4, f"no unit conversion: {amount}"


def test_displacement_amount_mm_scene_is_raw():
    nodes = mock_pymxs.make_scene_nodes(1)
    b, rt = mock_pymxs.install(selection=nodes, system_unit="mm")
    mat = b.build_material(MAPS, "Paver", "stone")
    b.assign_to_selection(mat, "stone", height_map="C:/fake/height.png")
    assert nodes[0].modifiers[0].props["amount"] == 3.0


def test_reassign_does_not_stack_displacement():
    """Re-assigning replaces the MatForge displacement mod, never doubles it."""
    nodes = mock_pymxs.make_scene_nodes(1)
    b, rt = mock_pymxs.install(selection=nodes)
    mat = b.build_material(MAPS, "Paver", "stone")
    b.assign_to_selection(mat, "stone", height_map="C:/fake/height.png")
    b.assign_to_selection(mat, "stone", height_map="C:/fake/height.png")
    disp = [m for m in nodes[0].modifiers
            if str(getattr(m, "name", "")) == "MatForge_Displace"]
    assert len(disp) == 1, "displacement modifier stacked on re-assign"
    assert len(rt.deleted_modifiers) == 1


# ---------- build_from_manifest (the production entry point) ----------

def test_build_from_manifest_end_to_end(tmp_path):
    maps = _write_maps(tmp_path)
    manifest = {"schema": 1, "name": "MF_Concrete", "class": "concrete",
                "res": "2k", "maps": maps, "warnings": []}
    mpath = tmp_path / "manifest.json"
    mpath.write_text(json.dumps(manifest))
    b, rt = mock_pymxs.install(active_slot=3)
    out = b.build_from_manifest(str(mpath), assign=False)
    assert out["material"] == "MF_Concrete"
    assert out["slot"] == 3
    assert rt.meditMaterials[2] is not None


@pytest.mark.parametrize("seamless,pattern,randomized",
                         [(True, None, True), (False, None, False), (None, None, True),
                          (True, True, False), (True, False, True)])
def test_build_from_manifest_randomizes_only_tiling_maps(tmp_path, seamless,
                                                         pattern, randomized):
    """Maps made with seamless off do not wrap, so the randomizer's wrapped
    offsets would run the photo's edges through every repeat. A pattern the
    forge kept (a striped rug) stays on plain tiling too: offsets shift each
    repeat's stripes by a random fraction of the tile. A manifest with no
    "seamless" or "pattern" key (older forge_cli) keeps stochastic tiling."""
    manifest = {"schema": 1, "name": "MF_Rug", "class": "carpet",
                "maps": _write_maps(tmp_path), "warnings": []}
    if seamless is not None:
        manifest["seamless"] = seamless
    if pattern is not None:
        manifest["pattern"] = pattern
    mpath = tmp_path / "manifest.json"
    mpath.write_text(json.dumps(manifest))
    nodes = mock_pymxs.make_scene_nodes(1)
    b, rt = mock_pymxs.install(selection=nodes, classes=ANTI_TILE)
    out = b.build_from_manifest(str(mpath), assign=True)
    mat = rt.meditMaterials[out["slot"] - 1]
    want = "VRayBitmap" if randomized else "Bitmaptexture"
    assert str(rt.classOf(mat.props["texmap_diffuse"])) == want
    dmod = nodes[0].modifiers[0].props
    assert str(rt.classOf(dmod["texmap"])) == want
    assert dmod["type"] == (1 if randomized else 0)


def test_manifest_validation_rejects_bad(tmp_path):
    b, rt = mock_pymxs.install()

    def mf(d):
        p = tmp_path / "m.json"
        p.write_text(json.dumps(d))
        return str(p)

    with pytest.raises(ValueError):  # missing 'class'
        b.build_from_manifest(mf({"name": "x", "maps": {}}))
    with pytest.raises(ValueError):  # unknown class
        b.build_from_manifest(mf({"name": "x", "class": "nope", "maps": {}}))
    with pytest.raises(FileNotFoundError):  # map file absent
        b.build_from_manifest(mf({"name": "x", "class": "concrete",
                                  "maps": {"albedo": "C:/nope/a.png"}}))
    with pytest.raises(ValueError):  # "false" would read as true
        b.build_from_manifest(mf({"name": "x", "class": "concrete",
                                  "maps": {}, "seamless": "false"}))
    with pytest.raises(ValueError):
        b.build_from_manifest(mf({"name": "x", "class": "fabric",
                                  "maps": {}, "pattern": 1}))
    for bad in ([0.8, 0.5], [0.8, float("nan"), 1.0], [1.2, 0.5, 1.0], "violet",
                [True, 0.5, 1.0]):
        with pytest.raises(ValueError):
            b.build_from_manifest(mf({"name": "x", "class": "gemstone",
                                      "maps": {}, "transmission_tint": bad}))


def test_build_from_manifest_tints_both_renderers(tmp_path):
    """One amethyst manifest built for V-Ray and Corona: both carry the
    photo's body colour (Corona used to drop it and render colourless)."""
    manifest = {"schema": 1, "name": "Amethyst", "class": "gemstone",
                "maps": _write_maps(tmp_path), "warnings": [],
                "transmission_tint": [0.859, 0.3945, 1.0]}
    mpath = tmp_path / "manifest.json"
    mpath.write_text(json.dumps(manifest))
    b, rt = mock_pymxs.install()
    out = b.build_from_manifest(str(mpath), renderer="both")
    got = {}
    for m in out["materials"]:
        p = rt.meditMaterials[m["slot"] - 1].props
        key = "refraction_fogColor" if m["renderer"] == "vray" else "volumetricAbsorptionColor"
        got[m["renderer"]] = p[key].as_unit()
    assert set(got) == {"vray", "corona"}
    for colour in got.values():
        assert colour[1] < 0.45 and colour[2] > 0.99      # violet, not near-white


def _run_cli(tmp_path, mclass, *flags):
    """Run the real forge_cli; return the manifest path."""
    ref = tmp_path / "ref.png"
    rng = np.random.default_rng(5)
    Image.fromarray((rng.random((64, 64, 3)) * 255).astype("uint8")).save(ref)
    proc = subprocess.run(
        [sys.executable, os.path.join(REPO, "forge_cli.py"), str(ref),
         "--name", "RoundTrip", "--type", mclass, "--res", "2k",
         "--out", str(tmp_path / "out")] + list(flags),
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])["manifest"]


def test_cli_manifest_feeds_builder(tmp_path):
    """Producer→consumer contract: a real CLI-produced manifest must wire."""
    manifest_path = _run_cli(tmp_path, "concrete")
    with open(manifest_path, encoding="utf-8") as f:
        assert json.load(f)["seamless"] is True
    b, rt = mock_pymxs.install()
    out = b.build_from_manifest(manifest_path, assign=False)
    assert out["material"] == "RoundTrip"


def test_cli_no_seamless_turns_off_stochastic_tiling(tmp_path):
    """Untick 'Make it tile seamlessly' on a rug photo: the maps do not wrap,
    so the builder must keep them plain (no random wrapped offsets)."""
    manifest_path = _run_cli(tmp_path, "carpet", "--no-seamless")
    with open(manifest_path, encoding="utf-8") as f:
        assert json.load(f)["seamless"] is False
    b, rt = mock_pymxs.install(classes=ANTI_TILE)
    out = b.build_from_manifest(manifest_path, assign=False)
    mat = rt.meditMaterials[out["slot"] - 1]
    assert str(rt.classOf(mat.props["texmap_diffuse"])) == "Bitmaptexture"
    assert not _misses(b)


def test_cli_striped_fabric_stays_on_plain_tiling(tmp_path):
    """A striped fabric photo: the forge keeps the stripes (no flattening)
    and records "pattern", so the builder lays them on plain tiling where
    every repeat's stripes line up. A plain fabric records no pattern."""
    stripes = np.zeros((256, 256, 3), np.uint8)
    stripes[:] = (200, 60, 50)
    stripes[:, (np.arange(256) // 32) % 2 == 1] = (235, 225, 205)     # 4 pairs
    paths = {}
    for label, img in (("striped", stripes), ("plain", None)):
        ref = tmp_path / (label + ".png")
        if img is None:
            rng = np.random.default_rng(5)
            img = (150 + 20 * rng.random((256, 256, 3))).astype("uint8")
        Image.fromarray(img).save(ref)
        proc = subprocess.run(
            [sys.executable, os.path.join(REPO, "forge_cli.py"), str(ref),
             "--name", label, "--type", "fabric", "--res", "2k",
             "--out", str(tmp_path / label)], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        paths[label] = json.loads(proc.stdout.strip().splitlines()[-1])["manifest"]
    for label, pattern, want in (("striped", True, "Bitmaptexture"),
                                 ("plain", None, "VRayBitmap")):
        with open(paths[label], encoding="utf-8") as f:
            assert json.load(f).get("pattern") is pattern
        b, rt = mock_pymxs.install(classes=ANTI_TILE)
        out = b.build_from_manifest(paths[label], assign=False)
        mat = rt.meditMaterials[out["slot"] - 1]
        assert str(rt.classOf(mat.props["texmap_diffuse"])) == want


@pytest.mark.parametrize("mclass,flags,seamless", [
    ("fabric", [], True), ("fabric", ["--no-seamless"], False),
    ("foliage", [], False)])          # generate_maps never tiles a cut-out
def test_cli_records_whether_maps_tile(tmp_path, monkeypatch, mclass, flags,
                                       seamless):
    import forge_cli
    ref = tmp_path / "ref.png"
    Image.new("RGB", (8, 8), (120, 90, 60)).save(ref)

    def fake_generate(image, out_dir, **kw):
        os.makedirs(out_dir, exist_ok=True)
        return {"albedo": str(ref)}

    monkeypatch.setattr(forge_cli, "generate_maps", fake_generate)
    out_dir = tmp_path / "out"
    assert forge_cli.main([str(ref), "--name", "T", "--type", mclass,
                           "--out", str(out_dir)] + flags) == 0
    with open(out_dir / "manifest.json", encoding="utf-8") as f:
        assert json.load(f)["seamless"] is seamless


# ---------- defensive fallback ----------

def test_missing_property_logs_miss_but_still_builds():
    # simulate a V-Ray build that lacks the thin-walled property entirely
    b, rt = mock_pymxs.install(drop={"refraction_thinWalled"})
    mat = b.build_material(MAPS, "Glazing", "glass_clear")
    assert str(rt.classOf(mat)) == "VRayMtl"      # build still succeeds
    assert "refraction" in mat.props              # rest of glass still wired
    assert any("thin-walled" in l for l in _misses(b)), \
        "a dropped property must surface as a logged MISS, not a crash"


def test_set_first_uses_second_candidate_when_first_absent():
    b, rt = mock_pymxs.install()
    node = mock_pymxs.MockNode("VRayMtl", frozenset({"fogMult"}))
    used = b._set_first(node, ["refraction_fogMult", "fogMult"], 0.1, "fog")
    assert used == "fogMult"
    assert node.props["fogMult"] == 0.1


def test_data_maps_open_raw_under_ocio():
    """3ds Max 2024+ OCIO ignores openBitMap's gamma keyword: on Max 2026.2 a
    50 % grey data map opened with gamma 1.0 read 0.216 (sRGB-decoded), with
    colorSpace "Raw" it read 0.502. Data maps must use the data colour space;
    albedo keeps following the scene's input rules."""
    import types
    b, rt = mock_pymxs.install()
    rt.ColorPipelineMgr = types.SimpleNamespace(Mode="OCIO_Default",
                                                DataColorSpace="Raw")
    mat = b.build_material(MAPS, "Oak", "wood_interior")
    rough = mat.props["texmap_reflectionGlossiness"].props["bitmap"]
    assert rough.colorSpace == "Raw" and rough.gamma is None
    nrm = mat.props["texmap_bump"].props["normal_map"].props["bitmap"]
    assert nrm.colorSpace == "Raw"
    assert "bitmap" not in mat.props["texmap_diffuse"].props   # albedo: rules
    assert not _misses(b)


def test_data_maps_keep_gamma_in_legacy_pipeline():
    b, rt = mock_pymxs.install()          # no ColorPipelineMgr: gamma mode
    mat = b.build_material(MAPS, "Oak", "wood_interior")
    rough = mat.props["texmap_reflectionGlossiness"].props["bitmap"]
    assert rough.gamma == 1.0 and rough.colorSpace is None
