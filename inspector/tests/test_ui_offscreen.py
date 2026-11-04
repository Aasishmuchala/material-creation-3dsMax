"""Drive the real PySide6 panel headlessly against the fake MAXScript runtime."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from material_inspector.max_adapter import ui  # noqa: E402
from tests.test_scene_and_fixes import vray_scene  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def panel(app, monkeypatch, tmp_path):
    monkeypatch.setenv("MATERIAL_INSPECTOR_CONFIG", str(tmp_path / "inspector.json"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    msgs = []
    monkeypatch.setattr(ui.InspectorPanel, "_notify", lambda self, t: msgs.append(t))
    monkeypatch.setattr(QtWidgets.QMessageBox, "question",
                        lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes)
    p = ui.InspectorPanel(vray_scene())
    p._msgs = msgs
    return p


def test_scan_populates_tree(panel):
    panel.chk_pixels.setChecked(False)
    panel.scan()
    assert panel.tree.topLevelItemCount() == 2
    assert "errors" in panel.status.text()


def test_fix_all_errors_then_rescan_clears_them(panel):
    panel.chk_pixels.setChecked(False)
    panel.scan()
    before = sum(f.severity.value == "error" and f.fixable for f in panel.findings)
    assert before > 0
    panel.fix_all_errors()
    assert panel._msgs and "Applied" in panel._msgs[-1]
    after = sum(f.severity.value == "error" and f.fixable for f in panel.findings)
    assert after < before


def test_scan_failure_is_logged_not_raised(panel, monkeypatch, tmp_path):
    monkeypatch.setattr(ui.SceneReader, "materials", lambda self: 1 / 0)
    panel.scan()
    assert "Scan failed" in panel._msgs[-1]
    log = tmp_path / "MeasuredLight" / "logs" / "inspector.log"
    assert log.exists() and "ZeroDivisionError" in log.read_text()
