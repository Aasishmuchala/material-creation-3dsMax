# MatForge v1 — reference image → render-ready V-Ray material

One click: reference image + name + material type + resolution (2K/4K/8K)
→ PBR maps derived, physically-correct VRayMtl wired, dropped on a
Material Editor sphere, optionally assigned to selection.

## Compatibility — 3ds Max 2022 → 2027
- **In-Max code runs on Python 3.7** (Max 2022) through 3.13 (Max 2027) —
  vermin-verified, no 3.8+ syntax, no type annotations that would break on 3.7.
- **Map generation runs in a system Python** (auto-resolved: `py -3.12` → `py -3`
  → `python`, first one that has Pillow+numpy) — never Max's bundled Python, so
  the Max version doesn't matter. Requires a system Python 3 with `pip install
  Pillow numpy` (and `fal-client` for the Ultra engine).
- **V-Ray**: every property is written through defensive candidate lists, so
  name drift across V-Ray 5/6/7 logs a MISS instead of crashing. Metalness maps
  need V-Ray 5+ (all supported Max versions ship it). Confirmed `SMOKE_OK` on
  Max 2026 + V-Ray 7.30.
- **UI**: the web **panel** needs the embedded IE-based WebBrowser (fine on
  most setups; the installer sets IE11 emulation). If it won't render (IE
  removed / newer .NET), the **rollout** — "MatForge (simple)" — is a pure
  MAXScript UI that works on every version with no browser at all.
- `pymxs.undo` is used only if present (older builds fall back to a no-op).

## Install (once)
1. Open Max 2026 (V-Ray 7 installed).
2. Scripting > Run Script... > **`install_matforge.ms`** — registers the
   **MatForge** actions, sets the IE11 emulation the panel needs, and opens it.
3. For one-click access later: Customize > Customize User Interface > Toolbars,
   category **MatForge**, drag **MatForge** onto a toolbar. (Max 2025+ dropped
   the classic menu API, so it's a toolbar button, not a menu.)

## Use — the panel (dark, three tabs)
- **CREATE** — pick a reference, name it, choose material type, resolution, and
  **Engine**:
  - **Fast** — deterministic heuristic maps, offline, no key.
  - **Ultra** — fal **PATINA** AI maps (studio-grade de-lit, up to 4K, real
    metalness) with a **Fable-5** vision prompt written from the photo.
  → **Create Material → Sphere** drops the wired VRayMtl on a Material Editor
  sphere; tick "Assign to selected objects" to also apply it (+ displacement).
- **SETTINGS** — paste your **fal** and **omega (Fable-5)** keys; saved to
  `_keys.json` (git-ignored), overriding the built-in fallback.
- **HELP** — a Fable-5 chat for when you're stuck on MatForge / V-Ray / workflow.

A plain rollout (`run_matforge.py`, action "MatForge (simple)") is the fallback
if the embedded browser won't render on your box.

## Plugin files
```
install_matforge.ms   run once -> MatForge menu + toolbar actions
matforge_panel.ms     hosts ui/panel.html in a dockable Max webview + bridge
ui/panel.html         the dark REFGRADE-style control panel
run_matforge.py       opens the simple rollout (fallback)
maxplugin/forge_max.py  UI backend: engine routing (Fast/Ultra) + panel bridge
```

## What the wiring guarantees (per material class, from `core/recipes.py`)
- Fresnel ON, IOR from physics table (1.5 dielectrics, 1.52 glass, ...)
- Roughness mode ON, roughness map plugged directly (no gloss-invert errors)
- Normal via VRayNormalMap at gamma 1.0; data maps loaded linear
- Glass: thin-walled, fog clamped near-white, affect-shadows ON
- Foliage: clip-mode opacity + VRay2SidedMtl translucency, **never refraction**
- Fabric sheen, leather/lacquer coat, marble translucency, brushed-metal
  anisotropy
- AO map exported but not wired (V-Ray GI already occludes; baked AO
  double-darkens)

## Architecture
```
forge_fal.py          fal PATINA backend: image -> studio-grade PBR maps
                      (basecolor/normal/roughness/metalness/height, de-lit,
                      seamless, up to 4K) behind the SAME manifest contract.
                      Needs FAL_KEY. This is the v4 AI quality upgrade.
forge_cli.py          system Python (py -3.12): image -> maps (PIL/numpy)
core/maps.py          deterministic derivation: de-light, normal, roughness,
                      height, AO, seamless tiling, 2K/4K/8K
core/recipes.py       physics + wiring table (single source of truth)
maxplugin/builder.py  in-Max pymxs wiring (defensive property candidates)
maxplugin/forge_max.py  dialog UI
MAX_SMOKE.py          run inside Max -> SMOKE_OK + property-miss report
tests/mock_pymxs.py   fake pymxs runtime — exercises builder wiring off-Max
tests/                75 pytest checks (py -3.12 -m pytest tests)
```

## What is proven WITHOUT 3ds Max
`tests/test_builder_logic.py` drives `builder.py` through a mock `pymxs`
runtime, so the class-correct wiring contract is verified deterministically:
foliage becomes a VRay2SidedMtl that never refracts + clip opacity; glass gets
thin-walled refraction with near-white clamped fog; metals get metalness +
anisotropy; data maps load linear while albedo does not; the material lands on
the active editor slot; displacement is added only where the recipe calls for
it; and a missing V-Ray property logs a MISS instead of crashing. The one thing
this cannot verify is whether the real V-Ray 7 property *names* match — that is
exactly what `MAX_SMOKE.py` checks live.

Two map backends, same manifest contract (swap freely, Max side unchanged):
- `forge_cli.py` — deterministic heuristic (Materialize-class), no key, offline.
- `forge_fal.py` — **fal PATINA** AI backend (studio-grade de-lit maps +
  per-pixel metalness, up to 4K). Set `FAL_KEY`, then:
  `py -3.12 forge_fal.py ref.jpg --name Oak --type wood_interior --upscale 2`.
  The builder auto-wires the metalness map (`texmap_metalness`) when present.

## Verify
- Core + wiring logic: `py -3.12 -m pytest tests -q` → 75 passed
- **Live V-Ray (no GUI):** `3dsmaxbatch.exe -log smoke_batch.log smoke_wrapper.ms`
  runs `HEADLESS_SMOKE.py` → writes `smoke_result.txt`. Builds all 35 classes
  against real V-Ray, reports any property-name misses. **Confirmed `SMOKE_OK`,
  0 misses on 3ds Max 2026 + V-Ray 7.30** (2026-07-22). Kill any interactive
  Max first so the batch can check out the license.
- In Max: run `MAX_SMOKE.py` → expect `SMOKE_OK` (or `SMOKE_OK_WITH_MISSES`
  listing V-Ray property names to add to the candidate lists)
