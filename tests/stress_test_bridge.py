"""STRESS SUITE D -- fal PATINA backend, rollout payload validation, user input.

Defects found by this suite (STRESS-D<n>, see .router/stress/D_bridge.md) are
fixed; their tests are now regression tests, the rest are contract tests.
No network, no paid calls: fal_client, urlretrieve, subprocess.run and the
omega HTTP call are all faked; key lookups are stubbed so no key file is read.
Heavy loops run 200 iterations by default, 2000 with STRESS_FULL=1.
"""
import json
import os
import random
import re
import shutil
import subprocess
import sys
import types

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.dirname(os.path.abspath(__file__))
for _p in (REPO, TESTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import forge_fal  # noqa: E402
import matphys  # noqa: E402
import mfconfig  # noqa: E402
import mock_pymxs  # noqa: E402
from core.recipes import RECIPES, RESOLUTIONS  # noqa: E402

FULL = bool(os.environ.get("STRESS_FULL"))
N_FUZZ = 2000 if FULL else 200
SECRET = "SENTINEL-FAKE-KEY-0123456789abcdef"     # never a real key


@pytest.fixture(autouse=True)
def _no_keys_no_net(monkeypatch):
    """No test may touch real key material or the network."""
    monkeypatch.setattr(mfconfig, "_load", lambda: {})
    monkeypatch.setitem(sys.modules, "_falkey", None)    # import -> ImportError
    monkeypatch.setitem(sys.modules, "_omegakey", None)
    monkeypatch.setitem(sys.modules, "winreg", None)

    def _no_net(*a, **k):
        raise AssertionError("network call attempted")
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", _no_net)


# ---------------------------------------------------------------------------
# 1. forge_fal
# ---------------------------------------------------------------------------

def _png(path, size=8):
    from PIL import Image
    Image.new("RGB", (size, size), (120, 120, 120)).save(str(path), "PNG")


def _items(types_=("basecolor", "normal", "roughness", "metalness", "height"),
           w=8):
    items = [{"url": "https://fake/flat.png"}]
    for t in types_:
        items.append({"url": "https://fake/%s.png" % t, "map_type": t,
                      "width": w, "height": w})
    return items


def _fal(tmp_path, monkeypatch, capsys, images=None, raises=None,
         retrieve=None, argv_extra=(), name="T", img=None, out="default",
         key=SECRET):
    """Run forge_fal.main with a fake fal_client. Returns (rc, out_text,
    err_text, calls, out_dir)."""
    calls = {"upload": 0, "subscribe": []}
    fake = types.ModuleType("fal_client")

    def upload_file(p):
        calls["upload"] += 1
        return "https://fake/img.jpg"

    def subscribe(model, arguments=None, with_logs=False):
        calls["subscribe"].append((model, arguments))
        if raises is not None:
            raise raises
        return {"images": _items() if images is None else images,
                "prompt": "expanded", "seed": 1}
    fake.upload_file = upload_file
    fake.subscribe = subscribe
    monkeypatch.setitem(sys.modules, "fal_client", fake)
    if key:
        monkeypatch.setenv("FAL_KEY", key)
    else:
        monkeypatch.delenv("FAL_KEY", raising=False)
        monkeypatch.setattr(mfconfig, "get_fal_key", lambda: None)

    def _default_retrieve(url, dest):
        _png(dest)
    monkeypatch.setattr(forge_fal.urllib.request, "urlretrieve",
                        retrieve or _default_retrieve)
    if img is None:
        img = tmp_path / "ref.png"
        _png(img)
    out_dir = tmp_path / "out"
    argv = [str(img), "--name", name, "--type", "wood_interior", "--no-fable"]
    if out == "default":
        argv += ["--out", str(out_dir)]
    argv += list(argv_extra)
    rc = forge_fal.main(argv)
    cap = capsys.readouterr()
    return rc, cap.out, cap.err, calls, out_dir


def _one_json(text):
    lines = [l for l in text.strip().splitlines() if l.strip()]
    assert len(lines) == 1, "stdout must be exactly one JSON line: %r" % text
    obj = json.loads(lines[0])
    assert isinstance(obj, dict) and isinstance(obj.get("ok"), bool)
    if not obj["ok"]:
        assert isinstance(obj.get("error"), str) and obj["error"]
    return obj


def _no_secret(*texts):
    for t in texts:
        assert SECRET not in (t or "")
        assert "Traceback" not in (t or "")


@pytest.mark.parametrize("images,ok", [
    ([], False),                                         # 0 images
    ([{"url": "https://fake/flat.png"}], False),         # only flat texture
    (_items(("basecolor", "basecolor")), True),          # duplicate map_type
    (_items(("basecolor", "sheen", "ao")), True),        # unknown map_type
    ([{"map_type": "basecolor", "width": 8}], False),    # item without url
    (_items(("basecolor",)) + [{"map_type": "height"}], False),
])
def test_fal_response_shapes_keep_json_contract(tmp_path, monkeypatch, capsys,
                                                images, ok):
    rc, out, err, _, out_dir = _fal(tmp_path, monkeypatch, capsys,
                                    images=images)
    obj = _one_json(out)
    assert obj["ok"] is ok and rc == (0 if ok else 1)
    _no_secret(out, err)
    if ok:
        mf = json.load(open(str(out_dir / "manifest.json")))
        assert set(mf["maps"]) == {"albedo"}
        _no_secret(json.dumps(mf))


def test_fal_width_absent_falls_back_to_png_header(tmp_path, monkeypatch,
                                                   capsys):
    imgs = [{"url": "u", "map_type": "basecolor"}]
    rc, out, _, _, _ = _fal(tmp_path, monkeypatch, capsys, images=imgs)
    assert _one_json(out)["res"] == "8px" and rc == 0


@pytest.mark.parametrize("exc", [
    TimeoutError("read timed out"),
    RuntimeError("HTTP 401 Unauthorized"),
    RuntimeError("HTTP 500 Internal Server Error"),
    RuntimeError("HTTP 429 rate limit exceeded"),
    ConnectionError("connection reset"),
])
def test_fal_client_errors_are_json(tmp_path, monkeypatch, capsys, exc):
    rc, out, err, _, _ = _fal(tmp_path, monkeypatch, capsys, raises=exc)
    obj = _one_json(out)
    assert rc == 1 and obj["ok"] is False
    _no_secret(out, err)


def test_fal_keyboard_interrupt_is_json(tmp_path, monkeypatch, capsys):
    """STRESS-D8 regression."""
    try:
        rc, out, err, _, _ = _fal(tmp_path, monkeypatch, capsys,
                                  raises=KeyboardInterrupt())
    except KeyboardInterrupt:
        pytest.fail("KeyboardInterrupt escaped forge_fal.main")
    assert rc != 0 and _one_json(out)["error"] == "cancelled"
    _no_secret(out, err)


def test_fal_no_key_is_clean(tmp_path, monkeypatch, capsys):
    rc, out, err, calls, _ = _fal(tmp_path, monkeypatch, capsys, key=None)
    obj = _one_json(out)
    assert rc == 1 and obj["error"] == "FAL_KEY not set"
    assert calls["upload"] == 0


@pytest.mark.parametrize("kind", ["missing", "dir"])
def test_fal_bad_image_path(tmp_path, monkeypatch, capsys, kind):
    p = tmp_path / "nope.png"
    if kind == "dir":
        p.mkdir()
    rc, out, _, calls, _ = _fal(tmp_path, monkeypatch, capsys, img=p)
    assert rc == 1 and _one_json(out)["ok"] is False
    assert calls["upload"] == 0


@pytest.mark.parametrize("kind", ["psd", "empty_png", "html_as_png",
                                  "truncated_png", "oversize"])
def test_fal_rejects_non_image_before_paid_call(tmp_path, monkeypatch, capsys,
                                                kind):
    """STRESS-D6 regression: nothing is uploaded or paid for."""
    import maxplugin.inputs as inputs
    p = tmp_path / ("ref.psd" if kind == "psd" else "ref.png")
    if kind == "psd":
        p.write_bytes(b"8BPS" + b"\x00" * 64)
    elif kind == "empty_png":
        p.write_bytes(b"")
    elif kind == "html_as_png":
        p.write_bytes(b"<html>404</html>")
    elif kind == "truncated_png":
        p.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")
    else:
        _png(p, size=64)
        monkeypatch.setattr(inputs, "MAX_IMAGE_BYTES", 16)
    rc, out, _, calls, _ = _fal(tmp_path, monkeypatch, capsys, img=p)
    assert calls["subscribe"] == [] and calls["upload"] == 0 and rc == 1
    assert _one_json(out)["ok"] is False


@pytest.mark.parametrize("payload", [b"", b"<html>404</html>",
                                     b"\x89PNG\r\n\x1a\n\x00\x00"])
def test_fal_rejects_bad_download(tmp_path, monkeypatch, capsys, payload):
    def retrieve(url, dest):
        with open(dest, "wb") as f:
            f.write(payload)
    imgs = [{"url": "u", "map_type": "basecolor"}]
    rc, out, _, _, out_dir = _fal(tmp_path, monkeypatch, capsys, images=imgs,
                                  retrieve=retrieve)
    assert _one_json(out)["ok"] is False and rc == 1     # STRESS-D5 regression
    assert not (out_dir / "albedo.png").exists()


def test_fal_mismatched_sizes(tmp_path, monkeypatch, capsys):
    imgs = [{"url": "a", "map_type": "basecolor", "width": 2048},
            {"url": "b", "map_type": "roughness", "width": 1024}]
    rc, out, _, _, out_dir = _fal(tmp_path, monkeypatch, capsys, images=imgs)
    mf = json.load(open(str(out_dir / "manifest.json")))   # STRESS-D7
    assert mf["res"] == "8px"                  # real albedo px, not the claim
    assert any("2048" in w for w in mf["warnings"])


def test_fal_real_size_mismatch_warns(tmp_path, monkeypatch, capsys):
    def retrieve(url, dest):
        _png(dest, size=16 if "roughness" in url else 8)
    rc, out, _, _, out_dir = _fal(tmp_path, monkeypatch, capsys,
                                  retrieve=retrieve)
    mf = json.load(open(str(out_dir / "manifest.json")))
    assert rc == 0 and mf["res"] == "8px"
    assert any("roughness 16x16" in w for w in mf["warnings"])


def test_fal_failed_download_cleans_part(tmp_path, monkeypatch, capsys):
    def retrieve(url, dest):
        with open(dest, "wb") as f:
            f.write(b"\x89PNG")
        raise ConnectionError("reset mid-download")
    rc, out, _, _, _ = _fal(tmp_path, monkeypatch, capsys, retrieve=retrieve)
    assert rc == 1 and _one_json(out)["ok"] is False     # STRESS-D9 regression
    assert not [f for f in os.listdir(str(tmp_path / "out"))
                if f.endswith(".part")]


def test_fal_manifest_paths_inside_out(tmp_path, monkeypatch, capsys):
    rc, out, _, _, out_dir = _fal(tmp_path, monkeypatch, capsys,
                                  name='../../x"; y')
    assert rc == 0
    mf = json.load(open(str(out_dir / "manifest.json")))
    root = os.path.realpath(str(out_dir))
    for p in mf["maps"].values():
        assert ".." not in p.split(os.sep)
        assert os.path.realpath(p).startswith(root + os.sep)


def test_fal_default_out_no_traversal(tmp_path, monkeypatch, capsys):
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    img = sub / "ref.png"
    _png(img)
    rc, out, _, _, _ = _fal(tmp_path, monkeypatch, capsys, img=img,
                            name="../../escaped", out=None)
    mp = _one_json(out).get("manifest", "")             # STRESS-D4 regression
    assert rc == 0
    assert os.path.realpath(mp).startswith(os.path.realpath(str(sub)) + os.sep)
    assert os.path.basename(os.path.dirname(mp)) == "escaped_maps"


def test_fal_long_prompt_passed_through(tmp_path, monkeypatch, capsys):
    big = "oak " * 2500
    rc, out, _, calls, _ = _fal(tmp_path, monkeypatch, capsys,
                                argv_extra=["--prompt", big])
    assert rc == 0 and calls["subscribe"][0][1]["prompt"] == big


@pytest.mark.parametrize("extra", [
    ["--mode", "bogus"], ["--mode", ""], ["--mode", "EXTRACT"],
    ["--upscale", "3"], ["--upscale", "abc"],
])
def test_fal_bad_args_still_json(tmp_path, monkeypatch, capsys, extra):
    try:                                                # STRESS-D10 regression
        _fal(tmp_path, monkeypatch, capsys, argv_extra=extra)
    except SystemExit as e:
        assert e.code == 2
    obj = _one_json(capsys.readouterr().out)
    assert obj["ok"] is False and obj["error"].startswith("bad arguments")


@pytest.mark.parametrize("argv", [
    ["img.png", "--name", "x", "--type", "bogus"],
    ["img.png", "--name", "x", "--type", "generic", "--res", "16k"],
    ["img.png", "--type", "generic"],
    ["/no/such/file.png", "--name", "x", "--type", "generic"],
])
def test_cli_bad_args_still_json(capsys, argv):
    import forge_cli
    try:
        forge_cli.main(argv)
    except SystemExit as e:
        assert e.code == 2
    obj = _one_json(capsys.readouterr().out)
    assert obj["ok"] is False


def test_cli_default_out_no_traversal(tmp_path, monkeypatch, capsys):
    import forge_cli
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    img = sub / "ref.png"
    _png(img, size=16)
    seen = {}

    def fake_generate(image, out_dir, **kw):
        seen["out"] = out_dir
        os.makedirs(out_dir, exist_ok=True)
        return {}
    monkeypatch.setattr(forge_cli, "generate_maps", fake_generate)
    rc = forge_cli.main([str(img), "--name", "../../escaped", "--type",
                         "generic", "--res", "2k"])
    assert rc == 0 and _one_json(capsys.readouterr().out)["ok"] is True
    assert os.path.realpath(seen["out"]) == os.path.realpath(
        str(sub / "escaped_maps"))


def test_cli_keyboard_interrupt_is_json(tmp_path, monkeypatch, capsys):
    import forge_cli
    img = tmp_path / "ref.png"
    _png(img)

    def boom(*a, **k):
        raise KeyboardInterrupt()
    monkeypatch.setattr(forge_cli, "generate_maps", boom)
    rc = forge_cli.main([str(img), "--name", "x", "--type", "generic"])
    assert rc != 0 and _one_json(capsys.readouterr().out)["error"] == "cancelled"


def test_fal_mode_fuzz_valid_values(tmp_path, monkeypatch, capsys):
    rng = random.Random(4)
    for mode in sorted(forge_fal.ENDPOINTS) * 2:
        up = rng.choice(["0", "2", "4"])
        rc, out, _, calls, _ = _fal(tmp_path, monkeypatch, capsys,
                                    argv_extra=["--mode", mode,
                                                "--upscale", up])
        assert rc == 0 and calls["subscribe"][0][0] == forge_fal.ENDPOINTS[mode]
        assert calls["subscribe"][0][1]["upscale_factor"] == int(up)


# ---------------------------------------------------------------------------
# 2. payload validation through mock pymxs
# ---------------------------------------------------------------------------

@pytest.fixture
def fm(monkeypatch, tmp_path):
    """forge_max bound to a fresh mock runtime + a fake generator subprocess
    that behaves like forge_cli/forge_fal's argparse (exit 2, empty stdout on
    a bad --type/--res) and otherwise writes a real manifest."""
    builder, rt = mock_pymxs.install()
    import importlib

    import maxplugin.forge_max as fmod
    importlib.reload(fmod)
    fmod._PYBIN = ["python3"]
    maps_dir = tmp_path / "maps"
    maps_dir.mkdir()
    maps = {}
    for k in ("albedo", "roughness", "normal", "height"):
        _png(maps_dir / (k + ".png"))
        maps[k] = str(maps_dir / (k + ".png"))
    calls = []

    def run(cmd, **kw):
        for a in cmd:
            if not isinstance(a, str):
                raise TypeError("expected str, bytes or os.PathLike object, "
                                "not %s" % type(a).__name__)
        calls.append({"cmd": cmd,      # never keep env: it holds real vars
                      "fal_key_is_fake": (kw.get("env") or {}).get(
                          "FAL_KEY") == SECRET})
        args = cmd[len(fmod._PYBIN):]
        opt = dict(zip(args[2::2], args[3::2]))
        bad = (opt.get("--type") not in RECIPES or
               ("--res" in opt and opt["--res"] not in RESOLUTIONS))
        if bad:
            return subprocess.CompletedProcess(cmd, 2, "", "usage: error")
        mp = tmp_path / "manifest.json"
        mp.write_text(json.dumps({"schema": 1, "name": opt["--name"],
                                  "class": opt["--type"], "maps": maps}))
        return subprocess.CompletedProcess(
            cmd, 0, json.dumps({"ok": True, "manifest": str(mp)}) + "\n", "")
    monkeypatch.setattr(fmod.subprocess, "run", run)
    monkeypatch.setattr(fmod, "_fal_key", lambda: SECRET)
    img = tmp_path / "ref.png"
    _png(img)
    fmod._test = types.SimpleNamespace(rt=rt, builder=builder, calls=calls,
                                       img=str(img), tmp=tmp_path)
    return fmod


_WEIRD_NAMES = ["", "x" * 10000, 'a"b', "a\\b", "a'b", "a\nb", "100%", "a)b",
                "../../etc", "Ünïcødé_名前", "nul\x00byte", None, 5, [], {}]
_FIELDS = {
    "rnd": ["auto", "vray", "corona", "both", "BOTH", "Vray", " corona",
            None, 1, ""],
    "metal": ["gold", "Gold", "", None, "bogus", 5, "stainless_steel", []],
    "cls": list(RECIPES)[:4] + ["bogus", None, "", 7, "metal_brushed"],
    "res": ["2k", "4k", "8k", "16k", 0, -1, None, "abc"],
    "eng": ["fast", "ultra", "turbo", None, "ULTRA"],
    "assign": [True, False, "false", "0", 0, None, "yes"],
    "slate": [True, False, "false", None],
    "name": _WEIRD_NAMES,
    "img": ["__IMG__", "", None, "/no/such/file.png", "__DIR__",
            "__TXT__", 5, ["x"]],
}


def _rand_payload(rng, fmod):
    p = {}
    for k, vals in _FIELDS.items():
        if rng.random() < 0.15:
            continue                                    # missing field
        v = rng.choice(vals)
        if v == "__IMG__":
            v = fmod._test.img
        elif v == "__DIR__":
            v = str(fmod._test.tmp)
        elif v == "__TXT__":
            t = fmod._test.tmp / "notes.txt"
            t.write_text("not an image")
            v = str(t)
        p[k] = v
    return p


def _check_result(state, text):
    assert state in ("ok", "err"), state
    assert isinstance(text, str) and text
    assert SECRET not in text and "Traceback" not in text


def _payload_result(fm, raw):
    """Parse a raw payload like the old bridge did, then validate+run it."""
    try:
        p = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        p = raw
    return fm._create_from_payload(p)


def test_bridge_bad_payload_shapes(fm):
    for raw in ("[1,2]", "5", '"s"', "null"):
        r = _payload_result(fm, raw)
        assert r["state"] == "err" and r["text"]


def test_chat_reply_never_raises(fm, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("gateway down")
    monkeypatch.setattr(mfconfig, "omega_message", boom)
    assert fm.chat_reply("x").startswith("Chat unavailable")


def test_bridge_create_fuzz(fm):
    rng = random.Random(1234)
    for i in range(N_FUZZ):
        if i % 10 == 0:                                 # corrupt payloads
            raw = rng.choice(["", "{", "null", "[1,2]", "5", '"s"',
                              "undefined", "{\"img\":"])
        else:
            raw = json.dumps(_rand_payload(rng, fm))
        r = _payload_result(fm, raw)                    # must never raise
        _check_result(r["state"], r["text"])


def test_create_from_panel_fuzz(fm):
    rng = random.Random(99)
    for i in range(N_FUZZ):
        p = None if i % 25 == 0 else _rand_payload(rng, fm)
        r = fm._create_from_payload(p)
        _check_result(r.get("state"), r.get("text"))


def test_bridge_happy_path_and_no_key_leak(fm):
    r = fm._create_from_payload({"img": fm._test.img, "name": "Oak",
                                 "cls": "wood_interior", "res": "4k",
                                 "eng": "ultra", "rnd": "vray",
                                 "metal": "", "assign": False,
                                 "slate": False})
    assert r["state"] == "ok", r["text"]
    assert SECRET not in r["text"]
    call = fm._test.calls[-1]
    assert SECRET not in " ".join(call["cmd"])          # key only via env
    assert call["fal_key_is_fake"]


@pytest.mark.parametrize("field,value", [
    ("rnd", "bogus"), ("rnd", 1), ("metal", "Gold"), ("metal", 5),
    ("cls", "bogus"), ("cls", None), ("res", "16k"), ("res", 0),
    ("eng", "turbo"), ("eng", None), ("assign", "yes"),
    ("img", ""), ("img", "/no/such/file.png"), ("img", "__TXT__"),
    ("img", "__PSD__"), ("img", "__EMPTY__"),
])
def test_bridge_validates_before_generation(fm, field, value):
    """STRESS-D2 regression: every bad field is an error and nothing runs."""
    if value == "__TXT__":
        value = str(fm._test.tmp / "notes.txt")
        open(value, "w").write("not an image")
    elif value == "__PSD__":
        value = str(fm._test.tmp / "ref.psd")
        open(value, "wb").write(b"8BPS" + b"\x00" * 64)
    elif value == "__EMPTY__":
        value = str(fm._test.tmp / "empty.png")
        open(value, "wb").close()
    p = {"img": fm._test.img, "name": "Oak", "cls": "metal_brushed",
         "res": "4k", "eng": "ultra", "rnd": "vray", "metal": "gold"}
    p[field] = value
    r = fm._create_from_payload(p)
    assert r["state"] == "err" and len(fm._test.calls) == 0
    assert r["text"] and "see listener" not in r["text"]


@pytest.mark.parametrize("field,value,want", [
    ("rnd", "BOTH", "both"), ("rnd", " corona", "corona"),
    ("rnd", "Vray", "vray"), ("eng", "ULTRA", None), ("res", "4K", None),
])
def test_bridge_normalises_case_and_space(fm, monkeypatch, field, value, want):
    seen = {}

    def spy(*a, **k):
        seen.update(k)
        return {"material": "Oak", "slot": 1, "log": []}
    monkeypatch.setattr(fm.builder, "build_from_manifest", spy)
    p = {"img": fm._test.img, "name": "Oak", "cls": "wood_interior",
         "res": "4k", "eng": "fast", "rnd": "vray"}
    p[field] = value
    r = fm._create_from_payload(p)
    assert r["state"] == "ok", r["text"]
    if want:
        assert seen["renderer"] == want
    if field == "eng":
        assert fm._test.calls[-1]["cmd"][len(fm._PYBIN)] == fm.FAL


def test_bridge_string_false_is_false(fm, monkeypatch):
    seen = {}
    real = fm.builder.build_from_manifest

    def spy(*a, **k):
        seen.update(k)
        return real(*a, **k)
    monkeypatch.setattr(fm.builder, "build_from_manifest", spy)
    fm._create_from_payload({"img": fm._test.img, "name": "Oak",
                             "cls": "wood_interior", "res": "2k",
                             "assign": "false", "slate": "false"})
    assert seen["assign"] is False and seen["slate"] is False   # STRESS-D3


@pytest.mark.parametrize("v,want", [(True, True), (1, True), ("true", True),
                                    ("1", True), (False, False), (0, False),
                                    ("0", False), (None, False)])
def test_bridge_bool_parser(fm, v, want):
    assert fm._parse_bool(v, "assign") is want


def test_bridge_caps_name_length(fm):
    fm._create_from_payload({"img": fm._test.img, "name": "x" * 10000,
                             "cls": "wood_interior", "res": "2k"})
    cmd = fm._test.calls[-1]["cmd"]                     # STRESS-D11 regression
    assert len(cmd[cmd.index("--name") + 1]) <= 48


def test_sanitize_makes_filesystem_safe_names(fm):
    rng = random.Random(7)
    alphabet = 'aZ09_"\\\'\n%)(../:*?<>|\x00 名é'
    for _ in range(N_FUZZ):
        s = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40)))
        out = fm._sanitize(s)
        assert out and not re.search(r'[\\/:*?"<>|\x00\n.%\'()\s]', out)


