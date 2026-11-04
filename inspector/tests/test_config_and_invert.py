import json

from material_inspector.core.config import load_options, write_example
from material_inspector.core.inspector import InspectorOptions, inspect
from material_inspector.max_adapter.fixes import FixApplier
from material_inspector.max_adapter.scene import SceneReader
from tests.fakert import Color, FakeRT, Node


def test_missing_config_gives_defaults(tmp_path):
    opt, warns = load_options(str(tmp_path / "nope.json"))
    assert warns == [] and opt.config.albedo_ceiling == 240.0


def test_config_overrides_and_warnings(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"disabled_rules": ["R015"], "rules": {"albedo_ceiling": 230, "bogus": 1},
                             "normal_convention": {"vray": "opengl", "corona": "sideways"}, "extra": 1}))
    opt, warns = load_options(str(p))
    assert opt.config.albedo_ceiling == 230 and opt.disabled_rules == ("R015",)
    assert opt.normal_convention == {"vray": "opengl", "corona": None}
    assert len(warns) == 3


def test_bad_json_falls_back(tmp_path):
    p = tmp_path / "c.json"; p.write_text("{not json")
    opt, warns = load_options(str(p))
    assert warns and isinstance(opt, InspectorOptions)


def test_write_example(tmp_path):
    path = write_example(str(tmp_path / "sub" / "inspector.json"))
    assert load_options(path)[1] == []


def test_corona_invert_fix():
    bm = Node("CoronaBitmap", "r", filename="C:/t/stone_rough.png", colorSpace="linear")
    m = Node("CoronaPhysicalMtl", "Stone", baseColor=Color(120, 110, 100), baseRoughness=0.5,
             metalnessMode=0, baseIor=1.5, baseRoughnessTexmap=bm)
    rt = FakeRT([m], existing_files={"C:/t/stone_rough.png"})
    mats = SceneReader(rt).materials()
    # simulate a gloss map in a Corona roughness slot
    mats[0].textures[0].path = "C:/t/stone_gloss.png"
    f = [x for x in inspect(mats, InspectorOptions(check_pixels=False)) if x.rule_id == "R005"][0]
    r = FixApplier(rt).apply(f, mats[0])
    assert r.ok, r.message
    wrapped = m._props["baseRoughnessTexmap"]
    assert wrapped._cls == "Output" and wrapped._props["map1"] is bm
    assert wrapped._props["output"]._props["invert"] is True


def test_invert_refuses_nested_graph():
    bm = Node("CoronaBitmap", "r", filename="C:/t/a_gloss.png", colorSpace="linear")
    cc = Node("CoronaColorCorrect", "cc", subtex=[bm])
    m = Node("CoronaPhysicalMtl", "Nested", baseRoughnessTexmap=cc)
    rt = FakeRT([m])
    mats = SceneReader(rt).materials()
    f = [x for x in inspect(mats, InspectorOptions(check_pixels=False)) if x.rule_id == "R005"][0]
    r = FixApplier(rt).apply(f, mats[0])
    assert not r.ok and "manually" in r.message
