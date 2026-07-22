"""MatForge UI — dockable dialog inside 3ds Max.

Run from Max:  Scripting > Run Script... > matforge/run_matforge.py
Flow: pick reference image -> name -> class -> 2K/4K/8K -> Create.
Map generation shells out to system Python (Pillow/numpy live there,
Max's bundled Python stays untouched); wiring happens in-process.
"""
import json
import os
import subprocess
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from core.recipes import class_choices  # noqa: E402
from maxplugin import builder  # noqa: E402

from pymxs import runtime as rt  # noqa: E402

# system interpreter that has Pillow+numpy; edit if your setup differs
PYTHON_CMD = ["py", "-3.12"]
CLI = os.path.join(_REPO, "forge_cli.py")     # Fast: deterministic heuristic
FAL = os.path.join(_REPO, "forge_fal.py")     # Ultra: fal PATINA AI (4K)

_CLASSES = class_choices()  # [(key, label)]


def _fal_key():
    """FAL_KEY from process env, else the persisted User env var, else the
    hardcoded _falkey.py fallback."""
    k = os.environ.get("FAL_KEY")
    if k:
        return k
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as h:
            v = winreg.QueryValueEx(h, "FAL_KEY")[0]
            if v:
                return v
    except Exception:
        pass
    try:
        import _falkey
        return _falkey.FAL_KEY
    except Exception:
        return None


def _ui():
    return rt.MatForgeRollout


def browse_image():
    f = rt.getOpenFileName(
        caption="MatForge — pick reference image",
        types="Images|*.jpg;*.jpeg;*.png;*.tif;*.tiff;*.bmp;*.webp|All|*.*")
    if f:
        _ui().edtImg.text = f
        # prefill name from filename if empty
        if not _ui().edtName.text:
            base = os.path.splitext(os.path.basename(f))[0]
            _ui().edtName.text = "".join(
                c if c.isalnum() else "_" for c in base)


def _sanitize(name):
    """Folder-safe material name (Windows rejects : * ? " < > | in paths)."""
    cleaned = "".join(c if c.isalnum() else "_" for c in name).strip("_")
    return cleaned or "MatForge_Material"


def _run_create(img, name, mclass, res, engine, seamless, assign):
    """Shared core used by both the rollout and the web panel. Generates the
    full slate of maps (heuristic 'fast' or fal-PATINA 'ultra') and wires the
    VRayMtl onto a Material Editor sphere. Returns a result dict:
      {state: 'ok'|'err', text, material?, slot?, notes?}
    """
    name = _sanitize(name or "MatForge_Material")
    if not img or not os.path.isfile(img):
        return {"state": "err", "text": "Pick a reference image first."}

    env = dict(os.environ)
    if engine == "ultra":
        key = _fal_key()
        if not key:
            return {"state": "err",
                    "text": "Ultra (fal PATINA) needs FAL_KEY. Use Fast."}
        env["FAL_KEY"] = key
        upscale = "4" if res in ("4k", "8k") else "2"
        cmd = PYTHON_CMD + [FAL, img, "--name", name, "--type", mclass,
                            "--upscale", upscale]
    else:
        cmd = PYTHON_CMD + [CLI, img, "--name", name, "--type", mclass,
                            "--res", res]
        if not seamless:
            cmd.append("--no-seamless")

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=1800, env=env)
    except FileNotFoundError:
        return {"state": "err", "text": "System Python not found "
                "(edit PYTHON_CMD)."}
    except subprocess.TimeoutExpired:
        return {"state": "err", "text": "Map generation timed out."}
    except OSError as e:
        return {"state": "err", "text": "Could not launch Python: %s" % e}

    if proc.returncode != 0:
        detail = ""
        try:
            detail = json.loads(
                (proc.stdout or "").strip().splitlines()[-1]).get("error", "")
        except Exception:
            pass
        print("[MatForge] CLI stderr:\n" + (proc.stderr or ""))
        return {"state": "err",
                "text": "Map generation failed: " + (detail or "see listener")}

    result = None
    for line in reversed((proc.stdout or "").strip().splitlines()):
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict) and ("manifest" in obj or "ok" in obj):
            result = obj
            break
    if not result or "manifest" not in result:
        return {"state": "err", "text": "Could not read generator output."}

    try:
        out = builder.build_from_manifest(result["manifest"], slot=None,
                                          assign=assign)
    except Exception as e:
        return {"state": "err", "text": "Material wiring failed: %s" % e}

    notes = list(result.get("warnings") or [])
    misses = [l for l in out.get("log", []) if "MISS" in l]
    if misses:
        notes.append("%d V-Ray propert%s could not be set" % (
            len(misses), "y" if len(misses) == 1 else "ies"))
    return {"state": "ok", "material": out["material"], "slot": out["slot"],
            "notes": notes,
            "text": "Done: '%s' -> editor slot %d%s" % (
                out["material"], out["slot"],
                "  (with notes)" if notes else "")}


