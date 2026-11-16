"""compress_albedo: an over- or under-exposed photo is brought into the
plausible albedo range by exposure and a toe, keeping the detail the hard
clamp flattened."""
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from core import maps as M  # noqa: E402


def _lum(rgb):
    return M._srgb_to_lin(rgb[..., :3]) @ np.array([0.2126, 0.7152, 0.0722], np.float32)


def _weave(mean, swing, n=64):
    yy, xx = np.mgrid[0:n, 0:n]
    v = mean + swing * np.sin(xx * 1.3) * np.sin(yy * 1.1)
    return np.repeat(v[..., None], 3, axis=2).astype(np.float32)


def test_a_photo_in_range_is_untouched():
    img = _weave(0.5, 0.2)
    out, changed = M.compress_albedo(img)
    assert changed is False and out is img


def test_white_cloth_keeps_its_weave():
    img = _weave(0.975, 0.02)                         # all of it above the 240 ceiling
    clamped, frac = M.clamp_albedo(img)
    assert frac > 0.99 and float(_lum(clamped).std()) < 1e-4         # the clamp alone: flat
    out, changed = M.compress_albedo(img)
    assert changed
    y = _lum(out)
    hi = float(M._srgb_to_lin(np.float32(240.0 / 255.0)))
    assert float(np.percentile(y, 99.5)) <= hi + 1e-4
    assert float(y.std() / y.mean()) > 0.95 * float(_lum(img).std() / _lum(img).mean())   # every ratio kept
    assert M.clamp_albedo(out)[1] < 0.01              # the backstop has almost nothing left to do


def test_black_stone_keeps_its_veining_and_hue():
    img = _weave(0.05, 0.03)
    img[..., 0] *= 1.2                                # a warm black
    out, changed = M.compress_albedo(np.clip(img, 0.0, 1.0))
    assert changed
    y = _lum(out)
    lo = float(M._srgb_to_lin(np.float32(30.0 / 255.0)))
    assert float(y.min()) >= lo - 1e-5 and float(y.std()) > 0.0005
    assert float((out[..., 0] / np.maximum(out[..., 1], 1e-4)).mean()) > 1.05          # still warm
    assert M.clamp_albedo(out)[1] < 0.01


def test_pure_black_and_alpha():
    img = np.zeros((8, 8, 4), np.float32)
    img[..., 3] = 0.5
    out, changed = M.compress_albedo(img)
    assert changed and np.isfinite(out).all()
    assert np.allclose(out[..., 3], 0.5) and float(_lum(out).min()) > 0.0


def _grey(v):
    return np.repeat(np.clip(v, 0.0, 1.0)[..., None], 3, axis=2).astype(np.float32)


def test_ribs_are_a_pattern_but_noise_and_brushing_are_not():
    """Fine regular ribs must stay off stochastic tiling (random offsets jog
    them at every seam); random brushing lines and plain grain need not."""
    rnd = np.random.default_rng(5)
    yy, xx = np.mgrid[0:512, 0:512].astype(np.float32)
    grain = rnd.normal(0.0, 0.03, (512, 512)).astype(np.float32)
    ribs = 0.5 + 0.08 * np.sin(yy * 2.0 * np.pi / 6.0) + grain          # a rib every 6 px
    assert M.has_line_pattern(_grey(ribs)) is True
    assert M.has_line_pattern(_grey(ribs.T)) is True                    # either axis
    assert M.has_line_pattern(_grey(0.5 + grain * 3.0)) is False        # plain grain
    brushed = 0.5 + np.repeat(rnd.normal(0.0, 0.05, (512, 1)).astype(np.float32), 512, axis=1) + grain * 0.3
    assert M.has_line_pattern(_grey(brushed)) is False                  # lines, but at random
    assert M.has_line_pattern(_grey(np.full((512, 512), 0.5, np.float32))) is False
    small = M.has_line_pattern(_grey(ribs[:256, :256]))                 # any size is resampled
    assert small in (True, False)


def test_vignette_is_removed_but_a_flat_photo_is_left_alone():
    """A pillow of light (flat in the middle, darker toward every edge)
    comes out of a plain surface; a tiled grid keeps the plain degree-2 fit."""
    rnd = np.random.default_rng(1)
    yy, xx = np.mgrid[0:256, 0:256].astype(np.float32) / 255.0 * 2.0 - 1.0
    plain = 0.6 + rnd.normal(0.0, 0.004, (256, 256)).astype(np.float32)
    pillow = plain * (1.0 - 0.25 * np.maximum(np.abs(xx), np.abs(yy)) ** 4)
    out = M._luminance(M.derive_albedo(_grey(pillow)))
    blocks = out.reshape(8, 32, 8, 32).mean(axis=(1, 3))
    assert float(blocks.std() / blocks.mean()) < 0.02          # was a 6 % pillow
    raw = _lum(_grey(pillow)).reshape(8, 32, 8, 32).mean(axis=(1, 3))
    assert float(raw.std() / raw.mean()) > 3.0 * float(blocks.std() / blocks.mean())


