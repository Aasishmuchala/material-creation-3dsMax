"""Core tests — map derivation + recipe table integrity (no Max needed)."""
import json
import os
import subprocess
import sys

import numpy as np
import pytest
from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from core import maps as M  # noqa: E402
from core.recipes import RECIPES, RESOLUTIONS, class_choices, get_recipe  # noqa: E402


# ---------- recipes ----------

REQUIRED_KEYS = {"label", "ior", "metalness", "base_roughness",
                 "roughness_variation", "bump_amount", "refraction",
                 "two_sided", "opacity", "reflect_color"}


def test_all_recipes_complete():
    for name, r in RECIPES.items():
        missing = REQUIRED_KEYS - set(r)
        assert not missing, f"{name} missing {missing}"


def test_physical_sanity():
    for name, r in RECIPES.items():
        assert 1.0 <= r["ior"] <= 2.5, name
        assert 0.0 <= r["metalness"] <= 1.0, name
        assert 0.0 < r["base_roughness"] <= 1.0, name
        # bump_amount is a 0-100 percentage (V-Ray default 30, ~100 = full),
        # NOT a 0-1 multiplier. A value < 1 (but non-zero) would render
        # effectively flat; exactly 0 is a legitimate "no bump" (emissive/glass).
        assert r["bump_amount"] == 0 or 1.0 <= r["bump_amount"] <= 200.0, (
            f"{name} bump scale wrong")
        refr = r["refraction"]
        if refr:
            # fog must stay near-white (the saturated-fog trap)
            assert min(refr["fog_color"]) > 0.9, f"{name} fog too saturated"
            assert refr["fog_mult"] <= 0.5, name


def test_foliage_rules():
    r = get_recipe("foliage")
    assert r["refraction"] is None, "leaves must never refract"
    assert r["two_sided"], "leaves need 2-sided translucency"
    assert r["opacity"], "leaves need opacity cutout"


def test_class_choices_order_and_unknown():
    keys = [k for k, _ in class_choices()]
    assert keys == list(RECIPES)
    with pytest.raises(KeyError):
        get_recipe("nope")


def test_resolutions():
    assert RESOLUTIONS == {"2k": 2048, "4k": 4096, "8k": 8192}


# ---------- map derivation ----------

@pytest.fixture(scope="module")
def ref_image(tmp_path_factory):
    """Synthetic wood-ish reference: planks + noise + a lighting gradient."""
    rng = np.random.default_rng(7)
    size = 256
    y, x = np.mgrid[0:size, 0:size].astype(np.float32) / size
    planks = ((np.sin(x * 40) * 0.5 + 0.5) > 0.85).astype(np.float32) * 0.3
    base = np.stack([0.55 + 0.1 * np.sin(y * 90), 0.38 * np.ones_like(x),
                     0.24 * np.ones_like(x)], axis=-1)
    lighting = (0.6 + 0.4 * x)[..., None]  # baked side-light to de-light
    img = np.clip((base - planks[..., None] * 0.2
                   + rng.normal(0, 0.03, (size, size, 1))) * lighting, 0, 1)
    p = tmp_path_factory.mktemp("ref") / "wood.png"
    Image.fromarray((img * 255).astype(np.uint8)).save(p)
    return str(p)


def test_generate_maps_full_set(ref_image, tmp_path):
    out = M.generate_maps(ref_image, str(tmp_path), mclass="wood_exterior",
                          resolution="2k", seamless=True)
    for key in ("albedo", "roughness", "normal", "height", "ao"):
        assert key in out and os.path.isfile(out[key]), key
        im = Image.open(out[key])
        assert im.size == (2048, 2048), key
    assert "opacity" not in out  # wood has no cutout


def test_foliage_gets_opacity(ref_image, tmp_path):
    out = M.generate_maps(ref_image, str(tmp_path), mclass="foliage",
                          resolution="2k")
    assert "opacity" in out


def test_foliage_rgb_input_warns_and_is_opaque(tmp_path):
    """An opaque RGB leaf photo can't yield a cutout — must warn, not pretend."""
    p = tmp_path / "leaf_rgb.png"
    Image.fromarray((np.zeros((32, 32, 3)) + 100).astype("uint8")).save(p)
    warns = []
    out = M.generate_maps(str(p), str(tmp_path / "o"), mclass="foliage",
                          resolution="2k", warnings=warns)
    op = np.asarray(Image.open(out["opacity"]).convert("L"))
    assert int(op.min()) == 255, "no alpha should fall back to fully opaque"
    assert any("alpha" in w.lower() for w in warns), "must warn about no alpha"