# ---------------------------------------------------------------------------
# 3. injection audit -- MAXScript string building
# ---------------------------------------------------------------------------

def _mxs_read_string(src, i):
    """Mini MAXScript lexer: src[i] == '"'. Returns (decoded, end_index)."""
    assert src[i] == '"'
    i += 1
    out = []
    while i < len(src):
        c = src[i]
        if c == "\\":
            out.append({"n": "\n", "t": "\t", "r": "\r"}.get(src[i + 1],
                                                            src[i + 1]))
            i += 2
            continue
        if c == '"':
            return "".join(out), i
        out.append(c)
        i += 1
    raise ValueError("unterminated string")


_INJECT = ['a"b', 'x") ; deleteFile "c:\\\\x" ; ("', "a\\", "\\\"", "a)b",
           "100%", "%METAL_ITEMS%", "a\nb", "名前", "'q'", ""]


@pytest.mark.parametrize("s", _INJECT)
def test_mxs_str_round_trips(fm, s):
    lit = '"' + fm._mxs_str(s) + '"'
    decoded, end = _mxs_read_string(lit, 0)
    assert decoded == s and end == len(lit) - 1


def _rollouts(fm):
    seen = []
    fm._test.rt.execute = lambda src: seen.append(src) or True
    return seen


def test_show_twice_reregisters_cleanly(fm):
    seen = _rollouts(fm)
    fm.show_rollout()
    fm.show_rollout()
    assert len(seen) == 2 and seen[0] == seen[1]
    for src in seen:
        assert src.lstrip().startswith("try (destroyDialog MatForgeRollout)")
        assert "%CLASS_ITEMS%" not in src and "%METAL_ITEMS%" not in src
        for lab in [l for _, l in fm._CLASSES] + [
                l for _, l in matphys.metal_choices()]:
            assert '"%s"' % fm._mxs_str(lab) in src


