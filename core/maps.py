"""Reference image -> PBR map set (albedo, roughness, normal, height, AO,
optional opacity), at 2K/4K/8K, fully deterministic (no AI, no cloud).

The derivation is heuristic (Materialize-class quality): good for v1 and
instantly replaceable by an AI backend writing the same filenames.

Low-frequency operations use the resize-down/resize-up trick instead of
giant gaussian kernels so 8K stays fast and dependency-free.
"""
import os
import sys

import numpy as np
from PIL import Image

from .recipes import RESOLUTIONS, get_recipe
import matphys  # noqa: E402  (repo root put on sys.path by .recipes)

# Finite cap (not None): allow generous inputs but refuse decompression bombs.
# 24576² ~= 600 MP covers any realistic reference; beyond that the native-res
# decode alone would blow memory before we ever downsample.
Image.MAX_IMAGE_PIXELS = 24576 * 24576

MAP_FILES = {
    "albedo": "albedo.png",
    "roughness": "roughness.png",
    "normal": "normal.png",
    "height": "height.png",
    "ao": "ao.png",
    "opacity": "opacity.png",
    "sheen": "sheen.png",
}

# How much of the photo's luminance detail is real surface relief, per class
# (recipe "relief"). Wood grain, grout, mortar, weave and pile are relief;
# marble veins, terrazzo chips, trowel clouds and paint flakes are colour, so
# polished classes keep only fine micro-texture and glass/chrome stay flat.
# Band weights are (fine, mid, coarse); see derive_height().
RELIEF_BANDS = {
    "full": (0.30, 0.40, 0.30),
    "fine": (0.70, 0.30, 0.00),
    "flat": None,
}
# Contrast (std of sRGB luminance, 0-1) under which a band is counted as
# mostly noise, per band (fine, mid, coarse): measured on the lab's photos,
# linen reads 0.032 / 0.035 / 0.013 and black leather 0.016 / 0.007 / 0.003,
# white paint 0.002 / 0.002 / 0.001 and honed limestone 0.002 / 0.003 / 0.004.
# Fine noise still passes as tooth (paint's orange peel); coarse noise, which
# becomes centimetre lumps, needs real contrast to count.
RELIEF_FLOOR = (0.004, 0.008, 0.012)
# Normal strength per relief model at the 2K reference resolution; the
# recipe's bump_amount (V-Ray bump %) still sets the final depth.
NORMAL_STRENGTH = {"full": 2.0, "fine": 1.4, "flat": 0.0}


def _to_float(img):
    return np.asarray(img, dtype=np.float32) / 255.0


