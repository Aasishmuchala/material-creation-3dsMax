"""Assemble dist/MaterialInspector.bundle (Autodesk application package) from the source tree.

    python tools/build_bundle.py [--out DIR]

Copy the resulting folder to %ProgramData%\\Autodesk\\ApplicationPlugins\\ — or point the
ADSK_APPLICATION_PLUGINS environment variable at dist/ — and restart 3ds Max.

Never ships secrets (_keys.json, _falkey.py, _omegakey.py), tests, logs or the dev-only
material_inspector/devtools/ package; the build fails if any of those slip in.
"""
import argparse
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_BUNDLE = ROOT / "bundle" / "MaterialInspector.bundle"
BUNDLE_NAME = "MaterialInspector.bundle"

SECRET_NAMES = {"_keys.json", "_falkey.py", "_omegakey.py"}
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "*.log", "tests", "devtools",
                                *sorted(SECRET_NAMES))
FORBIDDEN_DIRS = {"tests", "devtools", "research_notes", "reports", ".router", "dist",
                  "__pycache__"}


def check(bundle):
    """Raise if a secret, test, log or excluded folder ended up in the bundle."""
    bad = []
    for p in bundle.rglob("*"):
        rel = p.relative_to(bundle)
        if (p.name in SECRET_NAMES or p.suffix == ".log"
                or FORBIDDEN_DIRS.intersection(rel.parts)):
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
    shutil.copytree(str(ROOT / "material_inspector"), str(scripts / "material_inspector"),
                    ignore=IGNORE)
    # shared physics tables (repo-root matphys/), imported by material_inspector.core.physics
    shutil.copytree(str(ROOT.parent / "matphys"), str(scripts / "matphys"), ignore=IGNORE)
    # shared Qt UI kit (repo-root forgeui/), imported by max_adapter.ui
    shutil.copytree(str(ROOT.parent / "forgeui"), str(scripts / "forgeui"), ignore=IGNORE)
    check(dist)
    return dist


def _say(text):
    """Print even on a console whose code page cannot show every character
    (a Windows cp1252 console and a destination path with a non-Latin name)."""
    try:
        print(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(text.encode(enc, "replace").decode(enc))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", help="output folder (default: <inspector>/dist)")
    a = ap.parse_args(argv)
    dist = build(a.out)
    _say("Built %s" % dist)
    return 0


if __name__ == "__main__":
    sys.exit(main())
