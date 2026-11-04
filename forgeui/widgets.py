"""Shared widgets for the MatForge and Material Inspector docks.

Every class takes parent=None last and labels itself for assistive tech. Looks come from the
kit sheet (forgeui.qss) through the dynamic "role" property; nothing here hard-codes colour.
"""
import os

from . import a11y
from .compat import QtCore, QtGui, QtWidgets, Signal, enum

CONTROL_H = 28
PRIMARY_H = 44


def _align(*names):
    flags = enum(QtCore.Qt, "AlignmentFlag", names[0])
    for n in names[1:]:
        flags = flags | enum(QtCore.Qt, "AlignmentFlag", n)
    return flags


def _policy(name):
    return enum(QtWidgets.QSizePolicy, "Policy", name)


def _repolish(widget):
    st = widget.style()
    st.unpolish(widget)
    st.polish(widget)
    widget.update()


def _no_mouse(widget):
    widget.setAttribute(enum(QtCore.Qt, "WidgetAttribute", "WA_TransparentForMouseEvents"), True)


class _NamedText(object):
    """Keeps accessible name and tooltip in step with setText unless they were customised."""

    def setText(self, text):
        old = self.text()
        super(_NamedText, self).setText(text)
        if self.accessibleName() in ("", old):
            self.setAccessibleName(text)
        if self.toolTip() == old and self._tip_follows:
            self.setToolTip(text)


# -- buttons -------------------------------------------------------------------

class _Button(_NamedText, QtWidgets.QPushButton):
    ROLE = "secondary"
    HEIGHT = CONTROL_H

    def __init__(self, text="", parent=None):
        super(_Button, self).__init__(text, parent)
        self._tip_follows = True
        self.setProperty("role", self.ROLE)
        self.setMinimumHeight(self.HEIGHT)
        self.setCursor(QtGui.QCursor(enum(QtCore.Qt, "CursorShape", "PointingHandCursor")))
        a11y.label(self, text)


class PrimaryButton(_Button):
    """The one primary action of a screen: accent fill, 44 px, default button."""
    ROLE = "primary"
    HEIGHT = PRIMARY_H

    def __init__(self, text="", parent=None):
        super(PrimaryButton, self).__init__(text, parent)
        self.setDefault(True)


class SecondaryButton(_Button):
    ROLE = "secondary"


class GhostButton(_Button):
    """Text-only accent button for low-weight actions ("Change", "Why?")."""
    ROLE = "ghost"

    def __init__(self, text="", parent=None):
        super(GhostButton, self).__init__(text, parent)
        self.setFlat(True)
        self.setSizePolicy(_policy("Maximum"), _policy("Fixed"))


# -- text ------------------------------------------------------------------------

class _Label(_NamedText, QtWidgets.QLabel):
    ROLE = ""
    WRAP = False

    def __init__(self, text="", parent=None):
        super(_Label, self).__init__(text, parent)
        self._tip_follows = False
        if self.ROLE:
            self.setProperty("role", self.ROLE)
        self.setWordWrap(self.WRAP)
        a11y.label(self, text, "")


class Title(_Label):
    """15 px / 600 heading."""
    ROLE = "title"
    WRAP = True


class Muted(_Label):
    """11 px secondary text in the muted colour; wraps."""
    ROLE = "muted"
    WRAP = True


class SeverityChip(_Label):
    """Small filled chip carrying a WORD ("Error", "Done"); kind in error, warning, ok, info."""
    ROLE = "chip"
    KINDS = ("error", "warning", "ok", "info")

    def __init__(self, word="", kind="info", parent=None):
        super(SeverityChip, self).__init__(word, parent)
        self.setAlignment(_align("AlignCenter"))
        self.setSizePolicy(_policy("Maximum"), _policy("Fixed"))
        self.set_kind(word, kind)

    def set_kind(self, word, kind):
        self.setText(word)
        self.setProperty("kind", kind if kind in self.KINDS else "info")
        _repolish(self)

    def kind(self):
        return self.property("kind")