def test_relief_follows_the_real_texture():
    """Noise on a featureless photo is not relief; real texture is."""
    rnd = np.random.default_rng(2)
    faint = _grey(0.7 + rnd.normal(0.0, 0.002, (256, 256)).astype(np.float32))      # honed stone, paint
    weave = _grey(0.5 + 0.1 * np.sin(np.arange(256, dtype=np.float32) * 0.9)[None, :] * np.ones((256, 1), np.float32))
    h_faint, h_weave = M.derive_height(faint, "full"), M.derive_height(weave, "full")
    assert float(h_weave.max() - h_weave.min()) > 0.9          # full depth for a real weave
    assert float(np.percentile(h_faint, 99) - np.percentile(h_faint, 1)) < 0.5      # a fraction for noise
    assert abs(float(h_faint.mean()) - 0.5) < 0.05
    flat = M.derive_height(_grey(np.full((64, 64), 0.5, np.float32)), "full")
    assert np.isfinite(flat).all() and float(np.ptp(flat)) < 1e-3


def test_mirror_smooth_classes_get_no_gloss_clouds():
    from core.recipes import RECIPES
    for key in ("glass_clear", "ceramic_glazed", "plastic_glossy", "metal_chrome"):
        assert RECIPES[key].get("roughness_broad") == 0.0, key
    rgb = _grey(np.full((128, 128), 0.5, np.float32))
    h = np.full((128, 128), 0.5, np.float32)
    clean = M.derive_roughness(rgb, 0.08, 0.05, height=h, seed=3, broad=0.0)
    cloudy = M.derive_roughness(rgb, 0.08, 0.05, height=h, seed=3)
    assert float(np.ptp(clean)) < 1e-6 and float(np.ptp(cloudy)) > 0.01


def test_seamless_does_not_invent_a_tone_gradient_on_a_fine_texture():
    """Ribs cut out of phase at the border: the top row a crest, the bottom
    one a trough. Read as a tone difference, that jump put a gradient into
    an evenly lit photo (a loop rug came out with a corner 2.3x darker) and
    every repeat showed as a frame. The wrap must still be seamless."""
    n = 256
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    ribs = (0.20 + 0.15 * np.cos(yy * 2.0 * np.pi * 35.5 / (n - 1))).astype(np.float32)
    out = M.make_seamless(_grey(ribs))
    drift = np.abs(M._gblur(out[..., 0], n / 32.0) - M._reflect_blur(ribs, n / 32.0))[8:-8]
    assert float(drift.max()) < 0.02                            # was 0.088: over a third of the tone
    wrap = float(np.abs(out[0, :, 0] - out[-1, :, 0]).mean())
    inner = float(np.abs(out[0, :, 0] - out[1, :, 0]).mean())
    assert wrap <= inner * 1.2                                  # the seam is no bigger a step than any other
    assert float(out.std()) > 0.9 * float(ribs.std())           # the ribs keep their contrast
    grad = _grey((0.3 + 0.2 * xx / n + 0.05 * np.sin(xx * 0.9)).astype(np.float32))
    even = M.make_seamless(grad)                                # a real tone difference is still evened out
    assert float(np.abs(even[:, 0, 0] - even[:, -1, 0]).mean()) < 0.06


def test_a_regular_weave_is_cropped_to_whole_repeats():
    """Ribs that do not fit the frame a whole number of times meet out of
    step at the wrap: a seam line along every repeat. Cropped to whole
    repeats they meet in phase; a texture without a lattice is untouched."""
    n = 256
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    cycles = 35.4                                                # not a whole number
    ribs = _grey((0.4 + 0.15 * np.cos(yy * 2.0 * np.pi * cycles / n)).astype(np.float32))
    assert abs(M.lattice_cycles(M._luminance(ribs), 0) - cycles) < 0.15
    assert M.lattice_cycles(M._luminance(ribs), 1) is None       # nothing regular across the ribs
    (snapped,), found = M.snap_to_lattice(ribs)
    assert found[0] is not None and found[1] is None and snapped.shape == ribs.shape
    whole = M.lattice_cycles(M._luminance(snapped), 0)
    assert abs(whole - round(whole)) < 0.12                      # 35 whole ribs now
    step = lambda im: float(np.abs(im[0, :, 0] - im[-1, :, 0]).mean()) / float(np.abs(im[0, :, 0] - im[1, :, 0]).mean() + 1e-6)
    assert step(snapped) < 0.5 * step(ribs)                      # the wrap is no longer a jump
    rnd = np.random.default_rng(4)
    grain = _grey((0.5 + rnd.normal(0.0, 0.05, (n, n))).astype(np.float32))
    (same,), found = M.snap_to_lattice(grain)
    assert found == (None, None) and same is grain