def test_foliage_rgba_input_uses_alpha(tmp_path):
    """A real transparent leaf PNG must drive the opacity cutout."""
    rgba = np.zeros((40, 40, 4), dtype="uint8")
    rgba[..., :3] = 120
    rgba[10:30, 10:30, 3] = 255  # a square alpha island
    p = tmp_path / "leaf_rgba.png"
    Image.fromarray(rgba, "RGBA").save(p)
    out = M.generate_maps(str(p), str(tmp_path / "o2"), mclass="foliage",
                          resolution="2k", seamless=False)
    op = np.asarray(Image.open(out["opacity"]).convert("L"))
    assert op.max() > 200 and op.min() < 60, "alpha not preserved into opacity"


def test_albedo_delights_gradient(ref_image, tmp_path):
    """Left/right brightness gap must shrink vs. the lit source image."""
    out = M.generate_maps(ref_image, str(tmp_path), mclass="generic",
                          resolution="2k", seamless=False)
    src = np.asarray(
        Image.open(ref_image).convert("L"), dtype=np.float32)
    alb = np.asarray(
        Image.open(out["albedo"]).convert("L"), dtype=np.float32)
    def lr_gap(a):
        w = a.shape[1]
        return abs(float(a[:, : w // 4].mean()) -
                   float(a[:, -w // 4:].mean()))
    assert lr_gap(alb) < lr_gap(src) * 0.5, "de-lighting did not flatten"


def test_seamless_edges_match():
    rng = np.random.default_rng(3)
    arr = rng.random((128, 128, 3)).astype(np.float32)
    s = M.make_seamless(arr)
    assert np.allclose(s[:, 0], s[:, -1], atol=0.02), "L/R edges differ"
    assert np.allclose(s[0, :], s[-1, :], atol=0.02), "T/B edges differ"
    # interior untouched
    assert np.allclose(s[40:88, 40:88], arr[40:88, 40:88])


def test_seamless_grayscale_shape():
    arr = np.random.default_rng(1).random((64, 64)).astype(np.float32)
    s = M.make_seamless(arr)
    assert s.shape == (64, 64)


def test_normal_map_is_unit_and_blueish():
    h = np.zeros((64, 64), dtype=np.float32)
    h[:, 32:] = 1.0  # a step edge
    n = M.derive_normal(h)
    vec = n * 2.0 - 1.0
    lengths = np.sqrt((vec ** 2).sum(axis=-1))
    assert np.allclose(lengths, 1.0, atol=1e-4)
    assert n[..., 2].mean() > 0.8  # mostly facing +Z (blue)


def test_generated_normal_map_tiles(ref_image, tmp_path):
    """The normal map from the full seamless pipeline must tile — guards the
    np.gradient border-seam bug the review found (normal wasn't seamless even
    though height was)."""
    out = M.generate_maps(ref_image, str(tmp_path), mclass="stone",
                          resolution="2k", seamless=True)
    n = np.asarray(Image.open(out["normal"]), dtype=np.float32)
    assert np.allclose(n[0, :], n[-1, :], atol=2.0), "top/bottom seam"
    assert np.allclose(n[:, 0], n[:, -1], atol=2.0), "left/right seam"


def test_roughness_range_respects_recipe(ref_image, tmp_path):
    out = M.generate_maps(ref_image, str(tmp_path), mclass="marble",
                          resolution="2k", seamless=False)
    r = np.asarray(Image.open(out["roughness"]), dtype=np.float32) / 255.0
    recipe = get_recipe("marble")
    hi = recipe["base_roughness"] + recipe["roughness_variation"] + 0.02
    assert float(r.max()) <= hi, "roughness exceeds recipe band"


# ---------- CLI ----------

def test_cli_end_to_end(ref_image, tmp_path):
    out_dir = str(tmp_path / "cli_out")
    proc = subprocess.run(
        [sys.executable, os.path.join(REPO, "forge_cli.py"), ref_image,
         "--name", "Test_Wood", "--type", "wood_exterior", "--res", "2k",
         "--out", out_dir],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    assert result["ok"]
    with open(result["manifest"], encoding="utf-8") as f:
        mf = json.load(f)
    assert mf["name"] == "Test_Wood"
    assert os.path.isfile(mf["maps"]["albedo"])
