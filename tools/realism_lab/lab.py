"""Realism lab driver (system Python).

  py -3.12 tools/realism_lab/lab.py forge  [ids...] [--res 2k]
  py -3.12 tools/realism_lab/lab.py render [ids...] [--fast] [--tag t] [--resume]
  py -3.12 tools/realism_lab/lab.py sheet  [ids...] [--tag t] [--out sheet.png]

References live in out/refs/<id>.png (made with Runway), maps in out/maps/<id>/,
renders in out/renders[_<tag>]/<id>.png. `render` runs lab_scene.py in
3dsmaxbatch. A pass keeps its job list, Max log and crash evidence (_crash_*)
in its own renders folder, so passes with other tags never share a file, and
it exits 1 when a job failed, was dropped or was never rendered.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "out")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import render_post  # noqa: E402
from lab_materials import MATERIALS  # noqa: E402

MAXBATCH = r"C:\Program Files\Autodesk\3ds Max 2026\3dsmaxbatch.exe"
# render size per --fast: handed to lab_scene (MF_LAB_SIZE), checked by --resume
SIZES = {False: (1280, 800), True: (640, 400)}
JOB_START = re.compile(r"job (\S+) start$")


def ids_or_all(ids):
    bad = [i for i in ids if i not in MATERIALS]
    if bad:
        raise SystemExit("unknown ids: %s" % ", ".join(bad))
    return ids or list(MATERIALS)


def forge(ids, res):
    for mid in ids_or_all(ids):
        cls = MATERIALS[mid][0]
        ref = os.path.join(OUT, "refs", mid + ".png")
        if not os.path.isfile(ref):
            print("skip %s: no reference" % mid)
            continue
        out = os.path.join(OUT, "maps", mid)
        # artwork hangs once in a frame: tiling would blend its edges together
        tile = ["--no-seamless"] if MATERIALS[mid][5].get("no_seamless") else []
        t0 = time.time()
        p = subprocess.run([sys.executable, os.path.join(ROOT, "forge_cli.py"), ref, "--name", mid,
                            "--type", cls, "--res", res, "--out", out] + tile,
                           capture_output=True, text=True)
        last = (p.stdout.strip().splitlines() or ["<no output>"])[-1]
        print("%-22s %-18s %5.1fs %s" % (mid, cls, time.time() - t0, last[:160]))


def jobs(ids, path=None):
    """Write the job list for the ids that have maps; returns (path, jobs).

    Without a path the list goes to out/jobs_manual.json, for a hand-run
    lab_scene: a render pass keeps its list in its renders folder, so this
    never swaps the jobs of a pass that is running.
    """
    out = []
    for mid in ids_or_all(ids):
        cls, hero, cam, tile, _, extra = MATERIALS[mid]
        mf = os.path.join(OUT, "maps", mid, "manifest.json")
        if not os.path.isfile(mf):
            print("skip %s: no maps" % mid)
            continue
        job = {"id": mid, "class": cls, "hero": hero, "cam": cam, "tile_cm": tile or 100,
               "manifest": mf}
        for k in ("metal", "maptype", "extra", "no_cal"):
            if k in extra:
                job[k] = extra[k]
        out.append(job)
    path = path or os.path.join(OUT, "jobs_manual.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    return path, out


def job_records(rdir, ids):
    """Per-job JSON records a pass has written so far, by id."""
    out = {}
    for mid in ids:
        p = os.path.join(rdir, mid + ".json")
        try:
            with open(p, encoding="utf-8") as fh:
                out[mid] = json.load(fh)
        except (OSError, ValueError):
            pass
    return out


def render_dir(tag):
    return os.path.join(OUT, "renders" + (("_" + tag) if tag else ""))


def resume_done(rdir, mid, rec, fast):
    """True when rec is an ok render at this pass's size and quality whose PNG
    is still there. Records from before lab_scene wrote fast and size are
    judged by the PNG's size, so a --fast pass never counts for a full one."""
    png = os.path.join(rdir, mid + ".png")
    if not (rec or {}).get("ok") or not os.path.isfile(png):
        return False
    if "size" in rec:
        return bool(rec.get("fast")) == bool(fast) and list(rec["size"]) == list(SIZES[fast])
    from PIL import Image
    try:
        with Image.open(png) as im:
            return tuple(im.size) == SIZES[fast]
    except OSError:
        return False


def _text(data):
    """Max's console output as text (3dsmaxbatch writes UTF-16)."""
    if not data:
        return ""
    if b"\x00" in data[:64]:
        return data.decode("utf-16-le", errors="replace").lstrip("\ufeff")
    return data.decode("utf-8", errors="replace")


