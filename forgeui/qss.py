"""Style sheet for both docks, built from Tokens.

Geometry rule: every bordered control is 1 px hairline + 1 px padding at rest and 2 px accent
+ 0 px padding when focused, so the focus ring never changes a widget's size. Heights are given
as content height (Qt adds padding and border): 24 + 2 + 2 = 28 px, 40 + 2 + 2 = 44 px.
Never sets font-family (the host UI font stays). px units only.
"""
import os
import tempfile

from . import tokens as _tk

_SHEET = """
QWidget { color: %(text)s; font-size: 13px; }
QLabel { background: transparent; }
QLabel[role="title"] { font-size: 15px; font-weight: 600; }
QLabel[role="muted"] { font-size: 11px; color: %(muted)s; }
QLabel[role="section"] { font-size: 13px; font-weight: 600; }
QLabel[role="path"] { color: %(muted)s; }
QFrame[role="hairline"] { background: %(hairline)s; border: none; min-height: 1px; max-height: 1px; }
QFrame[role="card"] { background: %(base)s; border: 1px solid %(hairline)s; border-radius: 4px; }

QToolTip { background: %(base)s; color: %(text)s; border: 1px solid %(hairline)s; border-radius: 4px; padding: 4px 8px; }

QPushButton { min-height: 24px; padding: 1px 12px; border: 1px solid %(hairline)s; border-radius: 4px; background: %(raised)s; color: %(text)s; }
QPushButton:hover { background: %(hover)s; }
QPushButton:pressed { background: %(base)s; }
QPushButton[role="primary"] { min-height: 40px; background: %(accent)s; color: %(on_accent)s; border-color: %(accent)s; font-weight: 600; }
QPushButton[role="primary"]:hover { background: %(accent_hover)s; border-color: %(accent_hover)s; }
QPushButton[role="primary"]:pressed { background: %(accent_pressed)s; border-color: %(accent_pressed)s; }
QPushButton[role="ghost"] { background: transparent; border-color: transparent; color: %(accent)s; padding: 1px 4px; text-align: left; }
QPushButton[role="ghost"]:hover { color: %(accent_hover)s; background: transparent; }
QPushButton[role="ghost"]:pressed { color: %(accent_pressed)s; background: transparent; }
QPushButton:focus { outline: none; border: 2px solid %(accent)s; padding: 0px 11px; }
QPushButton[role="primary"]:focus { border: 2px solid %(text)s; padding: 0px 11px; }
QPushButton[role="ghost"]:focus { border: 2px solid %(accent)s; padding: 0px 3px; }
QPushButton:disabled { background: %(window)s; color: %(muted)s; border-color: %(hairline)s; }
QPushButton[role="primary"]:disabled { background: %(raised)s; color: %(muted)s; border-color: %(hairline)s; }
QPushButton[role="ghost"]:disabled { background: transparent; border-color: transparent; color: %(muted)s; }

*:focus { outline: none; border: 2px solid %(accent)s; }

QLineEdit, QComboBox { min-height: 24px; border: 1px solid %(hairline)s; border-radius: 4px; background: %(base)s; padding: 1px 8px; color: %(text)s; selection-background-color: %(accent)s; selection-color: %(on_accent)s; }
QLineEdit:focus, QComboBox:focus { border: 2px solid %(accent)s; padding: 0px 7px; }
QLineEdit:disabled, QComboBox:disabled { color: %(muted)s; background: %(window)s; }
QComboBox:hover { border-color: %(muted)s; }
QComboBox:focus:hover { border-color: %(accent)s; }
QComboBox { padding-right: 24px; }
QComboBox:focus { padding-right: 23px; }
QComboBox::drop-down { border: none; width: 24px; subcontrol-origin: border; subcontrol-position: center right; }
QComboBox::down-arrow { width: 12px; height: 12px;%(arrow_image)s }
QComboBox QAbstractItemView { background: %(base)s; color: %(text)s; border: 1px solid %(hairline)s; selection-background-color: %(hover)s; selection-color: %(text)s; outline: none; }

QCheckBox { spacing: 8px; min-height: 24px; padding: 0px 4px; border: 2px solid transparent; border-radius: 4px; background: transparent; }
QCheckBox:focus { border: 2px solid %(accent)s; }
QCheckBox:disabled { color: %(muted)s; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid %(muted)s; border-radius: 4px; background: %(base)s; }
QCheckBox::indicator:hover { border-color: %(text)s; }
QCheckBox::indicator:checked { background: %(accent)s; border-color: %(accent)s;%(check_image)s }
QCheckBox::indicator:checked:hover { background: %(accent_hover)s; border-color: %(accent_hover)s; }
QCheckBox::indicator:disabled { background: %(window)s; border-color: %(hairline)s; }
QCheckBox::indicator:checked:disabled { background: %(raised)s; border-color: %(hairline)s; }

QToolButton { padding: 1px 8px; border: 1px solid transparent; border-radius: 4px; background: transparent; color: %(text)s; }
QToolButton:hover { background: %(hover)s; }
QToolButton:pressed { background: %(base)s; }
QToolButton[role="tile"], QToolButton[role="segment"] { border: 1px solid %(hairline)s; background: %(raised)s; }
QToolButton[role="tile"]:hover, QToolButton[role="segment"]:hover { background: %(hover)s; }
QToolButton[role="tile"]:checked, QToolButton[role="segment"]:checked { border: 1px solid %(accent)s; background: %(base)s; color: %(text)s; }
QToolButton:focus { outline: none; border: 2px solid %(accent)s; padding: 0px 7px; }
QToolButton[role="tile"]:focus, QToolButton[role="segment"]:focus { border: 2px solid %(accent)s; padding: 0px 7px; }
QToolButton:disabled { color: %(muted)s; }

QTabWidget::pane { border: none; border-top: 1px solid %(hairline)s; top: -1px; }
QTabWidget::tab-bar { left: 0px; }
QTabBar { background: transparent; border: none; }
QTabBar:focus { border: none; }
QTabBar::tab { min-height: 26px; padding: 0px 6px; margin: 0px; border: none; border-bottom: 2px solid transparent; background: transparent; color: %(muted)s; }
QTabBar::tab:hover { color: %(text)s; }
QTabBar::tab:selected { color: %(text)s; border-bottom: 2px solid %(accent)s; }
QTabBar::tab:disabled { color: %(hairline)s; }
QTabBar QToolButton { background: %(window)s; border: 1px solid %(hairline)s; }

QScrollArea { border: none; background: transparent; }
QScrollArea:focus { border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { width: 8px; background: transparent; border: none; margin: 0px; }
QScrollBar:horizontal { height: 8px; background: transparent; border: none; margin: 0px; }
QScrollBar::handle:vertical { background: %(raised)s; border-radius: 4px; min-height: 24px; }
QScrollBar::handle:horizontal { background: %(raised)s; border-radius: 4px; min-width: 24px; }
QScrollBar::handle:hover { background: %(hover)s; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0px; height: 0px; border: none; background: transparent; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QFrame[role="dropzone"] { background: %(base)s; border: 1px dashed %(dash)s; border-radius: 4px; }
QFrame[role="dropzone"][dragging="true"] { background: %(raised)s; border: 1px dashed %(accent)s; }
QLabel[role="dropheadline"] { font-size: 13px; font-weight: 600; }

QFrame[role="banner"] { background: %(base)s; border: 1px solid %(hairline)s; border-radius: 4px; }
QLabel[role="chip"] { font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 4px; border: 1px solid transparent; color: %(on_semantic)s; }
QLabel[role="chip"][kind="error"] { background: %(error)s; border-color: %(error)s; }
QLabel[role="chip"][kind="warning"] { background: %(warning)s; border-color: %(warning)s; }
QLabel[role="chip"][kind="ok"] { background: %(ok)s; border-color: %(ok)s; }
QLabel[role="chip"][kind="info"] { background: %(raised)s; border-color: %(hairline)s; color: %(text)s; }

QFrame[role="skeleton"] { background: %(base)s; border: none; border-radius: 4px; }
QFrame[role="skeleton"][pulse="true"] { background: %(pulse)s; }

QLabel[role="thumb"] { background: %(base)s; border: 1px solid %(hairline)s; border-radius: 4px; }
QLabel[role="thumb"][made="false"] { border: 1px dashed %(dash)s; color: %(muted)s; font-size: 11px; }
"""


