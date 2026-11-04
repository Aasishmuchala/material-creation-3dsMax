"""MatForge backend for 3ds Max: command building, output parsing, wiring.

Run from Max:  Scripting > Run Script... > matforge/run_matforge.py
Flow: pick reference image -> name -> class -> 2K/4K/8K -> Create.
Map generation shells out to system Python (Pillow/numpy live there,
Max's bundled Python stays untouched); wiring happens in-process.
The Qt dock (maxplugin.forge_qt) and the classic MAXScript rollout share the
three halves exposed here: build_command, parse_generator_output, finish_build.
"""
import json
import os
import re
import subprocess
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import matphys  # noqa: E402
import mfconfig  # noqa: E402

from core.recipes import RECIPES, RESOLUTIONS, class_choices  # noqa: E402
from maxplugin import builder  # noqa: E402
from maxplugin.inputs import image_problem, safe_name  # noqa: E402

from pymxs import runtime as rt  # noqa: E402

CLI = os.path.join(_REPO, "forge_cli.py")     # Fast: deterministic heuristic
FAL = os.path.join(_REPO, "forge_fal.py")     # Ultra: fal PATINA AI (4K)

_CLASSES = class_choices()  # [(key, label)]

# Map generation runs in a SYSTEM Python (with Pillow+numpy), never Max's own
# Python, so this works identically on Max 2022 (Py3.7) through 2027 (Py3.13).
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


_SAMPLE = os.path.join(_REPO, "sample_maps", "real_wood.jpg")


def diagnose(run_create=False):
    """Layer-by-layer self-test. Returns a plain multi-line report so the exact
    point of failure is visible (and pasteable) instead of a vague 'not
    working'. With run_create=True it also builds a material end-to-end from a
    bundled sample image, proving the whole Fast pipeline in one shot.

    Called by matforge_diagnose.ms (Scripting > Run Script)."""
    out = ["MatForge diagnostic", "-" * 46]

    def row(ok, label, extra=""):
        out.append(("  [OK]  " if ok else "  [FAIL] ") + label +
                   (("   -- " + extra) if extra else ""))

    # 1. system Python with Pillow + numpy (the map generator runs here)
    pybin = _python()
    libs = False
    try:
        cflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        r = subprocess.run(pybin + ["-c", "import PIL, numpy"],
                           capture_output=True, timeout=25, creationflags=cflags)
        libs = (r.returncode == 0)
    except Exception:
        pass
    row(libs, "system Python (%s) + Pillow/numpy" % " ".join(pybin),
        "" if libs else "install Python 3, then: pip install Pillow numpy")

    # 2. V-Ray present (VRayMtl plugin class resolves)
    try:
        vray = bool(rt.execute("(VRayMtl != undefined)"))
    except Exception:
        vray = False
    row(vray, "V-Ray (VRayMtl plugin loaded)",
        "" if vray else "set V-Ray as the active renderer")
    try:
        corona = bool(rt.execute("(CoronaPhysicalMtl != undefined)"))
    except Exception:
        corona = False
    row(corona, "Corona (CoronaPhysicalMtl plugin loaded)",
        "" if corona else "optional if V-Ray is present")
    if not vray and not corona:
        out.append("  [FAIL] neither renderer found   -- install/enable "
                   "V-Ray or Corona")

    # 3. keys (both optional; Fast engine needs neither)
    st = {}
    try:
        st = mfconfig.get_keys_status()
    except Exception:
        pass
    row(bool(st.get("fal")), "fal key (Ultra AI engine)",
        "" if st.get("fal") else "optional, Standard needs no key")
    row(bool(st.get("omega")), "omega key (Fable-5 chat/prompts)",
        "" if st.get("omega") else "optional")

    # 4. optional full pipeline test on a bundled sample
    if run_create:
        out.append("-" * 46)
        if not os.path.isfile(_SAMPLE):
            out.append("  live test skipped: no sample image at " + _SAMPLE)
        else:
            out.append("  running Fast pipeline on sample_maps/real_wood.jpg ...")
            try:
                r = _run_create(_SAMPLE, "MatForge_SelfTest", "wood_interior",
                                "2k", "fast", True, False)
                row(r.get("state") == "ok",
                    "end-to-end create -> " + str(r.get("text", "")))
            except Exception as e:
                row(False, "end-to-end create raised: %s" % e)

    out.append("-" * 46)
    out.append("If a row says FAIL, that layer is the problem. If the dock will "
               "not open, run forge_max.show_rollout() from the Listener.")
    return "\n".join(out)


