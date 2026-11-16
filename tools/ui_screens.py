"""Render every state of the MatForge dock and the Material Inspector dock to PNG.

Run from the repo root with the Qt venv:
    .venv-qt/bin/python tools/ui_screens.py

Headless (QT_QPA_PLATFORM=offscreen), against the mock pymxs runtime and the fake
generator, so no 3ds Max is needed. Writes docs/ui/screens/<panel>_<state>_<width>.png
and docs/ui/screens/index.md. Exits 1 if a state raises or a PNG is over 80 KB.
"""
import importlib
import os
import sys
import tempfile
import traceback

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_LOGGING_RULES", "*.warning=false;qt.qpa.*=false")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "ui", "screens")
WIDTHS = (320, 400, 560)
HEIGHT = 700
MAX_BYTES = 80 * 1024

# The Inspector path goes first so `tests.fakert` resolves to inspector/tests.
for _p in (os.path.join(ROOT, "tests"), ROOT, os.path.join(ROOT, "inspector")):
    if _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)

TMP = tempfile.mkdtemp(prefix="ui_screens_")
os.environ["MATERIAL_INSPECTOR_CONFIG"] = os.path.join(TMP, "inspector.json")
os.environ["LOCALAPPDATA"] = TMP

from PySide6 import QtWidgets  # noqa: E402

# A QApplication must exist before maxplugin.forge_qt is imported.
APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

from PIL import Image  # noqa: E402

MATFORGE_STATES = ("idle", "loaded", "loaded_more", "working", "done", "done_miss",
                   "error_nokey", "settings")
INSPECTOR_STATES = ("idle", "scanning", "results", "results_why", "empty", "error",
                    "fixed")

written = []      # (panel, state, width, filename)
failures = []


def _pump():
    APP.processEvents()
    APP.processEvents()


def snap(widget, panel, state, width):
    widget.resize(width, HEIGHT)
    widget.show()
    _pump()
    name = "%s_%s_%d.png" % (panel, state, width)
    path = os.path.join(OUT, name)
    if not widget.grab().toImage().save(path):
        raise RuntimeError("could not save " + path)
    img = Image.open(path).convert("RGB").quantize(256)
    img.save(path, optimize=True)
    size = os.path.getsize(path)
    if size > MAX_BYTES:
        raise RuntimeError("%s is %d bytes (limit %d)" % (name, size, MAX_BYTES))
    written.append((panel, state, width, name))


def run_state(panel, state, build, widths=WIDTHS):
    """build() -> widget (already driven into the state). Fresh widget per width."""
    for w in widths:
        widget = None
        try:
            widget = build()
            snap(widget, panel, state, w)
        except Exception:
            failures.append("%s %s %d" % (panel, state, w))
            traceback.print_exc()
        finally:
            if widget is not None:
                try:
                    widget.close()
                    widget.deleteLater()
                    _pump()
                except Exception:
                    pass


# ---------------------------------------------------------------- fixtures

def _write_png(path, size=8, grey=128):
    img = Image.new("RGB", (size, size))
    img.putdata([((grey + x * 9 + y * 5) % 256,) * 3 for y in range(size) for x in range(size)])
    img.save(path)


def matforge_fixtures():
    import mock_pymxs
    _builder, rt = mock_pymxs.install(renderer="vray")
    import maxplugin.forge_max as fm
    importlib.reload(fm)
    from maxplugin import forge_qt

    photo = os.path.join(TMP, "Oak floor.png")
    _write_png(photo, 8, 140)
    maps = {}
    for i, key in enumerate(("albedo", "roughness", "normal", "height", "metalness")):
        p = os.path.join(TMP, "Oak_floor_%s.png" % key)
        _write_png(p, 8, 40 + i * 40)
        maps[key] = p
    result = {
        "state": "ok", "material": "Oak_floor", "slot": 3, "mclass": "wood_interior",
        "materials": [{"renderer": "vray", "material": "Oak_floor", "slot": 3},
                      {"renderer": "corona", "material": "Oak_floor", "slot": 4}],
        "notes": ["Albedo clamp: 2.1% of pixels moved into range"],
        "misses": [], "assigned": False, "maps": maps,
    }
    return rt, forge_qt, photo, result


