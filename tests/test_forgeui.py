"""forgeui kit tests: tokens, sheet, widgets, 3.7 syntax and dash hygiene.

Runs under .venv-qt (PySide6); skips cleanly where PySide6 is not installed.
"""
import ast
import os
import pathlib
import re
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
KIT = pathlib.Path(REPO) / "forgeui"

QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from forgeui import a11y, compat, qss, tokens, widgets  # noqa: E402
from forgeui.compat import QtCore, QtGui  # noqa: E402


@pytest.fixture(scope="module")
def app():
    inst = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield inst


# (a) tokens ----------------------------------------------------------------------

def test_max_dark_has_all_tokens_and_contrast():
    t = tokens.max_dark()
    names = ("window", "base", "raised", "hover", "text", "muted", "hairline", "accent",
             "accent_hover", "accent_pressed", "on_accent", "error", "warning", "ok",
             "on_semantic")
    assert len(names) == 15
    for n in names:
        v = getattr(t, n)
        assert re.match(r"^#[0-9a-fA-F]{6}$", v), (n, v)
    assert t.accent == tokens.ACCENT == "#5FB89A"
    assert t.ok == t.accent
    assert tokens.contrast(t.accent, t.on_accent) >= 4.5
    assert tokens.contrast(t.text, t.window) >= 4.5
    assert tokens.contrast(t.error, t.on_semantic) >= 4.5
    assert tokens.contrast(t.warning, t.on_semantic) >= 4.5
    assert abs(tokens.contrast("#000000", "#ffffff") - 21.0) < 0.01
    assert tokens.RADIUS == 4 and tokens.SPACE == (4, 8, 12, 16, 24, 32)


# (b) palette derivation (D7) -------------------------------------------------------

def _palette(window, base, text):
    pal = QtGui.QPalette()
    role = lambda n: compat.enum(QtGui.QPalette, "ColorRole", n)
    pal.setColor(role("Window"), QtGui.QColor(window))
    pal.setColor(role("Base"), QtGui.QColor(base))
    pal.setColor(role("WindowText"), QtGui.QColor(text))
    return pal


def test_from_palette_light_and_none_fall_back(app):
    assert tokens.from_palette(None) == tokens.max_dark()
    assert tokens.from_palette(_palette("#efefef", "#ffffff", "#101010")) == tokens.max_dark()


def test_from_palette_dark_derives_but_keeps_accent(app):
    t = tokens.from_palette(_palette("#3c3c3c", "#2a2a2a", "#dddddd"))
    assert t.window == "#3c3c3c" and t.base == "#2a2a2a" and t.text == "#dddddd"
    assert t.raised != t.window and t.hover != t.raised
    assert t.hairline != t.window
    assert t.accent == "#5FB89A" and t.error == "#D06A6A" and t.warning == "#D9A441"


# (c) sheet ---------------------------------------------------------------------------

def test_build_qss_rules():
    sheet = qss.build_qss(tokens.max_dark())
    low = sheet.lower()
    assert "font-family" not in low
    assert "#000000" not in low and "#ffffff" not in low
    assert "#000;" not in low and "#fff;" not in low
    assert "box-shadow" not in low and "gradient" not in low
    radii = re.findall(r"border-radius:\s*([^;]+);", sheet)
    assert radii and all(r.strip() == "4px" for r in radii)
    sizes = re.findall(r"font-size:\s*([^;]+);", sheet)
    assert sizes and all(s.strip().endswith("px") for s in sizes)
    for needle in ('QPushButton[role="primary"]', "QCheckBox::indicator", "QTabBar::tab:selected",
                   'QToolButton[role="tile"]:checked', "QScrollBar:vertical", "QToolTip",
                   "*:focus", 'QFrame[role="dropzone"][dragging="true"]'):
        assert needle in sheet, needle
    assert tokens.ACCENT in sheet


def test_apply_styles_widget_and_is_stable(app):
    w = QtWidgets.QWidget()
    t = qss.apply(w)
    assert t == tokens.max_dark()                   # offscreen palette is light (D7)
    child = QtWidgets.QWidget(w)
    assert qss.apply(child) == t                    # reuses the ancestor's tokens
    assert "font-family" not in w.styleSheet()


