"""AI-generator fault signatures: M010 baked lighting, M013 upscaled, M012 height polarity,
widened M003, and the R020 aggregate (M003 + M004 only until M010/M013 are calibrated)."""
import numpy as np
import pytest
from PIL import Image

from material_inspector.core import map_checks as mc
from material_inspector.core.inspector import InspectorOptions, inspect
from material_inspector.core.model import ColorSpace, MaterialRecord, Renderer, SlotRole, TextureRef
from tests.test_map_checks import noise, normal_from_height

N = 1024


def flat_with_noise(seed=0, amount=0.08):
    rng = np.random.default_rng(seed)
    g = 0.5 + amount * (rng.random((N, N)) - 0.5) * 2
    return np.repeat(g[..., None], 3, axis=-1).astype(np.float32)


def ids(findings):
    return sorted(f.rule_id for f in findings)


def bicubic(a2d, side):
    return np.asarray(Image.fromarray(a2d.astype(np.float32)).resize((side, side), Image.BICUBIC))


# ---------------------------------------------------------------- M010
def rgb(g):
    return np.repeat(np.clip(g, 0, 1)[..., None], 3, axis=-1).astype(np.float32)


def grain(seed, amount):
    return amount * (np.random.default_rng(seed).random((N, N)) - 0.5) * 2


def smooth_field(seed, cells):
    """Periodic smooth noise, ~``cells`` blobs per side, zero mean, unit std."""
    f = np.fft.fft2(np.random.default_rng(seed).standard_normal((N, N)))
    k = np.sqrt(np.fft.fftfreq(N)[:, None] ** 2 + np.fft.fftfreq(N)[None, :] ** 2)
    out = np.real(np.fft.ifft2(f * np.exp(-(k * N / cells) ** 2 / 2)))
    return out / out.std()


