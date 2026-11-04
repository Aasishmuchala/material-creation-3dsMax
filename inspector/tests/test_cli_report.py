import json

import numpy as np
from PIL import Image

from material_inspector import cli
from material_inspector.core.report import to_html, to_json
from tests.test_map_checks import noise, normal_from_height


def _save(path, a):
    a = np.clip(a, 0, 1)
    if a.shape[-1] == 1:
        a = a[..., 0]
    Image.fromarray((a * 255).astype(np.uint8)).save(path)


def make_set(folder, name, albedo=0.5, rough_const=False, directx=False, seam=False):
    h = noise(seed=5)
    alb = np.dstack([np.full(h.shape[:2], albedo)] * 3).astype(np.float32)
    rough = np.full_like(h, 0.5) if rough_const else noise(seed=7)
    if seam:
        rough = np.clip(rough + 0.4 * np.linspace(0, 1, rough.shape[1])[None, :, None], 0, 1)  # non-tileable edge
    _save(folder / f"{name}_Color.png", alb)
    _save(folder / f"{name}_Roughness.png", rough)
    _save(folder / f"{name}_Displacement.png", h)
    _save(folder / f"{name}_NormalGL.png", normal_from_height(h, directx=directx))


def test_classify():
    assert cli.classify("Wood049_2K_Roughness.png")[:2][1].value == "roughness"
    assert cli.classify("Bricks_4K-NormalGL.jpg")[0] == "Bricks_4K"
    assert cli.classify("readme.png")[1] is None


def test_folder_check_end_to_end(tmp_path):
    make_set(tmp_path, "Good")
    make_set(tmp_path, "Bad", albedo=0.03, directx=True, seam=True)
    make_set(tmp_path, "Flat", rough_const=True)
    out_html, out_json = tmp_path / "r.html", tmp_path / "r.json"
    code = cli.main(["check-folder", str(tmp_path), "--normal-convention", "opengl",
                     "--report", str(out_html), "--json", str(out_json)])
    assert code == 1
    doc = json.loads(out_json.read_text())
    bad = {f["rule_id"] for f in doc["findings"] if f["material"] == "Bad"}
    good = {f["rule_id"] for f in doc["findings"] if f["material"] == "Good" and f["severity"] != "info"}
    flat = {f["rule_id"] for f in doc["findings"] if f["material"] == "Flat"}
    assert {"M001", "M005", "M007"} <= bad
    assert "M003" in flat
    assert good == set()
    assert "<table>" in out_html.read_text()


def test_report_escapes_html():
    from material_inspector.core.model import Finding, Severity
    f = Finding("R010", Severity.ERROR, "<script>x</script>", "msg & more")
    h = to_html([f])
    assert "<script>x" not in h and "&lt;script&gt;" in h
    assert json.loads(to_json([f]))["summary"]["error"] == 1