def _ui():
    return rt.MatForgeRollout


def browse_image():
    f = rt.getOpenFileName(
        caption="MatForge - pick reference image",
        types="Images|*.jpg;*.jpeg;*.png;*.tif;*.tiff;*.bmp;*.webp|All|*.*")
    # Cancel returns MAXScript 'undefined' (truthy via pymxs) -> require a str
    if not isinstance(f, str) or not f:
        return
    _ui().edtImg.text = f
    # prefill name from filename if empty
    if not _ui().edtName.text:
        base = os.path.splitext(os.path.basename(f))[0]
        _ui().edtName.text = "".join(
            c if c.isalnum() else "_" for c in base)


def _sanitize(name):
    """Folder-safe material name (Windows rejects : * ? " < > | in paths),
    capped at 48 characters so the map folder stays under MAX_PATH."""
    return safe_name(name)


RENDERERS = ("auto", "vray", "corona", "both")
ENGINES = ("fast", "ultra")


def _norm(v):
    return v.strip().lower() if isinstance(v, str) else v


def _check_args(img, mclass, res, engine, renderer, metal):
    """Validate every field BEFORE map generation (Ultra is a paid fal call).
    Returns (error_text_or_None, res, engine, renderer, metal) normalised."""
    renderer, engine, res = _norm(renderer), _norm(engine), _norm(res)
    if renderer not in RENDERERS:
        return ("Unknown renderer %r (use auto, vray, corona or both)."
                % (renderer,), res, engine, renderer, metal)
    if engine not in ENGINES:
        return ("Unknown engine %r (use fast or ultra)." % (engine,),
                res, engine, renderer, metal)
    if not isinstance(mclass, str) or mclass not in RECIPES:
        return ("Unknown material type %r." % (mclass,),
                res, engine, renderer, metal)
    if not isinstance(res, str) or res not in RESOLUTIONS:
        return ("Unknown resolution %r (use %s)." % (
            res, ", ".join(sorted(RESOLUTIONS))), res, engine, renderer, metal)
    if metal in (None, ""):
        metal = None
    elif not isinstance(metal, str) or metal not in matphys.METALS:
        return ("Unknown metal %r." % (metal,), res, engine, renderer, metal)
    return image_problem(img), res, engine, renderer, metal


def _parse_bool(v, field):
    """Strict panel boolean: True/False, 1/0, "true"/"false", "1"/"0"."""
    if v is None or v == "":
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, int) and v in (0, 1):
        return bool(v)
    if isinstance(v, str) and v.strip().lower() in ("true", "1"):
        return True
    if isinstance(v, str) and v.strip().lower() in ("false", "0"):
        return False
    raise ValueError("%s must be true or false, got %r" % (field, v))


PROGRESS_FLAG = "--progress"
NO_KEY_TEXT = "Best needs a fal key. Add it in Settings, or use Standard."


def _cmd_fail(text, name=None, res=None, engine=None, renderer=None,
              metal=None):
    return {"ok": False, "error": text, "argv": [], "env": {},
            "extra_note": None, "name": name, "res": res, "engine": engine,
            "renderer": renderer, "metal": metal}


def build_command(img, name, mclass, res, engine, seamless, renderer, metal,
                  progress=False):
    """Validate every field and build the generator command line. Pure: runs
    nothing. Never raises. Returns {ok, error, argv, env, extra_note, name,
    res, engine, renderer, metal} with the last five normalised."""
    try:
        name = _sanitize(name or "MatForge_Material")
        problem, res, engine, renderer, metal = _check_args(
            img, mclass, res, engine, renderer, metal)
        if problem:
            return _cmd_fail(problem, name, res, engine, renderer, metal)

        env = dict(os.environ)
        extra_note = None
        pybin = _python()
        if engine == "ultra":
            key = _fal_key()
            if not key:
                return _cmd_fail(NO_KEY_TEXT, name, res, engine, renderer,
                                 metal)
            env["FAL_KEY"] = key
            upscale = "4" if res in ("4k", "8k") else "2"
            if res == "8k":                    # PATINA's max is 4K
                extra_note = "Best caps at 4K, so it was made at 4096 px, not 8K."
            argv = list(pybin) + [FAL, img, "--name", name, "--type", mclass,
                                  "--upscale", upscale]
        else:
            argv = list(pybin) + [CLI, img, "--name", name, "--type", mclass,
                                  "--res", res]
            if not seamless:
                argv.append("--no-seamless")
        if progress:
            argv.append(PROGRESS_FLAG)
        return {"ok": True, "error": None, "argv": argv, "env": env,
                "extra_note": extra_note, "name": name, "res": res,
                "engine": engine, "renderer": renderer, "metal": metal}
    except Exception as e:
        return _cmd_fail("Could not prepare the command: %s" % e)


