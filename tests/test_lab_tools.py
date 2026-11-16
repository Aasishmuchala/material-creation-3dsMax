"""Lab tool tests - lab.py's crash handling, resume and sheet, lab_scene's job
records, run_apartment's exit codes. Max is faked throughout: 3dsmaxbatch is a
scripted stand-in, pymxs a runtime that answers anything."""
import importlib.util
import io
import json
import os
import runpy
import sys
import time
import types

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, "tools")
LAB_SCENE = os.path.join(TOOLS, "realism_lab", "lab_scene.py")

pytest.importorskip("cv2")                       # render_post, which both drivers import
from PIL import Image  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lab = _load("lab_under_test", os.path.join(TOOLS, "realism_lab", "lab.py"))
apt = _load("run_apartment_under_test", os.path.join(TOOLS, "apartment", "run_apartment.py"))

CRASH = 4294967295                               # 3dsmaxbatch's exit code when Max dies
IDS = ["oak_floor", "walnut_herringbone", "marble_tile_floor", "polished_concrete",
       "terrazzo_floor", "cork_floor", "wool_rug"]


def _dump(path, doc):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# ------------------------------------------------------------ fake 3dsmaxbatch
class _Round:
    """What one Max launch leaves behind, written the way lab_scene writes it."""

    def __init__(self, env, ids, maxlog, n):
        self.out = env["MF_LAB_OUT"]
        self.fast = env.get("MF_LAB_FAST") == "1"
        size = env.get("MF_LAB_SIZE") or ("640x400" if self.fast else "1280x800")
        self.size = [int(v) for v in size.split("x")]
        self.ids, self.maxlog, self.lines = ids, maxlog, []
        self.console = "Specified option script: round %d\n" % n
        with open(maxlog, "w", encoding="utf-8") as fh:
            fh.write("2026/11/05 07:00:00 INF: [1] [2] Max started, round %d\n" % n)

    def log(self, line):
        self.lines.append(line)
        _dump(os.path.join(self.out, "_lab_log.json"), {"log": self.lines, "running": True})

    def record(self, mid, ok=True):
        if ok:
            Image.new("RGB", tuple(self.size)).save(os.path.join(self.out, mid + ".png"))
        rec = {"id": mid, "ok": ok, "fast": self.fast, "size": self.size}
        if not ok:
            rec["error"] = "Traceback: boom"
        _dump(os.path.join(self.out, mid + ".json"), rec)

    def job(self, mid, ok=True):
        self.log("job %s start" % mid)
        self.record(mid, ok)
        self.log("job %s ok=%s 1s" % (mid, ok))

    def finish(self, fatal=None):
        doc = {"jobs": [], "log": self.lines}
        if fatal:
            doc["fatal"] = fatal
        _dump(os.path.join(self.out, "_summary.json"), doc)
        return 0


class FakeMax:
    """3dsmaxbatch running lab_scene: one script per launch (the last one
    repeats); each gets a _Round and returns Max's exit code."""

    def __init__(self, *scripts):
        self.scripts, self.calls = scripts, []

    def __call__(self, cmd, env=None, capture_output=False, **kw):
        with open(env["MF_LAB_JOBS"], encoding="utf-8") as fh:
            ids = [j["id"] for j in json.load(fh)]
        n = len(self.calls)
        self.calls.append({"cmd": list(cmd), "env": dict(env), "ids": ids})
        r = _Round(env, ids, cmd[cmd.index("-log") + 1], n + 1)
        rc = self.scripts[min(n, len(self.scripts) - 1)](r)
        return types.SimpleNamespace(returncode=rc, stdout=r.console.encode("utf-16-le"),
                                     stderr=b"")


def renders_all(r):
    for mid in r.ids:
        r.job(mid)
    return r.finish()


def dies_on(victim):
    def script(r):
        for mid in r.ids:
            if mid == victim:
                r.log("job %s start" % mid)
                return CRASH
            r.job(mid)
        return r.finish()
    return script


def dies_on_first(r):
    r.log("job %s start" % r.ids[0])
    return CRASH


def dies_after_record_of(victim):
    def script(r):
        for mid in r.ids:
            r.log("job %s start" % mid)
            r.record(mid)
            if mid == victim:
                return CRASH                     # before "ok=": the job had finished
            r.log("job %s ok=True 1s" % mid)
        return r.finish()
    return script


