"""Check the apartment furniture layout against the plan (system Python).

  py -3.12 tools/apartment/layout_check.py [--no-build]

Builds the doors and furniture in 3dsmaxbatch (MF_APT_PROBE, no materials or
renders), then reports per piece: the room it stands in, which way it faces,
wall penetration, the gap behind pieces that belong against a wall, overlaps
with other pieces and clashes with open door leaves. Exit code 1 on errors.
"""
import argparse
import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import plan as planmod  # noqa: E402

MAXBATCH = r"C:\Program Files\Autodesk\3ds Max 2026\3dsmaxbatch.exe"
PROBE = os.path.join(HERE, "out", "layout_probe.json")

# pieces whose back belongs against a wall (gap behind should be 0-3 cm)
AGAINST_WALL = {"build_kitchen_run", "build_fridge", "build_tv_console", "build_wardrobe",
                "build_bed", "build_vanity", "build_mirror", "build_toilet", "build_shower",
                "build_towel_rail", "build_nightstand"}
# (a, b): a may sit on, hang over or tuck into b
ALLOWED = {("build_tv", "build_tv_console"), ("build_decor_books", "build_coffee_table"),
           ("build_decor_vase", "build_coffee_table"), ("build_table_decor", "build_dining_table"),
           ("build_dining_chair", "build_dining_table"), ("build_table_lamp", "build_nightstand"),
           ("build_bath_decor", "build_vanity"), ("build_bath_decor", "build_toilet"),
           ("build_pendant_lamp", "build_dining_table"), ("build_table_lamp", "build_tv_console"),
           ("build_decor_books", "build_tv_console"),
           ("build_decor_vase", "build_tv_console")}                # anything may stand on a rug
TOL = 0.5          # cm


def run_probe():
    ms = os.path.join(HERE, "out", "layout_probe.ms")
    with open(ms, "w", encoding="utf-8") as fh:
        fh.write('python.ExecuteFile @"%s"\n' % os.path.join(HERE, "apartment_scene.py"))
    env = dict(os.environ, MF_APT_PROBE=PROBE, MF_APT_OUT=os.path.join(HERE, "out", "probe"))
    if os.path.isfile(PROBE):
        os.remove(PROBE)
    subprocess.run([MAXBATCH, "-log", ms + ".log", ms], env=env, capture_output=True)
    if not os.path.isfile(PROBE):
        raise SystemExit("probe failed; see %s.log and out/probe/_apartment_log.json" % ms)


def faces(pl, room):
    """Wall faces bounding a room, in Max cm: (side, coordinate, span lo, span hi).
    side W/E faces are x = const (span in y); N/S faces are y = const (span in x)."""
    r = pl.rooms[room]
    out = []
    for e in pl.edges:
        if room not in e.rooms:
            continue
        t = 0.0 if e.kind == "ext" else pl.int_t / 2.0
        if e.axis == "h":                       # plan y = c; Max y = -c
            north = abs(e.c - r.y) < 1e-6         # plan north edge of the room
            c = e.c + t if north else e.c - t
            out.append(("N" if north else "S", -c * 100, e.a * 100, e.b * 100))
        else:
            west = abs(e.c - r.x) < 1e-6
            c = e.c + t if west else e.c - t
            out.append(("W" if west else "E", c * 100, -e.b * 100, -e.a * 100))
    return out


def room_rect(pl, room):
    r = pl.rooms[room]
    return r.x * 100, r.x1 * 100, -r.y1 * 100, -r.y * 100


