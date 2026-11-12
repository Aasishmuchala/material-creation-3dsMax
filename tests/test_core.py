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

import matphys  # noqa: E402
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


class _Stop(Exception):
    """Raised by a spy to stop generate_maps once a test has what it needs."""


def _forge_until(monkeypatch, name, *args, **kwargs):
    """Run generate_maps(*args, **kwargs) up to its first call of M.<name>
    and return that call's arguments; the rest of the forge is skipped,
    which keeps the pipeline tests fast."""
    got = []

    def spy(*a, **k):
        got.append(a)
        raise _Stop

    monkeypatch.setattr(M, name, spy)
    with pytest.raises(_Stop):
        M.generate_maps(*args, **kwargs)
    monkeypatch.undo()
    return got[0]


# ---------- drift flattening ----------

_LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def _chromaticity(lin):
    return lin / np.maximum(lin.sum(axis=-1, keepdims=True), 1e-9)


def _low_cv(lin, n):
    y = (lin @ _LUMA).astype(np.float32)
    return float(np.std(M._gblur(y, n / 16.0)) / y.mean())


def test_flatten_drift_removes_lighting_drift_keeps_detail_and_colour():
    """Leftover lighting at tile scale (the band pattern that read as
    patchwork on a tiled sofa) goes; the weave, a mid-scale slub stripe, the
    mean and every pixel's colour stay."""
    rng = np.random.default_rng(11)
    n = 512
    yy, xx = np.mgrid[0:n, 0:n] / float(n)
    weave = 1.0 + 0.15 * np.sign(np.sin(2 * np.pi * 64 * xx) * np.sin(2 * np.pi * 64 * yy))
    weave = weave + 0.05 * rng.standard_normal((n, n))
    slub = np.cos(2 * np.pi * 24 * xx)                  # period 1/24 of the tile
    drift = 1.0 + 0.15 * np.cos(2 * np.pi * (xx + 0.3)) * np.cos(2 * np.pi * 2 * yy)
    y = 0.3 * weave * (1.0 + 0.08 * slub) * drift
    lin = (y[..., None] * np.array([1.0, 0.85, 0.7])).astype(np.float32)
    out = M._srgb_to_lin(M.flatten_drift(M._lin_to_srgb(lin)))
    y_in, y_out = lin @ _LUMA, out @ _LUMA

    def low(a):
        return M._gblur(a.astype(np.float32), n / 16.0)

    assert _low_cv(out, n) < 0.25 * _low_cv(lin, n)
    fine_in = float(np.std(y_in - low(y_in)) / y_in.mean())
    fine_out = float(np.std(y_out - low(y_out)) / y_out.mean())
    assert fine_out > 0.85 * fine_in, (fine_in, fine_out)
    # the slub stripe is texture, not drift: a 4x narrower low-pass ate half
    amp = lambda a: 2.0 * float((a * slub).mean() / a.mean())
    assert amp(y_out) > 0.9 * amp(y_in), (amp(y_in), amp(y_out))
    assert abs(y_out.mean() / y_in.mean() - 1.0) < 1e-3
    # one achromatic gain: no pixel changes hue or chromaticity
    assert np.abs(_chromaticity(out) - _chromaticity(lin)).max() < 2e-3
    # still tiles: the wrap step is like any neighbour step
    assert np.abs(y_out[:, 0] - y_out[:, -1]).mean() < 1.5 * np.abs(np.diff(y_out, axis=1)).mean()


def test_flatten_drift_never_moves_hue():
    """Mixed light can tint one side of a photo; the flatten only evens out
    brightness, so neither a pixel's hue nor the mean colour can move (the
    per-channel divide shifted both)."""
    n = 512
    yy, xx = np.mgrid[0:n, 0:n] / float(n)
    tint = 0.05 * np.cos(2 * np.pi * xx)                 # warm left, cool right
    lum = 0.25 * (1.0 + 0.12 * np.cos(2 * np.pi * yy))
    lin = np.stack([lum * (1 + tint), lum * 0.9 * np.ones_like(tint),
                    lum * 0.75 * (1 - tint)], -1).astype(np.float32)
    out = M._srgb_to_lin(M.flatten_drift(M._lin_to_srgb(lin)))
    assert np.abs(_chromaticity(out) - _chromaticity(lin)).max() < 2e-3
    m_in, m_out = lin.reshape(-1, 3).mean(0), out.reshape(-1, 3).mean(0)
    assert np.allclose(m_out / m_out.sum(), m_in / m_in.sum(), atol=1e-3)
    assert _low_cv(out, n) < 0.25 * _low_cv(lin, n)


def test_flatten_drift_keeps_a_pored_surface_even():
    """Sparse near-black pores (cork, leather, soil) pulled a low-pass of
    log luminance down where they cluster, and the gain blew that up into
    blotches; the low-pass of linear light stays even."""
    rng = np.random.default_rng(1)
    n = 512
    base = 0.25 * (1.0 + 0.05 * rng.standard_normal((n, n)))
    seeds = rng.random((n, n)) < 0.03 / 9.0
    pores = np.zeros((n, n), bool)
    for dy in range(3):
        for dx in range(3):
            pores |= np.roll(seeds, (dy, dx), axis=(0, 1))
    lin = (np.where(pores, 0.001, base)[..., None] * np.array([1.0, 0.95, 0.85])).astype(np.float32)
    out = M._srgb_to_lin(M.flatten_drift(M._lin_to_srgb(lin)))
    assert _low_cv(out, n) <= _low_cv(lin, n)


def test_flatten_drift_lifts_a_stain_at_most_a_quarter():
    """A stain or knot wider than the weave reads as drift to the low-pass,
    but it is a feature: the gain is clamped, so it is lifted by at most
    25 % (unclamped, this one came up by 57 %)."""
    rng = np.random.default_rng(4)
    n = 512
    yy, xx = np.mgrid[0:n, 0:n] / float(n)
    stain = 1.0 - 0.6 * np.exp(-((xx - 0.4) ** 2 + (yy - 0.6) ** 2) / (2 * (1 / 24.0) ** 2))
    y = 0.3 * (1.0 + 0.05 * rng.standard_normal((n, n))) * stain
    lin = (y[..., None] * np.array([1.0, 0.9, 0.8])).astype(np.float32)
    out = M._srgb_to_lin(M.flatten_drift(M._lin_to_srgb(lin)))
    c = (slice(int(0.6 * n) - 4, int(0.6 * n) + 5), slice(int(0.4 * n) - 4, int(0.4 * n) + 5))
    assert (out[c] @ _LUMA).mean() / (lin[c] @ _LUMA).mean() < 1.27


