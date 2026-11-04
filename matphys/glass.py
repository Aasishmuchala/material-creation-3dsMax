"""Dielectric table and renderer-neutral absorption.

Absorption is stored as a transmittance colour T at a reference thickness d
(mm), quoted at 650/550/450 nm. sigma (per mm) = -ln(T) / d. Converters turn
sigma into the V-Ray fog or Corona absorption parameters for a pane of a
given thickness.
"""
import math

_T_MIN = 1e-6

GLASS = {
    "soda_lime": {
        "label": "Soda-lime float glass", "ior": 1.52,
        "transmittance": (0.85, 0.95, 0.95), "thickness_mm": 10.0,
        "source": "Rubin 1985 (as in inspector RuleConfig)", "approx": False},
    "low_iron": {
        "label": "Low-iron (extra clear) glass", "ior": 1.52,
        "transmittance": (0.98, 0.985, 0.98), "thickness_mm": 10.0,
        "source": "typical low-iron float datasheets (approx)", "approx": True},
    "borosilicate": {
        "label": "Borosilicate glass", "ior": 1.47,
        "transmittance": (0.99, 0.99, 0.985), "thickness_mm": 10.0,
        "source": "typical borosilicate datasheets (approx)", "approx": True},
    "fused_silica": {
        "label": "Fused silica", "ior": 1.458,
        "transmittance": (0.999, 0.999, 0.999), "thickness_mm": 10.0,
        "source": "Malitson 1965 (IOR); near-lossless in the visible", "approx": False},
    "lead_crystal": {
        "label": "Lead crystal", "ior": 1.56,
        "transmittance": (0.97, 0.98, 0.97), "thickness_mm": 10.0,
        "source": "typical lead-crystal values (approx)", "approx": True},
    "tinted_bronze": {
        "label": "Tinted glass (bronze)", "ior": 1.52,
        "transmittance": (0.62, 0.50, 0.38), "thickness_mm": 6.0,
        "source": "typical float datasheets (approx)", "approx": True},
    "tinted_grey": {
        "label": "Tinted glass (grey)", "ior": 1.52,
        "transmittance": (0.48, 0.47, 0.45), "thickness_mm": 6.0,
        "source": "typical float datasheets (approx)", "approx": True},
    "tinted_green": {
        "label": "Tinted glass (green)", "ior": 1.52,
        "transmittance": (0.60, 0.82, 0.70), "thickness_mm": 6.0,
        "source": "typical float datasheets (approx)", "approx": True},
    "water": {
        "label": "Water (pure)", "ior": 1.333,
        "transmittance": (0.712, 0.945, 0.991), "thickness_mm": 1000.0,
        "source": "Pope & Fry 1997 a=(0.340,0.0565,0.0092)/m", "approx": False},
    "ice": {
        "label": "Ice", "ior": 1.31,
        "transmittance": (0.70, 0.95, 0.995), "thickness_mm": 1000.0,
        "source": "Warren & Brandt 2008 (approx)", "approx": True},
}


def _get(key):
    try:
        return GLASS[key]
    except KeyError:
        raise KeyError("unknown glass %r" % (key,))


def glass_ior(key):
    return _get(key)["ior"]


def glass_sigma_mm(key):
    """Absorption coefficient per mm, per channel: -ln(T) / d."""
    g = _get(key)
    d = float(g["thickness_mm"])
    return tuple(-math.log(min(max(t, _T_MIN), 1.0)) / d for t in g["transmittance"])


def sigma_from_transmittance(transmittance_rgb, thickness_mm):
    """Absorption per mm from a transmittance colour T at thickness_mm
    (recipes without a named glass, e.g. gemstone): -ln(T) / d."""
    d = float(thickness_mm)
    return tuple(-math.log(min(max(float(t), _T_MIN), 1.0)) / d
                 for t in transmittance_rgb)


def transmittance(sigma_mm, thickness_mm):
    """Beer-Lambert transmittance exp(-sigma d) per channel."""
    return tuple(math.exp(-s * thickness_mm) for s in sigma_mm)


def to_vray_fog(sigma_mm, thickness_mm, mm_per_scene_unit):
    """(fog_color, fog_mult) so one pane of thickness_mm reproduces T.

    fog_color = T(thickness); fog_mult = mm_per_scene_unit / thickness_mm.
    V-Ray's fog falloff model is an approximation (see VERIFY).
    """
    colour = transmittance(sigma_mm, thickness_mm)
    return colour, float(mm_per_scene_unit) / float(thickness_mm)


def to_corona_absorption(sigma_mm, thickness_mm, mm_per_scene_unit):
    """(absorption_color, distance_in_scene_units) for CoronaPhysicalMtl."""
    colour = transmittance(sigma_mm, thickness_mm)
    return colour, float(thickness_mm) / float(mm_per_scene_unit)


def glass_choices():
    return [(k, v["label"]) for k, v in GLASS.items()]
