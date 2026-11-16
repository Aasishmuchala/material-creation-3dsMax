"""Dockable Material Inspector panel for 3ds Max (PySide6, PySide2 fallback via forgeui.compat).

Pages: idle, scanning, results, empty, error. The scan runs on the main thread (records hold
pymxs wrappers); cancel is cooperative through inspect()'s progress callback, which pumps the
event loop so the Cancel button and Esc stay live.
"""
from __future__ import annotations

import os
import sys
import traceback

try:
    import forgeui  # noqa: F401
except ImportError:  # source tree or bundle without the kit's parent folder on sys.path
    _HERE = os.path.dirname(os.path.abspath(__file__))
    # bundle: forgeui sits next to material_inspector; source tree: at the repo root
    for _p in (os.path.join(_HERE, "..", ".."), os.path.join(_HERE, "..", "..", "..")):
        _p = os.path.abspath(_p)
        if os.path.isdir(os.path.join(_p, "forgeui")) and _p not in sys.path:
            sys.path.insert(0, _p)
    import forgeui  # noqa: F401

from forgeui import a11y, compat, qss, widgets
from forgeui.compat import QtCore, QtWidgets, enum

from ..core import titles
from ..core.config import load_options, write_example
from ..core.inspector import InspectorOptions, ScanCancelled, inspect, summary
from ..core.log import get_logger, log_dir
from ..core.model import Severity
from ..core.report import to_html, to_json
from .fixes import FixApplier
from .scene import SceneReader

PAGES = ("idle", "scanning", "results", "empty", "error")
_DASHES = (chr(0x2014), chr(0x2013))      # long dashes never reach the screen
_NBSP = chr(0xA0)


def _plain(text):
    """Swap long dashes from lower layers (fix messages, exceptions) for a comma."""
    for ch in _DASHES:
        text = text.replace(" " + ch + " ", ", ").replace(ch, ", ")
    return text


def _align(*names):
    flags = enum(QtCore.Qt, "AlignmentFlag", names[0])
    for n in names[1:]:
        flags = flags | enum(QtCore.Qt, "AlignmentFlag", n)
    return flags


def _policy(name):
    return enum(QtWidgets.QSizePolicy, "Policy", name)


def _vbox(widget=None, margins=0, spacing=8):
    lay = QtWidgets.QVBoxLayout(widget) if widget is not None else QtWidgets.QVBoxLayout()
    lay.setContentsMargins(margins, margins, margins, margins)
    lay.setSpacing(spacing)
    return lay


def _hbox(spacing=8):
    lay = QtWidgets.QHBoxLayout()
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(spacing)
    return lay


def _plural(n, one, many):
    return "%d %s" % (n, one if n == 1 else many)


