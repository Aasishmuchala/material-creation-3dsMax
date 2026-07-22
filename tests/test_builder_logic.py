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
    assert p["refraction_fogMult"] <= 0.5
    assert "texmap_opacity" not in p               # glass is not cut out
    assert "texmap_displacement" not in p          # glass does not displace
    assert not _misses(b)


def test_foliage_is_two_sided_and_never_refracts():
    """THE critical rule: leaves = clip opacity + 2-sided, no refraction."""
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
    # clip-mode opacity present
    assert "texmap_opacity" in front.props
    assert front.props["opacity_mode"] == 1
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
    assert mat.props["coat_amount"] == 0.35


def test_marble_translucency():
    b, _ = mock_pymxs.install()
    mat = b.build_material(MAPS, "Carrara", "marble")
    assert mat.props["translucency_on"] == 1              # V-Ray 7 mode enum
    assert isinstance(mat.props["translucency_color"], mock_pymxs.MockColor)
    # translucency only renders with non-black refraction (activation fix)
    assert "refraction" in mat.props


def test_fabric_sheen_and_leather_coat():
    b, _ = mock_pymxs.install()
    fab = b.build_material(MAPS, "Linen", "fabric")
    assert "sheen_color" in fab.props and "sheen_glossiness" in fab.props
    b, _ = mock_pymxs.install()
    lea = b.build_material(MAPS, "Hide", "leather")
    assert "coat_amount" in lea.props and "sheen_color" in lea.props


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


def test_cli_manifest_feeds_builder(tmp_path):
    """Producer→consumer contract: a real CLI-produced manifest must wire."""
    ref = tmp_path / "ref.png"
    rng = np.random.default_rng(5)
    Image.fromarray((rng.random((64, 64, 3)) * 255).astype("uint8")).save(ref)
    out_dir = tmp_path / "out"
    proc = subprocess.run(
        [sys.executable, os.path.join(REPO, "forge_cli.py"), str(ref),
         "--name", "RoundTrip", "--type", "concrete", "--res", "2k",
         "--out", str(out_dir)],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    manifest_path = json.loads(proc.stdout.strip().splitlines()[-1])["manifest"]
    b, rt = mock_pymxs.install()
    out = b.build_from_manifest(manifest_path, assign=False)
    assert out["material"] == "RoundTrip"


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
