# MatForge Constitution

## Core Principles

### I. Determinism Owns the Wiring (NON-NEGOTIABLE)
Material *assembly* — node graphs, parameter values, editor placement — is
always produced by code from the recipe table, never by AI. AI may only ever
touch pixels (map generation/upscaling), and only behind the manifest
contract. If a wiring value cannot be derived from the physics table or a
class recipe, it is a spec gap, not a guess.

### II. Physics from Tables, Never Estimated
IOR, Fresnel behavior, fog, metalness, and class responses (sheen, coat,
translucency, anisotropy) come from `core/recipes.py` — the single source of
truth. Reference constants: dielectrics 1.5, window glass 1.52, water 1.33.
Hard guards ship as tests: fog color min channel > 0.9 (saturated-fog trap),
foliage must never refract, foliage must be 2-sided + clip opacity.

### III. Core/Max Split (Testable Without Max)
All image math lives in pure Python (`core/`) runnable and pytest-covered on
system Python. The Max layer (`maxplugin/`) is thin pymxs wiring only. Max's
bundled Python never gains dependencies; heavy work shells out to system
Python via the CLI. Same architecture that shipped MaxOptimizer and
lightmatch-max.

### IV. Defensive Wiring, Verified Live
Every V-Ray property write goes through candidate-name lists with logged
misses — never hard failures. No release claim without a `MAX_SMOKE` run in
real 3ds Max + V-Ray printing `SMOKE_OK`; property misses found there are
folded back into the candidate lists before the feature is called done.

### V. The Manifest Is the Contract
Map generators (heuristic v1, AI later) and the Max builder communicate only
through `manifest.json` + fixed map filenames (albedo, roughness, normal,
height, ao, opacity). Backends may be swapped freely; the contract may only
change with a spec amendment.

### VI. User Names, User Chooses — No AI Classification
The user supplies the reference image, the material name, the class, and the
resolution. The plugin never renames, never auto-classifies, never
second-guesses. Output always lands on a Material Editor sphere, visibly.

## Quality Standards

- Data maps (normal, roughness, height, opacity) load linear / gamma 1.0;
  albedo loads sRGB. Roughness plugs invert-free via roughness mode.
- AO is exported but never wired into materials (GI double-darkening).
- Uniform roughness is a defect: every class recipe carries a variation term.
- Every material must survive the Vantage handoff: no features outside the
  Vantage-supported set may be wired by default.
- Resolutions offered: 2K (2048), 4K (4096), 8K (8192) — exact powers of two.

## Development Workflow

- Spec-kit flow: spec → plan → tasks → implement; artifacts live in
  `specs/###-feature/`.
- Tests green (`py -3.12 -m pytest tests`) before any live-Max step.
- Live-Max validation is a user-run checkpoint (`MAX_SMOKE.py`); its output
  gates completion.
- Solo-founder momentum rule: ship direct — build → test → smoke → report;
  no ceremony between green tests and the user's hands.

## Governance

This constitution supersedes ad-hoc practice for all MatForge work.
Amendments are made by editing this file with a version bump and a dated
rationale line. Any plan or task that conflicts with Principles I, II, or VI
is rejected at review, not negotiated at implementation time.

**Version**: 1.0.0 | **Ratified**: 2026-07-21 | **Last Amended**: 2026-07-21
