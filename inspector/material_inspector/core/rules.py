"""Inspector rules: pure functions over MaterialRecord -> list[Finding].

Thresholds come from the audited plan (v3 §3/§6, v5 §6). Every number lives in
``RuleConfig`` so Phase 0 calibration can change it without touching rule code.
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from typing import Callable, Iterable

from .colour import (luminance_linear, scale_to_luminance, srgb_luminance_8bit,
                     srgb_to_linear)
from .physics import matphys
from .model import (COLOR_ROLES, DATA_ROLES, ColorSpace, Finding, FixAction, MaterialRecord,
                    Renderer, Severity, SlotRole)


@dataclass(frozen=True)
class RuleConfig:
    # Dielectric base colour, one scalar (Rec.709 luminance, sRGB 0–255). PBR Guide pt 2.
    # Values come from the shared matphys package (one source with MatForge).
    albedo_floor_error: float = matphys.ALBEDO_FLOOR_ERROR      # tolerant floor
    albedo_floor_strict: float = matphys.ALBEDO_FLOOR_STRICT    # strict floor -> warning band 30–50
    albedo_ceiling: float = matphys.ALBEDO_CEILING
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
    # transmittance at 650/550/450 nm (Rubin 1985), from matphys.GLASS["soda_lime"].
    soda_lime_absorption: tuple[float, float, float] = tuple(
        round(c, 3) for c in matphys.transmittance(matphys.glass_sigma_mm("soda_lime"), 10.0))
    soda_lime_distance_mm: float = 10.0
    #: Whitelisted material-name tokens allowed above the albedo ceiling.
    bright_whitelist: tuple[str, ...] = tuple(matphys.BRIGHT_WHITELIST)
    # Largest per-channel linear difference between a named metal's swatch and its measured F0.
    metal_f0_tolerance: float = 0.10
    # M005 seam: score = robust z of the wrap step (median / 1.4826·MAD of the interior
    # adjacent-row/column steps, native pixels) minus seam_tail_ratio × the robust z of the
    # largest interior step, floored at 0. ERROR when score > seam_z_max. The tail term keeps
    # plank edges / grout lines on the border quiet (they recur inside the tile). Measured on
    # the stress corpus: seamless maps score 0; wrap/largest-interior ratio ≤ 1.3 on 11 tileable
    # families at any cyclic offset.
    seam_z_max: float = 4.0
    seam_tail_ratio: float = 1.5
    #: Experimental checks that stay OFF until removed from this tuple (inspector.json:
    #: "rules": {"experimental_off": []}). M013 (upscale) is uncalibrated: it misses
    #: low-contrast 8× upscales and flags native heights with soft bevels (stress B5).
    experimental_off: tuple[str, ...] = ("M013",)


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


def _finite(v) -> bool:
    """A real number we can compare (bools are flags, not values)."""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _finite_colour(c) -> bool:
    try:
        return len(c) >= 3 and all(_finite(x) for x in c[:3])
    except TypeError:
        return False


def _unreadable_reason(path: str) -> str | None:
    """Why an existing path cannot be loaded as an image, or None (missing paths are R004's
    ``file_exists`` case; paths that don't exist on this machine are not judged here)."""
    try:
        if not os.path.lexists(path):
            return None
        if os.path.isdir(path):
            return "is a folder, not an image file"
        if not os.path.exists(path):
            return "is a broken or looping link"
        if not os.path.isfile(path):
            return "is not a regular file"
        if not os.access(path, os.R_OK):
            return "cannot be read (no permission)"
    except (OSError, ValueError):
        return "cannot be checked"
    return None


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
    out = []
    for t in m.textures:
        if not t.path:
            continue
        if t.file_exists is False:
            out.append(Finding("R004", Severity.ERROR, m.name, f"{t.role.value} map file is missing",
                               t.path, None, _tex_label(t)))
            continue
        why = _unreadable_reason(t.path)
        if why:
            out.append(Finding("R004", Severity.ERROR, m.name,
                               f"{t.role.value} map path {why}",
                               f"{t.path} — the renderer cannot load it, so the slot renders as if empty.",
                               None, _tex_label(t)))
    return out


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
    return _finite(met) and met >= cfg.metal_fraction_high


@rule("R007")
def texmap_graph_truncated(m: MaterialRecord, cfg: RuleConfig) -> list[Finding]:
    depth = m.params.get("texmap_truncated")
    if not depth:
        return []
    return [Finding("R007", Severity.INFO, m.name,
                    f"Texture graph deeper than {depth} levels — deeper maps were not inspected",
                    "The walker stops at a fixed depth so a looping or huge graph cannot hang the scan. "
                    "Bitmaps below that depth get no colour-space, missing-file or pixel checks.")]


@rule("R008")
def unreadable_value(m: MaterialRecord, cfg: RuleConfig) -> list[Finding]:
    """NaN / ±inf parameters: the other rules skip them, so say so instead of passing silently."""
    out = []
    for k, v in m.params.items():
        if isinstance(v, bool):
            continue
        bad = (isinstance(v, float) and not math.isfinite(v)) or \
              (isinstance(v, (tuple, list)) and any(isinstance(x, float) and not math.isfinite(x) for x in v))
        if bad:
            out.append(Finding("R008", Severity.INFO, m.name,
                               f"Could not read {k.replace('_', ' ')}: value is {v!r}",
                               "The value is not a finite number (NaN or infinity), so no rule can judge "
                               "it. Re-enter the parameter by hand."))
    return out


@rule("R010")
def albedo_range(m: MaterialRecord, cfg: RuleConfig) -> list[Finding]:
    # Swatch convention: 3ds Max stores colour params scene-linear (picker
    # gamma / OCIO is display only). Metal swatches (R011, R018) are therefore
    # read as linear F0, matching what MatForge writes. The albedo bands below
    # (R010) read the swatch as 8-bit sRGB BY DESIGN: the 30/50/240 limits are
    # the published sRGB albedo charts and the tests pin that semantics.
    col = m.params.get("base_color")
    if col is None or m.has_texture(SlotRole.BASE_COLOR) or not _finite_colour(col):
        return []  # textured albedo is checked on the image (map_checks); NaN swatch -> R008
    if _is_metal(m, cfg):
        return []  # metals: R011 / R018
    lum = srgb_luminance_8bit(col)
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


@rule("R011")
def metal_too_dark(m: MaterialRecord, cfg: RuleConfig) -> list[Finding]:
    col = m.params.get("base_color")
    if col is None or m.has_texture(SlotRole.BASE_COLOR) or not _finite_colour(col) \
            or not _is_metal(m, cfg):
        return []
    if m.params.get("complex_ior"):
        return []  # Corona Complex IOR: n,k drive the reflectance, base colour unused
    y_lin = luminance_linear(col)
    if y_lin >= cfg.metal_luminance_floor:
        return []
    target = max(cfg.metal_luminance_floor, srgb_to_linear(170.0 / 255.0))
    k = target / y_lin if y_lin > 1e-9 else None
    fixed = (tuple(min(max(c * k, 0.0), 1.0) for c in col[:3]) if k is not None
             else (target,) * 3)
    return [Finding("R011", Severity.WARNING, m.name,
                    f"Metal colour is too dark (linear luminance {y_lin:.2f})",
                    "Real metals reflect at least ~40 % of light (titanium film is the "
                    "darkest common metal). Dark 'metals' are usually paint or a wrong map.",
                    FixAction("set_param", "base_color", fixed,
                              "Raise brightness, keep hue"))]


#: Name token -> matphys.METALS key. Whole tokens only ("alu" matches "Alu_Panel", not "value").
METAL_TOKENS = {"gold": "gold", "silver": "silver", "copper": "copper", "brass": "brass",
                "bronze": "bronze", "aluminium": "aluminium", "aluminum": "aluminium",
                "alu": "aluminium", "chrome": "chrome", "chromium": "chrome", "iron": "iron",
                "steel": "stainless_steel", "stainless": "stainless_steel",
                "inox": "stainless_steel", "titanium": "titanium", "nickel": "nickel",
                "zinc": "zinc", "platinum": "platinum"}


def metal_from_name(name: str) -> str | None:
    """First metal token in the material name (split on non-letters), or None."""
    for part in re.split(r"[^a-z]+", (name or "").lower()):
        if part in METAL_TOKENS:
            return METAL_TOKENS[part]
    return None


@rule("R018")
def metal_colour_vs_f0(m: MaterialRecord, cfg: RuleConfig) -> list[Finding]:
    """A metal named after a real metal whose swatch is far from that metal's measured F0.

    Warning only: the metal identity is inferred from the material name.
    """
    col = m.params.get("base_color")
    if col is None or not _finite_colour(col) or not _is_metal(m, cfg) \
            or m.has_texture(SlotRole.BASE_COLOR) or m.params.get("complex_ior"):
        return []
    key = metal_from_name(m.name)
    if key is None:
        return []
    f0 = matphys.metal_f0(key)
    # the swatch is stored scene-linear: compare it to F0 directly, no decode
    d = max(abs(a - b) for a, b in zip(col, f0))
    if d <= cfg.metal_f0_tolerance:
        return []
    label = matphys.METALS[key]["label"]
    return [Finding("R018", Severity.WARNING, m.name,
                    f"Metal colour does not match measured F0 of {label} (max Δ {d:.2f} linear)",
                    "The base colour of a metal is its reflectance at normal incidence (F0), which "
                    "is measured. The metal is guessed from the material name — ignore this if the "
                    "name is not the metal.",
                    FixAction("set_param", "base_color", tuple(f0),
                              "Set base colour to measured F0 (650/550/450 nm)"))]


@rule("R012")
def half_metal(m: MaterialRecord, cfg: RuleConfig) -> list[Finding]:
    met = m.params.get("metalness")
    if not _finite(met) or m.has_texture(SlotRole.METALNESS):
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
        if not _finite(v) or (key == "ior" and _is_metal(m, cfg)):  # NaN / inf -> R008
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
    if not _finite(refr) or refr < cfg.glass_refraction_threshold:
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
    return out


@rule("R016")
def perfect_mirror(m: MaterialRecord, cfg: RuleConfig) -> list[Finding]:
    if m.renderer != Renderer.VRAY:
        return []
    if m.params.get("use_roughness") is False and m.has_texture(SlotRole.GLOSSINESS) is False \
            and not m.has_texture(SlotRole.ROUGHNESS):
        g = m.params.get("glossiness")
        refr = m.params.get("refraction_amount")
        if _finite(g) and g >= 0.999 and (refr if _finite(refr) else 0) < 0.5:
            return [Finding("R016", Severity.WARNING, m.name,
                            "Reflection glossiness is exactly 1.0 — a perfect mirror",
                            "Only mirrors and liquids are this smooth. Polished stone ≈ 0.85–0.95 "
                            "glossiness; most surfaces need a roughness/glossiness map.")]
    return []


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