def _stripes(n, pairs, c1, c2):
    xx = np.arange(n)[None, :] / float(n)
    band = np.mod(xx * pairs, 1.0) < 0.5
    rgb = np.repeat(np.where(band[..., None], np.array(c1), np.array(c2)) / 255.0, n, axis=0)
    weave = 1.0 + 0.04 * np.sign(np.sin(2 * np.pi * 100 * xx) * np.sin(2 * np.pi * 100 * xx.T))
    return np.clip(rgb * weave[..., None], 0, 1).astype(np.float32), band[0]


@pytest.mark.parametrize("pairs, c1, c2", [(3, (35, 45, 90), (235, 235, 230)),     # navy / white
                                           (4, (195, 56, 56), (224, 218, 195)),    # red / cream
                                           (3, (120, 120, 122), (235, 235, 232)),  # grey / white
                                           (3, (180, 160, 130), (215, 200, 170)),  # tan / beige
                                           (8, (180, 160, 130), (215, 200, 170))])
def test_flatten_drift_leaves_stripe_fabrics_alone(pairs, c1, c2):
    """A 3-4 cycle stripe is pattern, not lighting, and no frequency test can
    tell them apart: wandering colour or a tone range beyond any leftover
    lighting skips the flatten, with a warning."""
    srgb, band = _stripes(512, pairs, c1, c2)
    warns = []
    out = M.flatten_drift(srgb, warnings=warns)
    for m in (band, ~band):
        assert np.abs(out[:, m].mean(axis=(0, 1)) - srgb[:, m].mean(axis=(0, 1))).max() * 255 < 1
    assert any("flattening skipped" in w for w in warns)


def _two_tone(n, cycles, c1, c2):
    """Two sRGB colours blended smoothly (a cosine in linear light) `cycles`
    times across the tile, on a fine weave: a dip-dye, or shading."""
    xx = np.arange(n)[None, :] / float(n)
    w = (0.5 + 0.5 * np.cos(2 * np.pi * cycles * xx))[..., None]
    lin = (w * M._srgb_to_lin(np.array(c1, np.float32) / 255.0)
           + (1 - w) * M._srgb_to_lin(np.array(c2, np.float32) / 255.0))
    weave = 1.0 + 0.04 * np.sign(np.sin(2 * np.pi * 100 * xx) * np.sin(2 * np.pi * 100 * xx.T))
    return M._lin_to_srgb(np.repeat(lin, n, axis=0) * weave[..., None])


@pytest.mark.parametrize("pattern", ["tone-on-tone stripe", "dip-dye", "grey ombre"])
def test_flatten_drift_has_a_skip_for_each_kind_of_pattern(pattern):
    """Each pattern passes the other two tests: a tan and beige stripe keeps
    its colour and a tone range the gain clamp can reach (flattened, its
    stripes moved 15 sRGB levels), a dip-dye of two colours of one tone has
    no tone to speak of, smooth grey shading has no colour and no edges."""
    srgb = {"tone-on-tone stripe": lambda: _stripes(512, 3, (180, 160, 130), (215, 200, 170))[0],
            "dip-dye": lambda: _two_tone(512, 2, (190, 110, 80), (80, 140, 140)),
            "grey ombre": lambda: _two_tone(512, 2, (110, 110, 110), (170, 170, 170))}[pattern]()
    warns = []
    out = M.flatten_drift(srgb, warnings=warns)
    assert np.abs(out - srgb).max() * 255 < 0.5
    assert any("flattening skipped" in w for w in warns)


@pytest.mark.parametrize("light", ["cast shadow", "soft bands"])
def test_flatten_drift_evens_out_light_that_is_not_a_print(light):
    """A shadow falling across the photo steps in sharp edges, but two edges
    are too few for a print; soft bands of light change all the way across,
    not in edges. Both are evened out."""
    n = 512
    xx = np.mgrid[0:n, 0:n][1] / float(n)
    y = 0.3 * {"cast shadow": lambda: np.where((xx > 0.3) & (xx < 0.55), 0.8, 1.0),
               "soft bands": lambda: 1.0 + 0.2 * np.cos(2 * np.pi * 3 * xx)}[light]()
    y = y * (1.0 + 0.02 * np.random.default_rng(2).standard_normal((n, n)))
    lin = (y[..., None] * np.array([1.0, 0.9, 0.8])).astype(np.float32)
    warns = []
    out = M._srgb_to_lin(M.flatten_drift(M._lin_to_srgb(lin), warnings=warns))
    assert not warns
    if light == "cast shadow":
        shade, lit = (xx > 0.35) & (xx < 0.5), (xx < 0.25) | (xx > 0.6)
        assert (out[shade] @ _LUMA).mean() / (out[lit] @ _LUMA).mean() > 0.97      # was 0.8
    else:
        assert _low_cv(out, n) < 0.25 * _low_cv(lin, n)


def _albedo_forged(monkeypatch, path, out_dir, mclass, warnings=None):
    """The 2K albedo generate_maps hands to the albedo clamp: the final
    albedo bar the clamp (in range here), with the rest of the forge skipped."""
    albedo, = _forge_until(monkeypatch, "clamp_albedo", str(path), str(out_dir), mclass=mclass,
                           resolution="2k", warnings=warnings)
    return albedo


def test_stripe_fabric_keeps_both_colours_through_generate_maps(monkeypatch, tmp_path):
    """Red and cream stripes came out of the fabric class both salmon; they
    must now match a class without the flatten, and the artist is told."""
    srgb, _ = _stripes(512, 4, (195, 56, 56), (224, 218, 195))
    p = tmp_path / "stripes.png"
    Image.fromarray((srgb * 255 + 0.5).astype(np.uint8)).save(p)
    warns = []
    fabric = _albedo_forged(monkeypatch, p, tmp_path / "f", "fabric", warns)
    wood = _albedo_forged(monkeypatch, p, tmp_path / "w", "wood_interior")
    assert np.abs(fabric - wood).max() * 255 < 1.0
    assert any("flattening skipped" in w for w in warns)


def test_only_stationary_classes_flatten(monkeypatch, tmp_path):
    """Plank-to-plank tone is real wood; drift in a linen photo is lighting."""
    n = 512
    yy = np.mgrid[0:n, 0:n][0] / float(n)
    rng = np.random.default_rng(5)
    # +-12 % leftover lighting in three bands, in linear light
    y = 0.2 * (1.0 + 0.12 * np.cos(2 * np.pi * 3 * yy)) * (1.0 + 0.15 * rng.standard_normal((n, n)))
    lin = np.clip(y[..., None] * np.array([1.0, 0.9, 0.75]), 0, 1).astype(np.float32)
    p = tmp_path / "drift.png"
    Image.fromarray((M._lin_to_srgb(lin) * 255 + 0.5).astype(np.uint8)).save(p)

    def drift(mclass):
        a = M._luminance(_albedo_forged(monkeypatch, p, tmp_path / mclass, mclass))[::4, ::4]
        return float(np.std(M._gblur(a, a.shape[0] / 16.0)) / a.mean())

    assert RECIPES["fabric"].get("stationary") and not RECIPES["wood_interior"].get("stationary")
    assert drift("fabric") < 0.3 * drift("wood_interior")


