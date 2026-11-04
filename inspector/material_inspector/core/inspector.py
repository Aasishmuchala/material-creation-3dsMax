"""Orchestrates parameter rules + pixel checks for a list of materials."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Iterable, Optional

from .model import ColorSpace, Finding, MaterialRecord, Severity, SlotRole
from .rules import DEFAULT_CONFIG, RuleConfig, all_rules, inspect_material
from . import map_checks as mc


@dataclass
class InspectorOptions:
    check_pixels: bool = True
    max_side: int = 1024
    #: Expected tangent-space convention per renderer: 'opengl' / 'directx' / None.
    #: None until verified in Phase 0 (see docs/VERIFY.md) — detection is still reported.
    normal_convention: dict = field(default_factory=lambda: {"vray": None, "corona": None, "openpbr": None})
    disabled_rules: tuple = ()
    config: RuleConfig = DEFAULT_CONFIG


#: Data maps whose real resolution matters (M013). Metalness is a mask: sharp or flat by design.
_UPSCALE_ROLES = (SlotRole.ROUGHNESS, SlotRole.GLOSSINESS, SlotRole.NORMAL, SlotRole.DISPLACEMENT)
#: Pixel findings typical of image-generator output (R020 aggregates them).
#: M010 / M013 stay out until calibrated on real scan sets (docs/VERIFY.md row 12).
AI_SIGNATURES = ("M003", "M004")
#: Every finding ID the pixel checks and the scan itself can emit (config validation uses it).
#: M009: scan-level info that M007 is inactive because ``normal_convention`` is unset.
PIXEL_RULE_IDS = ("M001", "M002", "M003", "M004", "M005", "M006", "M007", "M008", "M009",
                  "M010", "M012", "M013", "M900")
SCAN_RULE_IDS = ("R020", "R999")


def known_rule_ids() -> set[str]:
    return {rid for rid, _ in all_rules()} | set(PIXEL_RULE_IDS) | set(SCAN_RULE_IDS)


def _readable(path: Optional[str]) -> bool:
    """A regular file we may open. Directories, broken / looping links and files without read
    permission are reported by R004 instead of being loaded."""
    return bool(path) and os.path.isfile(path) and os.access(path, os.R_OK)  # type: ignore[arg-type]


def _m900(m: MaterialRecord, label: str, exc: BaseException, what: str = "Could not read image") -> Finding:
    return Finding("M900", Severity.INFO, m.name, what, repr(exc), None, label)


def pixel_findings(m: MaterialRecord, opt: InspectorOptions) -> list[Finding]:
    out: list[Finding] = []
    cache: dict[str, object] = {}
    seams: dict[str, float] = {}
    cfg = opt.config

    def get(path):
        if path not in cache:
            try:
                cache[path], seams[path] = mc.load_map_and_seam(path, opt.max_side,
                                                                tail_ratio=cfg.seam_tail_ratio)
            except Exception as exc:
                cache[path] = exc
        return cache[path]

    def run(label, fn, *args, **kw):
        """One check on one map: an unexpected exception becomes an M900, never a failed scan."""
        try:
            out.extend(fn(*args, **kw))
        except Exception as exc:
            out.append(_m900(m, label, exc, f"Check {getattr(fn, '__name__', fn)} failed on this map"))

    def seam(a, path, label):
        run(label, mc.check_seam, a, m.name, label, cfg.seam_z_max, seams.get(path), cfg.seam_tail_ratio)

    metal_mask = None
    for t in m.textures_for(SlotRole.METALNESS):
        if _readable(t.path):
            a = get(t.path)
            if not isinstance(a, Exception):
                metal_mask = a[..., 0]
                run(os.path.basename(t.path), mc.check_metal_bimodal, a, m.name, os.path.basename(t.path))

    upscale_on = "M013" not in cfg.experimental_off
    for t in m.textures:
        if not _readable(t.path):
            continue
        a = get(t.path)
        label = os.path.basename(t.path)
        if isinstance(a, Exception):
            out.append(_m900(m, label, a))
            continue
        if t.role == SlotRole.BASE_COLOR:
            # albedo range only means something on sRGB-encoded files
            if t.color_space != ColorSpace.LINEAR and not t.path.lower().endswith((".exr", ".hdr")):
                mm = metal_mask if metal_mask is not None and metal_mask.shape == a.shape[:2] else None
                run(label, mc.check_albedo, a, m.name, label, cfg.albedo_floor_error,
                    cfg.albedo_floor_strict, cfg.albedo_ceiling, mm)
                run(label, mc.check_baked_lighting, a, m.name, label)
            seam(a, t.path, label)
        elif t.role in (SlotRole.ROUGHNESS, SlotRole.GLOSSINESS):
            run(label, mc.check_constant, a, m.name, label, t.role.value)
            seam(a, t.path, label)
        elif t.role in (SlotRole.NORMAL, SlotRole.BUMP, SlotRole.DISPLACEMENT):
            seam(a, t.path, label)
        if upscale_on and t.role in _UPSCALE_ROLES:
            # resolution check needs native pixels, not the downsampled analysis copy
            try:
                crop = mc.load_crop(t.path)
            except Exception as exc:
                out.append(_m900(m, label, exc))
            else:
                run(label, mc.check_upscaled, crop, m.name, label)

    normals = [t for t in m.textures if t.role in (SlotRole.NORMAL, SlotRole.BUMP)
               and _readable(t.path) and t.via_normal_node is not False]
    heights = [t for t in m.textures if t.role == SlotRole.DISPLACEMENT and _readable(t.path)]
    if normals and heights:
        n, h = get(normals[0].path), get(heights[0].path)
        if not isinstance(n, Exception) and not isinstance(h, Exception) and n.shape[-1] >= 3:
            expected = opt.normal_convention.get(m.renderer.value)
            label = os.path.basename(normals[0].path)
            run(label, mc.check_normal_convention, n, h, m.name, label, expected,
                height_label=os.path.basename(heights[0].path))
    return out


def convention_unset_finding(materials: list[MaterialRecord], opt: InspectorOptions) -> Optional[Finding]:
    """M009: one scan-level info when M007 cannot run because ``normal_convention`` is unset
    for a renderer whose materials carry a normal map in this scan."""
    unset = sorted({m.renderer.value for m in materials
                    if any(t.role in (SlotRole.NORMAL, SlotRole.BUMP) and t.path for t in m.textures)
                    and not opt.normal_convention.get(m.renderer.value)})
    if not unset:
        return None
    return Finding("M009", Severity.INFO, "(scan)",
                   f"M007 inactive until normal_convention is set ({', '.join(unset)})",
                   "Normal maps are only reported (M008), never flagged as the wrong convention, until "
                   "the renderer's convention is set in inspector.json — see "
                   "docs/FIRST_WINDOWS_SESSION.md step 4.")


def ai_signature_finding(m: MaterialRecord, findings: Iterable[Finding]) -> Optional[Finding]:
    """R020: two or more independent image-generator signatures on one material."""
    ids = sorted({f.rule_id for f in findings if f.material == m.name} & set(AI_SIGNATURES))
    if len(ids) < 2:
        return None
    return Finding("R020", Severity.INFO, m.name, "Looks AI-generated: " + ", ".join(ids),
                   "Two or more generator signatures fired on this material's maps (flat maps, grey "
                   "metalness). Each alone is common; together they "
                   "usually mean the maps were generated from one image rather than measured.")


class ScanCancelled(Exception):
    """Raised by inspect() when the progress callback returns False."""


def inspect(materials: Iterable[MaterialRecord], opt: InspectorOptions | None = None,
            progress=None) -> list[Finding]:
    """``progress(i, total, name) -> bool`` is called before each material (1-based ``i``);
    returning False raises ScanCancelled."""
    opt = opt or InspectorOptions()
    materials = list(materials)
    out: list[Finding] = []
    for i, m in enumerate(materials):
        if progress is not None and progress(i + 1, len(materials), m.name) is False:
            raise ScanCancelled()
        mine = inspect_material(m, opt.config, opt.disabled_rules)
        if opt.check_pixels:
            mine += [f for f in pixel_findings(m, opt) if f.rule_id not in opt.disabled_rules]
        if "R020" not in opt.disabled_rules:
            agg = ai_signature_finding(m, mine)
            if agg is not None:
                mine.append(agg)
        for f in mine:
            f.material_index = i
        out += mine
    if opt.check_pixels and "M009" not in opt.disabled_rules:
        note = convention_unset_finding(materials, opt)
        if note is not None:
            out.append(note)
    order = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}
    return sorted(out, key=lambda f: (order[f.severity], f.material, f.rule_id))


def summary(findings: list[Finding]) -> dict:
    s = {"error": 0, "warning": 0, "info": 0, "fixable": 0, "materials_with_errors": 0}
    mats = set()
    for f in findings:
        s[f.severity.value] += 1
        s["fixable"] += int(f.fixable)
        if f.severity == Severity.ERROR:
            mats.add(f.material)
    s["materials_with_errors"] = len(mats)
    return s
