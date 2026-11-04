"""Small, dependency-free colour helpers (sRGB IEC 61966-2-1, Rec.709 luminance).

Same behaviour as inspector/material_inspector/core/colour.py (same clamps,
same Rec.709 weights, same zero-luminance branch in scale_to_luminance).
"""


def srgb_to_linear(v):
    v = min(max(v, 0.0), 1.0)
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def linear_to_srgb(v):
    v = min(max(v, 0.0), 1.0)
    return v * 12.92 if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055


def luminance_linear(rgb_linear):
    r, g, b = rgb_linear[:3]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def srgb_luminance_8bit(rgb_srgb):
    """Rec.709 luminance of an sRGB colour, re-encoded to sRGB 0-255.

    This is the single scalar the PBR range checks use (never per channel).
    """
    lin = [srgb_to_linear(c) for c in rgb_srgb[:3]]
    return linear_to_srgb(luminance_linear(lin)) * 255.0


def scale_to_luminance(rgb_srgb, target_8bit):
    """Return the colour with its hue/saturation kept and its luminance moved to target.

    Works in linear space so the ratio between channels is preserved physically.
    """
    lin = [srgb_to_linear(c) for c in rgb_srgb[:3]]
    y = luminance_linear(lin)
    target_lin = srgb_to_linear(target_8bit / 255.0)
    if y <= 1e-9:
        g = target_lin
        return (linear_to_srgb(g),) * 3
    k = target_lin / y
    out = [min(c * k, 1.0) for c in lin]
    return tuple(linear_to_srgb(c) for c in out)


def rgb_to_linear(rgb):
    """sRGB-encoded 3-tuple -> linear 3-tuple."""
    return tuple(srgb_to_linear(c) for c in rgb[:3])


def rgb_to_srgb(rgb):
    """Linear 3-tuple -> sRGB-encoded 3-tuple."""
    return tuple(linear_to_srgb(c) for c in rgb[:3])


def display_encode(rgb_linear, gamma_managed=True):
    """Linear RGB -> display (picker) encoding when gamma_managed.

    NOT for writing swatches: 3ds Max stores colour parameters scene-linear
    and gamma "Affect Color Selectors" / OCIO only changes the picker display,
    so the builders write linear values as-is. Kept for display-side use.
    """
    if gamma_managed:
        return rgb_to_srgb(rgb_linear)
    return tuple(rgb_linear)
