"""Scan every .max file in a folder — run INSIDE 3ds Max (Sprint 3: 50-scene test).

Set the folders first, then Scripting > Run Script… > tools/batch_scan.py
    set MI_BATCH_DIR=D:\\test_scenes
    set MI_BATCH_OUT=D:\\test_scenes\\inspector_out
or edit the two defaults below. For unattended runs:
    "C:\\Program Files\\Autodesk\\3ds Max 2026\\3dsmaxbatch.exe" tools\\batch_scan.py

Output:
  <out>/<scene>.json    full findings per scene
  <out>/review.csv      one row per finding with an empty 'verdict' column:
                        fill TP / FP by hand, then run
                        python -m material_inspector.devtools.fp_rate review.csv
Scenes are opened read-only in spirit: nothing is saved.
"""
import csv
import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from pymxs import runtime as rt  # noqa: E402

from material_inspector.core.config import load_options  # noqa: E402
from material_inspector.core.inspector import inspect, summary  # noqa: E402
from material_inspector.core.report import to_json  # noqa: E402
from material_inspector.max_adapter.scene import SceneReader  # noqa: E402

SRC = os.environ.get("MI_BATCH_DIR", r"D:\test_scenes")
OUT = os.environ.get("MI_BATCH_OUT", os.path.join(SRC, "inspector_out"))
os.makedirs(OUT, exist_ok=True)
opt, _ = load_options()

scenes = sorted(os.path.join(r, f) for r, _, fs in os.walk(SRC) for f in fs if f.lower().endswith(".max"))
rows, totals = [], []
for path in scenes:
    name = os.path.splitext(os.path.basename(path))[0]
    try:
        rt.loadMaxFile(path, quiet=True, useFileUnits=True)
        reader = SceneReader(rt)
        mats = reader.materials()
        findings = inspect(mats, opt)
        with open(os.path.join(OUT, name + ".json"), "w", encoding="utf-8") as fh:
            fh.write(to_json(findings, path, {"property_resolution": reader.log.as_dict(),
                                              "materials": len(mats)}))
        for f in findings:
            if f.severity.value != "info":
                rows.append({"scene": name, "material": f.material, "rule": f.rule_id,
                             "severity": f.severity.value, "texture": f.texture or "",
                             "message": f.message, "verdict": ""})
        s = summary(findings)
        totals.append({"scene": name, "materials": len(mats), **s, "status": "ok"})
        print(f"{name}: {len(mats)} materials, {s['error']} errors, {s['warning']} warnings")
    except Exception:
        totals.append({"scene": name, "status": "failed", "error": traceback.format_exc()[-400:]})
        print(f"{name}: FAILED")
    finally:
        try:
            rt.resetMaxFile(rt.Name("noPrompt"))
        except Exception:
            pass

with open(os.path.join(OUT, "review.csv"), "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=["scene", "material", "rule", "severity", "texture", "message", "verdict"])
    w.writeheader(); w.writerows(rows)
with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as fh:
    json.dump(totals, fh, indent=2)
print(f"\n{len(scenes)} scenes -> {OUT}")
