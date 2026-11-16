"""Execute tools/max_selftest.py against a fake pymxs, so the one-shot Windows run is not its first run."""
import json
import os
import runpy
import sys

from tests import fake_pymxs


def test_selftest_runs_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path)); monkeypatch.setenv("TEMP", str(tmp_path))
    import tempfile; monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    mod = fake_pymxs.install()
    monkeypatch.setitem(sys.modules, "pymxs", mod)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    runpy.run_path(os.path.join(root, "tools", "max_selftest.py"), run_name="__main__")
    rep = json.loads((tmp_path / "material_inspector_selftest.json").read_text())
    failed = [s for s in rep["steps"] if not s["ok"]]
    assert not failed, failed[0]["error"]
    for name, r in rep["expected_vs_found"].items():
        assert r["missing"] == [] and r["unexpected_errors_warnings"] == [], (name, r)
    assert rep["fixes"] and all(f["ok"] for f in rep["fixes"]), rep["fixes"]
    remaining = {tuple(x) for x in rep["after_fix"]}
    assert ("ST_VRay_Bad", "R001") not in remaining and ("ST_Corona_Glass", "R014") not in remaining
    assert mod.runtime.messages and "steps OK" in mod.runtime.messages[0]