def test_a_drifting_lattice_is_cut_where_it_runs_on():
    """Rows of loops whose spacing drifts down the photo have no one
    frequency to make whole; the cut is found by matching the start strip
    further on, and the wrap ends up in step (no wide gap row)."""
    n = 512
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    phase = 2.0 * np.pi * (yy / 13.3 + 0.9 * (yy / n) ** 2)             # the pitch tightens downward
    rng = np.random.default_rng(8)
    loops = _grey((0.4 + 0.12 * np.cos(phase) + rng.normal(0.0, 0.02, (n, n))).astype(np.float32))
    (cut,), kept = M.snap_to_lattice(loops)
    assert kept[0] is not None and kept[0] < n and kept[1] is None
    prof = lambda im: im[..., 0].mean(axis=1)
    step = lambda p: abs(p[0] - p[-1]) / np.abs(np.diff(p)).mean()
    assert step(prof(cut)) < 2.0 < step(prof(loops))


def test_photo_border_is_trimmed_but_not_a_lighting_ramp():
    """A glow along one edge and an off-tone last row are the photo's border,
    not the material: both go. A steady ramp of light across the frame is
    left for the de-lighting (only the fixed 1/256 goes)."""
    n = 512
    rng = np.random.default_rng(5)
    base = (0.45 + rng.normal(0.0, 0.03, (n, n))).astype(np.float32)
    glow = base.copy()
    glow[:, -10:] += np.linspace(0.0, 0.06, 10, dtype=np.float32)[None, :]
    glow[-1, :] += 0.05
    _, (top, bottom, left, right) = M.trim_photo_edges(_grey(glow))
    assert right >= 8 and (top, left) == (2, 2) and bottom == 2      # the last row goes with the fixed cut
    ramp = base + np.linspace(-0.08, 0.08, n, dtype=np.float32)[None, :]
    out, cuts = M.trim_photo_edges(_grey(ramp))
    assert cuts == (2, 2, 2, 2) and out.shape == (n, n, 3)


def test_uniform_texture_wraps_without_a_crease():
    """Two edges with different tone and texture: the run-on tiling leaves no
    step at the wrap in the picture or in the relief made from it, and the
    cross-faded strip keeps its contrast (a plain mix would halve it)."""
    n = 512
    rng = np.random.default_rng(11)
    yy = np.mgrid[0:n, 0:n][0].astype(np.float32) / n
    tex = rng.normal(0.0, 1.0, (n, n)).astype(np.float32)
    img = _grey(np.clip(0.5 - 0.10 * yy + (0.03 + 0.03 * yy) * tex, 0, 1))   # darker and busier downward
    (out,) = M.overlap_seamless([img])
    assert out.shape == img.shape
    for arr in (out[..., 0], M.derive_height(out, "full")):
        rows = M._gblur(arr, 3.0).mean(axis=1)
        assert abs(rows[0] - rows[-1]) < 3.0 * np.abs(np.diff(rows)).mean() + 1e-4
    hp = out[..., 0] - M._gblur(out[..., 0], 4.0)
    assert hp[:24].std() > 0.8 * hp[40:120].std()


def test_even_texture_levels_the_contrast_not_the_tone():
    n = 512
    rng = np.random.default_rng(12)
    xx = np.mgrid[0:n, 0:n][1].astype(np.float32) / n
    amp = 0.02 + 0.03 * (0.5 - 0.5 * np.cos(2 * np.pi * xx))                 # soft in the corners, crisp mid-tile
    img = _grey(np.clip(0.5 + amp * rng.normal(0.0, 1.0, (n, n)), 0, 1).astype(np.float32))
    out = M.even_texture(img)
    hp = lambda a: a[..., 0] - M._gblur(a[..., 0], 4.0)
    ratio = lambda a: hp(a)[:, 216:296].std() / hp(a)[:, :40].std()
    assert ratio(img) > 2.0 and ratio(out) < 1.45
    assert abs(float(out.mean()) - float(img.mean())) < 0.004

