"""Checks on the texture pixels themselves (no rendering).

Needs numpy + Pillow (available in 3ds Max's Python via pip, and in the engine).
Every check takes arrays, so tests can feed synthetic maps.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from .model import Finding, Severity

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
                   min_std: float = 0.01) -> list[Finding]:
    s = stats(a)
    if s.distinct < 2 or s.std < min_std:
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
                            expected: Optional[str] = None, min_corr: float = 0.3) -> list[Finding]:
    """expected: 'opengl', 'directx' or None (renderer convention not yet verified)."""
    if normal.shape[:2] != height.shape[:2]:
        from PIL import Image
        h_img = Image.fromarray((np.clip(_gray(height), 0, 1) * 255).astype(np.uint8))
        h_img = h_img.resize((normal.shape[1], normal.shape[0]), Image.BILINEAR)
        height = np.asarray(h_img).astype(np.float32)[..., None] / 255.0
    cx, cy = normal_height_agreement(normal, height)
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
