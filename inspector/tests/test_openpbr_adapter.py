from material_inspector.core.config import load_options
from material_inspector.core.inspector import InspectorOptions, inspect
from material_inspector.core.model import ColorSpace, Renderer, SlotRole
from material_inspector.max_adapter.fixes import FixApplier
from material_inspector.max_adapter.scene import SceneReader
from tests.fakert import Color, FakeRT, Node


def scene(cls="OpenPBRMaterial"):
    rough = Node("Bitmaptexture", "rough_bm", filename="C:/tex/X_Roughness.png", colorspace="sRGB")
    nrm = Node("Bitmaptexture", "nrm_bm", filename="C:/tex/X_NormalGL.png", colorspace="Raw")
    m = Node(cls, "Default OpenPBR", base_color=Color(10, 8, 6), specular_roughness=0.5,
             base_metalness=0.0, specular_ior=1.5, transmission_weight=0.0,
             specular_roughness_map=rough, geometry_normal_map=nrm)
    return FakeRT([m], existing_files={"C:/tex/X_Roughness.png", "C:/tex/X_NormalGL.png"})


def test_reads_openpbr_material():
    mats = SceneReader(scene()).materials()
    assert len(mats) == 1
    m = mats[0]
    assert m.renderer == Renderer.OPENPBR
    assert m.params["roughness"] == 0.5 and m.params["metalness"] == 0.0
    n = m.textures_for(SlotRole.NORMAL)[0]
    assert n.via_normal_node is True and n.color_space == ColorSpace.LINEAR
    assert m.textures_for(SlotRole.ROUGHNESS)[0].color_space == ColorSpace.SRGB


def test_openpbr_findings():
    mats = SceneReader(scene()).materials()
    ids = {f.rule_id for f in inspect(mats, InspectorOptions(check_pixels=False))}
    assert "R001" in ids and "R010" in ids
    assert "R006" not in ids


def test_openpbr_fixes_apply():
    rt = scene()
    mats = SceneReader(rt).materials()
    findings = inspect(mats, InspectorOptions(check_pixels=False))
    ap = FixApplier(rt)
    res = {f.rule_id: ap.apply(f, mats[0]) for f in findings if f.rule_id in ("R001", "R010")}
    assert res["R001"].ok and res["R010"].ok
    assert rt.sceneMaterials[0]._props["base_color"].r > 10


def test_alias_class_resolves_identically():
    for cls in ("OpenPBR_Material", "OpenPBRSurfaceMaterial"):
        m = SceneReader(scene(cls)).materials()[0]
        assert m.renderer == Renderer.OPENPBR and m.params["roughness"] == 0.5
        assert m.textures_for(SlotRole.NORMAL)[0].via_normal_node is True


def test_normal_bump_node_for_openpbr_insert():
    rt = FakeRT()
    assert rt.Normal_Bump()._cls == "Normal_Bump"


def test_openpbr_normal_convention_option(tmp_path):
    p = tmp_path / "cfg.json"
    p.write_text('{"normal_convention": {"openpbr": "opengl"}}')
    opts, warnings = load_options(str(p))
    assert not warnings
    assert opts.normal_convention["openpbr"] == "opengl"
