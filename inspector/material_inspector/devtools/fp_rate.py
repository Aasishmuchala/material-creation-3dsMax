"""False-positive rate from a hand-labelled review.csv (Sprint 3 exit: < 5 %).

    python -m material_inspector.devtools.fp_rate review.csv [--limit 0.05]

The 'verdict' column takes TP (real problem) or FP (Inspector was wrong);
blank rows are counted as unreviewed and reported.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict


def rates(rows: list[dict]) -> dict:
    per = defaultdict(Counter)
    for r in rows:
        v = (r.get("verdict") or "").strip().upper()
        per[r["rule"]][v if v in ("TP", "FP") else "UNREVIEWED"] += 1
    out, tp, fp, un = {}, 0, 0, 0
    for rule, c in sorted(per.items()):
        reviewed = c["TP"] + c["FP"]
        out[rule] = {"tp": c["TP"], "fp": c["FP"], "unreviewed": c["UNREVIEWED"],
                     "fp_rate": (c["FP"] / reviewed) if reviewed else None}
        tp += c["TP"]; fp += c["FP"]; un += c["UNREVIEWED"]
    overall = fp / (tp + fp) if tp + fp else None
    return {"rules": out, "overall": {"tp": tp, "fp": fp, "unreviewed": un, "fp_rate": overall}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv"); ap.add_argument("--limit", type=float, default=0.05)
    a = ap.parse_args(argv)
    with open(a.csv, newline="", encoding="utf-8") as fh:
        res = rates(list(csv.DictReader(fh)))
    for rule, r in res["rules"].items():
        fr = "  n/a" if r["fp_rate"] is None else f"{r['fp_rate']:5.1%}"
        flag = "  <-- over limit" if r["fp_rate"] is not None and r["fp_rate"] > a.limit else ""
        print(f"{rule}  TP {r['tp']:4}  FP {r['fp']:4}  unreviewed {r['unreviewed']:4}  FP rate {fr}{flag}")
    o = res["overall"]
    if o["fp_rate"] is None:
        print("\nNothing reviewed yet."); return 2
    print(f"\nOverall FP rate {o['fp_rate']:.1%} (limit {a.limit:.0%}), {o['unreviewed']} unreviewed")
    return 0 if o["fp_rate"] <= a.limit and o["unreviewed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
