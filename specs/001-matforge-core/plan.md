# Implementation Plan: MatForge Core (001)

**Spec**: [spec.md](spec.md) | **Constitution**: `.specify/memory/constitution.md` (v1.0.0)

**Status**: Implemented through Phase 4; Phase 5 (live-Max validation) awaits a
user-run smoke check. This plan documents the as-built architecture plus the
remaining gated work so future features (002+) extend it coherently.

## Technical Context

- **Host**: 3ds Max 2026 (pymxs, bundled Python untouched), V-Ray 7.30,
  Windows 11. Vantage downstream.
- **Compute**: system Python 3.12 (`py -3.12`) with Pillow 12 + numpy 2.4 for
  all image math; Max shells out via `subprocess`.
- **Proven prior art**: MaxOptimizer (defensive pymxs rule engine,
  SMOKE-gated), lightmatch-max (core/Max split, parity-tested numpy core).
  MatForge deliberately reuses both patterns.

## Architecture (as built)

```
UI (maxplugin/forge_max.py)          MXS rollout; reads user inputs only
  └─► subprocess: py -3.12 forge_cli.py <img> --name --type --res
        └─► core/maps.py             de-light, roughness±variation, normal,
                                     height, AO, seamless; 2K/4K/8K
        └─► manifest.json            THE contract (Constitution V)
  └─► maxplugin/builder.py           recipe-driven VRayMtl wiring,
                                     _set_first candidate lists, editor slot,
                                     optional assign + VRayDisplacementMod
core/recipes.py                      single source of truth (13 classes)
```

Key decisions and their rationale:

1. **Subprocess boundary, not in-Max imaging** — Max's Python has no
   Pillow/numpy and must stay clean; the boundary also makes the generator
   swappable (heuristic → AI) without touching Max code.
2. **Recipe table as data, not code paths** — class differences are values,
   so adding a class is a dict entry + tests, never new wiring logic.
3. **Roughness mode ON** — plugs derived roughness maps directly, eliminating
   the invert-vs-glossiness error class entirely.
4. **Defensive property writes** — V-Ray renames properties across builds;
   `_set_first` + logged misses turns an API break into a patchable report.
5. **AO generated, never wired** — V-Ray GI already occludes; wiring AO
   double-darkens. Kept on disk for compositing or non-GI uses.
6. **Foliage wraps in VRay2SidedMtl** — translucency for thin surfaces at
   ~1% of refraction's cost; refraction on leaves is forbidden by test.

## Phases

### Phase 0 — Scaffold ✅
Repo layout (`core/`, `maxplugin/`, `tests/`, `sample_maps/`), Python 3.12
environment verified (Pillow/numpy present).

### Phase 1 — Recipe Table ✅
13 class recipes + IOR/metal-tint reference constants + physics guards.
Exit: recipe completeness + sanity tests green.

### Phase 2 — Map Derivation Core ✅
De-light (low-frequency division), height (detail extraction), normal
(gradient, unit-length), roughness (base ± detail-driven variation), AO
(cavity approximation), seamless edge cross-blend, resolution handling.
Exit: 13 pytest checks green including measurable de-lighting (SC-002) and
seam tolerance (SC-003).

### Phase 3 — CLI + Manifest ✅
`forge_cli.py` argparse front end; machine-readable last-line JSON; manifest
written beside maps. Exit: CLI end-to-end test green.

### Phase 4 — Max Layer ✅ (code-complete)
`builder.py` (wiring, editor placement, assignment, displacement mod),
`forge_max.py` (rollout UI, subprocess orchestration), `run_matforge.py`
launcher, `MAX_SMOKE.py` (4 representative classes + editor placement +
class-of assertions + property-miss report), bundled 2K sample map set.

### Phase 5 — Live-Max Validation ⏳ (GATE — user action required)
Run `MAX_SMOKE.py` in Max 2026. Outcomes:
- `SMOKE_OK` → 001 is done; tag v1.
- `SMOKE_OK_WITH_MISSES` → fold listed property names into candidate lists,
  re-run, then done.
- `SMOKE_FAIL` → traceback names the exact wiring step; fix and re-run.
Then one real-world pass: user's own reference (patio/chair) through the
dialog, visual check of the sphere + a test render.

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| V-Ray 7 property names differ from candidates | Designed-in: miss report from smoke run feeds candidate lists (Constitution IV) |
| Sandbox file-write virtualization (files invisible to Max) | Known env gotcha; if Max can't see repo files, user copies repo or runs scripts from a shell-created path — verify during Phase 5 |
| Heuristic map quality below expectation on hard references | Scope-fenced: v1 promise is correct *wiring* + honest maps; AI backend is feature 002 behind the same manifest |
| 8K memory pressure during generation | float32 pipeline + resize-trick blurs; 8K ≈ 6 arrays × 256 MB, acceptable on 64 GB target machine |
| Editor slot overwrite when all 24 occupied | Documented; explicit slot picker in backlog |

## Feature Roadmap Beyond 001

**Superseded — the roadmap is now finalized in [research.md](research.md)**
(6-dimension research → synthesis → adversarial TD critique → reconciliation).
The original 002–005 sketch was reordered: base-shader correctness and output
accuracy (de-light, plausibility clamps, color-swatch working-space) pulled
early; scale/tiling/Vantage-parity inserted before the AI backend; cheap
deterministic material families split into their own release; and the
render-based lookdev parity gate promoted out of backlog because it is what
*proves* the Vantage-safe moat. Summary:

- **v1-gap** — correctness & Vantage-safety hardening (green-flip, 16-bit
  height, plausibility clamps, relative paths + explicit color space, swatch
  working-space, VRayBitmap, canonical naming, `.tx`).
- **v2** — real-world scale + texel density, stochastic tiling, triplanar,
  deterministic de-light v2, Vantage-safe pre-emit validator.
- **v2.5** — deterministic material families (velvet, glazed ceramic, water,
  SSS solids, emissive, cutout, anisotropy rotation).
- **v3** — VRayBlendMtl foundation + last-15% realism layers (edges/dirt/wear/
  per-element/wet), grunge bitmaps gated behind the manifest.
- **v3-gate** — calibrated lookdev + turntable/grazing/tiled-swatch parity proof.
- **v4** — AI/measured map backend behind the manifest (+ Poly Haven CC0,
  spectral metals, car paint, decals).
- **backlog** — multi-material segmentation, library management, slot picker.

See [research.md](research.md) for per-item rationale, the six research
dimensions, what v1 already gets right, the out-of-scope list, and sources.
