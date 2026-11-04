"""Inspector rules: pure functions over MaterialRecord -> list[Finding].

Thresholds come from the audited plan (v3 §3/§6, v5 §6). Every number lives in
``RuleConfig`` so Phase 0 calibration can change it without touching rule code.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Callable, Iterable

from .colour import scale_to_luminance, srgb_luminance_8bit, srgb_to_linear, luminance_linear
from .model import (COLOR_ROLES, DATA_ROLES, ColorSpace, Finding, FixAction, MaterialRecord,
                    Renderer, Severity, SlotRole)


@dataclass(frozen=True)
class RuleConfig:
    # Dielectric base colour, one scalar (Rec.709 luminance, sRGB 0–255). PBR Guide pt 2.
    albedo_floor_error: float = 30.0      # tolerant floor
    albedo_floor_strict: float = 50.0     # strict floor -> warning band 30–50
    albedo_ceiling: float = 240.0
    # Raw metals: linear luminance floor (titanium film ≈ 0.41 is the darkest common metal).
    metal_luminance_floor: float = 0.40
    # A constant metalness strictly between these is a "half metal".
    metal_fraction_low: float = 0.05
    metal_fraction_high: float = 0.95
    # Dielectric IOR tiers (OpenPBR normal range is [1, 3]).
    ior_silent: tuple[float, float] = (1.30, 1.80)
    ior_hard: tuple[float, float] = (1.0, 3.0)
    # Refraction above this counts as "glass-like".
    glass_refraction_threshold: float = 0.5
    # Absorption colour this close to white counts as "no absorption".
    white_tolerance: float = 0.02
    # Default absorption offered by the glass fix: clear soda-lime, 10 mm internal
    # transmittance at 650/550/450 nm (Rubin 1985).
    soda_lime_absorption: tuple[float, float, float] = (0.85, 0.95, 0.95)
    soda_lime_distance_mm: float = 10.0
    #: Whitelisted material-name tokens allowed above the albedo ceiling.
    bright_whitelist: tuple[str, ...] = ("snow", "spectralon", "ptfe", "whitereference")


DEFAULT_CONFIG = RuleConfig()

# ---------------------------------------------------------------- filename hints
_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")
_ROUGH_TOKENS = {"rough", "roughness", "rgh"}
_GLOSS_TOKENS = {"gloss", "glossiness", "gls", "smoothness"}
_NORMAL_TOKENS = {"normal", "nrm", "nor", "nrml", "normalgl", "normaldx"}
_HEIGHT_TOKENS = {"height", "disp", "displacement", "bump"}


def _tokens(path: str | None) -> set[str]:
    if not path:
        return set()
    stem = os.path.splitext(os.path.basename(path))[0].lower()
    toks = {t for t in _TOKEN_SPLIT.split(stem) if t}
    # catch glued names like "wood_NormalGL" -> "normalgl" and camelCase tails
    toks |= {t for t in re.findall(r"[a-z]+", stem)}
    return toks


def filename_says(path: str | None, kind: str) -> bool:
    toks = _tokens(path)
    table = {"rough": _ROUGH_TOKENS, "gloss": _GLOSS_TOKENS,
             "normal": _NORMAL_TOKENS, "height": _HEIGHT_TOKENS}[kind]
    return bool(toks & table)


def _tex_label(t) -> str:
    return os.path.basename(t.path) if t.path else (t.node_name or t.node_class or "texture")


Rule = Callable[[MaterialRecord, RuleConfig], list[Finding]]
_RULES: list[tuple[str, Rule]] = []


def rule(rule_id: str):
    def deco(fn: Rule) -> Rule:
        _RULES.append((rule_id, fn))
        fn.rule_id = rule_id  # type: ignore[attr-defined]
        return fn
    return deco


# ---------------------------------------------------------------- texture rules
@rule("R001")
def data_map_as_srgb(m: MaterialRecord, cfg: RuleConfig) -> list[Finding]:
    """Roughness, gloss, metal, normal, bump, height, opacity maps loaded with sRGB gamma."""
    out = []
    for t in m.textures:
        if t.role in DATA_ROLES and t.color_space == ColorSpace.SRGB:
            out.append(Finding(
                "R001", Severity.ERROR, m.name,
                f"{t.role.value} map is loaded as sRGB — it must be linear",
                "Data maps store numbers, not colours. sRGB decoding bends every value "
                "(e.g. roughness 0.5 is read as ≈0.21), so the surface looks wrong under any light.",
                FixAction("set_color_space", t.node_name or (t.path or ""), ColorSpace.LINEAR.value,
                          "Load this bitmap as linear / Raw (no gamma)"),
                _tex_label(t)))
    return out


@rule("R002")
def colour_map_as_linear(m: MaterialRecord, cfg: RuleConfig) -> list[Finding]:
    out = []
    for t in m.textures:
        if t.role in COLOR_ROLES and t.color_space == ColorSpace.LINEAR and t.path and \
                not t.path.lower().endswith((".exr", ".hdr")):
            out.append(Finding(
                "R002", Severity.WARNING, m.name,
                f"{t.role.value} map (8/16-bit image) is loaded as linear — colour maps are sRGB",
                "Colour photos and painted albedo are sRGB-encoded; loading them linear makes "
                "the material look washed out and too bright.",
                FixAction("set_color_space", t.node_name or t.path, ColorSpace.SRGB.value,
                          "Load this bitmap as sRGB"),
                _tex_label(t)))
    return out


@rule("R003")
def unknown_colour_space(m: MaterialRecord, cfg: RuleConfig) -> list[Finding]:
    return [Finding("R003", Severity.INFO, m.name,
                    f"Could not read the colour space of the {t.role.value} map",
                    "The Inspector reports this instead of guessing. Check the bitmap's colour "
                    "space / gamma setting by hand.", None, _tex_label(t))
            for t in m.textures if t.color_space == ColorSpace.UNKNOWN and t.path]


@rule("R004")
def missing_file(m: MaterialRecord, cfg: RuleConfig) -> list[Finding]:
    return [Finding("R004", Severity.ERROR, m.name, f"{t.role.value} map file is missing",
                    t.path or "", None, _tex_label(t))
            for t in m.textures if t.path and t.file_exists is False]


@rule("R005")
def gloss_rough_swap(m: MaterialRecord, cfg: RuleConfig) -> list[Finding]:
    """A file named 'gloss' in a roughness slot, or 'rough' in a glossiness slot (inverted surface)."""
    out = []
    for t in m.textures:
        wrong = (t.role == SlotRole.ROUGHNESS and filename_says(t.path, "gloss")
                 and not filename_says(t.path, "rough")) or \
                (t.role == SlotRole.GLOSSINESS and filename_says(t.path, "rough")
                 and not filename_says(t.path, "gloss"))
        if not wrong:
            continue
        fix = None
        if m.renderer == Renderer.VRAY:
            fix = FixAction("toggle_use_roughness", "use_roughness",
                            t.role == SlotRole.GLOSSINESS,
                            "Switch VRayMtl BRDF 'Use roughness' to match the map")
        else:
            fix = FixAction("invert_map", t.node_name or (t.path or ""), True,
                            "Invert this map (roughness = 1 − glossiness)")
        out.append(Finding(
            "R005", Severity.ERROR, m.name,
            f"{'Glossiness' if t.role == SlotRole.ROUGHNESS else 'Roughness'} map used as "
            f"{t.role.value} — the surface is inverted",
            "Shiny areas render matte and matte areas shiny. Detected from the file name; "
            "confirm before fixing.", fix, _tex_label(t)))
    return out


@rule("R006")
def normal_map_in_bump(m: MaterialRecord, cfg: RuleConfig) -> list[Finding]:
    out = []
    for t in m.textures:
        if t.role in (SlotRole.BUMP, SlotRole.NORMAL) and t.via_normal_node is False \
                and filename_says(t.path, "normal"):
            out.append(Finding(
                "R006", Severity.ERROR, m.name,
                "Normal map plugged straight into the bump slot",
                "A normal map read as a bump/height map produces noise instead of relief. "
                "It needs a VRayNormalMap / CoronaNormal node.",
                FixAction("insert_normal_node", t.node_name or (t.path or ""), None,
                          "Wrap the bitmap in the renderer's normal-map node"),
                _tex_label(t)))
    return out


# ---------------------------------------------------------------- parameter rules
def _is_metal(m: MaterialRecord, cfg: RuleConfig) -> bool:
    met = m.params.get("metalness")
    return isinstance(met, (int, float)) and met >= cfg.metal_fraction_high


@rule("R010")
def albedo_range(m: MaterialRecord, cfg: RuleConfig) -> list[Finding]:
    col = m.params.get("base_color")
    if col is None or m.has_texture(SlotRole.BASE_COLOR):
        return []  # textured albedo is checked on the image (map_checks), not the swatch
    lum = srgb_luminance_8bit(col)
    if _is_metal(m, cfg):
        y_lin = luminance_linear([srgb_to_linear(c) for c in col])
        if y_lin < cfg.metal_luminance_floor:
            target = srgb_luminance_8bit([cfg.metal_luminance_floor ** (1 / 2.2)] * 3)
            return [Finding("R011", Severity.WARNING, m.name,
                            f"Metal colour is too dark (linear luminance {y_lin:.2f})",
                            "Real metals reflect at least ~40 % of light (titanium film is the "
                            "darkest common metal). Dark 'metals' are usually paint or a wrong map.",
                            FixAction("set_param", "base_color",
                                      scale_to_luminance(col, max(target, 170.0)),
                                      "Raise brightness, keep hue"))]
        return []
    name = m.name.lower()
    if lum < cfg.albedo_floor_error:
        return [Finding("R010", Severity.ERROR, m.name,
                        f"Base colour too dark for a real surface (luminance {lum:.0f} sRGB)",
                        "Below ~30 sRGB nothing real exists except special absorbers; even "
                        "charcoal and fresh asphalt are ≈39.",
                        FixAction("set_param", "base_color",
                                  scale_to_luminance(col, cfg.albedo_floor_strict),
                                  "Raise to 50 sRGB luminance, keep hue"))]
    if lum < cfg.albedo_floor_strict:
        return [Finding("R010", Severity.WARNING, m.name,
                        f"Base colour very dark (luminance {lum:.0f} sRGB, strict floor 50)",
                        "Allowed for coal, asphalt, black rubber; otherwise usually too dark.",
                        FixAction("set_param", "base_color",
                                  scale_to_luminance(col, cfg.albedo_floor_strict),
                                  "Raise to 50 sRGB luminance, keep hue"))]
    if lum > cfg.albedo_ceiling and not any(w in name for w in cfg.bright_whitelist):
        return [Finding("R010", Severity.WARNING, m.name,
                        f"Base colour brighter than real paint or plaster (luminance {lum:.0f} sRGB)",
                        "Above ~240 sRGB only fresh snow and lab reference whites exist. Too-bright "
                        "albedo makes interiors glow and slows convergence.",
                        FixAction("set_param", "base_color",
                                  scale_to_luminance(col, cfg.albedo_ceiling),
                                  "Lower to 240 sRGB luminance, keep hue"))]
    return []


@rule("R012")
def half_metal(m: MaterialRecord, cfg: RuleConfig) -> list[Finding]:
    met = m.params.get("metalness")
    if not isinstance(met, (int, float)) or m.has_texture(SlotRole.METALNESS):
        return []
    if cfg.metal_fraction_low < met < cfg.metal_fraction_high:
        snap = 1.0 if met >= 0.5 else 0.0
        return [Finding("R012", Severity.WARNING, m.name,
                        f"Metalness {met:.2f} — a surface is either metal or not",
                        "Fractional metalness is only real where rust, dust or worn paint sits on "
                        "metal, and then it comes from a mask texture, not a constant.",
                        FixAction("set_param", "metalness", snap, f"Snap metalness to {snap:.0f}"))]
    return []


@rule("R013")
def ior_range(m: MaterialRecord, cfg: RuleConfig) -> list[Finding]:
    out = []
    for key in ("ior", "refraction_ior"):
        v = m.params.get(key)
        if not isinstance(v, (int, float)) or (key == "ior" and _is_metal(m, cfg)):
            continue
        lo, hi = cfg.ior_hard
        slo, shi = cfg.ior_silent
        if v < lo or v > hi:
            out.append(Finding("R013", Severity.ERROR, m.name,
                               f"{key.replace('_', ' ')} {v:.3f} is outside the physical range 1–3",
                               "No ordinary material has an IOR below 1 or above 3.",
                               FixAction("set_param", key, 1.5, "Reset to 1.5 (glass, plastic)")))
        elif not slo <= v <= shi:
            out.append(Finding("R013", Severity.WARNING, m.name,
                               f"{key.replace('_', ' ')} {v:.3f} is unusual",
                               "1.30–1.80 covers ice, water, glass, plastics and sapphire. Diamond "
                               "(2.42) and zirconia (2.16) are real but rare — confirm it's intended."))
    return out


@rule("R014")
def glass_without_absorption(m: MaterialRecord, cfg: RuleConfig) -> list[Finding]:
    refr = m.params.get("refraction_amount")
    if not isinstance(refr, (int, float)) or refr < cfg.glass_refraction_threshold:
        return []
    if m.params.get("thin_walled"):
        return []  # thin sheets (window panes modelled as single planes) need no volume
    absorb = m.params.get("absorption_color")
    no_absorb = absorb is None or all(c >= 1.0 - cfg.white_tolerance for c in absorb)
    if not no_absorb:
        return []
    return [Finding("R014", Severity.WARNING, m.name,
                    "Glass has no absorption colour — real glass is never perfectly clear",
                    "Clear window glass is green at depth (iron); only low-iron glass is nearly "
                    "colourless. Without absorption, thick glass and liquids look like plastic.",
                    FixAction("set_absorption", "absorption_color",
                              {"color": cfg.soda_lime_absorption,
                               "distance_mm": cfg.soda_lime_distance_mm},
                              "Apply clear soda-lime absorption (Rubin 1985, 10 mm)"))]


@rule("R015")
def vray_brdf(m: MaterialRecord, cfg: RuleConfig) -> list[Finding]:
    if m.renderer != Renderer.VRAY:
        return []
    out = []
    brdf = m.params.get("brdf")
    if isinstance(brdf, str) and brdf.lower() != "ggx":
        out.append(Finding("R015", Severity.WARNING, m.name,
                           f"VRayMtl uses the {brdf} BRDF — GGX matches real highlights best",
                           "Phong/Blinn/Ward lack GGX's long highlight tail; scanned and PBR maps "
                           "assume GGX.",
                           FixAction("set_param", "brdf", "ggx", "Switch BRDF to GGX")))
    if m.params.get("use_roughness") is False and m.has_texture(SlotRole.GLOSSINESS) is False \
            and not m.has_texture(SlotRole.ROUGHNESS):
        g = m.params.get("glossiness")
        if isinstance(g, (int, float)) and g >= 0.999 and (m.params.get("refraction_amount") or 0) < 0.5:
            out.append(Finding("R016", Severity.WARNING, m.name,
                               "Reflection glossiness is exactly 1.0 — a perfect mirror",
                               "Only mirrors and liquids are this smooth. Polished stone ≈ 0.85–0.95 "
                               "glossiness; most surfaces need a roughness/glossiness map."))
    return out


@rule("R017")
def legacy_material(m: MaterialRecord, cfg: RuleConfig) -> list[Finding]:
    if not m.params.get("is_legacy"):
        return []
    return [Finding("R017", Severity.INFO, m.name,
                    f"{m.material_class} is a legacy material type",
                    "CoronaLegacyMtl was superseded by CoronaPhysicalMtl in Corona 7. Conversion "
                    "will be offered in the Builder module.")]


# ---------------------------------------------------------------- engine
def all_rules() -> list[tuple[str, Rule]]:
    return list(_RULES)


def inspect_material(m: MaterialRecord, cfg: RuleConfig = DEFAULT_CONFIG,
                     disabled: Iterable[str] = ()) -> list[Finding]:
    disabled = set(disabled)
    out: list[Finding] = []
    for rid, fn in _RULES:
        if rid in disabled:
            continue
        try:
            out.extend(f for f in fn(m, cfg) if f.rule_id not in disabled)
        except Exception as exc:  # a broken rule must never stop a scene scan
            out.append(Finding("R999", Severity.INFO, m.name, f"Rule {rid} failed: {exc!r}"))
    return out


def inspect_scene(materials: Iterable[MaterialRecord], cfg: RuleConfig = DEFAULT_CONFIG,
                  disabled: Iterable[str] = ()) -> list[Finding]:
    out: list[Finding] = []
    for m in materials:
        out.extend(inspect_material(m, cfg, disabled))
    order = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}
    return sorted(out, key=lambda f: (order[f.severity], f.material, f.rule_id))
