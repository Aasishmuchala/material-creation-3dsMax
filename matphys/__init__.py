"""matphys - shared physics tables for MatForge and the Material Inspector.

Pure Python, zero dependencies, Python 3.7 syntax.

Wavelength convention: every spectral quantity here (metal n,k, glass
transmittance) is sampled at a single triplet, 650 / 550 / 450 nm, used as
R / G / B. This is a point-sample approximation; a D65-illuminant / CIE
colour-matching-function weighted projection of the full spectra is future
work.

Colours returned by the physics functions (F0, edge tint, transmittance) are
linear, and are written into Max colour swatches as-is: Max stores colour
parameters scene-linear (gamma / OCIO only affects the picker display).
display_encode() is kept for display-side use only; the builders never call it.
"""
from .colour import (
    srgb_to_linear, linear_to_srgb, luminance_linear, srgb_luminance_8bit,
    scale_to_luminance, rgb_to_linear, rgb_to_srgb, display_encode,
)
from .fresnel import (
    f0, fresnel_conductor, reflectance_at, edge_tint,
    rgb_f0, rgb_edge_tint, rgb_reflectance_at,
)
from .metals import METALS, metal_f0, metal_edge_tint, metal_nk, metal_choices
from .glass import (
    GLASS, glass_ior, glass_sigma_mm, transmittance, to_vray_fog,
    to_corona_absorption, glass_choices,
)
from .albedo import (
    ALBEDO_FLOOR_ERROR, ALBEDO_FLOOR_STRICT, ALBEDO_CEILING, BRIGHT_WHITELIST,
    is_whitelisted, clamp_albedo_srgb,
)

WAVELENGTHS_NM = (650.0, 550.0, 450.0)

__all__ = [
    "WAVELENGTHS_NM",
    "srgb_to_linear", "linear_to_srgb", "luminance_linear", "srgb_luminance_8bit",
    "scale_to_luminance", "rgb_to_linear", "rgb_to_srgb", "display_encode",
    "f0", "fresnel_conductor", "reflectance_at", "edge_tint",
    "rgb_f0", "rgb_edge_tint", "rgb_reflectance_at",
    "METALS", "metal_f0", "metal_edge_tint", "metal_nk", "metal_choices",
    "GLASS", "glass_ior", "glass_sigma_mm", "transmittance", "to_vray_fog",
    "to_corona_absorption", "glass_choices",
    "ALBEDO_FLOOR_ERROR", "ALBEDO_FLOOR_STRICT", "ALBEDO_CEILING", "BRIGHT_WHITELIST",
    "is_whitelisted", "clamp_albedo_srgb",
]
