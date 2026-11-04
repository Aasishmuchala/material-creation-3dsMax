"""Orchestrates parameter rules + pixel checks for a list of materials."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Iterable, Optional

from .model import ColorSpace, Finding, MaterialRecord, Severity, SlotRole
from .rules import DEFAULT_CONFIG, RuleConfig, inspect_material
from . import map_checks as mc


@dataclass
class InspectorOptions:
    check_pixels: bool = True
    max_side: int = 1024
    #: Expected tangent-space convention per renderer: 'opengl' / 'directx' / None.
    #: None until verified in Phase 0 (see docs/VERIFY.md) — detection is still reported.
    normal_convention: dict = field(default_factory=lambda: {"vray": None, "corona": None})
    disabled_rules: tuple = ()
    config: RuleConfig = DEFAULT_CONFIG


def _readable(path: Optional[str]) -> bool:
    return bool(path) and os.path.isfile(path)  # type: ignore[arg-type]


def pixel_findings(m: MaterialRecord, opt: InspectorOptions) -> list[Finding]:
    out: list[Finding] = []
    cache: dict[str, object] = {}

    def get(path):
        if path not in cache:
            try:
                cache[path] = mc.load_map(path, opt.max_side)
            except Exception as exc:
                cache[path] = exc
        return cache[path]

    metal_mask = None
    for t in m.textures_for(SlotRole.METALNESS):
        if _readable(t.path):
            a = get(t.path)
            if not isinstance(a, Exception):
                metal_mask = a[..., 0]
                out += mc.check_metal_bimodal(a, m.name, os.path.basename(t.path))

    for t in m.textures:
        if not _readable(t.path):
            continue
        a = get(t.path)
        label = os.path.basename(t.path)
        if isinstance(a, Exception):
            out.append(Finding("M900", Severity.INFO, m.name, "Could not read image", repr(a), None, label))
            continue
        if t.role == SlotRole.BASE_COLOR:
            # albedo range only means something on sRGB-encoded files
            if t.color_space != ColorSpace.LINEAR and not t.path.lower().endswith((".exr", ".hdr")):
                mm = metal_mask if metal_mask is not None and metal_mask.shape == a.shape[:2] else None
                out += mc.check_albedo(a, m.name, label, opt.config.albedo_floor_error,
                                       opt.config.albedo_floor_strict, opt.config.albedo_ceiling, mm)
            out += mc.check_seam(a, m.name, label)
        elif t.role in (SlotRole.ROUGHNESS, SlotRole.GLOSSINESS):
            out += mc.check_constant(a, m.name, label, t.role.value)
            out += mc.check_seam(a, m.name, label)
        elif t.role in (SlotRole.NORMAL, SlotRole.BUMP, SlotRole.DISPLACEMENT):
            out += mc.check_seam(a, m.name, label)

    normals = [t for t in m.textures if t.role in (SlotRole.NORMAL, SlotRole.BUMP)
               and _readable(t.path) and t.via_normal_node is not False]
    heights = [t for t in m.textures if t.role == SlotRole.DISPLACEMENT and _readable(t.path)]
    if normals and heights:
        n, h = get(normals[0].path), get(heights[0].path)
        if not isinstance(n, Exception) and not isinstance(h, Exception) and n.shape[-1] >= 3:
            expected = opt.normal_convention.get(m.renderer.value)
            out += mc.check_normal_convention(n, h, m.name, os.path.basename(normals[0].path), expected)
    return out


def inspect(materials: Iterable[MaterialRecord], opt: InspectorOptions | None = None) -> list[Finding]:
    opt = opt or InspectorOptions()
    out: list[Finding] = []
    for m in materials:
        out += inspect_material(m, opt.config, opt.disabled_rules)
        if opt.check_pixels:
            out += [f for f in pixel_findings(m, opt) if f.rule_id not in opt.disabled_rules]
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