def planks(values, seed=20):
    # monotonic plank values: the hardest case, a stepped "ramp" across the map
    col = np.repeat(np.asarray(values), N // len(values))
    return rgb(np.tile(col[None, :], (N, 1)) * (1 + grain(seed, 0.04)))


def stone_tiles(seed=21, n=3, var=0.10):
    vals = 0.5 * (1 + np.random.default_rng(seed).uniform(-var, var, (n, n)))
    idx = np.arange(N) * n // N
    return rgb(vals[idx[:, None], idx[None, :]] * (1 + grain(seed + 1, 0.03)))


def bricks(seed=22, rows=8, per_row=4, var=0.08, mortar=6):
    yy, xx = np.mgrid[0:N, 0:N]
    bh, bw = N // rows, N // per_row
    row = yy // bh
    xs = (xx + (row % 2) * (bw // 2)) % N
    vals = 0.45 * (1 + np.random.default_rng(seed).uniform(-var, var, (rows, per_row)))
    g = np.where(((yy % bh) < mortar) | ((xs % bw) < mortar), 0.6, vals[row, xs // bw])
    return rgb(g * (1 + grain(seed + 1, 0.05)))


def marble(seed=23, var=0.06):
    return rgb(0.7 * (1 + var * smooth_field(seed, 6)) * (1 + grain(seed + 1, 0.02)))


def concrete(seed=24, var=0.05):
    # mottling at 1/8 of the tile (±4-5 %)
    return rgb(0.5 * (1 + var * smooth_field(seed, 8)) * (1 + grain(seed + 1, 0.04)))


def lit(a, mult):
    """Multiply scene-linear light into an sRGB albedo."""
    return mc._linear_to_srgb(mc._srgb_to_linear(a.astype(np.float64)) * mult[..., None]).astype(np.float32)


def radius():
    yy, xx = np.mgrid[0:N, 0:N]
    return np.sqrt((xx - N / 2) ** 2 + (yy - N / 2) ** 2) / (N / 2 * np.sqrt(2))


def test_flat_albedo_has_no_baked_lighting():
    a = flat_with_noise()
    assert mc.smooth_trend(a)[0] < 0.05
    assert mc.check_baked_lighting(a, "m", "a") == []


def test_horizontal_ramp_is_baked_lighting():
    a = flat_with_noise() * np.linspace(0.6, 1.4, N)[None, :, None]
    f = mc.check_baked_lighting(np.clip(a, 0, 1).astype(np.float32), "m", "a")
    assert ids(f) == ["M010"] and f[0].severity.value == "warning"


def test_weak_ramp_is_baked_lighting():
    a = flat_with_noise() * np.linspace(0.85, 1.15, N)[None, :, None]
    assert ids(mc.check_baked_lighting(a.astype(np.float32), "m", "a")) == ["M010"]


@pytest.mark.parametrize("k", [0.4, 0.25])
def test_radial_vignette_is_baked_lighting(k):
    a = flat_with_noise() * (1.0 - k * radius())[..., None]
    assert ids(mc.check_baked_lighting(a.astype(np.float32), "m", "a")) == ["M010"]


@pytest.mark.parametrize("make", [
    lambda: lit(marble(), np.tile(np.linspace(0.7, 1.3, N)[None, :], (N, 1))),
    lambda: lit(concrete(), 1.0 - 0.4 * radius()),
    lambda: lit(planks([0.42, 0.51, 0.47, 0.56]), np.tile(np.linspace(0.7, 1.3, N)[:, None], (1, N))),
], ids=["marble+ramp", "concrete+vignette", "planks+cross-ramp"])
def test_light_baked_over_texture_is_flagged(make):
    assert ids(mc.check_baked_lighting(make(), "m", "a")) == ["M010"]


@pytest.mark.parametrize("make", [
    lambda: planks([0.42, 0.47, 0.51, 0.56]),
    lambda: stone_tiles(),
    lambda: bricks(),
    lambda: marble(),
    lambda: concrete(),
    lambda: planks([0.20, 0.23, 0.25, 0.28]),
], ids=["wood-planks", "stone-tiles", "brick", "marble", "concrete-mottling", "dark-planks"])
def test_textured_albedo_is_not_baked_lighting(make):
    # review defect #2: each of these fired the old p95-p05 spread score (0.27-0.73)
    assert mc.check_baked_lighting(make(), "m", "a") == []


def test_texture_blobs_are_not_baked_lighting():
    # Tileable noise(128) blobs repeated across a 1024 map at 8 % contrast.
    blobs = np.tile(noise(128)[..., 0], (N // 128, N // 128))
    a = np.repeat((0.5 + 0.08 * (blobs - 0.5))[..., None], 3, axis=-1).astype(np.float32)
    assert mc.check_baked_lighting(a, "m", "a") == []


# ---------------------------------------------------------------- M013
def q8(a):
    return (np.round(np.clip(a, 0, 1) * 255) / 255).astype(np.float32)[..., None]


def gauss_blur(g, sigma):
    k2 = np.fft.fftfreq(g.shape[0])[:, None] ** 2 + np.fft.fftfreq(g.shape[1])[None, :] ** 2
    return np.real(np.fft.ifft2(np.fft.fft2(g) * np.exp(-2 * np.pi ** 2 * sigma ** 2 * k2)))


def test_native_noise_is_not_upscaled():
    a = np.random.default_rng(1).random((N, N, 1)).astype(np.float32)
    assert mc.upscale_score(a)[0] > 0.5
    assert mc.check_upscaled(a, "m", "r") == []


@pytest.mark.parametrize("src,interp", [(256, Image.BICUBIC), (128, Image.BICUBIC), (171, Image.BICUBIC),
                                        (256, Image.BILINEAR)], ids=["4x-bicubic", "8x-bicubic",
                                                                     "6x-bicubic", "4x-bilinear"])
def test_real_upscale_is_flagged(src, interp):
    small = np.random.default_rng(2).random((src, src)).astype(np.float32)
    a = q8(np.asarray(Image.fromarray(small).resize((N, N), interp)))
    f = mc.check_upscaled(a, "m", "r")
    assert ids(f) == ["M013"] and f[0].severity.value == "info"


def test_2x_upscale_is_not_flagged():
    a = bicubic(np.random.default_rng(3).random((512, 512)), N)[..., None]
    assert mc.check_upscaled(a, "m", "r") == []


def test_small_maps_make_no_resolution_claim():
    a = bicubic(np.random.default_rng(2).random((32, 32)), 256)[..., None]
    assert mc.check_upscaled(a, "m", "r") == []


def _bevel_tiles(tile, bevel):
    yy, xx = np.mgrid[0:N, 0:N]
    d = np.minimum(np.minimum(xx % tile, tile - 1 - xx % tile), np.minimum(yy % tile, tile - 1 - yy % tile))
    return np.clip(d / bevel, 0, 1)


@pytest.mark.parametrize("make", [
    lambda: (((np.mgrid[0:N, 0:N] // (N // 4)).sum(axis=0) % 2).astype(np.float32))[..., None],
    lambda: q8(_bevel_tiles(256, 12)),
    lambda: q8(_bevel_tiles(128, 8)),
    lambda: q8(0.5 + 0.3 * np.sin(6 * np.pi * np.arange(N) / N)[None, :] * np.sin(6 * np.pi * np.arange(N) / N)[:, None]),
    lambda: normal_from_height(gauss_blur(np.random.default_rng(7).random((N, N)), 12)[..., None] * 40),
], ids=["binary-4x4-mask", "bevel-tiles-256", "bevel-tiles-128", "smooth-roughness-3cyc", "normal-sigma12"])
def test_sharp_or_smooth_native_maps_are_not_upscaled(make):
    # review defect #3: each of these fired the old roundtrip-residual score (0.001-0.062)
    assert mc.check_upscaled(make(), "m", "r") == []


def test_load_crop_keeps_native_pixels(tmp_path):
    p = tmp_path / "big.png"
    Image.fromarray((np.random.default_rng(4).random((1500, 1300)) * 255).astype(np.uint8)).save(p)
    a = mc.load_crop(str(p), 1024)
    assert a.shape == (1024, 1024, 1) and a.dtype == np.float32
    small = tmp_path / "small.png"
    Image.fromarray(np.zeros((40, 60, 3), np.uint8)).save(small)
    assert mc.load_crop(str(small)).shape == (40, 60, 3)


# ---------------------------------------------------------------- M012
def test_inverted_height_polarity():
    h = noise(seed=3)
    n = normal_from_height(h)
    f = mc.check_normal_convention(n, 1.0 - h, "m", "n.png", height_label="h.png")
    assert ids(f) == ["M012"] and f[0].severity.value == "error"
    assert f[0].fix.kind == "invert_map" and f[0].fix.target == "h.png" and f[0].texture == "h.png"
    assert not {"M007", "M008"} & set(ids(f))


def test_inverted_height_beats_convention_mismatch():
    h = noise(seed=3)
    f = mc.check_normal_convention(normal_from_height(h, directx=True), 1.0 - h, "m", "n",
                                   expected="opengl")
    assert ids(f) == ["M012"]


# ---------------------------------------------------------------- M003 widened
def test_narrow_span_is_constant():
    a = np.random.default_rng(5).uniform(0.50, 0.52, (64, 64, 1)).astype(np.float32)
    f = mc.check_constant(a, "m", "r", "roughness")
    assert ids(f) == ["M003"]


def test_real_variation_is_not_constant():
    assert mc.check_constant(noise(), "m", "r", "roughness") == []


# ---------------------------------------------------------------- R020 end to end
def _save(path, a):
    a = np.clip(a, 0, 1)
    if a.shape[-1] == 1:
        a = a[..., 0]
    Image.fromarray((a * 255).round().astype(np.uint8)).save(path)
    return str(path)


def _ai_material(tmp_path, name="AI_Oak"):
    ramp = flat_with_noise() * np.linspace(0.6, 1.4, N)[None, :, None]                # M010
    rough = np.full((256, 256, 1), 0.5, np.float32)                                    # M003
    metal = np.full((256, 256, 1), 0.5, np.float32)                                    # M004
    alb = _save(tmp_path / "ai_color.png", ramp)
    rgh = _save(tmp_path / "ai_roughness.png", rough)
    mtl = _save(tmp_path / "ai_metalness.png", metal)
    tex = [TextureRef(SlotRole.BASE_COLOR, alb, ColorSpace.SRGB, "Bitmaptexture", "alb", file_exists=True),
           TextureRef(SlotRole.ROUGHNESS, rgh, ColorSpace.LINEAR, "Bitmaptexture", "rgh", file_exists=True),
           TextureRef(SlotRole.METALNESS, mtl, ColorSpace.LINEAR, "Bitmaptexture", "mtl", file_exists=True)]
    return MaterialRecord(name, Renderer.OPENPBR, "OpenPBRMaterial",
                          params={"base_color": (0.5, 0.5, 0.5), "metalness": 0.0}, textures=tex)


def test_two_signatures_raise_r020(tmp_path):
    found = inspect([_ai_material(tmp_path)])
    got = ids(found)
    assert "M003" in got and "M004" in got and "R020" in got
    r020 = [f for f in found if f.rule_id == "R020"][0]
    assert r020.severity.value == "info" and "M003" in r020.message and "M004" in r020.message
    assert "M010" in got and "M010" not in r020.message      # fires, but is not a signature yet


def test_r020_respects_disabled_rules(tmp_path):
    m = _ai_material(tmp_path)
    assert "R020" not in ids(inspect([m], InspectorOptions(disabled_rules=("M004",))))
    assert "R020" not in ids(inspect([m], InspectorOptions(disabled_rules=("R020",))))


def test_uncalibrated_m010_m013_do_not_raise_r020(tmp_path):
    ramp = flat_with_noise() * np.linspace(0.6, 1.4, N)[None, :, None]                # M010
    rough = bicubic(np.random.default_rng(6).random((256, 256)), N)[..., None]       # M013
    alb = _save(tmp_path / "c.png", ramp)
    rgh = _save(tmp_path / "r.png", 0.3 + 0.4 * rough)
    m = MaterialRecord("Photo", Renderer.OPENPBR, "OpenPBRMaterial",
                       textures=[TextureRef(SlotRole.BASE_COLOR, alb, ColorSpace.SRGB, file_exists=True),
                                 TextureRef(SlotRole.ROUGHNESS, rgh, ColorSpace.LINEAR, file_exists=True)])
    got = ids(inspect([m]))
    assert "M010" in got and "M013" in got and "R020" not in got


def test_metalness_is_not_checked_for_upscaling(tmp_path):
    mask = ((np.mgrid[0:N, 0:N] // (N // 4)).sum(axis=0) % 2).astype(np.float32)[..., None]
    mtl = _save(tmp_path / "m.png", mask)
    m = MaterialRecord("Mask", Renderer.OPENPBR, "OpenPBRMaterial",
                       textures=[TextureRef(SlotRole.METALNESS, mtl, ColorSpace.LINEAR, file_exists=True)])
    assert "M013" not in ids(inspect([m]))


def test_one_signature_is_not_r020(tmp_path):
    rgh = _save(tmp_path / "r.png", np.full((256, 256, 1), 0.5, np.float32))
    m = MaterialRecord("Flat", Renderer.VRAY, "VRayMtl",
                       textures=[TextureRef(SlotRole.ROUGHNESS, rgh, ColorSpace.LINEAR, file_exists=True)])
    got = ids(inspect([m]))
    assert "M003" in got and "R020" not in got
