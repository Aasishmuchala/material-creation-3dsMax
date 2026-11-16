"""Drive the real PySide6 panel headlessly against the fake MAXScript runtime."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from material_inspector.core import titles  # noqa: E402
from material_inspector.core.inspector import ScanCancelled  # noqa: E402
from material_inspector.max_adapter import ui  # noqa: E402
from tests.fakert import Color, FakeRT, Node  # noqa: E402
from tests.test_scene_and_fixes import vray_scene  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _make(monkeypatch, tmp_path, rt):
    monkeypatch.setenv("MATERIAL_INSPECTOR_CONFIG", str(tmp_path / "inspector.json"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    msgs = []
    monkeypatch.setattr(ui.InspectorPanel, "_notify", lambda self, t: msgs.append(t))
    monkeypatch.setattr(QtWidgets.QMessageBox, "question",
                        lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes)
    p = ui.InspectorPanel(rt)
    p._msgs = msgs
    return p


@pytest.fixture
def panel(app, monkeypatch, tmp_path):
    return _make(monkeypatch, tmp_path, vray_scene())


def test_starts_idle(panel):
    assert panel.state() == "idle"
    assert panel.objectName() == "MaterialInspectorDock"
    assert panel.btn_scan.text() == "Check my scene" and panel.btn_scan.isEnabled()
    assert panel.status.text() == ""


def test_scan_populates_rows(panel):
    panel.chk_pixels.setChecked(False)
    panel.scan()
    assert panel.state() == "results"
    assert len(panel.rows()) >= 3
    assert "will render wrong" in panel.summary_text()
    assert panel.summary_text().endswith("2 materials checked")
    n_fix = sum(f.severity.value == "error" and f.fixable for f in panel.findings)
    assert panel.btn_fix_all.text() == "Fix all %d" % n_fix
    assert {r.finding.material for r in panel.rows()} == {"Oak floor", "Window glass"}
    assert panel.btn_scan.isEnabled()


def test_fix_all_errors_then_rescan_clears_them(panel):
    panel.chk_pixels.setChecked(False)
    panel.scan()
    before = sum(f.severity.value == "error" and f.fixable for f in panel.findings)
    assert before > 0
    panel.fix_all_errors()
    assert panel._msgs and "Applied" in panel._msgs[-1]
    after = sum(f.severity.value == "error" and f.fixable for f in panel.findings)
    assert after < before
    assert panel.state() == "results"
    assert panel.banner.isVisibleTo(panel) and panel.banner.text().startswith("Fixed ")


def test_scan_failure_is_logged_not_raised(panel, monkeypatch, tmp_path):
    monkeypatch.setattr(ui.SceneReader, "materials", lambda self: 1 / 0)
    panel.scan()
    assert "Scan failed" in panel._msgs[-1]
    assert panel.state() == "error"
    assert panel.btn_scan.isEnabled() and not panel._scanning
    log = tmp_path / "MeasuredLight" / "logs" / "inspector.log"
    assert log.exists() and "ZeroDivisionError" in log.read_text()


def test_settings_failure_opens_with_defaults_and_warning(app, monkeypatch, tmp_path):
    """Stress B3: a broken settings loader must not stop the panel opening."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(ui, "load_options", lambda *a: 1 / 0)
    p = ui.InspectorPanel(vray_scene())
    assert p.options.max_side == 1024 and p.config_warnings
    assert "settings problem" in p.status.text()


def test_wrongly_typed_settings_file_opens_with_warning(app, monkeypatch, tmp_path):
    cfg = tmp_path / "inspector.json"; cfg.write_text('{"max_side": "big", "rules": "x"}')
    monkeypatch.setenv("MATERIAL_INSPECTOR_CONFIG", str(cfg))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    p = ui.InspectorPanel(vray_scene())
    assert len(p.config_warnings) == 2 and "2 settings problem" in p.status.text()


def _vray(name, gloss_space):
    bm = Node("Bitmaptexture", name + "_bm", filename="C:/tex/Oak_Glossiness.png", colorspace=gloss_space)
    return Node("VRayMtl", name,
                diffuse=Color(128, 128, 128), reflection_glossiness=0.6, brdf_useRoughness=False,
                brdf_type=3, reflection_metalness=0.0, reflection_ior=1.5, refraction=Color(0, 0, 0),
                refraction_ior=1.6, refraction_fogColor=Color(255, 255, 255), refraction_fogMult=1.0,
                texmap_reflectionGlossiness=bm, texmap_bump=None, texmap_diffuse=None), bm


def test_duplicate_names_fix_the_right_material(app, monkeypatch, tmp_path):
    faulty, faulty_bm = _vray("Oak floor", "sRGB")       # gloss map read as colour (R001)
    clean, clean_bm = _vray("Oak floor", "raw")
    rt = FakeRT([Node("Multimaterial", "M", subs=[faulty, clean])],
                existing_files={"C:/tex/Oak_Glossiness.png"})
    p = _make(monkeypatch, tmp_path, rt)
    p.chk_pixels.setChecked(False)
    p.scan()
    assert [m.name for m in p.materials] == ["Oak floor", "Oak floor"]
    r001 = [f for f in p.findings if f.rule_id == "R001"]
    assert len(r001) == 1 and r001[0].material_index == 0
    p.fix_one(r001[0])
    assert faulty_bm._props["colorspace"] != "sRGB"
    assert clean_bm._props["colorspace"] == "raw"
    assert not any(f.rule_id == "R001" for f in p.findings)


