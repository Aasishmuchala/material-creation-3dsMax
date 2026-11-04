import pytest

from material_inspector.core.inspector import InspectorOptions, ScanCancelled, inspect
from material_inspector.max_adapter.scene import SceneReader
from tests.fakert import Color, FakeRT, Node
from tests.test_scene_and_fixes import vray_scene

OPT = InspectorOptions(check_pixels=False)


def _mats():
    return SceneReader(vray_scene()).materials()


def test_progress_called_per_material():
    calls = []
    inspect(_mats(), OPT, progress=lambda i, n, name: calls.append((i, n, name)) or True)
    assert calls == [(1, 2, "Oak floor"), (2, 2, "Window glass")]


def test_cancel_raises():
    def cb(i, n, name):
        return i < 2
    with pytest.raises(ScanCancelled):
        inspect(_mats(), OPT, progress=cb)


def test_material_index_filled():
    found = inspect(_mats(), InspectorOptions())
    assert found
    for f in found:
        if f.rule_id == "M009":
            assert f.material_index is None
        else:
            assert f.material_index in (0, 1)
    assert {f.material_index for f in found if f.material == "Window glass"} == {1}


def _vray(name, **over):
    props = dict(diffuse=Color(128, 128, 128), reflection_glossiness=0.6, brdf_useRoughness=False,
                 brdf_type=1, reflection_metalness=0.0, reflection_ior=1.5, refraction=Color(0, 0, 0),
                 refraction_ior=1.6, refraction_fogColor=Color(255, 255, 255), refraction_fogMult=1.0)
    props.update(over)
    return Node("VRayMtl", name, **props)


def test_duplicate_names_get_distinct_indices():
    a = _vray("Oak floor", diffuse=Color(10, 8, 6))          # albedo too dark (R010)
    b = _vray("Oak floor", brdf_type=0)                       # old BRDF (R015)
    mats = SceneReader(FakeRT([Node("Multimaterial", "M", subs=[a, b])])).materials()
    assert [m.name for m in mats] == ["Oak floor", "Oak floor"]
    found = inspect(mats, OPT)
    idx = {f.rule_id: f.material_index for f in found}
    assert idx.get("R010") == 0
    assert 1 in {f.material_index for f in found}
    assert len({f.material_index for f in found}) == 2
