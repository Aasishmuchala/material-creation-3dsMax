"""forge_max backend split: build_command, parse_generator_output,
finish_build, assign/slate/renderer helpers and the show() fallback.
No Qt, no 3ds Max: mock pymxs only."""
import importlib
import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.dirname(os.path.abspath(__file__))
for _p in (REPO, TESTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import mock_pymxs  # noqa: E402
from test_builder_logic import _write_maps  # noqa: E402

NO_KEY = "Best needs a fal key. Add it in Settings, or use Standard."


def _load(**install_kw):
    builder, rt = mock_pymxs.install(**install_kw)
    import maxplugin.forge_max as fm
    importlib.reload(fm)
    fm._PYBIN = ["python3"]
    return fm, builder, rt


@pytest.fixture
def fm(monkeypatch):
    mod, _b, _rt = _load()
    monkeypatch.setattr(mod, "_fal_key", lambda: "fal_fake")
    return mod


@pytest.fixture
def img(tmp_path):
    from PIL import Image
    p = tmp_path / "ref.png"
    Image.new("RGB", (8, 8), (120, 120, 120)).save(str(p), "PNG")
    return str(p)


def _cmd(fm, image, **kw):
    a = dict(img=image, name="Oak", mclass="wood_interior", res="4k",
             engine="fast", seamless=True, renderer="auto", metal=None)
    a.update(kw)
    return fm.build_command(**a)


# ---------- build_command ----------

def test_fast_argv_exact(fm, img):
    c = _cmd(fm, img)
    assert c["ok"] and c["error"] is None
    assert c["argv"] == fm._PYBIN + [fm.CLI, img, "--name", "Oak", "--type",
                                     "wood_interior", "--res", "4k"]
    assert c["name"] == "Oak" and c["res"] == "4k" and c["engine"] == "fast"
    assert c["extra_note"] is None
    assert "FAL_KEY" not in c["env"] or c["env"]["FAL_KEY"] != "fal_fake"


def test_no_seamless_flag(fm, img):
    c = _cmd(fm, img, seamless=False)
    assert c["argv"][-1] == "--no-seamless"


def test_progress_flag_last(fm, img):
    assert _cmd(fm, img, progress=True)["argv"][-1] == fm.PROGRESS_FLAG == "--progress"
    c = _cmd(fm, img, seamless=False, progress=True)
    assert c["argv"][-2:] == ["--no-seamless", "--progress"]
    assert "--progress" not in _cmd(fm, img)["argv"]


@pytest.mark.parametrize("res,up,note", [("2k", "2", False), ("4k", "4", False),
                                         ("8k", "4", True)])
def test_ultra_argv_and_note(fm, img, res, up, note):
    c = _cmd(fm, img, engine="ultra", res=res)
    assert c["ok"]
    assert c["argv"] == fm._PYBIN + [fm.FAL, img, "--name", "Oak", "--type",
                                     "wood_interior", "--upscale", up]
    assert c["env"]["FAL_KEY"] == "fal_fake"
    assert "fal_fake" not in " ".join(c["argv"])
    assert bool(c["extra_note"]) is note


def test_ultra_without_key(fm, img, monkeypatch):
    monkeypatch.setattr(fm, "_fal_key", lambda: None)
    c = _cmd(fm, img, engine="ultra")
    assert c["ok"] is False and c["error"] == NO_KEY and c["argv"] == []


def test_build_command_normalises_and_rejects(fm, img):
    c = _cmd(fm, img, renderer=" Both ", engine="FAST", res="4K")
    assert c["ok"] and (c["renderer"], c["engine"], c["res"]) == (
        "both", "fast", "4k")
    for kw in ({"mclass": "nope"}, {"res": "16k"}, {"renderer": "x"},
               {"engine": "turbo"}, {"metal": "bogus"}, {"img": ""}):
        c = _cmd(fm, img, **kw)
        assert c["ok"] is False and c["error"] and c["argv"] == []


def test_build_command_never_raises(fm):
    c = fm.build_command(None, 5, [], {}, object(), True, None, 3,
                         progress=True)
    assert c["ok"] is False and isinstance(c["error"], str)


# ---------- parse_generator_output ----------

def test_parse_success():
    from maxplugin import forge_max as fm
    out = "noise\n" + json.dumps({"ok": True, "manifest": "/m.json",
                                  "warnings": ["w1"]}) + "\n"
    assert fm.parse_generator_output(out) == ("/m.json", ["w1"], None)


def test_parse_nonzero_with_error():
    from maxplugin import forge_max as fm
    out = json.dumps({"ok": False, "error": "image unreadable"})
    assert fm.parse_generator_output(out, 1) == (None, [], "image unreadable")


def test_parse_nonzero_without_json():
    from maxplugin import forge_max as fm
    assert fm.parse_generator_output("garbage", 2) == (None, [], "see listener")
    assert fm.parse_generator_output("", 1)[2] == "see listener"


def test_parse_zero_without_manifest():
    from maxplugin import forge_max as fm
    for out in ("", "garbage", json.dumps({"ok": True})):
        m, w, e = fm.parse_generator_output(out, 0)
        assert m is None and w == [] and e == "Could not read generator output."


# ---------- finish_build + assign/slate ----------

def _manifest(tmp_path, **over):
    maps = _write_maps(tmp_path)
    mf = {"schema": 1, "name": "MF_Concrete", "class": "concrete",
          "res": "2k", "maps": maps, "warnings": []}
    mf.update(over)
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(mf))
    return str(p), maps