def dies_before_first_job(r):
    r.console += "MAXScript exception: python.ExecuteFile failed\n"
    with open(r.maxlog, "a", encoding="utf-8") as fh:
        fh.write("2026/11/05 07:00:01 ERR: [1] [2] SyntaxError: invalid syntax (lab_scene.py)\n")
    return CRASH


def fails(victim):
    def script(r):
        for mid in r.ids:
            r.job(mid, ok=mid != victim)
        return r.finish()
    return script


def fatal_summary(r):
    return r.finish(fatal="Traceback (most recent call last):\nSyntaxError: invalid syntax")


@pytest.fixture
def labdir(tmp_path, monkeypatch):
    """lab.py on a temp out/; returns forge(*ids), which gives ids their maps."""
    monkeypatch.setattr(lab, "OUT", str(tmp_path / "out"))
    monkeypatch.setattr(lab.render_post, "process_dir", lambda d, **kw: 0)

    def forge(*ids):
        for mid in ids:
            d = tmp_path / "out" / "maps" / mid
            d.mkdir(parents=True)
            (d / "manifest.json").write_text("{}")
    os.makedirs(lab.OUT)
    return forge


def _max(monkeypatch, *scripts):
    fake = FakeMax(*scripts)
    monkeypatch.setattr(lab, "subprocess", types.SimpleNamespace(run=fake))
    return fake


def _rdir(tag):
    return os.path.join(lab.OUT, "renders_" + tag)


# ------------------------------------------------------------ lab.py render
def test_crash_is_pinned_on_the_job_the_trail_started(labdir, monkeypatch, capsys):
    ids = IDS[:5]
    labdir(*[i for i in ids if i != "walnut_herringbone"])           # not forged yet
    fake = _max(monkeypatch, dies_on("marble_tile_floor"))
    res = lab.render(ids, False, "t")
    out = capsys.readouterr().out
    # the unforged id never reaches Max, so it can never be blamed; the job
    # that keeps killing Max is dropped and the rest still render
    assert [c["ids"] for c in fake.calls] == [
        ["oak_floor", "marble_tile_floor", "polished_concrete", "terrazzo_floor"],
        ["marble_tile_floor", "polished_concrete", "terrazzo_floor"],
        ["polished_concrete", "terrazzo_floor"]]
    assert "Max died on marble_tile_floor (2 time(s))" in out
    assert "dropping marble_tile_floor" in out
    assert "no maps: walnut_herringbone" in out
    assert "giving up" not in out
    assert res == (["marble_tile_floor"], False)


def test_finished_job_without_ok_line_is_not_blamed(labdir, monkeypatch, capsys):
    ids = ["oak_floor", "cork_floor", "wool_rug"]
    labdir(*ids)
    fake = _max(monkeypatch, dies_after_record_of("oak_floor"), renders_all)
    res = lab.render(ids, False, "t")
    assert [c["ids"] for c in fake.calls] == [ids, ["cork_floor", "wool_rug"]]
    out = capsys.readouterr().out
    assert "between two jobs" in out and "died on" not in out
    assert res == ([], False)


@pytest.mark.parametrize("trail", [False, True])
def test_death_before_the_first_job_blames_no_job(labdir, monkeypatch, capsys, trail):
    ids = ["oak_floor", "cork_floor"]
    labdir(*ids)

    def script(r):
        if trail:                                # got as far as building the scene
            r.log("denoiser vray_mild")
        return dies_before_first_job(r)
    fake = _max(monkeypatch, script)
    res = lab.render(ids, False, "t")
    out = capsys.readouterr().out
    assert [c["ids"] for c in fake.calls] == [ids, ids]           # one retry, nothing dropped
    assert "died on" not in out and "dropping" not in out
    assert "Max died before its first job (2 time(s) in a row)" in out
    if trail:
        assert "log: denoiser vray_mild" in out
    else:                                        # Max's own words: console (UTF-16) and log
        assert "max: MAXScript exception: python.ExecuteFile failed" in out
        assert "SyntaxError: invalid syntax (lab_scene.py)" in out
    assert res == (ids, True)