def lab_log(path):
    """lab_scene's running trail (_lab_log.json), [] when there is none. A
    crash can cut the file mid-write; the whole lines still in it are kept."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
    except OSError:
        return []
    try:
        return [str(line) for line in json.loads(raw)["log"]]
    except (ValueError, KeyError, TypeError):
        return re.findall(r'^  "(.*)",?$', raw, re.M)   # json.dump(indent=1): one per line


def crashed_job(lines, left):
    """The job Max died in: the last job the trail started, if it is among
    `left` (no record). lab_scene writes the record before it logs "ok=", so a
    start without "ok=" can be a finished job. None when Max died before its
    first job or between two."""
    for line in reversed(lines):
        m = JOB_START.match(line)
        if m:
            return m.group(1) if m.group(1) in left else None
    return None


def max_errors(path, n=4):
    """The last error lines in Max's own log, where a script error lands."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return [ln.rstrip() for ln in fh
                    if " ERR: " in ln or "Error" in ln or "Traceback" in ln][-n:]
    except OSError:
        return []


def keep_evidence(rdir, rnd, paths):
    """Rename a dead round's files to _crash_<time>_r<round>_* so the next
    round cannot overwrite them; returns where they ended up."""
    stamp = time.strftime("%Y%m%d_%H%M%S")
    kept = []
    for p in paths:
        if not os.path.isfile(p):
            continue
        dst = os.path.join(rdir, "_crash_%s_r%d%s" % (stamp, rnd, os.path.basename(p)))
        try:
            os.replace(p, dst)
        except OSError:                          # still open in a Max going down
            try:
                shutil.copyfile(p, dst)
            except OSError:
                dst = p
        kept.append(dst)
    return kept


def render(ids, fast, tag, resume=False, retries=3, startup_retries=1):
    """Render jobs in one 3dsmaxbatch; when Max dies mid-pass, start again on
    the jobs it had not reached.

    The job Max died in is the last one lab_scene's trail started without a
    record: it is dropped after two deaths, and the pass gives up after more
    than `retries` such deaths. A Max that dies before its first job blames
    no job; it gets `startup_retries` more launches in a row. Each dead
    round's logs are kept as _crash_* files.

    Returns (ids not rendered ok, aborted); aborted when lab_scene hit a fatal
    error or the pass gave up.
    """
    rdir = render_dir(tag)
    os.makedirs(rdir, exist_ok=True)
    todo = ids_or_all(ids)
    if resume:
        recs = job_records(rdir, todo)
        done = {i for i in todo if resume_done(rdir, i, recs.get(i), fast)}
        failed = sum(1 for r in recs.values() if not r.get("ok"))
        todo = [i for i in todo if i not in done]
        print("resume: %d done, %d to render (%d failed before, %d made at another size "
              "or missing their png)" % (len(done), len(todo), failed,
                                         len(recs) - len(done) - failed))
        if not todo:
            return [], False
    # everything a pass hands Max lives in its own renders folder: passes
    # with other tags never load each other's job list or write one log
    ms = os.path.join(rdir, "_lab_run.ms")
    with open(ms, "w", encoding="utf-8") as fh:
        fh.write('python.ExecuteFile @"%s"\n' % os.path.join(HERE, "lab_scene.py"))
    jpath = os.path.join(rdir, "_jobs.json")
    maxlog = os.path.join(rdir, "_lab_batch.log")
    console = os.path.join(rdir, "_lab_console.txt")
    summ = os.path.join(rdir, "_summary.json")
    trail = os.path.join(rdir, "_lab_log.json")
    ran = skipped = None
    died_on, startup, rnd = {}, 0, 0
    fatal = gave_up = False
    while todo:
        rnd += 1
        _, js = jobs(todo, jpath)
        if ran is None:                          # ids without maps never reach Max
            ran = [j["id"] for j in js]
            skipped = [i for i in todo if i not in ran]
            if not ran:
                raise SystemExit("no jobs")
        todo = [j["id"] for j in js]
        if not todo:
            break
        for stale in (summ, trail):
            if os.path.isfile(stale):
                os.remove(stale)
        for mid in todo:                         # so a record means "done this run"
            if os.path.isfile(os.path.join(rdir, mid + ".json")):
                os.remove(os.path.join(rdir, mid + ".json"))
        env = dict(os.environ, MATFORGE_ROOT=ROOT, MF_LAB_JOBS=jpath, MF_LAB_OUT=rdir,
                   MF_LAB_FAST="1" if fast else "0", MF_LAB_SIZE="%dx%d" % SIZES[fast])
        env.pop("MF_LAB_ONLY", None)             # lab_scene would skip jobs this loop waits on
        t0 = time.time()
        p = subprocess.run([MAXBATCH, "-log", maxlog, ms], env=env, capture_output=True)
        print("3dsmaxbatch exit %s after %.0fs" % (p.returncode, time.time() - t0))
        said = (_text(p.stdout) + "\n" + _text(p.stderr)).strip()
        with open(console, "w", encoding="utf-8") as fh:
            fh.write(said)
        print("dithered %d 16-bit renders to 8 bits" % render_post.process_dir(rdir))
        recs = job_records(rdir, todo)
        for mid in todo:
            j = recs.get(mid)
            if not j:
                continue
            miss = [l for l in j.get("builder_log", []) if "MISS" in l]
            print("%-22s ok=%s %6ss  shutter 1/%s %s%s" % (
                mid, j.get("ok"), j.get("seconds"), j.get("shutter"),
                ("MISS " + "; ".join(miss)) if miss else "",
                ("\n   " + j["error"][-600:]) if j.get("error") else ""))
        try:
            with open(summ, encoding="utf-8") as fh:
                s = json.load(fh)
        except (OSError, ValueError):            # none, or cut short: Max died
            s = None
        if s is not None:
            if s.get("fatal"):
                fatal = True
                print("FATAL:", s["fatal"][-1500:])
            for line in s.get("log", [])[-12:]:
                print("  log:", line[:200])
            break
        left = [i for i in todo if i not in recs]
        if not left:
            break
        lines = lab_log(trail)
        victim = crashed_job(lines, left)
        errs = [] if lines else max_errors(maxlog)
        kept = keep_evidence(rdir, rnd, (maxlog, trail, console))
        print("Max died in round %d; its logs: %s" % (rnd, ", ".join(kept) or "none"))
        for line in lines[-6:]:
            print("  log:", line[:200])
        if not lines:                            # lab_scene said nothing: show what Max said
            for line in [l for l in said.splitlines() if l.strip()][-4:] + errs:
                print("  max:", line.strip()[:300])
        if victim:
            startup = 0
            died_on[victim] = died_on.get(victim, 0) + 1
            print("Max died on %s (%d time(s))" % (victim, died_on[victim]))
            if died_on[victim] >= 2:
                print("dropping %s from this pass" % victim)
                left.remove(victim)
            if sum(died_on.values()) > retries:
                gave_up = True
                print("giving up after %d crashes; not rendered: %s" % (
                    sum(died_on.values()), ", ".join(left)))
                break
        elif recs:
            startup = 0
            print("Max died between two jobs; no job to blame")
        else:
            startup += 1
            print("Max died before its first job (%d time(s) in a row); no job to blame"
                  % startup)
            if startup > startup_retries:
                gave_up = True
                print("giving up: Max never reached a job; not rendered: %s" % ", ".join(left))
                break
        todo = left
    recs = job_records(rdir, ran)
    failed = [i for i in ran if i in recs and not recs[i].get("ok")]
    missing = [i for i in ran if i not in recs]
    print("pass: %d of %d rendered ok%s%s%s" % (
        len(ran) - len(failed) - len(missing), len(ran),
        ("; failed: " + ", ".join(failed)) if failed else "",
        ("; not rendered: " + ", ".join(missing)) if missing else "",
        ("; no maps: " + ", ".join(skipped)) if skipped else ""))
    return failed + missing, fatal or gave_up


