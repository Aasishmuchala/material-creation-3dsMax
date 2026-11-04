"""Check PBR texture sets on disk, outside 3ds Max.

    python -m material_inspector.cli check-folder <folder> [--report out.html] [--json out.json]

Files are grouped into materials by their name stem (text before the map-type
token, e.g. ``Wood049_2K_Roughness.png`` -> ``Wood049_2K``) and assigned roles
from the map-type token. Colour space is assumed from the role (colour maps sRGB,
data maps linear), which is how a correct import would load them.

Exit codes: 0 clean, 1 errors found, 2 could not check (bad folder argument or no
texture sets found; the reason goes to stderr).
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict

from .core.inspector import InspectorOptions, inspect, summary
from .core.model import (COLOR_ROLES, ColorSpace, MaterialRecord, Renderer, SlotRole,
                         TextureRef)
from .core.report import to_html, to_json

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".tga", ".exr", ".bmp")

# order matters: longer / more specific tokens first
ROLE_TOKENS = [
    (SlotRole.NORMAL, ("normalgl", "normaldx", "normal", "nrm", "nor")),
    (SlotRole.ROUGHNESS, ("roughness", "rough")),
    (SlotRole.GLOSSINESS, ("glossiness", "gloss", "smoothness")),
    (SlotRole.METALNESS, ("metalness", "metallic", "metal")),
    (SlotRole.DISPLACEMENT, ("displacement", "height", "disp")),
    (SlotRole.OPACITY, ("opacity", "alpha", "mask")),
    (SlotRole.BASE_COLOR, ("basecolor", "base_color", "albedo", "diffuse", "color", "col", "diff")),
    (SlotRole.EMISSION, ("emission", "emissive")),
]
_SPLIT = re.compile(r"[_\-. ]+")


def classify(filename: str):
    stem = os.path.splitext(filename)[0]
    parts = _SPLIT.split(stem)
    for i in range(len(parts) - 1, -1, -1):
        p = parts[i].lower()
        for role, toks in ROLE_TOKENS:
            if p in toks:
                return "_".join(parts[:i]) or stem, role, p
    return None, None, None


def materials_from_folder(folder: str) -> list[MaterialRecord]:
    groups: dict[str, list[TextureRef]] = defaultdict(list)
    for root, _, files in os.walk(folder):
        for fn in sorted(files):
            if not fn.lower().endswith(IMAGE_EXT):
                continue
            name, role, token = classify(fn)
            if role is None:
                continue
            path = os.path.join(root, fn)
            cs = ColorSpace.SRGB if role in COLOR_ROLES else ColorSpace.LINEAR
            via = True if role == SlotRole.NORMAL else None
            groups[os.path.join(os.path.relpath(root, folder), name)].append(
                TextureRef(role, path, cs, "file", fn, via_normal_node=via, file_exists=True))
    return [MaterialRecord(name=k.lstrip("./"), renderer=Renderer.OTHER, material_class="texture set",
                           textures=v) for k, v in sorted(groups.items())]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="material-inspector")
    sub = ap.add_subparsers(dest="cmd", required=True)
    cf = sub.add_parser("check-folder", help="check PBR texture sets in a folder")
    cf.add_argument("folder")
    cf.add_argument("--report", help="write an HTML report")
    cf.add_argument("--json", help="write a JSON report")
    cf.add_argument("--normal-convention", choices=["opengl", "directx"], default=None,
                    help="flag normal maps that don't match this convention")
    cf.add_argument("--show-info", action="store_true")
    a = ap.parse_args(argv)

    # exit 2 = could not check (bad argument / nothing found); 1 = errors found; 0 = clean
    if not os.path.exists(a.folder):
        print(f"error: folder does not exist: {a.folder}", file=sys.stderr)
        return 2
    if not os.path.isdir(a.folder):
        print(f"error: not a folder: {a.folder}", file=sys.stderr)
        return 2
    if not os.access(a.folder, os.R_OK | os.X_OK):
        print(f"error: cannot read folder (permission denied): {a.folder}", file=sys.stderr)
        return 2
    mats = materials_from_folder(a.folder)
    if not mats:
        print("No texture sets found.", file=sys.stderr)
        return 2
    opt = InspectorOptions(normal_convention={"other": a.normal_convention})
    findings = inspect(mats, opt)
    shown = [f for f in findings if a.show_info or f.severity.value != "info"]
    for f in shown:
        tex = f" [{f.texture}]" if f.texture else ""
        print(f"{f.severity.value.upper():8} {f.rule_id}  {f.material}{tex}: {f.message}")
    s = summary(findings)
    print(f"\n{len(mats)} texture sets · {s['error']} errors · {s['warning']} warnings · {s['info']} info")
    if a.report:
        with open(a.report, "w", encoding="utf-8") as fh:
            fh.write(to_html(findings, os.path.abspath(a.folder)))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            fh.write(to_json(findings, os.path.abspath(a.folder)))
    return 1 if s["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
