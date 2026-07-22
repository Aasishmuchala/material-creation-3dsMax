# Tasks: MatForge Core (001)

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

Status legend: [X] done · [ ] open · [USER] requires the user at a live
3ds Max session.

## Phase 0 — Scaffold

- [X] T001 Repo layout `core/`, `maxplugin/`, `tests/`, `sample_maps/`
- [X] T002 Verify `py -3.12` has Pillow + numpy

## Phase 1 — Recipe Table (US2)

- [X] T003 13 class recipes in `core/recipes.py` (wood int/ext, concrete,
      stone, marble, metal brushed/painted, glass, fabric, leather, paint,
      foliage, generic)
- [X] T004 IOR + metal-tint reference constants; `get_recipe` /
      `class_choices` accessors
- [X] T005 Tests: recipe completeness, physics sanity (IOR/metalness/fog
      guards), foliage rules (no refraction, 2-sided, opacity)

## Phase 2 — Map Derivation (US1, US3, US5)

- [X] T006 De-light albedo (low-frequency division, mean-preserving)
- [X] T007 Height from detail; unit-length tangent normal; cavity AO
- [X] T008 Roughness = class base ± detail-driven variation
- [X] T009 Seamless edge cross-blend (interior untouched; normals derived
      post-blend)
- [X] T010 2K/4K/8K center-crop-square resize; alpha→opacity for foliage
- [X] T011 Tests: full-set generation, dimensions, de-light metric (SC-002),
      seam tolerance (SC-003), normal unit-length, roughness band, opacity
      presence per class

## Phase 3 — CLI + Manifest (Constitution V)

- [X] T012 `forge_cli.py` with --name/--type/--res/--out/--no-seamless;
      manifest.json; machine-readable stdout
- [X] T013 CLI end-to-end test

## Phase 4 — Max Layer (US1, US2, US4)

- [X] T014 `builder.py`: `_set_first` defensive writes; VRayMtl wiring
      (Fresnel, roughness mode, linear data maps, VRayNormalMap, class
      extras, glass block, foliage 2-sided wrap, opacity clip)
- [X] T015 Editor-sphere placement (first free slot) + editor focus
- [X] T016 Assign-to-selection + VRayDisplacementMod where recipe demands
- [X] T017 `forge_max.py` rollout UI (image browse, name prefill, class +
      resolution dropdowns, seamless/assign checkboxes, status line) +
      `run_matforge.py` launcher
- [X] T018 `MAX_SMOKE.py`: 4 representative classes, class-of assertions,
      editor placement, property-miss report; bundled sample map set

## Phase 4.5 — Correctness Hardening + Off-Max Wiring Proof

- [X] T023 Fix bump multiplier scale: recipes used 30-50 (percentage
      convention) but VRayMtl bump is a ~1.0 multiplier → rescaled to
      0.10-0.50; regression guard added in `test_core.py`
- [X] T024 Deterministic color management in `_bitmap_tex`: data maps forced
      linear via `openBitMap gamma:1.0`; albedo inherits project gamma;
      dropped the ambiguous VRayBitmap `color_space` guess
- [X] T025 Lock reflection IOR to refraction IOR so one dielectric IOR drives
      Fresnel + refraction (physically correct)
- [X] T026 Fix editor placement: "first free slot" heuristic was broken
      (default slots named "01 - Default", not "Material #") → now targets the
      active slot; documented + tested
- [X] T027 Broaden defensive candidate spellings (fog, opacity mode, bump,
      thin-walled) — additive-safe, improves first-run smoke odds
- [X] T028 Mock-pymxs harness (`tests/mock_pymxs.py`) + 29 wiring-logic tests
      (`tests/test_builder_logic.py`): proves class-correct wiring off-Max
      (foliage 2-sided/no-refraction, glass thin-walled/clamped-fog,
      metalness, data-map linearity, active-slot placement, displacement
      assignment, defensive fallback). 42/42 total green.
- [X] T029 Reconciled the `matforge-harden` review workflow (20 agents, 14
      findings verified, 9 confirmed real). Fixes applied:
      - **[CRITICAL] Reverted the bump-scale change** — research confirmed
        `texmap_bump_multiplier` is a 0-100 percentage (default 30), so the
        earlier 30→0.30 rescale (T023) was itself the bug. Values restored to
        30-50; comment + guards corrected. The workflow caught my own
        regression.
      - [HIGH] Displacement modifier now actually displaces: threads the
        height map into `assign_to_selection`, sets `dmod.texmap` + world-unit
        `amount` + 2D type; removed the mis-scaled material-slot displacement.
      - [HIGH] Normal map now tiles: periodic (roll-based) gradients +
        `make_seamless` on the encoded normal (np.gradient left a seam).
      - [MEDIUM] `_lowfreq` kept in float (PIL 'F' mode) — kills uint8 banding
        that rippled into every derived map.
      - [MEDIUM] `derive_albedo` de-lights on luminance only (hue-preserving)
        with clamped gain — no more hue shift / blowout / over-flatten.
      - [MEDIUM] Marble translucency activated with a small refraction + fog
        tint (was a silent no-op with black refraction).
      - [HIGH/MED] `forge_max` catches TimeoutExpired/OSError + surfaces CLI
        errors; `forge_cli` emits `{"ok":false,"error":...}`; typed name is
        sanitized.
      - Added regression tests (normal-tiles, working-displacement,
        no-displacement-without-height, percentage bump scale). 44/44 green.