def test_show_compile_false_raises(fm):
    fm._test.rt.execute = lambda src: False
    with pytest.raises(RuntimeError):
        fm.show_rollout()


def test_show_template_single_pass(fm, monkeypatch):
    monkeypatch.setattr(fm, "_CLASSES", [("x", "Evil %METAL_ITEMS%")])
    seen = _rollouts(fm)                                # STRESS-D12 regression
    fm.show_rollout()
    assert '"Evil %METAL_ITEMS%"' in seen[0]


def _macro_src(root, file_name="run_matforge.py"):
    """Python port of matforge_macros.ms mfMacroSrc (after trimRight)."""
    root = root.rstrip("\\/")
    return ('macroScript MatForge_Open\n(\n    on execute do (\n'
            '        global MatForgeRoot = @"' + root + '"\n'
            '        local p = @"' + root + "\\" + file_name + '"\n    )\n)\n')


def _verbatim_literals(src):
    """@"..." verbatim strings: no escapes; the first '"' ends the literal."""
    return re.findall(r'@"([^"]*)"', src)


def test_macro_port_matches_ms_source():
    ms = open(os.path.join(REPO, "matforge_macros.ms"), encoding="utf-8").read()
    assert 'global MatForgeRoot = @\\"" + root + "\\"' in ms
    assert 'root = trimRight root "\\\\/"' in ms


