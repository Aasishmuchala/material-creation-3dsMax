"""Assemble dist/MatForge.bundle (Autodesk application package) from the source tree.

    python tools/build_matforge_bundle.py [--out DIR]

Copy the resulting MatForge.bundle folder to %ProgramData%\\Autodesk\\ApplicationPlugins\\
(or point the ADSK_APPLICATION_PLUGINS environment variable at dist/) and restart 3ds Max.
The startup script registers the MatForge actions (Customize > Toolbars, category "MatForge")
against the bundle's own Contents/scripts folder.

Never ships secrets (_keys.json, _falkey.py, _omegakey.py), tests, research notes, reports or
generated maps; the build fails if any of those slip in.
"""
import argparse
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_BUNDLE = ROOT / "packaging" / "MatForge.bundle"
BUNDLE_NAME = "MatForge.bundle"

# runtime python packages and files that the Max-side plugin and its system-Python
# map generators import (forge_cli.py / forge_fal.py are shelled out to)
PACKAGES = ["core", "maxplugin", "matphys", "ui"]
FILES = [
    "forge_cli.py",
    "forge_fal.py",
    "mfconfig.py",
    "run_matforge.py",
    "requirements.txt",
    "install_matforge.ms",
    "matforge_macros.ms",
    "matforge_panel.ms",
    "matforge_diagnose.ms",
]

SECRET_NAMES = {"_keys.json", "_falkey.py", "_omegakey.py"}
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "*.log", "*_maps", "tests",
                                *sorted(SECRET_NAMES))
FORBIDDEN_DIRS = {"tests", "research_notes", "reports", ".router", "dist", "__pycache__"}


def check(bundle):
    """Raise if a secret, test or excluded folder ended up in the bundle."""
    bad = []
    for p in bundle.rglob("*"):
        rel = p.relative_to(bundle)
        if p.name in SECRET_NAMES or FORBIDDEN_DIRS.intersection(rel.parts):
            bad.append(str(rel))
    if bad:
        raise SystemExit("refusing to ship: " + ", ".join(sorted(bad)))


def build(out_dir=None):
    out_dir = pathlib.Path(out_dir) if out_dir else ROOT / "dist"
    dist = out_dir / BUNDLE_NAME
    if dist.exists():
        shutil.rmtree(str(dist))
    shutil.copytree(str(SRC_BUNDLE), str(dist), ignore=IGNORE)
    scripts = dist / "Contents" / "scripts"
    for pkg in PACKAGES:
        shutil.copytree(str(ROOT / pkg), str(scripts / pkg), ignore=IGNORE)
    for name in FILES:
        shutil.copy2(str(ROOT / name), str(scripts / name))
    check(dist)
    return dist


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", help="output folder (default: <repo>/dist)")
    a = ap.parse_args(argv)
    dist = build(a.out)
    print("Built %s" % dist)
    return 0


if __name__ == "__main__":
    sys.exit(main())