def test_finish_build_ok(tmp_path):
    fm, b, rt = _load(active_slot=3)
    path, maps = _manifest(tmp_path)
    r = fm.finish_build(path, ["fake warning"], "extra", False, False,
                        "both", None)
    assert r["state"] == "ok" and r["material"] == "MF_Concrete"
    assert [m["renderer"] for m in r["materials"]] == ["vray", "corona"]
    assert r["maps"] == maps and r["mclass"] == "concrete"
    assert r["assigned"] is False and r["renderer"] == "both"
    assert r["notes"][:2] == ["fake warning", "extra"]
    assert isinstance(r["misses"], list)
    assert r["text"].startswith("Done: 'MF_Concrete' -> editor slot 3")


def test_finish_build_error(tmp_path):
    fm, b, rt = _load()
    r = fm.finish_build(str(tmp_path / "missing.json"), [], None, False,
                        False, "auto", None)
    assert r["state"] == "err" and r["text"].startswith(
        "Material wiring failed:")


def test_assign_result_vray_and_none_selected(tmp_path):
    fm, b, rt = _load()
    path, _ = _manifest(tmp_path)
    r = fm.finish_build(path, [], None, False, False, "vray", None)
    assert fm.assign_result(r) == (False, "Nothing is selected.")
    node = mock_pymxs.MockNode("Box", frozenset())
    rt.selection = [node]
    ok, text = fm.assign_result(r)
    assert ok and text == "Put on 1 selected objects."
    assert node.material is rt.meditMaterials[r["slot"] - 1]


def test_assign_result_picks_active_renderer_when_both(tmp_path):
    fm, b, rt = _load(renderer="corona")
    path, _ = _manifest(tmp_path)
    r = fm.finish_build(path, [], None, False, False, "both", None)
    node = mock_pymxs.MockNode("Box", frozenset())
    rt.selection = [node]
    ok, _t = fm.assign_result(r)
    corona = [m for m in r["materials"] if m["renderer"] == "corona"][0]
    assert ok and node.material is rt.meditMaterials[corona["slot"] - 1]


def test_assign_result_never_raises(fm):
    ok, text = fm.assign_result({"materials": [{"renderer": "vray", "slot": 99}],
                                 "mclass": "nope"})
    assert ok is False and isinstance(text, str)
    assert fm.assign_result({})[0] is False


def test_slate_result_guarded(tmp_path):
    fm, b, rt = _load()
    path, _ = _manifest(tmp_path)
    r = fm.finish_build(path, [], None, False, False, "vray", None)
    assert fm.slate_result(r) in (True, False)     # mock has no sme: False
    assert fm.slate_result({}) is False


# ---------- renderer_status ----------

@pytest.mark.parametrize("renderer,classes,want", [
    ("vray", ("VRayMtl",), ("vray", "V-Ray found")),
    ("corona", ("CoronaPhysicalMtl",), ("corona", "Corona found")),
    ("vray", ("VRayMtl", "CoronaPhysicalMtl"),
     ("both", "V-Ray and Corona found")),
    (None, (), (None, "No renderer found")),
])
def test_renderer_status(renderer, classes, want):
    fm, b, rt = _load(renderer=renderer, classes=classes)
    assert fm.renderer_status() == want


# ---------- show() fallback ----------

def test_show_falls_back_to_rollout(fm, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "maxplugin.forge_qt", None)
    called = []
    monkeypatch.setattr(fm, "show_rollout", lambda: called.append(1) or "r")
    assert fm.show() == "r"
    assert called == [1]
    out = capsys.readouterr().out
    assert "[MatForge] Qt dock unavailable (" in out
    assert "opening the classic rollout." in out


def test_no_dashes_in_new_strings():
    src = open(os.path.join(REPO, "maxplugin", "forge_max.py"),
               encoding="utf-8").read()
    assert "—" not in src and "–" not in src
