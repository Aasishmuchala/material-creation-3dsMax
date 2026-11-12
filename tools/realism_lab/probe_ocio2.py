"""Probe #4: find a way to load data maps RAW under 3ds Max 2026 OCIO.

Dumps the ColorPipelineMgr interface and tries several loaders on a 50 %
grey PNG; each candidate is rendered self-lit to a float EXR and read back.
0.502 = raw, ~0.20-0.22 = sRGB-decoded.
"""
import json
import os
import shutil
import tempfile
import traceback

import numpy as np
from PIL import Image
from pymxs import runtime as rt

D = os.path.join(tempfile.gettempdir(), "mf_ocio")
os.makedirs(D, exist_ok=True)
png = os.path.join(D, "grey128.png")
Image.fromarray(np.full((64, 64, 3), 128, np.uint8)).save(png)
raw_png = os.path.join(D, "grey128_raw.png")
shutil.copy(png, raw_png)
res = {}
rt.resetMaxFile(rt.Name("noPrompt"))
try:
    res["cpm_interface"] = str(rt.execute(
        "(ss = stringStream \"\"; showInterface ColorPipelineMgr to:ss; ss as string)"))[:6000]
except Exception as exc:
    res["cpm_interface"] = "err %s" % exc
try:
    res["bitmap_props"] = str(rt.execute(
        "(ss = stringStream \"\"; b = openBitMap @\"%s\"; showProperties b to:ss; ss as string)" % png))[:1500]
except Exception as exc:
    res["bitmap_props"] = "err %s" % exc
try:
    res["bitmaptex_props"] = str(rt.execute(
        "(ss = stringStream \"\"; showProperties (Bitmaptexture()) to:ss; ss as string)"))[:2500]
except Exception as exc:
    res["bitmaptex_props"] = "err %s" % exc

vray = [c for c in rt.RendererClass.classes if "V_Ray" in str(c) and "GPU" not in str(c)][0]
r = vray()
rt.renderers.production = r
r.imageSampler_type = 3
r.progressive_max_render_time = 0.1
r.gi_on = False

cands = []


def add(name, fn):
    try:
        tex = fn()
        cands.append((name, tex))
    except Exception:
        res["build_" + name] = traceback.format_exc().splitlines()[-1]


def bt_gamma():
    t = rt.Bitmaptexture()
    t.bitmap = rt.openBitMap(png, gamma=1.0)
    return t


def bt_kw_colorspace():
    t = rt.Bitmaptexture()
    t.bitmap = rt.execute('openBitMap @"%s" colorSpace:"Raw"' % png)
    return t


def bt_set_colorspace():
    t = rt.Bitmaptexture()
    b = rt.openBitMap(png)
    b.colorSpace = "Raw"
    t.bitmap = b
    return t


def bt_raw_name():
    t = rt.Bitmaptexture()
    t.filename = raw_png
    return t


def bt_prop_colorspace():
    t = rt.Bitmaptexture()
    t.filename = png
    for nm in ("colorSpace", "colorspace", "ColorSpace"):
        if rt.isProperty(t, rt.Name(nm)):
            setattr(t, nm, "Raw")
            return t
    raise RuntimeError("no colorspace prop on Bitmaptexture")


add("A_bt_gamma1", bt_gamma)
add("B_bt_kw_colorSpace_Raw", bt_kw_colorspace)
add("C_bt_set_bitmap_colorSpace_Raw", bt_set_colorspace)
add("D_bt_filename_raw_suffix", bt_raw_name)
add("E_bt_prop_colorspace", bt_prop_colorspace)
for cs in (0, 1, 2, 3, 4):
    def vb(cs=cs):
        t = rt.VRayBitmap()
        t.HDRIMapName = png
        t.color_space = cs
        return t
    add("F_vraybitmap_cs%d" % cs, vb)


def vb_ocio():
    t = rt.VRayBitmap()
    t.HDRIMapName = png
    t.ocioColorSpace = True
    return t


add("G_vraybitmap_ocioflag", vb_ocio)
cam = rt.Freecamera(pos=rt.Point3(0, 0, 400))
cam.fov = 60
n = len(cands)
for i, (name, tex) in enumerate(cands):
    p = rt.Plane(width=20, length=20, pos=rt.Point3(-150 + i * 30, 0, 0))
    m = rt.VRayLightMtl()
    m.color = rt.Color(255, 255, 255)
    m.texmap = tex
    p.material = m
out = os.path.join(D, "ocio_probe2.exr")
rt.render(camera=cam, outputwidth=1200, outputheight=200, outputfile=out, vfb=False, quiet=True)
bm = rt.openBitMap(out)
# map world x of each plane centre to pixel x (fov 60, distance 400)
half_w = 400 * np.tan(np.radians(30))
for i, (name, _) in enumerate(cands):
    wx = -150 + i * 30
    px = int((wx / half_w * 0.5 + 0.5) * 1200)
    c = rt.getPixels(bm, rt.Point2(px, 100), 1)[0]
    res[name] = round(float(c.r) / 255.0, 4)
with open(os.path.join(D, "ocio_probe2.json"), "w") as fh:
    json.dump(res, fh, indent=1)
