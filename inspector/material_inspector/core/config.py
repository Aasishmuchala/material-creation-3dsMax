"""User-editable settings: thresholds, disabled rules, normal-map convention.

Looked up in order: $MATERIAL_INSPECTOR_CONFIG, %APPDATA%/MeasuredLight/inspector.json
(~/.config/measuredlight/inspector.json elsewhere). Missing file = defaults.
Unknown keys are reported, not silently ignored.
"""
from __future__ import annotations

import dataclasses
import json
import math
import os
from typing import Optional

from .inspector import InspectorOptions
from .rules import RuleConfig

EXAMPLE = {
    "disabled_rules": [],
    "check_pixels": True,
    "max_side": 1024,
    "normal_convention": {"vray": None, "corona": None, "openpbr": None},
    # Defaults flow from RuleConfig (i.e. matphys); no second copy of the numbers here.
    "rules": {"albedo_floor_error": RuleConfig.albedo_floor_error,
              "albedo_floor_strict": RuleConfig.albedo_floor_strict,
              "albedo_ceiling": RuleConfig.albedo_ceiling},
}


def default_path() -> str:
    env = os.environ.get("MATERIAL_INSPECTOR_CONFIG")
    if env:
        return env
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    folder = "MeasuredLight" if os.environ.get("APPDATA") else "measuredlight"
    return os.path.join(base, folder, "inspector.json")


_RENDERERS = ("vray", "corona", "openpbr", "other")


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _rule_value(name: str, v, default):
    """Validated override for one RuleConfig field, or raise ValueError with the reason.

    Types follow the field's default: numbers must be finite and non-negative, number
    tuples keep their length, string tuples must be lists of strings.
    """
    if isinstance(default, bool):
        if not isinstance(v, bool):
            raise ValueError("must be true or false")
        return v
    if isinstance(default, (int, float)):
        if not _number(v) or v < 0:
            raise ValueError("must be a finite, non-negative number")
        return float(v)
    if isinstance(default, tuple):
        if not isinstance(v, list):
            raise ValueError("must be a list")
        if all(isinstance(x, str) for x in default) and (default or name == "experimental_off"):
            if not all(isinstance(x, str) for x in v):
                raise ValueError("must be a list of strings")
            return tuple(v)
        if len(v) != len(default) or not all(_number(x) and x >= 0 for x in v):
            raise ValueError(f"must be a list of {len(default)} finite, non-negative numbers")
        return tuple(float(x) for x in v)
    raise ValueError("cannot be set from inspector.json")


def load_options(path: Optional[str] = None) -> tuple[InspectorOptions, list[str]]:
    """Return (options, warnings). Never raises on file content: every key is type-checked
    and falls back to its default with a warning."""
    from .inspector import known_rule_ids
    path = path or default_path()
    warnings: list[str] = []
    if not os.path.isfile(path):
        return InspectorOptions(), warnings
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        return InspectorOptions(), [f"Could not read {path}: {exc} — using defaults"]
    if not isinstance(data, dict):
        return InspectorOptions(), [f"{path} must hold a JSON object, not {type(data).__name__} — using defaults"]
    default = InspectorOptions()

    rule_fields = {f.name: f for f in dataclasses.fields(RuleConfig)}
    base = RuleConfig()
    overrides = {}
    rules = data.get("rules") or {}
    if not isinstance(rules, dict):
        warnings.append("'rules' must be an object — rule settings ignored"); rules = {}
    for k, v in rules.items():
        if k not in rule_fields:
            warnings.append(f"Unknown rule setting '{k}' ignored")
            continue
        try:
            overrides[k] = _rule_value(k, v, getattr(base, k))
        except ValueError as exc:
            warnings.append(f"rules.{k} {exc} — default {getattr(base, k)!r} kept")
    if "experimental_off" in overrides:
        unknown = [r for r in overrides["experimental_off"] if r not in known_rule_ids()]
        if unknown:
            warnings.append(f"rules.experimental_off: unknown rule ID(s) {', '.join(unknown)}")
    lo, st = (overrides.get(k, getattr(base, k)) for k in ("albedo_floor_error", "albedo_floor_strict"))
    if lo > st:
        warnings.append("rules.albedo_floor_error is above albedo_floor_strict — both defaults kept")
        overrides.pop("albedo_floor_error", None); overrides.pop("albedo_floor_strict", None)

    known = {"disabled_rules", "check_pixels", "max_side", "normal_convention", "rules"}
    warnings += [f"Unknown setting '{k}' ignored" for k in data if k not in known]

    nc_raw = data.get("normal_convention") or {}
    if not isinstance(nc_raw, dict):
        warnings.append("normal_convention must be an object like {\"vray\": \"opengl\"} — ignored")
        nc_raw = {}
    nc = {"vray": None, "corona": None, "openpbr": None}
    for r, v in nc_raw.items():
        if r not in _RENDERERS:
            warnings.append(f"normal_convention.{r}: unknown renderer ignored"); continue
        if v not in (None, "opengl", "directx"):
            warnings.append(f"normal_convention.{r} must be opengl, directx or null"); v = None
        nc[r] = v

    check_pixels = data.get("check_pixels", default.check_pixels)
    if not isinstance(check_pixels, bool):
        warnings.append("check_pixels must be true or false — default kept"); check_pixels = default.check_pixels

    max_side = data.get("max_side", default.max_side)
    if not (_number(max_side) and float(max_side).is_integer() and 16 <= max_side <= 65536):
        warnings.append(f"max_side must be a whole number of pixels, 16–65536 — default "
                        f"{default.max_side} kept"); max_side = default.max_side

    disabled = data.get("disabled_rules") or []
    if not isinstance(disabled, list) or not all(isinstance(x, str) for x in disabled):
        warnings.append('disabled_rules must be a list of rule IDs like ["R015"] — ignored'); disabled = []
    ids = known_rule_ids()
    unknown = [r for r in disabled if r not in ids]
    if unknown:
        warnings.append(f"disabled_rules: unknown rule ID(s) {', '.join(unknown)} ignored")
    disabled = [r for r in disabled if r in ids]

    opt = InspectorOptions(check_pixels=check_pixels, max_side=int(max_side), normal_convention=nc,
                           disabled_rules=tuple(disabled),
                           config=dataclasses.replace(RuleConfig(), **overrides))
    return opt, warnings


def write_example(path: Optional[str] = None) -> str:
    path = path or default_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(EXAMPLE, fh, indent=2)
    return path