@pytest.mark.parametrize("root", [
    r"C:\Program Files\Mat Forge", r"C:\100%\MatForge", "C:\\Ünï\\名前",
    "C:\\MatForge\\", "D:\\a b\\c\\\\",
])
def test_macro_root_safe_paths(root):
    lits = _verbatim_literals(_macro_src(root))
    clean = root.rstrip("\\/")
    assert lits == [clean, clean + "\\run_matforge.py"]


def test_macro_root_with_quote_documented_impossible():
    """STRESS-D13: a root containing '"' would close the @"..." literal, but
    NTFS forbids '"' in names; documented in VERIFY_INSTALL, no code guard."""
    doc = open(os.path.join(REPO, "docs", "VERIFY_INSTALL.md"),
               encoding="utf-8").read()
    assert "STRESS-D13" in doc and "NTFS forbids" in doc


def test_execute_sites_use_constants_only():
    """Every rt.execute call site is a constant or the single-pass
    template fill."""
    fm_src = open(os.path.join(REPO, "maxplugin", "forge_max.py"),
                  encoding="utf-8").read()
    sites = re.findall(r"rt\.execute\((.*)", fm_src)
    assert len(sites) == 3
    assert sites[0].startswith('"(VRayMtl') and sites[1].startswith(
        '"(CoronaPhysicalMtl') and sites[2].startswith("_fill_rollout(")
    fill = fm_src[fm_src.index("def _fill_rollout"):fm_src.index("def show_rollout")]
    assert "re.sub(" in fill and "ROLLOUT_MXS)" in fill