## Phase 4.6 — Completeness-Audit Fixes (35 gaps found; genuine bugs fixed)

Second adversarial workflow (5 hunt axes, 50 candidates → 35 confirmed).
Bug/correctness items fixed in code; product-layer items scheduled (see
research.md §3b and the roadmap below).

- [X] T030 **Scene-units conversion** (bug-now): `displacement_mm` → system
      units via `rt.units.decodeValue`; was wrong-magnitude geometry in any
      non-mm scene. Tests for inch + mm scenes.
- [X] T031 **Undo transaction** wrapping create+place+assign (`pymxs.undo`);
      mock supports it.
- [X] T032 **Idempotent displacement** — remove prior `MatForge_Displace` mod
      before adding (no stacking/doubling on re-assign); test added.
- [X] T033 **Manifest validation** — schema version, known-class check,
      map-path existence; `build_from_manifest` + CLI round-trip tests (the
      production entry point was previously untested).
- [X] T034 **forge_max** success-path stdout parse hardened (no IndexError);
      generator warnings + wiring MISSes surfaced in the dialog.
- [X] T035 **Foliage opacity honesty** — read palette/`PA` alpha; warn on
      opaque RGB instead of emitting a solid quad; RGB-warn + RGBA-alpha tests.
- [X] T036 **Roughness decoupled** from raw specular highlights (measured on
      de-lit albedo); **AO** derived from seamless height (consistent w/ normal).
- [X] T037 Finite decompression-bomb cap; pinned `requirements.txt`.
- [X] T038 MAX_SMOKE breadth (marble/fabric/leather — coat/sheen/translucency)
      + displacement MISS-check. 52/52 pytest green.

## Phase 5 — Live-Max Validation (GATE for 001-done)

- [X] T019 **Ran live on real 3ds Max 2026 + V-Ray 7.30** — headless via
      `3dsmaxbatch.exe` (GUI opened on an un-capturable monitor, so pivoted to
      batch; see `HEADLESS_SMOKE.py` + `smoke_wrapper.ms`). First run: all 13
      classes built (12 VRayMtl + foliage VRay2SidedMtl), displacement modifier
      attached, **exactly 1 property miss**.
- [X] T020 The one miss — marble `translucency` mode — corrected to V-Ray 7's
      real `translucency_on` (int enum, MAXScript-only; Chaos docs). Mock schema
      + marble test updated; **re-ran headless → `SMOKE_OK`, 0 misses.** 52/52
      pytest green.
- [X] T021 **Render check done headless** (`RENDER_CHECK.py` via 3dsmaxbatch):
      reset scene → V-Ray 7 renderer → ground + 4 boxes, each with a real
      MatForge material (wood, brushed metal, marble, glass) → dome+key light →
      **rendered to `render_check.png`, RENDER_OK**. Visual result confirms each
      class behaves correctly: diffuse boxes show colour, metal reads reflective
      (metalness path live), **glass renders transparent/refractive**, ground
      shows bump/normal relief + reflection. Caveat: all boxes share the one
      bundled wood-derived sample map set, so colours look similar and the metal
      is dark (dark input albedo) — a *test* artifact, not a wiring bug; real
      per-material references give distinct maps. Still outstanding: the
      interactive dialog→editor-sphere UX (`forge_max.py` rollout) needs a live
      GUI session — batch has no Material Editor.
- [X] T022 Closed out: spec Status → **Validated**; memory + README updated.

## Finalized roadmap (out of 001 scope — see research.md for rationale)

Reordered from the original 002–005 sketch after the material-creation research
+ critique (2026-07-21). Full detail: [research.md](research.md) §3.

**v1-gap — correctness & Vantage-safety hardening (deterministic, small):**
- [ ] G-00a Async generation with progress + Cancel (8K freezes Max for minutes)
- [ ] G-00b Install/packaging: macroscript + menu/toolbar button (not "Run Script")
- [ ] G-00c Bring-your-own-maps on-ramp (wire existing scan sets — opens the
      paying-studio market; near-zero code, reuses build_from_manifest)
