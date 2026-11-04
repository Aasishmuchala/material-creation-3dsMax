"""Material Inspector self-test — run INSIDE 3ds Max on an EMPTY scene.

    Scripting > Run Script… > tools/max_selftest.py

What it does, in order (each step is recorded even if an earlier one fails):
  1. records 3ds Max / Python / V-Ray / Corona versions and which modules import
  2. dumps the real MAXScript property names of every class the Inspector reads
  3. writes small test textures and builds known-broken VRayMtl / CoronaPhysicalMtl
     materials on boxes
  4. scans the scene, compares findings with the expected list
  5. applies every automatic fix inside undo, re-scans, records what remains
Result: %TEMP%\\material_inspector_selftest.json  (send this file back).
It never saves or overwrites your scene; it refuses to run if the scene isn't empty.
"""
import json
import os
import platform
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from pymxs import runtime as rt  # noqa: E402
import pymxs  # noqa: E402

OUT = os.path.join(tempfile.gettempdir(), "material_inspector_selftest.json")
report = {"version": 1, "environment": {}, "imports": {}, "props_dump": {}, "steps": [],
          "expected_vs_found": {}, "fixes": [], "after_fix": []}

DUMP_CLASSES = ["VRayMtl", "CoronaPhysicalMtl", "CoronaLegacyMtl", "Bitmaptexture", "VRayBitmap",
                "CoronaBitmap", "VRayNormalMap", "CoronaNormal", "Normal_Bump", "Output",
                "VRayUVWRandomizer", "CoronaUvwRandomizer"]


def step(name):
    def deco(fn):
        try:
            res = fn()
            report["steps"].append({"name": name, "ok": True, "result": res})
        except Exception:
            report["steps"].append({"name": name, "ok": False, "error": traceback.format_exc()})
        return fn
    return deco


def _try(expr):
    try:
        return str(rt.execute(expr))
    except Exception as exc:
        return f"<unavailable: {exc}>"


@step("environment")
def _env():
    e = report["environment"]
    e["max_version"] = _try("maxVersion()")
    e["python"] = sys.version
    e["platform"] = platform.platform()
    e["vray_version"] = _try("vrayVersion()")
    e["corona_version"] = _try("CoronaRenderer.getCoronaVersion()")
    e["renderer"] = _try("renderers.current as string")
    e["units"] = _try("units.SystemType as string") + " x " + _try("units.SystemScale as string")
    e["color_management"] = _try("colorMan.mode as string")
    for mod in ("numpy", "PIL", "PySide6", "PySide2", "qtmax"):
        try:
            __import__(mod)
            report["imports"][mod] = True
        except Exception as exc:
            report["imports"][mod] = f"missing: {exc}"
    return e


def _dump(obj):
    names = [str(n) for n in rt.getPropNames(obj)]
    out = {}
    for n in names:
        try:
            v = rt.getProperty(obj, n)
            out[n] = {"type": str(rt.classOf(v)), "value": str(v)[:80]}
        except Exception as exc:
            out[n] = {"type": "<error>", "value": str(exc)[:80]}
    return out


@step("props_dump")
def _props():
    for cname in DUMP_CLASSES:
        try:
            cls = rt.execute(cname)
            if cls is None:
                report["props_dump"][cname] = {"installed": False}
                continue
            obj = cls()
            entry = {"installed": True, "props": _dump(obj)}
            if cname == "Output":
                try:
                    entry["output_props"] = _dump(rt.getProperty(obj, "output"))
                except Exception as exc:
                    entry["output_props_error"] = str(exc)
            report["props_dump"][cname] = entry
        except Exception as exc:
            report["props_dump"][cname] = {"installed": False, "error": str(exc)}
    return {k: v.get("installed") for k, v in report["props_dump"].items()}


EXPECTED = {
    "ST_VRay_Bad": ["R001", "R005", "R006", "R010", "R015"],
    "ST_Corona_Glass": ["R014"],
    "ST_Corona_Good": [],
}
TEX = {}


@step("write_test_textures")
def _textures():
    import numpy as np
    from PIL import Image
    d = os.path.join(tempfile.gettempdir(), "material_inspector_selftest_tex")
    os.makedirs(d, exist_ok=True)
    yy, xx = np.mgrid[0:256, 0:256] / 256.0
    h = (np.sin(xx * 2 * np.pi * 4) * np.sin(yy * 2 * np.pi * 4) * 0.5 + 0.5)   # tileable
    gy, gx = np.gradient(h)
    n = np.dstack([-gx * 40, gy * 40, np.ones_like(h)]); n /= np.linalg.norm(n, axis=2, keepdims=True)
    files = {
        "albedo": (np.dstack([np.full_like(h, 0.55)] * 3), "ST_Color.png"),
        "gloss": (h, "ST_Glossiness.png"),
        "normal": (n * 0.5 + 0.5, "ST_NormalGL.png"),
        "rough": (h * 0.5 + 0.25, "ST_Roughness.png"),
    }
    for key, (a, fn) in files.items():
        p = os.path.join(d, fn)
        Image.fromarray((np.clip(a, 0, 1) * 255).astype("uint8")).save(p)
        TEX[key] = p
    return TEX


