"""Compare a self-test props dump with the property table in max_adapter/props.py.

    python -m material_inspector.devtools.props_check material_inspector_selftest.json

Prints, for every canonical entry, whether one of its candidate names exists on the
real class and, if not, the closest real names. MAXScript names are case-insensitive.
Exit code 1 if anything the Inspector needs is unresolved.
"""
from __future__ import annotations

import difflib
import json
import sys

from ..max_adapter import props as P


def _entries():
    for cls, table in P.PARAMS.items():
        for key, names in table.items():
            yield cls, f"param:{key}", names
    for cls, table in P.SLOTS.items():
        for role, names in table.items():
            yield cls, f"slot:{role.value}", names
    for cls, spec in P.BITMAP_CLASSES.items():
        for key, names in spec.items():
            yield cls, f"bitmap:{key}", names
    for cls, spec in P.NORMAL_CLASSES.items():
        for key, names in spec.items():
            yield cls, f"normal:{key}", names
    yield "Output", "output:input", P.OUTPUT_MAP["input"]
    yield "Output", "output:settings", P.OUTPUT_MAP["settings"]
    yield "Output.output", "output:invert", P.OUTPUT_MAP["invert"]


def check(dump: dict) -> list[dict]:
    rows = []
    for cls, key, names in _entries():
        base = cls.split(".")[0]
        entry = dump.get(base, {})
        if not entry.get("installed"):
            rows.append({"class": cls, "key": key, "status": "class not installed", "candidates": names})
            continue
        real = entry.get("output_props" if cls == "Output.output" else "props", {})
        lower = {n.lower(): n for n in real}
        hit = next((lower[n.lower()] for n in names if n.lower() in lower), None)
        if hit:
            rows.append({"class": cls, "key": key, "status": "ok", "resolved": hit,
                         "type": real[hit].get("type"), "value": real[hit].get("value")})
        else:
            close = difflib.get_close_matches(names[0].lower(), list(lower), n=4, cutoff=0.5)
            rows.append({"class": cls, "key": key, "status": "MISSING", "candidates": names,
                         "closest": [lower[c] for c in close]})
    return rows


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__); return 2
    with open(argv[0], encoding="utf-8") as fh:
        data = json.load(fh)
    rows = check(data.get("props_dump", {}))
    bad = [r for r in rows if r["status"] == "MISSING"]
    for r in rows:
        if r["status"] == "ok":
            print(f"ok       {r['class']:<20} {r['key']:<28} -> {r['resolved']} ({r['type']})")
        elif r["status"] == "MISSING":
            print(f"MISSING  {r['class']:<20} {r['key']:<28} tried {r['candidates']}  closest {r['closest']}")
        else:
            print(f"skip     {r['class']:<20} {r['key']:<28} ({r['status']})")
    print(f"\n{len(rows) - len(bad)} resolved, {len(bad)} missing")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
