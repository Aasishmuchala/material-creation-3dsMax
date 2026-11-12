"""Render a furniture module preview through 3dsmaxbatch (system Python).

  py -3.12 tools/apartment/run_preview.py furn_living [front|three_quarter|top]

Writes tools/apartment/out/preview_<module>_<view>.png (+ .json, or
.error.txt with the Python traceback if the module failed inside Max).
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
MAXBATCH = r"C:\Program Files\Autodesk\3ds Max 2026\3dsmaxbatch.exe"


def main():
    mod = sys.argv[1]
    view = sys.argv[2] if len(sys.argv) > 2 else "three_quarter"
    out_dir = os.path.join(HERE, "out")
    os.makedirs(out_dir, exist_ok=True)
    png = os.path.join(out_dir, "preview_%s_%s.png" % (mod, view))
    for suffix in ("", ".json", ".error.txt"):
        if os.path.exists(png + suffix):
            os.remove(png + suffix)
    ms = os.path.join(out_dir, "preview_%s.ms" % mod)
    with open(ms, "w", encoding="utf-8") as fh:
        fh.write('python.ExecuteFile @"%s"\n' % os.path.join(HERE, "preview.py"))
    env = dict(os.environ, MF_PREVIEW_MODULE=mod, MF_PREVIEW_OUT=png, MF_PREVIEW_VIEW=view)
    t0 = time.time()
    subprocess.run([MAXBATCH, "-log", ms + ".log", ms], env=env, capture_output=True)
    if os.path.exists(png + ".error.txt"):
        print("ERROR inside Max:\n" + open(png + ".error.txt").read())
        return 1
    if not os.path.exists(png):
        print("no image produced; see", ms + ".log")
        return 1
    print("preview ->", png, "(%.0fs)" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