def create_material():
    """Rollout entry point."""
    ui = _ui()
    r = _run_create(
        img=ui.edtImg.text.strip(),
        name=ui.edtName.text.strip() or "MatForge_Material",
        mclass=_CLASSES[ui.ddClass.selection - 1][0],
        res=["2k", "4k", "8k"][ui.ddRes.selection - 1],
        engine=["fast", "ultra"][ui.ddEngine.selection - 1],
        seamless=bool(ui.chkSeamless.checked),
        assign=bool(ui.chkAssign.checked))
    ui.lblStatus.text = r["text"]
    if r["state"] == "err":
        rt.messageBox(r["text"], title="MatForge")
    elif r.get("notes"):
        rt.messageBox("Created with notes:\n\n- " + "\n- ".join(r["notes"]),
                      title="MatForge")


# ---- web-panel bridge entry points (called by matforge_panel.ms) ----

def create_from_panel(payload_json):
    """Called by the panel bridge with a JSON string of params. Returns a
    compact JSON status string the bridge feeds back to the panel."""
    try:
        p = json.loads(payload_json)
        r = _run_create(img=p.get("img", ""), name=p.get("name", ""),
                        mclass=p.get("cls", "generic"), res=p.get("res", "4k"),
                        engine=p.get("eng", "fast"), seamless=True,
                        assign=bool(p.get("assign")))
    except Exception as e:
        r = {"state": "err", "text": "panel error: %s" % e}
    return json.dumps(r)


def browse_for_panel():
    """Open a native file dialog; return the chosen path (bridge sets it in
    the panel via mfImage)."""
    f = rt.getOpenFileName(
        caption="MatForge — pick reference image",
        types="Images|*.jpg;*.jpeg;*.png;*.tif;*.tiff;*.bmp;*.webp|All|*.*")
    return f or ""


# The matforge_panel.ms bridge exchanges data via MAXScript globals (avoids
# fragile string escaping across the JS->title->MAXScript->Python hops).

def _bridge_browse():
    rt.mfBridgeImage = browse_for_panel()


def _bridge_create():
    import urllib.parse
    raw = str(getattr(rt, "mfBridgePayload", "") or "")
    try:
        raw = urllib.parse.unquote(raw)
    except Exception:
        pass
    try:
        p = json.loads(raw)
        r = _run_create(p.get("img", ""), p.get("name", ""),
                        p.get("cls", "generic"), p.get("res", "4k"),
                        p.get("eng", "fast"), True, bool(p.get("assign")))
    except Exception as e:
        r = {"state": "err", "text": "panel error: %s" % e}
    rt.mfBridgeState = r.get("state", "ok")
    rt.mfBridgeText = r.get("text", "")


ROLLOUT_MXS = """
try (destroyDialog MatForgeRollout) catch()
rollout MatForgeRollout "MatForge v1" width:340
(
    edittext edtImg "Image:" fieldWidth:230 across:2 align:#left
    button btnBrowse "..." width:30 align:#right
    edittext edtName "Name:" fieldWidth:230
    dropdownlist ddClass "Material type:" items:#(%CLASS_ITEMS%)
    dropdownlist ddRes "Resolution:" items:#("2K (2048)","4K (4096)","8K (8192)") selection:2
    dropdownlist ddEngine "Engine:" items:#("Fast  (offline, no key)","Ultra  (fal PATINA AI)") selection:1
    checkbox chkSeamless "Make seamless (tileable)" checked:true
    checkbox chkAssign "Assign to selected objects" checked:false
    button btnCreate "Create Material  ->  Editor Sphere" width:320 height:32
    label lblStatus "Ready." align:#left

    on btnBrowse pressed do python.Execute "import maxplugin.forge_max as _mf; _mf.browse_image()"
    on btnCreate pressed do python.Execute "import maxplugin.forge_max as _mf; _mf.create_material()"
)
createDialog MatForgeRollout
"""


def show():
    items = ",".join('"%s"' % label for _, label in _CLASSES)
    rt.execute(ROLLOUT_MXS.replace("%CLASS_ITEMS%", items))


if __name__ == "__main__":
    show()
