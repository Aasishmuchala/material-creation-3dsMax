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

import mfconfig  # noqa: E402

from core.recipes import class_choices  # noqa: E402
from maxplugin import builder  # noqa: E402

from pymxs import runtime as rt  # noqa: E402

CLI = os.path.join(_REPO, "forge_cli.py")     # Fast: deterministic heuristic
FAL = os.path.join(_REPO, "forge_fal.py")     # Ultra: fal PATINA AI (4K)

_CLASSES = class_choices()  # [(key, label)]

# Map generation runs in a SYSTEM Python (with Pillow+numpy), never Max's own
# Python — so this works identically on Max 2022 (Py3.7) through 2027 (Py3.13).
_PYBIN = None


def _python():
    """First system interpreter that has Pillow+numpy. Resolved once and
    cached, so a box without 'py -3.12' still works via any Python 3."""
    global _PYBIN
    if _PYBIN is not None:
        return _PYBIN
    cflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    for cand in ([["py", "-3.12"], ["py", "-3"], ["python"], ["python3"]]):
        try:
            r = subprocess.run(cand + ["-c", "import PIL, numpy"],
                               capture_output=True, timeout=20,
                               creationflags=cflags)
            if r.returncode == 0:
                _PYBIN = cand
                return cand
        except Exception:
            continue
    _PYBIN = ["py", "-3.12"]   # fall back; fails later with a clear message
    return _PYBIN


def _fal_key():
    return mfconfig.get_fal_key()


def set_ie_emulation():
    """Make the .NET WebBrowser render as IE11 edge (default is IE7 doc mode,
    where the panel's modern HTML/JS wouldn't run). Set before the control is
    created; takes effect next time the panel opens."""
    try:
        import winreg
        key = (r"Software\Microsoft\Internet Explorer\Main\FeatureControl"
               r"\FEATURE_BROWSER_EMULATION")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
            winreg.SetValueEx(k, "3dsmax.exe", 0, winreg.REG_DWORD, 11001)
        return True
    except Exception:
        return False


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
    extra_note = None
    pybin = _python()
    if engine == "ultra":
        key = _fal_key()
        if not key:
            return {"state": "err",
                    "text": "Ultra (fal PATINA) needs a fal key — add it in "
                    "Settings, or use Fast."}
        env["FAL_KEY"] = key
        upscale = "4" if res in ("4k", "8k") else "2"
        if res == "8k":                    # PATINA's max is 4K
            extra_note = "Ultra caps at 4K — generated at 4096px, not 8K."
        cmd = pybin + [FAL, img, "--name", name, "--type", mclass,
                       "--upscale", upscale]
    else:
        cmd = pybin + [CLI, img, "--name", name, "--type", mclass,
                       "--res", res]
        if not seamless:
            cmd.append("--no-seamless")

    # don't flash a console window when launched from the GUI 3dsmax.exe
    cflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=1800, env=env, creationflags=cflags)
    except FileNotFoundError:
        return {"state": "err", "text": "No system Python 3 with Pillow+numpy "
                "found (install Python 3 + `pip install Pillow numpy`)."}
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
    if extra_note:
        notes.append(extra_note)
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

def chat_reply(question):
    """Answer a user question via Fable-5 (omega). Used by the Help chat."""
    system = ("You are the in-panel assistant for MatForge, a 3ds Max + V-Ray "
              "material-creation plugin (reference image -> physically-correct "
              "VRayMtl on a Material Editor sphere; Fast=heuristic maps, "
              "Ultra=fal PATINA AI + Fable-5 prompts). Help the user with "
              "MatForge, V-Ray materials, and the archviz workflow. Be concise "
              "and practical (a few sentences).")
    try:
        return mfconfig.omega_message(
            [{"type": "text", "text": str(question)[:2000]}],
            max_tokens=800, system=system, timeout=45)
    except Exception as e:
        return "Chat unavailable: %s (check the omega key in Settings)." % e


# --- bridge: MAXScript sets rt.mfBridgePayload from the panel's mfGetPayload,
#     then calls one of these; results go back via other rt.* globals. ---

def _bridge_browse():
    rt.mfBridgeImage = browse_for_panel()


def _payload():
    try:
        return json.loads(str(getattr(rt, "mfBridgePayload", "") or "") or "{}")
    except Exception:
        return {}


def _bridge_create():
    p = _payload()
    try:
        r = _run_create(p.get("img", ""), p.get("name", ""),
                        p.get("cls", "generic"), p.get("res", "4k"),
                        p.get("eng", "fast"), True, bool(p.get("assign")))
    except Exception as e:
        r = {"state": "err", "text": "panel error: %s" % e}
    rt.mfBridgeState = r.get("state", "ok")
    rt.mfBridgeText = r.get("text", "")


def _bridge_savekeys():
    p = _payload()
    try:
        mfconfig.save_keys(fal_key=(p.get("fal") or None),
                           omega_key=(p.get("omega") or None),
                           omega_model=(p.get("model") or None))
        rt.mfBridgeState = "ok"
        rt.mfBridgeText = "Keys saved."
    except Exception as e:
        rt.mfBridgeState = "err"
        rt.mfBridgeText = "Save failed: %s" % e


def _bridge_getkeys():
    try:
        rt.mfBridgeText = json.dumps(mfconfig.get_keys_status())
    except Exception:
        rt.mfBridgeText = "{}"


def _bridge_chat():
    p = _payload()
    rt.mfBridgeText = chat_reply(p.get("q", ""))


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