# -- containers --------------------------------------------------------------------

class Card(QtWidgets.QFrame):
    """Sunken group surface: base fill, hairline border, 4 px radius."""

    def __init__(self, name="Group", parent=None):
        super(Card, self).__init__(parent)
        self.setProperty("role", "card")
        a11y.label(self, name, "")


class _Hairline(QtWidgets.QFrame):
    def __init__(self, parent=None):
        super(_Hairline, self).__init__(parent)
        self.setProperty("role", "hairline")
        self.setFixedHeight(1)


class SectionHeader(QtWidgets.QWidget):
    """13 px / 600 section label with a hairline under it."""

    def __init__(self, text="", parent=None):
        super(SectionHeader, self).__init__(parent)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.label = QtWidgets.QLabel(text)
        self.label.setProperty("role", "section")
        lay.addWidget(self.label)
        lay.addWidget(_Hairline())
        self.setMinimumHeight(CONTROL_H)
        a11y.label(self, text, "")

    def set_text(self, text):
        self.label.setText(text)
        self.setAccessibleName(text)

    def text(self):
        return self.label.text()


class DropZone(QtWidgets.QFrame):
    """Drag-and-drop target for ONE local image file, with a Browse... button inside."""
    fileChosen = Signal(str)
    EXTS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp")

    def __init__(self, headline="Drop a photo of the material here",
                 hint="JPG, PNG, TIFF, BMP or WebP, up to 64 MB", parent=None):
        super(DropZone, self).__init__(parent)
        self._browse = None
        self.setProperty("role", "dropzone")
        self.setProperty("dragging", False)
        self.setAcceptDrops(True)
        self.setMinimumHeight(180)
        self.setSizePolicy(_policy("Expanding"), _policy("Expanding"))

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(16, 24, 16, 24)
        lay.setSpacing(8)
        lay.addStretch(1)
        self.headline = QtWidgets.QLabel(headline)
        self.headline.setProperty("role", "dropheadline")
        self.headline.setAlignment(_align("AlignHCenter"))
        self.headline.setWordWrap(True)
        self.or_label = QtWidgets.QLabel("or")
        self.or_label.setProperty("role", "muted")
        self.or_label.setAlignment(_align("AlignHCenter"))
        self.browse_button = SecondaryButton("Browse...")
        a11y.label(self.browse_button, "Browse...", "Choose a photo from disk")
        self.browse_button.clicked.connect(self._on_browse)
        self.hint = QtWidgets.QLabel(hint)
        self.hint.setProperty("role", "muted")
        self.hint.setAlignment(_align("AlignHCenter"))
        self.hint.setWordWrap(True)
        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.browse_button)
        row.addStretch(1)
        lay.addWidget(self.headline)
        lay.addWidget(self.or_label)
        lay.addLayout(row)
        lay.addSpacing(4)
        lay.addWidget(self.hint)
        lay.addStretch(1)
        a11y.label(self, headline, hint)

    # public API
    def set_texts(self, headline, hint):
        self.headline.setText(headline)
        self.hint.setText(hint)
        a11y.label(self, headline, hint)

    def set_browse(self, callback):
        self._browse = callback

    def is_dragging(self):
        return bool(self.property("dragging"))

    @classmethod
    def path_from_mime(cls, mime):
        """The single acceptable local image path in mime, else None."""
        if mime is None or not mime.hasUrls():
            return None
        urls = mime.urls()
        if len(urls) != 1 or not urls[0].isLocalFile():
            return None
        path = urls[0].toLocalFile()
        if os.path.splitext(path)[1].lower() not in cls.EXTS or not os.path.isfile(path):
            return None
        return path

    # internals
    def _on_browse(self):
        if self._browse is not None:
            self._browse()

    def _set_dragging(self, on):
        self.setProperty("dragging", bool(on))
        _repolish(self)

    def mousePressEvent(self, event):
        if event.button() == enum(QtCore.Qt, "MouseButton", "LeftButton"):
            self._on_browse()
        super(DropZone, self).mousePressEvent(event)

    def dragEnterEvent(self, event):
        if self.path_from_mime(event.mimeData()):
            event.acceptProposedAction()
            self._set_dragging(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self.path_from_mime(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._set_dragging(False)
        super(DropZone, self).dragLeaveEvent(event)

    def dropEvent(self, event):
        path = self.path_from_mime(event.mimeData())
        self._set_dragging(False)
        if not path:
            event.ignore()
            return
        event.acceptProposedAction()
        self.fileChosen.emit(path)


class StatusBanner(QtWidgets.QFrame):
    """Inline banner: chip with the WORD + one sentence + at most one ghost action."""
    WORDS = {"error": "Error", "warning": "Warning", "ok": "Done", "info": "Note"}

    def __init__(self, parent=None):
        super(StatusBanner, self).__init__(parent)
        self._action = None
        self.setProperty("role", "banner")
        self.setProperty("kind", "info")
        self.setMinimumHeight(CONTROL_H + 8)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 4, 4)
        lay.setSpacing(8)
        self.chip = SeverityChip("Note", "info")
        self.sentence = QtWidgets.QLabel("")
        self.sentence.setWordWrap(True)
        self.sentence.setSizePolicy(_policy("Expanding"), _policy("Preferred"))
        self.action_button = GhostButton("")
        self.action_button.clicked.connect(self._on_action)
        self.action_button.setVisible(False)
        # Every column is top-aligned behind a spacer sized by _align_first_line(), so the chip,
        # the FIRST line of the sentence and the action share one centre line even when the
        # sentence wraps.
        self._pads = {}
        for key, w, stretch in (("chip", self.chip, 0), ("sentence", self.sentence, 1),
                                ("action", self.action_button, 0)):
            col = QtWidgets.QVBoxLayout()
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(0)
            pad = QtWidgets.QSpacerItem(0, 0, _policy("Minimum"), _policy("Fixed"))
            col.addSpacerItem(pad)
            col.addWidget(w, 0, _align("AlignTop"))
            col.addStretch(1)
            lay.addLayout(col, stretch)
            self._pads[key] = (pad, col)
        a11y.label(self, "Status", "")
        self.setVisible(False)

    def _align_first_line(self):
        if not getattr(self, "_pads", None):
            return
        for w in (self.chip, self.sentence, self.action_button):
            w.ensurePolished()
        heights = {"chip": self.chip.sizeHint().height(),
                   "sentence": self.sentence.fontMetrics().height(),
                   "action": (self.action_button.sizeHint().height()
                              if not self.action_button.isHidden() else 0)}
        band = max(heights.values())
        for key, (pad, col) in self._pads.items():
            pad.changeSize(0, max(0, (band - heights[key] + 1) // 2),
                           _policy("Minimum"), _policy("Fixed"))
            col.invalidate()

    def first_line_centres(self):
        """Vertical centre (in banner coordinates) of the chip, first sentence line and action."""
        line_h = self.sentence.fontMetrics().height()
        out = {"chip": self.chip.geometry().center().y(),
               "sentence": self.sentence.geometry().top() + line_h // 2}
        if not self.action_button.isHidden():
            out["action"] = self.action_button.geometry().center().y()
        return out

    def showEvent(self, event):
        self._align_first_line()
        super(StatusBanner, self).showEvent(event)

    def changeEvent(self, event):
        super(StatusBanner, self).changeEvent(event)
        if event.type() in (enum(QtCore.QEvent, "Type", "StyleChange"),
                            enum(QtCore.QEvent, "Type", "FontChange")):
            self._align_first_line()

    def show(self, kind=None, sentence="", action_text=None, action=None):
        if kind is None:                    # plain QWidget.show() semantics
            self.setVisible(True)
            return
        kind = kind if kind in self.WORDS else "info"
        word = self.WORDS[kind]
        self.setProperty("kind", kind)
        self.chip.set_kind(word, kind)
        self.sentence.setText(sentence)
        self._action = action
        if action_text is None:
            self.action_button.setVisible(False)
        else:
            self.action_button.setText(action_text)
            a11y.label(self.action_button, action_text)
            self.action_button.setVisible(True)
        self.setAccessibleName("%s: %s" % (word, sentence))
        _repolish(self)
        self._align_first_line()
        self.setVisible(True)

    def hide(self):
        self.setVisible(False)

    def kind(self):
        return self.property("kind")

    def word(self):
        return self.chip.text()

    def text(self):
        return self.sentence.text()

    def _on_action(self):
        if self._action is not None:
            self._action()


class SkeletonRows(QtWidgets.QWidget):
    """Loading placeholder shaped like the final layout: grey bars, then optional square tiles."""

    def __init__(self, rows=6, tiles=0, parent=None):
        super(SkeletonRows, self).__init__(parent)
        self.bars = []
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(900)
        self._timer.timeout.connect(self._tick)
        self._phase = False
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        for i in range(rows):
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(0)
            bar = self._bar()
            bar.setFixedHeight(12)
            if i % 2 == 0:
                row.addWidget(bar, 1)
            else:
                row.addWidget(bar, 7)
                row.addStretch(3)
            lay.addLayout(row)
        if tiles:
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(8)
            for _ in range(tiles):
                tile = self._bar()
                tile.setFixedSize(64, 64)
                row.addWidget(tile)
            row.addStretch(1)
            lay.addLayout(row)
        a11y.label(self, "Loading", "")

    def _bar(self):
        f = QtWidgets.QFrame()
        f.setProperty("role", "skeleton")
        f.setProperty("pulse", False)
        self.bars.append(f)
        return f

    def set_pulse(self, on):
        if on:
            self._timer.start()
        else:
            self._timer.stop()
            self._phase = True              # _tick flips it back to the resting shade
            self._tick()

    def is_pulsing(self):
        return self._timer.isActive()

    def _tick(self):
        self._phase = not self._phase
        for b in self.bars:
            b.setProperty("pulse", self._phase)
            _repolish(b)


class MoreOptions(QtWidgets.QWidget):
    """Collapsible section; the header is a ghost button with a ">" / "v" prefix."""
    toggled = Signal(bool)

    def __init__(self, title="More options", parent=None):
        super(MoreOptions, self).__init__(parent)
        self._title = title
        self._content = None
        self._expanded = False
        self._lay = QtWidgets.QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(8)
        self.header = GhostButton("")
        self.header.clicked.connect(lambda: self.set_expanded(not self._expanded))
        self._lay.addWidget(self.header, 0, _align("AlignLeft"))
        self.setMinimumHeight(CONTROL_H)
        a11y.label(self, title, "")
        self._sync()

    def set_content(self, widget):
        if self._content is not None:
            self._lay.removeWidget(self._content)
            self._content.setParent(None)
        self._content = widget
        if widget is not None:
            self._lay.addWidget(widget)
        self._sync()

    def content(self):
        return self._content

    def set_expanded(self, on):
        on = bool(on)
        changed = on != self._expanded
        self._expanded = on
        self._sync()
        if changed:
            self.toggled.emit(on)

    def is_expanded(self):
        return self._expanded

    def _sync(self):
        self.header.setText(("v " if self._expanded else "> ") + self._title)
        a11y.label(self.header, self._title,
                   "Hide %s" % self._title.lower() if self._expanded
                   else "Show %s" % self._title.lower())
        self.header.setAccessibleDescription("expanded" if self._expanded else "collapsed")
        if self._content is not None:
            self._content.setVisible(self._expanded)


class EmptyState(QtWidgets.QWidget):
    """Centred headline, optional body and one ghost action."""

    def __init__(self, headline, body="", action_text=None, action=None, parent=None):
        super(EmptyState, self).__init__(parent)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(16, 24, 16, 24)
        lay.setSpacing(8)
        lay.addStretch(1)
        self.headline = Title(headline)
        self.headline.setAlignment(_align("AlignHCenter"))
        lay.addWidget(self.headline)
        self.body = Muted(body)
        self.body.setAlignment(_align("AlignHCenter"))
        self.body.setVisible(bool(body))
        lay.addWidget(self.body)
        self.action_button = None
        if action_text:
            self.action_button = GhostButton(action_text)
            if action is not None:
                self.action_button.clicked.connect(lambda: action())
            lay.addWidget(self.action_button, 0, _align("AlignHCenter"))
        lay.addStretch(1)
        self.setMinimumHeight(CONTROL_H)
        a11y.label(self, headline, "")

    def set_texts(self, headline, body=""):
        self.headline.setText(headline)
        self.body.setText(body)
        self.body.setVisible(bool(body))
        self.setAccessibleName(headline)


class Thumb(QtWidgets.QLabel):
    """Square map preview with a caption under it; "Not made" when the file is missing."""

    def __init__(self, path_or_None=None, size=64, caption="", parent=None):
        super(Thumb, self).__init__(parent)
        self._size = int(size)
        self._path = None
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.image = QtWidgets.QLabel()
        self.image.setProperty("role", "thumb")
        self.image.setFixedSize(self._size, self._size)
        self.image.setAlignment(_align("AlignCenter"))
        self.image.setWordWrap(True)
        self.caption = QtWidgets.QLabel(caption)
        self.caption.setProperty("role", "muted")
        self.caption.setAlignment(_align("AlignHCenter"))
        self.caption.setVisible(bool(caption))
        lay.addWidget(self.image, 0, _align("AlignHCenter"))
        lay.addWidget(self.caption)
        cap_h = self.caption.sizeHint().height() + 4 if caption else 0
        self.setFixedSize(max(self._size, self.caption.sizeHint().width()), self._size + cap_h)
        self._caption = caption
        self.set_path(path_or_None)

    def set_path(self, path_or_None):
        pix = None
        if path_or_None and os.path.isfile(path_or_None):
            pix = QtGui.QPixmap(path_or_None)
            if pix.isNull():
                pix = None
        inner = self._size - 2
        if pix is not None:
            self._path = path_or_None
            self.image.setPixmap(pix.scaled(
                inner, inner, enum(QtCore.Qt, "AspectRatioMode", "KeepAspectRatioByExpanding"),
                enum(QtCore.Qt, "TransformationMode", "SmoothTransformation")).copy(
                0, 0, inner, inner))
            self.image.setProperty("made", True)
        else:
            self._path = None
            self.image.clear()
            self.image.setText("Not made")
            self.image.setProperty("made", False)
        _repolish(self.image)
        name = "%s: %s" % (self._caption or "Map", "made" if pix is not None else "Not made")
        a11y.label(self, name, path_or_None if pix is not None else "Not made")

    def is_made(self):
        return self._path is not None

    def path(self):
        return self._path


class SegmentedChoice(QtWidgets.QWidget):
    """Row of exclusive choices, each a button with a label and an 11 px hint underneath."""
    changed = Signal(str)

    def __init__(self, options, parent=None):
        super(SegmentedChoice, self).__init__(parent)
        self._buttons = {}
        self._keys = []
        self._group = QtWidgets.QButtonGroup(self)
        self._group.setExclusive(True)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        for key, text, hint in options:
            b = QtWidgets.QToolButton()
            b.setProperty("role", "segment")
            b.setCheckable(True)
            b.setFixedHeight(PRIMARY_H)
            b.setSizePolicy(_policy("Expanding"), _policy("Fixed"))
            b.setFocusPolicy(enum(QtCore.Qt, "FocusPolicy", "StrongFocus"))
            inner = QtWidgets.QVBoxLayout(b)
            inner.setContentsMargins(8, 4, 8, 4)
            inner.setSpacing(0)
            top = QtWidgets.QLabel(text)
            top.setAlignment(_align("AlignHCenter"))
            low = QtWidgets.QLabel(hint or "")
            low.setProperty("role", "muted")
            low.setAlignment(_align("AlignHCenter"))
            low.setVisible(bool(hint))
            for lbl in (top, low):
                _no_mouse(lbl)
                inner.addWidget(lbl)
            b.setMinimumWidth(max(top.sizeHint().width(), low.sizeHint().width()) + 20)
            a11y.label(b, text if not hint else "%s, %s" % (text, hint))
            b.clicked.connect(lambda checked=False, k=key: self._on_click(k))
            self._group.addButton(b)
            lay.addWidget(b, 1)
            self._buttons[key] = b
            self._keys.append(key)
        if self._keys:
            self._buttons[self._keys[0]].setChecked(True)
        self.setMinimumHeight(PRIMARY_H)
        a11y.label(self, "Choice", "")

    def _on_click(self, key):
        self.changed.emit(key)

    def current(self):
        for k in self._keys:
            if self._buttons[k].isChecked():
                return k
        return None

    def set_current(self, key):
        """Select key; emits changed when the selection moves. False for an unknown key."""
        b = self._buttons.get(key)
        if b is None:
            return False
        moved = not b.isChecked()
        b.setChecked(True)
        if moved:
            self.changed.emit(key)
        return True

    def button(self, key):
        return self._buttons.get(key)

    def keys(self):
        return list(self._keys)


class TileGrid(QtWidgets.QWidget):
    """Grid of exclusive checkable tiles (28 px tall) with a case-insensitive label filter."""
    selected = Signal(str)

    def __init__(self, items=None, columns=2, parent=None):
        super(TileGrid, self).__init__(parent)
        self._columns = max(1, int(columns))
        self._tiles = []                    # [(key, label, button)] in original order
        self._group = QtWidgets.QButtonGroup(self)
        self._group.setExclusive(True)
        self._grid = QtWidgets.QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(8)
        self._grid.setVerticalSpacing(8)
        for c in range(self._columns):
            self._grid.setColumnStretch(c, 1)
        for key, text in (items or []):
            b = QtWidgets.QToolButton()
            b.setText(text)
            b.setProperty("role", "tile")
            b.setCheckable(True)
            b.setFixedHeight(CONTROL_H)
            b.setSizePolicy(_policy("Expanding"), _policy("Fixed"))
            b.setFocusPolicy(enum(QtCore.Qt, "FocusPolicy", "StrongFocus"))
            a11y.label(b, text)
            b.clicked.connect(lambda checked=False, k=key: self.selected.emit(k))
            self._group.addButton(b)
            self._tiles.append((key, text, b))
        self._filter = ""
        self._relayout()
        a11y.label(self, "Types", "")

    def _relayout(self):
        for _, _, b in self._tiles:
            self._grid.removeWidget(b)
        i = 0
        for _, text, b in self._tiles:
            show = not self._filter or self._filter in text.lower()
            b.setVisible(show)
            if show:
                self._grid.addWidget(b, i // self._columns, i % self._columns)
                i += 1
        self._visible = i

    def set_filter(self, text):
        """Hide tiles whose label lacks text (case-insensitive). Returns the visible count."""
        self._filter = (text or "").strip().lower()
        self._relayout()
        return self._visible

    def visible_count(self):
        return self._visible

    def visible_keys(self):
        return [k for k, _, b in self._tiles if not b.isHidden()]

    def keys(self):
        return [k for k, _, _ in self._tiles]

    def tile(self, key):
        for k, _, b in self._tiles:
            if k == key:
                return b
        return None

    def label_for(self, key):
        for k, text, _ in self._tiles:
            if k == key:
                return text
        return None

    def set_current(self, key):
        """Check key's tile and emit selected(key). False for an unknown key."""
        b = self.tile(key)
        if b is None:
            return False
        b.setChecked(True)
        self.selected.emit(key)
        return True

    def current(self):
        for k, _, b in self._tiles:
            if b.isChecked():
                return k
        return None

    def clear_current(self):
        """Uncheck every tile (used when the selection moves to another grid)."""
        self._group.setExclusive(False)
        for _, _, b in self._tiles:
            b.setChecked(False)
        self._group.setExclusive(True)
