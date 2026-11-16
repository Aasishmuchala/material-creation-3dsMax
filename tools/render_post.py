"""Turn 16-bit renders into dithered 8-bit PNGs (system Python, needs cv2).

V-Ray's denoised output is smooth enough that a plain 8-bit save bands on
flat walls: R, G and B each step one code value at different places, which
reads as pink and green blotches. 3ds Max writes 16-bit PNGs instead; this
adds triangular (TPDF) dither of +/-1 code value, about what a camera
sensor's noise does, quantises to 8 bits, and keeps the 16-bit master in a
16bit/ subfolder. An optional photographic grade (bloom, halation, S-curve or
toe, vignette) runs on the way down.
"""
import os
import zlib

import cv2
import numpy as np

TOE_PIVOT = 0.72    # on screen, a wall metered to 0.48 linear (bench1's PATCH_EXPOSURE)


def tone_curve(x, amount):
    """Gentle photographic S-curve on display values in [0, 1]: a blend of the
    identity and smoothstep, so 0 and 1 stay put, shadows deepen and upper
    mid-tones lift. V-Ray's Reinhard gives a shoulder but no toe, and the
    apartment's white rooms read flat without one. The blend fades out above
    0.7 (gone by 0.95): lifting the highlights too pushed sunlit white fabric
    to paper-white and erased its weave."""
    t = np.clip((x - 0.7) / 0.25, 0.0, 1.0)
    w = amount * (1.0 - t * t * (3.0 - 2.0 * t))
    return (1.0 - w) * x + w * x * x * (3.0 - 2.0 * x)


def toe_curve(x, k, pivot=TOE_PIVOT):
    """Toe-only curve on display values in [0, 1]: pivot * (x / pivot) ** k
    below the pivot, x itself from the pivot up. Pivoted at the metered wall,
    k > 1 deepens the shadows and lower mid-tones and leaves the wall, the
    windows and the sunlit whites exactly as they were; tone_curve pivots at
    0.5, under most of a high-key frame, and mostly lifts its 0.5-0.7 band
    (bench1 graded with it read flat). Continuous at the pivot (both sides
    give pivot there) and monotonic for k > 0; the slope steps from k to 1
    across it."""
    p = np.float32(pivot)
    lo = p * (np.clip(x, 0.0, p) / p) ** np.float32(k)
    return np.where(x < p, lo, x)


def bloom(x, amount, threshold=0.92, sigma_frac=0.006):
    """Lens bloom on display values in [0, 1] (H x W x 3): what lies above
    `threshold` is blurred (sigma a fraction of the image width) and added
    back, so windows and specular hot spots glow softly into their
    surroundings as they do through a real lens. Below the threshold nothing
    changes. (At 0.82 and a 1.5 % blur every sunlit white haloed.)"""
    hl = np.clip((x - np.float32(threshold)) / np.float32(1.0 - threshold), 0.0, 1.0) * x
    sigma = max(1.0, sigma_frac * x.shape[1])
    glow = cv2.GaussianBlur(hl, (0, 0), sigmaX=sigma, sigmaY=sigma)
    return np.minimum(x + np.float32(amount) * glow, np.float32(1.0))


def halation(x, amount, threshold=0.90, sigma_frac=0.025):
    """bloom()'s wide companion for blown windows: halation, the faint haze a
    window throws far over the wall and frame round it (light scattered in
    the lens and back off the film). The same pass with a lower threshold and
    a blur about four times wider; nothing below the threshold glows."""
    return bloom(x, amount, threshold, sigma_frac)


def vignette(x, amount):
    """Darken toward the corners, as a lens does: 1 - amount at the corners,
    no change inside about 60 % of the half-diagonal."""
    h, w = x.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.sqrt(((xx - (w - 1) / 2.0) / ((w - 1) / 2.0)) ** 2 +
                ((yy - (h - 1) / 2.0) / ((h - 1) / 2.0)) ** 2) / np.float32(np.sqrt(2.0))
    t = np.clip((r - 0.6) / 0.4, 0.0, 1.0)
    fall = np.float32(1.0) - np.float32(amount) * t * t * (3.0 - 2.0 * t)
    return x * fall[:, :, None]


def to8(path, master_dir, curve=0.0, glow=0.0, vig=0.0, toe=0.0, halo=0.0, toe_pivot=TOE_PIVOT):
    """Dither one 16-bit PNG down to 8 bits in place. False if not 16-bit.
    The grade, each 0 = none, runs in this order before dithering: glow
    (bloom amount), halo (halation amount), curve (S-curve amount), toe (the
    toe curve's exponent k, pivoted at toe_pivot), vig (vignette amount).
    The S-curve is the apartment's, the toe the benchmarks'; the spill of
    light comes first, as the lens adds it before the film responds."""
    a = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if a is None or a.dtype != np.uint16:
        return False
    os.makedirs(master_dir, exist_ok=True)
    os.replace(path, os.path.join(master_dir, os.path.basename(path)))
    rng = np.random.default_rng(zlib.crc32(os.path.basename(path).encode()))
    f = a.astype(np.float32) * np.float32(255.0 / 65535.0)
    if f.ndim == 3 and f.shape[2] == 4:          # alpha: quantise, no dither
        alpha = f[:, :, 3].copy()
        f = f[:, :, :3]
    else:
        alpha = None
    if curve or glow or vig or toe or halo:
        x = f / np.float32(255.0)
        if glow:
            x = bloom(x, glow)
        if halo:
            x = halation(x, halo)
        if curve:
            x = tone_curve(x, np.float32(curve))
        if toe:
            x = toe_curve(x, toe, toe_pivot)
        if vig:
            x = vignette(x, vig)
        f = x * np.float32(255.0)
    f += rng.random(f.shape, dtype=np.float32) - rng.random(f.shape, dtype=np.float32)
    out = np.clip(np.rint(f), 0, 255).astype(np.uint8)
    if alpha is not None:
        out = np.dstack([out, np.clip(np.rint(alpha), 0, 255).astype(np.uint8)])
    cv2.imwrite(path, out)
    return True


def process_dir(d, master="16bit", curve=0.0, glow=0.0, vig=0.0, toe=0.0, halo=0.0,
                toe_pivot=TOE_PIVOT):
    """Dither every 16-bit render in d (skips _cal_/_exp_ exposure probes),
    graded as to8 says."""
    n = 0
    for fn in sorted(os.listdir(d)):
        if fn.lower().endswith(".png") and not fn.startswith("_"):
            n += to8(os.path.join(d, fn), os.path.join(d, master), curve, glow, vig,
                     toe=toe, halo=halo, toe_pivot=toe_pivot)
    return n