def test_cancel_mid_scan(panel, monkeypatch):
    def fake_inspect(materials, opt=None, progress=None):
        for i in (1, 2):
            if i == 1:
                panel._cancel = True
            if progress(i, 2, "m%d" % i) is False:
                raise ScanCancelled()
        return []
    monkeypatch.setattr(ui, "inspect", fake_inspect)
    panel.scan()
    assert panel.state() == "idle"
    assert panel._msgs == []
    assert panel.banner.isVisibleTo(panel)
    assert panel.banner.text() == "Scan stopped. Nothing was changed."
    assert panel.btn_scan.isEnabled() and not panel._scanning


def test_cancel_is_noop_when_idle(panel):
    panel.cancel()
    assert panel._cancel is False and panel.state() == "idle"


def test_empty_scene_shows_empty_state(app, monkeypatch, tmp_path):
    p = _make(monkeypatch, tmp_path, FakeRT([]))
    p.scan()
    assert p.state() == "empty"
    assert "Nothing to fix" in p.empty_title.text()
    assert p.rows() == []


def test_rows_have_headline_not_rule_id_first(panel):
    panel.chk_pixels.setChecked(False)
    panel.scan()
    assert panel.rows()
    for row in panel.rows():
        f = row.finding
        assert row.headline.text() == titles.headline(f)
        assert not row.headline.text().startswith(f.rule_id)
        assert f.rule_id in row.rule_line.text()
        assert (row.btn_fix is not None) == f.fixable
        if f.severity.value == "info":
            assert row.manual is None                        # notes: nothing on the right
        else:
            assert (row.manual is not None) == (not f.fixable)
        assert row.rule_line.text().endswith(f.rule_id)
        assert not row.is_expanded()
        row.toggle_detail()
        assert row.is_expanded()


def test_note_row_has_no_manual_label_but_keeps_advice(panel, monkeypatch):
    from material_inspector.core.model import Finding, Severity
    note = Finding("M009", Severity.INFO, "(scan)", "Convention unset")
    monkeypatch.setattr(ui, "inspect", lambda *a, **k: [note])
    panel.scan()
    row, = panel.rows()
    assert row.manual is None and row.btn_fix is None
    assert row.rule_line.text() == "Set it in Settings  M009"
    assert row.line2.full_text() == "Whole scene"


def test_manual_count_line_under_fix_all(panel):
    panel.chk_pixels.setChecked(False)
    panel.scan()
    errors = sum(f.severity.value == "error" for f in panel.findings)
    n_fix = sum(f.severity.value == "error" and f.fixable for f in panel.findings)
    assert errors - n_fix == 1                               # R004 missing file has no fix
    assert panel.manual_note.isVisibleTo(panel)
    assert panel.manual_note.text() == "1 needs a manual fix"


def test_only_notes_say_nothing_will_render_wrong(panel, monkeypatch):
    from material_inspector.core.model import Finding, Severity
    note = Finding("M013", Severity.INFO, "Oak floor", "Map looks upscaled", material_index=0)
    monkeypatch.setattr(ui, "inspect", lambda *a, **k: [note])
    panel.scan()
    assert panel.state() == "results"
    assert panel.summary_text().startswith("Nothing will render wrong")
    assert not panel.btn_fix_all.isVisibleTo(panel)
    assert not panel.manual_note.isVisibleTo(panel)


def test_controls_are_labelled_and_short(panel):
    panel.chk_pixels.setChecked(False)
    panel.scan()
    for b in panel.findChildren(QtWidgets.QAbstractButton):
        assert b.accessibleName(), b.text()
        if isinstance(b, QtWidgets.QPushButton):
            assert len(b.text().split()) <= 3, b.text()


def test_no_dashes_in_ui_strings():
    src = open(ui.__file__, encoding="utf-8").read()
    assert chr(0x2014) not in src and chr(0x2013) not in src


def test_enter_on_focused_settings_button_does_not_scan(panel, monkeypatch):
    from PySide6 import QtCore, QtTest
    calls = []
    monkeypatch.setattr(panel, "open_settings", lambda *a: calls.append(1))
    panel.btn_settings.clicked.disconnect()
    panel.btn_settings.clicked.connect(lambda *a: panel.open_settings())
    panel.show()
    panel.activateWindow()
    QtTest.QTest.qWaitForWindowActive(panel)
    panel.btn_settings.setFocus()
    QtTest.QTest.keyClick(panel.btn_settings, QtCore.Qt.Key.Key_Return)
    assert calls == [1]
    assert panel.state() == "idle"
    assert panel.btn_scan.isEnabled()


def test_unfixable_warning_makes_no_fix_promise(panel):
    from material_inspector.core.model import Finding, Severity
    f = Finding(rule_id="R013", severity=Severity.WARNING, material="Glass",
                message="unusual IOR", fix=None)
    row = ui.FindingRow(f)
    text = row.rule_line.text()
    assert "Sets a plausible IOR" not in text
    assert text.endswith("R013")
    note = Finding("M009", Severity.INFO, "(scan)", "Convention unset")
    assert ui.FindingRow(note).rule_line.text() == "Set it in Settings  M009"
