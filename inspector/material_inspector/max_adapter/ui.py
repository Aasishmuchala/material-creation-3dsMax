"""Dockable Material Inspector panel for 3ds Max (PySide6, PySide2 fallback)."""
from __future__ import annotations

import os

try:                                    # 3ds Max 2025+
    from PySide6 import QtCore, QtWidgets
except ImportError:                     # 3ds Max 2022–2024
    from PySide2 import QtCore, QtWidgets  # type: ignore

import traceback

from ..core.config import load_options, write_example
from ..core.inspector import inspect, summary
from ..core.log import get_logger, log_dir
from ..core.model import Severity
from ..core.report import to_html, to_json
from .fixes import FixApplier
from .scene import SceneReader

_SEV_ORDER = {Severity.ERROR: "●", Severity.WARNING: "▲", Severity.INFO: "·"}


class InspectorPanel(QtWidgets.QDockWidget):
    def __init__(self, rt, undo=None, parent=None):
        super().__init__("Material Inspector", parent)
        self.rt, self.undo = rt, undo
        self.setObjectName("MaterialInspectorDock")
        self.materials, self.findings = [], []
        self.reader = None
        self.log = get_logger()
        self.options, warns = load_options()
        for w_ in warns:
            self.log.warning(w_)

        w = QtWidgets.QWidget(); lay = QtWidgets.QVBoxLayout(w)
        bar = QtWidgets.QHBoxLayout()
        self.btn_scan = QtWidgets.QPushButton("Scan scene")
        self.btn_fix = QtWidgets.QPushButton("Fix selected")
        self.btn_fix_all = QtWidgets.QPushButton("Fix all errors")
        self.btn_report = QtWidgets.QPushButton("Export report…")
        self.btn_settings = QtWidgets.QPushButton("Settings…")
        self.chk_pixels = QtWidgets.QCheckBox("Check texture pixels")
        for b in (self.btn_scan, self.btn_fix, self.btn_fix_all, self.btn_report, self.btn_settings):
            bar.addWidget(b)
        bar.addStretch(1); bar.addWidget(self.chk_pixels)
        lay.addLayout(bar)
        self.status = QtWidgets.QLabel("Press Scan scene."); lay.addWidget(self.status)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["", "Material / finding", "Texture", "Fix"])
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.tree.setColumnWidth(0, 28); self.tree.setColumnWidth(1, 360)
        lay.addWidget(self.tree, 1)
        self.detail = QtWidgets.QLabel(); self.detail.setWordWrap(True); lay.addWidget(self.detail)
        self.setWidget(w)

        self.btn_scan.clicked.connect(self.scan)
        self.btn_fix.clicked.connect(self.fix_selected)
        self.btn_fix_all.clicked.connect(self.fix_all_errors)
        self.btn_report.clicked.connect(self.export_report)
        self.btn_settings.clicked.connect(self.open_settings)
        self.chk_pixels.setChecked(self.options.check_pixels)
        self.tree.itemSelectionChanged.connect(self._show_detail)

    # ------------------------------------------------------------ actions
    def _notify(self, text):
        QtWidgets.QMessageBox.information(self, "Material Inspector", text)

    def scan(self):
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            self.reader = SceneReader(self.rt)
            self.materials = self.reader.materials()
            self.options.check_pixels = self.chk_pixels.isChecked()
            self.findings = inspect(self.materials, self.options)
            s = summary(self.findings)
            self.log.info("scan: %d materials, %d errors, %d warnings; unresolved props: %s",
                          len(self.materials), s["error"], s["warning"],
                          self.reader.log.as_dict()["missing"])
        except Exception:
            self.log.error("scan failed\n%s", traceback.format_exc())
            QtWidgets.QApplication.restoreOverrideCursor()
            self._notify(f"Scan failed — details in {log_dir()}")
            return
        QtWidgets.QApplication.restoreOverrideCursor()
        self._populate()

    def open_settings(self):
        path = write_example()
        self._notify(f"Settings file:\n{path}\n\nEdit it, then press Scan scene again.")
        try:
            os.startfile(path)  # type: ignore[attr-defined]  (Windows only)
        except Exception:
            pass
        self.options, warns = load_options()

    def _populate(self):
        self.tree.clear()
        by_mat = {}
        for f in self.findings:
            by_mat.setdefault(f.material, []).append(f)
        for name, fs in by_mat.items():
            worst = min(fs, key=lambda f: list(_SEV_ORDER).index(f.severity)).severity
            top = QtWidgets.QTreeWidgetItem(["" if worst == Severity.INFO else _SEV_ORDER[worst], name, "", ""])
            for f in fs:
                child = QtWidgets.QTreeWidgetItem([_SEV_ORDER[f.severity], f"{f.rule_id}  {f.message}",
                                                   f.texture or "", f.fix.description if f.fix else "manual"])
                child.setData(0, QtCore.Qt.UserRole, self.findings.index(f))
                top.addChild(child)
            self.tree.addTopLevelItem(top)
            top.setExpanded(worst == Severity.ERROR)
        s = summary(self.findings)
        self.status.setText(f"{len(self.materials)} materials · {s['error']} errors · "
                            f"{s['warning']} warnings · {s['fixable']} fixable")

    def _selected_findings(self):
        idx = [it.data(0, QtCore.Qt.UserRole) for it in self.tree.selectedItems()]
        return [self.findings[i] for i in idx if i is not None]

    def _show_detail(self):
        fs = self._selected_findings()
        self.detail.setText(fs[0].detail if fs else "")

    def _apply(self, fs):
        applier = FixApplier(self.rt, self.undo)
        mats = {m.name: m for m in self.materials}
        done, manual = 0, []
        for f in fs:
            if f.fix is None or f.material not in mats:
                continue
            r = applier.apply(f, mats[f.material])
            self.log.info("fix %s on %s: %s", f.rule_id, f.material, r.message)
            done += r.ok
            if not r.ok:
                manual.append(f"{f.material}: {r.message}")
        self._notify(f"Applied {done} fix(es)." + ("\n\nFix manually:\n" + "\n".join(manual[:20]) if manual else ""))
        self.scan()

    def fix_selected(self):
        self._apply(self._selected_findings())

    def fix_all_errors(self):
        todo = [f for f in self.findings if f.severity == Severity.ERROR and f.fix]
        if not todo:
            self._notify("No automatically fixable errors."); return
        ok = QtWidgets.QMessageBox.question(self, "Material Inspector",
                                            f"Apply {len(todo)} fixes? Each one can be undone with Ctrl+Z.")
        if ok == QtWidgets.QMessageBox.StandardButton.Yes:
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
            main.addDockWidget(QtCore.Qt.RightDockWidgetArea, _panel)
            _panel.setFloating(False)
    _panel.show(); _panel.raise_()
    return _panel
