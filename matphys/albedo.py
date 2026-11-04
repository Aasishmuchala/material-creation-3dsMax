"""Albedo range constants (sRGB 8-bit luminance) shared by MatForge and the Inspector."""
from .colour import srgb_luminance_8bit, scale_to_luminance

ALBEDO_FLOOR_ERROR = 30.0    # below: physically implausible (error)
ALBEDO_FLOOR_STRICT = 50.0   # below: suspicious (warning only)
ALBEDO_CEILING = 240.0       # above: only snow / lab reference whites

BRIGHT_WHITELIST = ("snow", "spectralon", "ptfe", "whitereference")


def is_whitelisted(name):
    """True when the material name carries a bright-whitelist token (case-insensitive)."""
    low = (name or "").lower()
    return any(w in low for w in BRIGHT_WHITELIST)


def clamp_albedo_srgb(rgb_srgb, name=""):
    """Move a swatch colour into [floor 30, ceiling 240] luminance, hue kept.

    Returns (rgb, changed). Whitelisted names skip the ceiling; the floor
    always applies.
    """
    rgb = tuple(rgb_srgb[:3])
    lum = srgb_luminance_8bit(rgb)
    if lum < ALBEDO_FLOOR_ERROR:
        return scale_to_luminance(rgb, ALBEDO_FLOOR_ERROR), True
    if lum > ALBEDO_CEILING and not is_whitelisted(name):
        return scale_to_luminance(rgb, ALBEDO_CEILING), True
    return rgb, False
