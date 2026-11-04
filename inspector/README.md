# Material Inspector — Phase 1 of the 3ds Max material plugin

Scans every V-Ray and Corona material in a 3ds Max scene, finds physically wrong
settings and broken texture setups, and fixes them with one click (undoable).
It checks material parameters and texture pixels only — it never renders.

## Status (Sprints 1–3: everything that can be done without 3ds Max)

| Part | State |
|---|---|
| Rule engine (17 rules) + pixel checks (8) | done, tested |
| HTML / JSON report | done, tested |
| CLI for texture folders (works without Max) | done, tested |
| Scene walker (VRayMtl, CoronaPhysicalMtl, CoronaLegacyMtl, Multi/Sub, nested texmaps) | done, tested against a fake MAXScript runtime |
| One-click fixes with undo | colour space, parameters, roughness toggle, invert map, glass absorption, normal node — tested on the fake runtime |
| Settings file (thresholds, disabled rules, normal convention) | done, tested |
| Crash log (`%LOCALAPPDATA%\MeasuredLight\logs`) | done, tested |
| Dockable PySide6 panel | tested headless against the fake runtime |
| Self-test for the first Windows run (`tools/max_selftest.py`) | done; executed end-to-end against a fake `pymxs` |
| Property-table checker (`devtools/props_check`) | done, tested |
| Batch scanner + false-positive tooling (`tools/batch_scan.py`, `devtools/fp_rate`) | done; fp_rate tested, batch_scan untested (needs Max) |
| Windows installer (`tools/install.ps1`) and CI (`.github/workflows/tests.yml`) | written, not yet run |
| Macroscript + Autodesk .bundle | written, **not yet run in 3ds Max** |

**Next: `docs/FIRST_WINDOWS_SESSION.md` (60–90 min).** Before trusting it in production, work through `docs/VERIFY.md` — the MAXScript property
names could not be checked against current V-Ray 7 / Corona docs from the build machine.

## What it checks

| ID | Severity | Check |
|---|---|---|
| R001 | error | Data map (roughness, gloss, metal, normal, bump, height, opacity) loaded as sRGB |
| R002 | warning | 8/16-bit colour map loaded as linear |
| R003 | info | Colour space unreadable — reported, never guessed |
| R004 | error | Texture file missing |
| R005 | error | Gloss map in a roughness slot or vice versa (from the file name) |
| R006 | error | Normal map plugged straight into bump without a normal-map node |
| R010 | error / warning | Base colour luminance < 30 / < 50 / > 240 sRGB (snow, reference whites exempt) |
| R011 | warning | Metal darker than any real metal (linear luminance < 0.40) |
| R012 | warning | Constant metalness between 0.05 and 0.95 |
| R013 | error / warning | IOR outside 1–3 / outside 1.30–1.80 |
| R014 | warning | Glass with no absorption colour (fix: clear soda-lime, Rubin 1985) |
| R015 | warning | VRayMtl BRDF is not GGX |
| R016 | warning | Reflection glossiness exactly 1.0 on a non-glass material |
| R017 | info | Legacy material type (Corona Legacy Mtl) |
| M001/M002 | error / warning | Albedo map pixels darker / brighter than real surfaces |
| M003 | warning | Roughness/gloss map is effectively one value |
| M004 | warning | Metalness map mostly grey |
| M005 | error | Visible tiling seam (wrap-boundary z-score > 4) |
| M006 | warning | Normal map doesn't match the height map |
| M007 | error | Normal map convention (OpenGL / DirectX) differs from what the slot expects |
| M008 | info | Detected normal-map convention |

All thresholds are in `core/rules.py: RuleConfig` and get calibrated in Phase 0.

## Run the tests

```bash
cd material-inspector && python3 -m pytest -q
```

## Check a folder of PBR textures (no 3ds Max needed)

```bash
python3 -m material_inspector.cli check-folder path/to/textures --report report.html --normal-convention opengl
```

## Install in 3ds Max

```powershell
powershell -ExecutionPolicy Bypass -File tools\install.ps1
```

Restart 3ds Max, then add **Measured Light › Material Inspector** to a toolbar (Customize User Interface).
Settings: the panel's **Settings…** button opens `%APPDATA%\MeasuredLight\inspector.json`.

## Layout

```
material_inspector/
  core/          renderer-neutral: model, colour, rules, map_checks, inspector, report
  max_adapter/   3ds Max only: props (MAXScript names), scene walker, fixes, PySide6 panel
  devtools/      props_check (verify property table), fp_rate (false-positive rate)
  cli.py         folder checker
bundle/          Autodesk application package (PackageContents.xml, startup macroscript)
tools/           install.ps1, build_bundle.py, max_selftest.py, batch_scan.py, dump_props.ms
tests/           pytest suite + fake MAXScript runtime
docs/            FIRST_WINDOWS_SESSION.md (runbook), VERIFY.md, sample_report.html
```
