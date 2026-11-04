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
| 10 | OpenPBR Material MAXScript class name and property names (Max 2026/2027) | `max_adapter/props.py` (`OpenPBRMaterial` and aliases, `NORMAL_INPUT_SLOTS`) | Dump with `tools/dump_props.ms` on an OpenPBR Material and correct the table. |
| 11 | R018 token→metal mapping false-positive rate (`steel` → stainless, `alu` → aluminium, first token wins; painted metals named "Gold_…" with metalness 1) | `core/rules.py` `METAL_TOKENS`, `metal_f0_tolerance` 0.10 | Batch-scan real scenes (`tools/batch_scan.py`); count R018 hits that are not the named metal, or are a deliberate tint (e.g. rose gold, anodised). Warning only until then. |
| 12 | M010 / M013 thresholds on real scans (M010: trend range/mean > 0.12, R² ≥ 0.5, consistency ≥ 0.5; M013: spectral ratio < 0.01 at k = 3–8, skipped under 512 px or when < 5 % of pixels curve in both axes). Both are **out of R020's `AI_SIGNATURES`** until this row is done | `core/map_checks.py` `smooth_trend`, `check_baked_lighting`, `upscale_score`, `curved_fraction`, `check_upscaled`; `core/inspector.py` `AI_SIGNATURES` | Run `devtools/fp_rate` on CC0 scan sets (Poly Haven, ambientCG) vs. generator output, then decide whether M010/M013 rejoin `AI_SIGNATURES`. Synthetic 1024² measurements (`tests/test_ai_faults.py`; old score → new score, r2, consistency): wood planks 0.42–0.56 0.61 → 0.33/0.94/0.01; stone 3×3 ±10 % 0.37 → 0.20/0.58/0.01; brick ±8 % 0.33 → 0.04/0.05; marble ±6 % 0.37 → 0.08/0.11; concrete mottling 1/8 tile 0.26 → 0.04/0.05; dark planks 0.20–0.28 0.64 → 0.38/0.94/0.01 — all pass (old limit 0.25 fired all six). Ramp 0.6–1.4 0.75/1.00/1.00, ramp 0.85–1.15 0.28/1.00/1.00, vignette 0.4 0.42/0.95/0.98, vignette 0.25 0.24/0.95/0.98, marble+ramp 0.27/0.69/1.19, concrete+vignette 0.24/0.63/1.07 — all fire. 300-seed sweep: 0 % false fires on the six textures, 100 % on ramps/vignettes, 68–100 % on light baked over texture (worst: brick + vignette). M013 (curved fraction, spectral ratio): native noise 0.98, 1.0; 2× bicubic 0.92, 8e-2 (pass); 4× bicubic 0.63, 5e-4; 6× 0.32, 5e-5; 8× 0.14, 3e-5; 4× bilinear 0.20, 1e-3 (all fire); binary 4×4 mask 0.000, bevel tiles 0.001–0.002, smooth roughness 3 cycles 0.000, normal from σ-12 height 0.000 (all skipped; old score fired all four). Metalness is no longer checked. Known limits: a native map blurred with σ ≳ 2 px is spectrally identical to an upscale and fires M013 (σ 2: 0.50, 6e-4); a stepped albedo that is also lit fires M010 only when the light dominates; low-contrast upscales (8-bit steps ≲ 3 LSB) are skipped. |
| 13 | M012 height-polarity sign (negative corr_x = inverted height) and V-Ray fog fix via `matphys.to_vray_fog` | `map_checks.check_normal_convention`, `fixes._fix_set_absorption` | Render a displaced plane with a known OpenGL normal + height pair; confirm corr_x > 0. Fog: see row 5. |
| 14 | Corona Complex IOR toggle name (`useComplexIor`, `complexIorEnabled`, `metalComplexIor`, same candidates as MatForge `corona_props` `complex_ior_on`); R011/R018 skip when on | `max_adapter/props.py` `PARAMS["CoronaPhysicalMtl"]["complex_ior"]`, `scene.read_material` | `showProperties` on a CoronaPhysicalMtl with Complex IOR ticked; the report's `property_resolution.missing` must not list `complex_ior`. |

### Row 10 detail: OpenPBR candidate names (all UNVERIFIED)

The first name in each list is the one `tests/test_openpbr_adapter.py` builds its fake material with. Correct the lists in `max_adapter/props.py` from a `tools/dump_props.ms` dump.

| Kind | Canonical | Candidate names |
|---|---|---|
| class | material | `OpenPBRMaterial`, `OpenPBR_Material`, `OpenPBRSurfaceMaterial` |
| param | base_color | `base_color`, `baseColor` |
| param | roughness | `specular_roughness`, `roughness` |
| param | metalness | `base_metalness`, `metalness`, `metallic` |
| param | ior | `specular_ior`, `ior` |
| param | refraction_amount | `transmission_weight`, `transmission` |
| param | absorption_color | `transmission_color` |
| param | absorption_distance | `transmission_depth` |
| param | thin_walled | `geometry_thin_walled`, `thin_walled` |
| slot | BASE_COLOR | `base_color_map` |
| slot | ROUGHNESS | `specular_roughness_map`, `roughness_map` |
| slot | METALNESS | `base_metalness_map`, `metalness_map` |
| slot | NORMAL (also `NORMAL_INPUT_SLOTS`) | `geometry_normal_map`, `normal_map` |
| slot | BUMP | `bump_map` |
| slot | DISPLACEMENT | `displacement_map`, `geometry_displacement_map` |
| slot | OPACITY | `geometry_opacity_map`, `opacity_map`, `cutout_map` |
| slot | COAT | `coat_weight_map` |
| slot | SHEEN | `fuzz_weight_map` |
| slot | EMISSION | `emission_color_map` |
