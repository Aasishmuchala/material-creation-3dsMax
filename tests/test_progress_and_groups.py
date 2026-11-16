"""T3: progress lines, class groups, fake generator."""
import json
import os
import re
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.recipes import (CLASS_GROUPS, RECIPES, grouped_class_choices,
                          wants_metal_picker)

PIL = pytest.importorskip("PIL.Image")
FAKE = os.path.join(ROOT, "tests", "fake_generator.py")
CLI = os.path.join(ROOT, "forge_cli.py")
PROG = re.compile(r"^PROGRESS (\d+)/(\d+) (.+)$")


def _png(tmp_path, name="src.png"):
    p = tmp_path / name
    PIL.new("RGB", (8, 8), (120, 90, 60)).save(str(p))
    return str(p)


def _run(cmd, env=None, **kw):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run(cmd, capture_output=True, text=True, env=e,
                          timeout=120, **kw)


def test_cli_progress_lines(tmp_path):
    img = _png(tmp_path)
    r = _run([sys.executable, CLI, img, "--name", "T", "--type", "generic",
              "--res", "2k", "--progress"])
    assert r.returncode == 0, r.stderr
    lines = [PROG.match(l) for l in r.stderr.splitlines() if l.startswith("PROGRESS")]
    assert [(m.group(1), m.group(2), m.group(3)) for m in lines] == [
        ("1", "3", "Reading the photo"), ("2", "3", "Making the maps"),
        ("3", "3", "Saving the maps")]
    assert json.loads(r.stdout.strip().splitlines()[-1])["ok"] is True
    assert "PROGRESS" not in r.stdout


def test_cli_without_progress_flag(tmp_path):
    img = _png(tmp_path)
    r = _run([sys.executable, CLI, img, "--name", "T", "--type", "generic",
              "--res", "2k"])
    assert r.returncode == 0, r.stderr
    assert "PROGRESS" not in r.stderr


def test_fal_has_progress_flag():
    r = _run([sys.executable, os.path.join(ROOT, "forge_fal.py"), "--help"])
    assert r.returncode == 0
    assert "--progress" in r.stdout


def test_generate_maps_swallows_progress_errors(tmp_path):
    from core.maps import generate_maps
    calls = []

    def boom(n, t, l):
        calls.append(n)
        raise RuntimeError("nope")

    maps = generate_maps(_png(tmp_path), str(tmp_path / "out"),
                         mclass="generic", resolution="2k", progress=boom)
    assert calls == [1, 2, 3]
    assert "albedo" in maps


def test_groups_cover_recipes_once():
    keys = [k for _g, ks in CLASS_GROUPS for k in ks]
    assert len(keys) == len(set(keys))
    assert set(keys) == set(RECIPES)
    assert [g for g, _ in CLASS_GROUPS] == [
        "Wood", "Stone", "Metal", "Glass", "Fabric", "Plastic", "Other"]
    flat = [k for _g, items in grouped_class_choices() for k, _l in items]
    assert flat == keys
    assert wants_metal_picker("metal_rust") is True
    assert wants_metal_picker("car_paint") is False


def _fake(tmp_path, mode, extra=()):
    img = _png(tmp_path)
    cmd = [sys.executable, FAKE, img, "--name", "Fk", "--type", "stone",
           "--res", "2k", "--progress"] + list(extra)
    return img, cmd, {"MATFORGE_FAKE_MODE": mode}


def test_fake_ok(tmp_path):
    img, cmd, env = _fake(tmp_path, "ok")
    r = _run(cmd, env)
    assert r.returncode == 0, r.stderr
    assert [l for l in r.stderr.splitlines() if l.startswith("PROGRESS")] == [
        "PROGRESS 1/3 Reading the photo", "PROGRESS 2/3 Making the maps",
        "PROGRESS 3/3 Saving the maps"]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["ok"] is True and out["warnings"] == ["fake warning"]
    man = json.load(open(out["manifest"]))
    assert man["schema"] == 1 and man["name"] == "Fk" and man["class"] == "stone"
    assert man["res"] == "2k" and man["warnings"] == ["fake warning"]
    assert sorted(man["maps"]) == sorted(
        ["albedo", "roughness", "normal", "height", "metalness"])
    assert os.path.dirname(out["manifest"]) == str(tmp_path / "Fk_maps")
    for p in man["maps"].values():
        with PIL.open(p) as im:
            assert im.size == (8, 8)
            im.load()


def test_fake_fail(tmp_path):
    _img, cmd, env = _fake(tmp_path, "fail")
    r = _run(cmd, env)
    assert r.returncode == 1
    assert json.loads(r.stdout.strip()) == {
        "ok": False, "error": "Fake failure: image unreadable"}


def test_fake_badjson(tmp_path):
    _img, cmd, env = _fake(tmp_path, "badjson")
    r = _run(cmd, env)
    assert r.returncode == 0
    assert r.stdout.strip() == "garbage"


def test_fake_hang(tmp_path):
    _img, cmd, env = _fake(tmp_path, "hang")
    e = dict(os.environ)
    e.update(env)
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, env=e)
    try:
        t0 = time.time()
        line = p.stderr.readline()
        assert time.time() - t0 < 2.0 + 1.0  # interpreter start-up slack
        assert line.strip() == "PROGRESS 1/3 Reading the photo"
        assert p.poll() is None
    finally:
        p.kill()
        p.wait()
