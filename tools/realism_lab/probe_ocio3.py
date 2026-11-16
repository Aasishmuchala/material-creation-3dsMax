"""Probe #5: how does a loaded bitmap report its colour space under OCIO?"""
import json
import os
import tempfile

import numpy as np
from PIL import Image
from pymxs import runtime as rt

D = os.path.join(tempfile.gettempdir(), "mf_ocio")
os.makedirs(D, exist_ok=True)
png = os.path.join(D, "probe3_grey.png")
Image.fromarray(np.full((16, 16, 3), 128, np.uint8)).save(png)
raw_png = os.path.join(D, "probe3_roughness.png")
Image.fromarray(np.full((16, 16, 3), 128, np.uint8)).save(raw_png)
res = {"data_cs": str(rt.ColorPipelineMgr.DataColorSpace)}


def info(bm):
    out = {}
    for p in ("colorSpace", "colorspace", "gamma", "inputGamma", "colorSpaceRule"):
        try:
            out[p] = str(rt.getProperty(bm, p))
        except Exception as exc:
            out[p] = "err: " + str(exc)[:60]
    return out


res["default"] = info(rt.openBitMap(png))
res["raw_kw"] = info(rt.openBitMap(raw_png, colorSpace=res["data_cs"]))
t = rt.Bitmaptexture()
t.filename = png
res["bitmaptexture_bitmap"] = info(t.bitmap)
try:
    rules = []
    for i in range(1, int(rt.ColorPipelineMgr.InputRulesCount) + 1):
        r = rt.execute('(n = "" ; cs = "" ; pat = "" ; ext = "" ; rx = "" ; '
                       'ColorPipelineMgr.GetInputRule %d name:&n colorSpace:&cs pattern:&pat '
                       'extension:&ext regex:&rx ; n + " | " + cs + " | " + pat + " | " + ext + " | " + rx)' % i)
        rules.append(str(r))
    res["input_rules"] = rules
except Exception as exc:
    res["input_rules"] = "err %s" % exc
with open(os.path.join(D, "ocio_probe3.json"), "w") as fh:
    json.dump(res, fh, indent=1)
