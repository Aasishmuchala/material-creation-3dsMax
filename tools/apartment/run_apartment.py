"""Build and render the MatForge test apartment through 3dsmaxbatch (system Python).

  py -3.12 tools/apartment/run_apartment.py [--cams living,kitchen] [--final | --preview] [--tag t] [--save]

Exits 1 when Max failed, died before or during the run (no fresh log, or a log
still marked running or cut short), hit a fatal error or failed a camera.
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
MAXBATCH = r"C:\Program Files\Autodesk\3ds Max 2026\3dsmaxbatch.exe"


def _text(data):
    """Max's console output as text (3dsmaxbatch writes UTF-16)."""
    if not data:
        return ""
    if b"\x00" in data[:64]:
        return data.decode("utf-16-le", errors="replace").lstrip("\ufeff")
    return data.decode("utf-8", errors="replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cams", default="")
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--preview", action="store_true", help="640 x 400, 1.5 min per view")
    ap.add_argument("--tag", default="draft")
    ap.add_argument("--save", action="store_true")
    a = ap.parse_args()
    out = os.path.join(HERE, "out", "renders_" + a.tag)
    os.makedirs(out, exist_ok=True)
    ms = os.path.join(HERE, "out", "run_apartment.ms")
    with open(ms, "w", encoding="utf-8") as fh:
        fh.write('python.ExecuteFile @"%s"\n' % os.path.join(HERE, "apartment_scene.py"))
    env = dict(os.environ, MF_APT_CAMS=a.cams, MF_APT_OUT=out,
               MF_APT_QUALITY="final" if a.final else "preview" if a.preview else "draft")
    if a.save:
        env["MF_APT_SAVE"] = os.path.join(HERE, "out", "matforge_apartment.max")
    # the previous run's log would pass for this one's when Max dies before
    # its first line
    logp = os.path.join(out, "_apartment_log.json")
    if os.path.isfile(logp):
        os.remove(logp)
    t0 = time.time()
    # below-normal priority: a render saturates every core, and whatever the
    # user is doing in the foreground keeps running smoothly
    p = subprocess.run([MAXBATCH, "-log", ms + ".log", ms], env=env, capture_output=True,
                       creationflags=getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0))
    print("3dsmaxbatch exit %s after %.0fs" % (p.returncode, time.time() - t0))
    # a photographic finish on the apartment renders (the lab's stay ungraded):
    # gentle S-curve, soft bloom round windows and sun patches, light vignette
    print("dithered %d 16-bit renders to 8 bits" % render_post.process_dir(out, curve=0.25, glow=0.08,
                                                                             vig=0.10))
    if not os.path.isfile(logp):
        print("no log: Max died before the scene's first line; see", ms + ".log")
        said = (_text(p.stdout) + "\n" + _text(p.stderr)).strip()
        try:                                     # a script error lands in Max's own log
            with open(ms + ".log", encoding="utf-8", errors="replace") as fh:
                errs = [ln for ln in fh if " ERR: " in ln or "Error" in ln or "Traceback" in ln]
        except OSError:
            errs = []
        for line in [l for l in said.splitlines() if l.strip()][-4:] + errs[-4:]:
            print("  max: " + line.strip()[:300])
        raise SystemExit(1)
    with open(logp, encoding="utf-8", errors="replace") as fh:
        raw = fh.read()
    try:
        d = json.loads(raw)
    except ValueError:
        # Max died while rewriting the log: keep the whole lines it holds
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
    failed = [l for l in d.get("log", []) if re.match(r"render \S+ failed", l)]
    if p.returncode or d.get("fatal") or d.get("running") or failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