class _ElidedLabel(QtWidgets.QLabel):
    """One muted line that shortens itself in the middle instead of widening the dock."""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full = text
        self.setProperty("role", "muted")
        self.setSizePolicy(_policy("Ignored"), _policy("Preferred"))
        a11y.label(self, text)
        self._elide()

    def full_text(self):
        return self._full

    def minimumSizeHint(self):
        return QtCore.QSize(0, super().minimumSizeHint().height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    def _elide(self):
        mode = enum(QtCore.Qt, "TextElideMode", "ElideMiddle")
        super().setText(self.fontMetrics().elidedText(self._full, mode, max(self.width(), 0)))


class FindingRow(QtWidgets.QFrame):
    """One finding as a card: headline, material line, Fix / Manual, and a Why? detail."""

    def __init__(self, finding, on_fix=None, parent=None):
        super().__init__(parent)
        self.finding = finding
        f = finding
        self.setProperty("role", "card")
        self.setSizePolicy(_policy("Preferred"), _policy("Maximum"))
        grid = QtWidgets.QGridLayout(self)
        grid.setContentsMargins(12, 8, 8, 8)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)
        grid.setColumnStretch(0, 1)

        self.headline = QtWidgets.QLabel(titles.headline(f))
        self.headline.setWordWrap(True)
        self.headline.setSizePolicy(_policy("Ignored"), _policy("Preferred"))
        a11y.label(self.headline, self.headline.text(), "")
        grid.addWidget(self.headline, 0, 0)

        where = f.material if f.material_index is not None else "Whole scene"
        line2 = where + (" · " + f.texture if f.texture else "")
        self.line2 = _ElidedLabel(line2)
        grid.addWidget(self.line2, 1, 0)

        if f.fixable:
            self.btn_fix = widgets.SecondaryButton("Fix")
            self.btn_fix.setSizePolicy(_policy("Fixed"), _policy("Fixed"))
            a11y.label(self.btn_fix, "Fix: " + self.headline.text(),
                       titles.fix_sentence(f) or "Apply the fix (undo with Ctrl+Z)")
            if on_fix is not None:
                self.btn_fix.clicked.connect(lambda: on_fix(self.finding))
            self.manual = None
            grid.addWidget(self.btn_fix, 0, 1, _align("AlignRight", "AlignTop"))
        elif f.severity == Severity.INFO:      # notes: nothing to do, so nothing on the right
            self.btn_fix = None
            self.manual = None
        else:
            self.btn_fix = None
            self.manual = widgets.Muted("Manual")
            self.manual.setWordWrap(False)
            a11y.label(self.manual, "Manual", "No automatic fix; open Why? for what to do")
            grid.addWidget(self.manual, 0, 1, _align("AlignRight", "AlignVCenter"))

        self.btn_why = widgets.GhostButton("Why?")
        a11y.label(self.btn_why, "Why: " + self.headline.text(), "Show why this was flagged")
        self.btn_why.clicked.connect(self.toggle_detail)
        grid.addWidget(self.btn_why, 1, 1, _align("AlignRight", "AlignVCenter"))

        self.detail = QtWidgets.QWidget()
        dl = _vbox(self.detail, 0, 4)
        dl.setContentsMargins(0, 4, 0, 0)
        self.detail_text = widgets.Muted(_plain(f.detail or f.message))
        self.detail_text.setSizePolicy(_policy("Ignored"), _policy("Preferred"))
        manual = not f.fixable and f.severity != Severity.INFO
        sentence = titles.fix_sentence(f)
        if not sentence and f.severity == Severity.INFO:      # notes may still carry advice
            sentence = titles.HEADLINES.get(f.rule_id, ("", ""))[1]
        if not sentence and manual:
            sentence = "Manual"
        self.rule_line = widgets.Muted(_plain((sentence + "  " + f.rule_id).strip()))
        self.rule_line.setSizePolicy(_policy("Ignored"), _policy("Preferred"))
        dl.addWidget(self.detail_text)
        dl.addWidget(self.rule_line)
        self.detail.setVisible(False)
        grid.addWidget(self.detail, 2, 0, 1, 2)
        a11y.label(self, self.headline.text(), "")

    def is_expanded(self):
        return not self.detail.isHidden()

    def toggle_detail(self):
        on = self.detail.isHidden()
        self.detail.setVisible(on)
        self.btn_why.setAccessibleDescription("expanded" if on else "collapsed")

    def focusables(self):
        return [w for w in (self.btn_fix, self.btn_why) if w is not None]


