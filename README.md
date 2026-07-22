# MatForge v1 — reference image → render-ready V-Ray material

One click: reference image + name + material type + resolution (2K/4K/8K)
→ PBR maps derived, physically-correct VRayMtl wired, dropped on a
Material Editor sphere, optionally assigned to selection.

## Install (once)
1. Open Max 2026 (V-Ray 7 installed).
2. Scripting > Run Script... > **`install_matforge.ms`**.
   This registers a persistent **MatForge** menu (and toolbar actions under
   Customize > Toolbars, category "MatForge"). No more "Run Script" each time.

## Use
- **MatForge > MatForge** — the dark web **panel** (the premium UI): pick a
  reference, name it, choose material type, resolution, and **Engine**:
  - **Fast** — deterministic heuristic maps, offline, no key.
  - **Ultra** — fal **PATINA** AI maps (studio-grade de-lit, up to 4K, real
    metalness). Needs `FAL_KEY` set. → **Create Material → Sphere**.
- **MatForge > MatForge (simple)** — a plain MAXScript rollout with the same
  controls, as a guaranteed-render fallback if the web panel doesn't display
  on your box (it uses Max's embedded browser).

Either UI generates the whole slate of maps and drops the wired VRayMtl onto a
Material Editor sphere; tick "Assign to selected objects" to also apply it (and
add a VRayDisplacementMod where the recipe calls for displacement).

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
tests/                52 pytest checks (py -3.12 -m pytest tests)
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
- Core + wiring logic: `py -3.12 -m pytest tests -q` → 52 passed
- **Live V-Ray (no GUI):** `3dsmaxbatch.exe -log smoke_batch.log smoke_wrapper.ms`
  runs `HEADLESS_SMOKE.py` → writes `smoke_result.txt`. Builds all 13 classes
  against real V-Ray, reports any property-name misses. **Confirmed `SMOKE_OK`,
  0 misses on 3ds Max 2026 + V-Ray 7.30** (2026-07-22). Kill any interactive
  Max first so the batch can check out the license.
- In Max: run `MAX_SMOKE.py` → expect `SMOKE_OK` (or `SMOKE_OK_WITH_MISSES`
  listing V-Ray property names to add to the candidate lists)
