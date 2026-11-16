"""MatForge dock for 3ds Max: native Qt (PySide6, PySide2 fallback via forgeui.compat).

Three actions for a first-time artist: drop a photo, pick what it is, Make material.
Map generation runs in a QProcess owned by the dock (main-thread event loop, no worker
thread); the finished slot wires the material through forge_max.finish_build on the
main thread, so pymxs is only ever touched there. Importing this module raises
ImportError only when Qt itself is missing, so forge_max.show() can fall back to the
classic MAXScript rollout.
"""
import os
import re
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from forgeui import compat, tokens, qss, a11y, widgets  # noqa: E402  (ImportError = no Qt)
from forgeui.compat import QtCore, QtGui, QtWidgets, enum  # noqa: E402


class QtUnavailable(ImportError):
    """Qt imports but cannot be used here (no QApplication, e.g. outside 3ds Max).
    An ImportError so callers that fall back on ImportError treat both cases alike."""


# A QWidget built without a QApplication aborts the interpreter (a Qt fatal, not an
# exception). Refusing at import time lets forge_max.show()'s `except ImportError`
# open the classic rollout instead; show() repeats the check for late callers.
if QtWidgets.QApplication.instance() is None:
    raise QtUnavailable("no QApplication; MatForge must run inside 3ds Max")

import matphys  # noqa: E402
from core.recipes import grouped_class_choices, wants_metal_picker  # noqa: E402
from maxplugin import inputs  # noqa: E402

TIMEOUT_MS = 1800000                    # 30 min guard, same as the rollout's subprocess timeout
STDERR_TAIL = 200
PROGRESS_RE = re.compile(r"^PROGRESS (\d+)/(\d+) (.+)$")
STATES = ("idle", "loaded", "working", "done", "error")

QUALITY = [("fast", "Standard", "free, offline"), ("ultra", "Best", "AI, needs a key")]
RENDERERS = [("auto", "Auto"), ("vray", "V-Ray"), ("corona", "Corona"), ("both", "Both")]
SIZES = [("2k", "2K"), ("4k", "4K"), ("8k", "8K")]
MAP_TILES = [("albedo", "Colour"), ("roughness", "Roughness"), ("normal", "Normal"),
             ("height", "Height"), ("metalness", "Metalness")]
RENDERER_NAMES = {"vray": "V-Ray", "corona": "Corona"}
DURATION = {"fast": "This takes 10 to 60 seconds", "ultra": "This takes about a minute"}
FIRST_PHASE = "Reading the photo"
WIRING_PHASE = "Wiring the material"
NO_PYTHON = "No system Python with Pillow and numpy was found."
TIMED_OUT = "This took too long and was stopped."
STOPPED = "Stopped. Nothing was made."


def _fm():
    """forge_max, imported lazily (it pulls in pymxs; tests reload it under a mock)."""
    from maxplugin import forge_max
    return forge_max


def _align(*names):
    flags = enum(QtCore.Qt, "AlignmentFlag", names[0])
    for n in names[1:]:
        flags = flags | enum(QtCore.Qt, "AlignmentFlag", n)
    return flags


def _policy(name):
    return enum(QtWidgets.QSizePolicy, "Policy", name)


def _short_label(label):
    """Tile text that fits two columns at 320 px: "Wood (interior / lacquered)" -> "Wood
    interior", "Stone / paver / brick" -> "Stone". The full label stays as the tooltip
    and is what the filter matches."""
    base, _, inner = label.partition("(")
    base = base.strip()
    if "/" in base:
        return base.split("/")[0].strip()
    if inner and " " not in base:
        word = re.split(r"[ /+)]", inner.strip())[0]
        return "%s %s" % (base, word.lower()) if word else base
    return base


def _sentence(text):
    """text as one sentence ending in a single period."""
    text = (text or "").strip()
    return text if text.endswith((".", "!", "?")) else text + "."


def _gear_icon(colour):
    """Small gear drawn with QPainter (no image files, no font glyph)."""
    pix = QtGui.QPixmap(40, 40)
    pix.fill(QtGui.QColor(0, 0, 0, 0))
    p = QtGui.QPainter(pix)
    p.setRenderHint(enum(QtGui.QPainter, "RenderHint", "Antialiasing"), True)
    body = QtGui.QPainterPath()
    body.addEllipse(QtCore.QPointF(20, 20), 11, 11)
    for i in range(8):
        tooth = QtGui.QPainterPath()
        tooth.addRoundedRect(QtCore.QRectF(17, 4, 6, 9), 1.5, 1.5)
        tr = QtGui.QTransform()
        tr.translate(20, 20)
        tr.rotate(45 * i)
        tr.translate(-20, -20)
        body = body.united(tr.map(tooth))
    hole = QtGui.QPainterPath()
    hole.addEllipse(QtCore.QPointF(20, 20), 4.5, 4.5)
    p.fillPath(body.subtracted(hole), QtGui.QColor(colour))
    p.end()
    return QtGui.QIcon(pix)


class _Elided(QtWidgets.QLabel):
    """One-line label that elides instead of forcing the dock wider."""

    def __init__(self, text="", role=None, parent=None):
        super(_Elided, self).__init__(parent)
        self._full = ""
        if role:
            self.setProperty("role", role)
        self.setSizePolicy(_policy("Ignored"), _policy("Preferred"))
        self.setText(text)

    def setText(self, text):
        self._full = text or ""
        self.setAccessibleName(self._full)
        self._refresh()

    def full_text(self):
        return self._full

    def _refresh(self):
        fm = self.fontMetrics()
        shown = fm.elidedText(self._full, enum(QtCore.Qt, "TextElideMode", "ElideRight"),
                              max(16, self.width()))
        super(_Elided, self).setText(shown)
        self.setToolTip(self._full if shown != self._full else "")

    def minimumSizeHint(self):
        return QtCore.QSize(16, super(_Elided, self).minimumSizeHint().height())

    def resizeEvent(self, event):
        super(_Elided, self).resizeEvent(event)
        self._refresh()

    def changeEvent(self, event):
        super(_Elided, self).changeEvent(event)
        if event.type() in (enum(QtCore.QEvent, "Type", "FontChange"),
                            enum(QtCore.QEvent, "Type", "StyleChange")):
            self._refresh()