def test_gives_up_after_retries(labdir, monkeypatch, capsys):
    ids = ["oak_floor", "cork_floor", "wool_rug", "polished_concrete"]
    labdir(*ids)
    fake = _max(monkeypatch, dies_on_first)
    res = lab.render(ids, False, "t")
    assert len(fake.calls) == 4
    assert "giving up after 4 crashes; not rendered: wool_rug, polished_concrete" in \
        capsys.readouterr().out
    assert res == (ids, True)


def test_each_dead_round_keeps_its_logs(labdir, monkeypatch, capsys):
    ids = ["oak_floor", "cork_floor"]
    labdir(*ids)
    _max(monkeypatch, dies_on("cork_floor"), renders_all)
    lab.render(ids, False, "t")
    rdir = _rdir("t")
    crash = {n.split("_r1", 1)[1]: os.path.join(rdir, n)
             for n in os.listdir(rdir) if n.startswith("_crash_")}
    assert sorted(crash) == ["_lab_batch.log", "_lab_console.txt", "_lab_log.json"]
    assert "round 1" in _read(crash["_lab_batch.log"])
    assert "round 1" in _read(crash["_lab_console.txt"])          # decoded from UTF-16
    assert json.loads(_read(crash["_lab_log.json"]))["log"][-1] == "job cork_floor start"
    assert "round 2" in _read(os.path.join(rdir, "_lab_batch.log"))
    assert "log: job cork_floor start" in capsys.readouterr().out


def test_summary_cut_short_is_not_fatal(labdir, monkeypatch):
    ids = ["oak_floor", "cork_floor"]
    labdir(*ids)

    def script(r):                               # every job done, then died writing the summary
        for mid in r.ids:
            r.job(mid)
        with open(os.path.join(r.out, "_summary.json"), "w", encoding="utf-8") as fh:
            fh.write('{"jobs": [{"id": "oak_fl')
        return CRASH
    fake = _max(monkeypatch, script)
    assert lab.render(ids, False, "t") == ([], False)
    assert len(fake.calls) == 1


def test_cut_trail_still_names_the_job(tmp_path):
    p = str(tmp_path / "_lab_log.json")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write('{\n "log": [\n  "denoiser vray_mild",\n  "job cork_floor start",\n  "calib')
    assert lab.lab_log(p) == ["denoiser vray_mild", "job cork_floor start"]
    assert lab.crashed_job(lab.lab_log(p), ["cork_floor"]) == "cork_floor"


def test_pass_files_stay_in_the_renders_folder(labdir, monkeypatch):
    labdir("oak_floor", "cork_floor")
    monkeypatch.setenv("MF_LAB_ONLY", "oak_floor")
    fake = _max(monkeypatch, renders_all)
    lab.render(["oak_floor", "cork_floor"], False, "p4full")
    lab.render(["cork_floor"], True, "check")
    for call, tag, size in zip(fake.calls, ("p4full", "check"), ("1280x800", "640x400")):
        rdir = _rdir(tag)
        assert "MF_LAB_ONLY" not in call["env"]
        assert call["env"]["MF_LAB_JOBS"] == os.path.join(rdir, "_jobs.json")
        assert call["env"]["MF_LAB_SIZE"] == size
        assert call["cmd"][1:] == ["-log", os.path.join(rdir, "_lab_batch.log"),
                                   os.path.join(rdir, "_lab_run.ms")]
    assert not any(os.path.exists(os.path.join(lab.OUT, n))
                   for n in ("jobs.json", "lab_run.ms", "lab_batch.log"))


@pytest.mark.parametrize("script, launches, code", [
    (renders_all, 1, None),
    (fails("oak_floor"), 1, 1),
    (fatal_summary, 1, 1),                       # no retry: the error is in the code
    (dies_on("oak_floor"), 3, 1),                # dropped
    (dies_before_first_job, 2, 1),               # gave up
])
def test_render_exit_code(labdir, monkeypatch, capsys, script, launches, code):
    labdir("oak_floor", "cork_floor")
    fake = _max(monkeypatch, script)
    monkeypatch.setattr(sys, "argv", ["lab.py", "render", "oak_floor", "cork_floor", "--tag", "t"])
    if code is None:
        lab.main()
    else:
        with pytest.raises(SystemExit) as e:
            lab.main()
        assert e.value.code == code
    assert len(fake.calls) == launches
    if script is fatal_summary:
        assert "FATAL:" in capsys.readouterr().out