def compass(v):
    ang = math.degrees(math.atan2(v[1], v[0])) % 360     # Max: +Y = plan north
    names = ["E", "NE", "N", "NW", "W", "SW", "S", "SE"]
    return "%s (%.0f deg)" % (names[int((ang + 22.5) // 45) % 8], ang)


def overlap(a, b):
    d = [min(a["max"][k], b["max"][k]) - max(a["min"][k], b["min"][k]) for k in range(3)]
    return d if min(d) > TOL else None


def seg_box(p, q, lo, hi):
    """Does segment p->q (plan, cm) cross the XY box lo..hi? (Liang-Barsky)"""
    t0, t1 = 0.0, 1.0
    d = (q[0] - p[0], q[1] - p[1])
    for k in range(2):
        if abs(d[k]) < 1e-9:
            if p[k] < lo[k] or p[k] > hi[k]:
                return False
            continue
        ta, tb = (lo[k] - p[k]) / d[k], (hi[k] - p[k]) / d[k]
        t0, t1 = max(t0, min(ta, tb)), min(t1, max(ta, tb))
        if t0 > t1:
            return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-build", action="store_true", help="reuse out/layout_probe.json")
    a = ap.parse_args()
    if not a.no_build:
        run_probe()
    data = json.load(open(PROBE, encoding="utf-8"))
    for line in data.get("log", []):
        if "failed" in line:
            print("BUILD", line)
    pl = planmod.load(os.path.join(HERE, "plan_two_bed.txt"), 2.7)
    rects = {rid: room_rect(pl, rid) for rid in pl.rooms}
    items = data["items"]
    errors = 0
    for it in items:
        lo, hi = it["min"], it["max"]
        cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
        room = next((rid for rid, (x0, x1, y0, y1) in rects.items()
                     if x0 <= cx <= x1 and y0 <= cy <= y1), None)
        size = [hi[k] - lo[k] for k in range(3)]
        msg = []
        if room is None:
            msg.append("ERROR outside every room")
        else:
            # how far the box reaches past each wall face it spans
            gaps = {}
            for side, c, s0, s1 in faces(pl, room):
                span = (lo[1], hi[1]) if side in "WE" else (lo[0], hi[0])
                if min(span[1], s1) - max(span[0], s0) <= TOL:
                    continue                    # this wall segment is not beside the piece
                pen = {"W": c - lo[0], "E": hi[0] - c, "S": c - lo[1], "N": hi[1] - c}[side]
                if pen > TOL:
                    msg.append("ERROR into %s wall by %.1f cm" % (side, pen))
                gaps[side] = min(gaps.get(side, 1e9), -pen)
            if it["fn"] in AGAINST_WALL:
                f = it["front"]
                back = "E" if -f[0] > 0.7 else "W" if -f[0] < -0.7 else "N" if -f[1] > 0 else "S"
                gap = gaps.get(back)
                if gap is None or gap > 3.0:
                    msg.append("WARN back (%s) %s cm off the wall" % (
                        back, "?" if gap is None else "%.1f" % gap))
        if lo[2] > TOL and it["fn"] not in ("build_tv", "build_table_lamp", "build_decor_books",
                                            "build_decor_vase", "build_table_decor",
                                            "build_bath_decor", "build_mirror", "build_vanity",
                                            "build_pendant_lamp", "build_towel_rail"):
            msg.append("WARN floats %.1f cm above the floor" % lo[2])
        print("%2d %-20s %-8s faces %-14s size %5.0f x %5.0f x %5.0f  z %5.1f-%5.1f  %s" % (
            it["index"], it["fn"], room, compass(it["front"]), size[0], size[1], size[2],
            lo[2], hi[2], "; ".join(msg)))
        errors += sum(m.startswith("ERROR") for m in msg)
    print()
    for i, p in enumerate(items):
        for q in items[i + 1:]:
            d = overlap(p, q)
            if not d:
                continue
            pair = (p["fn"], q["fn"])
            ok = pair in ALLOWED or pair[::-1] in ALLOWED or "rug" in p["fn"] + q["fn"]
            tag = "ok  " if ok else "ERROR"
            if not ok:
                errors += 1
            print("%s overlap %d %s / %d %s: %.1f x %.1f x %.1f cm" % (
                tag, p["index"], p["fn"], q["index"], q["fn"], d[0], d[1], d[2]))
    for dr in data.get("doors", []):
        h = dr["hinge"]
        tip = (h[0] + dr["dir"][0] * dr["len"], h[1] + dr["dir"][1] * dr["len"])
        for it in items:
            if it["min"][2] > 205:
                continue
            lo = (it["min"][0] - 2, it["min"][1] - 2)
            hi = (it["max"][0] + 2, it["max"][1] + 2)
            if seg_box(h, tip, lo, hi):
                errors += 1
                print("ERROR door %s leaf hits %d %s" % ("/".join(dr["rooms"]), it["index"], it["fn"]))
        print("door %-12s hinge (%.0f, %.0f) leaf toward %s" % ("/".join(dr["rooms"]), h[0], h[1],
                                                            compass(dr["dir"])))
    print("\n%d error(s)" % errors)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
