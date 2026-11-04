"""Checks on the texture pixels themselves (no rendering).

Needs numpy + Pillow (available in 3ds Max's Python via pip, and in the engine).
Every check takes arrays, so tests can feed synthetic maps.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from .model import Finding, FixAction, Severity

# ---------------------------------------------------------------- loading

def load_map(path: str, max_side: int = 1024) -> np.ndarray:
    """Load an image as float32 in [0, 1], H×W×C, downsampled for speed.

    Pixel values are returned as stored (no colour conversion): callers decide
    whether the file is sRGB-encoded or linear data.
    """
    from PIL import Image
    im = Image.open(path)
    if max(im.size) > max_side:
        im.thumbnail((max_side, max_side), Image.BILINEAR)
    mode_max = 65535.0 if im.mode in ("I;16", "I;16B", "I") else 255.0
    if im.mode not in ("L", "RGB", "RGBA", "I;16", "I;16B", "I"):
        im = im.convert("RGB"); mode_max = 255.0
    a = np.asarray(im).astype(np.float32) / mode_max
    if a.ndim == 2:
        a = a[..., None]
    return np.clip(a, 0.0, 1.0)


def load_crop(path: str, side: int = 1024) -> np.ndarray:
    """Centre crop at native resolution (whole image if smaller), float32 H×W×C in [0, 1].

    Resolution checks need the stored pixels; ``load_map`` downsamples, which would
    hide (or fake) upscaling.
    """
    from PIL import Image
    im = Image.open(path)
    w, h = im.size
    if w > side or h > side:
        cw, ch = min(w, side), min(h, side)
        x0, y0 = (w - cw) // 2, (h - ch) // 2
        im = im.crop((x0, y0, x0 + cw, y0 + ch))
    mode_max = 65535.0 if im.mode in ("I;16", "I;16B", "I") else 255.0
    if im.mode not in ("L", "RGB", "RGBA", "I;16", "I;16B", "I"):
        im = im.convert("RGB"); mode_max = 255.0
    a = np.asarray(im).astype(np.float32) / mode_max
    if a.ndim == 2:
        a = a[..., None]
    return np.clip(a, 0.0, 1.0)


def _gray(a: np.ndarray) -> np.ndarray:
    return a[..., 0] if a.shape[-1] == 1 else a[..., :3].mean(axis=-1)


def _srgb_to_linear(a: np.ndarray) -> np.ndarray:
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(a: np.ndarray) -> np.ndarray:
    a = np.clip(a, 0, 1)
    return np.where(a <= 0.0031308, a * 12.92, 1.055 * a ** (1 / 2.4) - 0.055)


@dataclass
class MapStats:
    mean: float
    std: float
    p01: float
    p99: float
    distinct: int


def stats(a: np.ndarray) -> MapStats:
    g = _gray(a)
    q = np.round(g * 255).astype(np.int32)
    return MapStats(float(g.mean()), float(g.std()), float(np.percentile(g, 1)),
                    float(np.percentile(g, 99)), int(np.unique(q).size))

# ---------------------------------------------------------------- albedo

def check_albedo(a: np.ndarray, material: str, label: str,
                 floor: float = 30.0, strict: float = 50.0, ceiling: float = 240.0,
                 metal_mask: Optional[np.ndarray] = None,
                 max_fraction: float = 0.05) -> list[Finding]:
    """Per-pixel Rec.709 luminance (sRGB 0–255) on an sRGB-encoded albedo map."""
    rgb = a[..., :3] if a.shape[-1] >= 3 else np.repeat(a, 3, axis=-1)
    lin = _srgb_to_linear(rgb)
    y = 0.2126 * lin[..., 0] + 0.7152 * lin[..., 1] + 0.0722 * lin[..., 2]
    lum = _linear_to_srgb(y) * 255.0
    valid = np.ones(lum.shape, bool) if metal_mask is None else (metal_mask < 0.5)
    if not valid.any():
        return []
    lv = lum[valid]
    out = []
    dark = float((lv < floor).mean()); dim = float((lv < strict).mean())
    bright = float((lv > ceiling).mean())
    if dark > max_fraction:
        out.append(Finding("M001", Severity.ERROR, material,
                           f"{dark:.0%} of the albedo is darker than any real surface (< {floor:.0f} sRGB)",
                           "Usually baked shadows/AO or a photo shot too dark. Re-capture or lift the "
                           "map's levels.", None, label))
    elif dim > max_fraction * 4:
        out.append(Finding("M001", Severity.WARNING, material,
                           f"{dim:.0%} of the albedo is below the strict floor ({strict:.0f} sRGB)",
                           "Fine for coal, asphalt or black rubber; otherwise too dark.", None, label))
    if bright > max_fraction:
        out.append(Finding("M002", Severity.WARNING, material,
                           f"{bright:.0%} of the albedo is brighter than real paint (> {ceiling:.0f} sRGB)",
                           "Usually baked highlights or an over-exposed photo.", None, label))
    return out

# ---------------------------------------------------------------- roughness / gloss / metal

def check_constant(a: np.ndarray, material: str, label: str, role: str,
                   min_std: float = 0.01, span_min: float = 0.04) -> list[Finding]:
    """Flat map: one value, tiny spread, or a p01–p99 span narrower than ``span_min``.

    The span test catches generator output that is "noise on a constant" (e.g. every
    pixel in 0.50–0.52): std is above ``min_std`` but the map carries no real variation.
    """
    s = stats(a)
    if s.distinct < 2 or s.std < min_std or (s.p99 - s.p01) < span_min:
        return [Finding("M003", Severity.WARNING, material,
                        f"{role} map is effectively a single value ({s.mean:.2f})",
                        "Real surfaces vary: wear, fingerprints and polish change roughness from "
                        "place to place. A flat map adds memory and no realism.", None, label)]
    return []


def check_metal_bimodal(a: np.ndarray, material: str, label: str,
                        lo: float = 0.05, hi: float = 0.95, max_mid: float = 0.05) -> list[Finding]:
    g = _gray(a)
    mid = float(((g > lo) & (g < hi)).mean())
    if mid > max_mid:
        return [Finding("M004", Severity.WARNING, material,
                        f"{mid:.0%} of the metalness map is neither metal nor non-metal",
                        "Metalness should be 0 or 1 except at edges and under rust/dust layers. "
                        "Large grey areas are usually a mis-converted specular map.", None, label)]
    return []

# ---------------------------------------------------------------- AI-generator signatures

def _resize(g: np.ndarray, w: int, h: int, method) -> np.ndarray:
    from PIL import Image
    return np.asarray(Image.fromarray(np.ascontiguousarray(g, dtype=np.float32)).resize((w, h), method),
                      dtype=np.float64)


def smooth_trend(a: np.ndarray, grid: int = 16) -> tuple[float, float, float]:
    """Smooth low-order brightness trend of an albedo: (score, r2, consistency).

    Box-average sRGB-encoded luminance to ``grid``×``grid`` and fit a quadratic
    surface in (x, y). ``score`` is the fitted surface's range over the mean box
    value; ``r2`` is the share of box-mean variance the fit explains;
    ``consistency`` is the median ratio of measured to fitted neighbour steps.

    Baked key light, AO falloff or a vignette is a smooth trend: high r2, and every
    local step follows the fit (consistency ≈ 1). Planks, tiles and bricks also
    vary at this scale but in steps — flat inside each piece, so most local steps
    are ≈ 0 (consistency ≈ 0). Marble clouds and mottling are not low-order
    (low r2). Plain variance (the old p95 − p05 spread) cannot tell these apart.
    """
    from PIL import Image
    if a.shape[-1] == 1:
        y = a[..., 0].astype(np.float64)
    else:
        lin = _srgb_to_linear(a[..., :3].astype(np.float64))
        y = _linear_to_srgb(0.2126 * lin[..., 0] + 0.7152 * lin[..., 1] + 0.0722 * lin[..., 2])
    s = _resize(y, grid, grid, Image.BOX)
    c = (np.arange(grid) + 0.5) / (grid / 2) - 1
    yy, xx = np.meshgrid(c, c, indexing="ij")
    basis = np.stack([t.ravel() for t in (np.ones_like(xx), xx, yy, xx * xx, xx * yy, yy * yy)], 1)
    coef, *_ = np.linalg.lstsq(basis, s.ravel(), rcond=None)
    fit = (basis @ coef).reshape(grid, grid)
    sst = float(((s - s.mean()) ** 2).sum())
    r2 = 1.0 - float(((s - fit) ** 2).sum()) / sst if sst > 0 else 0.0
    d = np.concatenate([np.diff(s, axis=0).ravel(), np.diff(s, axis=1).ravel()])
    f = np.concatenate([np.diff(fit, axis=0).ravel(), np.diff(fit, axis=1).ravel()])
    keep = np.abs(f) >= 0.25 * max(float(np.abs(f).mean()), 1e-12)
    consistency = float(np.median(d[keep] / f[keep])) if keep.any() else 0.0
    score = float((fit.max() - fit.min()) / max(float(s.mean()), 1e-6))
    return score, r2, consistency


def check_baked_lighting(a: np.ndarray, material: str, label: str, max_score: float = 0.12,
                         min_r2: float = 0.5, min_consistency: float = 0.5) -> list[Finding]:
    s, r2, cons = smooth_trend(a)
    if s > max_score and r2 >= min_r2 and cons >= min_consistency:
        return [Finding("M010", Severity.WARNING, material,
                        f"Albedo carries a smooth brightness gradient (score {s:.2f}, limit "
                        f"{max_score:.2f}) — baked lighting, shadow or vignette",
                        "Albedo must hold only surface colour. A light falloff baked into the map "
                        "repeats on every tile and fights the scene lighting. Typical of photos "
                        "and of image-generator output; flatten it (high-pass / delight) first.",
                        None, label)]
    return []


def curved_fraction(a: np.ndarray, eps: float = 3.0 / 255) -> float:
    """Share of pixels whose second differences along x AND y both exceed ``eps``.

    Piecewise-constant and piecewise-linear maps (masks, flat tiles, bevels) bend
    only along edge lines — one axis at a time — and smooth maps bend by less than
    an 8-bit step anywhere, so both score near 0 (≤ 0.002 measured). Upscaled noise
    bends in both axes almost everywhere (4× bicubic 0.63, 8× 0.13). Maps near 0
    lack fine detail by design and carry no upscaling evidence. ``eps`` sits above
    8-bit quantisation (≤ 2 LSB).
    """
    g = _gray(a).astype(np.float64)
    if min(g.shape) < 3:
        return 1.0
    dxx = np.abs(g[1:-1, 2:] - 2 * g[1:-1, 1:-1] + g[1:-1, :-2])
    dyy = np.abs(g[2:, 1:-1] - 2 * g[1:-1, 1:-1] + g[:-2, 1:-1])
    return float(((dxx > eps) & (dyy > eps)).mean())


#: Upscale factors tested by ``upscale_score`` (2× is too common and too mild to report).
UPSCALE_FACTORS = (3, 4, 6, 8)


def upscale_score(a: np.ndarray, min_band: float = 0.10) -> tuple[float, int]:
    """Spectral cut-off test: (score, factor). Low score = upscaled by ≥ ``factor``.

    A map upscaled k× has (almost) no energy above Nyquist/k while the band just
    below it is full. For each k, score = mean power above 1.15·fc over mean power
    in [0.5, 0.9]·fc (fc = Nyquist/k), counted only when [0.5, 1]·fc holds at least
    ``min_band`` of the AC energy (otherwise the map is smooth and there is no band
    to cut off). Native noise or scans score ≈ 1; a 4× bicubic upscale ≈ 1e-3.
    Returns the lowest score and its k, or (1.0, 0) when no k qualifies.
    """
    g = _gray(a).astype(np.float64)
    h, w = g.shape
    g = (g - g.mean()) * np.outer(np.hanning(h), np.hanning(w))
    p = np.abs(np.fft.fft2(g)) ** 2
    f = np.sqrt(np.fft.fftfreq(h)[:, None] ** 2 + np.fft.fftfreq(w)[None, :] ** 2)
    total = float(p[f > 0].sum())
    best, best_k = 1.0, 0
    if total <= 0:
        return best, best_k
    for k in UPSCALE_FACTORS:
        fc = 0.5 / k
        if float(p[(f >= 0.5 * fc) & (f < fc)].sum()) / total < min_band:
            continue
        inside = float(p[(f >= 0.5 * fc) & (f < 0.9 * fc)].mean())
        s = float(p[f >= 1.15 * fc].mean()) / max(inside, 1e-30)
        if s < best:
            best, best_k = s, k
    return best, best_k


def check_upscaled(a: np.ndarray, material: str, label: str, max_score: float = 0.01,
                   min_side: int = 512, min_curved: float = 0.05) -> list[Finding]:
    """``a`` should come from ``load_crop`` (native pixels). Maps under ``min_side`` make no
    resolution claim worth checking; flat maps are M003's job. Piecewise-constant/linear
    and smooth maps (< ``min_curved`` of pixels bend, see ``curved_fraction``) are
    skipped: they lack fine detail by design, not because they were upscaled."""
    if max(a.shape[:2]) < min_side or float(_gray(a).std()) < 1e-4:
        return []
    if curved_fraction(a) < min_curved:
        return []
    s, k = upscale_score(a)
    if s < max_score:
        return [Finding("M013", Severity.INFO, material,
                        f"Map has almost no detail above 1/{k} of its resolution (score {s:.0e}) — "
                        f"likely upscaled ≥ {k}×",
                        "Its file resolution overstates its real detail: up close it looks soft. "
                        "Common in generated or AI-upscaled maps. Use it at its real texel density "
                        "or regenerate at a higher native resolution.", None, label)]
    return []

# ---------------------------------------------------------------- tiling

def seam_score(a: np.ndarray) -> float:
    """Largest z-score of the wrap-boundary step versus interior steps (values only).

    A seamless tile has a wrap step drawn from the same distribution as interior
    steps (z ≈ 0–2). A visible seam gives a large z. Autocorrelation is NOT a seam
    test (any tiled image is periodic), see plan v3 finding #18.
    """
    g = _gray(a).astype(np.float64)
    scores = []
    for axis in (0, 1):
        x = g if axis == 1 else g.T
        interior = np.abs(np.diff(x, axis=1)).mean(axis=0)   # mean |step| per interior column
        wrap = np.abs(x[:, 0] - x[:, -1]).mean()
        mu, sd = interior.mean(), interior.std() + 1e-9
        scores.append((wrap - mu) / sd)
    return float(max(scores))


def check_seam(a: np.ndarray, material: str, label: str, z_max: float = 4.0) -> list[Finding]:
    z = seam_score(a)
    if z > z_max:
        return [Finding("M005", Severity.ERROR, material,
                        f"Visible tiling seam (score {z:.1f}, limit {z_max:.0f})",
                        "The map's left/right or top/bottom edges don't match, so a line repeats "
                        "across every tile. Make the map tileable before use.", None, label)]
    return []

# ---------------------------------------------------------------- normal vs height

def normal_height_agreement(normal: np.ndarray, height: np.ndarray) -> tuple[float, float]:
    """Correlation of the normal map's X and Y with the height map's −gradient.

    Returns (corr_x, corr_y). For an OpenGL (+Y up) map both are positive;
    a DirectX (−Y) map gives corr_y < 0. Both maps must share size.
    """
    n = normal[..., :3] * 2.0 - 1.0
    h = _gray(height).astype(np.float64)
    gy, gx = np.gradient(h)
    # image rows grow downwards, so +Y (up) in tangent space is −d/drow
    exp_x, exp_y = -gx, gy
    def corr(a, b):
        a = a.ravel() - a.mean(); b = b.ravel() - b.mean()
        d = np.sqrt((a * a).sum() * (b * b).sum())
        return float((a * b).sum() / d) if d > 0 else 0.0
    return corr(n[..., 0], exp_x), corr(n[..., 1], exp_y)


def check_normal_convention(normal: np.ndarray, height: np.ndarray, material: str, label: str,
                            expected: Optional[str] = None, min_corr: float = 0.3,
                            height_label: Optional[str] = None) -> list[Finding]:
    """expected: 'opengl', 'directx' or None (renderer convention not yet verified).

    corr_x is convention-independent (X is never flipped), so a strongly negative
    corr_x means the height map is inverted (pits read as bumps), not a DirectX map.
    """
    if normal.shape[:2] != height.shape[:2]:
        from PIL import Image
        h_img = Image.fromarray((np.clip(_gray(height), 0, 1) * 255).astype(np.uint8))
        h_img = h_img.resize((normal.shape[1], normal.shape[0]), Image.BILINEAR)
        height = np.asarray(h_img).astype(np.float32)[..., None] / 255.0
    cx, cy = normal_height_agreement(normal, height)
    if cx < -min_corr:
        return [Finding("M012", Severity.ERROR, material,
                        f"Height map polarity is inverted relative to the normal map (corr_x {cx:.2f})",
                        "Displacement pushes out where the normal map shows pits and vice versa. "
                        "Generators often export height with white = low.",
                        FixAction("invert_map", height_label or label, True, "Invert the height map"),
                        height_label or label)]
    if abs(cx) < min_corr:
        return [Finding("M006", Severity.WARNING, material,
                        "Normal map doesn't match the height map",
                        f"Correlation with the height gradient is only {cx:.2f}; the two maps may "
                        "come from different sources or scales.", None, label)]
    detected = "opengl" if cy > 0 else "directx"
    if expected and detected != expected:
        return [Finding("M007", Severity.ERROR, material,
                        f"Normal map is {detected.upper()} but the slot expects {expected.upper()}",
                        "Every bump is lit from the wrong side. Flip the green channel in the "
                        "normal-map node.", None, label)]
    return [Finding("M008", Severity.INFO, material,
                    f"Normal map convention detected: {detected.upper()}",
                    f"corr_x={cx:.2f}, corr_y={cy:.2f}", None, label)]