# ---------- laid-tile grid re-lay ----------

def _tile_photo(n=512, period=60.0, phase=23.0, grout=4, seed=2):
    """Square tiles of random shades with white grout; the borders cut tiles."""
    rng = np.random.default_rng(seed)
    img = np.zeros((n, n, 3), np.float32)
    ix = np.floor((np.arange(n) + phase) / period).astype(int)
    shade = rng.uniform(0.25, 0.55, (ix.max() + 2, ix.max() + 2))
    img[...] = shade[ix[:, None], ix[None, :]][..., None] * np.array([0.8, 1.0, 0.75])
    img += rng.normal(0, 0.02, img.shape).astype(np.float32)
    on = (np.mod(np.arange(n) + phase, period) < grout)
    img[on, :] = 0.92
    img[:, on] = 0.92
    return np.clip(img, 0, 1)


def _grid_photo(n=1024, px=160.0, py=80.0, phase=(37.0, 21.0), grout=6, grout_val=0.92,
                lo=0.25, hi=0.55, seed=3, angle=0.0, bond=0.0, lit=0.0, bevel=0.0, glint=0.0,
                ribs=0.0):
    """Tiles of random shades with their own x and y period and phase and
    `grout` px joints; `bond` offsets alternate rows (0.5 = running bond)
    and `angle` turns the whole layout. Window light: `lit` brightens the
    left of every tile, `bevel` lights that fraction of the face along the
    left and top edges (+30 %) and shades the right and bottom (-25 %), and
    `glint` adds a highlight of that strength near the upper-left corner.
    `ribs` gives every face four upright ribs of that contrast.
    Returns (photo, tile id per pixel, joint mask)."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)
    c, s = np.cos(np.radians(angle)), np.sin(np.radians(angle))
    xr = c * (xx - n / 2) + s * (yy - n / 2) + n / 2 + phase[0]
    yr = -s * (xx - n / 2) + c * (yy - n / 2) + n / 2 + phase[1]
    row = np.floor(yr / py).astype(int)
    xs = xr + bond * px * (row % 2)
    col = np.floor(xs / px).astype(int)
    u = (np.mod(xs, px) - grout) / (px - grout)              # 0..1 across the tile face
    v = (np.mod(yr, py) - grout) / (py - grout)
    shade = rng.uniform(lo, hi, (64, 64))[row % 64, col % 64]
    shade = shade * (1.0 + lit * (0.5 - np.mod(xs, px) / px)) * (1.0 + ribs * np.cos(8 * np.pi * u))
    if bevel:
        shade = shade * np.where((u < bevel) | (v < bevel), 1.3,
                                 np.where((u > 1 - bevel) | (v > 1 - bevel), 0.75, 1.0))
    img = shade[..., None] * np.array([0.8, 1.0, 0.75]) + rng.normal(0, 0.02, (n, n, 3))
    if glint:
        img += glint * np.exp(-((u - 0.12) ** 2 + (v - 0.12) ** 2) / 0.0018)[..., None]
    joint = (np.mod(xs, px) < grout) | (np.mod(yr, py) < grout)
    img[joint] = grout_val
    return np.clip(img, 0, 1).astype(np.float32), row * 4096 + col, joint


def _wavy_photo(n=1024, p=128.0, grout=8, amp=3.0, seed=3):
    """Handmade tiles: every joint wanders `amp` px either side of its line,
    one wave per tile. Returns (photo, joint mask)."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)

    def joints(t, s, start, phase):
        k = np.round((t - start) / p).astype(int)            # the nearest joint
        return k, t - (k * p + start + amp * np.sin(2 * np.pi * s / p + phase[k % 64]))

    kx, dx = joints(xx, yy, 17.0, rng.uniform(0, 2 * np.pi, 64))
    ky, dy = joints(yy, xx, 41.0, rng.uniform(0, 2 * np.pi, 64))
    joint = (np.abs(dx) < grout / 2.0) | (np.abs(dy) < grout / 2.0)
    shade = rng.uniform(0.25, 0.55, (64, 64))[(ky - (dy < 0)) % 64, (kx - (dx < 0)) % 64]
    img = shade[..., None] * np.array([0.8, 1.0, 0.75]) + rng.normal(0, 0.02, (n, n, 3))
    img[joint] = 0.92
    return np.clip(img, 0, 1).astype(np.float32), joint


def _hex_photo(n=1024, s=60.0, grout=6, seed=3):
    """Pointy-top hexagonal tiles; grout where the nearest centre changes."""
    rng = np.random.default_rng(seed)
    h = grout // 2
    yy, xx = np.mgrid[-h:n + h, -h:n + h].astype(np.float64)
    q = (np.sqrt(3) / 3 * (xx + 17.0) - (yy + 29.0) / 3) / s     # axial coordinates
    r = (2.0 / 3 * (yy + 29.0)) / s
    rq, rr, rs = np.round(q), np.round(r), np.round(-q - r)       # cube rounding
    dq, dr, ds = np.abs(rq - q), np.abs(rr - r), np.abs(rs + q + r)
    fix_q = (dq > dr) & (dq > ds)
    rq = np.where(fix_q, -rr - rs, rq)
    rr = np.where(~fix_q & (dr > ds), -rq - rs, rr)
    ids = (rq * 1000 + rr).astype(int)
    core = ids[h:-h, h:-h]
    joint = ((core != ids[h:-h, 2 * h:]) | (core != ids[h:-h, :-2 * h])
             | (core != ids[2 * h:, h:-h]) | (core != ids[:-2 * h, h:-h]))
    shade = rng.uniform(0.3, 0.55, 4096)[np.mod(core, 4096)]
    img = shade[..., None] * np.array([0.9, 0.55, 0.4]) + rng.normal(0, 0.02, (n, n, 3))
    img[joint] = 0.8
    return np.clip(img, 0, 1).astype(np.float32)


def _noise_photo(sigma, seed, n=2048):
    """Untiled clay or glaze: blurred noise, no joints anywhere."""
    rng = np.random.default_rng(seed)
    a = M._gblur(rng.standard_normal((n, n)).astype(np.float32), sigma)
    a = 0.45 + 0.12 * a / a.std()
    return np.clip(np.stack([a, a * 0.7, a * 0.5], -1), 0, 1).astype(np.float32)


