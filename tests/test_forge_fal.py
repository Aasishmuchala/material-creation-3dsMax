"""forge_fal: fake fal_client, no network, no spend."""
import json
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import forge_fal  # noqa: E402

TYPES = ["basecolor", "height", "normal", "roughness", "metalness"]


def _response(with_base=True):
    items = [{"url": "https://fake/flat.png"}]
    for t in TYPES:
        if t == "basecolor" and not with_base:
            continue
        items.append({"url": "https://fake/%s.png" % t, "map_type": t,
                      "width": 8, "height": 8})
    return {"images": items, "seed": 1, "prompt": "expanded"}


def _run(tmp_path, monkeypatch, extra=(), with_base=True):
    calls = []
    fake = types.ModuleType("fal_client")
    fake.upload_file = lambda p: "https://fake/img.jpg"

    def subscribe(model, arguments=None, with_logs=False):
        calls.append((model, arguments))
        return _response(with_base)
    fake.subscribe = subscribe
    monkeypatch.setitem(sys.modules, "fal_client", fake)
    monkeypatch.setenv("FAL_KEY", "test")

    from PIL import Image

    def retrieve(url, dest):
        Image.new("RGB", (8, 8), (120, 120, 120)).save(dest, format="PNG")
    monkeypatch.setattr(forge_fal.urllib.request, "urlretrieve", retrieve)

    img = tmp_path / "ref.png"
    Image.new("RGB", (8, 8)).save(str(img))
    out = tmp_path / "out"
    rc = forge_fal.main([str(img), "--name", "T", "--type", "metal_brushed",
                         "--no-fable", "--out", str(out)] + list(extra))
    return rc, calls, out


def test_extract_default(tmp_path, monkeypatch):
    rc, calls, out = _run(tmp_path, monkeypatch)
    assert rc == 0
    assert calls[0][0] == "fal-ai/patina/material/extract"
    assert calls[0][1]["image_url"] == "https://fake/img.jpg"
    mf = json.load(open(str(out / "manifest.json")))
    assert set(mf["maps"]) == {"albedo", "normal", "roughness", "metalness",
                               "height"}
    assert mf["source"] == "fal-patina-extract"


def test_generate_mode(tmp_path, monkeypatch):
    rc, calls, out = _run(tmp_path, monkeypatch, ["--mode", "generate"])
    assert rc == 0
    assert calls[0][0] == "fal-ai/patina/material"
    mf = json.load(open(str(out / "manifest.json")))
    assert mf["source"] == "fal-patina-generate"


def test_no_basecolor_fails(tmp_path, monkeypatch, capsys):
    rc, calls, out = _run(tmp_path, monkeypatch, with_base=False)
    assert rc == 1
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert json.loads(last)["ok"] is False
