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
}


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


def _resize_square(img, size):
    """Center-crop to square, then resize to target size."""
    w, h = img.size
    side = min(w, h)
    left, top = (w - side) // 2, (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    return img.resize((size, size), Image.LANCZOS)


def make_seamless(arr, border=0.08):
    """Make the map tile by cross-fading each edge toward the opposite edge.

    Weight ramps from 0.5 at the image border to 0 at the inner end of the
    blend band, so opposite edges become identical (both 50/50 mixes of the
    same two strips) while the interior is untouched.
    """
    squeeze = arr.ndim == 2
    a = arr[..., None] if squeeze else arr
    h, w = a.shape[:2]
    bw, bh = max(2, int(w * border)), max(2, int(h * border))

    out = a.copy()
    # horizontal: blend left band with mirrored right band and vice versa
    wx = np.linspace(0.5, 0.0, bw, dtype=np.float32)[None, :, None]
    left, right = a[:, :bw].copy(), a[:, w - bw:].copy()
    out[:, :bw] = left * (1 - wx) + right[:, ::-1] * wx
    out[:, w - bw:] = right * (1 - wx[:, ::-1]) + left[:, ::-1] * wx[:, ::-1]
    # vertical: same treatment on the result
    a2 = out
    wy = np.linspace(0.5, 0.0, bh, dtype=np.float32)[:, None, None]
    top, bottom = a2[:bh, :].copy(), a2[h - bh:, :].copy()
    out[:bh, :] = top * (1 - wy) + bottom[::-1, :] * wy
    out[h - bh:, :] = bottom * (1 - wy[::-1]) + top[::-1, :] * wy[::-1]
    return out[..., 0] if squeeze else out


def derive_albedo(rgb):
    """De-light: remove the low-frequency *luminance* (shading) while keeping
    hue and genuine albedo variation.

    Dividing each channel by its OWN low-frequency (the old approach) shifts
    hue under chromatic shading and repaints large colored regions toward the
    global mean. Instead we compute one achromatic gain from the luminance of
    the low-frequency, normalize to the image's mean luminance, and clamp the
    gain so bright-thin-over-dark features don't blow out to white.
    """
    low = _lowfreq(rgb)
    low_lum = _luminance(low)[..., None]
    target = float(_luminance(rgb).mean())
    gain = np.clip(target / np.maximum(low_lum, 0.02), 0.5, 2.0)
    return np.clip(rgb * gain, 0.0, 1.0)


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


def derive_height(rgb):
    lum = _luminance(rgb)
    # remove global shading trend so height is local relief, not lighting
    detail = lum - _lowfreq(lum)
    lo, hi = np.percentile(detail, 1), np.percentile(detail, 99)
    return np.clip((detail - lo) / max(hi - lo, 1e-6), 0.0, 1.0)


def derive_normal(height, strength=2.0):
    # Periodic (wrap-around) central differences so that when `height` tiles
    # seamlessly, the normal map tiles too. np.gradient uses one-sided diffs
    # at the borders, which left a visible ridge along every seam even though
    # the height was seamless.
    h = height.astype(np.float32)
    gx = 0.5 * (np.roll(h, -1, axis=1) - np.roll(h, 1, axis=1))
    gy = 0.5 * (np.roll(h, -1, axis=0) - np.roll(h, 1, axis=0))
    nx, ny = -gx * strength, -gy * strength
    nz = np.ones_like(h)
    norm = np.sqrt(nx * nx + ny * ny + nz * nz)
    n = np.stack([nx / norm, ny / norm, nz / norm], axis=-1)
    return n * 0.5 + 0.5  # tangent-space encode


def derive_roughness(rgb, base, variation):
    """base roughness +/- variation driven by local detail contrast.

    Uniform roughness is the #1 CG tell — the variation term is the point.
    """
    lum = _luminance(rgb)
    detail = np.abs(lum - _lowfreq(lum))
    d = detail / max(float(np.percentile(detail, 98)), 1e-6)
    rough = base + (np.clip(d, 0, 1) - 0.5) * 2.0 * variation
    return np.clip(rough, 0.02, 1.0)


def derive_ao(height):
    """Occlusion approximation: recessed-below-neighborhood areas darken."""
    cavity = _lowfreq(height, factor=24) - height
    ao = 1.0 - np.clip(cavity, 0.0, None) * 1.8
    return np.clip(ao, 0.0, 1.0)


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


def generate_maps(image_path, out_dir, mclass="generic", resolution="4k",
                  seamless=True, warnings=None, name="",
                  clamp_albedo_range=True, progress=None):
    """Derive the full PBR set. Returns {map_name: absolute_path}.

    `progress`, if callable, is called as progress(n, total, label) at three
    phase boundaries; exceptions raised by it are swallowed.

    If `warnings` is a list, non-fatal advisories (e.g. foliage with no alpha)
    are appended to it for the caller to surface to the artist.
    """
    recipe = get_recipe(mclass)
    size = RESOLUTIONS[resolution.lower()]
    os.makedirs(out_dir, exist_ok=True)

    _tick(progress, 1, "Reading the photo")
    src = Image.open(image_path)
    opacity = derive_opacity(src)
    rgb_img = _resize_square(_to_rgb8(src), size)
    rgb = _to_float(rgb_img)

    _tick(progress, 2, "Making the maps")
    albedo = derive_albedo(rgb)
    # Emissive / refractive albedos carry intent (glow, tint), so never clamp.
    if (clamp_albedo_range and recipe["metalness"] < 0.5
            and not recipe.get("self_illum") and not recipe.get("refraction")
            and not matphys.is_whitelisted(name)):
        albedo, frac = clamp_albedo(albedo)
        if frac > 0.01:
            msg = ("albedo clamp: %.1f%% of pixels moved into the 30\u2013240 "
                   "sRGB range" % (frac * 100.0))
            if warnings is not None:
                warnings.append(msg)
    height = derive_height(rgb)
    # Measure roughness variation from the DE-LIT albedo, not the raw photo:
    # raw specular highlights (the smoothest spots) would otherwise push
    # roughness UP where it should go down. (Full cavity-correlation is a
    # de-light-v2 item.)
    rough = derive_roughness(albedo, recipe["base_roughness"],
                             recipe["roughness_variation"])

    # Make height seamless FIRST so AO and normal derive from the same tiled
    # height field (keeps cavity dirt and relief consistent at the seams).
    if seamless:
        albedo = make_seamless(albedo)
        height = make_seamless(height)
        rough = make_seamless(rough)
    ao = derive_ao(height)
    # Periodic gradients keep the interior consistent; blending the encoded
    # normal's border guarantees tile edges match exactly.
    normal = derive_normal(height)
    if seamless:
        ao = make_seamless(ao)
        normal = make_seamless(normal)

    out = {}
    def save(name, arr):
        path = os.path.join(out_dir, MAP_FILES[name])
        _to_image(arr).save(path)
        out[name] = os.path.abspath(path)

    _tick(progress, 3, "Saving the maps")
    save("albedo", albedo)
    save("roughness", rough)
    save("normal", normal)
    save("height", height)
    save("ao", ao)

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
