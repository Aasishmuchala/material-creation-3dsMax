import csv
import json

from material_inspector.devtools import fp_rate, props_check
from material_inspector.max_adapter import props as P


def perfect_dump():
    """A dump where the first candidate of every entry exists (with odd casing)."""
    d = {}
    for cls, key, names in props_check._entries():
        base = cls.split(".")[0]
        e = d.setdefault(base, {"installed": True, "props": {}})
        bucket = e.setdefault("output_props", {}) if cls == "Output.output" else e["props"]
        bucket[names[0].upper()] = {"type": "Float", "value": "0"}
    return d


def test_props_check_all_ok_case_insensitive():
    rows = props_check.check(perfect_dump())
    assert all(r["status"] == "ok" for r in rows)


def test_props_check_reports_missing_with_suggestion(tmp_path):
    d = perfect_dump()
    real = d["VRayMtl"]["props"]
    real.pop("BRDF_USEROUGHNESS")
    real["brdf_use_roughness"] = {"type": "BooleanClass", "value": "true"}
    d["CoronaBitmap"] = {"installed": False}
    rows = props_check.check(d)
    miss = [r for r in rows if r["status"] == "MISSING"]
    assert len(miss) == 1 and miss[0]["key"] == "param:use_roughness"
    assert "brdf_use_roughness" in miss[0]["closest"]
    assert any(r["status"] == "class not installed" for r in rows)
    p = tmp_path / "st.json"; p.write_text(json.dumps({"props_dump": d}))
    assert props_check.main([str(p)]) == 1


def test_fp_rate(tmp_path):
    p = tmp_path / "review.csv"
    rows = [{"scene": "s", "material": "m", "rule": "R001", "severity": "error", "texture": "",
             "message": "", "verdict": v} for v in ["TP"] * 19 + ["FP"]]
    rows += [{"scene": "s", "material": "m", "rule": "R014", "severity": "warning", "texture": "",
              "message": "", "verdict": "fp"}]
    with open(p, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    res = fp_rate.rates(list(csv.DictReader(open(p))))
    assert res["rules"]["R001"]["fp_rate"] == 0.05 and res["rules"]["R014"]["fp_rate"] == 1.0
    assert abs(res["overall"]["fp_rate"] - 2 / 21) < 1e-9
    assert fp_rate.main([str(p)]) == 1
