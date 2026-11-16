"""Small, dependency-free colour helpers (sRGB IEC 61966-2-1, Rec.709 luminance).

Re-exported from the shared ``matphys.colour`` so MatForge and the Inspector use
one implementation.
"""
from __future__ import annotations

from .physics import matphys

srgb_to_linear = matphys.colour.srgb_to_linear
linear_to_srgb = matphys.colour.linear_to_srgb
luminance_linear = matphys.colour.luminance_linear
srgb_luminance_8bit = matphys.colour.srgb_luminance_8bit
scale_to_luminance = matphys.colour.scale_to_luminance
rgb_to_linear = matphys.colour.rgb_to_linear
rgb_to_srgb = matphys.colour.rgb_to_srgb
display_encode = matphys.colour.display_encode

__all__ = ["srgb_to_linear", "linear_to_srgb", "luminance_linear", "srgb_luminance_8bit",
           "scale_to_luminance", "rgb_to_linear", "rgb_to_srgb", "display_encode"]