- [ ] G-00d Iterate/re-edit: per-material overrides (roughness/bump/de-light/
      tiling) seeded from recipe, persisted in manifest; "regenerate with tweaks"
- [ ] G-00e Reference capture spec + deterministic input-quality gate (warn on
      clipped highlights / hard shadows / low res / perspective)
- [ ] G-00f Class-picker tooltips + example thumbnails + "unsure → generic"
- [ ] G-01 Normal via VRayNormalMap + DirectX↔OpenGL green-flip toggle + Raw tag
- [ ] G-02 16-bit height/displacement output (kill 8-bit terracing)
- [ ] G-03 Physical-plausibility clamps (albedo 30–240 sRGB, roughness 0.04–0.98,
      diffuse+reflection ≤ 1 energy, metals metalness=1 + non-elevated diffuse)
- [ ] G-04 Relative texture paths + explicit per-slot color space (never `Auto`)
- [ ] G-05 Color-swatch working-space: detect ACEScg/OCIO, convert VRayColor tints
- [ ] G-06 Confirm VRayBitmap loader everywhere; canonical naming + node stamp
- [ ] G-07 `.tx` tiled/mip conversion; downtier height; 16K hard cap

**v2 — scale, repeat-breaking, Vantage parity (deterministic):**
- [ ] V2-00a Batch mode: folder/CSV of (image,name,class,res) → queue + summary
- [ ] V2-00b Optional auto white-balance (grey-world/white-patch) on de-lit albedo
- [ ] V2-01 Real-world scale (`real_world_mm` per recipe) + px/m texel budget
- [ ] V2-02 VRayUVWRandomizer stochastic tiling + constrained rotation/offset
- [ ] V2-03 VRayTriplanarTex projection for un-UV'd geometry
- [ ] V2-04 Deterministic de-light v2 (highlight/shadow suppression + AO split)
- [ ] V2-05 Vantage-safe pre-emit validator + per-material parity report
      (incl. displacement 2D-vs-3D decision)

**v2.5 — deterministic material families (no AI, no blend):**
- [ ] V25-01 Velvet/sheen, glazed ceramic, water/liquids, SSS solids, emissive,
      cutout/perforated, brushed-metal anisotropy rotation
- [ ] V25-02 Taxonomy expansion: chrome/mirror, glossy/matte plastic, rubber,
      carpet, corten, terracotta (everyday archviz materials with no class today)

**v3 — last-15% realism layers (deterministic masks; grunge gated):**
- [ ] V3-01 VRayBlendMtl layering foundation (base+coat+mask, ≤10)
- [ ] V3-02 VRayEdgesTex edges (+ bake/accept-sharp Vantage fallback),
      VRayDirt, VRayCurvature, VRayMultiSubTex, micro-roughness/normal
- [ ] V3-03 Wet-surface blend (puddle mask from height map)
- [ ] V3-04 Bake-to-bitmap fallback for Vantage-unsafe procedurals

**v3-gate — render-based parity proof (promoted from backlog):**
- [ ] VG-01 Calibrated lookdev scene + turntable/grazing/tiled-swatch,
      Max-preview vs Vantage side-by-side

**v4 — AI/measured backend behind the manifest:**
- [X] V4-01 **fal PATINA backend built + working** (`forge_fal.py`): reference →
      studio-grade de-lit basecolor/normal/roughness/**metalness**/height, up to
      4K, seamless, behind the same manifest contract (zero Max-side change).
      Builder upgraded to wire per-pixel `texmap_metalness` when present (+test,
      53 green). Verified live: generated 2048px wood/marble/metal sets, rendered
      in V-Ray with 0 property misses. Needs `FAL_KEY` (configured).
- [~] V4-01b Poly Haven CC0 retrieval helper (used ad-hoc for references +
      HDRIs via api.polyhaven.com; not yet a formal in-plugin path).
- [ ] V4-02 Spectral metals; car paint; decals

**business workstream (parallel — not blocking the material roadmap):**
- [ ] BIZ-01 Commercialization: license/activation, pricing tier, update channel,
      distribution (Cosmos / Autodesk App Store / Gumroad / ScriptSpot), EULA
- [ ] BIZ-02 CI (GitHub Actions running pytest on push; deps now pinned)

**backlog:**
- [ ] B-01 Explicit editor-slot picker + Slate view
- [ ] B-02 Multi-material segmentation of one photo (AI segmentation — gated)
- [ ] B-03 Library management (.vrmat export, pixel-hash dedup/relink)
- [ ] B-04 8K memory guard + slow-marked 8K generation test (peak ~3–4 GB;
      plan.md's 1.5 GB estimate was ~2.5× low)
