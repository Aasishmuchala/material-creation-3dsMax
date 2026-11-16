"""Build and render a MatForge benchmark scene through 3dsmaxbatch (system Python).

  py -3.12 tools/apartment/run_bench.py [--scene bench1] [--final | --preview] [--tag t] [--save] [--probe]

--probe builds the geometry only and writes the placed pieces' world boxes to
out/<scene>_probe.json (no materials, no renders). Exit status as
run_apartment.py: 1 when Max failed, died, hit a fatal error or failed a camera.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import render_post  # noqa: E402
from run_apartment import MAXBATCH, _text  # noqa: E402

# The benchmarks' finish (render_post.to8). Graded like the apartment (S-curve
# 0.25), bench1 read flat against its reference: luminance percentiles 5/50/95
# 0.14/0.39/0.53 there, 0.01/0.47/0.90 in the target. The S-curve pivots at
# 0.5, under most of a high-key frame; the toe pivots at the metered wall
# (0.48 linear, 0.72 on screen) and deepens only what lies below it. A
# stronger narrow bloom, a wide halation round the blown windows and the
# apartment's light vignette.
GRADE = dict(toe=1.3, toe_pivot=0.72, glow=0.12, halo=0.04, vig=0.10)
# the toe pivots at each scene's metered wall in display values (1.055 x
# PATCH_EXPOSURE ** (1 / 2.4) - 0.055): bench1 0.48, bench2 0.22, bench3 0.45
TOE_PIVOT = {"bench1": 0.72, "bench2": 0.51, "bench3": 0.70}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", default="bench1")
    ap.add_argument("--cams", default="")
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--preview", action="store_true", help="400 x 480")
    ap.add_argument("--tag", default="draft")
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--probe", action="store_true")
    a = ap.parse_args()
    out = os.path.join(HERE, "out", "%s_%s" % (a.scene, a.tag))
    os.makedirs(out, exist_ok=True)
    ms = os.path.join(HERE, "out", "run_%s.ms" % a.scene)
    with open(ms, "w", encoding="utf-8") as fh:
        fh.write('python.ExecuteFile @"%s"\n' % os.path.join(HERE, "%s_scene.py" % a.scene))
    env = dict(os.environ, MF_APT_CAMS=a.cams, MF_APT_OUT=out,
               MF_APT_QUALITY="final" if a.final else "preview" if a.preview else "draft")
    probe = os.path.join(HERE, "out", "%s_probe.json" % a.scene)
    if a.probe:
        env["MF_BENCH_PROBE"] = probe
        if os.path.isfile(probe):
            os.remove(probe)
    if a.save:
        env["MF_APT_SAVE"] = os.path.join(HERE, "out", "matforge_%s.max" % a.scene)
    logp = os.path.join(out, "_apartment_log.json")
    if os.path.isfile(logp):
        os.remove(logp)
    t0 = time.time()
    p = subprocess.run([MAXBATCH, "-log", ms + ".log", ms], env=env, capture_output=True,
                       creationflags=getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0))
    print("3dsmaxbatch exit %s after %.0fs" % (p.returncode, time.time() - t0))
    if a.probe:
        if not os.path.isfile(probe):
            print("no probe written; see", ms + ".log", "and", logp)
            _max_errors(p, ms)
            raise SystemExit(1)
        with open(probe, encoding="utf-8") as fh:
            d = json.load(fh)
        for it in d["items"]:
            print("  %-14s %3d nodes  min %s  max %s" % (it["label"], it["nodes"], it["min"], it["max"]))
        for line in d.get("log", []):
            print("  " + line[:300])
        if _failed(d):
            raise SystemExit(1)
        return
    grade = dict(GRADE, toe_pivot=TOE_PIVOT.get(a.scene, GRADE["toe_pivot"]))
    print("dithered %d 16-bit renders to 8 bits" % render_post.process_dir(out, **grade))
    if not os.path.isfile(logp):
        print("no log: Max died before the scene's first line; see", ms + ".log")
        _max_errors(p, ms)
        raise SystemExit(1)
    with open(logp, encoding="utf-8", errors="replace") as fh:
        raw = fh.read()
    try:
        d = json.loads(raw)
    except ValueError:
        print("Max died mid-run (the log is cut short); the log stops at:")
        for line in re.findall(r'^  "(.*)",?$', raw, re.M)[-12:]:
            print("  " + line[:300])
        raise SystemExit(1)
    if d.get("fatal"):
        print("FATAL:", d["fatal"][-2000:])
    if d.get("running"):
        print("Max died mid-run (out of memory?); the log stops at:")
    for line in d.get("log", []):
        print("  " + line[:300])
    if p.returncode or d.get("fatal") or d.get("running") or _failed(d):
        raise SystemExit(1)


def _failed(d):
    """Log lines of a failed render or a piece that did not build (put()
    logs it and carries on, which left a benchmark without its chair
    exiting 0)."""
    return [l for l in d.get("log", []) if re.match(r"(render|piece) \S+ failed", l)]


def _max_errors(p, ms):
    """The tail of Max's console and the errors in its own log: an import or
    syntax error in the scene module lands there before any scene log."""
    said = (_text(p.stdout) + "\n" + _text(p.stderr)).strip()
    try:
        with open(ms + ".log", encoding="utf-8", errors="replace") as fh:
            errs = [ln for ln in fh if " ERR: " in ln or "Error" in ln or "Traceback" in ln]
    except OSError:
        errs = []
    for line in [l for l in said.splitlines() if l.strip()][-4:] + errs[-6:]:
        print("  max: " + line.strip()[:300])


if __name__ == "__main__":
    main()