def test_focus_ring_keeps_geometry(app):
    w = QtWidgets.QWidget()
    lay = QtWidgets.QVBoxLayout(w)
    pb = widgets.PrimaryButton("Make material")
    sb = widgets.SecondaryButton("Cancel")
    le = QtWidgets.QLineEdit()
    for x in (pb, sb, le):
        lay.addWidget(x)
    qss.apply(w)
    w.show()
    app.processEvents()
    before = [x.sizeHint() for x in (pb, sb, le)]
    assert pb.height() == 44 and sb.height() == 28 and le.height() == 28
    for x in (pb, sb, le):
        x.setFocus()
        app.processEvents()
        x.style().unpolish(x)
        x.style().polish(x)
    after = [x.sizeHint() for x in (pb, sb, le)]
    assert before == after


# (d) DropZone ----------------------------------------------------------------------

def _drop(zone, path):
    mime = QtCore.QMimeData()
    mime.setUrls([QtCore.QUrl.fromLocalFile(str(path))])
    ev = QtGui.QDropEvent(QtCore.QPointF(10, 10), compat.enum(QtCore.Qt, "DropAction", "CopyAction"),
                          mime, compat.enum(QtCore.Qt, "MouseButton", "LeftButton"),
                          compat.enum(QtCore.Qt, "KeyboardModifier", "NoModifier"))
    zone.dropEvent(ev)
    return mime


