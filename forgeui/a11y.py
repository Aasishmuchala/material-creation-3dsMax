"""Accessibility helpers: names, tooltips, tab order and keyboard triggers."""
from .compat import QtCore, QtGui, QtWidgets, QShortcut, enum


def label(widget, name, tip=None):
    """setAccessibleName + setToolTip (tip defaults to name; pass "" for no tooltip)."""
    widget.setAccessibleName(name or "")
    widget.setToolTip(name if tip is None else tip)
    return widget


def tab_order(widgets):
    """Chain QWidget.setTabOrder through widgets in order (None entries are skipped)."""
    chain = [w for w in widgets if w is not None]
    for a, b in zip(chain, chain[1:]):
        a.setTabOrder(a, b)


def _shortcut(host, key_name, slot):
    sc = QShortcut(QtGui.QKeySequence(enum(QtCore.Qt, "Key", key_name)), host)
    sc.setContext(enum(QtCore.Qt, "ShortcutContext", "WidgetWithChildrenShortcut"))
    sc.activated.connect(slot)
    return sc


def enter_triggers(host, button):
    """Return / Enter anywhere inside host clicks button (when it is visible and enabled)."""
    def fire():
        fw = QtWidgets.QApplication.focusWidget()
        if (isinstance(fw, (QtWidgets.QPushButton, QtWidgets.QToolButton))
                and fw is not button and fw.isEnabled()):
            fw.click()                      # a focused button owns Return
            return
        if button.isEnabled() and button.isVisible():
            button.click()
    return [_shortcut(host, "Key_Return", fire), _shortcut(host, "Key_Enter", fire)]


def esc_triggers(host, callback):
    """Escape anywhere inside host calls callback()."""
    return _shortcut(host, "Key_Escape", lambda: callback())