def _rec(rdir, mid, png=None, **rec):
    if png:
        Image.new("RGB", png).save(os.path.join(rdir, mid + ".png"))
    _dump(os.path.join(rdir, mid + ".json"), dict({"id": mid}, **rec))


def test_resume_counts_only_ok_renders_at_this_size(labdir, monkeypatch, capsys):
    labdir(*IDS)
    rdir = _rdir("p4full")
    os.makedirs(rdir)
    full = {"fast": False, "size": [1280, 800]}
    _rec(rdir, "oak_floor", (1280, 800), ok=True, **full)                 # done
    _rec(rdir, "walnut_herringbone", None, ok=False, **full)              # failed
    _rec(rdir, "marble_tile_floor", (640, 400), ok=True, fast=True, size=[640, 400])
    _rec(rdir, "polished_concrete", (1280, 800), ok=True)                 # old record, full png
    _rec(rdir, "terrazzo_floor", (640, 400), ok=True)                     # old record, fast png
    _rec(rdir, "cork_floor", None, ok=True, **full)                       # png gone
    fake = _max(monkeypatch, renders_all)                                 # wool_rug: never ran
    lab.render(IDS, False, "p4full", resume=True)
    assert fake.calls[0]["ids"] == ["walnut_herringbone", "marble_tile_floor",
                                    "terrazzo_floor", "cork_floor", "wool_rug"]
    assert "resume: 2 done, 5 to render (1 failed before, 3 made at another size or " \
        "missing their png)" in capsys.readouterr().out


def test_fast_pass_does_not_satisfy_a_full_resume(labdir, monkeypatch, capsys):
    ids = ["oak_floor", "cork_floor"]
    labdir(*ids)
    fake = _max(monkeypatch, renders_all)
    lab.render(ids, True, "")                                             # render --fast
    lab.render(ids, False, "", resume=True)                               # render --resume
    assert [c["ids"] for c in fake.calls] == [ids, ids]
    assert lab.render(ids, False, "", resume=True) == ([], False)
    assert len(fake.calls) == 2
    assert "resume: 2 done, 0 to render" in capsys.readouterr().out


# ------------------------------------------------------------ lab.py sheet / jobs / main
def test_sheet_shows_only_this_tags_ok_renders(labdir, tmp_path, capsys):
    rdir = _rdir("p4full")
    os.makedirs(rdir)
    _rec(rdir, "oak_floor", (64, 40), ok=True)
    _rec(rdir, "cork_floor", (64, 40), ok=False)          # re-render failed: old png stays
    Image.new("RGB", (64, 40)).save(os.path.join(rdir, "wool_rug.png"))   # never reached
    out = str(tmp_path / "sheet.png")
    lab.sheet(["oak_floor", "cork_floor", "wool_rug"], out, "p4full", cols=1)
    assert Image.open(out).size == (1000, 520)            # one cell
    assert "left out 2 render(s) without an ok record in this tag: cork_floor, wool_rug" in \
        capsys.readouterr().out
    with pytest.raises(SystemExit):
        lab.sheet(["cork_floor", "wool_rug"], out, "p4full")


def test_jobs_cmd_writes_a_list_no_pass_reads_and_output_is_line_buffered(labdir, monkeypatch):
    labdir("oak_floor")
    stream = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(sys, "argv", ["lab.py", "jobs", "oak_floor"])
    lab.main()
    # line buffering: the path is in the byte stream already, not held back
    assert stream.line_buffering and b"jobs_manual.json" in stream.buffer.getvalue()
    with open(os.path.join(lab.OUT, "jobs_manual.json"), encoding="utf-8") as fh:
        assert [j["id"] for j in json.load(fh)] == ["oak_floor"]
    assert not os.path.exists(os.path.join(lab.OUT, "jobs.json"))


# ------------------------------------------------------------ lab_scene.py on a fake pymxs
class _Any:
    """Any pymxs value: attributes, calls and iteration all work, and what is
    set on it reads back."""

    def __init__(self, label="any"):
        self.__dict__["_label"] = label

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        v = self.__dict__[name] = _Any(name)
        return v

    def __call__(self, *a, **kw):
        return _Any(self._label)

    def __iter__(self):
        return iter(())

    def __float__(self):
        return 1.0

    def __int__(self):
        return 1

    def __str__(self):
        return self._label


