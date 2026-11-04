"""MatForge CLI — reference image -> PBR map folder.

Runs on system Python (needs Pillow + numpy); the Max plugin shells out to
this so 3ds Max's bundled Python needs no extra packages.

Usage:
  py -3.12 forge_cli.py <image> --name Patio_Teak --type wood_exterior \
      --res 4k [--out DIR] [--no-seamless]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.maps import generate_maps
from core.recipes import RECIPES, RESOLUTIONS
from maxplugin.inputs import default_out_dir, image_problem


class JsonArgParser(argparse.ArgumentParser):
    """Argument errors still end with the one-JSON-line contract on stdout."""

    def error(self, message):
        self.print_usage(sys.stderr)
        print(json.dumps({"ok": False, "error": "bad arguments: %s" % message}))
        raise SystemExit(2)


def _stderr_progress(n, total, label):
    print("PROGRESS %d/%d %s" % (n, total, label), file=sys.stderr)
    sys.stderr.flush()


def main(argv=None):
    try:
        return _main(argv)
    except KeyboardInterrupt:
        print(json.dumps({"ok": False, "error": "cancelled"}))
        return 130


def _main(argv):
    ap = JsonArgParser(description="MatForge map generator")
    ap.add_argument("image", help="reference image path")
    ap.add_argument("--name", required=True, help="material name")
    ap.add_argument("--type", required=True, choices=sorted(RECIPES),
                    dest="mclass", help="material class")
    ap.add_argument("--res", default="4k", choices=sorted(RESOLUTIONS),
                    help="output resolution (default 4k)")
    ap.add_argument("--out", default=None,
                    help="output dir (default: <image dir>/<name>_maps)")
    ap.add_argument("--no-seamless", action="store_true",
                    help="skip edge cross-blend tiling")
    ap.add_argument("--progress", action="store_true",
                    help="print PROGRESS n/total label lines to stderr")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.image):
        ap.error(f"image not found: {args.image}")
    problem = image_problem(args.image)
    if problem:
        print(json.dumps({"ok": False, "error": problem}))
        return 1
    try:
        out_dir = args.out or default_out_dir(args.image, args.name)
    except ValueError as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1

    # Always end with a machine-readable line so the Max plugin can tell a
    # read-only path / corrupt image / decode failure apart from success,
    # instead of only seeing a bare non-zero exit + traceback.
    progress = _stderr_progress if args.progress else None
    try:
        warnings = []
        maps = generate_maps(args.image, out_dir, mclass=args.mclass,
                             resolution=args.res,
                             seamless=not args.no_seamless, warnings=warnings,
                             name=args.name, progress=progress)
        manifest = {"schema": 1, "name": args.name, "class": args.mclass,
                    "res": args.res, "maps": maps, "warnings": warnings}
        manifest_path = os.path.join(out_dir, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}))
        return 1
    print(json.dumps({"ok": True, "manifest": os.path.abspath(manifest_path),
                      "warnings": warnings}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