class _FitTabs(QtWidgets.QTabWidget):
    """QTabWidget whose height follows the CURRENT page. The stock size hints take the
    tallest page (size policies are not consulted), which left empty rows under short
    groups such as Wood."""

    def _fit(self, base, page_hint):
        w = self.currentWidget()
        if w is None:
            return base
        bar = self.tabBar().sizeHint().height() if self.tabBar().isVisible() else 0
        return QtCore.QSize(base.width(), bar + page_hint(w).height() + 2)   # + pane line

    def sizeHint(self):
        return self._fit(super(_FitTabs, self).sizeHint(), lambda w: w.sizeHint())

    def minimumSizeHint(self):
        return self._fit(super(_FitTabs, self).minimumSizeHint(),
                         lambda w: w.minimumSizeHint())


class _Reflow(QtWidgets.QWidget):
    """Fixed-size items in a grid that drops to fewer columns when the dock is narrow,
    so five 64 px thumbnails never clip at 320 px."""

    def __init__(self, item_w, parent=None):
        super(_Reflow, self).__init__(parent)
        self._item_w = item_w
        self._items = []
        self._cols = 0
        self._grid = QtWidgets.QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(8)
        self._grid.setVerticalSpacing(8)
        self.setMinimumWidth(item_w)
        self.setSizePolicy(_policy("Preferred"), _policy("Fixed"))

    def set_items(self, items):
        for w in self._items:
            self._grid.removeWidget(w)
            w.setParent(None)
            w.deleteLater()
        self._items = list(items)
        for w in self._items:
            w.setParent(self)
        self._cols = 0
        self._relayout(self.width())

    def items(self):
        return list(self._items)

    def _relayout(self, width):
        cols = max(1, min(len(self._items) or 1, (max(width, 0) + 8) // (self._item_w + 8)))
        if cols == self._cols:
            return
        self._cols = cols
        for w in self._items:
            self._grid.removeWidget(w)
        for i, w in enumerate(self._items):
            self._grid.addWidget(w, i // cols, i % cols, _align("AlignLeft", "AlignTop"))
        for c in range(len(self._items) + 1):
            self._grid.setColumnStretch(c, 0)
        self._grid.setColumnStretch(cols, 1)
        self.updateGeometry()

    def resizeEvent(self, event):
        super(_Reflow, self).resizeEvent(event)
        self._relayout(event.size().width())


def _page(scroll=False):
    """(outer widget for the stack, inner layout) with 16 px margins."""
    inner = QtWidgets.QWidget()
    lay = QtWidgets.QVBoxLayout(inner)
    lay.setContentsMargins(16, 16, 16, 16)
    lay.setSpacing(12)
    if not scroll:
        return inner, inner, lay
    area = QtWidgets.QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(enum(QtWidgets.QFrame, "Shape", "NoFrame"))
    area.setHorizontalScrollBarPolicy(enum(QtCore.Qt, "ScrollBarPolicy", "ScrollBarAlwaysOff"))
    area.setWidget(inner)
    return area, inner, lay


def _row(*items, **kw):
    lay = QtWidgets.QHBoxLayout()
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(kw.get("spacing", 8))
    for it in items:
        if it is None:
            lay.addStretch(1)
        elif isinstance(it, QtWidgets.QLayout):
            lay.addLayout(it)
        else:
            lay.addWidget(it)
    return lay


class _SettingsSheet(QtWidgets.QDialog):
    """Keys, the help question field and the classic rollout escape hatch."""

    def __init__(self, parent=None):
        super(_SettingsSheet, self).__init__(parent)
        self.setObjectName("MatForgeSettings")
        self.setWindowTitle("Settings")
        self.setMinimumWidth(340)
        qss.apply(self)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(8)
        lay.addWidget(widgets.Title("Settings"))

        self.fal, self.fal_status = self._secret_field(
            lay, "fal key", "Paste a fal key to set or replace it")
        self.omega, self.omega_status = self._secret_field(
            lay, "omega key (optional)", "Paste an omega key to set or replace it")
        lay.addWidget(QtWidgets.QLabel("omega model"))
        self.model = QtWidgets.QLineEdit()
        a11y.label(self.model, "omega model", "Model name used for questions")
        lay.addWidget(self.model)

        self.banner = widgets.StatusBanner()
        lay.addWidget(self.banner)
        self.btn_save = widgets.PrimaryButton("Save")
        a11y.label(self.btn_save, "Save", "Save the keys on this computer")
        self.btn_save.clicked.connect(self.save)
        self.btn_close = widgets.SecondaryButton("Close")
        a11y.label(self.btn_close, "Close", "Close settings")
        self.btn_close.clicked.connect(self.reject)
        self.btn_close.setMinimumHeight(widgets.PRIMARY_H)
        lay.addLayout(_row(self.btn_save, self.btn_close))

        lay.addSpacing(8)
        lay.addWidget(widgets.SectionHeader("Ask a question"))
        self.ask_edit = QtWidgets.QLineEdit()
        self.ask_edit.setPlaceholderText("How do I make wood look older?")
        a11y.label(self.ask_edit, "Ask a question", "Ask about MatForge or materials")
        self.btn_ask = widgets.SecondaryButton("Ask")
        a11y.label(self.btn_ask, "Ask", "Send the question")
        self.btn_ask.clicked.connect(self.ask)
        lay.addLayout(_row(self.ask_edit, self.btn_ask))
        self.answer = widgets.Muted("")
        self.answer.setTextInteractionFlags(
            enum(QtCore.Qt, "TextInteractionFlag", "TextSelectableByMouse"))
        self.answer.setVisible(False)
        lay.addWidget(self.answer)

        lay.addStretch(1)
        self.btn_rollout = widgets.GhostButton("Open classic rollout")
        a11y.label(self.btn_rollout, "Open classic rollout",
                   "Open the old MAXScript MatForge window")
        self.btn_rollout.clicked.connect(self.open_rollout)
        lay.addWidget(self.btn_rollout, 0, _align("AlignLeft"))

        a11y.tab_order([self.fal, self.omega, self.model, self.btn_save, self.btn_close,
                        self.ask_edit, self.btn_ask, self.btn_rollout])
        self.refresh()

    def _secret_field(self, lay, title, tip):
        status = QtWidgets.QLabel("")
        status.setProperty("role", "muted")
        lay.addLayout(_row(QtWidgets.QLabel(title), None, status))
        edit = QtWidgets.QLineEdit()
        edit.setEchoMode(enum(QtWidgets.QLineEdit, "EchoMode", "Password"))
        edit.setPlaceholderText("Paste a new key")
        a11y.label(edit, title, tip)
        lay.addWidget(edit)
        return edit, status

    @staticmethod
    def _status(st, key):
        if not st.get(key + "_set"):
            return "Not set"
        return "Set: " + (st.get(key) or "set").replace(u"…", "...")

    def refresh(self):
        try:
            import mfconfig
            st = mfconfig.get_keys_status()
        except Exception:
            st = {}
        self.fal_status.setText(self._status(st, "fal"))
        self.omega_status.setText(self._status(st, "omega"))
        if not self.model.text():
            self.model.setText(st.get("omega_model") or "")

    def save(self):
        try:
            import mfconfig
            mfconfig.save_keys(fal_key=self.fal.text().strip() or None,
                               omega_key=self.omega.text().strip() or None,
                               omega_model=self.model.text().strip() or None)
        except Exception as e:
            self.banner.show("error", _sentence("Could not save the keys: %s" % e))
            return False
        self.fal.clear()
        self.omega.clear()
        self.refresh()
        self.banner.show("ok", "Saved.")
        return True

    def ask(self):
        q = self.ask_edit.text().strip()
        if not q:
            return
        self.btn_ask.setEnabled(False)
        self.answer.setText("Thinking...")
        self.answer.setVisible(True)
        QtWidgets.QApplication.processEvents()
        try:
            reply = _fm().chat_reply(q)
        except Exception as e:
            reply = "Chat unavailable: %s" % e
        self.answer.setText(str(reply))
        self.btn_ask.setEnabled(True)

    def open_rollout(self):
        try:
            _fm().show_rollout()
        except Exception as e:
            self.banner.show("error", _sentence("Could not open the classic rollout: %s" % e))
            return False
        return True

    def keyPressEvent(self, event):
        if event.key() in (enum(QtCore.Qt, "Key", "Key_Return"),
                           enum(QtCore.Qt, "Key", "Key_Enter")) and self.ask_edit.hasFocus():
            self.ask()
            event.accept()
            return
        super(_SettingsSheet, self).keyPressEvent(event)


class MatForgeDock(QtWidgets.QDockWidget):
    """The MatForge panel. Pages: idle, loaded, working, done, error."""

    def __init__(self, rt=None, parent=None):
        super(MatForgeDock, self).__init__(parent)
        self._rt = rt
        self._img = None
        self._auto_name = ""
        self._cls = "generic"
        self._cmd = None
        self._eng = "fast"
        self._result = None
        self._phase = ""
        self._phase_log = []
        self._stdout = b""
        self._stderr_buf = b""
        self._stderr_tail = []
        self._cancelled = False
        self._timed_out = False
        self._pending_renderer = False
        self._settings = None

        self.setObjectName("MatForgeDock")
        self.setWindowTitle("MatForge")
        self.setMinimumWidth(320)
        self.setAllowedAreas(enum(QtCore.Qt, "DockWidgetArea", "LeftDockWidgetArea")
                             | enum(QtCore.Qt, "DockWidgetArea", "RightDockWidgetArea"))
        self._tokens = qss.apply(self)
        a11y.label(self, "MatForge", "")

        self._stack = QtWidgets.QStackedWidget()
        self._pages = {}
        self._build_idle()
        self._build_loaded()
        self._build_working()
        self._build_done()
        self._build_error()
        self.setWidget(self._stack)

        self._proc = QtCore.QProcess(self)
        self._proc.setProcessChannelMode(
            enum(QtCore.QProcess, "ProcessChannelMode", "SeparateChannels"))
        self._proc.setWorkingDirectory(_fm()._REPO)
        self._proc.readyReadStandardError.connect(self._on_stderr)
        self._proc.readyReadStandardOutput.connect(self._on_stdout)
        self._proc.finished.connect(self._on_finished)
        self._proc.errorOccurred.connect(self._on_proc_error)
        self._guard = QtCore.QTimer(self)
        self._guard.setSingleShot(True)
        self._guard.setInterval(TIMEOUT_MS)
        self._guard.timeout.connect(self._on_timeout)

        self._show_page("idle")
        self.drop.browse_button.setFocus()

    # -- pages -----------------------------------------------------------------------

    def _add_page(self, key, outer):
        self._pages[key] = outer
        self._stack.addWidget(outer)

    def _build_idle(self):
        outer, inner, lay = _page()
        self.idle_page = inner
        key, label = _fm().renderer_status()
        self.renderer_chip = widgets.SeverityChip(label, "info" if key else "warning")
        a11y.label(self.renderer_chip, label, "Renderers MatForge can build for")
        self.btn_change_renderer = widgets.GhostButton("Change")
        a11y.label(self.btn_change_renderer, "Change renderer",
                   "Choose which renderer gets the material")
        self.btn_change_renderer.clicked.connect(self._on_change_renderer)
        self.btn_gear = QtWidgets.QToolButton()
        self.btn_gear.setIcon(_gear_icon(self._tokens.muted))
        self.btn_gear.setIconSize(QtCore.QSize(20, 20))
        self.btn_gear.setFixedSize(28, 28)
        self.btn_gear.setStyleSheet("QToolButton, QToolButton:focus { padding: 0px; }")
        self.btn_gear.setCursor(QtGui.QCursor(enum(QtCore.Qt, "CursorShape",
                                                   "PointingHandCursor")))
        a11y.label(self.btn_gear, "Settings")
        self.btn_gear.clicked.connect(self.open_settings)
        head = _row(self.renderer_chip, self.btn_change_renderer, None, self.btn_gear)
        lay.addLayout(head)
        self.idle_banner = widgets.StatusBanner()
        lay.addWidget(self.idle_banner)
        self.drop = widgets.DropZone("Drop a photo of the material here",
                                     "JPG, PNG, TIFF, BMP or WebP, up to 64 MB")
        self.drop.set_browse(self.browse)
        self.drop.fileChosen.connect(self.load_image)
        lay.addWidget(self.drop, 1)
        a11y.tab_order([self.btn_change_renderer, self.btn_gear, self.drop.browse_button])
        self._add_page("idle", outer)

    def _build_loaded(self):
        outer, inner, lay = _page(scroll=True)
        self.loaded_page = inner
        self.loaded_banner = widgets.StatusBanner()
        lay.addWidget(self.loaded_banner)

        self.thumb = QtWidgets.QLabel()
        self.thumb.setProperty("role", "thumb")
        self.thumb.setFixedSize(96, 96)
        self.thumb.setAlignment(_align("AlignCenter"))
        a11y.label(self.thumb, "Photo", "")
        name_lbl = QtWidgets.QLabel("Name")
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setValidator(QtGui.QRegularExpressionValidator(
            compat.QRegularExpression("[A-Za-z0-9_]{0,48}"), self.name_edit))
        self.name_edit.setPlaceholderText("MatForge_Material")
        a11y.label(self.name_edit, "Name", "Material name: letters, digits and _")
        self.btn_change_photo = widgets.GhostButton("Change photo")
        a11y.label(self.btn_change_photo, "Change photo", "Pick a different photo")
        self.btn_change_photo.clicked.connect(self._on_change_photo)
        right = QtWidgets.QVBoxLayout()
        right.setSpacing(4)
        right.addWidget(name_lbl)
        right.addWidget(self.name_edit)
        right.addWidget(self.btn_change_photo, 0, _align("AlignLeft"))
        right.addStretch(1)
        top = _row(self.thumb, right, spacing=12)
        top.setStretch(1, 1)
        lay.addLayout(top)

        what = QtWidgets.QLabel("What is it?")
        what.setProperty("role", "section")
        self.filter_edit = QtWidgets.QLineEdit()
        self.filter_edit.setPlaceholderText("Filter types")
        self.filter_edit.setMaximumWidth(160)
        self.filter_edit.setClearButtonEnabled(True)
        a11y.label(self.filter_edit, "Filter types", "Type to narrow the list of types")
        self.filter_edit.textChanged.connect(self._on_filter)
        lay.addLayout(_row(what, None, self.filter_edit))
        self.selected_label = _Elided("", "muted")
        lay.addWidget(self.selected_label)

        self.tabs = _FitTabs()
        self.tabs.setUsesScrollButtons(False)
        self._tab_pad = None
        self._tab_avail = None
        self.tabs.tabBar().setElideMode(enum(QtCore.Qt, "TextElideMode", "ElideNone"))
        a11y.label(self.tabs, "Material groups", "Groups of material types")
        self.grids = []
        for group, items in grouped_class_choices():
            grid = widgets.TileGrid(items, columns=2)
            for k, full in items:
                tile = grid.tile(k)
                tile.setText(_short_label(full))
                a11y.label(tile, full)
            grid.selected.connect(lambda k, g=grid: self._on_tile(g, k))
            holder = QtWidgets.QWidget()
            hl = QtWidgets.QVBoxLayout(holder)
            hl.setContentsMargins(0, 8, 0, 0)
            hl.addWidget(grid)
            hl.addStretch(1)
            self.tabs.addTab(holder, group)
            self.grids.append((group, grid))
        self.tabs.currentChanged.connect(self._fit_tab)
        self._fit_tab(0)
        lay.addWidget(self.tabs)
        self.no_match = widgets.Muted("No type matches. Clear the filter to see all.")
        self.no_match.setVisible(False)
        lay.addWidget(self.no_match)

        q_lbl = QtWidgets.QLabel("Quality")
        self.quality = widgets.SegmentedChoice(QUALITY)
        a11y.label(self.quality, "Quality", "Standard is free and offline; Best uses AI")
        self.quality.changed.connect(self._on_quality)
        lay.addLayout(_row(q_lbl, self.quality, spacing=12))

        self.btn_make = widgets.PrimaryButton("Make material")
        a11y.label(self.btn_make, "Make material", "Make the maps and the material (Enter)")
        self.btn_make.clicked.connect(self.start)
        lay.addWidget(self.btn_make)

        self.more = widgets.MoreOptions("More options")
        opts = QtWidgets.QWidget()
        ol = QtWidgets.QVBoxLayout(opts)
        ol.setContentsMargins(0, 0, 0, 0)
        ol.setSpacing(8)
        self.renderer_combo = self._combo(RENDERERS, "Renderer",
                                          "Auto uses the active renderer")
        self.metal_combo = self._combo(
            [(None, "From the photo")] + list(matphys.metal_choices()), "Metal",
            "Which real metal this is")
        self.size_combo = self._combo(SIZES, "Size", "Map size in pixels")
        self.size_combo.setCurrentIndex(1)
        self.renderer_row = self._option_row(ol, "Renderer", self.renderer_combo)
        self.metal_row = self._option_row(ol, "Metal", self.metal_combo)
        self.size_row = self._option_row(ol, "Size", self.size_combo)
        self.chk_seamless = QtWidgets.QCheckBox("Make it tile seamlessly")
        self.chk_seamless.setChecked(True)
        a11y.label(self.chk_seamless, "Make it tile seamlessly", "Hide the seams when it repeats")
        self.chk_assign = QtWidgets.QCheckBox("Put on selected objects")
        a11y.label(self.chk_assign, "Put on selected objects",
                   "Apply the new material to the current selection")
        self.chk_slate = QtWidgets.QCheckBox("Open in Slate")
        a11y.label(self.chk_slate, "Open in Slate", "Show the node wiring in Slate")
        for c in (self.chk_seamless, self.chk_assign, self.chk_slate):
            c.setMinimumHeight(widgets.CONTROL_H)
            ol.addWidget(c)
        self.more.set_content(opts)
        self.more.setMinimumHeight(0)       # let the expanded content set the height
        lay.addWidget(self.more)
        lay.addStretch(1)

        self.metal_row.setVisible(False)
        self._building = True                   # default stays Generic, Wood tab shown first
        self.grid_for("generic").set_current("generic")
        self._building = False
        tiles = []
        for _, g in self.grids:
            tiles.extend(g.tile(k) for k in g.keys())
        a11y.tab_order([self.name_edit, self.btn_change_photo, self.filter_edit,
                        self.tabs.tabBar()] + tiles +
                       [self.quality.button("fast"), self.quality.button("ultra"),
                        self.btn_make, self.more.header, self.renderer_combo,
                        self.metal_combo, self.size_combo, self.chk_seamless,
                        self.chk_assign, self.chk_slate])
        a11y.enter_triggers(self.loaded_page, self.btn_make)
        self._add_page("loaded", outer)

    def _fit_tab(self, index):
        """Size the tab area to the current group only (no empty rows under short groups)."""
        for i in range(self.tabs.count()):
            pol = _policy("Preferred") if i == index else _policy("Ignored")
            self.tabs.widget(i).setSizePolicy(_policy("Preferred"), pol)
        self.tabs.updateGeometry()

    def _combo(self, items, name, tip):
        cb = QtWidgets.QComboBox()
        for key, text in items:
            cb.addItem(text, key)
        a11y.label(cb, name, tip)
        return cb

    def _option_row(self, lay, title, combo):
        row = QtWidgets.QWidget()
        rl = QtWidgets.QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(12)
        lbl = QtWidgets.QLabel(title)
        lbl.setFixedWidth(64)
        rl.addWidget(lbl)
        rl.addWidget(combo, 1)
        lay.addWidget(row)
        return row

    def _build_working(self):
        outer, inner, lay = _page()
        self.working_page = inner
        self.phase_title = widgets.Title(FIRST_PHASE)
        self.phase_title.setWordWrap(False)
        self.duration_label = QtWidgets.QLabel(DURATION["fast"])
        lay.addWidget(self.phase_title)
        lay.addWidget(self.duration_label)
        lay.addSpacing(4)
        lay.addWidget(widgets.SkeletonRows(rows=1, tiles=0))
        self.skeleton_tiles = _Reflow(64)
        sk = []
        for _ in MAP_TILES:
            f = QtWidgets.QFrame()
            f.setProperty("role", "skeleton")
            f.setFixedSize(64, 64)
            sk.append(f)
        self.skeleton_tiles.set_items(sk)
        lay.addWidget(self.skeleton_tiles)
        self.btn_cancel = widgets.SecondaryButton("Cancel")
        a11y.label(self.btn_cancel, "Cancel", "Stop making this material (Esc)")
        self.btn_cancel.setMinimumWidth(120)
        self.btn_cancel.clicked.connect(self.cancel)
        lay.addLayout(_row(None, self.btn_cancel, None))
        lay.addStretch(1)                   # actions sit right under the content
        a11y.tab_order([self.btn_cancel])
        a11y.esc_triggers(self.working_page, self.cancel)
        self._add_page("working", outer)

    def _build_done(self):
        outer, inner, lay = _page(scroll=True)
        self.done_page = inner
        self.done_chip = widgets.SeverityChip("Done", "ok")
        self.done_title = _Elided("", "title")
        lay.addLayout(_row(self.done_chip, self.done_title))
        self.slots_label = QtWidgets.QLabel("")
        a11y.label(self.slots_label, "Material Editor slots", "")
        lay.addWidget(self.slots_label)
        self.miss_banner = widgets.StatusBanner()
        lay.addWidget(self.miss_banner)
        self.miss_details = self._details_box()
        lay.addWidget(self.miss_details)
        self.done_banner = widgets.StatusBanner()
        lay.addWidget(self.done_banner)
        self.thumbs = _Reflow(64)
        lay.addWidget(self.thumbs)
        self.notes_label = widgets.Muted("")
        self.notes_label.setVisible(False)
        lay.addWidget(self.notes_label)
        self.btn_assign = widgets.SecondaryButton("Put on selected")
        a11y.label(self.btn_assign, "Put on selected objects",
                   "Apply the material to the selected objects")
        self.btn_assign.clicked.connect(self._on_assign)
        self.btn_slate = widgets.SecondaryButton("Open in Slate")
        a11y.label(self.btn_slate, "Open in Slate", "Show the node wiring in Slate")
        self.btn_slate.clicked.connect(self._on_slate)
        post = _row(self.btn_assign, self.btn_slate)
        post.setStretch(0, 1)
        post.setStretch(1, 1)
        lay.addLayout(post)
        self.btn_another = widgets.PrimaryButton("Make another")
        a11y.label(self.btn_another, "Make another", "Back to the photo and settings")
        self.btn_another.clicked.connect(self.set_state_loaded)
        lay.addWidget(self.btn_another)
        lay.addStretch(1)
        a11y.tab_order([self.miss_banner.action_button, self.btn_assign, self.btn_slate,
                        self.btn_another])
        self._add_page("done", outer)

    def _details_box(self):
        box = QtWidgets.QPlainTextEdit()
        box.setReadOnly(True)
        box.setFont(compat.fixed_font())
        box.setMaximumHeight(160)
        box.setVisible(False)
        a11y.label(box, "Details", "")
        return box

    def _build_error(self):
        outer, inner, lay = _page()
        self.error_page = inner
        self.error_banner = widgets.StatusBanner()
        lay.addWidget(self.error_banner)
        self.error_details = self._details_box()
        lay.addWidget(self.error_details)
        self.btn_back = widgets.SecondaryButton("Back")
        a11y.label(self.btn_back, "Back", "Back to the photo and settings")
        self.btn_back.clicked.connect(self._on_back)
        lay.addWidget(self.btn_back)
        lay.addStretch(1)
        a11y.tab_order([self.error_banner.action_button, self.btn_back])
        self._add_page("error", outer)

    # -- public API ------------------------------------------------------------------

    def state(self):
        w = self._stack.currentWidget()
        for k, v in self._pages.items():
            if v is w:
                return k
        return "idle"

    def renderer_label(self):
        return self.renderer_chip.text()

    def grid_for(self, key):
        for _, g in self.grids:
            if key in g.keys():
                return g
        return None

    def load_image(self, path):
        problem = inputs.image_problem(path)
        if problem:
            self._show_page("idle")
            self.idle_banner.show("error", problem)
            return False
        self.idle_banner.hide()
        self._img = path
        pix = QtGui.QPixmap(path)
        if pix.isNull():
            self.thumb.setText("Photo")
        else:
            self.thumb.setPixmap(pix.scaled(
                96, 96, enum(QtCore.Qt, "AspectRatioMode", "KeepAspectRatio"),
                enum(QtCore.Qt, "TransformationMode", "SmoothTransformation")))
        a11y.label(self.thumb, "Photo: " + os.path.basename(path), path)
        stem = os.path.splitext(os.path.basename(path))[0]
        name = inputs.safe_name(stem)
        if not self.name_edit.text() or self.name_edit.text() == self._auto_name:
            self.name_edit.setText(name)
        self._auto_name = name
        self.set_state_loaded()
        if self._pending_renderer:
            self._pending_renderer = False
            self._open_renderer_choice()
        return True

    def params(self):
        return {"img": self._img, "name": self.name_edit.text().strip(), "cls": self._cls,
                "res": self.size_combo.currentData(), "eng": self.quality.current(),
                "rnd": self.renderer_combo.currentData(),
                "metal": self.metal_combo.currentData() if wants_metal_picker(self._cls)
                else None,
                "assign": self.chk_assign.isChecked(), "slate": self.chk_slate.isChecked(),
                "seamless": self.chk_seamless.isChecked()}

    def set_params(self, **kw):
        if kw.get("img"):
            self.load_image(kw["img"])
        if "name" in kw:
            self.name_edit.setText(kw["name"] or "")
        if kw.get("cls"):
            g = self.grid_for(kw["cls"])
            if g is not None:
                g.set_current(kw["cls"])
        for key, combo in (("res", self.size_combo), ("rnd", self.renderer_combo),
                           ("metal", self.metal_combo)):
            if key in kw:
                i = combo.findData(kw[key])
                if i >= 0:
                    combo.setCurrentIndex(i)
        if kw.get("eng"):
            self.quality.set_current(kw["eng"])
        for key, chk in (("assign", self.chk_assign), ("slate", self.chk_slate),
                         ("seamless", self.chk_seamless)):
            if key in kw:
                chk.setChecked(bool(kw[key]))

    def is_running(self):
        return self._proc.state() != enum(QtCore.QProcess, "ProcessState", "NotRunning")

    def start(self):
        if self.is_running():
            return False
        fm = _fm()
        p = self.params()
        cmd = fm.build_command(p["img"], p["name"], p["cls"], p["res"], p["eng"],
                               p["seamless"], p["rnd"], p["metal"], progress=True)
        if not cmd["ok"]:
            text = cmd["error"] or "Could not start."
            if "fal key" in text:
                self.set_error("Best needs a fal key.", "Add key in Settings",
                               self.open_settings)
            else:
                self.set_error(_sentence(text))
            return False
        self._cmd = cmd
        self._eng = cmd["engine"]
        self._args = p
        self._stdout = b""
        self._stderr_buf = b""
        self._stderr_tail = []
        self._phase_log = []
        self._cancelled = False
        self._timed_out = False
        self.duration_label.setText(DURATION.get(self._eng, DURATION["fast"]))
        self.set_phase(FIRST_PHASE)
        self._show_page("working")
        env = QtCore.QProcessEnvironment.systemEnvironment()
        if self._eng == "ultra" and cmd["env"].get("FAL_KEY"):
            env.insert("FAL_KEY", cmd["env"]["FAL_KEY"])
        self._proc.setProcessEnvironment(env)
        argv = cmd["argv"]
        self._proc.start(argv[0], argv[1:])
        if self.state() == "error":         # FailedToStart can fire synchronously inside start()
            return False
        self._guard.start()
        self.btn_make.setEnabled(False)
        self.btn_cancel.setFocus()
        return True

    def cancel(self):
        if not self.is_running():
            return
        self._cancelled = True
        self._proc.kill()
        self._proc.waitForFinished(3000)     # finished -> _on_finished runs here

    def set_phase(self, text):
        self._phase = text
        self._phase_log.append(text)
        self.phase_title.setText(text)
        self.working_page.setAccessibleName(text)

    def phase(self):
        return self._phase

    def phases(self):
        return list(self._phase_log)

    def set_done(self, result):
        self._result = result
        self.done_title.setText(result.get("material") or "Material")
        lines = []
        for m in result.get("materials") or []:
            lines.append("%s: slot %s" % (RENDERER_NAMES.get(m.get("renderer"),
                                                             m.get("renderer")), m.get("slot")))
        if not lines and result.get("slot"):
            lines.append("Slot %s" % result["slot"])
        self.slots_label.setText("\n".join(lines))
        self.slots_label.setAccessibleName("; ".join(lines))
        maps = result.get("maps") or {}
        self.thumbs.set_items([widgets.Thumb(maps.get(k), 64, cap) for k, cap in MAP_TILES])
        notes = [n for n in (result.get("notes") or []) if n]
        self.notes_label.setText("\n".join(u"• " + str(n) for n in notes))
        self.notes_label.setVisible(bool(notes))
        misses = list(result.get("misses") or [])
        self.miss_details.setPlainText("\n".join(misses))
        self.miss_details.setVisible(False)
        if misses:
            self.miss_banner.show("warning", "Some settings could not be applied",
                                  "Show details", lambda: self._toggle(self.miss_details))
        else:
            self.miss_banner.hide()
        self.done_banner.hide()
        self.btn_assign.setVisible(not result.get("assigned"))
        self._show_page("done")
        self.btn_another.setFocus()

    def set_error(self, sentence, action_text=None, action=None):
        self.error_details.setPlainText("")
        self.error_details.setVisible(False)
        self.error_banner.show("error", sentence, action_text, action)
        self._show_page("error")
        if action_text:
            self.error_banner.action_button.setFocus()
        else:
            self.btn_back.setFocus()

    def set_state_loaded(self):
        self.loaded_banner.hide()
        self._show_page("loaded" if self._img else "idle")
        if self._img:
            self.name_edit.setFocus()
        else:
            self.drop.browse_button.setFocus()

    def open_settings(self):
        if self._settings is None:
            self._settings = _SettingsSheet(self)
        self._settings.refresh()
        self._settings.open()
        return self._settings

    # -- events ----------------------------------------------------------------------

    def _show_page(self, key):
        self._stack.setCurrentWidget(self._pages[key])
        self.btn_make.setEnabled(not self.is_running())

    def browse(self):
        path = None
        rt = self._rt
        fn = getattr(rt, "getOpenFileName", None) if rt is not None else None
        if callable(fn):
            try:
                f = fn(caption="MatForge: pick a photo of the material",
                       types="Images|*.jpg;*.jpeg;*.png;*.tif;*.tiff;*.bmp;*.webp|All|*.*")
                path = f if isinstance(f, str) and f else None
            except Exception:
                fn = None
        if not callable(fn):
            f, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Pick a photo of the material", "",
                "Images (*.jpg *.jpeg *.png *.tif *.tiff *.bmp *.webp)")
            path = f or None
        if path:
            self.load_image(path)

    def _on_change_renderer(self):
        if self._img:
            self.set_state_loaded()
            self._open_renderer_choice()
            return
        self._pending_renderer = True
        self.idle_banner.show("info", "Pick a photo first, then choose the renderer.")

    def _open_renderer_choice(self):
        self.more.set_expanded(True)
        self.renderer_combo.setFocus()

    def _on_change_photo(self):
        self.idle_banner.hide()
        self._show_page("idle")
        self.drop.browse_button.setFocus()

    def _on_back(self):
        self.set_state_loaded()

    def _on_tile(self, grid, key):
        for _, g in self.grids:
            if g is not grid:
                g.clear_current()
        self._cls = key
        idx = [g for _, g in self.grids].index(grid)
        if self.tabs.currentIndex() != idx and not self._building:
            self.tabs.setCurrentIndex(idx)      # a type picked in code shows its own tab
        self.selected_label.setText("Selected: " + (grid.label_for(key) or key))
        self.metal_row.setVisible(wants_metal_picker(key))

    def _on_filter(self, text):
        first = -1
        for i, (_, g) in enumerate(self.grids):
            n = g.set_filter(text)
            self.tabs.setTabEnabled(i, n > 0)
            if n and first < 0:
                first = i
        cur = self.grids[self.tabs.currentIndex()][1]
        if first >= 0 and cur.visible_count() == 0:
            self.tabs.setCurrentIndex(first)
        self.no_match.setVisible(first < 0)
        self.tabs.setVisible(first >= 0)
        self.tabs.updateGeometry()              # fewer visible tiles, fewer rows

    def _on_quality(self, key):
        best = key == "ultra"
        self.chk_seamless.setEnabled(not best)
        a11y.label(self.chk_seamless, "Make it tile seamlessly",
                   "Best always tiles" if best else "Hide the seams when it repeats")

    def _toggle(self, box):
        box.setVisible(not box.isVisible())

    def _on_assign(self):
        if not self._result:
            return
        ok, text = _fm().assign_result(self._result)
        self.done_banner.show("ok" if ok else "info", text)

    def _on_slate(self):
        if not self._result:
            return
        if _fm().slate_result(self._result):
            self.done_banner.show("ok", "Opened in Slate.")
        else:
            self.done_banner.show("info", "Slate could not open here.")

    # -- process ---------------------------------------------------------------------

    def _on_stdout(self):
        self._stdout += bytes(self._proc.readAllStandardOutput().data())

    def _on_stderr(self):
        self._stderr_buf += bytes(self._proc.readAllStandardError().data())
        lines = self._stderr_buf.split(b"\n")
        self._stderr_buf = lines.pop()
        for raw in lines:
            self._stderr_line(raw)

    def _stderr_line(self, raw):
        line = raw.decode("utf-8", "replace").rstrip("\r")
        m = PROGRESS_RE.match(line)
        if m:
            self.set_phase(m.group(3).strip())
            return
        if line.strip():
            self._stderr_tail.append(line)
            del self._stderr_tail[:-STDERR_TAIL]

    def _on_timeout(self):
        if self.is_running():
            self._timed_out = True
            self._proc.kill()

    def _details_text(self):
        prog = " ".join((self._cmd or {}).get("argv", [])[:2])
        out = ["Command: " + prog] if prog else []
        if self._stderr_tail:
            out.append("")
            out.extend(self._stderr_tail)
        tail = self._stdout.decode("utf-8", "replace").strip().splitlines()[-20:]
        if tail:
            out.append("")
            out.extend(tail)
        return "\n".join(out)

    def _error_with_details(self, sentence, action_text=None, action=None, details=None):
        text = details if details is not None else self._details_text()
        if action_text == "Show details":
            action = lambda: self._toggle(self.error_details)
        self.set_error(sentence, action_text, action)
        self.error_details.setPlainText(text)
        if text:
            print("[MatForge] %s\n%s" % (sentence, text))

    def _try_standard(self):
        self.quality.set_current("fast")
        self.set_state_loaded()
        self.start()

    def _on_proc_error(self, err):
        if err != enum(QtCore.QProcess, "ProcessError", "FailedToStart"):
            return                          # crashes and kills arrive via finished
        self._guard.stop()
        self.btn_make.setEnabled(True)
        prog = " ".join((self._cmd or {}).get("argv", [])[:1])
        self._error_with_details(
            NO_PYTHON, "Show details",
            details="Tried to run: %s\n%s\n\nInstall Python 3, then run: "
                    "pip install Pillow numpy" % (prog, self._proc.errorString()))

    def _on_finished(self, exit_code, exit_status=None):
        self._guard.stop()
        self._on_stdout()
        if self._stderr_buf:
            self._stderr_line(self._stderr_buf)
            self._stderr_buf = b""
        self.btn_make.setEnabled(True)
        if self._cancelled:
            self._cancelled = False
            self.set_state_loaded()
            self.loaded_banner.show("info", STOPPED)
            return
        if self._timed_out:
            self._timed_out = False
            self._error_with_details(TIMED_OUT, "Try again", self._retry)
            return
        fm = _fm()
        crashed = exit_status == enum(QtCore.QProcess, "ExitStatus", "CrashExit")
        code = exit_code if not crashed else (exit_code or 1)
        manifest, warnings, err = fm.parse_generator_output(
            self._stdout.decode("utf-8", "replace"), code)
        if err or code != 0:
            if not err or err == "see listener":
                err = "the generator stopped unexpectedly"
            sentence = "Could not make the maps: %s" % _sentence(err)
            if self._eng == "ultra":
                self._error_with_details(sentence, "Try Standard", self._try_standard)
            else:
                self._error_with_details(sentence, "Show details")
            return
        self.set_phase(WIRING_PHASE)
        QtWidgets.QApplication.processEvents()
        cmd, p = self._cmd, self._args
        try:
            result = fm.finish_build(manifest, warnings, cmd["extra_note"], p["assign"],
                                     p["slate"], cmd["renderer"], cmd["metal"])
        except Exception as e:
            result = {"state": "err", "text": "Material wiring failed: %s" % e}
        if result.get("state") == "ok":
            self.set_done(result)
            return
        text = result.get("text") or ""
        prefix = "Material wiring failed: "
        if text.startswith(prefix):
            text = text[len(prefix):]
        self._error_with_details("Could not wire the material: %s" % _sentence(text),
                                 "Show details", details=result.get("text") or "")

    def _retry(self):
        self.set_state_loaded()
        self.start()

    def resizeEvent(self, event):
        super(MatForgeDock, self).resizeEvent(event)
        m = 16 if event.size().width() >= 360 else 12     # 12 keeps 320 px docks unclipped
        for page in (self.idle_page, self.loaded_page, self.working_page, self.done_page,
                     self.error_page):
            page.layout().setContentsMargins(m, 16, m, 16)
        self._fit_tab_padding(event.size().width() - 2 * m - 8)

    def _fit_tab_padding(self, avail):
        """Spread the 7 group tabs across the width: padding shrinks (never below 2 px)
        so every tab stays visible down to a 320 px dock."""
        if avail == self._tab_avail:
            return
        self._tab_avail = avail
        bar = self.tabs.tabBar()
        for pad in range(8, 1, -1):
            self.tabs.setStyleSheet("QTabBar::tab { padding: 0px %dpx; }" % pad)
            self._tab_pad = pad
            if bar.sizeHint().width() <= avail:
                break

    def keyPressEvent(self, event):
        if event.key() == enum(QtCore.Qt, "Key", "Key_Escape") and self.state() == "working":
            self.cancel()
            event.accept()
            return
        super(MatForgeDock, self).keyPressEvent(event)

    def closeEvent(self, event):
        if self.is_running():
            self.cancel()
        super(MatForgeDock, self).closeEvent(event)


_dock = None


def _alive(w):
    try:
        w.objectName()
        return True
    except RuntimeError:                    # C++ side already deleted
        return False


def show():
    """Open (or raise) the single MatForge dock and return it."""
    global _dock
    if QtWidgets.QApplication.instance() is None:   # a QWidget without one aborts Python
        raise QtUnavailable("no QApplication; MatForge must run inside 3ds Max")
    if _dock is not None and not _alive(_dock):
        _dock = None
    if _dock is None:
        main = None
        try:
            import qtmax
            main = qtmax.GetQMaxMainWindow()
        except Exception:
            main = None
        _dock = MatForgeDock(rt=_fm().rt, parent=main)
        if main is not None and hasattr(main, "addDockWidget"):
            main.addDockWidget(enum(QtCore.Qt, "DockWidgetArea", "RightDockWidgetArea"), _dock)
        else:
            _dock.setFloating(True)
    _dock.show()
    _dock.raise_()
    return _dock
