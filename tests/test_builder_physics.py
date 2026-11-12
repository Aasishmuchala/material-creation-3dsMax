"""V-Ray builder consumes the matphys physics layer (mock runtime)."""
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
import matphys  # noqa: E402
from test_builder_logic import MAPS, _misses, _write_maps  # noqa: E402


def _close(a, b, tol=1e-3):
    return all(abs(x - y) <= tol for x, y in zip(a, b)) and len(a) == len(b)


def test_chrome_f0_mode():
    b, rt = mock_pymxs.install()
    mat = b.build_material(MAPS, "Chrome", "metal_chrome")
    p = mat.props
    # Max stores colour params scene-linear: F0 / edge tint written as-is
    f0 = matphys.metal_f0("chrome")
    edge = matphys.metal_edge_tint("chrome")
    assert _close(p["diffuse"].as_unit(), f0)
    assert p["texmap_diffuse_multiplier"] == 30.0
    assert _close(p["reflection"].as_unit(), edge)
    assert p["reflection_metalness"] == 1.0
    assert not _misses(b)


@pytest.mark.parametrize("gamma", [True, False])
def test_chrome_swatch_linear_regardless_of_gamma(gamma):
    b, rt = mock_pymxs.install(gamma=gamma)
    mat = b.build_material(MAPS, "Chrome", "metal_chrome")
    assert _close(mat.props["diffuse"].as_unit(), matphys.metal_f0("chrome"))
    assert abs(mat.props["diffuse"].as_unit()[0] - 0.556) < 2e-3   # not 0.771


def test_brushed_without_metal_unchanged():
    b, rt = mock_pymxs.install()
    mat = b.build_material(MAPS, "B", "metal_brushed")
    assert "texmap_diffuse_multiplier" not in mat.props
    assert _close(mat.props["reflection"].as_unit(), (1.0, 1.0, 1.0))


def test_brushed_with_gold_is_f0_mode():
    b, rt = mock_pymxs.install()
    mat = b.build_material(MAPS, "B", "metal_brushed", metal="gold")
    assert mat.props["texmap_diffuse_multiplier"] == 30.0
    assert _close(mat.props["diffuse"].as_unit(), matphys.metal_f0("gold"))


def test_metalness_map_keeps_map_mode():
    b, rt = mock_pymxs.install()
    maps = dict(MAPS, metalness="C:/fake/metalness.png")
    mat = b.build_material(maps, "B", "metal_brushed", metal="gold")
    assert "texmap_diffuse_multiplier" not in mat.props


def test_unknown_metal_raises():
    b, rt = mock_pymxs.install()
    with pytest.raises(ValueError):
        b.build_material(MAPS, "B", "metal_brushed", metal="unobtainium")


def test_glass_clear_fog_mm_scene():
    b, rt = mock_pymxs.install()
    mat = b.build_material(MAPS, "G", "glass_clear")
    p = mat.props
    assert _close(p["refraction_fogColor"].as_unit(), (0.907, 0.970, 0.970),
                  0.005)
    # V-Ray reads fog per cm (refraction_fogUnitsScale_on): depth = 6 mm
    assert p["refraction_fogUnitsScale_on"] is True
    assert p["refraction_fogDepth"] == pytest.approx(0.6, abs=1e-9)
    assert p["refraction_ior"] == 1.52


def test_glass_clear_fog_cm_scene():
    b, rt = mock_pymxs.install(system_unit="cm")
    mat = b.build_material(MAPS, "G", "glass_clear")
    p = mat.props
    # same 0.6 cm depth in a cm scene: no per-scene-unit maths any more
    assert p["refraction_fogDepth"] == pytest.approx(0.6, abs=1e-9)
    assert _close(p["refraction_fogColor"].as_unit(), (0.907, 0.970, 0.970),
                  0.005)


def test_water_fog():
    b, rt = mock_pymxs.install()
    mat = b.build_material(MAPS, "W", "water")
    p = mat.props
    assert _close(p["refraction_fogColor"].as_unit(), (0.712, 0.945, 0.991),
                  0.005)
    assert p["refraction_fogDepth"] == pytest.approx(100.0, abs=1e-9)  # 1 m of water


def test_gemstone_fog_through_matphys():
    """Recipe fog_color = T at thickness_mm (10 mm); fog depth = 1 cm in
    every scene unit, like every glass (V-Ray reads fog per cm)."""
    b, rt = mock_pymxs.install()
    mat = b.build_material(MAPS, "S", "gemstone")
    p = mat.props
    assert _close(p["refraction_fogColor"].as_unit(), (0.97, 0.99, 1.0), 0.003)
    assert p["refraction_fogDepth"] == pytest.approx(1.0, abs=1e-9)
    b, rt = mock_pymxs.install(system_unit="m")
    p = b.build_material(MAPS, "S", "gemstone").props
    assert p["refraction_fogDepth"] == pytest.approx(1.0, abs=1e-9)


def test_manifest_unknown_metal(tmp_path):
    b, rt = mock_pymxs.install()
    mf = {"name": "X", "class": "metal_brushed", "metal": "nope",
          "maps": _write_maps(tmp_path)}
    path = tmp_path / "m.json"
    path.write_text(json.dumps(mf))
    with pytest.raises(ValueError):
        b.build_from_manifest(str(path))


def test_manifest_metal_honoured(tmp_path):
    b, rt = mock_pymxs.install()
    mf = {"name": "X", "class": "metal_brushed", "metal": "copper",
          "maps": _write_maps(tmp_path)}
    path = tmp_path / "m.json"
    path.write_text(json.dumps(mf))
    b.build_from_manifest(str(path))
    mat = rt.meditMaterials[0]
    assert mat.props["texmap_diffuse_multiplier"] == 30.0


def test_gemstone_tint_deepens_fog_colour():
    b, rt = mock_pymxs.install()
    plain = b.build_material(MAPS, "S", "gemstone").props["refraction_fogColor"].as_unit()
    b, rt = mock_pymxs.install()
    tinted = b.build_material(MAPS, "S", "gemstone",
                              tint=(0.8, 0.5, 1.0)).props["refraction_fogColor"].as_unit()
    assert tinted[1] < plain[1] - 0.3 and tinted[2] == pytest.approx(plain[2], abs=0.01)