def build_qss(tokens, icons=None):
    """Full sheet for tokens. icons: optional {"check": png, "arrow": png} drawn by apply()."""
    icons = icons or {}
    values = tokens.as_dict()
    values["dash"] = _tk.blend(tokens.muted, tokens.window, 0.45)
    values["pulse"] = _tk.blend(tokens.base, tokens.window, 0.5)
    for key, slot in (("check", "check_image"), ("arrow", "arrow_image")):
        path = icons.get(key)
        values[slot] = ' image: url("%s");' % path.replace("\\", "/") if path else ""
    return _SHEET % values


# polylines on a 32 px canvas: a tick for checked boxes, a chevron for combo boxes
_SHAPES = {"check": ((8, 16.5), (13.5, 22), (24, 10)),
           "arrow": ((9, 12.5), (16, 19.5), (23, 12.5))}


def _icon(kind, colour):
    """Draw shape kind in colour into a cached 32 px PNG (Qt only, no Pillow). None on failure."""
    try:
        from .compat import QtCore, QtGui, enum
        path = os.path.join(tempfile.gettempdir(),
                            "forgeui_%s_%s.png" % (kind, colour.lstrip("#").lower()))
        if os.path.isfile(path):
            return path
        img = QtGui.QImage(32, 32, enum(QtGui.QImage, "Format", "Format_ARGB32_Premultiplied"))
        img.fill(QtGui.QColor(0, 0, 0, 0))
        p = QtGui.QPainter(img)
        p.setRenderHint(enum(QtGui.QPainter, "RenderHint", "Antialiasing"), True)
        pen = QtGui.QPen(QtGui.QColor(colour), 4.0 if kind == "check" else 3.0)
        pen.setCapStyle(enum(QtCore.Qt, "PenCapStyle", "RoundCap"))
        pen.setJoinStyle(enum(QtCore.Qt, "PenJoinStyle", "RoundJoin"))
        p.setPen(pen)
        p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in _SHAPES[kind]]))
        p.end()
        tmp = "%s.%d.tmp" % (path, os.getpid())
        if not img.save(tmp, "PNG"):
            return None
        os.replace(tmp, path)
        return path
    except Exception:
        return None