def parse_generator_output(stdout_text, returncode=0):
    """Read the generator's last JSON line. Returns (manifest_path|None,
    warnings list, error text|None)."""
    result = None
    for line in reversed((stdout_text or "").strip().splitlines()):
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict) and ("manifest" in obj or "ok" in obj):
            result = obj
            break
    if returncode != 0:
        detail = ""
        if result is not None and isinstance(result.get("error"), str):
            detail = result["error"]
        return None, [], (detail or "see listener")
    if not result or "manifest" not in result:
        if result is not None and isinstance(result.get("error"), str) \
                and result["error"]:
            return None, [], result["error"]
        return None, [], "Could not read generator output."
    warnings = result.get("warnings") or []
    if not isinstance(warnings, list):
        warnings = [str(warnings)]
    return result["manifest"], list(warnings), None


def finish_build(manifest, warnings, extra_note, assign, slate, renderer,
                 metal):
    """Main-thread half of a build: wire the material from the manifest.
    Returns the result dict (state 'ok' with material/slot/notes/text/
    materials/misses/renderer/mclass/maps/assigned) or {state:'err', text}."""
    try:
        out = builder.build_from_manifest(manifest, slot=None,
                                          assign=assign, slate=slate,
                                          renderer=renderer, metal=metal)
    except Exception as e:
        return {"state": "err", "text": "Material wiring failed: %s" % e}

    notes = list(warnings or [])
    if extra_note:
        notes.append(extra_note)
    misses = [l for l in out.get("log", []) if "MISS" in l]
    if misses:
        notes.append("%d renderer propert%s could not be set (see listener)" % (
            len(misses), "y" if len(misses) == 1 else "ies"))
    if slate and not out.get("slate"):
        notes.append("Slate node view unavailable (needs an interactive Max "
                     "session).")
    maps, mclass = {}, None
    try:
        with open(manifest, "r", encoding="utf-8") as f:
            mf = json.load(f)
        maps = dict(mf.get("maps") or {})
        mclass = mf.get("class")
    except Exception:
        pass
    slate_txt = "  + Slate node view" if out.get("slate") else ""
    return {"state": "ok", "material": out["material"], "slot": out["slot"],
            "notes": notes,
            "text": "Done: '%s' -> editor slot %d%s%s" % (
                out["material"], out["slot"], slate_txt,
                "  (with notes)" if notes else ""),
            "materials": list(out.get("materials") or []),
            "misses": misses, "renderer": out.get("renderer", renderer),
            "mclass": mclass, "maps": maps, "assigned": bool(assign)}


def _run_create(img, name, mclass, res, engine, seamless, assign, slate=False,
                renderer="auto", metal=None):
    """Synchronous composition of build_command + subprocess + parse +
    finish_build; used by the rollout and the fuzz tests. Returns a result
    dict: {state: 'ok'|'err', text, material?, slot?, notes?, ...}
    """
    cmd = build_command(img, name, mclass, res, engine, seamless, renderer,
                        metal)
    if not cmd["ok"]:
        return {"state": "err", "text": cmd["error"]}

    # don't flash a console window when launched from the GUI 3dsmax.exe
    cflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(cmd["argv"], capture_output=True, text=True,
                              timeout=1800, env=cmd["env"],
                              creationflags=cflags)
    except FileNotFoundError:
        return {"state": "err", "text": "No system Python 3 with Pillow+numpy "
                "found (install Python 3 + `pip install Pillow numpy`)."}
    except subprocess.TimeoutExpired:
        return {"state": "err", "text": "Map generation timed out."}
    except OSError as e:
        return {"state": "err", "text": "Could not launch Python: %s" % e}

    manifest, warnings, err = parse_generator_output(proc.stdout,
                                                     proc.returncode)
    if err:
        if proc.returncode != 0:
            print("[MatForge] CLI stderr:\n" + (proc.stderr or ""))
            return {"state": "err", "text": "Map generation failed: " + err}
        return {"state": "err", "text": err}
    return finish_build(manifest, warnings, cmd["extra_note"], assign, slate,
                        cmd["renderer"], cmd["metal"])


