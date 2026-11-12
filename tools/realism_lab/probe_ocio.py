"""Probe #3: are MatForge's data maps really linear under 3ds Max 2026 OCIO?

Three self-lit planes each show one 50 % grey PNG (pixel 128):
  A  Bitmaptexture + openBitMap(path, gamma=1.0)   (MatForge data-map path)
  B  Bitmaptexture + filename                      (MatForge albedo path)
  C  VRayBitmap, color_space 0 / rgbColorSpace raw
Rendered to float EXR (no output conversion). Raw data reads 0.502; an sRGB
decode reads 0.216. Writes the colour-pipeline state and the three values.
"""
import json
import os
import tempfile

import numpy as np
from PIL import Image
from pymxs import runtime as rt

D = os.path.join(tempfile.gettempdir(), "mf_ocio")
os.makedirs(D, exist_ok=True)
png = os.path.join(D, "grey128.png")
Image.fromarray(np.full((64, 64, 3), 128, np.uint8)).save(png)
res = {}
rt.resetMaxFile(rt.Name("noPrompt"))
try:
    cpm = rt.ColorPipelineMgr
    res["mode"] = str(cpm.Mode)
    res["rendering_space"] = str(cpm.RenderingColorSpace)
except Exception as exc:
    res["cpm_error"] = str(exc)
vray = [c for c in rt.RendererClass.classes if "V_Ray" in str(c) and "GPU" not in str(c)][0]
r = vray()
rt.renderers.production = r
r.imageSampler_type = 3
r.progressive_max_render_time = 0.1
r.gi_on = False


def lightmtl(tex):
    m = rt.VRayLightMtl()
    m.color = rt.Color(255, 255, 255)
    m.multiplier = 1.0
    m.texmap = tex
    return m


a = rt.Bitmaptexture()
a.bitmap = rt.openBitMap(png, gamma=1.0)
b = rt.Bitmaptexture()
b.filename = png
c = rt.VRayBitmap()
c.HDRIMapName = png
for prop, val in (("color_space", 0), ("rgbColorSpace", 0)):
    try:
        setattr(c, prop, val)
    except Exception as exc:
        res["vraybitmap_" + prop] = str(exc)
for i, t in enumerate((a, b, c)):
    p = rt.Plane(width=40, length=40, pos=rt.Point3(-50 + i * 50, 0, 0))
    p.material = lightmtl(t)
cam = rt.Freecamera(pos=rt.Point3(0, 0, 300))
cam.fov = 50
out = os.path.join(D, "ocio_probe.exr")
rt.render(camera=cam, outputwidth=600, outputheight=200, outputfile=out, vfb=False, quiet=True)
bm = rt.openBitMap(out)
for i, x in enumerate((150, 300, 450)):
    px = rt.getPixels(bm, rt.Point2(x, 100), 1)[0]
    res["plane_" + "ABC"[i]] = [round(float(px.r) / 255.0, 4), round(float(px.g) / 255.0, 4)]
with open(os.path.join(D, "ocio_probe.json"), "w") as fh:
    json.dump(res, fh, indent=1)