def sheet(ids, out_path, tag, cols=3):
    """Contact sheet of a tag's renders. Only ids whose record in that tag says
    ok: a re-render that failed or was never reached leaves the previous
    pass's PNG behind, and that must not pass for this pass's result."""
    from PIL import Image, ImageDraw
    rdir = render_dir(tag)
    want = ids_or_all(ids)
    recs = job_records(rdir, want)
    cells, left_out = [], []
    for mid in want:
        rp = os.path.join(rdir, mid + ".png")
        if not os.path.isfile(rp):
            continue
        if not recs.get(mid, {}).get("ok"):
            left_out.append(mid)
            continue
        ren = Image.open(rp).convert("RGB")
        ren.thumbnail((800, 500))
        cell = Image.new("RGB", (800 + 200, 520), (24, 24, 24))
        cell.paste(ren, (0, 0))
        ref = os.path.join(OUT, "refs", mid + ".png")
        if os.path.isfile(ref):
            r = Image.open(ref).convert("RGB")
            r.thumbnail((190, 190))
            cell.paste(r, (805, 5))
        d = ImageDraw.Draw(cell)
        d.text((805, 200), mid, fill=(230, 230, 230))
        d.text((805, 215), MATERIALS[mid][0], fill=(160, 160, 160))
        cells.append(cell)
    if left_out:
        print("left out %d render(s) without an ok record in this tag: %s" % (
            len(left_out), ", ".join(left_out)))
    if not cells:
        raise SystemExit("nothing rendered")
    rows = (len(cells) + cols - 1) // cols
    W, H = cells[0].size
    img = Image.new("RGB", (W * cols, H * rows), (10, 10, 10))
    for i, c in enumerate(cells):
        img.paste(c, ((i % cols) * W, (i // cols) * H))
    img.save(out_path)
    print("sheet ->", out_path, img.size)


def main():
    # progress has to reach a redirected log as it happens, not at exit
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["forge", "jobs", "render", "sheet"])
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--res", default="2k")
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--tag", default="", help="renders_<tag> folder (keeps passes apart)")
    ap.add_argument("--resume", action="store_true",
                    help="skip jobs this tag already rendered ok at this size")
    ap.add_argument("--out", default=os.path.join(OUT, "sheet.png"))
    a = ap.parse_args()
    if a.cmd == "forge":
        forge(a.ids, a.res)
    elif a.cmd == "jobs":
        print(jobs(a.ids)[0])
    elif a.cmd == "render":
        bad, aborted = render(a.ids, a.fast, a.tag, a.resume)
        if bad or aborted:
            raise SystemExit(1)
    else:
        sheet(a.ids, a.out, a.tag)


if __name__ == "__main__":
    main()