def _set(obj, names, value, log):
    for nm in names:
        if rt.isProperty(obj, nm):
            rt.setProperty(obj, nm, value)
            return nm
    log.append(f"could not set any of {names}")
    return None


@step("build_test_scene")
def _scene():
    if len(rt.objects) > 0:
        raise RuntimeError("Scene is not empty — open a new empty scene (File > New) and run again.")
    from material_inspector.max_adapter import props as P
    log = []
    def bitmap(path, srgb):
        b = rt.Bitmaptexture(filename=path)
        vals = P.COLOR_SPACE_VALUES["Bitmaptexture"]["srgb" if srgb else "linear"]
        for v in vals:
            if _set(b, P.BITMAP_CLASSES["Bitmaptexture"]["color_space"], v, []):
                break
        else:
            log.append("Bitmaptexture colour space could not be set — check props_dump")
        return b

    mats = []
    if report["props_dump"].get("VRayMtl", {}).get("installed"):
        m = rt.VRayMtl(name="ST_VRay_Bad")
        _set(m, P.PARAMS["VRayMtl"]["base_color"], rt.Color(10, 8, 6), log)
        _set(m, P.PARAMS["VRayMtl"]["brdf"], 1, log)                    # Blinn
        _set(m, P.PARAMS["VRayMtl"]["use_roughness"], True, log)
        _set(m, P.SLOTS["VRayMtl"][P.SlotRole.GLOSSINESS], bitmap(TEX["gloss"], srgb=True), log)
        _set(m, P.SLOTS["VRayMtl"][P.SlotRole.BUMP], bitmap(TEX["normal"], srgb=False), log)
        mats.append(m)
    if report["props_dump"].get("CoronaPhysicalMtl", {}).get("installed"):
        g = rt.CoronaPhysicalMtl(name="ST_Corona_Glass")
        _set(g, P.PARAMS["CoronaPhysicalMtl"]["refraction_amount"], 1.0, log)
        _set(g, P.PARAMS["CoronaPhysicalMtl"]["absorption_color"], rt.Color(255, 255, 255), log)
        mats.append(g)
        ok = rt.CoronaPhysicalMtl(name="ST_Corona_Good")
        _set(ok, P.PARAMS["CoronaPhysicalMtl"]["base_color"], rt.Color(150, 130, 110), log)
        _set(ok, P.SLOTS["CoronaPhysicalMtl"][P.SlotRole.BASE_COLOR], bitmap(TEX["albedo"], srgb=True), log)
        _set(ok, P.SLOTS["CoronaPhysicalMtl"][P.SlotRole.ROUGHNESS], bitmap(TEX["rough"], srgb=False), log)
        mats.append(ok)
    for i, m in enumerate(mats):
        b = rt.Box(length=50, width=50, height=50, pos=rt.Point3(i * 80, 0, 0))
        b.material = m
    return {"materials": [str(m.name) for m in mats], "log": log}


def _scan():
    from material_inspector.core.inspector import InspectorOptions, inspect
    from material_inspector.max_adapter.scene import SceneReader
    reader = SceneReader(rt)
    mats = reader.materials()
    return reader, mats, inspect(mats, InspectorOptions())


@step("scan")
def _first_scan():
    reader, mats, findings = _scan()
    found = {}
    for f in findings:
        found.setdefault(f.material, set()).add(f.rule_id)
    for name, exp in EXPECTED.items():
        got = sorted(found.get(name, set()))
        report["expected_vs_found"][name] = {
            "expected": exp, "found": got,
            "missing": sorted(set(exp) - set(got)),
            "unexpected_errors_warnings": sorted(
                r for r in set(got) - set(exp) if not r.startswith(("R003", "M008")))}
    report["property_resolution"] = reader.log.as_dict()
    report["records"] = [{"name": m.name, "class": m.material_class, "params": {k: str(v) for k, v in m.params.items()},
                          "textures": [{"role": t.role.value, "path": t.path, "color_space": t.color_space.value,
                                        "node_class": t.node_class, "via_normal_node": t.via_normal_node}
                                       for t in m.textures]} for m in mats]
    return {k: v["missing"] for k, v in report["expected_vs_found"].items()}


@step("fix_and_rescan")
def _fix():
    from material_inspector.max_adapter.fixes import FixApplier
    reader, mats, findings = _scan()
    by = {m.name: m for m in mats}
    ap = FixApplier(rt, pymxs.undo)
    for f in findings:
        if f.fix and f.material in by:
            r = ap.apply(f, by[f.material])
            report["fixes"].append({"material": f.material, "rule": f.rule_id, "ok": r.ok, "message": r.message})
    _, _, after = _scan()
    report["after_fix"] = sorted({(f.material, f.rule_id) for f in after if f.severity.value != "info"})
    return {"applied": sum(x["ok"] for x in report["fixes"]), "failed": sum(not x["ok"] for x in report["fixes"])}


with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(report, fh, indent=2, default=str)

ok = sum(s["ok"] for s in report["steps"])
msg = f"Material Inspector self-test: {ok}/{len(report['steps'])} steps OK.\nResult: {OUT}"
print(msg)
try:
    rt.messageBox(msg, title="Material Inspector")
except Exception:
    pass
