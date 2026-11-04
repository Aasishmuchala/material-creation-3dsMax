# Verify in 3ds Max before Sprint 2 ends

The core (rules, map checks, report, CLI, config, panel) is tested here: 60 tests, synthetic data.
All items below are covered by one run of `tools/max_selftest.py` plus steps 3–5 of `FIRST_WINDOWS_SESSION.md`.
The 3ds Max layer is tested only against a fake MAXScript runtime. These assumptions
must be confirmed on a real machine with 3ds Max 2025–2027, V-Ray 7 and Corona 13/14.

| # | Assumption | Where | How to check |
|---|---|---|---|
| 1 | MAXScript property names for VRayMtl, CoronaPhysicalMtl, CoronaLegacyMtl, Output | `max_adapter/props.py` | `tools/max_selftest.py` dumps them; `python -m material_inspector.devtools.props_check` compares. The report's `property_resolution.missing` list shows every name that didn't resolve. |
| 2 | Bitmap colour-space property and values (Bitmaptexture under OCIO, VRayBitmap, CoronaBitmap) | `props.py` `BITMAP_CLASSES`, `COLOR_SPACE_VALUES` | Load one texture as sRGB and one as Raw in each bitmap type; dump properties. |
| 3 | `brdf_type` integer for GGX is 3 | `props.py` `VRAY_BRDF` | Set GGX in the UI, read `brdf_type`. |
| 4 | Corona `metalnessMode` 1 = metal | `scene.py` `read_material` | Toggle metal mode, read the value. |
| 5 | V-Ray fog multiplier ↔ absorption distance | `fixes.py` `_fix_set_absorption` | Phase 2 parameter mapping (marked approximate). |
| 6 | Normal-map convention each renderer expects (OpenGL vs DirectX) | `InspectorOptions.normal_convention` | Render a known OpenGL test map in each renderer; set the option. Until then the Inspector reports the detected convention but does not flag mismatches. |
| 7a | `invert_map` fix uses the Output map (`map1`, `output.invert`) | `fixes.py` `_fix_invert_map` | Self-test props dump of `Output`. |
| 7 | Startup script and macroscript load from the bundle | `bundle/…/material_inspector_startup.ms` | `python tools/build_bundle.py`, install, restart Max, find "Measured Light › Material Inspector" in Customize UI. |
| 8 | numpy + Pillow available in Max's Python | `core/map_checks.py` | In Max: `python.Execute "import numpy, PIL"`. If missing: `"%ProgramFiles%\Autodesk\3ds Max 2026\Python\python.exe" -m pip install --user numpy pillow`. |
| 9 | Real-data false-positive rate | whole Inspector | Sprint 3: 50 downloaded archviz scenes, < 5 % false positives. Could not download CC0 sets from this sandbox (network policy). |
