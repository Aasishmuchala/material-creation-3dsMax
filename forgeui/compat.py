"""PySide6 / PySide2 compatibility shim: the ONLY place the kit touches Qt binding differences.

3ds Max 2025+ ships PySide6; 2022 to 2024 ship PySide2. Everything else in forgeui (and both
docks) imports Qt from here. ImportError propagates when neither binding exists, so callers can
fall back to the MAXScript rollout.
"""
try:                                    # 3ds Max 2025+
    from PySide6 import QtCore, QtGui, QtWidgets
    IS_PYSIDE6 = True
except ImportError:                     # 3ds Max 2022 to 2024
    from PySide2 import QtCore, QtGui, QtWidgets  # type: ignore
    IS_PYSIDE6 = False

Signal = QtCore.Signal
Slot = QtCore.Slot

if IS_PYSIDE6:
    QAction = QtGui.QAction
    QShortcut = QtGui.QShortcut
else:
    QAction = QtWidgets.QAction
    QShortcut = QtWidgets.QShortcut

QRegularExpression = QtCore.QRegularExpression


def enum(owner, name, member):
    """Scoped-or-flat enum lookup: enum(QtCore.Qt, "AlignmentFlag", "AlignLeft")."""
    scope = getattr(owner, name, None)
    if scope is not None:
        value = getattr(scope, member, None)
        if value is not None:
            return value
    return getattr(owner, member)


def exec_dialog(dialog):
    """Run a modal dialog: exec() on PySide6, exec_() on PySide2."""
    if hasattr(dialog, "exec"):
        return dialog.exec()
    return dialog.exec_()


def font_families():
    """Installed font families as a list of str."""
    db = QtGui.QFontDatabase
    try:
        return list(db.families())          # static on PySide6
    except TypeError:
        return list(db().families())        # instance method on PySide2


def fixed_font():
    """The system monospace font (used for file paths only)."""
    return QtGui.QFontDatabase.systemFont(
        enum(QtGui.QFontDatabase, "SystemFont", "FixedFont"))