class InspectorPanel(QtWidgets.QDockWidget):
    def __init__(self, rt, undo=None, parent=None):
        super().__init__("Material Inspector", parent)
        self.rt, self.undo = rt, undo
        self.setObjectName("MaterialInspectorDock")
        self.materials, self.findings = [], []
        self.reader = None
        self.log = get_logger()
        self.options, self.config_warnings = self._load_options()
        self._scanning = False
        self._cancel = False
        self._rows = []
        self._manual = []
        self._settings = None

        root = QtWidgets.QWidget()
        lay = _vbox(root, 16, 12)
        self.banner = widgets.StatusBanner()
        a11y.label(self.banner.action_button, "Show details")
        lay.addWidget(self.banner)
        self.stack = QtWidgets.QStackedWidget()
        lay.addWidget(self.stack, 1)
        self._pages = {}
        for name, build in (("idle", self._build_idle), ("scanning", self._build_scanning),
                            ("results", self._build_results), ("empty", self._build_empty),
                            ("error", self._build_error)):
            page = QtWidgets.QWidget()
            build(page)
            self._pages[name] = page
            self.stack.addWidget(page)
        self.setWidget(root)
        qss.apply(self)

        # keyboard: Enter = Check my scene on idle (the shortcut only fires while it is visible),
        # Esc = Cancel while scanning
        self._keys = a11y.enter_triggers(self, self.btn_scan)
        self._keys.append(a11y.esc_triggers(self, self.cancel))
        self.chk_pixels.setChecked(self.options.check_pixels)
        self._refresh_status()
        self._go("idle")

    # ------------------------------------------------------------ pages
    def _build_idle(self, page):
        lay = _vbox(page, 0, 8)
        title = widgets.Title("Find what will render wrong in this scene")
        body = QtWidgets.QLabel("Checks every V-Ray, Corona and OpenPBR material. "
                                "Fixes are one click and can be undone.")
        body.setWordWrap(True)
        a11y.label(body, body.text(), "")
        self.btn_scan = widgets.PrimaryButton("Check my scene")
        a11y.label(self.btn_scan, "Check my scene", "Look at every material in the scene (Enter)")
        self.btn_scan.clicked.connect(self.scan)
        self.chk_pixels = QtWidgets.QCheckBox("Also check texture pixels")
        a11y.label(self.chk_pixels, "Also check texture pixels (slower, more thorough)")
        hint = widgets.Muted("(slower, more thorough)")
        hint.setContentsMargins(30, 0, 0, 0)       # under the checkbox text, past the indicator
        self.btn_report = widgets.GhostButton("Export report")
        a11y.label(self.btn_report, "Export report", "Save the last check as HTML or JSON")
        self.btn_report.clicked.connect(self.export_report)
        self.btn_settings = widgets.GhostButton("Settings")
        a11y.label(self.btn_settings, "Settings", "Thresholds, disabled checks, normal maps")
        self.btn_settings.clicked.connect(self.open_settings)
        ghosts = _hbox(16)
        ghosts.addWidget(self.btn_report)
        ghosts.addWidget(self.btn_settings)
        ghosts.addStretch(1)
        self.status = widgets.Muted("")
        a11y.label(self.status, "Settings status", "")

        lay.addWidget(title)
        lay.addWidget(body)
        lay.addSpacing(8)
        lay.addWidget(self.btn_scan)
        lay.addSpacing(4)
        lay.addWidget(self.chk_pixels)
        lay.addWidget(hint)
        lay.addSpacing(4)
        lay.addLayout(ghosts)
        lay.addWidget(self.status)
        lay.addStretch(1)
        a11y.tab_order([self.btn_scan, self.chk_pixels, self.btn_report, self.btn_settings])

    def _build_scanning(self, page):
        lay = _vbox(page, 0, 12)
        self.phase = widgets.Title("Reading materials from the scene")
        a11y.label(self.phase, "Scan progress", "")
        self.skeleton = widgets.SkeletonRows(6)
        self.btn_cancel = widgets.SecondaryButton("Cancel")
        a11y.label(self.btn_cancel, "Cancel", "Stop the check; nothing is changed (Esc)")
        self.btn_cancel.clicked.connect(self.cancel)
        row = _hbox()
        row.addStretch(1)
        row.addWidget(self.btn_cancel)
        row.addStretch(1)
        lay.addWidget(self.phase)
        lay.addWidget(self.skeleton)
        lay.addSpacing(8)
        lay.addLayout(row)
        lay.addStretch(1)

    def _build_results(self, page):
        lay = _vbox(page, 0, 12)
        self.summary = QtWidgets.QLabel("")
        self.summary.setProperty("role", "section")
        self.summary.setWordWrap(True)
        a11y.label(self.summary, "Summary", "")
        self.btn_fix_all = widgets.PrimaryButton("Fix all")
        a11y.label(self.btn_fix_all, "Fix all", "Fix everything that will render wrong (Ctrl+Z undoes)")
        self.btn_fix_all.clicked.connect(self.fix_all_errors)
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(enum(QtCore.Qt, "ScrollBarPolicy", "ScrollBarAlwaysOff"))
        self.scroll.setFrameShape(enum(QtWidgets.QFrame, "Shape", "NoFrame"))
        a11y.label(self.scroll, "Findings", "")
        self.scroll.setWidget(QtWidgets.QWidget())
        self.btn_report_results = widgets.GhostButton("Export report")
        a11y.label(self.btn_report_results, "Export report", "Save this check as HTML or JSON")
        self.btn_report_results.clicked.connect(self.export_report)
        self.btn_again = widgets.GhostButton("Check again")
        a11y.label(self.btn_again, "Check again", "Run the check again")
        self.btn_again.clicked.connect(self.scan)
        foot = _hbox(16)
        foot.addWidget(self.btn_report_results)
        foot.addWidget(self.btn_again)
        foot.addStretch(1)
        lay.addWidget(self.summary)
        lay.addWidget(self.btn_fix_all)
        self.manual_note = widgets.Muted("")
        a11y.label(self.manual_note, "Manual fixes", "")
        self.manual_note.setVisible(False)
        lay.addWidget(self.manual_note)
        lay.addWidget(self.scroll, 1)
        lay.addLayout(foot)

    def _build_empty(self, page):
        lay = _vbox(page, 0, 8)
        self.empty_title = widgets.Title("Nothing to fix.")
        self.empty_title.setAlignment(_align("AlignHCenter"))
        self.empty_body = widgets.Muted("")
        self.empty_body.setAlignment(_align("AlignHCenter"))
        self.btn_report_empty = widgets.GhostButton("Export report")
        a11y.label(self.btn_report_empty, "Export report", "Save this check as HTML or JSON")
        self.btn_report_empty.clicked.connect(self.export_report)
        self.btn_again_empty = widgets.SecondaryButton("Check again")
        a11y.label(self.btn_again_empty, "Check again", "Run the check again")
        self.btn_again_empty.clicked.connect(self.scan)
        row = _hbox(16)
        row.addStretch(1)
        row.addWidget(self.btn_report_empty)
        row.addWidget(self.btn_again_empty)
        row.addStretch(1)
        lay.addSpacing(32)
        lay.addWidget(self.empty_title)
        lay.addWidget(self.empty_body)
        lay.addSpacing(8)
        lay.addLayout(row)
        lay.addStretch(1)
        a11y.tab_order([self.btn_again_empty, self.btn_report_empty])

    def _build_error(self, page):
        lay = _vbox(page, 0, 12)
        self.error_banner = widgets.StatusBanner()
        self.error_banner.show("error", "The scan failed.", "Show log", self._show_log)
        self.error_path = QtWidgets.QLabel("")
        self.error_path.setProperty("role", "path")
        self.error_path.setFont(compat.fixed_font())
        self.error_path.setWordWrap(True)
        self.error_path.setTextInteractionFlags(enum(QtCore.Qt, "TextInteractionFlag", "TextSelectableByMouse"))
        a11y.label(self.error_path, "Log folder", "")
        self.btn_retry = widgets.SecondaryButton("Try again")
        a11y.label(self.btn_retry, "Try again", "Run the check again")
        self.btn_retry.clicked.connect(self.scan)
        row = _hbox()
        row.addWidget(self.btn_retry)
        row.addStretch(1)
        lay.addWidget(self.error_banner)
        lay.addWidget(self.error_path)
        lay.addLayout(row)
        lay.addStretch(1)
        a11y.tab_order([self.error_banner.action_button, self.btn_retry])

    def _go(self, name):
        self.stack.setCurrentWidget(self._pages[name])

    def state(self) -> str:
        cur = self.stack.currentWidget()
        for name, page in self._pages.items():
            if page is cur:
                return name
        return "idle"

    def rows(self) -> list:
        return list(self._rows)

    def summary_text(self) -> str:
        return self.summary.text().replace(_NBSP, " ")

    # ------------------------------------------------------------ settings
    def _load_options(self):
        """Settings never stop the panel opening: any failure means defaults plus a warning."""
        try:
            opt, warns = load_options()
        except Exception as exc:
            self.log.error("settings failed to load\n%s", traceback.format_exc())
            opt, warns = InspectorOptions(), [f"Settings could not be loaded ({exc!r}); using defaults"]
        for w_ in warns:
            self.log.warning(w_)
        return opt, warns

    def _status_line(self) -> str:
        n = len(self.config_warnings)
        return f"{n} settings problem(s), see log" if n else ""

    def _refresh_status(self):
        text = self._status_line()
        self.status.setText(text)
        self.status.setVisible(bool(text))

    def open_settings(self):
        dlg = self._settings_dialog()
        compat.exec_dialog(dlg)

    def _settings_dialog(self):
        path = write_example()
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Settings")
        dlg.setObjectName("MaterialInspectorSettings")
        qss.apply(dlg)
        lay = _vbox(dlg, 16, 8)
        title = widgets.Title("Settings")
        hint = widgets.Muted("Edit this file, save it, then press Reload.")
        where = QtWidgets.QLabel(path)
        where.setProperty("role", "path")
        where.setFont(compat.fixed_font())
        where.setWordWrap(True)
        where.setTextInteractionFlags(enum(QtCore.Qt, "TextInteractionFlag", "TextSelectableByMouse"))
        a11y.label(where, "Settings file", path)
        state = widgets.Muted(self._status_line() or "No settings problems.")
        a11y.label(state, "Settings status", "")
        b_open = widgets.SecondaryButton("Open settings file")
        a11y.label(b_open, "Open settings file", "Open the file in your text editor")
        b_reload = widgets.SecondaryButton("Reload")
        a11y.label(b_reload, "Reload", "Read the settings file again")
        b_close = widgets.SecondaryButton("Close")
        a11y.label(b_close, "Close", "Close settings (Esc)")

        def do_open():
            try:
                os.startfile(path)  # type: ignore[attr-defined]  (Windows only)
            except Exception:
                pass

        def do_reload():
            self.options, self.config_warnings = self._load_options()
            self.chk_pixels.setChecked(self.options.check_pixels)
            self._refresh_status()
            state.setText(self._status_line() or "No settings problems.")

        b_open.clicked.connect(do_open)
        b_reload.clicked.connect(do_reload)
        b_close.clicked.connect(dlg.accept)
        row = _hbox()
        row.addWidget(b_open)
        row.addWidget(b_reload)
        row.addStretch(1)
        row.addWidget(b_close)
        lay.addWidget(title)
        lay.addWidget(hint)
        lay.addWidget(where)
        lay.addWidget(state)
        lay.addSpacing(8)
        lay.addLayout(row)
        a11y.tab_order([b_open, b_reload, b_close])
        dlg.resize(420, dlg.sizeHint().height())
        self._settings = dlg
        return dlg

    # ------------------------------------------------------------ actions
    def _notify(self, text):
        QtWidgets.QMessageBox.information(self, "Material Inspector", text)

    def _show_log(self):
        path = log_dir()
        try:
            os.startfile(path)  # type: ignore[attr-defined]  (Windows only)
        except Exception:
            self._notify("Log folder:\n" + path)

    def _set_phase(self, text):
        self.phase.setText(text)
        self.phase.setAccessibleName(text)

    def _progress(self, i, n, name):
        self._set_phase(f"Checking material {i} of {n}")
        QtWidgets.QApplication.processEvents()
        return not self._cancel

    def cancel(self):
        """Stop a running scan at the next material (Esc). No-op when idle."""
        if self._scanning:
            self._cancel = True

    def scan(self):
        if self._scanning:
            return
        self._scanning, self._cancel = True, False
        self.btn_scan.setEnabled(False)
        self.banner.hide()
        self._set_phase("Reading materials from the scene")
        self._go("scanning")
        self.btn_cancel.setFocus()
        QtWidgets.QApplication.processEvents()
        try:
            self.reader = SceneReader(self.rt)
            self.materials = self.reader.materials()
            self.options.check_pixels = self.chk_pixels.isChecked()
            self.findings = inspect(self.materials, self.options, progress=self._progress)
            s = summary(self.findings)
            self.log.info("scan: %d materials, %d errors, %d warnings; unresolved props: %s",
                          len(self.materials), s["error"], s["warning"],
                          self.reader.log.as_dict()["missing"])
        except ScanCancelled:
            self.log.info("scan cancelled")
            self.findings = []
            self._go("idle")
            self.banner.show("info", "Scan stopped. Nothing was changed.")
            self.btn_scan.setEnabled(True)
            self.btn_scan.setFocus()
            return
        except Exception:
            self.log.error("scan failed\n%s", traceback.format_exc())
            self.error_path.setText("Details are in the log:\n" + log_dir())
            self._go("error")
            self._notify("Scan failed. Details in " + log_dir())
            return
        finally:
            self._scanning = False
            self.btn_scan.setEnabled(True)
        self._populate()

    def _summary(self):
        s = summary(self.findings)
        parts = []
        if s["error"]:
            parts.append(_plural(s["error"], "thing will render wrong", "things will render wrong"))
        elif not s["warning"]:
            parts.append("Nothing will render wrong")
        if s["warning"]:
            parts.append(f"{s['warning']} worth a look")
        parts.append(_plural(len(self.materials), "material checked", "materials checked"))
        # each part keeps its words together, so a narrow dock wraps only at the separators
        return " · ".join(p.replace(" ", _NBSP) for p in parts)

    def _populate(self):
        old = self.scroll.takeWidget()
        if old is not None:
            old.deleteLater()               # a row's Fix button may still be on the call stack
        self._rows = []
        if not self.findings:
            n = len(self.materials)
            self.empty_body.setText(_plural(n, "material checked", "materials checked") + ", all fine."
                                    if n else "No materials found in this scene.")
            self._go("empty")
            self.btn_again_empty.setFocus()
            return

        content = QtWidgets.QWidget()
        lay = _vbox(content, 0, 8)
        lay.setContentsMargins(0, 0, 8, 0)      # room for the scroll bar
        groups = {"Will render wrong": [], "Worth a look": [], "Notes": []}
        for f in self.findings:
            groups[titles.group(f)].append(f)
        order = []
        for name in ("Will render wrong", "Worth a look"):
            fs = groups[name]
            if not fs:
                continue
            if order:
                lay.addSpacing(8)
            lay.addWidget(widgets.SectionHeader(f"{name} ({len(fs)})"))
            for f in fs:
                row = FindingRow(f, self.fix_one)
                self._rows.append(row)
                order += row.focusables()
                lay.addWidget(row)
        if groups["Notes"]:
            lay.addSpacing(8)
            notes = widgets.MoreOptions(title=f"Notes ({len(groups['Notes'])})")
            box = QtWidgets.QWidget()
            bl = _vbox(box, 0, 8)
            for f in groups["Notes"]:
                row = FindingRow(f, self.fix_one)
                self._rows.append(row)
                bl.addWidget(row)
            notes.set_content(box)
            notes.set_expanded(False)
            order.append(notes.header)
            lay.addWidget(notes)
        lay.addStretch(1)
        self.scroll.setWidget(content)

        self.summary.setText(self._summary())
        self.summary.setAccessibleName(self.summary.text())
        n_fix = sum(1 for f in self.findings if f.severity == Severity.ERROR and f.fixable)
        self.btn_fix_all.setText(f"Fix all {n_fix}")
        a11y.label(self.btn_fix_all, f"Fix all {n_fix}",
                   "Fix everything that will render wrong (Ctrl+Z undoes)")
        self.btn_fix_all.setVisible(n_fix > 0)
        n_hand = summary(self.findings)["error"] - n_fix
        self.manual_note.setText(_plural(n_hand, "needs", "need") + " a manual fix" if n_hand > 0 else "")
        self.manual_note.setVisible(n_hand > 0)
        self._go("results")
        a11y.tab_order([self.btn_fix_all] + order + [self.btn_report_results, self.btn_again])
        (self.btn_fix_all if n_fix else self.btn_again).setFocus()

    def _record(self, f):
        i = f.material_index
        if i is None or not 0 <= i < len(self.materials):
            return None
        return self.materials[i]

    def _apply(self, fs):
        applier = FixApplier(self.rt, self.undo)
        done, manual = 0, []
        for f in fs:
            mat = self._record(f)
            if f.fix is None or mat is None:
                continue
            r = applier.apply(f, mat)
            self.log.info("fix %s on %s: %s", f.rule_id, f.material, r.message)
            done += r.ok
            if not r.ok:
                manual.append(_plain(f"{f.material}: {r.message}"))
        self._notify(f"Applied {done} fix(es)." + ("\n\nFix manually:\n" + "\n".join(manual[:20]) if manual else ""))
        self.scan()
        self._manual = manual
        fixed = "Fixed " + _plural(done, "thing.", "things.")
        if manual:
            need = _plural(len(manual), "needs", "need")
            self.banner.show("warning" if not done else "ok", f"{fixed} {need} a manual fix.",
                             "Show details", self._show_manual)
        else:
            self.banner.show("ok", fixed)

    def _show_manual(self):
        self._notify("Fix manually:\n" + "\n".join(self._manual[:20]))

    def fix_one(self, finding):
        """Row Fix button: apply one fix, no confirmation (Ctrl+Z undoes it)."""
        self._apply([finding])

    def fix_all_errors(self):
        todo = [f for f in self.findings if f.severity == Severity.ERROR and f.fix]
        if not todo:
            self._notify("No automatically fixable errors."); return
        n = len(todo)
        ok = QtWidgets.QMessageBox.question(
            self, "Material Inspector",
            f"Fix {n} thing{'' if n == 1 else 's'} now? Each one can be undone with Ctrl+Z.")
        if ok == enum(QtWidgets.QMessageBox, "StandardButton", "Yes"):
            self._apply(todo)

    def export_report(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save report", "material_report.html",
                                                        "HTML (*.html);;JSON (*.json)")
        if not path:
            return
        scene = str(getattr(self.rt, "maxFilePath", "")) + str(getattr(self.rt, "maxFileName", ""))
        extra = {"property_resolution": self.reader.log.as_dict()} if self.reader else None
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(to_json(self.findings, scene, extra) if path.lower().endswith(".json")
                     else to_html(self.findings, scene))


_panel = None


def show():
    """Entry point called from the macroscript."""
    global _panel
    from pymxs import runtime as rt, undo  # only importable inside 3ds Max
    try:
        import qtmax
        main = qtmax.GetQMaxMainWindow()
    except Exception:
        main = None
    if _panel is None:
        _panel = InspectorPanel(rt, undo, main)
        if main is not None:
            main.addDockWidget(enum(QtCore.Qt, "DockWidgetArea", "RightDockWidgetArea"), _panel)
            _panel.setFloating(False)
    _panel.show(); _panel.raise_()
    return _panel
