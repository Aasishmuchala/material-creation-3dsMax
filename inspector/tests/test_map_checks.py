import numpy as np
import pytest

from material_inspector.core import map_checks as mc


def noise(n=128, seed=0, smooth=4):
    """Tileable smooth noise in [0,1] (periodic by construction via FFT filtering)."""
    r = np.random.default_rng(seed).random((n, n))
    f = np.fft.fft2(r)
    ky = np.fft.fftfreq(n)[:, None]; kx = np.fft.fftfreq(n)[None, :]
    f *= np.exp(-(kx ** 2 + ky ** 2) * (smooth * 20) ** 2 / 2)
    out = np.real(np.fft.ifft2(f))
    out = (out - out.min()) / (out.max() - out.min())
    return out[..., None].astype(np.float32)


def test_seamless_tile_passes_and_seam_fails():
    a = noise()
    assert mc.check_seam(a, "m", "x") == []
    # a non-tileable edge: brightness ramps across the tile, so only the wrap has the jump
    b = np.clip(a + 0.3 * np.linspace(0, 1, a.shape[1])[None, :, None], 0, 1)
    assert mc.seam_score(b) > mc.seam_score(a)
    assert mc.check_seam(b, "m", "x")[0].rule_id == "M005"


def test_step_that_recurs_inside_the_tile_is_not_a_seam():
    # half the tile offset: the wrap step equals the mid-tile step (a 2-plank / 2-tile layout),
    # so the border is not unusual for this tile (stress B1)
    a = noise()
    b = a.copy()
    b[:, : b.shape[1] // 2] = np.clip(b[:, : b.shape[1] // 2] + 0.3, 0, 1)
    assert mc.check_seam(b, "m", "x") == []


def test_albedo_dark_and_bright_fractions():
    dark = np.full((32, 32, 3), 0.05, np.float32)
    assert mc.check_albedo(dark, "m", "a")[0].severity.value == "error"
    ok = np.full((32, 32, 3), 0.5, np.float32)
    assert mc.check_albedo(ok, "m", "a") == []
    bright = np.full((32, 32, 3), 0.99, np.float32)
    assert mc.check_albedo(bright, "m", "a")[0].rule_id == "M002"


def test_albedo_metal_pixels_excluded():
    dark = np.full((32, 32, 3), 0.05, np.float32)
    mask = np.ones((32, 32), np.float32)
    assert mc.check_albedo(dark, "m", "a", metal_mask=mask) == []


def test_constant_map_and_metal_bimodal():
    assert mc.check_constant(np.full((16, 16, 1), 0.5, np.float32), "m", "r", "roughness")
    assert mc.check_constant(noise(), "m", "r", "roughness") == []
    assert mc.check_metal_bimodal(np.full((16, 16, 1), 0.5, np.float32), "m", "x")
    binary = (noise() > 0.5).astype(np.float32)
    assert mc.check_metal_bimodal(binary, "m", "x") == []


def normal_from_height(h, strength=8.0, directx=False):
    g = h[..., 0].astype(np.float64)
    gy, gx = np.gradient(g)
    nx, ny, nz = -gx * strength, gy * strength, np.ones_like(g)
    if directx:
        ny = -ny
    l = np.sqrt(nx ** 2 + ny ** 2 + nz ** 2)
    return (np.dstack([nx / l, ny / l, nz / l]) * 0.5 + 0.5).astype(np.float32)


@pytest.mark.parametrize("dx,expected", [(False, "opengl"), (True, "directx")])
def test_normal_convention_detection(dx, expected):
    h = noise(seed=3)
    n = normal_from_height(h, directx=dx)
    cx, cy = mc.normal_height_agreement(n, h)
    assert cx > 0.9 and (cy > 0.9 if not dx else cy < -0.9)
    info = mc.check_normal_convention(n, h, "m", "n")
    assert info[0].rule_id == "M008" and expected.upper() in info[0].message
    wrong = "directx" if expected == "opengl" else "opengl"
    assert mc.check_normal_convention(n, h, "m", "n", expected=wrong)[0].rule_id == "M007"


def test_unrelated_normal_and_height():
    n = normal_from_height(noise(seed=1))
    h = noise(seed=99)
    assert mc.check_normal_convention(n, h, "m", "n")[0].rule_id == "M006"