def _carried(joint, x0, x1, y0, y1):
    """Grout px a cut cell carries at its left, right, top and bottom."""
    my, mx = (y0 + y1) // 2, (x0 + x1) // 2
    across = joint[my - 4:my + 4, x0:x1].all(axis=0)
    down = joint[y0:y1, mx - 4:mx + 4].all(axis=1)
    lead = lambda v: v.size if v.all() else int(np.argmin(v))
    return lead(across), lead(across[::-1]), lead(down), lead(down[::-1])


def _seam_joints(lum, nx, ny, width):
    """Bright grout found at every seam of a re-laid map, the wrap included,
    across the middle of every band of the other axis: yields (axis, band,
    seam, joint px as offsets from the seam), `width` (x, y) being the joint
    expected there."""
    n = lum.shape[0]
    for axis, cnt, other, w in ((1, nx, ny, width[0]), (0, ny, nx, width[1])):
        reach = int(2 * w) + 4
        for b in range(other):
            lo, hi = int((b + 0.3) * n / other), int((b + 0.7) * n / other)
            grout = (lum[lo:hi].mean(axis=0) if axis == 1 else lum[:, lo:hi].mean(axis=1)) > 0.7
            for e in (int(round(k * n / cnt)) for k in range(cnt)):
                yield axis, b, e, np.flatnonzero(grout[(np.arange(-reach, reach) + e) % n]) - reach + 0.5


def _assert_one_centred_joint(lum, nx, ny, width, tol):
    """Every seam carries one joint of `width` (+/- tol px), centred on it."""
    for axis, b, e, at in _seam_joints(lum, nx, ny, width):
        w = width[0] if axis == 1 else width[1]
        assert at.size and at[-1] - at[0] + 1 == at.size, (axis, b, e)       # one joint
        assert abs(at.size - w) <= tol, (axis, b, e, at.size, w)
        assert abs(at.mean()) <= 1.0, (axis, b, e, at.mean())                # centred


@pytest.mark.parametrize("grout_val", [0.92, 0.06])        # white and dark grout
def test_grid_plan_cuts_every_tile_at_joint_centres(grout_val):
    """Oblong tiles, x and y with their own period and phase, white or dark
    grout: every pool cell is one whole tile with half a joint on each side.
    Cuts on a joint's edge (or on the shoulder beside dark grout) left seams
    with no joint or a double one, and slivers of the next tile."""
    dark = grout_val < 0.5
    photo, ids, joint = _grid_photo(grout_val=grout_val, lo=0.6 if dark else 0.25,
                                    hi=0.9 if dark else 0.55)
    plan = M.grid_plan(photo, seed=4)
    assert plan is not None and plan["sign"] == (-1 if dark else 1)
    assert not plan["square"] and (plan["nx"], plan["ny"]) == (6, 12)    # 2:1 kept
    assert {t for _, t in plan["cells"]} <= {0, 2}                        # oblong: half turns
    assert len(plan["pool"]) >= 40
    for (x0, x1), (y0, y1) in plan["pool"]:
        assert np.unique(ids[y0:y1, x0:x1][~joint[y0:y1, x0:x1]]).size == 1, "sliver of a tile"
        assert all(abs(g - 3) <= 1 for g in _carried(joint, x0, x1, y0, y1)), (x0, x1, y0, y1)


def test_grid_plan_centres_the_cuts_on_the_unit_photo():
    """The suite's own photo had every cut on a 4 px joint's edge: some
    seams lost the joint, others got two."""
    photo = _tile_photo()
    joint = (np.mod(np.arange(512) + 23.0, 60.0) < 4)
    joint = joint[:, None] | joint[None, :]
    plan = M.grid_plan(photo, seed=4)
    assert plan is not None and plan["nx"] == plan["ny"] == round(512 / 60.0)
    for (x0, x1), (y0, y1) in plan["pool"]:
        assert _carried(joint, x0, x1, y0, y1) == (2, 2, 2, 2)


def test_grid_relay_puts_one_centred_joint_on_every_seam():
    """Every seam of the re-laid map, the wrap included, carries one whole
    joint centred on it, in every band of the other axis."""
    photo, _, _ = _grid_photo()
    plan = M.grid_plan(photo, seed=4)
    lum = M._luminance(M.apply_grid_plan(photo, plan))
    n = lum.shape[0]
    # 6 px joints, scaled with their tile
    _assert_one_centred_joint(lum, plan["nx"], plan["ny"],
                              (6.0 * n / plan["nx"] / 160.0, 6.0 * n / plan["ny"] / 80.0), 1.5)


def test_lay_cells_never_puts_a_tile_beside_itself_across_the_wrap():
    """Tiled, the last column meets the first and the bottom row the top."""
    for seed in range(30):
        cells = M._lay_cells(6, 5, 4, (0, 1, 2, 3), np.random.default_rng(seed))
        k = [c for c, _ in cells]
        for j in range(4):
            for i in range(5):
                assert k[j * 5 + i] != k[j * 5 + (i - 1) % 5]
                assert k[j * 5 + i] != k[((j - 1) % 4) * 5 + i]
    plan = M.grid_plan(_grid_photo()[0], seed=4)
    assert len({c for c, _ in plan["cells"]}) >= 0.6 * len(plan["pool"])


@pytest.mark.parametrize("count", [8, 10, 12])
def test_grid_plan_finds_the_tile_not_a_multiple(count):
    """A frame of whole tiles is periodic over the frame, and a circular
    autocorrelation then locked onto two or three tiles."""
    p = 1024.0 / count
    photo, _, _ = _grid_photo(px=p, py=p, phase=(0.37 * p, 0.61 * p), grout=5, seed=count)
    plan = M.grid_plan(photo, seed=1)
    assert plan is not None and plan["square"] and plan["nx"] == plan["ny"] == count
    for (x0, x1), (y0, y1) in plan["pool"]:
        assert abs((x1 - x0) / p - 1) < 0.05 and abs((y1 - y0) / p - 1) < 0.05


def test_grid_plan_keeps_near_square_tiles_oblong():
    """10 x 11.5 cm tiles were laid square and quarter-turned."""
    photo, _, _ = _grid_photo(px=115.0, py=100.0, phase=(29.0, 47.0), grout=5)
    plan = M.grid_plan(photo, seed=2)
    assert plan is not None and not plan["square"]
    assert {t for _, t in plan["cells"]} <= {0, 2}
    aspect = (1024.0 / plan["nx"]) / (1024.0 / plan["ny"])
    assert abs(aspect / 1.15 - 1) < 0.04, aspect


