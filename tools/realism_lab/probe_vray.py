"""Dump V-Ray 7 property names the realism lab relies on (run via 3dsmaxbatch)."""
import json
import os
import tempfile

from pymxs import runtime as rt

OUT = os.path.join(tempfile.gettempdir(), "mf_probe_vray.json")
res = {}


def props(obj):
    out = {}
    for n in rt.getPropNames(obj):
        n = str(n)
        try:
            v = rt.getProperty(obj, n)
            out[n] = str(v)[:60]
        except Exception as exc:
            out[n] = "<err %s>" % str(exc)[:40]
    return out


vray_cls = None
for c in rt.RendererClass.classes:
    n = str(c)
    if "V_Ray" in n and "GPU" not in n and "RT" not in n:
        vray_cls = c
        break
res["renderer_class"] = str(vray_cls)
rt.renderers.production = vray_cls()
res["renderer"] = props(rt.renderers.production)
for name in ("VRayLight", "VRaySun", "VRayPhysicalCamera", "VRayMtl", "VRayBitmap",
             "VRayDisplacementMod", "VRayNormalMap", "VRay2SidedMtl", "VRayDirt",
             "VRayDenoiser", "VRayHDRI", "VRaySky", "VRayColor"):
    try:
        cls = rt.execute(name)
        if cls is None:
            res[name] = "missing"
            continue
        res[name] = props(cls())
    except Exception as exc:
        res[name] = "error %s" % exc
res["render_elements"] = [str(c) for c in rt.execute("RenderElement.classes")]
res["units"] = str(rt.units.SystemType)
res["gamma"] = {"in": str(rt.fileInGamma), "out": str(rt.fileOutGamma),
                "display": str(rt.displayGamma)}
try:
    res["gamma_enabled"] = str(rt.IDisplayGamma.colorCorrectionMode)
except Exception as exc:
    res["gamma_enabled"] = "err %s" % exc
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(res, fh, indent=1)