def _to_image(arr):
    return Image.fromarray(
        (np.clip(arr, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8))


def _resize_f(chan, size):
    """Resize a single float32 channel via PIL 'F' mode (no uint8 hop)."""
    im = Image.fromarray(np.ascontiguousarray(chan, dtype=np.float32))  # 'F'
    return np.asarray(im.resize(size, Image.BILINEAR), dtype=np.float32)


def _lowfreq(arr, factor=48):
    """Cheap large-radius blur: resize down to ~factor px, back up.

    Kept entirely in float32 (PIL 'F' mode) — the earlier uint8 round-trip
    quantized this basis to 256 steps, which then divided/subtracted into
    every derived map and produced faint contour banding (and ridge lines in
    the normal map). Float in, float out, no banding.
    """
    a = arr.astype(np.float32)
    h, w = a.shape[:2]
    small = (max(4, w // factor), max(4, h // factor))
    if a.ndim == 2:
        down = _resize_f(a, small)
        return _resize_f(down, (w, h))
    chans = [_resize_f(_resize_f(a[..., c], small), (w, h))
             for c in range(a.shape[2])]
    return np.stack(chans, axis=-1)


def _luminance(rgb):
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114


def _box1d_wrap(a, r, axis):
    """Box filter of radius r along one axis with wrap-around edges, O(N)
    via a cumulative sum, so tileable inputs stay tileable."""
    n = a.shape[axis]
    r = int(min(r, n // 2 - 1))
    if r < 1:
        return a
    idx = np.r_[np.arange(n - r - 1, n), np.arange(n), np.arange(0, r)]
    c = np.cumsum(np.take(a, idx, axis=axis), axis=axis, dtype=np.float64)
    # slices, not take(): the same numbers without two full-size copies
    hi, lo = [slice(None)] * a.ndim, [slice(None)] * a.ndim
    hi[axis], lo[axis] = slice(2 * r + 1, n + 2 * r + 1), slice(0, n)
    return ((c[tuple(hi)] - c[tuple(lo)]) / (2 * r + 1)).astype(np.float32)


def _gblur(a, sigma):
    """Periodic near-Gaussian blur: three box passes. Three passes of radius
    r give sigma = sqrt(r (r + 1)), so r is solved from sigma (rounding
    sigma itself made a 0.7 px prefilter a 1.4 px one at every resolution,
    which broke resolution independence)."""
    out = a.astype(np.float32)
    if sigma < 1.0:
        # sub-pixel: binomial [1, 2, 1] / 4 passes, each adding variance 0.5
        for _ in range(int(round(2.0 * sigma * sigma))):
            for ax in (0, 1):
                out = 0.25 * (np.roll(out, 1, axis=ax) + 2.0 * out
                              + np.roll(out, -1, axis=ax))
        return out
    r = int(round((np.sqrt(1.0 + 4.0 * sigma * sigma) - 1.0) / 2.0))
    for _ in range(3):
        out = _box1d_wrap(_box1d_wrap(out, r, 0), r, 1)
    return out


def _periodic_noise(shape, seed, cutoff=6.0):
    """Tileable low-frequency noise in [-1, 1]: white noise low-passed in the
    Fourier domain (periodic by construction), deterministic per seed."""
    h, w = shape
    rng = np.random.default_rng(seed)
    f = np.fft.rfft2(rng.standard_normal((h, w)))
    fy = np.fft.fftfreq(h)[:, None] * h
    fx = np.fft.rfftfreq(w)[None, :] * w
    f *= np.exp(-(fx * fx + fy * fy) / (2.0 * cutoff * cutoff))
    n = np.fft.irfft2(f, s=(h, w)).astype(np.float32)
    return np.clip(n / (3.0 * float(n.std()) + 1e-9), -1.0, 1.0)


def _resize_square(img, size):
    """Center-crop to square, then resize to target size."""
    w, h = img.size
    side = min(w, h)
    left, top = (w - side) // 2, (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    return img.resize((size, size), Image.LANCZOS)


def _periodic_component(u):
    """Periodic part of a 2-D channel (Moisan 2011, periodic + smooth).

    The smooth component s solves a Poisson problem driven only by the jumps
    across the image borders; p = u - s tiles with no seam while every bit
    of interior detail survives (s is smooth). rfft keeps 8K affordable.
    """
    m, n = u.shape
    u64 = u.astype(np.float64)
    v = np.zeros((m, n), dtype=np.float64)
    d = u64[:, -1] - u64[:, 0]
    v[:, 0] += d
    v[:, -1] -= d
    d = u64[-1, :] - u64[0, :]
    v[0, :] += d
    v[-1, :] -= d
    vh = np.fft.rfft2(v)
    q = np.arange(m)[:, None]
    r = np.arange(n // 2 + 1)[None, :]
    den = 2.0 * np.cos(2.0 * np.pi * q / m) + 2.0 * np.cos(2.0 * np.pi * r / n) - 4.0
    den[0, 0] = 1.0
    sh = vh / den
    sh[0, 0] = 0.0
    s = np.fft.irfft2(sh, s=(m, n))
    return (u64 - s).astype(np.float32)


def lattice_cycles(lum, axis, share=0.25):
    """Cycles per tile of a regular lattice running along `axis` (ribs,
    rows of loops, a weave's threads), to a fraction of a cycle, or None.

    The mean profile of the detail across the other axis is Fourier
    transformed; a lattice is one bin (and its two neighbours) holding at
    least `share` of the profile's power, at 8 cycles per tile or more
    (fewer is a broad stripe, not a lattice). The peak is refined between
    bins from the two beside it.
    """
    detail = lum - _reflect_blur(lum, max(2.0, lum.shape[0] / 64.0))
    prof = detail.mean(axis=1 - axis).astype(np.float64)
    prof = (prof - prof.mean()) * np.hanning(prof.size)
    mag = np.abs(np.fft.rfft(prof)) ** 2
    if mag.size < 12 or float(mag[1:].sum()) <= 0.0:
        return None
    k = int(np.argmax(mag[8:-1])) + 8
    if float(mag[k - 1:k + 2].sum()) < share * float(mag[1:].sum()):
        return None
    a, b, c = (np.log(max(float(v), 1e-30)) for v in mag[k - 1:k + 2])
    den = a - 2.0 * b + c
    return k + (0.5 * (a - c) / den if abs(den) > 1e-12 else 0.0)


def _wrap_step(lum, axis):
    """The step across the wrap along `axis` over the step between two
    neighbouring rows: about 1 for a seam like any other place, far more
    where a lattice meets itself out of phase."""
    first, second, last = (np.take(lum, i, axis=axis) for i in (0, 1, -1))
    return float(np.abs(first - last).mean()) / (float(np.abs(first - second).mean()) + 1e-6)


def snap_to_lattice(*images):
    """Crop a photo of a regular texture to a whole number of its repeats.

    A loop pile, a ribbed rug, a knit or a plain weave almost never fits the
    frame in whole repeats, so tiled it meets itself out of step and a seam
    line runs along every repeat however well the tones match. Where the
    first image has a lattice along an axis (lattice_cycles), every image is
    cropped along it to the largest whole number of cycles, centred, and
    scaled back to size: under one repeat is lost, and the edges meet in
    phase. Images without a lattice come back untouched. Returns (images,
    (cycles along y or None, cycles along x or None)).
    """
    ref = images[0]
    lum = _luminance(ref)
    size = ref.shape[:2]
    cuts, found = [], []
    for axis in (0, 1):
        f = lattice_cycles(lum, axis)
        n = size[axis]
        keep = n
        if f is not None:
            keep = int(round(n * np.floor(f + 1e-6) / f))
            # already whole to within the measurement (a print drawn to tile,
            # a knit the photo happens to fit), or not a fine lattice after all
            if abs(f - round(f)) < 0.1 or n - keep < 1 or keep < 0.9 * n:
                keep, f = n, None
            else:
                # and only where it really brings the two edges into step
                lo = (n - keep) // 2
                cut = np.take(lum, range(lo, lo + keep), axis=axis)
                if _wrap_step(cut, axis) > 0.8 * _wrap_step(lum, axis):
                    keep, f = n, None
        lo = (n - keep) // 2
        cuts.append((lo, lo + keep))
        found.append(f)
    if found == [None, None]:
        return list(images), (None, None)
    (y0, y1), (x0, x1) = cuts
    out = []
    for im in images:
        crop = np.clip(im[y0:y1, x0:x1], 0.0, 1.0)
        pil = Image.fromarray((crop * 255.0 + 0.5).astype(np.uint8))
        out.append(_to_float(pil.resize((size[1], size[0]), Image.LANCZOS)))
    return out, tuple(found)


def _reflect_blur(a, sigma):
    """_gblur without the wrap: the array is mirrored 3 sigma past each edge
    first, so one border never bleeds into the opposite one."""
    pad = int(min(max(1, round(3.0 * sigma)), min(a.shape[:2]) - 1))
    return _gblur(np.pad(a, pad, mode="reflect"), sigma)[pad:-pad, pad:-pad]


def make_seamless(arr, border=0.08):
    """Make the map tile seamlessly (periodic + smooth decomposition).

    The earlier edge cross-fade blended each border with its MIRROR, which
    made the first and last columns identical, left a Rorschach ghost along
    every seam and a flat strip in the normal map. Removing the smooth
    component instead makes the wrap continuous without mirroring, ghosting
    or loss of contrast. `border` is kept for API compatibility.

    The decomposition reads the jump between opposite border pixels as a
    difference in tone to be evened out across the tile. On a fine,
    contrasty texture that jump is mostly phase: one edge cut through bright
    loops, the other through the gaps between them. An evenly lit loop-pile
    photo came out with a corner 2.3x darker, and every repeat showed as a
    frame. So the texture's detail (the map minus its own local mean, which
    has no tone to even out) is put back to zero local mean afterwards with a
    periodic low-pass: the wrap stays exact, real tone differences between
    the edges are still smoothed away, the phantom ones are not created.
    """
    a = arr.astype(np.float32)
    lo, hi = float(a.min()), float(a.max())
    sigma = max(2.0, a.shape[0] / 48.0)

    def one(u):
        detail = _periodic_component(u - _reflect_blur(u, sigma))
        return _periodic_component(u) - _gblur(detail, sigma)

    if a.ndim == 2:
        out = one(a)
    else:
        out = np.stack([one(a[..., c]) for c in range(a.shape[2])], axis=-1)
    return np.clip(out, lo, hi)


def derive_albedo(rgb):
    """De-light: remove smooth lighting (vignetting, falloff, gradients)
    while keeping genuine albedo variation.

    Dividing by a ~48 px blur (the old approach) also removed real tone
    differences between planks, tiles and stones: on a synthetic plank floor
    98 % of plank-to-plank variation vanished, a classic CG tell. Lighting
    falloff across a texture photo is smooth, so a degree-2 polynomial is
    fitted to log luminance on 64 x 64 block medians (robust Tukey
    reweighting ignores dark joints and bright flecks), and divided out as
    one achromatic gain in linear light, clamped to [0.45, 2.2].
    """
    lin = _srgb_to_lin(np.clip(rgb[..., :3], 0.0, 1.0))
    y = lin[..., 0] * 0.2126 + lin[..., 1] * 0.7152 + lin[..., 2] * 0.0722
    h, w = y.shape
    g = 64 if min(h, w) >= 64 else max(2, min(h, w))
    bh, bw = h // g, w // g
    # Block means of linear light (then the log), not medians: on a regular
    # texture (a loop pile: bright loops, black gaps) the median of a block
    # flips between the two as the pattern drifts through the block grid, a
    # moire the fit took for light, and a rug photographed evenly came out
    # with one corner 2.3x darker. The mean moves by a loop in thirty; the
    # Tukey weights below still drop the odd block (a joint, a fleck).
    blocks = y[:bh * g, :bw * g].reshape(g, bh, g, bw)
    med = np.log(np.maximum(blocks.transpose(0, 2, 1, 3).reshape(g, g, -1).mean(axis=-1), 1e-4))
    c = (np.arange(g) + 0.5) / g * 2.0 - 1.0
    gx, gy = np.meshgrid(c, c)

    def basis(x, yy, quartic):
        cols = [np.ones_like(x), x, yy, x * x, x * yy, yy * yy]
        if quartic:
            cols += [x ** 4, x * x * yy * yy, yy ** 4]
        return np.stack(cols, axis=-1)

    b = med.reshape(-1)

    def robust(quartic):
        a = basis(gx, gy, quartic).reshape(b.size, -1)
        wts = np.ones_like(b)
        coef, mad = np.zeros(a.shape[1]), 0.0
        for _ in range(4):
            coef = np.linalg.lstsq(a * wts[:, None], b * wts, rcond=None)[0]
            res = b - a @ coef
            mad = float(np.median(np.abs(res - np.median(res)))) + 1e-6
            u = res / (4.685 * 1.4826 * mad)
            wts = np.where(np.abs(u) < 1.0, (1.0 - u * u) ** 2, 0.0)
        return coef, mad

    # Degree 2, or with the even quartic terms where they explain the photo
    # clearly better (residual spread down a fifth): a lens vignette and a
    # soft box's falloff go as r^4 (flat in the middle, darker toward every
    # edge), and with degree 2 alone a plain glaze kept a pillow in every
    # tile, a quilt of them once the map repeated. Where they do not (a
    # tiled wall, planks), the extra freedom only chases the pattern.
    coef, mad2 = robust(False)
    coef4, mad4 = robust(True)
    quartic = mad4 < 0.8 * mad2
    if quartic:
        coef = coef4
    fx = (np.arange(w, dtype=np.float32) + 0.5) / w * 2.0 - 1.0
    fy = (np.arange(h, dtype=np.float32) + 0.5) / h * 2.0 - 1.0
    fit = (coef[0] + coef[1] * fx[None, :] + coef[2] * fy[:, None]
           + coef[3] * (fx * fx)[None, :] + coef[4] * fy[:, None] * fx[None, :]
           + coef[5] * (fy * fy)[:, None]).astype(np.float32)
    if quartic:
        fit = fit + (coef[6] * (fx ** 4)[None, :] + coef[7] * (fy * fy)[:, None] * (fx * fx)[None, :]
                     + coef[8] * (fy ** 4)[:, None]).astype(np.float32)
    # (0.45-2.2: a rug shot with one corner 2.3x darker kept a dark frame in
    # every repeat under the old 0.6-1.6; the fit is a smooth surface, so a
    # wider gain still cannot follow a pattern)
    gain = np.clip(np.exp(float(fit.mean()) - fit), 0.45, 2.2)
    return np.clip(_lin_to_srgb(lin * gain[..., None]), 0.0, 1.0)


# Laid-tile grids are found on a 2K frame whatever the output size, so a
# material approved at 2K lays the same tiles at 4K or 8K.
GRID_FRAME = 2048
# Cement grout beside any glaze or fired clay: matte.
GROUT_ROUGHNESS = 0.8


def _slide(a, size, fn):
    """`fn` (np.min or np.max) over a centred window of `size`, edges held."""
    lo = size // 2
    p = np.pad(a, (lo, size - 1 - lo), mode="edge")
    return fn(np.lib.stride_tricks.sliding_window_view(p, size), axis=-1)


def _tophat(prof, size, sign):
    """Narrow features of one sign in a 1-D profile: the profile minus its
    morphological opening. A joint narrower than `size` stands out, while a
    light tile meeting a dark one across the joint, or broad shading, drops
    out (a median baseline counted the lighter tile as grout)."""
    q = sign * np.asarray(prof, dtype=np.float64)
    size = max(3, int(size) | 1)
    return q - _slide(_slide(q, size, np.min), size, np.max)


def _half_max_run(th, i):
    """Inclusive run [a, b] around peak i where `th` stays above half of it."""
    t = 0.5 * th[i]
    a = b = i
    while a > 0 and th[a - 1] > t:
        a -= 1
    while b < th.size - 1 and th[b + 1] > t:
        b += 1
    return a, b


def _axis_joints(prof, min_cells=3):
    """Straight grout joints along one axis of a laid-tile photo, or None.

    `prof` is the photo's mean luminance across the other axis: tile shades
    average out and joints running the full width stand out as a comb.
    Grout is a thin line, so the comb is skewed toward the grout's side and
    the skew says bright or dark grout (a pick count tied, and the shoulders
    beside dark grout won). A zero-padded autocorrelation, which decays with
    lag, gives the rough period that spaces the picks (a circular one locked
    onto two or three tiles when the frame held whole tiles); the period
    itself is the median step between joints. Each joint is centred on its
    half-maximum run, so every cell carries half a joint on either side.
    Anything irregular returns None: a missed joint, uneven steps (more than
    one cut row), joints of mixed widths, a border gap wider than a tile.
    """
    n = prof.size
    lo, hi = max(8, n // 24), n // 3
    if hi <= lo + 2:
        return None
    k = max(3, n // 25) | 1
    trend = np.convolve(np.pad(prof, k // 2, mode="reflect"), np.ones(k) / k, mode="valid")
    d = prof - trend
    d = d - d.mean()
    sd = float(d.std())
    if sd < 1e-6:
        return None
    skew = float((d ** 3).mean()) / sd ** 3
    if abs(skew) < 1.0:
        return None
    sign = 1.0 if skew > 0 else -1.0
    e = sign * d
    ac = np.fft.irfft(np.abs(np.fft.rfft(e, 2 * n)) ** 2, 2 * n)[:n]
    p0 = lo + int(np.argmax(ac[lo:hi]))
    if ac[p0] < 0.2 * ac[0]:
        return None
    # joint width from the strongest teeth of the comb
    peaks = sorted((i for i in range(1, n - 1) if e[i] >= e[i - 1] and e[i] > e[i + 1]),
                   key=lambda i: -e[i])
    top = []
    for i in peaks:
        if all(abs(i - j) >= 0.5 * p0 for j in top):
            top.append(i)
        if len(top) >= max(3, n // p0 - 1):
            break
    widths = []
    for i in top:
        a0, b0 = max(0, i - p0 // 3), min(n, i + p0 // 3)
        a, b = _half_max_run(e[a0:b0] - np.median(e[a0:b0]), i - a0)
        widths.append(b - a + 1)
    if not widths:
        return None
    g0 = float(np.median(widths))
    if g0 > 0.2 * p0:
        return None                          # broad bands, not joints
    size = int(min(max(3.0 * g0, g0 + 6.0), 0.4 * p0))
    th = _tophat(prof, size, sign)
    peaks = sorted((i for i in range(1, n - 1) if th[i] >= th[i - 1] and th[i] > th[i + 1]),
                   key=lambda i: -th[i])
    big = []
    for i in peaks:
        if all(abs(i - j) >= 0.5 * p0 for j in big):
            big.append(i)
        if len(big) >= max(3, int(round(n / p0)) - 1):
            break
    amp = float(np.median(th[big])) if big else 0.0
    if amp <= 0.0:
        return None
    sep = max(2.0 * g0 + 2.0, 0.25 * p0)     # a cut row is narrower than a tile
    picks = []
    for i in peaks:
        if th[i] < 0.35 * amp:
            break
        if all(abs(i - j) >= sep for j in picks):
            picks.append(i)
    # a joint cut by the frame border cannot be centred
    runs = [r for r in (_half_max_run(th, i) for i in sorted(picks)) if r[0] > 0 and r[1] < n - 1]
    if len(runs) < min_cells + 1:
        return None
    cen = np.array([0.5 * (a + b) for a, b in runs])
    wid = np.array([b - a + 1 for a, b in runs], dtype=np.float64)
    steps = np.diff(cen)
    period = float(np.median(steps))
    regular = np.abs(steps - period) <= 0.12 * period
    short = (steps < 0.88 * period) & ~regular
    gw = float(np.median(wid))
    if (np.any(steps > 1.12 * period) or np.any(steps < 0.3 * period)
            or short.sum() > max(1, len(steps) // 4) or regular.sum() < min_cells
            or float(np.std(steps[regular])) > 0.05 * period
            or cen[0] > 1.12 * period + wid[0] or n - cen[-1] > 1.12 * period + wid[-1]
            or np.any(wid > 2.5 * gw + 2.0) or np.any(wid < 0.4 * gw)):
        return None
    return {"sign": sign, "period": period, "centres": cen, "runs": runs,
            "regular": regular, "size": size, "amp": amp, "grout": gw}


def _grout_lines(prof, min_cells=3):
    """(period, joint-centre cuts) along one axis, or None; see _axis_joints()."""
    j = _axis_joints(prof, min_cells)
    if j is None:
        return None
    return int(round(j["period"])), [(a + b + 1) // 2 for a, b in j["runs"]]


def _band_joints(lum, lines, other, axis):
    """Every joint of `lines` found again inside each band between the
    joints of `other` (axis 0: vertical joints in row bands), or None.

    A real grout line is a narrow, strong line in every band it crosses.
    Running bond and hex lose it in alternate bands, while noise and weave
    never hold it. Handmade joints wander from band to band, so each cell is
    later cut at the joint centres found in its own band. Every band must
    show the joint at least faintly (pale glossy tiles barely contrast with
    white grout) and each line's median band must show it clearly.
    Returns (per line, per band (a, b, strength, contrast, margin) or None
    for a band too thin to read, the bands); margin is _cut_margin()'s.
    """
    m, n = (lum.shape[0], lum.shape[1]) if axis == 0 else (lum.shape[1], lum.shape[0])
    period, size, sign, gw = lines["period"], lines["size"], lines["sign"], lines["grout"]
    reach = max(4.0, 0.08 * period)
    edges = [(0, 0)] + list(other["runs"]) + [(m - 1, m - 1)]
    bands = [(b0 + 2, a1 - 2) for (_, b0), (a1, _) in zip(edges[:-1], edges[1:])]
    found = [[None] * len(bands) for _ in lines["centres"]]
    read = 0
    for bi, (lo, hi) in enumerate(bands):
        if hi - lo < 0.25 * other["period"]:
            continue                         # a sliver of a row at the border
        read += 1
        lp = lum[lo:hi].mean(axis=0) if axis == 0 else lum[:, lo:hi].mean(axis=1)
        th = _tophat(lp, size, sign)
        # the band again in strips along its joints, which a handmade joint
        # can wander across within one tile's length
        k = int(max(2, min(6, (hi - lo) // max(12.0, 2.0 * gw))))
        e = np.linspace(lo, hi, k + 1).astype(int)
        strips = [_tophat(lum[s0:s1].mean(axis=0) if axis == 0 else lum[:, s0:s1].mean(axis=1),
                          size, sign) for s0, s1 in zip(e[:-1], e[1:])]
        for li, c in enumerate(lines["centres"]):
            s0, s1 = int(max(1, c - reach)), int(min(n - 1, c + reach + 1))
            i = s0 + int(np.argmax(th[s0:s1]))
            a, b = _half_max_run(th, i)
            w = b - a + 1
            w0, w1 = int(max(0, c - 0.45 * period)), int(min(n, c + 0.45 * period))
            rest = np.r_[th[w0:max(w0, a - w)], th[min(w1, b + w + 1):w1]]
            noise = float(np.percentile(rest, 95)) if rest.size > 8 else 0.0
            pk = float(th[i])
            if pk < 0.2 * lines["amp"] or pk < 1.3 * noise or not 0.2 * gw <= w <= 2.5 * gw + 3:
                return None
            found[li][bi] = (a, b, pk / lines["amp"], pk / max(noise, 1e-9),
                             _cut_margin(strips, a, b))
    if read < 3:
        return None
    for row in found:
        if (np.median([f[2] for f in row if f]) < 0.6
                or np.median([f[3] for f in row if f]) < 4.0):
            return None
    return found, bands


def _cut_margin(strips, a, b):
    """Joint px the thinner side keeps when a band's joint run (a, b) is cut
    at its centre, in the worst strip of the band (`strips`: top-hats of the
    band in strips along the joint). The band's run is the joint smeared
    over the tile's length; below 0 the joint wanders off the cut in that
    strip and the cell there carries a sliver of the next tile, which
    re-laid shows as a seam with no joint or two. Strips where the joint
    fades out (glare, a chipped edge) are not judged."""
    cut = (a + b + 1) // 2
    reads = []
    for th in strips:
        s0, s1 = max(1, a - 3), min(th.size - 1, b + 4)
        if s1 <= s0:
            continue
        i = s0 + int(np.argmax(th[s0:s1]))
        ra, rb = _half_max_run(th, i)
        reads.append((float(th[i]), min(cut - ra, rb + 1 - cut)))
    top = max((p for p, _ in reads), default=0.0)
    kept = [m for p, m in reads if p > 0.0 and p >= 0.35 * top]
    return min(kept) if kept else 0


def _joint_slope(row, bands):
    """Lean of one joint across the bands (px per px), from its centres."""
    pts = [(0.5 * (lo + hi), 0.5 * (f[0] + f[1])) for (lo, hi), f in zip(bands, row) if f]
    if len(pts) < 3:
        return 0.0
    y, x = np.array(pts, dtype=np.float64).T
    return float(np.polyfit(y, x, 1)[0])


def _lay_cells(n_pool, nx, ny, turns, rng):
    """(pool tile, quarter turns) for each output cell, row by row: never the
    tile to its left or above, across the wrap included (tiled, the last
    column meets the first and the bottom row the top)."""
    cells = []
    for j in range(ny):
        for i in range(nx):
            avoid = set()
            if i:
                avoid.add(cells[-1][0])
            if j:
                avoid.add(cells[-nx][0])
            if i == nx - 1:
                avoid.add(cells[-nx + 1][0])           # wraps onto the row start
            if j == ny - 1:
                avoid.add(cells[i][0])                 # wraps onto the top row
            choice = [k for k in range(n_pool) if k not in avoid] or list(range(n_pool))
            turn = int(turns[int(rng.integers(len(turns)))]) if len(turns) > 1 else int(turns[0])
            cells.append((int(rng.choice(choice)), turn))
    return cells


def _lit_tiles(shade, pool, joints, margin, square):
    """True when the pool's tiles share a light direction that turning them
    would scatter: a lit bevel and a shadowed one, a glint near a corner,
    falloff across the glaze (or ribs a quarter turn would lay sideways).

    Each tile face, its joints and `margin` px cut off, is averaged on an
    8 x 8 grid relative to its own mean, out to the face edge where bevels
    and glints sit (the middle two thirds missed them), and compared with
    itself turned. A difference consistent over the pool (t > 4, over
    2.5 %), or a left/right or top/bottom imbalance of the whole face (t >
    2.5, over 1 %), is a light direction. Faces too small to read count as
    lit: an unturned tile costs variety, a turned one shows four lights.
    """
    grids = []
    for ((x0, x1), (y0, y1)), (l, r, t, b) in zip(pool, joints):
        face = shade[y0 + t + margin:y1 - b - margin, x0 + l + margin:x1 - r - margin]
        if min(face.shape) < 16:
            return True
        ye = np.linspace(0, face.shape[0], 9).astype(int)
        xe = np.linspace(0, face.shape[1], 9).astype(int)
        g = np.add.reduceat(np.add.reduceat(face.astype(np.float64), ye[:-1], axis=0), xe[:-1], axis=1)
        g /= np.outer(np.diff(ye), np.diff(xe))
        grids.append(g / max(float(g.mean()), 1e-6))
    g = np.array(grids)

    def consistent(d, floor, tmin):
        mu = d.mean(axis=0)
        se = d.std(axis=0, ddof=1) / np.sqrt(len(d))
        return bool(np.any((np.abs(mu) > floor) & (np.abs(mu) > tmin * se)))

    halves = np.stack([g[:, :, :4].mean(axis=(1, 2)) - g[:, :, 4:].mean(axis=(1, 2)),
                       g[:, :4].mean(axis=(1, 2)) - g[:, 4:].mean(axis=(1, 2))], axis=1)
    return (consistent(halves, 0.01, 2.5)
            or any(consistent(g - np.rot90(g, k, axes=(1, 2)), 0.025, 4.0)
                   for k in ((1, 2) if square else (2,))))


def grid_plan(rgb, seed=0, albedo=None):
    """How to re-lay a tiled photo (zellige, terracotta) so it repeats cleanly.

    A photo of a tiled wall rarely ends on grout: tiled, the border puts two
    tiles edge to edge with no joint, and the photo's few tiles stand on a
    lattice (the same glaze pooling every fifth tile). The photo is cut into
    whole tiles at the joint centres measured in each row and column of
    tiles, which absorbs handmade joints wandering from tile to tile. Off-size
    cells (a cut row) are dropped, and so is a tile whose joint wanders
    across the cut along its own length, which would carry a sliver of its
    neighbour (_cut_margin); joints that do that at most tiles leave too few
    to lay. An output grid that keeps the tile's aspect is filled with
    random tiles, never the same tile beside or above itself, across the wrap
    included. Tiles are turned (quarter turns if square, half turns if
    oblong) only when the pool shows no consistent light direction: turned,
    a lit bevel or glint would point four ways. `albedo` (the de-lit photo,
    same size; derived when omitted) judges that.

    Returns None unless both axes hold a straight, regular grid of grout
    lines confirmed in every band: running bond, hex, a turn of more than
    ~0.3 deg or anything irregular is left alone, since a false grid cuts
    hard seams through the photo while a missed one only keeps its repeat.
    """
    lum = _luminance(rgb)
    h, w = lum.shape
    jx, jy = _axis_joints(lum.mean(axis=0)), _axis_joints(lum.mean(axis=1))
    if jx is None or jy is None or jx["sign"] != jy["sign"]:
        return None
    bx, by = _band_joints(lum, jx, jy, 0), _band_joints(lum, jy, jx, 1)
    if bx is None or by is None:
        return None
    (fx, rows), (fy, cols) = bx, by
    # a turned photo leans every joint the same way; handmade ones wander
    # both ways, which the per-band cuts absorb
    lean = max(abs(float(np.median([_joint_slope(f, rows) for f in fx]))),
               abs(float(np.median([_joint_slope(f, cols) for f in fy]))))
    if lean > np.tan(np.radians(0.3)):
        return None
    px, py = jx["period"], jy["period"]
    pool, joints = [], []
    for j in range(len(fy) - 1):
        if not jy["regular"][j]:
            continue                         # a cut row
        for i in range(len(fx) - 1):
            if not jx["regular"][i]:
                continue
            l, r, t, b = fx[i][j + 1], fx[i + 1][j + 1], fy[j][i + 1], fy[j + 1][i + 1]
            if None in (l, r, t, b):
                continue
            x0, x1 = (l[0] + l[1] + 1) // 2, (r[0] + r[1] + 1) // 2
            y0, y1 = (t[0] + t[1] + 1) // 2, (b[0] + b[1] + 1) // 2
            if abs(x1 - x0 - px) > 0.12 * px or abs(y1 - y0 - py) > 0.12 * py:
                continue
            if min(l[4], r[4], t[4], b[4]) < 0:
                continue                     # a joint wanders off the cut: a sliver
            pool.append(((x0, x1), (y0, y1)))
            # grout px the cell carries: left, right, top, bottom
            joints.append((l[1] - x0 + 1, x1 - r[0], t[1] - y0 + 1, y1 - b[0]))
    if len(pool) < 9:
        return None
    # tile counts chosen together so the re-laid tile keeps its aspect (a
    # wrong shape shows, a slightly different size does not); only
    # near-square tiles (within 4 %) are laid square
    square = abs(px - py) <= 0.04 * max(px, py)
    aspect = 1.0 if square else px / py
    best = None
    for cx in range(max(3, int(w / px) - 1), int(w / px) + 3):
        for cy in range(max(3, int(h / py) - 1), int(h / py) + 3):
            cost = (abs(np.log(w * cy / (h * cx * aspect)))
                    + 0.1 * (abs(np.log(w / (cx * px))) + abs(np.log(h / (cy * py)))))
            if best is None or cost < best[0]:
                best = (cost, cx, cy)
    nx, ny = best[1], best[2]
    shade = _luminance(albedo if albedo is not None else derive_albedo(rgb))
    margin = max(2, int(round(0.25 * (jx["grout"] + jy["grout"]) / 2.0)))
    lit = _lit_tiles(shade, pool, joints, margin, square)
    turns = (0,) if lit else ((0, 1, 2, 3) if square else (0, 2))
    cells = _lay_cells(len(pool), nx, ny, turns, np.random.default_rng(seed))
    return {"nx": nx, "ny": ny, "pool": pool, "cells": cells, "joints": joints,
            "size": (h, w), "sign": int(jx["sign"]), "square": square, "turns": not lit,
            "period": (px, py), "grout": (jx["grout"], jy["grout"])}


def apply_grid_plan(arr, plan):
    """Re-lay `arr` (H x W or H x W x C) by a grid_plan(); the output tiles.
    A plan made on another size of the same photo (its "size") is scaled to
    `arr`, so one plan serves every output resolution."""
    a = arr.astype(np.float32)
    h, w = a.shape[:2]
    ph, pw = plan.get("size", (h, w))
    fx, fy = w / float(pw), h / float(ph)
    chans = a[..., None] if a.ndim == 2 else a
    out = np.empty_like(chans)
    nx, ny = plan["nx"], plan["ny"]
    xe = [int(round(i * w / nx)) for i in range(nx + 1)]
    ye = [int(round(j * h / ny)) for j in range(ny + 1)]
    for idx, (k, turns) in enumerate(plan["cells"]):
        i, j = idx % nx, idx // nx
        (x0, x1), (y0, y1) = plan["pool"][k]
        x0, x1 = int(round(x0 * fx)), int(round(x1 * fx))
        y0, y1 = int(round(y0 * fy)), int(round(y1 * fy))
        src = np.rot90(chans[y0:y1, x0:x1], turns)
        size = (xe[i + 1] - xe[i], ye[j + 1] - ye[j])
        out[ye[j]:ye[j + 1], xe[i]:xe[i + 1]] = np.stack(
            [_resize_f(src[..., c], size) for c in range(src.shape[2])], axis=-1)
    return out[..., 0] if a.ndim == 2 else out


def grout_mask(plan, lum):
    """Soft grout mask (1 in the joints) of a re-laid grid, at `lum`'s size.

    derive_height() reads white grout as raised and the glaze's roughness
    would make it glossy; generate_maps() uses this mask to sink it and make
    it matte. The core is the half joint each cell carries (from the plan);
    a seam zone one joint wider adds pixels whose tone is grout-like against
    that cell's own tile body, so wavy handmade joints are covered too.
    """
    h, w = lum.shape
    nx, ny = plan["nx"], plan["ny"]
    xe = [int(round(i * w / nx)) for i in range(nx + 1)]
    ye = [int(round(j * h / ny)) for j in range(ny + 1)]
    sign = float(plan.get("sign", 1))
    gw = float(np.mean(plan.get("grout", (2.0, 2.0))))

    def edges(shape, sides, extra):
        m = np.zeros(shape, bool)
        l, r, t, b = (s + extra for s in sides)
        m[:, :l] = True
        m[:, shape[1] - r:] = True
        m[:t] = True
        m[shape[0] - b:] = True
        return m

    # cell by cell, so an 8K map holds no full-size temporaries
    cells = []
    for idx, (k, turns) in enumerate(plan["cells"]):
        i, j = idx % nx, idx // nx
        (x0, x1), (y0, y1) = plan["pool"][k]
        l, r, t, b = plan["joints"][k]
        for _ in range(turns % 4):           # np.rot90: top -> left, right -> top
            l, r, t, b = t, b, r, l
            (x0, x1), (y0, y1) = (y0, y1), (x0, x1)
        fx = (xe[i + 1] - xe[i]) / float(x1 - x0)
        fy = (ye[j + 1] - ye[j]) / float(y1 - y0)
        sides = (int(round(l * fx)), int(round(r * fx)), int(round(t * fy)), int(round(b * fy)))
        cells.append(((slice(ye[j], ye[j + 1]), slice(xe[i], xe[i + 1])), sides,
                      max(2, int(round(0.75 * gw * fx)))))
    levels, cores = [], []
    for cell, sides, extra in cells:
        q = sign * lum[cell]
        tile = q[~edges(q.shape, sides, extra)]
        levels.append(float(np.median(tile)) if tile.size else 0.0)
        cores.append(q[edges(q.shape, sides, 0)])
    cores = np.concatenate(cores)
    if not cores.size:
        return np.zeros((h, w), np.float32)
    grout = float(np.median(cores))
    contrast = grout - float(np.median(levels))
    mask = np.zeros((h, w), np.float32)
    for (cell, sides, extra), level in zip(cells, levels):
        core = edges(mask[cell].shape, sides, 0)
        m = core.astype(np.float32)
        if contrast > 0:
            # a pale tile barely below the grout must not turn to grout itself
            zone = edges(m.shape, sides, extra) & ~core
            like = (sign * lum[cell][zone] - level) / max(grout - level, 0.5 * contrast)
            m[zone] = np.clip(like, 0.0, 1.0)
        mask[cell] = m
    return np.clip(_gblur(mask, 0.6 * h / 2048.0), 0.0, 1.0)


def _photo_seed(img):
    """Seed from the photo's own centre square at 16 x 16 (taken before any
    resize), so 2K look-dev and a 4K or 8K final lay the same tiles."""
    w, h = img.size
    side = min(w, h)
    left, top = (w - side) // 2, (h - side) // 2
    small = img.crop((left, top, left + side, top + side)).resize((16, 16), Image.BOX)
    return int(np.asarray(small, dtype=np.int64).sum()) % (2 ** 31)


def _joint_run(rgb, axis, band, c, gw, size, sign):
    """Half-maximum run (a, b) of the joint nearest `c` in `rgb`, or None.
    axis 1: `c` is an x position and the profile is averaged over the rows
    in `band`; axis 0: a y position, averaged over the columns in `band`."""
    n = rgb.shape[axis]
    reach = max(2, int(round(0.5 * gw)))
    lo, hi = max(0, int(c) - reach - size), min(n, int(c) + reach + size + 2)
    if band[1] - band[0] < 4 or hi - lo < 3:
        return None
    seg = rgb[band[0]:band[1], lo:hi] if axis == 1 else rgb[lo:hi, band[0]:band[1]]
    th = _tophat(_luminance(seg.mean(axis=1 - axis)), size, sign)
    s0, s1 = max(0, int(round(c)) - reach - lo), min(hi - lo, int(round(c)) + reach + 1 - lo)
    if s1 <= s0:
        return None
    i = s0 + int(np.argmax(th[s0:s1]))
    a, b = _half_max_run(th, i)
    # the widths _band_joints() accepts: handmade joints thin out in places
    if th[i] <= 0 or not 0.2 * gw <= b - a + 1 <= 2.5 * gw + 3 or abs(0.5 * (a + b) + lo - c) > reach:
        return None
    return lo + a, lo + b


def _fit_plan(plan, rgb):
    """`plan` moved onto `rgb`, the same photo at another size, with every
    cut re-centred on its joint there. A 2K cut scaled by 2 or 4 scales its
    pixel error too: 4K seams got joints up to 4 px too wide or narrow. A
    joint that cannot be read keeps its scaled cut."""
    h, w = rgb.shape[:2]
    ph, pw = plan["size"]
    fx, fy = w / float(pw), h / float(ph)
    gx, gy = plan["grout"][0] * fx, plan["grout"][1] * fy
    px, py = plan["period"][0] * fx, plan["period"][1] * fy
    sx = int(min(max(3.0 * gx, gx + 6.0), 0.4 * px)) | 1
    sy = int(min(max(3.0 * gy, gy + 6.0), 0.4 * py)) | 1
    pool, joints = [], []
    for ((x0, x1), (y0, y1)), (l, r, t, b) in zip(plan["pool"], plan["joints"]):
        rows = (int(round((y0 + t + 2) * fy)), int(round((y1 - b - 2) * fy)))
        cols = (int(round((x0 + l + 2) * fx)), int(round((x1 - r - 2) * fx)))
        cut = []
        # (cut, carried px, side 0 left/top or 1 right/bottom, axis, band, scale, joint, top-hat)
        for c, k, side, axis, band, f, g, s in ((x0, l, 0, 1, rows, fx, gx, sx), (x1, r, 1, 1, rows, fx, gx, sx),
                                                (y0, t, 0, 0, cols, fy, gy, sy), (y1, b, 1, 0, cols, fy, gy, sy)):
            run = _joint_run(rgb, axis, band, c * f, g, s, plan["sign"])
            if run is None:
                cut.append((int(round(c * f)), int(round(k * f))))
            else:
                m = (run[0] + run[1] + 1) // 2
                cut.append((m, run[1] - m + 1 if side == 0 else m - run[0]))
        (X0, L), (X1, R), (Y0, T), (Y1, B) = cut
        if abs(X1 - X0 - (x1 - x0) * fx) > 0.05 * px or abs(Y1 - Y0 - (y1 - y0) * fy) > 0.05 * py:
            (X0, L), (X1, R), (Y0, T), (Y1, B) = [(int(round(c * f)), int(round(k * f))) for c, k, f in
                                                  ((x0, l, fx), (x1, r, fx), (y0, t, fy), (y1, b, fy))]
        pool.append(((X0, X1), (Y0, Y1)))
        joints.append((L, R, T, B))
    return dict(plan, pool=pool, joints=joints, size=(h, w), period=(px, py), grout=(gx, gy))


def _photo_grid_plan(src8, size, rgb=None, albedo=None):
    """grid_plan() of a photo (8-bit PIL), the same tiles at every output
    `size`: found on its 2K frame and seeded by the photo itself. `rgb` and
    `albedo` are the output-size photo and its de-lit albedo: reused at 2K,
    and at 4K or 8K every cut is re-centred on its joint in `rgb`."""
    frame = rgb if size == GRID_FRAME and rgb is not None else None
    if frame is None:
        frame, albedo = _to_float(_resize_square(src8, GRID_FRAME)), None
    plan = grid_plan(frame, _photo_seed(src8), albedo)
    if plan is not None and rgb is not None and rgb.shape[:2] != plan["size"]:
        plan = _fit_plan(plan, rgb)
    return plan


def _printed_steps(lin):
    """True when the tone changes in sharp steps that line up across the
    tile: a stripe or check, even tone on tone, which a low-pass cannot tell
    from light.

    Light falls off smoothly, while a print steps at its edges, along whole
    rows or columns. The log luminance (at most 512 px, threads blurred out)
    is cut into 8 strips each way; every strip's profile across the strips is
    differenced and the steps averaged over the strips, so edges in the same
    place in every strip add up (a check flips sign from strip to strip, which
    a mean of the profiles would cancel) and texture levels out. A print is
    4 to 24 edges of at least 4 % holding 70 % of the variation. Every lab
    photo of a plain material scores 1 to 52 peaks carrying no more than a
    third of it; a cast shadow is two edges. Diagonal stripes are not seen.
    """
    y = lin @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    f = max(1, min(y.shape) // 512)
    h, w = y.shape[0] // f, y.shape[1] // f
    if min(h, w) < 64:
        return False
    small = y[:h * f, :w * f].reshape(h, f, w, f).mean(axis=(1, 3))
    ly = _gblur(np.log(small + 1e-4).astype(np.float32), max(1.0, min(h, w) / 256.0))
    for axis in (0, 1):
        prof = np.array([s.mean(axis=axis) for s in np.array_split(ly, 8, axis=axis)])
        step = np.abs(np.roll(prof, -1, axis=1) - prof).mean(axis=0)
        n = step.size
        tall = [i for i in range(n) if step[i] >= 0.3 * step.max()
                and step[i] >= step[i - 1] and step[i] >= step[(i + 1) % n]]
        peaks = []
        for i in sorted(tall, key=lambda i: -step[i]):
            if all(min(abs(i - j), n - abs(i - j)) > 6 for j in peaks):
                peaks.append(i)
        if not 4 <= len(peaks) <= 24:
            continue
        near = np.zeros(n, bool)
        for i in peaks:
            near[np.arange(i - 4, i + 5) % n] = True
        edges = [float(step[np.arange(i - 4, i + 5) % n].sum()) for i in peaks]
        if (float(step[near].sum()) >= 0.7 * float(step.sum())
                and float(np.median(edges)) >= 0.04):
            return True
    return False


def flatten_drift(albedo, sigma_frac=1.0 / 32.0, warnings=None):
    """Even out brightness drift wider than ~2 * sigma_frac of the tile.

    In a uniform texture (weave, pile, paint, brushing) variation at tile
    scale is lighting the degree-2 de-light missed, plus the smooth part the
    periodic decomposition pushes toward the borders. Tiled, it repeats as a
    grid of soft-edged rectangles: a linen sofa read as patchwork. Linear
    luminance is divided by its periodic low-pass as one achromatic gain,
    clamped to [0.8, 1.25], and the mean restored, so every pixel keeps its
    hue and chromaticity (dividing each channel by its own low-pass turned
    red and cream stripes salmon). The low-pass is of linear light, not of
    its log, which sparse near-black pores dragged into blotches.
    sigma 1/32 of the tile removes ~90 % of the 1-3 cycle drift that makes
    the grid (1/16 left a third of it) and leaves features under ~1/100 of
    the tile (threads, loops, pores) untouched.

    Frequency cannot tell lighting from a 2-3 stripe print, so the albedo is
    returned unchanged, with a note in `warnings`, when its tile-scale
    variation is beyond leftover lighting: wandering chromaticity (std over
    0.025: stripes, checks, prints, dip-dye), a low-pass luminance spread
    over 0.5 in log (about +/-28 %, past what the gain clamp can even out),
    or tone stepping in sharp edges lined up across the tile (a tone-on-tone
    stripe or check, which passes both: _printed_steps).
    """
    lin = _srgb_to_lin(np.clip(albedo[..., :3], 0.0, 1.0))
    wts = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    sigma = sigma_frac * lin.shape[0]
    low = [_gblur(lin[..., c], sigma) + 1e-6 for c in range(3)]
    total = low[0] + low[1] + low[2]
    # chromaticity, not log(R/G): sheen on a saturated red or green moves
    # the small channel's log by more than a stripe would
    chroma = max(float((c / total).std()) for c in low)
    ly = np.log(wts[0] * low[0] + wts[1] * low[1] + wts[2] * low[2])
    spread = float(np.percentile(ly, 99) - np.percentile(ly, 1))
    why = None
    if chroma > 0.025 or spread > 0.5:
        why = ("the colour or tone varies too much across the tile to be leftover "
               "lighting (a pattern, a print or large texture)")
    elif _printed_steps(lin):
        why = ("the tone steps in sharp edges lined up across the tile (a stripe "
               "or check, even tone on tone), which is pattern, not light")
    if why:
        if warnings is not None:
            warnings.append("drift flattening skipped: %s, so it was kept" % why)
        return np.clip(albedo[..., :3], 0.0, 1.0).astype(np.float32)
    before = float((lin @ wts).mean())
    gain = np.clip(np.exp(float(ly.mean()) - ly), 0.8, 1.25)
    out = lin * gain[..., None]
    out *= before / max(float((out @ wts).mean()), 1e-6)
    return _lin_to_srgb(out)


def _srgb_to_lin(a):
    return np.where(a <= 0.04045, a / 12.92,
                    ((a + 0.055) / 1.055) ** 2.4).astype(np.float32)


def _lin_to_srgb(a):
    a = np.clip(a, 0.0, 1.0)
    return np.where(a <= 0.0031308, a * 12.92,
                    1.055 * np.power(a, 1.0 / 2.4) - 0.055).astype(np.float32)


def clamp_albedo(rgb, floor_8bit=matphys.ALBEDO_FLOOR_ERROR,
                 ceiling_8bit=matphys.ALBEDO_CEILING):
    """Pull per-pixel albedo luminance into [floor, ceiling] (8-bit sRGB
    luminance), scaling in linear so hue is preserved.

    Only the first three channels are touched (an alpha channel passes
    through unchanged). A pixel with any NaN channel has no usable colour:
    it becomes the neutral floor grey (and counts as changed); +/-inf clip.

    Returns (rgb, fraction_of_pixels_changed).
    """
    arr = rgb.astype(np.float32)
    col = arr[..., :3]
    nan = np.isnan(col).any(axis=-1)
    col = np.nan_to_num(col, nan=0.0, posinf=1.0, neginf=0.0)
    lin = _srgb_to_lin(np.clip(col, 0.0, 1.0))
    y = (lin[..., 0] * 0.2126 + lin[..., 1] * 0.7152
         + lin[..., 2] * 0.0722)
    lo = float(_srgb_to_lin(np.float32(floor_8bit / 255.0)))
    hi = float(_srgb_to_lin(np.float32(ceiling_8bit / 255.0)))
    target = np.where(nan, lo, np.clip(y, lo, hi))
    changed = (target != y) | nan
    scale = np.where(changed, target / np.maximum(y, 1e-6), 1.0)
    # pure black (or NaN) has no hue to keep: lift it to a neutral grey
    black = changed & ((y <= 1e-6) | nan)
    out = lin * scale[..., None]
    out = np.where(black[..., None], target[..., None], out)
    out = np.clip(_lin_to_srgb(out), 0.0, 1.0)
    if arr.shape[-1] > 3:
        out = np.concatenate([out, arr[..., 3:]], axis=-1)
    return out, float(changed.mean())


def derive_height(rgb, relief="full", upscale=1.0):
    """Height from luminance, split into frequency bands so only real relief
    survives.

    Bands are differences of periodic blurs at sigma ~0.6/2/8/32 px (scaled
    with resolution, so 2K and 4K describe the same physical features). Each
    band is normalised, then weighted by the class's relief model: "full"
    keeps grain, joints and weave; "fine" keeps only micro-texture (polished
    stone, glaze, paint); "flat" returns a neutral 0.5 plane. Dark is low,
    which holds for mortar, pores, grain grooves and dark grout (white grout
    of a re-laid tile grid is sunk afterwards; see grout_mask()).

    `upscale` (output size / the photo's native size) widens the finest
    prefilter so interpolation from upsampling never becomes fake relief.
    """
    lum = _luminance(rgb)
    weights = RELIEF_BANDS.get(relief, RELIEF_BANDS["full"])
    if weights is None:
        return np.full(lum.shape, 0.5, dtype=np.float32)
    s = lum.shape[0] / 2048.0
    first = max(0.6 * s, 0.7 * float(upscale))
    levels = [_gblur(lum, first)] + [_gblur(lum, sg * s) for sg in (2.0, 8.0, 32.0)]
    h = np.zeros(lum.shape, dtype=np.float32)
    strongest = 0.0
    for wgt, floor, fine, coarse in zip(weights, RELIEF_FLOOR, levels[:-1], levels[1:]):
        if wgt:
            band = fine - coarse
            std = float(band.std())
            # A band is normalised so real texture comes out at full depth
            # whatever the photo's contrast; but a band with almost nothing
            # in it is sensor noise, and normalising that made relief out of
            # nothing: honed limestone (0.3 % contrast) forged as lumpy
            # roughcast, a plain glaze as a quilt. Under its floor a band
            # counts in proportion to what is really there.
            real = min(1.0, std / floor)
            strongest = max(strongest, real)
            h += wgt * real * band / (std + 1e-6)
    lo, hi = np.percentile(h, 1), np.percentile(h, 99)
    unit = np.clip((h - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    return (0.5 + (unit - 0.5) * strongest).astype(np.float32)


def derive_normal(height, strength=2.0, scale=1.0):
    """Tangent-space normal from height. `scale` (= size / 2048) keeps the
    slope per physical distance constant, so a 4K map is as deep as a 2K one
    instead of half as deep."""
    # Periodic (wrap-around) central differences so that when `height` tiles
    # seamlessly, the normal map tiles too. np.gradient uses one-sided diffs
    # at the borders, which left a visible ridge along every seam even though
    # the height was seamless.
    h = height.astype(np.float32)
    k = strength * scale
    # Scharr: central difference smoothed [3, 10, 3] / 16 across, which keeps
    # gradient direction accurate to ~0.3 deg (plain central differences are
    # anisotropic by up to ~7 deg), still periodic via np.roll.
    sx = 0.5 * (np.roll(h, -1, axis=1) - np.roll(h, 1, axis=1))
    sy = 0.5 * (np.roll(h, -1, axis=0) - np.roll(h, 1, axis=0))
    gx = (3.0 * np.roll(sx, 1, axis=0) + 10.0 * sx + 3.0 * np.roll(sx, -1, axis=0)) / 16.0
    gy = (3.0 * np.roll(sy, 1, axis=1) + 10.0 * sy + 3.0 * np.roll(sy, -1, axis=1)) / 16.0
    nx, ny = -gx * k, -gy * k
    nz = np.ones_like(h)
    norm = np.sqrt(nx * nx + ny * ny + nz * nz)
    n = np.stack([nx / norm, ny / norm, nz / norm], axis=-1)
    return n * 0.5 + 0.5  # tangent-space encode


def _renormalize(encoded):
    v = encoded * 2.0 - 1.0
    v /= np.maximum(np.sqrt((v * v).sum(axis=-1, keepdims=True)), 1e-6)
    return v * 0.5 + 0.5


def derive_roughness(rgb, base, variation, height=None, seed=0, broad=0.45):
    """base roughness +/- variation, kept inside [base - var, base + var].

    Uniform roughness is the #1 CG tell, but deriving it from albedo contrast
    makes every colour pattern (veins, figure, flecks) a gloss pattern too.
    Variation instead comes from (a) cavities in the height map, which hold
    dust and wear and read rougher, and (b) tileable low-frequency noise that
    stands in for smudges and uneven finish. With no height (legacy callers)
    the cavity term falls back to local luminance contrast.
    """
    lum = _luminance(rgb)
    s = lum.shape[0] / 2048.0
    if height is not None:
        cav = _gblur(height, 6.0 * s) - height        # > 0 in recesses
    else:
        cav = np.abs(lum - _lowfreq(lum))
        cav = cav - float(cav.mean())
    # (at least 0.06 of the height range: the cavities of a nearly flat
    # height map are noise, and normalising them by themselves blotched it)
    floor = 0.06 if height is not None else 0.0
    cav = np.clip(cav / (max(float(np.percentile(np.abs(cav), 98)), floor) + 1e-6), -1, 1)
    # `broad`: the share of tile-wide cloudy noise (smudges, uneven finish).
    # 0 for mirror-smooth classes: on glass or a glaze each stochastic tile
    # showed as its own patch of gloss
    clouds = _periodic_noise(lum.shape, seed) if broad else 0.0
    t = np.clip((1.0 - broad) * cav + broad * clouds, -1.0, 1.0)
    return np.clip(base + t * variation, 0.02, 1.0)


def derive_sheen(albedo):
    """Sheen colour for cloth: the fibre colour lifted toward white (sqrt in
    linear), so velvet glows in its own hue instead of a grey film."""
    lin = _srgb_to_lin(np.clip(albedo[..., :3], 0.0, 1.0))
    return _lin_to_srgb(np.sqrt(lin))


def derive_ao(height):
    """Occlusion approximation: recessed-below-neighborhood areas darken."""
    cavity = _lowfreq(height, factor=24) - height
    ao = 1.0 - np.clip(cavity, 0.0, None) * 1.8
    return np.clip(ao, 0.0, 1.0)


def dim_bright_leaf(albedo, opacity, lum_max):
    """Darken a cut-out leaf whose photo is brighter than living leaves are.

    Studio shots on a white sweep are exposed for the paper: a monstera came
    out at a mean luminance of 0.29 and a strelitzia at 0.42, three to four
    times a real green leaf (0.05-0.15), and rendered neon. Where most of
    the subject is green and its mean linear luminance exceeds `lum_max`,
    the whole albedo is scaled (in linear, hue kept) to that mean. Flowers
    and autumn leaves (not mostly green) are left alone. Returns (albedo,
    the mean it had) or (albedo, None) when nothing changed.
    """
    sub = opacity[..., 0] > 0.5 if opacity.ndim == 3 else opacity > 0.5
    if not sub.any():
        return albedo, None
    lin = _srgb_to_lin(np.clip(albedo[..., :3].astype(np.float32), 0.0, 1.0))
    px = lin[sub]
    green = (px[:, 1] > px[:, 0] * 1.05) & (px[:, 1] > px[:, 2])
    mean = float((px @ np.array([0.2126, 0.7152, 0.0722], np.float32)).mean())
    if float(green.mean()) < 0.5 or mean <= lum_max:
        return albedo, None
    out = np.clip(_lin_to_srgb(lin * (lum_max / mean)), 0.0, 1.0).astype(np.float32)
    if albedo.shape[-1] > 3:
        out = np.concatenate([out, albedo[..., 3:]], axis=-1)
    return out, mean


def has_line_pattern(rgb, share=0.25, periodic=0.40):
    """True when the tile carries straight, regularly spaced lines along an
    axis: a rug's ribs, a knit's rows, a plain weave's threads.

    flatten_drift() only reports broad stripes and checks; fine ribs passed
    as "uniform" and stochastic tiling then shifted every repeat by a random
    offset, so the ribs jogged and ghosted at each seam. Measured at 512 px
    on the detail left after a 17 px box blur: the lines must hold at least
    `share` of that detail's variance (their mean profile across the other
    axis), and the profile must repeat (an autocorrelation peak of at least
    `periodic` after its first minimum). Brushed metal has the first without
    the second: its random scratches tile stochastically without harm.
    """
    lum = rgb[..., :3].astype(np.float32) @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    if lum.shape[0] != 512 or lum.shape[1] != 512:
        img = Image.fromarray(np.clip(lum * 255.0, 0, 255).astype(np.uint8))
        lum = np.asarray(img.resize((512, 512), Image.BILINEAR), np.float32) / 255.0
    detail = lum - _box_mean(lum, 8)
    total = float(detail.var())
    if total < 1e-9:
        return False
    rows, cols = detail.mean(axis=1), detail.mean(axis=0)
    prof = rows if rows.var() >= cols.var() else cols
    if float(prof.var()) / total < share:
        return False
    prof = prof - prof.mean()
    ac = np.correlate(prof, prof, "full")[len(prof) - 1:]
    ac = ac / max(float(ac[0]), 1e-12)
    k, half = 1, len(ac) // 2
    while k < half and ac[k + 1] < ac[k]:
        k += 1
    return bool(k < half and float(ac[k:half].max()) >= periodic)


def compress_albedo(rgb, floor_8bit=matphys.ALBEDO_FLOOR_ERROR,
                    ceiling_8bit=matphys.ALBEDO_CEILING):
    """Bring an over- or under-exposed photo into the plausible albedo range
    without flattening it; clamp_albedo() stays the hard backstop.

    The clamp alone clipped: half the pixels of a white cotton photo landed
    on the ceiling and nine tenths of a black marble on the floor, and the
    weave or veining in them went flat (15-27 % of the fine contrast).
      * Too bright: one exposure change for the whole photo, so its 99.5th
        percentile luminance sits on the ceiling. Every ratio in it is kept.
      * Too dark: a toe. Luminance under three floors is squeezed into
        [floor, 3 floors], so the darkest detail keeps two thirds of its
        contrast instead of none.
    A photo already inside the range comes back untouched. Hue is preserved
    (linear scaling); alpha passes through. Returns (rgb, changed: bool).
    """
    arr = rgb.astype(np.float32)
    col = np.nan_to_num(arr[..., :3], nan=0.0, posinf=1.0, neginf=0.0)
    lin = _srgb_to_lin(np.clip(col, 0.0, 1.0))
    w = np.array([0.2126, 0.7152, 0.0722], np.float32)
    y = lin @ w
    lo = float(_srgb_to_lin(np.float32(floor_8bit / 255.0)))
    hi = float(_srgb_to_lin(np.float32(ceiling_8bit / 255.0)))
    top, bottom = (float(v) for v in np.percentile(y, (99.5, 0.5)))
    changed = False
    if top > hi:
        gain = hi / top
        lin, y = lin * gain, y * gain
        changed = True
    if bottom < lo:
        knee = 3.0 * lo
        toe = lo + y * (knee - lo) / knee
        scale = np.where(y < knee, toe / np.maximum(y, 1e-6), 1.0)
        lin = np.where((y <= 1e-6)[..., None], lo, lin * scale[..., None])
        changed = True
    if not changed:
        return rgb, False
    out = np.clip(_lin_to_srgb(lin), 0.0, 1.0).astype(np.float32)
    if arr.shape[-1] > 3:
        out = np.concatenate([out, arr[..., 3:]], axis=-1)
    return out, True


def derive_opacity(img):
    """Alpha channel if the source has one (incl. palette 'P'/'PA' with a
    transparency entry), else None. We cannot invent a cutout from an opaque
    RGB photo without segmentation (forbidden — that would be AI classifying)."""
    if img.mode in ("RGBA", "LA"):
        return _to_float(img.getchannel("A"))
    # palette or other modes that carry transparency -> normalize to RGBA
    if img.mode in ("P", "PA") and "transparency" in img.info:
        return _to_float(img.convert("RGBA").getchannel("A"))
    return None


def _box_mean(a, r):
    """Box mean of radius r px (edges clamped)."""
    if r < 1:
        return a
    c = np.cumsum(np.cumsum(np.pad(a, r, mode="edge").astype(np.float64), 0), 1)
    c = np.pad(c, ((1, 0), (1, 0)))
    k = 2 * r + 1
    h, w = a.shape
    return ((c[k:k + h, k:k + w] - c[:h, k:k + w] - c[k:k + h, :w] + c[:h, :w])
            / (k * k)).astype(np.float32)


def key_plain_background(rgb, tol=0.10):
    """Alpha for a subject shot on a plain backdrop (a leaf on white paper or
    on a grey card), or None when the photo has no plain backdrop.

    Deterministic colour keying, not segmentation. The backdrop is a smooth
    surface fitted through a 2 % border (a quadratic per channel: a lit card
    falls off toward its corners, and one flat colour left a haze of card in
    the corners of a grey-card shot), and it only counts as a backdrop when
    the border follows that surface and the subject covers 5-95 % of the
    frame. Pixels within `tol` of the local backdrop are transparent, with a
    soft ramp for clean edges, except that
      * a pixel of another hue than the backdrop is subject even where its
        tone matches it (an olive leaf on mid-grey keyed out as a hole);
      * a pixel only darker than the backdrop, by less than 45 %, in the
        backdrop's own hue is the subject's shadow on the card, not subject
        (the shadows fattened every cut-out and filled a leaf's splits);
      * specks of card grain go, and the rim is choked one step so no
        card-coloured fringe rides on the cut-out.
    """
    h, w = rgb.shape[:2]
    col = rgb[..., :3].astype(np.float32)
    b = max(2, int(min(h, w) * 0.02))
    ring = np.zeros((h, w), bool)
    ring[:b] = ring[-b:] = True
    ring[:, :b] = ring[:, -b:] = True
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    yy = yy / max(h - 1, 1) * 2.0 - 1.0
    xx = xx / max(w - 1, 1) * 2.0 - 1.0

    def basis(x, y):
        return np.stack([np.ones_like(x), x, y, x * x, y * y, x * y], -1)

    border = col[ring]
    keep = np.abs(border - np.median(border, axis=0)).max(1) < 0.25
    if keep.mean() < 0.6:                    # (a stalk may cross the border)
        return None
    design = basis(xx[ring], yy[ring])[keep]
    coef = np.linalg.lstsq(design, border[keep], rcond=None)[0]
    if float(np.abs(design @ coef - border[keep]).max(axis=1).mean()) > tol * 0.5:
        return None                                   # border isn't a backdrop
    bg = np.clip(basis(xx, yy) @ coef, 1e-3, 1.0).astype(np.float32)
    diff = np.abs(col - bg).max(axis=-1)
    lin, lbg = _srgb_to_lin(np.clip(col, 0.0, 1.0)), _srgb_to_lin(bg)
    lum = np.array([0.2126, 0.7152, 0.0722], np.float32)
    rel = (lin @ lum) / np.maximum(lbg @ lum, 1e-4)
    hue = np.abs(lin / np.maximum(lin.sum(-1, keepdims=True), 1e-4)
                 - lbg / np.maximum(lbg.sum(-1, keepdims=True), 1e-4)).max(axis=-1)
    alpha = np.clip((diff - tol * 0.5) / (tol * 0.5), 0.0, 1.0)
    shadow = (rel > 0.55) & (rel < 1.0)
    alpha = np.where(shadow, alpha * np.clip((0.75 - rel) / 0.2, 0.0, 1.0), alpha)
    alpha = np.maximum(alpha, np.clip((hue - 0.018) / 0.018, 0.0, 1.0)
                       * np.clip(diff / (tol * 0.3), 0.0, 1.0))
    dense = _box_mean((alpha > 0.5).astype(np.float32),
                      max(1, int(round(min(h, w) * 0.004))))
    alpha = alpha * np.clip((dense - 0.35) / 0.2, 0.0, 1.0)
    alpha = np.clip(np.minimum(alpha, _box_mean(alpha, 1) * 1.5 - 0.5), 0.0, 1.0)
    cover = float((alpha > 0.5).mean())
    if not 0.05 <= cover <= 0.95:
        return None
    return alpha.astype(np.float32)


def _to_rgb8(src):
    """PIL image -> 8-bit RGB. Single-channel 16-bit ('I;16*', 'I') and float
    ('F') references are normalised first: PIL's convert('RGB') clips them to
    0-255, so 16-bit greys came out white and 0-1 floats black.

    Integer modes scale by their nominal range (255 / 65535, else the max);
    floats already in 0-1 are kept, otherwise scaled by the max. Negative
    values clip to 0.
    """
    mode = src.mode
    if not (mode.startswith("I") or mode == "F"):
        return src.convert("RGB")
    a = np.asarray(src, dtype=np.float64)
    a = np.nan_to_num(a, nan=0.0, posinf=0.0, neginf=0.0)
    top = float(a.max()) if a.size else 0.0
    if mode.startswith("I;16"):
        scale = 65535.0
    elif mode == "F" and top <= 1.0:
        scale = 1.0
    elif top <= 255.0:
        scale = 255.0
    elif top <= 65535.0:
        scale = 65535.0
    else:
        scale = top
    a = np.clip(a / scale, 0.0, 1.0)
    return Image.fromarray((a * 255.0 + 0.5).astype(np.uint8)).convert("RGB")


def _tick(progress, n, label):
    if callable(progress):
        try:
            progress(n, 3, label)
        except Exception:
            pass


def transmission_tint(albedo_srgb, min_chroma=0.15, strength=0.85):
    """Body colour of a transparent material from its photo, or None.

    Refractive classes ignore the albedo (refraction takes the energy), so an
    amethyst or a green bottle photographed for MatForge rendered colourless.
    Only the chroma of the body colour is used, normalised so the brightest
    channel transmits fully: a clear pane on a white or dark backdrop stays
    clear, and photos with weak colour (chroma < min_chroma) return None.
    The body is the more saturated half of the pixels bar the darkest 5 %,
    as a median chromaticity: glints and pale facets are surface reflection,
    and the linear mean they dominate lifted red toward blue (an amethyst
    photo at red 0.84 of blue gave 0.94), so thick facets in warm light
    rendered magenta.
    Returns the transmittance (0-1 linear RGB) of one recipe thickness.
    """
    lin = _srgb_to_lin(np.clip(albedo_srgb[..., :3], 0.0, 1.0)).reshape(-1, 3)
    peak = lin.max(axis=1)
    chroma = (peak - lin.min(axis=1)) / np.maximum(peak, 1e-6)
    body = lin[(chroma >= np.percentile(chroma, 50)) & (peak >= np.percentile(peak, 5))]
    colour = np.median(body / np.maximum(body.sum(axis=1, keepdims=True), 1e-6), axis=0)
    top = float(colour.max())
    if top <= 1e-4:
        return None
    rel = colour / top
    if 1.0 - float(rel.min()) < min_chroma:
        return None
    tint = 1.0 - strength * (1.0 - rel)
    return tuple(round(float(c), 4) for c in tint)


def generate_maps(image_path, out_dir, mclass="generic", resolution="4k",
                  seamless=True, warnings=None, name="",
                  clamp_albedo_range=True, progress=None, extra=None):
    """Derive the full PBR set. Returns {map_name: absolute_path}.

    `progress`, if callable, is called as progress(n, total, label) at three
    phase boundaries; exceptions raised by it are swallowed.

    If `warnings` is a list, non-fatal advisories (e.g. foliage with no alpha)
    are appended to it for the caller to surface to the artist.

    If `extra` is a dict it receives non-map results for the manifest:
    "transmission_tint" for refractive classes photographed in colour,
    "grid_tiles" for a re-laid tile grid, and "pattern" when flatten_drift()
    kept a uniform class's stripe or check (the builder then skips
    stochastic tiling).
    """
    recipe = get_recipe(mclass)
    size = RESOLUTIONS[resolution.lower()]
    os.makedirs(out_dir, exist_ok=True)

    _tick(progress, 1, "Reading the photo")
    src = Image.open(image_path)
    opacity = derive_opacity(src)
    native = max(1, min(src.size))          # the photo's real detail limit
    src8 = _to_rgb8(src)
    rgb_img = _resize_square(src8, size)
    rgb = _to_float(rgb_img)
    relief = recipe.get("relief", "full")
    if recipe.get("opacity"):
        # a cut-out (leaf, decal) is a single object, not a repeating
        # texture: edge cross-fading would smear the backdrop into it
        seamless = False
        if opacity is None:
            keyed = key_plain_background(rgb)
            if keyed is not None:
                opacity = keyed
                if warnings is not None:
                    warnings.append("cut-out keyed from the plain photo "
                                    "backdrop (no alpha channel)")
    # deterministic per photo: same image -> same roughness noise
    seed = int(np.asarray(rgb_img.resize((16, 16)), dtype=np.int64).sum()) % (2 ** 31)

    _tick(progress, 2, "Making the maps")
    albedo = derive_albedo(rgb)
    if recipe.get("refraction"):
        # Glass, water, gems: the photo gives the body colour, nothing else.
        # A photo of glass is a photo of what lies behind it and of its own
        # edges (a pane's frame, a block's rim), and as an albedo that grid
        # showed in every repeat. One flat colour: its mean.
        albedo = np.broadcast_to(albedo.reshape(-1, albedo.shape[-1]).mean(axis=0),
                                 albedo.shape).astype(np.float32).copy()
    plan = None
    if seamless and recipe.get("grid"):
        plan = _photo_grid_plan(src8, size, rgb, albedo)
        if plan is not None:
            rgb, albedo = apply_grid_plan(rgb, plan), apply_grid_plan(albedo, plan)
            if extra is not None:
                extra["grid_tiles"] = [plan["nx"], plan["ny"]]
    # Tile the photo and the de-lit albedo FIRST: height, roughness and
    # normals then come from periodic filters on a periodic image, so every
    # map tiles without its own seam pass (no blended or flattened seams).
    if seamless:
        # (uniform classes only: in marble or wood a strong vein spacing
        # would pass for a lattice)
        if recipe.get("stationary") and not recipe.get("opacity"):
            (albedo, rgb), cycles = snap_to_lattice(albedo, rgb)
            if cycles != (None, None) and warnings is not None:
                warnings.append("regular weave found: the photo was cropped to whole "
                                "repeats so its edges meet in step")
        albedo = make_seamless(albedo)
        rgb = make_seamless(rgb)
        if recipe.get("stationary") or (recipe.get("plain_unless_tiled") and plan is None):
            notes = []
            albedo = flatten_drift(albedo, warnings=notes)
            if notes and extra is not None:
                # a pattern the flatten left alone: the builder keeps it off
                # stochastic tiling, whose random offsets would break its
                # stripes or checks at every repeat
                extra["pattern"] = True
            if warnings is not None:
                warnings.extend(notes)
            if not notes and has_line_pattern(albedo):
                if extra is not None:
                    extra["pattern"] = True
                if warnings is not None:
                    warnings.append("regular ribs or weave lines found: kept off "
                                    "stochastic tiling so they stay in step")
    # Emissive / refractive albedos carry intent (glow, tint), so never clamp.
    if (clamp_albedo_range and recipe["metalness"] < 0.5
            and not recipe.get("self_illum") and not recipe.get("refraction")
            and not matphys.is_whitelisted(name)):
        albedo, _soft = compress_albedo(albedo)
        albedo, frac = clamp_albedo(albedo)
        if frac > 0.01:
            msg = ("albedo clamp: %.1f%% of pixels moved into the 30\u2013240 "
                   "sRGB range" % (frac * 100.0))
            if warnings is not None:
                warnings.append(msg)
        elif _soft and warnings is not None:
            warnings.append("albedo clamp: the photo ran outside the 30–240 sRGB "
                            "range and was compressed into it (exposure / toe), "
                            "detail kept")
    if recipe.get("leaf_lum_max") and opacity is not None and opacity.shape[:2] == albedo.shape[:2]:
        albedo, was = dim_bright_leaf(albedo, opacity, recipe["leaf_lum_max"])
        if was and warnings is not None:
            warnings.append("leaf photographed brighter than a real leaf (mean "
                            "luminance %.2f): darkened to %.2f"
                            % (was, recipe["leaf_lum_max"]))
    height = derive_height(rgb, relief, upscale=size / float(native))
    grout = None
    if plan is not None:
        # re-laid joints are recessed, matte cement: luminance alone made
        # white grout a raised bead as glossy as the glaze
        grout = grout_mask(plan, _luminance(rgb))
        height = height * (1.0 - grout)
    # Roughness from cavities + tileable noise (not from albedo contrast);
    # both terms tile when the height does.
    rough = derive_roughness(albedo, recipe["base_roughness"],
                             recipe["roughness_variation"], height=height,
                             seed=seed,
                             broad=recipe.get("roughness_broad", 0.45))
    if grout is not None:
        rough = rough + (GROUT_ROUGHNESS - rough) * grout
    ao = derive_ao(height)
    # Periodic Scharr gradients of a periodic height: the normal map tiles
    # by construction (blending its encoded border used to flatten a strip
    # along every seam).
    normal = _renormalize(derive_normal(height, NORMAL_STRENGTH.get(relief, 2.0),
                                        scale=size / 2048.0))
    if seamless:
        ao = make_seamless(ao)          # its low-pass isn't periodic

    out = {}
    def save(name, arr):
        path = os.path.join(out_dir, MAP_FILES[name])
        _to_image(arr).save(path)
        out[name] = os.path.abspath(path)

    if extra is not None and recipe.get("refraction"):
        tint = transmission_tint(albedo)
        if tint is not None:
            extra["transmission_tint"] = tint
    _tick(progress, 3, "Saving the maps")
    save("albedo", albedo)
    save("roughness", rough)
    save("normal", normal)
    save("height", height)
    save("ao", ao)
    if recipe.get("sheen"):
        save("sheen", derive_sheen(albedo))

    if recipe.get("opacity"):
        if opacity is not None:
            op_img = _resize_square(
                Image.fromarray((opacity * 255).astype(np.uint8)), size)
            op = _to_float(op_img)
        else:
            # Honest limitation: a leaf cutout needs a real alpha; we do not
            # invent one from an opaque photo (that would be AI segmentation).
            op = np.ones((size, size), dtype=np.float32)
            msg = ("foliage class: source image has no alpha channel, so the "
                   "opacity map is fully opaque (no leaf silhouette). Supply "
                   "an RGBA/transparent PNG for a real cutout.")
            if warnings is not None:
                warnings.append(msg)
            print("[MatForge][warn] " + msg, file=sys.stderr)
        save("opacity", op)

    return out