@pytest.mark.parametrize("sigma, seed", [(6, 4), (12, 7), (25, 1), (50, 0)])
def test_grid_plan_rejects_blurred_noise(sigma, seed):
    """Untiled clay or glaze at 2K: each of these was gridded before, with
    hard seams through every map."""
    assert M.grid_plan(_noise_photo(sigma, seed)) is None


@pytest.mark.parametrize("layout", ["running bond", "half-offset squares", "hex",
                                    "turned 0.5 deg", "turned 1 deg"])
def test_grid_plan_rejects_layouts_it_cannot_cut_straight(layout):
    """Bonds and hex have no straight joint through every band, and a turned
    photo leaves a sliver of the next tile in every cell: all stay as shot."""
    photo = {"running bond": lambda: _grid_photo(px=200.0, py=100.0, bond=0.5)[0],
             "half-offset squares": lambda: _grid_photo(px=150.0, py=150.0, bond=0.5)[0],
             "hex": lambda: _hex_photo(),
             "turned 0.5 deg": lambda: _grid_photo(px=150.0, py=150.0, grout=8, angle=0.5)[0],
             "turned 1 deg": lambda: _grid_photo(px=150.0, py=150.0, grout=8, angle=1.0)[0]}[layout]()
    assert M.grid_plan(photo, seed=1) is None


def test_grid_plan_ignores_untiled_photos():
    rng = np.random.default_rng(1)
    plain = np.clip(0.5 + 0.05 * rng.standard_normal((256, 256, 3)), 0, 1).astype(np.float32)
    assert M.grid_plan(plain) is None


@pytest.mark.parametrize("px, py, grout", [(430.0, 145.0, 10),     # 3:1 brick
                                           (300.0, 150.0, 8)])     # subway tile
def test_grid_plan_rejects_running_bond_at_2k_in_the_band_check(px, py, grout):
    """At 2K both axes of a running bond read as joints (the head joints of
    alternate courses fall on one comb), and only the band check sees that
    each head joint is missing from every other course; without it half the
    cuts ran through bricks. The 1K bonds above fail earlier checks."""
    photo, _, _ = _grid_photo(n=2048, px=px, py=py, grout=grout, bond=0.5, grout_val=0.85,
                              phase=(0.37 * px, 0.21 * py), seed=5)
    lum = M._luminance(photo)
    jx, jy = M._axis_joints(lum.mean(axis=0)), M._axis_joints(lum.mean(axis=1))
    assert jx is not None and jy is not None
    assert M._band_joints(lum, jx, jy, 0) is None
    assert M.grid_plan(photo, seed=1) is None


def _whole_tile_frame(count, seed, n=2048, grout=8, jitter=0.0):
    """A frame of `count` whole square tiles each way, 8 px joints (that
    wander by `jitter` px), shifted by a random wrap: periodic over the
    frame, so its autocorrelation peaks at every multiple of the tile."""
    rng = np.random.default_rng(seed)
    p = n / float(count)
    ex = np.arange(count + 1) * p + rng.normal(0, jitter, count + 1)
    ey = np.arange(count + 1) * p + rng.normal(0, jitter, count + 1)
    t = np.arange(n)
    ix, iy = np.searchsorted(ex, t, side="right") - 1, np.searchsorted(ey, t, side="right") - 1
    shade = 0.45 + 0.15 * rng.random((count + 2, count + 2))
    img = shade[iy[:, None], ix[None, :]][..., None] * np.array([1.0, 0.95, 0.85])
    img[:, np.min(np.abs(t[:, None] - ex[None, :]), axis=1) < grout / 2] = 0.9
    img[np.min(np.abs(t[:, None] - ey[None, :]), axis=1) < grout / 2, :] = 0.9
    img = img + rng.normal(0, 0.02, img.shape)
    img = np.roll(img, (int(rng.integers(n)), int(rng.integers(n))), axis=(0, 1))
    return np.clip(img, 0, 1).astype(np.float32)


@pytest.mark.parametrize("seed", [0, 2])
def test_grid_plan_finds_16_whole_tiles_in_a_2k_frame(seed):
    """With a circular autocorrelation, these frames of 16 whole tiles found
    no tile at all; the zero-padded one decays with lag."""
    plan = M.grid_plan(_whole_tile_frame(16, seed), seed=1)
    assert plan is not None and plan["nx"] == plan["ny"] == 16


def _sliver(joint, cell, reach):
    """Widest strip of the next tile (px) a cut cell carries outside its
    joint, along any of its edges, `reach` px from the corners left out."""
    (x0, x1), (y0, y1) = cell
    m = joint[y0:y1, x0:x1]
    h, w = m.shape
    widest = 0
    for lines in (m[reach:h - reach], m[reach:h - reach, ::-1],
                  m[:, reach:w - reach].T, m[::-1, reach:w - reach].T):
        for row in lines[:, :reach]:
            if not row[0] and row.any():
                widest = max(widest, int(np.argmax(row)))
    return widest


@pytest.mark.parametrize("n, p, amp", [(1024, 128.0, 2.0), (1024, 128.0, 4.0), (1024, 128.0, 6.0),
                                       (2048, 230.0, 3.0), (2048, 230.0, 6.0), (2048, 230.0, 10.0)])
def test_grid_plan_leaves_out_tiles_a_joint_wanders_off(n, p, amp):
    """Handmade joints that wander across the straight cut along a tile's
    length left 57 of 64 cells at 2K with a sliver of the next tile (seams
    re-laid with no joint or two). Such tiles stay out of the pool, which
    leaves these photos as shot from 5 px of wander on 8 px joints; joints
    within ~3 px of the cut keep every tile."""
    photo, joint = _wavy_photo(n=n, p=p, grout=8, amp=amp, seed=4)
    plan = M.grid_plan(photo, seed=1)
    if amp <= 3:
        assert plan is not None and len(plan["pool"]) == (49 if n == 1024 else 64)
    for cell in (plan["pool"] if plan else ()):
        assert _sliver(joint, cell, 20) <= 1, cell


def test_grid_plan_does_not_judge_a_cut_where_glare_hides_the_joint():
    """Glare on the glaze washes a joint out over part of a tile; read there,
    the joint's position is noise, and straight joints lost 8 of 49 tiles."""
    photo, _, _ = _grid_photo(px=128.0, py=128.0, grout=5, phase=(37.0, 53.0))
    rng = np.random.default_rng(7)
    yy, xx = np.mgrid[0:1024, 0:1024]
    for _ in range(6):
        cx, cy = 128 * rng.integers(1, 7) - 34.5, rng.uniform(150, 870)    # on a joint
        photo[(xx - cx) ** 2 + (yy - cy) ** 2 < 22 ** 2] = 0.92
    plan = M.grid_plan(photo, seed=1)
    assert plan is not None and len(plan["pool"]) == 49


