from material_inspector.core.inspector import InspectorOptions, inspect
from material_inspector.core.model import ColorSpace, Renderer, SlotRole
from material_inspector.max_adapter.fixes import FixApplier
from material_inspector.max_adapter.scene import SceneReader
from tests.fakert import Color, FakeRT, Node


def vray_scene():
    rough_bm = Node("Bitmaptexture", "rough_bm", filename="C:/tex/Oak_Glossiness.png", colorspace="sRGB")
    out_node = Node("Output", "out", subtex=[rough_bm])                     # wrapped in an Output map
    normal_bm = Node("VRayBitmap", "nrm_bm", HDRIMapName="C:/tex/Oak_NormalGL.png", color_space=0)
    vm = Node("VRayMtl", "Oak floor",
              diffuse=Color(10, 8, 6), reflection_glossiness=0.6, brdf_useRoughness=True, brdf_type=1,
              reflection_metalness=0.0, reflection_ior=1.5, refraction=Color(0, 0, 0),
              refraction_ior=1.6, refraction_fogColor=Color(255, 255, 255), refraction_fogMult=1.0,
              texmap_reflectionGlossiness=out_node, texmap_bump=normal_bm, texmap_diffuse=None)
    glass = Node("CoronaPhysicalMtl", "Window glass", baseColor=Color(128, 128, 128),
                 baseRoughness=0.0, metalnessMode=0, baseIor=1.52, refractionAmount=1.0,
                 volumetricAbsorptionColor=Color(255, 255, 255), volumetricAbsorptionDistance=10.0,
                 useThinMode=False)
    multi = Node("Multimaterial", "Multi", subs=[vm, glass, vm])  # vm repeated: visited once
    return FakeRT([multi], existing_files={"C:/tex/Oak_Glossiness.png"})


def test_walker_reads_records_through_multi_and_output():
    rt = vray_scene()
    reader = SceneReader(rt)
    mats = reader.materials()
    assert [m.name for m in mats] == ["Oak floor", "Window glass"]
    oak, glass = mats
    assert oak.renderer == Renderer.VRAY and oak.scene_path == "Multi/Oak floor"
    assert oak.params["use_roughness"] is True and oak.params["roughness"] == 0.6
    assert oak.params["brdf"] == "blinn"
    rough = oak.textures_for(SlotRole.ROUGHNESS)[0]
    assert rough.color_space == ColorSpace.SRGB and rough.file_exists is True
    bump = oak.textures_for(SlotRole.BUMP)[0]
    assert bump.via_normal_node is False and bump.color_space == ColorSpace.LINEAR
    assert bump.file_exists is False
    assert glass.params["refraction_amount"] == 1.0 and glass.params["absorption_color"] == (1.0, 1.0, 1.0)
    assert "CoronaPhysicalMtl.base_color" in reader.log.as_dict()["used"]


def test_scene_findings_end_to_end():
    mats = SceneReader(vray_scene()).materials()
    found = {(f.material, f.rule_id) for f in inspect(mats, InspectorOptions(check_pixels=False))}
    assert ("Oak floor", "R001") in found      # gloss map as sRGB
    assert ("Oak floor", "R005") in found      # gloss file in roughness mode
    assert ("Oak floor", "R006") in found      # normal map straight in bump
    assert ("Oak floor", "R004") in found      # missing normal file
    assert ("Oak floor", "R010") in found      # albedo too dark
    assert ("Oak floor", "R015") in found      # Blinn BRDF
    assert ("Window glass", "R014") in found   # glass without absorption


def test_fixes_apply_and_report_failures():
    rt = vray_scene()
    mats = {m.name: m for m in SceneReader(rt).materials()}
    findings = inspect(list(mats.values()), InspectorOptions(check_pixels=False))
    ap = FixApplier(rt)
    results = {f.rule_id: ap.apply(f, mats[f.material]) for f in findings if f.fix}
    assert results["R001"].ok                       # colorspace set on Bitmaptexture
    assert results["R005"].ok                       # use_roughness toggled
    assert results["R010"].ok and results["R015"].ok
    assert results["R014"].ok                       # Corona absorption colour + distance
    assert results["R006"].ok                       # VRayNormalMap inserted
    oak = mats["Oak floor"].handle
    assert oak._props["brdf_useRoughness"] is False
    assert oak._props["brdf_type"] == 3
    assert oak._props["texmap_bump"]._cls == "VRayNormalMap"
    glass = mats["Window glass"].handle
    assert glass._props["volumetricAbsorptionColor"].g < 255
    # re-scan: the fixed issues are gone
    again = {(f.material, f.rule_id) for f in inspect(SceneReader(rt).materials(), InspectorOptions(check_pixels=False))}
    for rid in ("R001", "R005", "R006", "R010", "R015"):
        assert ("Oak floor", rid) not in again
    assert ("Window glass", "R014") not in again


def test_unknown_class_property_is_logged_missing():
    weird = Node("VRayMtl", "bare")      # no properties at all
    reader = SceneReader(FakeRT([weird]))
    mats = reader.materials()
    assert mats[0].params == {"is_legacy": False}
    assert "VRayMtl.base_color" in reader.log.as_dict()["missing"]


def test_bitmaptexture_gamma_path_matforge_style():
    """MatForge loads data maps via openBitMap(path, gamma=1.0): read and fix that way."""
    rt = FakeRT()
    bad = Node("Bitmaptexture", "r", filename="C:/t/oak_Roughness.png", bitmap=rt.openBitMap("C:/t/oak_Roughness.png"))
    good = Node("Bitmaptexture", "n", filename="C:/t/oak_Color.png", bitmap=rt.openBitMap("C:/t/oak_Color.png"))
    m = Node("VRayMtl", "Oak", diffuse=Color(140, 110, 80), brdf_useRoughness=True, brdf_type=3,
             texmap_reflectionGlossiness=bad, texmap_diffuse=good)
    rt.sceneMaterials = [m]
    reader = SceneReader(rt)
    mats = reader.materials()
    rough = mats[0].textures_for(SlotRole.ROUGHNESS)[0]
    assert rough.color_space == ColorSpace.SRGB
    assert mats[0].textures_for(SlotRole.BASE_COLOR)[0].color_space == ColorSpace.SRGB
    assert reader.log.as_dict()["used"]["Bitmaptexture.color_space"] == "bitmap.gamma"
    f = [x for x in inspect(mats, InspectorOptions(check_pixels=False)) if x.rule_id == "R001"][0]
    r = FixApplier(rt).apply(f, mats[0])
    assert r.ok and bad._props["bitmap"]._props["gamma"] == 1.0
    again = SceneReader(rt).materials()[0].textures_for(SlotRole.ROUGHNESS)[0]
    assert again.color_space == ColorSpace.LINEAR
