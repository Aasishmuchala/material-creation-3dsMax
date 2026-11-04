"""JSON + self-contained HTML report a studio can attach to a delivery."""
from __future__ import annotations

import html
import json
from dataclasses import asdict
from typing import Optional

from .inspector import summary
from .model import Finding

VERSION = "0.1.0"


def to_json(findings: list[Finding], scene: str = "", extra: Optional[dict] = None) -> str:
    rows = []
    for f in findings:
        d = asdict(f)
        d["severity"] = f.severity.value
        if f.fix is not None:
            d["fix"]["value"] = _jsonable(f.fix.value)
        rows.append(d)
    doc = {"tool": "Material Inspector", "version": VERSION, "scene": scene,
           "summary": summary(findings), "findings": rows}
    if extra:
        doc.update(extra)
    return json.dumps(doc, indent=2, ensure_ascii=False)


def _jsonable(v):
    if isinstance(v, tuple):
        return [round(x, 4) if isinstance(x, float) else x for x in v]
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    return v


_CSS = """
:root{--paper:#F4F1EA;--ink:#1B1B1A;--grey:#8A8780;--rule:#DAD5CB;--acc:#E5531A}
@media (prefers-color-scheme:dark){:root{--paper:#1B1B1A;--ink:#F4F1EA;--grey:#A9A59D;--rule:#3a3833}}
body{background:var(--paper);color:var(--ink);font:14px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;margin:0;padding:32px 16px}
main{max-width:1100px;margin:0 auto}
h1{font:400 34px/1.1 Georgia,serif;margin:0 0 4px} .sub{color:var(--grey);margin:0 0 28px}
.kpis{display:flex;gap:28px;flex-wrap:wrap;margin-bottom:28px}
.kpi b{display:block;font:400 30px Georgia,serif} .kpi span{color:var(--grey);font-size:12px}
table{width:100%;border-collapse:collapse} th{text-align:left;font:500 11px ui-monospace,monospace;color:var(--grey);letter-spacing:.06em;text-transform:uppercase;padding:8px 6px;border-bottom:1px solid var(--ink)}
td{padding:9px 6px;border-bottom:1px solid var(--rule);vertical-align:top}
.sev{font:600 11px ui-monospace,monospace;text-transform:uppercase}
.error .sev{color:var(--acc)} .warning .sev{color:var(--ink)} .info .sev{color:var(--grey)}
.det{color:var(--grey);font-size:12.5px} code{font-size:12px}
footer{color:var(--grey);font-size:12px;margin-top:28px}
.wrap{overflow-x:auto}
"""


def to_html(findings: list[Finding], scene: str = "") -> str:
    s = summary(findings)
    rows = []
    for f in findings:
        fix = html.escape(f.fix.description) if f.fix else "—"
        tex = f"<br><code>{html.escape(f.texture)}</code>" if f.texture else ""
        rows.append(
            f"<tr class='{f.severity.value}'><td class='sev'>{f.severity.value}</td>"
            f"<td><code>{f.rule_id}</code></td><td>{html.escape(f.material)}{tex}</td>"
            f"<td>{html.escape(f.message)}<div class='det'>{html.escape(f.detail)}</div></td>"
            f"<td>{fix}</td></tr>")
    kpi = "".join(f"<div class='kpi'><b>{v}</b><span>{k.replace('_', ' ')}</span></div>"
                  for k, v in s.items())
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Material Inspector report</title><style>{_CSS}</style></head><body><main>
<h1>Material Inspector</h1><p class="sub">{html.escape(scene) or 'Scene'} · version {VERSION}</p>
<div class="kpis">{kpi}</div>
<div class="wrap"><table><thead><tr><th>Severity</th><th>Rule</th><th>Material</th><th>Finding</th><th>Fix</th></tr></thead>
<tbody>{''.join(rows) or '<tr><td colspan=5>No findings.</td></tr>'}</tbody></table></div>
<footer>Checks are on material parameters and texture pixels only — nothing is rendered.</footer>
</main></body></html>"""