# ---------------------------------------------------------------------------
# 4. reentrancy / state
# ---------------------------------------------------------------------------

def test_bridge_create_ignores_stale_log(fm):
    fm._test.builder.LOG[:] = ["  MISS: stale line from a previous build"] * 5
    r = fm._create_from_payload({"img": fm._test.img, "name": "Oak",
                                 "cls": "wood_interior", "res": "2k",
                                 "rnd": "vray"})
    assert r["state"] == "ok" and "with notes" not in r["text"]


def test_bridge_err_after_ok_overwrites_text(fm):
    r = fm._create_from_payload({"img": fm._test.img, "cls": "generic",
                                 "res": "2k"})
    assert r["state"] == "ok"
    r = fm._create_from_payload({"img": ""})
    assert r["state"] == "err" and "reference image" in r["text"]


def test_chat_reply_no_key_is_clean(fm, monkeypatch):
    monkeypatch.setattr(mfconfig, "get_omega",
                        lambda: ("", mfconfig.OMEGA_DEFAULT_BASE,
                                 mfconfig.OMEGA_DEFAULT_MODEL))
    r = fm.chat_reply("how do I make oak?")
    assert r.startswith("Chat unavailable: no omega key set")


def test_chat_reply_http_failure_no_key_echo(fm, monkeypatch):
    monkeypatch.setattr(mfconfig, "get_omega",
                        lambda: (SECRET, "https://example.invalid/v1",
                                 mfconfig.OMEGA_DEFAULT_MODEL))
    import urllib.request

    def boom(req, timeout=None):
        raise OSError("HTTP Error 403: Forbidden")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    r = fm.chat_reply("x" * 10000)
    assert r.startswith("Chat unavailable") and SECRET not in r


def test_chat_reply_returns_omega_text(fm, monkeypatch):
    monkeypatch.setattr(
        mfconfig, "omega_message",
        lambda content, **k: "reply:%d" % len(content[0]["text"]))
    assert fm.chat_reply("hi") == "reply:2"


def test_keys_status_masked(monkeypatch):
    monkeypatch.setenv("FAL_KEY", SECRET)
    st = mfconfig.get_keys_status()
    assert st["fal_set"] is True and SECRET not in json.dumps(st)


def test_diagnose_without_renderers(monkeypatch):
    builder, rt = mock_pymxs.install(classes=())
    import importlib

    import maxplugin.forge_max as fmod
    importlib.reload(fmod)
    fmod._PYBIN = ["python3"]
    monkeypatch.setattr(fmod.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0))
    monkeypatch.setattr(mfconfig, "get_keys_status", lambda: {})
    rep = fmod.diagnose()
    assert "[FAIL] V-Ray" in rep and "[FAIL] Corona" in rep
    assert "neither renderer found" in rep and "Traceback" not in rep