def assign_result(result):
    """Put the freshly built material on the selected objects (one undo step).
    Returns (ok, text). Never raises."""
    try:
        entries = list(result.get("materials") or [])
        if not entries:
            return False, "Nothing to assign."
        entry = entries[0]
        if len(entries) > 1:
            det = builder.detect_renderer()
            for e in entries:
                if e.get("renderer") == det:
                    entry = e
                    break
        mat = rt.meditMaterials[int(entry["slot"]) - 1]
        mclass = result.get("mclass")
        height = (result.get("maps") or {}).get("height")
        with builder._undo_ctx("MatForge Assign"):
            if entry.get("renderer") == "corona":
                from maxplugin import builder_corona
                n = builder_corona.assign_to_selection(
                    mat, mclass, height_map=height)
            else:
                n = builder.assign_to_selection(mat, mclass,
                                                height_map=height)
        if not n:
            return False, "Nothing is selected."
        return True, "Put on %d selected objects." % n
    except Exception as e:
        return False, "Could not put it on the selection: %s" % e


def slate_result(result):
    """Open the built material in Slate. Returns True on success; never
    raises."""
    try:
        mat = rt.meditMaterials[int(result["slot"]) - 1]
        return bool(builder.show_in_slate(mat))
    except Exception:
        return False


def renderer_status():
    """(key, label) for the renderer chip: vray | corona | both | None."""
    try:
        has_v = builder._has_class("VRayMtl")
        has_c = builder._has_class("CoronaPhysicalMtl")
    except Exception:
        has_v = has_c = False
    if has_v and has_c:
        return "both", "V-Ray and Corona found"
    if has_v:
        return "vray", "V-Ray found"
    if has_c:
        return "corona", "Corona found"
    return None, "No renderer found"


def create_material():
    """Rollout entry point."""
    ui = _ui()
    # Show feedback and force a repaint BEFORE the blocking subprocess, so Max
    # doesn't just sit at 'Not Responding' while maps generate (10-60s).
    ui.lblStatus.text = "Working... generating maps (10-60s), please wait."
    try:
        rt.windows.processPostedMessages()
    except Exception:
        pass
    r = _run_create(
        img=ui.edtImg.text.strip(),
        name=ui.edtName.text.strip() or "MatForge_Material",
        mclass=_CLASSES[ui.ddClass.selection - 1][0],
        res=["2k", "4k", "8k"][ui.ddRes.selection - 1],
        engine=["fast", "ultra"][ui.ddEngine.selection - 1],
        seamless=bool(ui.chkSeamless.checked),
        assign=bool(ui.chkAssign.checked),
        slate=bool(ui.chkSlate.checked),
        renderer=["auto", "vray", "corona", "both"][ui.ddRenderer.selection - 1],
        metal=(None if ui.ddMetal.selection <= 1 else
               matphys.metal_choices()[ui.ddMetal.selection - 2][0]))
    ui.lblStatus.text = r["text"]
    if r["state"] == "err":
        rt.messageBox(r["text"], title="MatForge")
    elif r.get("notes"):
        rt.messageBox("Created with notes:\n\n- " + "\n- ".join(r["notes"]),
                      title="MatForge")


def _create_from_payload(p):
    """Validated dict -> _run_create. Never raises; always returns
    {state, text}. Kept as the fuzz-tested validation surface."""
    try:
        if not isinstance(p, dict):
            return {"state": "err", "text": "panel error: bad payload"}
        name = p.get("name", "")
        return _run_create(img=p.get("img", ""),
                           name=name if isinstance(name, str) else "",
                           mclass=p.get("cls", "generic"),
                           res=p.get("res", "4k"),
                           engine=p.get("eng", "fast"), seamless=True,
                           assign=_parse_bool(p.get("assign"), "assign"),
                           slate=_parse_bool(p.get("slate"), "slate"),
                           renderer=p.get("rnd", "auto"),
                           metal=p.get("metal") or None)
    except Exception as e:
        return {"state": "err", "text": "panel error: %s" % e}


