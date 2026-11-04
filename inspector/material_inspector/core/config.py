"""User-editable settings: thresholds, disabled rules, normal-map convention.

Looked up in order: $MATERIAL_INSPECTOR_CONFIG, %APPDATA%/MeasuredLight/inspector.json
(~/.config/measuredlight/inspector.json elsewhere). Missing file = defaults.
Unknown keys are reported, not silently ignored.
"""
from __future__ import annotations

import dataclasses
import json
import os
from typing import Optional

from .inspector import InspectorOptions
from .rules import RuleConfig

EXAMPLE = {
    "disabled_rules": [],
    "check_pixels": True,
    "max_side": 1024,
    "normal_convention": {"vray": None, "corona": None},
    "rules": {"albedo_floor_error": 30.0, "albedo_floor_strict": 50.0, "albedo_ceiling": 240.0},
}


def default_path() -> str:
    env = os.environ.get("MATERIAL_INSPECTOR_CONFIG")
    if env:
        return env
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    folder = "MeasuredLight" if os.environ.get("APPDATA") else "measuredlight"
    return os.path.join(base, folder, "inspector.json")


def load_options(path: Optional[str] = None) -> tuple[InspectorOptions, list[str]]:
    """Return (options, warnings)."""
    path = path or default_path()
    warnings: list[str] = []
    if not os.path.isfile(path):
        return InspectorOptions(), warnings
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        return InspectorOptions(), [f"Could not read {path}: {exc} — using defaults"]
    rule_fields = {f.name: f for f in dataclasses.fields(RuleConfig)}
    overrides = {}
    for k, v in (data.get("rules") or {}).items():
        if k not in rule_fields:
            warnings.append(f"Unknown rule setting '{k}' ignored")
            continue
        overrides[k] = tuple(v) if isinstance(v, list) else v
    known = {"disabled_rules", "check_pixels", "max_side", "normal_convention", "rules"}
    warnings += [f"Unknown setting '{k}' ignored" for k in data if k not in known]
    nc = {"vray": None, "corona": None, **(data.get("normal_convention") or {})}
    for r, v in nc.items():
        if v not in (None, "opengl", "directx"):
            warnings.append(f"normal_convention.{r} must be opengl, directx or null"); nc[r] = None
    opt = InspectorOptions(check_pixels=bool(data.get("check_pixels", True)),
                           max_side=int(data.get("max_side", 1024)),
                           normal_convention=nc,
                           disabled_rules=tuple(data.get("disabled_rules") or ()),
                           config=dataclasses.replace(RuleConfig(), **overrides))
    return opt, warnings


def write_example(path: Optional[str] = None) -> str:
    path = path or default_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(EXAMPLE, fh, indent=2)
    return path
