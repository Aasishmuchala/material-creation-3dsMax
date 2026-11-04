# First Windows session — runbook

Goal: turn every "unverified" item in `docs/VERIFY.md` into a fact, in about **60–90 minutes**.
Everything that could be prepared without 3ds Max is done and tested (60 tests).

## Bring

| Item | Notes |
|---|---|
| Windows 10/11 x64 PC | any GPU; nothing here renders |
| 3ds Max 2025, 2026 or 2027 | trial licence is fine |
| V-Ray 7 and Corona 13 or 14 | trial licences are fine; at least one of the two |
| Internet on that PC | `pip install numpy pillow` into Max's Python |
| This folder (`material-inspector/`) | zip it, or clone it once it's in a git repo |
| 10–50 real archviz `.max` scenes | for step 5 — downloaded / client scenes with V-Ray or Corona materials |

**Faster option:** connect that PC to this Claude session (Claude desktop app › Remote Control, add the
`material-inspector` folder). Then I can run steps 2, 4 and 5 myself and fix the code on the spot.

## Steps

### 1 · Install (5 min)
```powershell
powershell -ExecutionPolicy Bypass -File tools\install.ps1
```
Restart 3ds Max. Customize › Customize User Interface › Category **Measured Light** › drag
**Material Inspector** onto a toolbar.
*If it fails:* send the PowerShell output. Manual route: `python tools\build_bundle.py` with Max's
`python.exe`, copy `dist\MaterialInspector.bundle` to `%APPDATA%\Autodesk\ApplicationPlugins\`.

### 2 · Self-test (5 min) — the most important step
File › New (empty scene) → Scripting › Run Script… → `tools\max_selftest.py`.
A message box reports `N/6 steps OK` and the file path. **Send me**
`%TEMP%\material_inspector_selftest.json`. It contains the real property names of every V-Ray /
Corona / Max class the Inspector touches, versions, and the scan-and-fix results on known-broken
test materials. With it I run:
```bash
python -m material_inspector.devtools.props_check material_inspector_selftest.json
```
and correct `material_inspector/max_adapter/props.py` in one pass.

### 3 · Panel on a real scene (10 min)
Open any real scene → click **Material Inspector** → **Scan scene** → **Export report…** (HTML and JSON).
Try **Fix selected** on two findings, then Ctrl+Z to confirm undo works. **Send:** both reports and
`%LOCALAPPDATA%\MeasuredLight\logs\inspector.log`.

### 4 · Normal-map convention (10 min, one-time)
For each renderer: new scene, a plane, material with `%TEMP%\material_inspector_selftest_tex\ST_NormalGL.png`
through VRayNormalMap / CoronaNormal (flip green **off**), one light from the top-left, render.
If the bumps look raised (lit top-left), that renderer expects **OpenGL**; if sunken, **DirectX**.
Tell me the two answers; they go into `normal_convention` in the settings file and switch on rule M007.
*(Internal check only — rendering is not part of the product.)*

### 5 · Batch scan for the false-positive test (30 min + review)
```bat
set MI_BATCH_DIR=D:\test_scenes
set MI_BATCH_OUT=D:\test_scenes\inspector_out
```
then Scripting › Run Script… › `tools\batch_scan.py` (or `3dsmaxbatch.exe tools\batch_scan.py`).
Open `inspector_out\review.csv`, fill **verdict** with `TP` (real problem) or `FP` (Inspector wrong), then:
```bash
python -m material_inspector.devtools.fp_rate review.csv
```
Sprint 3 exit: overall false-positive rate **< 5 %**. **Send:** `review.csv` and `summary.json`.

## What happens next
1. Property table corrected from the self-test → re-run step 2 → expect `6/6` and no "missing".
2. Rules with high false-positive rates get recalibrated (thresholds live in `RuleConfig`).
3. Sprint 4: licence keys, installer polish, beta to 10 studios (Gate 1).
