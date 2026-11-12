"""Download Runway reference images listed in out/tasks.txt from a saved list_recent JSON."""
import json
import os
import sys
import urllib.request

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")


def main(listing):
    with open(listing, encoding="utf-8") as fh:
        data = json.load(fh)
    urls = {}
    for a in data.get("assets", []):
        tid = a.get("taskId") or a.get("task_id")
        url = a.get("url") or a.get("assetUrl")
        if tid and url:
            urls[tid] = url
    os.makedirs(os.path.join(OUT, "refs"), exist_ok=True)
    pending = []
    for line in open(os.path.join(OUT, "tasks.txt"), encoding="utf-8"):
        if not line.strip():
            continue
        mid, tid = line.split()
        dst = os.path.join(OUT, "refs", mid + ".png")
        if os.path.isfile(dst):
            continue
        if tid not in urls:
            pending.append(mid)
            continue
        req = urllib.request.Request(urls[tid], headers={"User-Agent": "MatForgeLab/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r, open(dst, "wb") as f:
            f.write(r.read())
        print("got", mid, os.path.getsize(dst))
    print("pending:", " ".join(pending) or "none")


if __name__ == "__main__":
    main(sys.argv[1])