def _carried_error(plan, scale, period, grout, phase):
    """|grout px each cut cell carries - half a joint| of a _grid_photo()
    (exact `grout` px joints every `period` from -`phase`), at `scale` plan
    px per photo px."""
    err = []
    for (x0, x1), (y0, y1) in plan["pool"]:
        for c, side, p, o in ((x0, 0, period[0], phase[0]), (x1, 1, period[0], phase[0]),
                              (y0, 0, period[1], phase[1]), (y1, 1, period[1], phase[1])):
            k = np.round((c / scale + o - grout / 2.0) / p)           # the nearest joint
            a, b = scale * (k * p - o), scale * (k * p - o + grout)
            err.append(abs((b - c if side == 0 else c - a) - 0.5 * scale * grout))
    return np.array(err)


def test_forge_lays_the_same_tiles_at_2k_and_4k(monkeypatch, tmp_path):
    """A material approved at 2K and forged at 4K for the final must lay the
    same tiles (the plan and seed came from the resized output, and every
    photo changed), each cut on its joint centre at its own size: 2K cuts
    scaled by 2 doubled their error. The forge stops at the re-lay."""
    shape = dict(px=160.0, py=80.0, phase=(13.0, 29.0), grout=5)
    photo, _, _ = _grid_photo(n=1400, seed=5, **shape)
    p = tmp_path / "tiles.png"
    Image.fromarray((photo * 255 + 0.5).astype(np.uint8)).save(p)
    laid = {}
    for res in ("2k", "4k"):
        rgb, plan = _forge_until(monkeypatch, "apply_grid_plan", str(p), str(tmp_path / res),
                                 mclass="ceramic_glazed", resolution=res)
        n = rgb.shape[0]
        assert _carried_error(plan, n / 1400.0, (160.0, 80.0), 5, (13.0, 29.0)).max() <= 1.25, n
        # the half joints the plan records, which grout_mask() sinks
        assert np.abs(np.array(plan["joints"]) - 2.5 * n / 1400.0).max() <= 1.25, n
        laid[n] = M.apply_grid_plan(M._luminance(rgb), plan), plan
    (lum2, plan2), (lum4, plan4) = laid[2048], laid[4096]
    nx, ny = plan2["nx"], plan2["ny"]
    assert (plan4["nx"], plan4["ny"]) == (nx, ny) and plan4["cells"] == plan2["cells"]
    assert np.abs(lum4.reshape(2048, 2, 2048, 2).mean(axis=(1, 3)) - lum2).mean() < 0.02
    joint = 5.0 * 4096 / 1400.0                                  # px at 4K, scaled with the tile
    _assert_one_centred_joint(lum4, nx, ny, (joint * 4096 / nx / (160.0 * 4096 / 1400.0),
                                             joint * 4096 / ny / (80.0 * 4096 / 1400.0)), 3.0)


def test_a_plan_scales_to_another_size_of_its_photo():
    """apply_grid_plan() and grout_mask() take a plan made on one size of a
    photo to another: the crops, and the joint each cell carries."""
    photo, _, _ = _grid_photo(px=150.0, py=100.0, phase=(41.0, 67.0), grout=6)
    plan = M.grid_plan(photo, seed=3)                       # made at 1024 px
    big = Image.fromarray((photo * 255 + 0.5).astype(np.uint8)).resize((2048, 2048), Image.LANCZOS)
    lum = M._luminance(M.apply_grid_plan(M._to_float(big), plan))
    nx, ny = plan["nx"], plan["ny"]
    width = (12.0 * 2048 / nx / 300.0, 12.0 * 2048 / ny / 200.0)
    _assert_one_centred_joint(lum, nx, ny, width, 3.0)
    mask = M.grout_mask(plan, lum)
    assert (mask[lum > 0.7] >= 0.5).mean() > 0.97
    # with no tone to go by, the mask is the joints the cells carry, scaled
    core = M.grout_mask(plan, np.zeros((2048, 2048), np.float32))
    _assert_one_centred_joint(core, nx, ny, width, 2.0)


def test_grout_mask_follows_wavy_joints():
    """Handmade joints wander off their line within a tile's length: the
    half joints the plan carries alone left a quarter of the grout raised
    and glossy, so the mask also takes grout-toned pixels beside them."""
    photo, joint = _wavy_photo()
    plan = M.grid_plan(photo, seed=2)
    laid = M.apply_grid_plan(photo, plan)
    grout = M.apply_grid_plan(joint.astype(np.float32), plan) > 0.5
    near = grout.copy()
    for d in range(-3, 4):
        near |= np.roll(grout, d, axis=0) | np.roll(grout, d, axis=1)
    mask = M.grout_mask(plan, M._luminance(laid))
    assert (mask[grout] >= 0.5).mean() > 0.97
    assert (mask[~near] >= 0.5).mean() < 0.005


def test_grid_turns_tiles_only_without_a_light_direction():
    """Turned, a window's light on each tile would point four ways: a lit
    bevel opposite a shadowed one, a glint near a corner, falloff across the
    glaze. Bevels and glints sit at the face edge, which a test of the
    middle of each tile never saw. Ribs would lie sideways after a quarter
    turn, though they leave both halves of a tile alike."""
    def plan(**kw):
        return M.grid_plan(_grid_photo(px=128.0, py=128.0, grout=5, **kw)[0], seed=2)

    flat = plan()
    assert flat["turns"] and {1, 3} & {t for _, t in flat["cells"]}
    for kw in (dict(lit=0.4), dict(bevel=0.05), dict(bevel=0.1), dict(glint=0.3), dict(ribs=0.1)):
        lit = plan(**kw)
        assert not lit["turns"] and {t for _, t in lit["cells"]} == {0}, kw
    oblong = M.grid_plan(_grid_photo(bevel=0.05)[0], seed=4)      # a half turn swaps the lit side
    assert not oblong["turns"] and {t for _, t in oblong["cells"]} == {0}


