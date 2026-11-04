# Windows box runbook (one page)

## Prerequisites
- Windows 10/11 x64, 3ds Max 2025, 2026 or 2027
- V-Ray 7.x and/or Corona 14/15 (at least one)
- System Python 3 (`py -3.12`, `py -3` or `python`) with internet for `pip install Pillow numpy pytest`

## 1. Install
Follow the **Install** section of the root `README.md` (MatForge) and
`inspector/docs/FIRST_WINDOWS_SESSION.md` step 1 (Material Inspector). Restart Max afterwards.

## 2. Run the automated pass
Close interactive Max first (batch needs the licence seat), then in PowerShell from the repo root:
```powershell
powershell -ExecutionPolicy Bypass -File tools\onbox_verify.ps1
# optional: -MaxRoot "C:\Program Files\Autodesk\3ds Max 2026" -OutDir .\onbox_out
```
It runs root and inspector pytest, the V-Ray/Corona smoke and the Inspector self-test through
`3dsmaxbatch.exe`, and prints a PASS/FAIL summary. If the self-test fails in batch it prints the
manual GUI step (File > New, then Scripting > Run Script... > `inspector\tools\max_selftest.py`).

## 3. Send back
`onbox_out.zip` (smoke_result.txt, smoke_batch.log, material_inspector_selftest.json, inspector logs,
pytest logs, summary.txt). No keys or key files are read or collected.

## 4. Manual checks, in order
1. `docs/VERIFY_VRAY.md` - do the **swatch-is-linear** check first
2. `docs/VERIFY_CORONA.md`
3. `inspector/docs/VERIFY.md`
4. `docs/VERIFY_INSTALL.md`
5. `inspector/docs/FIRST_WINDOWS_SESSION.md` steps 3-5 (dock on a real scene, normal-map convention, batch scan)
6. `docs/ui/screens` vs the real dock: dark theme matches, nothing clipped at 360 px dock width

Report each item as pass/fail with a screenshot or the relevant log lines.
