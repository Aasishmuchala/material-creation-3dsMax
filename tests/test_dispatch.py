"""Renderer dispatch (auto / vray / corona / both) through build_from_manifest."""
import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.dirname(os.path.abspath(__file__))
for p in (REPO, TESTS):
    if p not in sys.path:
        sys.path.insert(0, p)

import mock_pymxs  # noqa: E402
from test_builder_logic import _write_maps  # noqa: E402


def _manifest(tmp_path, mclass="wood_interior", **extra):
    mf = {"name": "Disp_Test", "class": mclass, "maps": _write_maps(tmp_path)}
    mf.update(extra)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(mf))
    return str(path)


def test_auto_corona(tmp_path):
    b, rt = mock_pymxs.install(renderer="corona")
    r = b.build_from_manifest(_manifest(tmp_path), slot=3)
    assert r["renderer"] == "corona"
    assert rt.meditMaterials[r["slot"] - 1].cls == "CoronaPhysicalMtl"
    assert [m["renderer"] for m in r["materials"]] == ["corona"]


def test_auto_vray(tmp_path):
    b, rt = mock_pymxs.install(renderer="vray")
    r = b.build_from_manifest(_manifest(tmp_path), slot=3)
    assert r["renderer"] == "vray"
    assert rt.meditMaterials[r["slot"] - 1].cls == "VRayMtl"


def test_auto_falls_back_to_available_class(tmp_path):
    b, rt = mock_pymxs.install(renderer=None, classes=("CoronaPhysicalMtl",))
    r = b.build_from_manifest(_manifest(tmp_path), slot=2)
    assert r["renderer"] == "corona"


def test_auto_no_classes(tmp_path):
    b, rt = mock_pymxs.install(renderer=None, classes=())
    with pytest.raises(RuntimeError, match="Neither V-Ray nor Corona"):
        b.build_from_manifest(_manifest(tmp_path))


def test_both(tmp_path):
    b, rt = mock_pymxs.install(renderer="vray")
    r = b.build_from_manifest(_manifest(tmp_path), slot=4, renderer="both")
    assert r["renderer"] == "both"
    assert [m["renderer"] for m in r["materials"]] == ["vray", "corona"]
    assert [m["slot"] for m in r["materials"]] == [4, 5]
    assert r["slot"] == 4
    assert rt.meditMaterials[3].cls == "VRayMtl"
    assert rt.meditMaterials[4].cls == "CoronaPhysicalMtl"
    # combined log keeps the V-Ray lines ahead of the Corona ones
    assert any("placed" in l for l in r["log"])


def test_both_last_slot_puts_corona_one_back(tmp_path):
    b, rt = mock_pymxs.install(renderer="vray")
    n = int(rt.meditMaterials.count)
    r = b.build_from_manifest(_manifest(tmp_path), slot=n, renderer="both")
    assert [m["slot"] for m in r["materials"]] == [n, n - 1]
    assert rt.meditMaterials[n - 1].cls == "VRayMtl"
    assert rt.meditMaterials[n - 2].cls == "CoronaPhysicalMtl"


def test_both_assign_follows_active_renderer(tmp_path):
    nodes = mock_pymxs.make_scene_nodes(2)
    b, rt = mock_pymxs.install(renderer="corona", selection=nodes)
    b.build_from_manifest(_manifest(tmp_path), slot=1, renderer="both",
                          assign=True)
    assert all(n.material.cls == "CoronaPhysicalMtl" for n in nodes)
    nodes = mock_pymxs.make_scene_nodes(2)
    b, rt = mock_pymxs.install(renderer=None, selection=nodes)
    b.build_from_manifest(_manifest(tmp_path), slot=1, renderer="both",
                          assign=True)
    assert all(n.material.cls == "VRayMtl" for n in nodes)


def test_corona_requested_but_missing(tmp_path):
    b, rt = mock_pymxs.install(renderer="vray", classes=("VRayMtl",))
    with pytest.raises(RuntimeError, match="Corona"):
        b.build_from_manifest(_manifest(tmp_path), renderer="corona")


def test_both_requires_both(tmp_path):
    b, rt = mock_pymxs.install(renderer="vray", classes=("VRayMtl",))
    with pytest.raises(RuntimeError, match="Corona"):
        b.build_from_manifest(_manifest(tmp_path), renderer="both")


def test_bad_renderer(tmp_path):
    b, rt = mock_pymxs.install()
    with pytest.raises(ValueError, match="auto|vray|corona|both"):
        b.build_from_manifest(_manifest(tmp_path), renderer="x")


def test_metal_kwarg_reaches_vray(tmp_path):
    b, rt = mock_pymxs.install()
    r = b.build_from_manifest(_manifest(tmp_path, "metal_brushed"), slot=1,
                              renderer="vray", metal="gold")
    assert rt.meditMaterials[0].props["texmap_diffuse_multiplier"] == 30.0


def test_manifest_metal_honoured(tmp_path):
    b, rt = mock_pymxs.install()
    b.build_from_manifest(_manifest(tmp_path, "metal_brushed", metal="copper"),
                          slot=1, renderer="vray")
    assert rt.meditMaterials[0].props["texmap_diffuse_multiplier"] == 30.0
    b2, rt2 = mock_pymxs.install()
    b2.build_from_manifest(_manifest(tmp_path, "metal_brushed"), slot=1,
                           renderer="vray")
    assert "texmap_diffuse_multiplier" not in rt2.meditMaterials[0].props