FAKE_BUILDER = '''
LOG = []
CALLS = []


def _data_color_space():
    return None


def _remove_matforge_disp(node):
    pass


def build_material(maps, name, mclass, metal=None, tint=None, anti_tile=True, roughness_base=None):
    CALLS.append({"name": name, "anti_tile": anti_tile})
    LOG.append("building %r as %s" % (name, mclass))
    return object()


def assign_to_selection(mat, mclass, height_map=None):
    LOG.append("assigned")
'''


@pytest.fixture
def scene(tmp_path, monkeypatch):
    """Runs lab_scene.py on a fake pymxs and a fake maxplugin.builder; returns
    run(jobs, env, builder_src, renders) -> (out dir, builder module)."""
    saved = {k: sys.modules.pop(k, None) for k in ("maxplugin", "maxplugin.builder", "pymxs")}
    monkeypatch.setattr(sys, "path", list(sys.path))
    for k in ("MF_LAB_ONLY", "MF_LAB_DENOISE", "MF_LAB_SIZE", "MF_LAB_FAST"):
        monkeypatch.delenv(k, raising=False)

    def run(jobs, env=(), builder_src=FAKE_BUILDER, renders=True):
        root = tmp_path / "root"
        (root / "maxplugin").mkdir(parents=True)
        (root / "maxplugin" / "__init__.py").write_text("")
        (root / "maxplugin" / "builder.py").write_text(builder_src)
        (tmp_path / "jobs.json").write_text(json.dumps(jobs))
        rt = _Any("runtime")
        rt.RendererClass = types.SimpleNamespace(classes=[_Any("V_Ray_7")])

        def render(outputfile=None, **kw):
            if renders:
                with open(outputfile, "wb") as fh:
                    fh.write(b"png")
        rt.render = render
        pymxs = types.ModuleType("pymxs")
        pymxs.runtime = rt
        sys.modules["pymxs"] = pymxs
        monkeypatch.setenv("MATFORGE_ROOT", str(root))
        monkeypatch.setenv("MF_LAB_JOBS", str(tmp_path / "jobs.json"))
        monkeypatch.setenv("MF_LAB_OUT", str(tmp_path / "renders"))
        for k, v in dict(env).items():
            monkeypatch.setenv(k, v)
        runpy.run_path(LAB_SCENE, run_name="lab_scene_under_test")
        return str(tmp_path / "renders"), sys.modules.get("maxplugin.builder")
    yield run
    for k, v in saved.items():
        sys.modules.pop(k, None)
        if v is not None:
            sys.modules[k] = v


def _manifest(tmp_path, name, **extra):
    p = tmp_path / (name + "_manifest.json")
    p.write_text(json.dumps(dict({"maps": {}, "name": name, "class": "carpet"}, **extra)))
    return str(p)


def _job(mid, cam, manifest, **extra):
    return dict({"id": mid, "class": "carpet", "hero": ["rug"], "cam": cam, "tile_cm": 60,
                 "manifest": manifest}, **extra)


def test_lab_scene_records_size_and_honours_seamless(scene, tmp_path):
    jobs = [_job("wool_rug", "rug", _manifest(tmp_path, "rug", seamless=False)),
            _job("cork_floor", "floor", _manifest(tmp_path, "cork"), no_cal=True)]
    out, builder = scene(jobs, {"MF_LAB_FAST": "0", "MF_LAB_SIZE": "1280x800"})
    with open(os.path.join(out, "_summary.json"), encoding="utf-8") as fh:
        assert "fatal" not in json.load(fh)
    for mid in ("wool_rug", "cork_floor"):
        with open(os.path.join(out, mid + ".json"), encoding="utf-8") as fh:
            rec = json.load(fh)
        assert (rec["ok"], rec["fast"], rec["size"]) == (True, False, [1280, 800]), rec
    # maps forged with seamless off get no stochastic tiling; older manifests keep it
    assert builder.CALLS == [{"name": "rug", "anti_tile": False},
                             {"name": "cork", "anti_tile": True}]


def test_lab_scene_sizes_from_fast_when_lab_py_sets_no_size(scene, tmp_path):
    out, _ = scene([_job("wool_rug", "rug", _manifest(tmp_path, "rug"))], {"MF_LAB_FAST": "1"})
    with open(os.path.join(out, "wool_rug.json"), encoding="utf-8") as fh:
        rec = json.load(fh)
    assert (rec["ok"], rec["fast"], rec["size"]) == (True, True, [640, 400])


