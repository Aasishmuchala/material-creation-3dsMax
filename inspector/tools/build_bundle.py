"""Assemble dist/MaterialInspector.bundle (Autodesk application package) from the source tree.

    python tools/build_bundle.py

Copy the resulting folder to %ProgramData%\\Autodesk\\ApplicationPlugins\\ — or point the
ADSK_APPLICATION_PLUGINS environment variable at dist/ — and restart 3ds Max.
"""
import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_BUNDLE = ROOT / "bundle" / "MaterialInspector.bundle"
DIST = ROOT / "dist" / "MaterialInspector.bundle"

if DIST.exists():
    shutil.rmtree(DIST)
shutil.copytree(SRC_BUNDLE, DIST)
shutil.copytree(ROOT / "material_inspector", DIST / "Contents" / "scripts" / "material_inspector",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
print(f"Built {DIST}")
