"""Render the close-up swatches through 3dsmaxbatch and build contact sheets.

  py -3.12 tools/realism_lab/swatch_run.py [ids ...] [--tag t] [--size 440] [--time 0.5]
"""
import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "apartment"))
sys.path.insert(0, os.path.dirname(HERE))
from run_apartment import MAXBATCH  # noqa: E402
import render_post  # noqa: E402


def sheets(out, cols=8, cell=220):
    from PIL import Image, ImageDraw
    fs = sorted(f for f in os.listdir(out) if f.endswith(".png") and not f.startswith("_"))
    paths = []
    for part in range(0, len(fs), cols * 5):
        chunk = fs[part:part + cols * 5]
        rows = -(-len(chunk) // cols)
        sheet = Image.new("RGB", (cols * cell, rows * (cell + 14)), (25, 25, 25))
        dr = ImageDraw.Draw(sheet)
        for i, f in enumerate(chunk):
            im = Image.open(os.path.join(out, f)).convert("RGB").resize((cell, cell), Image.LANCZOS)
            x, y = (i % cols) * cell, (i // cols) * (cell + 14)
            sheet.paste(im, (x, y + 14))
            dr.text((x + 3, y + 1), f[:-4][:32], fill=(235, 235, 235))
        p = os.path.join(out, "_sheet_%d.jpg" % (part // (cols * 5)))
        sheet.save(p, quality=88)
        paths.append(p)
    return paths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--tag", default="all")
    ap.add_argument("--size", default="440")
    ap.add_argument("--time", default="0.5")
    a = ap.parse_args()
    out = os.path.join(HERE, "out", "swatches_" + a.tag)
    os.makedirs(out, exist_ok=True)
    ms = os.path.join(HERE, "out", "swatch_run.ms")
    with open(ms, "w", encoding="utf-8") as fh:
        fh.write('python.ExecuteFile @"%s"\n' % os.path.join(HERE, "swatch_scene.py"))
    env = dict(os.environ, MF_SWATCH_OUT=out, MF_SWATCH_IDS=",".join(a.ids), MF_SWATCH_SIZE=a.size,
               MF_SWATCH_TIME=a.time, MF_APT_QUALITY="draft")
    t0 = time.time()
    p = subprocess.run([MAXBATCH, "-log", ms + ".log", ms], env=env, capture_output=True,
                       creationflags=getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0))
    print("3dsmaxbatch exit %s after %.0fs" % (p.returncode, time.time() - t0))
    print("dithered %d" % render_post.process_dir(out))
    for s in sheets(out):
        print(s)


if __name__ == "__main__":
    main()
