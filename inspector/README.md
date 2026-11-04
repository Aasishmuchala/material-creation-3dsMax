# Material Inspector — Phase 1 of the 3ds Max material plugin

Scans every V-Ray and Corona material in a 3ds Max scene, finds physically wrong
settings and broken texture setups, and fixes them with one click (undoable).
It checks material parameters and texture pixels only — it never renders.

## Status (Sprints 1–3: everything that can be done without 3ds Max)

| Part | State |
|---|---|
| Rule engine (18 rule IDs, R001–R020) + pixel checks (12, M013 experimental and off by default) | done, tested |
| HTML / JSON report | done, tested |
| CLI for texture folders (works without Max) | done, tested |
| Scene walker (VRayMtl, CoronaPhysicalMtl, CoronaLegacyMtl, Multi/Sub, nested texmaps) | done, tested against a fake MAXScript runtime |
| One-click fixes with undo | colour space, parameters, roughness toggle, invert map, glass absorption, normal node — tested on the fake runtime |
| Settings file (thresholds, disabled rules, normal convention) | done, tested |
| Crash log (`%LOCALAPPDATA%\MeasuredLight\logs`) | done, tested |
| Dockable PySide6/PySide2 dock | tested headless against the fake runtime |
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
| R004 | error | Texture file missing, or the path is a folder, a broken/looping link or unreadable |
| R005 | error | Gloss map in a roughness slot or vice versa (from the file name) |
| R006 | error | Normal map plugged straight into bump without a normal-map node |
| R007 | info | Texture graph deeper than `MAX_TEXMAP_DEPTH` (8) — deeper maps were not inspected |
| R008 | info | Parameter is NaN / ±infinity — no rule can judge it (other rules skip it) |
| R010 | error / warning | Base colour luminance < 30 / < 50 / > 240 sRGB (snow, reference whites exempt) |
| R011 | warning | Metal darker than any real metal (linear luminance < 0.40) |
| R012 | warning | Constant metalness between 0.05 and 0.95 |
| R013 | error / warning | IOR outside 1–3 / outside 1.30–1.80 |
| R014 | warning | Glass with no absorption colour (fix: clear soda-lime, Rubin 1985) |
| R015 | warning | VRayMtl BRDF is not GGX |
| R016 | warning | Reflection glossiness exactly 1.0 on a non-glass material |
| R017 | info | Legacy material type (Corona Legacy Mtl) |
| R018 | warning | Metal named after a real metal (gold, copper, steel, alu, …) whose swatch is > 0.10 linear from that metal's measured F0 (fix: set the F0 from `matphys`) |
| R020 | info | Looks AI-generated: M003 and M004 on one material (M010 / M013 join once calibrated on real scans, see docs/VERIFY.md row 12) |
| M001/M002 | error / warning | Albedo map pixels darker / brighter than real surfaces |
| M003 | warning | Roughness/gloss map is effectively one value (also: p01–p99 span < 0.04, i.e. noise on a constant) |
| M004 | warning | Metalness map mostly grey |
| M005 | error | Visible tiling seam, measured at native resolution: robust z of the wrap step (median / MAD of the interior adjacent-row/column steps) minus 1.5 × the robust z of the largest interior step > 4 — plank edges and grout lines on the border recur inside the tile and stay quiet (`RuleConfig.seam_z_max`, `seam_tail_ratio`) |
| M006 | warning | Normal map doesn't match the height map |
| M007 | error | Normal map convention (OpenGL / DirectX) differs from what the slot expects |
| M008 | info | Detected normal-map convention |
| M009 | info | Once per scan: M007 is inactive because `normal_convention` is unset for a renderer whose materials carry normal maps (see `docs/FIRST_WINDOWS_SESSION.md` step 4) |
| M010 | warning | Albedo carries a smooth brightness gradient — baked lighting, shadow or vignette (quadratic fit to 16×16 sRGB-luminance box means: range / mean > 0.12, R² ≥ 0.5, local steps follow the fit ≥ 0.5; planks/tiles/bricks/marble pass) |
| M012 | error | Height map polarity inverted relative to the normal map (corr_x < −0.3; fix: invert the height map) |
| M013 | info | **Experimental, off by default** (`RuleConfig.experimental_off`; enable with `"rules": {"experimental_off": []}`) until calibrated on real scans (docs/VERIFY.md row 12). Data map (rough/gloss/normal/height ≥ 512 px) has a spectral cut-off at Nyquist/k (k = 3–8): power above it < 1 % of the band below — likely upscaled ≥ k×. Masks, bevels and smooth maps are skipped |
| M900 | info | Map could not be read, is too small (< 8 px) for a check, or a check failed on it — one bad map never stops the scan |

Rules cover VRayMtl, CoronaPhysicalMtl and OpenPBR Material. Physical constants (metal F0 at
650/550/450 nm, glass absorption, albedo limits) come from the shared `matphys/` package at
the repo root — the same tables MatForge's builders use. `tools/build_bundle.py` copies it into
the bundle next to `material_inspector`.

All thresholds are in `core/rules.py: RuleConfig` and get calibrated in Phase 0.

## Run the tests

```bash
cd material-inspector && python3 -m pytest -q
```

## Check a folder of PBR textures (no 3ds Max needed)

```bash
python3 -m material_inspector.cli check-folder path/to/textures --report report.html --normal-convention opengl
```

Exit codes: `0` clean, `1` errors found, `2` could not check (folder missing, not a folder,
unreadable, or no texture sets in it — the reason is printed on stderr).

Settings (`inspector.json`) are type-checked key by key: a wrong type, a NaN or negative
threshold, an unknown rule ID or a `max_side` outside 16–65536 gives a warning and that key
keeps its default. The dock shows the warning count on its first screen.

## Install in 3ds Max

```powershell
powershell -ExecutionPolicy Bypass -File tools\install.ps1
```

Restart 3ds Max, then add **Measured Light › Material Inspector** to a toolbar (Customize User Interface).
The dock has two steps: press **Check my scene**, then **Fix all N** (each fix can be undone with Ctrl+Z).
Findings are grouped as **Will render wrong**, **Worth a look** and **Notes**; each row has a
**Fix** button (or **Manual** when it needs a hand fix) and **Why?** for the detail and rule id.
**Export report** is on every screen. The **Settings** sheet shows `%APPDATA%\MeasuredLight\inspector.json`
and has **Open settings file** and **Reload**. The dock uses the shared `forgeui/` kit, which the bundle copies in.

![Material Inspector idle screen](docs/ui/screens/inspector_idle_400.png)

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