def test_dropzone_accepts_one_image_only(app, tmp_path):
    png = tmp_path / "oak.png"
    png.write_bytes(b"x")
    psd = tmp_path / "oak.psd"
    psd.write_bytes(b"x")
    zone = widgets.DropZone()
    got = []
    zone.fileChosen.connect(got.append)
    _drop(zone, png)
    assert got == [str(png)]
    _drop(zone, psd)
    assert got == [str(png)]
    assert not zone.is_dragging()
    two = QtCore.QMimeData()
    two.setUrls([QtCore.QUrl.fromLocalFile(str(png)), QtCore.QUrl.fromLocalFile(str(png))])
    assert widgets.DropZone.path_from_mime(two) is None
    web = QtCore.QMimeData()
    web.setUrls([QtCore.QUrl("https://example.com/oak.png")])
    assert widgets.DropZone.path_from_mime(web) is None
    assert widgets.DropZone.EXTS == (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp")


def test_dropzone_browse_and_texts(app):
    zone = widgets.DropZone()
    calls = []
    zone.set_browse(lambda: calls.append(1))
    zone.browse_button.click()
    assert calls == [1]
    assert zone.browse_button.text() == "Browse..."
    zone.set_texts("Drop it", "Small hint")
    assert zone.headline.text() == "Drop it" and zone.hint.text() == "Small hint"
    assert zone.accessibleName() == "Drop it"


# (e) StatusBanner ------------------------------------------------------------------

def test_status_banner_words_and_action(app):
    host = QtWidgets.QWidget()
    lay = QtWidgets.QVBoxLayout(host)
    b = widgets.StatusBanner()
    lay.addWidget(b)
    host.show()
    assert not b.isVisible()
    for kind, word in (("error", "Error"), ("warning", "Warning"), ("ok", "Done"), ("info", "Note")):
        b.show(kind, "Something happened.")
        assert b.isVisible()
        assert b.word() == word and b.chip.text() == word
        assert b.kind() == kind and b.chip.kind() == kind
        assert b.text() == "Something happened."
        assert not b.action_button.isVisible()
    hits = []
    b.show("error", "Best needs a fal key.", "Add key in Settings", lambda: hits.append(1))
    assert b.action_button.isVisible() and b.action_button.text() == "Add key in Settings"
    b.action_button.click()
    assert hits == [1]
    assert b.sentence.wordWrap()
    b.hide()
    assert not b.isVisible()


@pytest.mark.parametrize("sentence", [
    "Fixed 3 things.",
    "Fixed 2 things. 1 needs a manual fix because the texture file could not be found on disk.",
])
@pytest.mark.parametrize("action_text", [None, "Show details"])
def test_status_banner_chip_aligns_with_first_line(app, sentence, action_text):
    host = QtWidgets.QWidget()
    lay = QtWidgets.QVBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    b = widgets.StatusBanner()
    lay.addWidget(b)
    lay.addStretch(1)
    qss.apply(host)
    host.resize(320, 200)
    b.show("warning", sentence, action_text, None)
    host.show()
    app.processEvents()
    c = b.first_line_centres()
    for key, y in c.items():
        assert abs(y - c["chip"]) <= 1, (key, c)
    wraps = b.sentence.height() > b.sentence.fontMetrics().height() * 1.5
    assert wraps == (len(sentence) > 40)
    assert b.chip.geometry().top() >= 4


# (f) MoreOptions ---------------------------------------------------------------------

def test_more_options_toggles(app):
    m = widgets.MoreOptions()
    inner = QtWidgets.QLabel("x")
    m.set_content(inner)
    assert not m.is_expanded() and m.header.text() == "> More options"
    assert inner.isHidden()
    m.header.click()
    assert m.is_expanded() and m.header.text() == "v More options"
    assert not inner.isHidden()
    m.set_expanded(False)
    assert not m.is_expanded()


# (g) TileGrid + SegmentedChoice -----------------------------------------------------

def test_tile_grid_filter_and_current(app):
    g = widgets.TileGrid([("wood_interior", "Wood interior"), ("wood_exterior", "Wood exterior"),
                          ("cork", "Cork")], columns=2)
    assert g.visible_count() == 3
    assert g.set_filter("EXT") == 1
    assert g.visible_keys() == ["wood_exterior"]
    assert g.tile("cork").isHidden() and g.tile("wood_interior").isHidden()
    assert g._grid.getItemPosition(g._grid.indexOf(g.tile("wood_exterior")))[:2] == (0, 0)
    g.set_filter("")
    assert g.visible_count() == 3
    got = []
    g.selected.connect(got.append)
    assert g.set_current("cork")
    assert got == ["cork"] and g.current() == "cork"
    g.tile("wood_interior").click()
    assert got == ["cork", "wood_interior"] and g.current() == "wood_interior"
    assert not g.set_current("nope")
    assert g.tile("cork").height() == 28 or g.tile("cork").minimumHeight() == 28


def test_segmented_choice(app):
    s = widgets.SegmentedChoice([("fast", "Standard", "free, offline"),
                                 ("ultra", "Best", "AI, needs a key")])
    assert s.current() == "fast"
    got = []
    s.changed.connect(got.append)
    s.button("ultra").click()
    assert got == ["ultra"] and s.current() == "ultra"
    assert s.button("ultra").accessibleName() == "Best, AI, needs a key"


def test_misc_widgets(app, tmp_path):
    pb = widgets.PrimaryButton("Make material")
    assert pb.property("role") == "primary" and pb.minimumHeight() == 44 and pb.isDefault()
    assert pb.accessibleName() == "Make material" and pb.toolTip() == "Make material"
    pb.setText("Make another")
    assert pb.accessibleName() == "Make another"
    assert widgets.SecondaryButton("Cancel").minimumHeight() == 28
    assert widgets.GhostButton("Why?").property("role") == "ghost"
    assert widgets.Title("T").property("role") == "title"
    m = widgets.Muted("m")
    assert m.property("role") == "muted" and m.wordWrap()
    assert widgets.Card().property("role") == "card"
    h = widgets.SectionHeader("What is it?")
    h.set_text("Notes")
    assert h.text() == "Notes"
    chip = widgets.SeverityChip("Error", "error")
    assert chip.text() == "Error" and chip.kind() == "error"
    sk = widgets.SkeletonRows(rows=6, tiles=5)
    assert len(sk.bars) == 11 and not sk.is_pulsing()
    sk.set_pulse(True)
    assert sk.is_pulsing()
    sk.set_pulse(False)
    assert not sk.is_pulsing() and all(not b.property("pulse") for b in sk.bars)
    e = widgets.EmptyState("Nothing to fix.", "48 materials checked, all fine.", "Check again")
    assert e.action_button.text() == "Check again"
    assert not widgets.Thumb(None, 64, "Normal").is_made()
    assert widgets.Thumb(None, 64, "Normal").image.text() == "Not made"
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not a png")
    assert not widgets.Thumb(str(bad), 64, "Height").is_made()
    good = tmp_path / "good.png"
    img = QtGui.QImage(8, 8, compat.enum(QtGui.QImage, "Format", "Format_RGB32"))
    img.fill(QtGui.QColor("#808080"))
    assert img.save(str(good))
    assert widgets.Thumb(str(good), 64, "Colour").is_made()


def test_a11y_and_compat(app):
    host = QtWidgets.QWidget()
    a, b = QtWidgets.QLineEdit(host), QtWidgets.QPushButton("Go", host)
    a11y.label(a, "Name", "Material name")
    assert a.accessibleName() == "Name" and a.toolTip() == "Material name"
    a11y.tab_order([a, None, b])
    assert len(a11y.enter_triggers(host, b)) == 2
    assert a11y.esc_triggers(host, lambda: None) is not None
    assert compat.IS_PYSIDE6
    assert compat.QAction is QtGui.QAction
    assert isinstance(compat.font_families(), list) and compat.font_families()
    assert isinstance(compat.fixed_font(), QtGui.QFont)
    assert compat.enum(QtCore.Qt, "AlignmentFlag", "AlignLeft") == QtCore.Qt.AlignmentFlag.AlignLeft
    d = QtWidgets.QDialog()
    QtCore.QTimer.singleShot(0, d.accept)
    assert compat.exec_dialog(d) == 1


# (h) + (i) source hygiene ---------------------------------------------------------

def _kit_files():
    files = sorted(KIT.rglob("*.py"))
    assert len(files) >= 6
    return files


def test_kit_parses_as_python37():
    for p in _kit_files():
        ast.parse(p.read_text(encoding="utf-8"), str(p), feature_version=(3, 7))


def test_kit_has_no_long_dashes():
    for p in _kit_files() + [pathlib.Path(__file__)]:
        src = p.read_text(encoding="utf-8")
        assert chr(0x2014) not in src and chr(0x2013) not in src, p


def test_kit_has_no_numpy_or_pillow():
    for p in _kit_files():
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for n in names:
                assert n.split(".")[0] not in ("numpy", "PIL"), (p, n)


# (z) Return with another button focused -------------------------------------------

def test_enter_triggers_defers_to_a_focused_button(app):
    QtTest = pytest.importorskip("PySide6.QtTest")
    host = QtWidgets.QWidget()
    lay = QtWidgets.QVBoxLayout(host)
    primary = QtWidgets.QPushButton("Go")
    other = QtWidgets.QPushButton("Other")
    edit = QtWidgets.QLineEdit()
    for w in (primary, other, edit):
        lay.addWidget(w)
    counts = {"primary": 0, "other": 0}
    primary.clicked.connect(lambda: counts.__setitem__("primary", counts["primary"] + 1))
    other.clicked.connect(lambda: counts.__setitem__("other", counts["other"] + 1))
    a11y.enter_triggers(host, primary)
    host.show()
    host.activateWindow()
    QtTest.QTest.qWaitForWindowActive(host)
    other.setFocus()
    QtTest.QTest.keyClick(host, QtCore.Qt.Key.Key_Return)
    assert counts == {"primary": 0, "other": 1}
    primary.setFocus()
    QtTest.QTest.keyClick(host, QtCore.Qt.Key.Key_Return)
    assert counts["primary"] == 1 and counts["other"] == 1
    edit.setFocus()
    QtTest.QTest.keyClick(host, QtCore.Qt.Key.Key_Return)
    assert counts["primary"] == 2 and counts["other"] == 1
    host.close()