def test_relaid_grout_is_recessed_and_matte(tmp_path):
    """From luminance alone white grout was raised relief as glossy as the
    glaze; re-laid joints are sunk below the tiles and matte."""
    photo, _, _ = _grid_photo(px=128.0, py=128.0, phase=(37.0, 53.0), grout=6)
    p = tmp_path / "tiles.png"
    Image.fromarray((photo * 255 + 0.5).astype(np.uint8)).save(p)
    extra = {}
    out = M.generate_maps(str(p), str(tmp_path / "o"), mclass="ceramic_glazed",
                          resolution="2k", extra=extra)
    nx, ny = extra["grid_tiles"]
    h = np.asarray(Image.open(out["height"]), dtype=np.float32) / 255.0
    r = np.asarray(Image.open(out["roughness"]), dtype=np.float32) / 255.0
    n = h.shape[0]
    edges = [int(round(k * n / nx)) for k in range(nx)]
    seam = np.zeros(n, bool)
    seam[[(e + d) % n for e in edges for d in range(-2, 2)]] = True
    body = np.ones(n, bool)
    body[[(e + d) % n for e in edges for d in range(-24, 24)]] = False
    assert nx == ny
    tile_h = float(np.median(h[np.ix_(body, body)]))
    assert h[np.ix_(body, seam)].max() < tile_h and h[np.ix_(body, seam)].mean() < 0.3 * tile_h
    assert r[np.ix_(body, seam)].mean() > 0.7
    recipe = get_recipe("ceramic_glazed")
    assert r[np.ix_(body, body)].max() <= recipe["base_roughness"] + recipe["roughness_variation"] + 0.02


LAB_REFS = os.path.join(REPO, "tools", "realism_lab", "out", "refs")


@pytest.mark.skipif(not os.path.isfile(os.path.join(LAB_REFS, "zellige_wall.png")),
                    reason="realism-lab reference photos not present")
def test_lab_refs_only_the_zellige_wall_is_a_grid():
    """The lab zellige (handmade, wavy joints, one cut row) is re-laid with a
    joint on every seam; refs that are not laid tiles stay as shot."""
    def load(name):
        src = Image.open(os.path.join(LAB_REFS, name + ".png"))
        return M._to_float(M._resize_square(M._to_rgb8(src), 2048))

    rgb = load("zellige_wall")
    plan = M.grid_plan(rgb, seed=1)
    assert plan is not None and plan["nx"] >= 8 and plan["ny"] >= 8
    # most of its tiles are a little lighter toward the bottom: kept upright
    assert not plan["turns"] and {t for _, t in plan["cells"]} == {0}
    lum = M._luminance(M.apply_grid_plan(rgb, plan))
    n, g = lum.shape[0], max(plan["grout"])
    for cnt, other, axis in ((plan["nx"], plan["ny"], 1), (plan["ny"], plan["nx"], 0)):
        for b in range(other):
            lo, hi = int((b + 0.15) * n / other), int((b + 0.85) * n / other)
            prof = lum[lo:hi].mean(axis=0) if axis == 1 else lum[:, lo:hi].mean(axis=1)
            th = M._tophat(np.r_[prof, prof, prof], 3 * g, plan["sign"])[n:2 * n]
            for e in (int(round(k * n / cnt)) for k in range(cnt)):
                win = (np.arange(-60, 60) + e) % n
                i = int(np.argmax(th[win]))
                assert abs(i - 60) <= max(4, g), (axis, b, e, i - 60)       # a joint on the seam
    for name in ("terracotta_pot", "white_porcelain", "terracotta_floor", "brick_wall",
                 "slate_floor", "linen_sofa", "velvet_sofa", "leather_sofa", "art_canvas",
                 "walnut_table"):
        if os.path.isfile(os.path.join(LAB_REFS, name + ".png")):
            assert M.grid_plan(load(name), seed=1) is None, name


def test_seamless_wrap_is_continuous():
    """Tiling means the last column flows into the first like any two
    neighbours do -- not that the two edges are identical (the old mirror
    blend made them identical, which left a ghost and a flat seam)."""
    rng = np.random.default_rng(3)
    yy, xx = np.mgrid[0:128, 0:128] / 128.0
    arr = (rng.random((128, 128, 3)) * 0.3
           + (0.2 + 0.5 * xx + 0.2 * yy)[..., None]).astype(np.float32)
    s = M.make_seamless(arr)
    inner_x = np.abs(s[:, 1:] - s[:, :-1]).mean()
    inner_y = np.abs(s[1:] - s[:-1]).mean()
    assert np.abs(s[:, 0] - s[:, -1]).mean() < 1.5 * inner_x, "L/R wrap jumps"
    assert np.abs(s[0] - s[-1]).mean() < 1.5 * inner_y, "T/B wrap jumps"
    assert np.abs(arr[:, 0] - arr[:, -1]).mean() > 3 * inner_x  # it was seamy
    # detail survives: the high-pass of the result matches the input's
    hp = lambda a: a - (np.roll(a, 1, 0) + np.roll(a, -1, 0)
                        + np.roll(a, 1, 1) + np.roll(a, -1, 1)) / 4
    c = np.corrcoef(hp(arr)[8:-8, 8:-8].ravel(), hp(s)[8:-8, 8:-8].ravel())[0, 1]
    assert c > 0.98, "interior detail changed"


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
    inner_y = np.abs(n[1:] - n[:-1]).mean()
    inner_x = np.abs(n[:, 1:] - n[:, :-1]).mean()
    assert np.abs(n[0] - n[-1]).mean() < 1.5 * inner_y, "top/bottom seam"
    assert np.abs(n[:, 0] - n[:, -1]).mean() < 1.5 * inner_x, "left/right seam"


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


# ---------- physics metadata + albedo clamp ----------

def test_recipe_glass_keys_resolve():
    for name, r in RECIPES.items():
        refr = r["refraction"]
        if refr and "glass" in refr:
            assert refr["glass"] in matphys.GLASS, name
            assert refr["thickness_mm"] > 0, name
    assert "glass" not in RECIPES["gemstone"]["refraction"]
    assert RECIPES["gemstone"]["refraction"]["thickness_mm"] == 10.0
    assert RECIPES["water"]["refraction"]["thickness_mm"] == 1000.0


def test_recipe_metal_keys_valid():
    for name, r in RECIPES.items():
        assert r.get("metal") is None or r["metal"] in matphys.METALS, name
    assert RECIPES["metal_chrome"]["metal"] == "chrome"
    assert RECIPES["metal_satin"]["metal"] == "stainless_steel"
    assert RECIPES["metal_brushed"]["metal"] is None
    # Jensen et al. 2001 marble (red channel 8.5 mm); candle wax ~2 cm
    assert RECIPES["marble"]["translucency"]["sss_radius_mm"] == 8.5
    assert RECIPES["wax"]["translucency"]["sss_radius_mm"] == 20.0


def _lum8(rgb):
    return np.array([matphys.srgb_luminance_8bit(tuple(float(c) for c in p))
                     for p in rgb.reshape(-1, 3)[:1]])[0]


