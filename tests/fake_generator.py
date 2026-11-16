"""Test double for forge_cli.py AND forge_fal.py (stdlib only, Python 3.7+).

Accepts: IMG --name N --type C [--res R] [--upscale U] [--no-seamless]
         [--progress]
Mode via env MATFORGE_FAKE_MODE: ok (default) | fail | hang | badjson.
MATFORGE_FAKE_DELAY (seconds, default 0) sleeps after each PROGRESS line.
"""
import argparse
import json
import os
import struct
import sys
import time
import zlib

MAPS = ("albedo", "roughness", "normal", "height", "metalness")


def _chunk(tag, data):
    body = tag + data
    return (struct.pack(">I", len(data)) + body
            + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))


def write_png(path, size=8, grey=128):
    row = b"\x00" + bytes([grey]) * size
    raw = row * size
    png = (b"\x89PNG\r\n\x1a\n"
           + _chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 0, 0, 0, 0))
           + _chunk(b"IDAT", zlib.compress(raw))
           + _chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)


def _progress(on, n, label, delay):
    if on:
        sys.stderr.write("PROGRESS %d/3 %s\n" % (n, label))
        sys.stderr.flush()
    if delay:
        time.sleep(delay)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--name", required=True)
    ap.add_argument("--type", required=True, dest="mclass")
    ap.add_argument("--res", default="4k")
    ap.add_argument("--upscale", default=None)
    ap.add_argument("--no-seamless", action="store_true")
    ap.add_argument("--progress", action="store_true")
    a, _extra = ap.parse_known_args(argv)

    mode = os.environ.get("MATFORGE_FAKE_MODE", "ok")
    delay = float(os.environ.get("MATFORGE_FAKE_DELAY", "0") or 0)

    if mode == "fail":
        print(json.dumps({"ok": False,
                          "error": "Fake failure: image unreadable"}))
        return 1
    if mode == "badjson":
        print("garbage")
        return 0
    if mode == "hang":
        _progress(a.progress, 1, "Reading the photo", 0)
        time.sleep(120)
        return 0

    _progress(a.progress, 1, "Reading the photo", delay)
    _progress(a.progress, 2, "Making the maps", delay)
    _progress(a.progress, 3, "Saving the maps", delay)
    out_dir = os.path.join(os.path.dirname(os.path.abspath(a.image)),
                           a.name + "_maps")
    os.makedirs(out_dir, exist_ok=True)
    maps = {}
    for i, key in enumerate(MAPS):
        p = os.path.join(out_dir, key + ".png")
        write_png(p, grey=40 + 40 * i)
        maps[key] = os.path.abspath(p)
    warnings = ["fake warning"]
    manifest = {"schema": 1, "name": a.name, "class": a.mclass, "res": a.res,
                "maps": maps, "warnings": warnings}
    mp = os.path.join(out_dir, "manifest.json")
    with open(mp, "w") as f:
        json.dump(manifest, f, indent=2)
    print(json.dumps({"ok": True, "manifest": os.path.abspath(mp),
                      "warnings": warnings}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