def build_matforge(rt, forge_qt, photo, result, state):
    dock = forge_qt.MatForgeDock(rt=rt)
    if state == "idle":
        return dock
    if not dock.load_image(photo):
        raise RuntimeError("load_image failed")
    if state == "loaded":
        return dock
    if state == "loaded_more":
        dock.grid_for("metal_brushed").set_current("metal_brushed")
        dock.more.set_expanded(True)
        return dock
    if state == "working":
        dock._show_page("working")
        dock.duration_label.setText(forge_qt.DURATION["fast"])
        dock.set_phase("Making the maps")
        return dock
    if state == "done":
        dock.set_done(dict(result))
        return dock
    if state == "done_miss":
        r = dict(result)
        r["misses"] = ["V-Ray: refraction glossiness is not available on this version"]
        dock.set_done(r)
        return dock
    if state == "error_nokey":
        dock.set_error("Best needs a fal key.", "Add key in Settings", dock.open_settings)
        return dock
    if state == "settings":
        return dock.open_settings()
    raise ValueError(state)


def inspector_fixtures():
    from material_inspector.max_adapter import ui
    from tests.fakert import FakeRT
    from tests.test_scene_and_fixes import vray_scene
    ui.InspectorPanel._notify = lambda self, t: None
    QtWidgets.QMessageBox.question = lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes
    return ui, FakeRT, vray_scene


def build_inspector(ui, FakeRT, vray_scene, state):
    if state == "empty":
        p = ui.InspectorPanel(FakeRT([]))
        p.scan()
        return p
    if state == "error":
        p = ui.InspectorPanel(vray_scene())
        orig = ui.SceneReader.materials
        ui.SceneReader.materials = lambda self: 1 / 0
        try:
            p.scan()
        finally:
            ui.SceneReader.materials = orig
        return p
    p = ui.InspectorPanel(vray_scene())
    if state == "idle":
        return p
    if state == "scanning":
        p._go("scanning")
        p._set_phase("Checking material 12 of 48")
        return p
    p.scan()
    if state == "results":
        return p
    if state == "results_why":
        rows = p.rows()
        if rows:
            rows[0].toggle_detail()
        return p
    if state == "fixed":
        p.fix_all_errors()
        return p
    raise ValueError(state)


def write_index():
    lines = ["# UI state gallery", "",
             "Generated by `tools/ui_screens.py`; do not edit by hand. "
             "See `../README.md` for how to regenerate and what to check.", ""]
    for panel, title, states in (("matforge", "MatForge dock", MATFORGE_STATES),
                                 ("inspector", "Material Inspector dock", INSPECTOR_STATES)):
        lines += ["## " + title, "",
                  "| State | " + " | ".join("%d px" % w for w in WIDTHS) + " |",
                  "|---|" + "---|" * len(WIDTHS)]
        for state in states:
            cells = []
            for w in WIDTHS:
                name = "%s_%s_%d.png" % (panel, state, w)
                cells.append("![%s %s at %d px](%s)" % (panel, state.replace("_", " "), w, name))
            lines.append("| %s | %s |" % (state, " | ".join(cells)))
        lines.append("")
    with open(os.path.join(OUT, "index.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def main():
    os.makedirs(OUT, exist_ok=True)
    for name in os.listdir(OUT):
        if name.endswith(".png"):
            os.remove(os.path.join(OUT, name))

    try:
        rt, forge_qt, photo, result = matforge_fixtures()
        for state in MATFORGE_STATES:
            run_state("matforge", state,
                      lambda s=state: build_matforge(rt, forge_qt, photo, result, s))
    except Exception:
        failures.append("matforge setup")
        traceback.print_exc()

    try:
        ui, FakeRT, vray_scene = inspector_fixtures()
        for state in INSPECTOR_STATES:
            run_state("inspector", state,
                      lambda s=state: build_inspector(ui, FakeRT, vray_scene, s))
    except Exception:
        failures.append("inspector setup")
        traceback.print_exc()

    if failures:
        print("FAILED: " + ", ".join(failures), file=sys.stderr)
        return 1
    write_index()
    print("wrote %d screens" % len(written))
    return 0


if __name__ == "__main__":
    sys.exit(main())