def test_clamp_albedo_lifts_dark():
    img = np.full((16, 16, 3), 0.05, dtype=np.float32)
    out, frac = M.clamp_albedo(img)
    assert frac == 1.0
    assert _lum8(out) >= 29.5


def test_clamp_albedo_leaves_midtones():
    img = np.full((16, 16, 3), 0.5, dtype=np.float32)
    out, frac = M.clamp_albedo(img)
    assert frac == 0.0
    assert np.allclose(out, img, atol=1e-4)


def test_clamp_albedo_caps_bright():
    img = np.full((16, 16, 3), 0.99, dtype=np.float32)
    out, frac = M.clamp_albedo(img)
    assert frac == 1.0
    assert _lum8(out) <= 240.5


def _dark_image(tmp_path):
    p = tmp_path / "dark.png"
    Image.fromarray(np.full((64, 64, 3), 12, dtype=np.uint8)).save(p)
    return str(p)


def test_dielectric_dark_image_is_clamped_with_warning(tmp_path):
    warns = []
    out = M.generate_maps(_dark_image(tmp_path), str(tmp_path / "o"),
                          mclass="concrete", resolution="2k", seamless=False,
                          warnings=warns)
    a = np.asarray(Image.open(out["albedo"]), dtype=np.float32) / 255.0
    assert _lum8(a) >= 29.0
    assert any(w.startswith("albedo clamp:") for w in warns)


def test_metal_dark_image_not_clamped(tmp_path):
    out = M.generate_maps(_dark_image(tmp_path), str(tmp_path / "o"),
                          mclass="metal_brushed", resolution="2k",
                          seamless=False)
    a = np.asarray(Image.open(out["albedo"]), dtype=np.float32) / 255.0
    assert _lum8(a) < 20.0


def test_whitelisted_name_skips_clamp(tmp_path):
    warns = []
    out = M.generate_maps(_dark_image(tmp_path), str(tmp_path / "o"),
                          mclass="concrete", resolution="2k", seamless=False,
                          warnings=warns, name="Fresh_Snow")
    a = np.asarray(Image.open(out["albedo"]), dtype=np.float32) / 255.0
    assert _lum8(a) < 20.0
    assert not any(w.startswith("albedo clamp:") for w in warns)


def test_emissive_keeps_pure_black(tmp_path):
    p = tmp_path / "black.png"
    Image.fromarray(np.zeros((64, 64, 3), dtype=np.uint8)).save(p)
    warns = []
    out = M.generate_maps(str(p), str(tmp_path / "o"), mclass="emissive",
                          resolution="2k", seamless=False, warnings=warns)
    a = np.asarray(Image.open(out["albedo"]))
    assert a.max() == 0
    assert not any(w.startswith("albedo clamp:") for w in warns)


@pytest.mark.parametrize("mclass", ["glass_clear", "water"])
def test_refractive_class_albedo_not_clamped(tmp_path, mclass):
    warns = []
    out = M.generate_maps(_dark_image(tmp_path), str(tmp_path / "o"),
                          mclass=mclass, resolution="2k", seamless=False,
                          warnings=warns)
    a = np.asarray(Image.open(out["albedo"]), dtype=np.float32) / 255.0
    assert _lum8(a) < 20.0
    assert not any(w.startswith("albedo clamp:") for w in warns)


def test_delight_keeps_plank_to_plank_tone():
    """De-lighting removes the lighting gradient but keeps real albedo
    variation (the old ~48 px divide erased ~98 % of plank-to-plank tone)."""
    rng = np.random.default_rng(5)
    size = 512
    tones = np.array([0.35, 0.55, 0.42, 0.62, 0.48, 0.38, 0.58, 0.45])
    img = np.tile(np.repeat(tones, size // 8)[None, :, None], (size, 1, 3))
    img = img + rng.normal(0, 0.01, (size, size, 3))
    xx = np.mgrid[0:size, 0:size][1] / size
    lit = np.clip(img * (0.7 + 0.6 * xx)[..., None], 0, 1).astype(np.float32)
    alb = M.derive_albedo(lit).mean(-1)
    means = np.array([alb[:, i * 64 + 8:(i + 1) * 64 - 8].mean() for i in range(8)])
    true_cv = tones.std() / tones.mean()
    assert means.std() / means.mean() > 0.6 * true_cv, "plank tone erased"
    lit_l = lit.mean(-1)
    gap = lambda a: abs(a[:, :size // 4].mean() - a[:, -size // 4:].mean())
    assert gap(alb) < 0.5 * gap(lit_l), "lighting gradient not removed"


def test_flat_relief_class_gets_flat_normal(ref_image, tmp_path):
    """Glass/chrome: photo colour must never become bump."""
    out = M.generate_maps(ref_image, str(tmp_path), mclass="glass_clear",
                          resolution="2k")
    n = np.asarray(Image.open(out["normal"])).astype(int)
    assert np.abs(n[..., :2] - 128).max() <= 1


def test_coloured_glass_photo_gives_a_transmission_tint(tmp_path):
    """Refractive classes ignore albedo, so a purple amethyst photo rendered
    colourless; its chroma now becomes a transmission tint in the manifest."""
    p = tmp_path / "amethyst.png"
    Image.fromarray(np.full((64, 64, 3), (120, 70, 160), np.uint8)).save(p)
    extra = {}
    M.generate_maps(str(p), str(tmp_path / "o"), mclass="gemstone",
                    resolution="2k", extra=extra)
    r, g, b = extra["transmission_tint"]
    assert b == pytest.approx(1.0) and g < r < b          # violet transmits blue/red
    clear = tmp_path / "clear.png"
    Image.fromarray(np.full((64, 64, 3), 235, np.uint8)).save(clear)
    extra = {}
    M.generate_maps(str(clear), str(tmp_path / "c"), mclass="glass_clear",
                    resolution="2k", extra=extra)
    assert "transmission_tint" not in extra                # clear stays clear


def test_transmission_tint_reads_the_body_not_the_glints():
    """Glints and pale facets are surface reflection: the mean colour they
    dominate lifted red toward blue, and thick facets rendered magenta."""
    rng = np.random.default_rng(3)
    body = np.array((110, 50, 150), np.float32) / 255.0
    img = np.tile(body, (128, 128, 1)) * (1.0 + 0.05 * rng.standard_normal((128, 128, 1)))
    img[rng.random((128, 128)) < 0.35] = np.array((245, 228, 240)) / 255.0
    tint = M.transmission_tint(np.clip(img, 0, 1).astype(np.float32))
    lin = M._srgb_to_lin(body)
    assert np.allclose(tint, 1.0 - 0.85 * (1.0 - lin / lin.max()), atol=0.02), tint