def chat_reply(question):
    """Answer a user question via Fable-5 (omega). Used by the Settings help field."""
    system = ("You are the in-panel assistant for MatForge, a 3ds Max + V-Ray or Corona "
              "material-creation plugin (reference image -> physically-correct "
              "VRayMtl or CoronaPhysicalMtl on a Material Editor sphere; Fast=heuristic maps, "
              "Ultra=fal PATINA AI + Fable-5 prompts). Help the user with "
              "MatForge, V-Ray or Corona materials, and the archviz workflow. Be concise "
              "and practical (a few sentences).")
    try:
        return mfconfig.omega_message(
            [{"type": "text", "text": str(question)[:2000]}],
            max_tokens=800, system=system, timeout=45)
    except Exception as e:
        return "Chat unavailable: %s (check the omega key in Settings)." % e


ROLLOUT_MXS = """
try (destroyDialog MatForgeRollout) catch()
rollout MatForgeRollout "MatForge v1" width:340
(
    edittext edtImg "Image:" fieldWidth:230 across:2 align:#left
    button btnBrowse "..." width:30 align:#right
    edittext edtName "Name:" fieldWidth:230
    dropdownlist ddClass "Material type:" items:#(%CLASS_ITEMS%)
    dropdownlist ddEngine "Engine:" items:#("Fast  (offline, no key)","Ultra  (fal PATINA AI)") selection:1
    dropdownlist ddRenderer "Renderer:" items:#("Auto (active renderer)","V-Ray","Corona","Both") selection:1
    dropdownlist ddMetal "Metal (for metal_ types):" items:#(%METAL_ITEMS%) selection:1
    checkbox chkSeamless "Make seamless (tileable)" checked:true
    checkbox chkAssign "Assign to selected objects" checked:false
    checkbox chkSlate "Open in Slate ME (show node wiring)" checked:false
    dropdownlist ddRes "Resolution (final output):" items:#("2K  -  2048 px","4K  -  4096 px","8K  -  8192 px") selection:2
    button btnCreate "Create Material  ->  Editor Sphere" width:320 height:32
    label lblStatus "Ready." width:320 align:#left

    on btnBrowse pressed do python.Execute "import maxplugin.forge_max as _mf; _mf.browse_image()"
    on btnCreate pressed do python.Execute "import maxplugin.forge_max as _mf; _mf.create_material()"
)
createDialog MatForgeRollout
"""


def _mxs_str(s):
    """Escape a Python string so it is a safe MAXScript double-quoted literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _fill_rollout(fill):
    """Fill %CLASS_ITEMS% / %METAL_ITEMS% in ONE pass, so a label that itself
    contains a placeholder is never re-expanded."""
    return re.sub(r"%(CLASS|METAL)_ITEMS%", lambda m: fill[m.group(1)],
                  ROLLOUT_MXS)


def show_rollout():
    items = ",".join('"%s"' % _mxs_str(label) for _, label in _CLASSES)
    metal_items = ",".join(
        '"%s"' % _mxs_str(label)
        for label in ["(from image)"] + [l for _, l in matphys.metal_choices()])
    ok = rt.execute(_fill_rollout({"CLASS": items, "METAL": metal_items}))
    # rt.execute returns false (not an exception) on a MAXScript COMPILE error,
    # so the dialog would silently not appear. Surface it instead.
    if ok is False:
        raise RuntimeError(
            "MatForge rollout failed to compile (rt.execute returned false). "
            "See the MAXScript Listener for the syntax error.")


def show():
    """Open the Qt dock; fall back to the classic rollout when Qt is missing."""
    try:
        from maxplugin import forge_qt
    except ImportError as e:
        print("[MatForge] Qt dock unavailable (%s); opening the classic "
              "rollout." % e)
        return show_rollout()
    return forge_qt.show()


if __name__ == "__main__":
    show()