def _apply_palette(widget, t):
    """Match the widget palette to the tokens so plain surfaces paint the right window colour."""
    from .compat import QtGui, enum
    pal = widget.palette()
    role = lambda name: enum(QtGui.QPalette, "ColorRole", name)
    for name, value in (("Window", t.window), ("WindowText", t.text), ("Base", t.base),
                        ("AlternateBase", t.raised), ("Text", t.text), ("Button", t.raised),
                        ("ButtonText", t.text), ("ToolTipBase", t.base), ("ToolTipText", t.text),
                        ("Highlight", t.accent), ("HighlightedText", t.on_accent)):
        pal.setColor(role(name), QtGui.QColor(value))
    widget.setPalette(pal)


def _inherited_tokens(widget):
    """Tokens already applied to widget or an ancestor (apply() rewrites the palette, so
    re-deriving from it would drift)."""
    w = widget
    while w is not None:
        t = getattr(w, "_forgeui_tokens", None)
        if t is not None:
            return t
        w = w.parentWidget()
    return None


def apply(widget, tokens=None):
    """Style widget (and its children) with the kit sheet. Returns the Tokens used."""
    t = tokens or _inherited_tokens(widget) or _tk.from_palette(widget.palette())
    _apply_palette(widget, t)
    widget.setStyleSheet(build_qss(t, {"check": _icon("check", t.on_accent),
                                          "arrow": _icon("arrow", t.muted)}))
    try:
        widget._forgeui_tokens = t
    except Exception:
        pass
    return t
