"""MatForge Qt dock: states, QProcess lifecycle (fake generator), cancel, errors, a11y.

Runs under .venv-qt (PySide6); skips cleanly where PySide6 is not installed.
pymxs is mocked (tests/mock_pymxs.py); map generation is tests/fake_generator.py.
"""
import ast
import importlib
import os
import sys
import time
import types

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.dirname(os.path.abspath(__file__))
for _p in (REPO, TESTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

QtWidgets = pytest.importorskip("PySide6.QtWidgets")
from PySide6 import QtCore, QtTest  # noqa: E402

import mock_pymxs  # noqa: E402
from fake_generator import write_png  # noqa: E402

FAKE = os.path.join(TESTS, "fake_generator.py")
NOT_RUNNING = QtCore.QProcess.ProcessState.NotRunning


@pytest.fixture(scope="module")
def app():
    inst = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield inst


@pytest.fixture(scope="module", autouse=True)
def _unload_forge_qt():
    """Leave no maxplugin.forge_qt behind: `from maxplugin import forge_qt` reads the
    package attribute first, which would defeat later tests that block the import via
    sys.modules (test_forge_backend.test_show_falls_back_to_rollout)."""
    yield
    import maxplugin
    maxplugin.__dict__.pop("forge_qt", None)
    sys.modules.pop("maxplugin.forge_qt", None)


def wait_for(cond, timeout_ms=15000):
    end = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < end:
        QtWidgets.QApplication.processEvents()
        if cond():
            return True
        QtTest.QTest.qWait(20)
    QtWidgets.QApplication.processEvents()
    return bool(cond())


@pytest.fixture
def env(app, monkeypatch, tmp_path):
    monkeypatch.setenv("MATFORGE_FAKE_MODE", "ok")
    monkeypatch.setenv("MATFORGE_FAKE_DELAY", "0")
    _builder, rt = mock_pymxs.install(renderer="vray")
    import maxplugin.forge_max as fm
    importlib.reload(fm)
    fm._PYBIN = [sys.executable]
    fm.CLI = fm.FAL = FAKE
    monkeypatch.setattr(fm, "_fal_key", lambda: "fal_fake")
    from maxplugin import forge_qt
    photo = str(tmp_path / "Oak floor.png")
    write_png(photo, 8, 140)
    return types.SimpleNamespace(fm=fm, rt=rt, qt=forge_qt, photo=photo, tmp=tmp_path)


@pytest.fixture
def dock(env):
    d = env.qt.MatForgeDock(rt=env.rt)
    d.resize(400, 700)
    d.show()
    QtWidgets.QApplication.processEvents()
    try:
        yield d
    finally:
        if d._proc.state() != NOT_RUNNING:
            d._proc.kill()
            d._proc.waitForFinished(3000)
        d.close()
        d.deleteLater()
        QtWidgets.QApplication.processEvents()


def _loaded(dock, env):
    assert dock.load_image(env.photo)
    return dock


# ---------- idle / loaded ----------

def test_idle_after_construction(dock):
    assert dock.state() == "idle"
    assert dock.renderer_label() == "V-Ray and Corona found"
    assert not dock.idle_banner.isVisible()
    assert dock.btn_gear.toolTip() == "Settings"


def test_bad_file_stays_idle_with_error(dock, env):
    txt = env.tmp / "notes.txt"
    txt.write_text("hello")
    assert dock.load_image(str(txt)) is False
    assert dock.state() == "idle"
    assert dock.idle_banner.isVisible() and dock.idle_banner.word() == "Error"


def test_load_png_prefills_and_selects_generic(dock, env):
    _loaded(dock, env)
    assert dock.state() == "loaded"
    p = dock.params()
    assert p["name"] == "Oak_floor" and p["cls"] == "generic" and p["img"] == env.photo
    assert p["res"] == "4k" and p["eng"] == "fast" and p["rnd"] == "auto"
    assert p["seamless"] is True and p["assign"] is False and p["metal"] is None
    assert dock.metal_row.isHidden()
    assert dock.selected_label.full_text() == "Selected: Generic dielectric"
    assert dock.tabs.currentIndex() == 0                  # Wood shown first


def test_metal_class_shows_metal_row(dock, env):
    _loaded(dock, env)
    dock.grid_for("metal_brushed").set_current("metal_brushed")
    assert not dock.metal_row.isHidden()
    dock.set_params(metal="gold")
    assert dock.params()["metal"] == "gold"
    assert dock.grid_for("generic").current() is None     # one selection across tabs
    dock.grid_for("wood_interior").set_current("wood_interior")
    assert dock.metal_row.isHidden() and dock.params()["metal"] is None


def test_filter_jumps_to_matching_tab(dock, env):
    _loaded(dock, env)
    dock.filter_edit.setText("terrazzo")
    stone = [g for name, g in dock.grids if name == "Stone"][0]
    assert dock.grids[dock.tabs.currentIndex()][0] == "Stone"
    assert stone.visible_keys() == ["granite"]
    dock.filter_edit.setText("zzzz")
    assert dock.no_match.isVisible()
    dock.filter_edit.setText("")
    assert not dock.no_match.isVisible() and dock.tabs.isVisible()


def test_best_disables_seamless(dock, env):
    _loaded(dock, env)
    dock.quality.set_current("ultra")
    assert not dock.chk_seamless.isEnabled()
    assert dock.chk_seamless.toolTip() == "Best always tiles"
    dock.quality.set_current("fast")
    assert dock.chk_seamless.isEnabled()


def test_change_renderer_before_photo_opens_choice_after(dock, env):
    dock.btn_change_renderer.click()
    assert dock.idle_banner.isVisible() and dock.state() == "idle"
    _loaded(dock, env)
    assert dock.more.is_expanded()


# ---------- the full run ----------

def test_start_runs_to_done(dock, env, monkeypatch):
    monkeypatch.setenv("MATFORGE_FAKE_DELAY", "0.05")
    _loaded(dock, env)
    assert dock.start() is True
    assert dock.state() == "working"
    assert wait_for(lambda: dock.state() == "done"), (dock.state(), dock.error_banner.text())
    phases = dock.phases()
    assert "Reading the photo" in phases and "Making the maps" in phases
    assert phases[-1] == "Wiring the material"
    assert "V-Ray: slot" in dock.slots_label.text()
    thumbs = dock.thumbs.items()
    assert len(thumbs) == 5 and all(t.is_made() for t in thumbs)
    assert [t.caption.text() for t in thumbs] == ["Colour", "Roughness", "Normal",
                                                  "Height", "Metalness"]
    assert any(env.rt.meditMaterials[i].cls == "VRayMtl"
               for i in range(env.rt.meditMaterials.count))
    assert dock.done_title.full_text() == "Oak_floor"
    assert dock.notes_label.isVisible() and "fake warning" in dock.notes_label.text()
    assert dock.btn_assign.isVisible()
    dock.btn_assign.click()
    assert dock.done_banner.text() == "Nothing is selected."
    dock.btn_another.click()
    assert dock.state() == "loaded" and dock.params()["img"] == env.photo


def test_best_without_key_offers_settings(dock, env, monkeypatch):
    monkeypatch.setattr(env.fm, "_fal_key", lambda: None)
    _loaded(dock, env)
    dock.quality.set_current("ultra")
    assert dock.start() is False
    assert dock.state() == "error"
    assert dock.error_banner.word() == "Error"
    assert dock.error_banner.text() == "Best needs a fal key."
    assert dock.error_banner.action_button.text() == "Add key in Settings"


def test_generator_failure(dock, env, monkeypatch):
    monkeypatch.setenv("MATFORGE_FAKE_MODE", "fail")
    _loaded(dock, env)
    assert dock.start()
    assert wait_for(lambda: dock.state() == "error")
    assert "Could not make the maps" in dock.error_banner.text()
    assert "Fake failure: image unreadable" in dock.error_banner.text()
    assert dock.error_banner.action_button.text() == "Show details"


def test_generator_failure_under_best_offers_standard(dock, env, monkeypatch):
    monkeypatch.setenv("MATFORGE_FAKE_MODE", "fail")
    _loaded(dock, env)
    dock.quality.set_current("ultra")
    assert dock.start()
    assert wait_for(lambda: dock.state() == "error")
    assert dock.error_banner.action_button.text() == "Try Standard"


def test_bad_json(dock, env, monkeypatch):
    monkeypatch.setenv("MATFORGE_FAKE_MODE", "badjson")
    _loaded(dock, env)
    assert dock.start()
    assert wait_for(lambda: dock.state() == "error")
    assert "Could not read generator output" in dock.error_banner.text()


def test_failed_to_start(dock, env):
    env.fm._PYBIN = [str(env.tmp / "no_such_python")]
    _loaded(dock, env)
    dock.start()
    assert wait_for(lambda: dock.state() == "error")
    assert dock.error_banner.text() == "No system Python with Pillow and numpy was found."
    assert dock.error_banner.action_button.text() == "Show details"


def _start_hanging(dock, env, monkeypatch):
    monkeypatch.setenv("MATFORGE_FAKE_MODE", "hang")
    _loaded(dock, env)
    assert dock.start()
    # the first entry is the dock's own; the second comes from the child's PROGRESS line
    assert wait_for(lambda: dock.phases().count("Reading the photo") >= 2, 5000)


def test_cancel_returns_to_loaded(dock, env, monkeypatch):
    _start_hanging(dock, env, monkeypatch)
    dock.cancel()
    assert wait_for(lambda: dock.state() == "loaded", 3000)
    assert dock._proc.state() == NOT_RUNNING
    assert dock.loaded_banner.isVisible()
    assert dock.loaded_banner.text() == "Stopped. Nothing was made."


def test_reentrancy_and_restart(dock, env, monkeypatch):
    _start_hanging(dock, env, monkeypatch)
    assert dock.start() is False
    assert not dock.btn_make.isEnabled()
    dock.cancel()
    assert wait_for(lambda: dock.state() == "loaded", 3000)
    assert dock.btn_make.isEnabled()
    assert dock.start() is True
    assert dock.state() == "working"
    dock.cancel()
    assert wait_for(lambda: dock.state() == "loaded", 3000)


def test_escape_cancels_working(dock, env, monkeypatch):
    _start_hanging(dock, env, monkeypatch)
    QtTest.QTest.keyClick(dock.btn_cancel, QtCore.Qt.Key.Key_Escape)
    assert wait_for(lambda: dock.state() == "loaded", 3000)
    assert dock._proc.state() == NOT_RUNNING


def test_timeout_kills_and_offers_retry(dock, env, monkeypatch):
    monkeypatch.setenv("MATFORGE_FAKE_MODE", "hang")
    _loaded(dock, env)
    dock._guard.setInterval(300)
    assert dock.start()
    assert wait_for(lambda: dock.state() == "error", 5000)
    assert dock.error_banner.text() == "This took too long and was stopped."
    assert dock.error_banner.action_button.text() == "Try again"
    assert dock._proc.state() == NOT_RUNNING


def test_set_done_hides_assign_and_shows_miss(dock, env):
    maps = {}
    for k in ("albedo", "roughness"):
        p = str(env.tmp / (k + ".png"))
        write_png(p)
        maps[k] = p
    dock.set_done({"material": "Oak_floor", "slot": 3, "maps": maps, "assigned": True,
                   "materials": [{"renderer": "vray", "slot": 3},
                                 {"renderer": "corona", "slot": 4}],
                   "notes": [], "misses": ["MISS reflection_lockIOR"]})
    assert dock.state() == "done"
    assert dock.slots_label.text() == "V-Ray: slot 3\nCorona: slot 4"
    assert not dock.btn_assign.isVisible()
    assert dock.miss_banner.isVisible() and dock.miss_banner.word() == "Warning"
    assert dock.miss_banner.text() == "Some settings could not be applied"
    assert [t.is_made() for t in dock.thumbs.items()] == [True, True, False, False, False]
    dock.miss_banner.action_button.click()
    assert dock.miss_details.isVisible()


# ---------- settings + show() ----------

def test_settings_sheet(dock, env, monkeypatch):
    import mfconfig
    monkeypatch.setattr(mfconfig, "get_keys_status", lambda: {
        "fal": u"fal_ab…wxyz", "fal_set": True, "omega": "", "omega_set": False,
        "omega_model": "m1"})
    saved = []
    monkeypatch.setattr(mfconfig, "save_keys", lambda **kw: saved.append(kw) or True)
    sheet = dock.open_settings()
    try:
        assert sheet.windowTitle() == "Settings"
        assert sheet.fal_status.text() == "Set: fal_ab...wxyz"
        assert sheet.omega_status.text() == "Not set"
        sheet.fal.setText("fal_new")
        assert sheet.save()
        assert saved == [{"fal_key": "fal_new", "omega_key": None, "omega_model": "m1"}]
        monkeypatch.setattr(env.fm, "chat_reply", lambda q: "Use a rougher map.")
        sheet.ask_edit.setText("how?")
        sheet.ask()
        assert sheet.answer.text() == "Use a rougher map." and sheet.btn_ask.isEnabled()
    finally:
        sheet.close()


def test_show_returns_singleton_dock(env, monkeypatch):
    monkeypatch.setattr(env.qt, "_dock", None)
    d = env.qt.show()
    try:
        assert isinstance(d, env.qt.MatForgeDock) and d.isVisible()
        assert env.qt.show() is d
    finally:
        d.close()
        d.deleteLater()


def test_show_without_qapplication_raises_importerror(env, monkeypatch):
    fake = types.SimpleNamespace(QApplication=types.SimpleNamespace(instance=lambda: None))
    monkeypatch.setattr(env.qt, "QtWidgets", fake)
    with pytest.raises(ImportError) as e:
        env.qt.show()
    assert isinstance(e.value, env.qt.QtUnavailable)


# ---------- hygiene ----------

def _source(env):
    with open(env.qt.__file__, encoding="utf-8") as f:
        return f.read()


def test_source_rules(env):
    src = _source(env)
    assert "QThread" not in src
    assert chr(0x2014) not in src and chr(0x2013) not in src
    ast.parse(src, env.qt.__file__, feature_version=(3, 7))


def test_buttons_short_and_everything_labelled(dock, env):
    _loaded(dock, env)
    dock.more.set_expanded(True)
    sheet = dock.open_settings()
    try:
        for host in (dock, sheet):
            for b in host.findChildren(QtWidgets.QPushButton):
                if b.text():
                    assert len(b.text().split()) <= 3, b.text()
            for cls in (QtWidgets.QAbstractButton, QtWidgets.QLineEdit,
                        QtWidgets.QComboBox):
                for w in host.findChildren(cls):
                    if w.isHidden():          # e.g. an unused banner action
                        continue
                    if w.focusPolicy() != QtCore.Qt.FocusPolicy.NoFocus and \
                            not isinstance(w.parent(), QtWidgets.QComboBox):
                        assert w.accessibleName(), (cls.__name__, w.text()
                                                    if hasattr(w, "text") else w)
    finally:
        sheet.close()


def test_enter_makes_material_on_loaded_page(dock, env):
    _loaded(dock, env)
    dock.activateWindow()
    dock.name_edit.setFocus()
    QtTest.QTest.keyClick(dock.name_edit, QtCore.Qt.Key.Key_Return)
    assert dock.state() == "working"
    assert wait_for(lambda: dock.state() == "done")


def test_enter_on_a_focused_segment_does_not_start(dock, env):
    _loaded(dock, env)
    dock.activateWindow()
    best = dock.quality.button("ultra")
    best.setFocus()
    QtTest.QTest.keyClick(best, QtCore.Qt.Key.Key_Return)
    assert dock.state() == "loaded"
    assert dock.quality.current() == "ultra"


def test_synchronous_failed_to_start_stops_start(dock, env, monkeypatch):
    _loaded(dock, env)
    kind = QtCore.QProcess.ProcessError.FailedToStart
    monkeypatch.setattr(dock._proc, "start", lambda *a, **k: dock._on_proc_error(kind))
    assert dock.start() is False
    assert dock.state() == "error"
    assert not dock._guard.isActive()
    assert dock.btn_make.isEnabled()


def test_no_qapplication_falls_back_to_rollout_in_a_fresh_interpreter():
    """Outside Max (no QApplication) importing the dock raises QtUnavailable, so
    forge_max.show() opens the classic rollout instead of aborting Python."""
    import subprocess
    code = ("import sys; sys.path[:0] = [sys.argv[1], sys.argv[2]]; import mock_pymxs; "
            "mock_pymxs.install(); import maxplugin.forge_max as fm; "
            "fm.show_rollout = lambda: print('ROLLOUT'); fm.show()")
    r = subprocess.run([sys.executable, "-c", code, REPO, TESTS], capture_output=True,
                       text=True, timeout=60,
                       env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
    assert r.returncode == 0, r.stderr
    assert "[MatForge] Qt dock unavailable (no QApplication" in r.stdout
    assert r.stdout.strip().splitlines()[-1] == "ROLLOUT"


def test_tile_area_follows_current_tab(dock, env):
    _loaded(dock, env)
    names = [n for n, _ in dock.grids]

    def stack_height(group):
        dock.tabs.setCurrentIndex(names.index(group))
        for _ in range(3):
            QtWidgets.QApplication.processEvents()
        return dock.tabs.height()

    wood, stone = stack_height("Wood"), stack_height("Stone")
    assert wood < stone
    assert stack_height("Wood") == wood                 # shrinks back, not just grows
    assert dock.tabs.sizeHint().height() < stone


def test_type_picked_in_code_shows_its_tab(dock, env):
    _loaded(dock, env)
    assert dock.tabs.currentIndex() == 0                  # Generic selected, Wood shown
    dock.grid_for("metal_brushed").set_current("metal_brushed")
    assert dock.grids[dock.tabs.currentIndex()][0] == "Metal"