def test_lab_scene_old_png_is_not_a_render(scene, tmp_path):
    (tmp_path / "renders").mkdir()
    old = tmp_path / "renders" / "wool_rug.png"
    old.write_bytes(b"png")
    an_hour_ago = time.time() - 3600
    os.utime(old, (an_hour_ago, an_hour_ago))
    out, _ = scene([_job("wool_rug", "rug", _manifest(tmp_path, "rug"))], renders=False)
    with open(os.path.join(out, "wool_rug.json"), encoding="utf-8") as fh:
        rec = json.load(fh)
    assert rec["ok"] is False and "no new" in rec["error"]


def test_lab_scene_broken_builder_writes_a_fatal_summary(scene, tmp_path):
    out, _ = scene([_job("wool_rug", "rug", _manifest(tmp_path, "rug"))],
                   builder_src="def build_material(:\n")
    with open(os.path.join(out, "_summary.json"), encoding="utf-8") as fh:
        assert "SyntaxError" in json.load(fh)["fatal"]
    assert not os.path.exists(os.path.join(out, "wool_rug.json"))


# ------------------------------------------------------------ run_apartment.py
@pytest.fixture
def aptdir(tmp_path, monkeypatch):
    """run_apartment on a temp HERE; returns (renders dir, launch(rc, log text))."""
    monkeypatch.setattr(apt, "HERE", str(tmp_path))
    monkeypatch.setattr(apt.render_post, "process_dir", lambda d, **kw: 0)
    monkeypatch.setattr(sys, "argv", ["run_apartment.py", "--tag", "draft1"])
    out = tmp_path / "out" / "renders_draft1"

    def launch(rc, write=None):
        seen = {}

        def run(cmd, env=None, capture_output=False, **kw):
            seen["old_log"] = os.path.exists(os.path.join(env["MF_APT_OUT"], "_apartment_log.json"))
            if write is not None:
                (out / "_apartment_log.json").write_text(write)
            return types.SimpleNamespace(returncode=rc, stderr=b"",
                                         stdout="Script File Not Found".encode("utf-16-le"))
        monkeypatch.setattr(apt, "subprocess", types.SimpleNamespace(run=run))
        return seen
    return out, launch


def test_apartment_old_log_does_not_pass_for_this_run(aptdir, capsys):
    out, launch = aptdir
    out.mkdir(parents=True)
    (out / "_apartment_log.json").write_text(json.dumps(
        {"log": ["scene built in 15s", "render living 306s -> living.png"], "seconds": 700}))
    seen = launch(CRASH)
    with pytest.raises(SystemExit) as e:
        apt.main()
    assert e.value.code == 1 and seen["old_log"] is False
    text = capsys.readouterr().out
    assert "exit 4294967295" in text and "no log" in text
    assert "max: Script File Not Found" in text
    assert "render living" not in text


def test_apartment_cut_log_is_a_mid_run_death(aptdir, capsys):
    _, launch = aptdir
    launch(CRASH, write='{\n "log": [\n  "architecture built",\n  "render kitch')
    with pytest.raises(SystemExit) as e:
        apt.main()
    assert e.value.code == 1
    text = capsys.readouterr().out
    assert "cut short" in text and "  architecture built" in text


@pytest.mark.parametrize("rc, doc, code", [
    (0, {"log": ["scene built in 15s", "render living 306s -> living.png"], "seconds": 700}, None),
    (0, {"fatal": "Traceback (most recent call last): ...", "log": []}, 1),
    (CRASH, {"log": ["render living started"], "running": True}, 1),
    (0, {"log": ["render kitchen failed: Traceback ..."], "seconds": 9}, 1),
    (1, {"log": ["scene built in 15s"], "seconds": 9}, 1),
])
def test_apartment_exit_code(aptdir, capsys, rc, doc, code):
    _, launch = aptdir
    launch(rc, write=json.dumps(doc, indent=1))
    if code is None:
        apt.main()
    else:
        with pytest.raises(SystemExit) as e:
            apt.main()
        assert e.value.code == code
    assert "3dsmaxbatch exit %s" % rc in capsys.readouterr().out
