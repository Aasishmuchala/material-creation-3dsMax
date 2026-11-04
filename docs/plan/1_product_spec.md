# Hyper-realistic Material Plugin for 3ds Max — V-Ray & Corona
### Final plan (v5) — material creation

**Scope.** The product is **material creation, not rendering**: perfect maps (colour, roughness, metalness, normal, height, opacity, transmission, translucency) and correctly set material parameters. The user renders with their own V-Ray or Corona; we never ship a renderer, render farm or render-comparison feature. We use renders **internally only**, once per renderer release, to confirm our parameter mapping (a roughness value means nothing until a highlight shows it).

A 3ds Max plugin that creates hyper-realistic materials — colour, texture, roughness, metalness, normal/height, transparency, translucency/SSS — and builds them as **native V-Ray (`VRayMtl`) and Corona (`CoronaPhysicalMtl`) materials** from one measured source.

**Confidence tags.** [Certain] = verified in the v3 audit or standard physics. [Likely] = strong inference or known behaviour **not yet re-verified** for 3ds Max/V-Ray/Corona. [Guessing] = estimate, to be calibrated. The capture physics, map rules, validator and statistics carry over from the audited Plan v3 (35/36 findings confirmed). Max/V-Ray/Corona specifics were web-checked on 4 Nov 2026 (see §12, *Verification record*); items confirmed there are tagged [Certain], the rest stay [Likely] until Phase 0 checks them in the current Chaos docs.

---

## 0. The uncomfortable part first

1. **You are entering Chaos's home turf.** Chaos makes both V-Ray and Corona, and ships **Chaos Scans** inside both through Chaos Cosmos — 3,100+ scanned materials, added to Corona 12 Update 2 (Apr 2025) and V-Ray 7 Update 1 (May 2025), included in Premium/Enterprise tiers. Chaos also partners with material producers, so "manufacturer catalogue" scans are partly their territory. A generic "realistic material library" loses to the renderer vendor's own free-with-subscription library. [Certain]
2. **Where you can win:** (a) materials from *the customer's own* physical samples (flooring, stone, fabric, a client's exact finish) captured in-house the same day — no public evidence of a Chaos service that scans customer samples [Likely]; (b) **one source → identical-looking V-Ray and Corona materials** — studios mix both; (c) **a validator that audits and fixes every material already in a scene** — no vendor sells that, and archviz scenes are full of broken downloaded materials. [Likely]
3. **(c) is your fastest revenue.** A scene-wide "material QA + auto-fix" tool needs no camera rig and no AI, and it is useful from day one. Build it first. [Likely]

## 1. Product, in three modules (shipped in this order)

| Module | What it does | Why this order |
|---|---|---|
| **A. Material Inspector** (MVP) | Scans every VRayMtl / CoronaPhysicalMtl / legacy material and bitmap in the scene; flags physically wrong values (albedo too dark or bright, fake metals, glossiness 1.0 everywhere, wrong bitmap gamma on roughness/normal maps, DirectX/OpenGL normal flips, missing refraction fog on glass, unmeasured IOR); one-click fixes; a per-material report. | Needs no capture hardware or ML. Sells to every archviz studio. Builds the validator that modules B and C depend on. |
| **B. Material Builder + Capture** | Creates materials from (1) a measured preset library (metals, glass, stone, skin, fabrics…), (2) a calibrated tripod phone/camera capture of a real sample, (3) imported PBR sets (Substance, Megascans, Poliigon, ambientCG); emits native VRayMtl *and* CoronaPhysicalMtl with matched appearance. | The core "hyper-realistic" promise; calibrated capture is the differentiator vs Chaos Scans. |
| **C. AI Generator** | Text/photo → full PBR stack → validated → native V-Ray/Corona material. | Last: hardest to make physically correct; must pass module A's validator before it ships. |

## 2. Architecture for 3ds Max

```
3ds Max (Windows)                                   matcore engine (separate process)
┌────────────────────────────────────┐   IPC      ┌─────────────────────────────────────┐
│ Max plugin  (Python 3 via pymxs +  │ files+JSON │ capture/   RAW ingest, polarisation, │
│ PySide6 UI; small C++ only if a    │◀─────────▶│            photometric stereo, solve │
│ hot path needs it)                 │  localhost │ validate/  rules, metrics, score     │
│  • Inspector: scene scan + fixes   │            │ reference/ n,k · IOR · σa/σs′ tables │
│  • Builder: VRayMtl / Corona-      │            │ procedural/ tiled map generation     │
│    PhysicalMtl node construction   │            │ ml/        PyTorch generation        │
│  • Bitmap setup (colour space)     │            │ render/    reference renders (V-Ray  │
│  • Job polling, previews           │            │            Standalone, Mitsuba 3)    │
└────────────────────────────────────┘            └─────────────────────────────────────┘
```

- **Plugin language:** Python 3 (3ds Max 2026 bundles Python 3.11.9 [Certain]) + `pymxs` (MaxPlus is removed since 2022 [Certain]) + PySide6 with Autodesk's `qtmax` helpers for UI [Likely on the exact PySide6 version] for UI and material construction; it creates and edits native materials through MAXScript-exposed properties. C++ SDK (`.dlu`/`.dlm`) only if profiling demands it, because C++ plugins are tied to each Max release's SDK and must be rebuilt per year. [Likely]
- **Engine stays a separate process** — not for licensing this time (Max plugins can be closed-source and sold commercially) but because a 2+ GB PyTorch install in Max's bundled Python is fragile, Max's UI runs on one thread, and V-Ray GPU / Corona compete for the same VRAM. [Likely]
- **Licensing is simpler than in Blender.** No GPL constraint. Your own licence key / seat server is allowed. [Likely]
- **Native output only — non-negotiable.** Every generated material uses only stock V-Ray / Corona / Max nodes (VRayBitmap / CoronaBitmap, VRayUVWRandomizer — has *Stochastic Tiling* [Certain] / CoronaUvwRandomizer (Corona 6+) [Likely], VRayNormalMap / CoronaNormal, VRayTriplanarTex / CoronaTriplanar). Scenes must render on a render farm or a client machine **without your plugin installed**. Custom texmaps would break that. [Certain as a design rule]
- **Supported matrix (start):** 3ds Max 2025–2027 · V-Ray 7 · Corona 13–14 · Windows 10/11 x64 [Likely — Corona 14 is current per third-party tooling; confirm in Phase 0]. 3ds Max 2026 ships OpenColorIO 2.4.1 and fixed OCIO network-rendering issues, so **OCIO colour management is the baseline**; support legacy gamma mode only as a detected-and-warned state [Certain on 2026].
- **Distribution:** Autodesk App Store and/or your own store, packaged as an Autodesk application package: `PackageContents.xml` at the package root (`AutodeskProduct="3ds Max"`, `ProductType="Application"`), installed under `%ALLUSERSPROFILE%\Autodesk\ApplicationPlugins\<name>`; test with `ADSK_APPLICATION_PLUGINS` [Certain].

## 2b. How each map is made perfect — the core of the product

Every map comes from **one measured or generated structure signal**, so a scratch changes colour, roughness and height together. All data maps are 16-bit linear, tileable, at **2048 px per metre** (4096 for close-ups) with physical scale stored. [Certain]

| Map | How we make it perfect | Typical ranges we enforce | Common mistake we prevent |
|---|---|---|---|
| **Base colour (albedo)** | Cross-polarised RAW capture removes highlights; ColorChecker calibration gives true colour (camera error mean ΔE2000 ≤ 2.0); flat-field removes light fall-off; no shadows or AO baked in; natural low-frequency hue variation kept, not flattened | Dielectric luminance 30/50–240 sRGB; snow and white references whitelisted [Certain] | Photos with baked-in shadows, highlights, auto white balance |
| **Roughness** | Base value fitted from a co-located flash frame per material; spatial detail from wear/curvature/fingerprint layers tied to the height map; histogram non-uniform | Indicative: glazed ceramic 0.02–0.1 · polished stone 0.05–0.2 · honed stone 0.3–0.5 · brushed metal 0.25–0.45 (anisotropic) · satin paint 0.4–0.6 · matte paint 0.6–0.85 · concrete 0.7–0.95 · fabric 0.7–1.0 [Guessing — calibrated per class in Phase 0] | Flat single-value roughness; gloss map used as roughness (inverted); map loaded as sRGB |
| **Metalness** | Bimodal: pure 0 or 1, fractional only where rust, dust or worn paint sits on metal | ≥ 95 % of texels at 0 or 1 [Certain] | Grey "half-metal" everywhere |
| **Metal colour** | From measured complex IOR (n, k) of the real metal under D65 — gold, brass, copper, aluminium, steel, chrome, titanium… — not picked by eye | Per-metal measured F0 ± 0.05 linear [Certain] | Yellow paint called "gold" |
| **Normal** | Photometric stereo from 8 calibrated light positions (near-light model); OpenGL +Y, with DirectX output when the target needs it; verified against the height map | Convention test corr > 0.9 [Certain] | DirectX/OpenGL flip that inverts every bump |
| **Height / displacement** | Integrated from normals (Poisson solve), scaled in mm from a scale marker; macro shape added from extra photos when the sample isn't flat | Physical mm, never arbitrary 0–1 [Certain] | Displacement scaled by eye; bumps at the wrong size |
| **Opacity** | Cutout only (leaves, mesh, lace, perforated metal) | Binary edges with 1–2 px anti-aliasing | Opacity used to fake glass |
| **Transmission / glass** | Measured IOR by glass family plus a measured absorption colour at a stated thickness | Window glass 1.52 with green tint; low-iron 1.52 nearly clear; borosilicate 1.47; crystal ≥ 1.545; water 1.333 [Certain] | Perfectly clear, colourless glass |
| **Translucency / SSS** | Measured scattering coefficients (Jensen 2001: skin, marble, milk…) converted to each renderer's inputs; thickness baked per object | No value without a measured source [Certain] | Waxy plastic look from guessed SSS radius |
| **Anisotropy, coat, sheen** | From measured presets, or extra capture passes (rotated light for anisotropy, grazing light for sheen) | Badged "preset" when not captured | Eyeballed clearcoat on everything |
| **AO / cavity** | Separate map, never multiplied into colour | — | Dark grime baked into albedo |

**Map-level quality checks (no rendering needed)** — run on every created material [Certain]:
colour ΔE2000 vs the calibrated photo; luminance and metal ranges; roughness spread and its link to height detail; normal-vs-height consistency; seamless tiling (wrap-seam test) and repetition check; correct colour space per map; physical scale present.

## 3. One source, two renderers — the core technical problem

A single canonical material (OpenPBR-style parameters + measured maps) is **translated** into each renderer. The renderers do not use identical parameters, so the translation is **calibrated by rendering**, not assumed.

| Canonical channel | V-Ray (`VRayMtl`) | Corona (`CoronaPhysicalMtl`) | Notes |
|---|---|---|---|
| Base colour (linear) | Diffuse | Base color | Bitmaps sRGB; one luminance check: 30 / 50 – 240 sRGB [Certain] |
| Roughness | BRDF **GGX** with **Use roughness** on (reflection becomes *Reflection roughness*) [Certain]; **refraction stays glossiness** even then — set Refraction glossiness = 1 − r explicitly [Likely] | Base roughness | Exact α mapping per renderer **fitted from renders** (§4) [Likely] |
| Metalness | Metalness | Metalness (Metal mode) | Bimodal ≥ 95 % at 0 / 1; fractional only in rust/dirt layers [Certain] |
| Metal F0 / edge tint | Metalness 1 with base (diffuse) colour = metal colour [Likely]; edge behaviour fitted in §4 | Base color = F0 + **Edge Color**, or **Complex IOR** (n, k) for physically exact metals (Corona 7+) [Certain] — prefer Complex IOR from the §5.1 n,k table | F0 from measured n,k under D65; never "≥ 180 sRGB per channel" [Certain physics / Likely params] |
| IOR (dielectric) | Fresnel IOR | IOR | Default 1.5; tiers: 1.30–1.80 silent, outside warns, outside 1–3 error [Certain] |
| Normal | VRayNormalMap (OpenGL / DirectX flip set explicitly) | CoronaNormal (flip G set explicitly) | Bitmap gamma **1.0 / linear**; convention test vs height [Certain] |
| Height | VRayDisplacementMod / Max Displace, mm → scene units | Corona displacement in material, mm → scene units | Physical scale from capture marker |
| Transparency / glass | Refract white, Refraction IOR, **Fog colour + multiplier** (absorption), Abbe for dispersion | Refraction amount, IOR, **Volumetric absorption** (colour + distance), dispersion; Thin mode for windows | Glass always with a measured absorption colour (clear soda-lime is green at depth) [Certain physics] |
| Translucency / SSS | VRayMtl Translucency modes incl. **Volume** (fog colour) and **SSS** (scatter radius, depth/scale) [Likely] | **SSS mode** (amount, radius, scatter colour) or **Volumetric mode** (absorption + scattering) [Likely, from Chaos's feature page — verify Physical Mtl naming] | Store measured σa / σs′; convert per renderer and verify with a slab render vs Mitsuba 3 [Certain physics / Likely params] |
| Thin translucency (leaves, curtains, lampshades) | Translucency (two-sided) / VRay2SidedMtl | Translucency, or **Thin shell** for hollow surfaces with no interior volume [Likely] | Thickness baked per object, never generated |
| Coat | Coat layer | Clearcoat layer | Only from measured preset or a capture with the extra pass |
| Sheen (fabric, velvet) | Sheen | Sheen | Preset or grazing-angle capture |
| Thin film | Thin film (if present in version) | Thin film (if present) | Only where measured |
| Tiling without repetition | VRayUVWRandomizer, Stochastic Tiling + small Tile Blend [Certain] | CoronaUvwRandomizer [Likely] | Native nodes only. **Never on patterned textures** (bricks, tiles, planks): randomising breaks the pattern — use the §5.4 procedural variation instead |
| Colour space | VRayBitmap colour-space setting / Max OCIO | CoronaBitmap gamma / Max OCIO | Colour maps sRGB, **all data maps linear** — the #1 bug in downloaded materials [Likely] |

**Parameter equivalence (internal, not a product feature).** We confirm once per V-Ray/Corona release that the same map set produces the same look in both, so the user gets matching materials without ever running a test themselves.

## 4. Parameter-mapping calibration (internal, once per renderer version — the user never sees this)

You **cannot** trust that "roughness 0.4" in V-Ray equals "roughness 0.4" in Corona, or that both match the physics. So fit it. [Likely that they differ; Certain that you must test]
1. **White-furnace test** in each renderer: uniform white environment, white dielectric and F0 = 1 metal at roughness 0 → 1. An energy-conserving BRDF vanishes against the background. Record any gain or loss.
2. **Roughness transfer curve:** render a sphere under a point light at roughness 0.05…0.9 in V-Ray and Corona; also in Mitsuba 3 with a reference GGX. Fit V-Ray's and Corona's roughness-to-α curves so all three highlights match. Store the curves per renderer version.
3. **SSS transfer:** render a 10 mm slab with a back light for each measured scattering material (skin, marble, wax, milk, jade) in all three; fit each renderer's radius/scale inputs to match Mitsuba's transmitted profile.
4. **Glass absorption:** 10 mm and 50 mm slabs; fit fog multiplier (V-Ray) and absorption distance (Corona) to the measured transmittance (Rubin 1985 values).
5. Re-run the whole suite automatically on every new V-Ray / Corona release (V-Ray: export `.vrscene` and render headless with **V-Ray Standalone**, which ships with V-Ray for 3ds Max [Certain]; Corona: render through `3dsmaxbatch.exe` with a MAXScript driver [Likely — confirm Corona's command-line options]). Chaos licences for CI are a budget line — ask about Chaos's developer / partner programme. [Likely]

## 5. Creating hyper-realistic materials — the four sources

### 5.1 Measured preset library [Certain physics]
- **Metals (~30):** n,k from refractiveindex.info (CC0), projected to F0 + edge tint under D65 — gold, silver, copper, brass, bronze, aluminium, chrome, iron, steel, titanium, nickel, zinc… Variants: polished, brushed (anisotropic), satin, oxidised.
- **Glass and liquids:** fused silica 1.458, borosilicate ≈1.47, window/soda-lime 1.52 with green absorption, low-iron, tinted bronze/grey/green (Rubin 1985), lead crystal ≥ 1.545, water 1.333, ice 1.31.
- **Dielectrics:** plastics, ceramics, lacquers, stone, concrete, plaster, wood finishes, with albedo inside 30/50–240 sRGB.
- **Scattering:** skin, marble, milk, wax, jade from Jensen 2001 and Narasimhan 2006 σa/σs′; no row without a measured source.
- **Fabrics:** sheen-based presets (velvet, satin, cotton, wool) — flagged "preset", not measured.

### 5.2 Calibrated capture of real samples (the differentiator) [Certain]
- **Rig:** camera or phone on a tripod looking straight down; flat sample; ColorChecker, scale marker, chrome ball, black sphere in frame; **one external polarised LED moved to 8 positions** (45° steps, 45–60° elevation); crossed + parallel frame per position; one extra frame from the phone's own flash (co-located) for roughness.
- **Bayer RAW only**, everything locked (exposure, ISO, focus, white balance). No JPEG, HEIC or Apple ProRAW.
- **Solve:** albedo D = 2·I_cross/m, specular S = (I_par − I_cross)/m (m from checker greys); calibrated near-light photometric stereo for normals; Poisson integration for height; **one GGX roughness per material** from the co-located flash, spatial variation as a tagged prior; tileable via patch synthesis + histogram blending.
- **Output:** albedo, roughness, metalness, normal, height (+ opacity) → canonical material → VRayMtl + CoronaPhysicalMtl via §3–4.
- **Not measurable with this rig:** coat, sheen, iridescence, true per-pixel roughness — these come from presets and are badged "preset".
- **Hardware alternative for studios:** support an off-the-shelf polarised light box / turntable later; the solver is the same.

### 5.3 Imported PBR sets (Substance, Megascans, Poliigon, ambientCG) [Likely]
- Auto-detect map types and conventions (DirectX vs OpenGL normals, gloss vs roughness, packed ORM), set correct colour spaces, fix out-of-range albedo, convert to both renderers.
- Run the Inspector on the result; show what was corrected.

### 5.4 Procedural & AI generation [Likely]
- **Procedural:** wear, dirt, scratches, fingerprints and edge damage driven by curvature/AO masks from **one structure signal**, so a scratch changes colour, roughness and height together. Exported as baked maps into native nodes.
- **AI (module C):** fine-tune Stable Diffusion 2.x / StableMaterials (Marigold recipe) on licence-clean data (MatSynth CC0 subset + your captures). Outputs base colour, normal, height, roughness, metallic. Seamless via circular padding + noise rolling; 2–4K via patched diffusion. Mandatory physics projection + validator. Roughness is always a prior.

## 6. The Inspector / validator rules (module A)

**Errors (block "approve")** [Certain unless tagged]
- Dielectric albedo luminance < 30 sRGB (strict < 50) or > 240 (unless whitelisted: snow, white references).
- Metal colour inconsistent with measured F0; metalness fractional outside a declared rust/dirt mask.
- **Data maps loaded as sRGB** (roughness, glossiness, metalness, normal, height, displacement). [Likely the most common real-world error]
- Normal map convention mismatch (test against height gradient), or loaded through a plain Bump slot.
- Glossiness map in a roughness slot (or vice versa), detected by histogram vs highlight behaviour.
- Glass with no absorption / fog colour; refraction IOR outside 1–3; "thin" mode on thick objects or vice versa.
- Spatially constant roughness on a textured material.
- Wrap seams in tiling maps (boundary z-score > 4σ).
- Displacement or texture scale not in physical units.

**Warnings**
- Roughness clipped at 0 / 1 over large areas; IOR outside 1.3–1.8; albedo 30–50 sRGB.
- Visible repetition (autocorrelation peak) — suggest the randomizer node.
- Legacy material types (Corona Legacy Mtl — superseded by CoronaPhysicalMtl since Corona 7 [Certain]; old VRayMtl Fresnel/glossiness setups) — offer conversion.
- Scene in legacy gamma mode instead of OCIO — warn and offer the switch.
- V-Ray vs Corona appearance mismatch > ΔE 2.0 for the same canonical material.

**Fixes:** one click per rule, all undoable, logged in a report the studio can attach to a delivery.

## 7. Proving "hyper-realistic" (map accuracy, then appearance)

- **Colour pipeline:** scene-linear Rec.709 D65 everywhere; RAW photos decoded linearly with a ColorChecker matrix; renders saved as EXR; one named display transform for viewing tests; Max OCIO configured and pinned. [Certain]
- **Colour accuracy:** camera chain mean ΔE2000 ≤ 2.0 over 24 patches; material ΔE2000 ≤ 2.0 vs spectrophotometer at ≥ 3 spots. [Certain]
- **Photo match** (captured materials only): registered re-render vs photo, LPIPS and SSIM with thresholds calibrated on same-sample photo pairs (placeholders 0.15 / 0.85). [Certain method / Guessing thresholds]
- **Map accuracy first:** albedo ΔE vs instrument, normal angular error and height error vs the capture, roughness vs the flash fit — all checked on the maps themselves.
- **Blind test:** "which is the photo?" 2AFC; pass when the one-sided 95 % Wilson lower bound on picking the render ≥ 0.40 over ≥ 150 trials per material class, archviz artists as a separate cohort. [Certain]
- **Every material ships a report:** source (measured / captured / preset / AI), calibration data, metric values, renderer versions, validator version.

## 8. Phases

| Phase | Weeks | Deliverable / exit criterion |
|---|---|---|
| **0 Verify & position** | 2 | Confirm every [Likely] Max/V-Ray/Corona parameter against current docs; supported version matrix fixed; Chaos partner/CI licences requested; 10 studio interviews; 20 real samples photographed RAW for calibration. |
| **1 Inspector MVP** (module A) | 8 | pymxs plugin scans VRayMtl / CoronaPhysicalMtl / bitmaps; all §6 rules + one-click fixes + report; tested on 50 real downloaded archviz scenes; false-positive rate < 5 %. **Sell it (beta) at week 10.** |
| **2 Parameter mapping** | 3 | Internal: roughness, metal, glass and SSS parameter tables fitted for V-Ray and Corona so one map set looks the same in both. |
| **3 Builder + preset library** | 6 | Canonical material → native VRayMtl + CoronaPhysicalMtl; ~150 measured presets; V-Ray vs Corona ΔE ≤ 2.0; import of Substance/Megascans/Poliigon sets. |
| **4 Capture pipeline** | 8 | Tripod RAW capture app (iOS/Android) + solver; ≥ 10 new samples pass colour, photo-match and 2AFC tests; demo beats Adobe Sampler and Chaos Scans-style workflow on turnaround for a customer's own sample. |
| **5 Translucency, glass, fabric** | 5 | Skin, marble, wax, leaves, curtains, glass families pass backlight and slab tests in both renderers. |
| **6 AI generation** (module C) | 10 | Generator passes validator rules **before** projection ≥ 60 %; seamless; 2–4K; licence-clean training manifest. |
| **7 Ship** | 4 | Autodesk App Store / own store, licence server, docs, version matrix CI, 15 artists through the blind test. |

**Total ≈ 46 weeks solo** [Guessing]. **Revenue can start around week 10** with module A. A 3-person team (Max/pymxs dev, imaging/capture dev, ML dev) parallelises phases 2–6 to ≈ 30 weeks. [Guessing]

**Kill / pivot gates**
- **Week 10:** fewer than 5 of 10 studios would pay for the Inspector → rethink before building capture.
- **End of Phase 4:** capture doesn't beat existing workflows on accuracy or turnaround → ship Inspector + Builder + presets only, and drop the capture differentiator.

## 9. Risks

| Risk | Mitigation |
|---|---|
| Chaos ships the same features (scene QA, own-sample capture) | Move fast on the Inspector; support **both** renderers plus import/export (Chaos is unlikely to optimise for competitors' libraries); keep the calibrated report as the trust asset. [Likely] |
| Renderer parameter changes between V-Ray / Corona versions | Calibration suite in CI; version-specific translation tables. |
| Max SDK / Python / Qt changes per release | Stay in pymxs + PySide6; avoid C++ unless necessary; test on 3 Max versions. [Likely] |
| Materials must work anywhere the user renders | Native nodes only; never custom texmaps. |
| GPU contention with the user's V-Ray GPU / Corona | Engine in a separate process with a VRAM budget; heavy jobs paused while the user renders. |
| Training-data licences | MatSynth CC0 subset + own captures; Poliigon only with its AI licence; Fab assets only if not tagged NoAI. [Certain] |
| Capture usability (polariser alignment is fiddly) | Guided live-view UI; later, support a commercial light box. |

## 10. Hard rules

1. Native V-Ray / Corona nodes only; materials render without the plugin.
2. Data maps (roughness, gloss, metal, normal, height) are always linear.
3. Never bake lighting or AO into base colour.
4. Never eyeball IOR, metal colour or SSS: every value has a measured source or a "preset / artistic" badge.
5. Never treat phone or AI roughness as measured.
6. Glass always carries a measured absorption colour.
7. Every material ships with its validation report and renderer versions.
8. V-Ray and Corona versions of one material must match within ΔE 2.0, or the mismatch is flagged.

## 11. If you only have 12 weeks

Build **Phase 0 + Phase 1 (Inspector MVP) + a small Builder with ~40 measured presets** (metals, glass, common dielectrics) for V-Ray and Corona. That is a sellable product for archviz studios. Capture and AI come after it has paying users. [Likely]

---
## 12. Verification record (web-checked 4 Nov 2026)

| Claim | Result | Source |
|---|---|---|
| 3ds Max 2026 Python | **3.11.9** (one Autodesk page still says 3.9 — outdated) | [What's New in 3ds Max 2026](https://help.autodesk.com/cloudhelp/2026/ENU/3DSMax-What-s-New/files/GUID-5E7810B6-59DF-434E-AB24-BC2A452C715C.htm), [MAXDEV Python: what's new](https://help.autodesk.com/cloudhelp/2026/ENU/MAXDEV-Python/files/MAXDEV_Python_what_s_new_in_3ds_max_python_api_html.html) |
| pymxs is the API; MaxPlus removed since 2022 | Confirmed | [Porting Explode Geometry to Python](https://blog.autodesk.io/porting-explode-geometry-to-python-life-after-maxplus/), [About Python in 3ds Max](https://help.autodesk.com/cloudhelp/2026/ENU/MAXDEV-Python/files/MAXDEV_Python_about_the_3ds_max_python_api_html.html) |
| OCIO in Max 2026 | OpenColorIO **2.4.1**, OCIO network-render fixes | [What's New in 3ds Max 2026](https://help.autodesk.com/cloudhelp/2026/ENU/3DSMax-What-s-New/files/GUID-5E7810B6-59DF-434E-AB24-BC2A452C715C.htm) |
| PySide6 version | Not confirmed from an Autodesk source (third-party says 6.5) | [3dsmax scripting skill page](https://skills.sh/TerminalSkills/skills/3dsmax-scripting) |
| Plugin packaging | PackageContents.xml at package root, ApplicationPlugins folder, ADSK_APPLICATION_PLUGINS for testing | [Packaging Plug-ins (2025)](https://help.autodesk.com/cloudhelp/2025/ENU/MAXDEV-Developer/files/writing_plug-ins/plugin_package/packaging_plugins.html), [PackageContents format (2026)](https://help.autodesk.com/cloudhelp/2026/ENU/MAXDEV-Developer/files/writing_plug-ins/plugin_package/packagexml_format.html) |
| VRayMtl "Use roughness" | Reflection switches to roughness; refraction glossiness does not | [VMAX docs: VRayMtl](https://initdc.github.io/VMAX_docs/VRayMtl.html), [TurboSquid V-Ray notes](https://resources.turbosquid.com/?p=20588) |
| VRayMtl translucency Volume / SSS modes | Listed by third parties; official V-Ray 7 page not retrieved | [D5 V-Ray support table](https://docs.d5render.com/workflow/3ds-max/vray-function-support-table), [Foundry Mari VRayMtl](https://learn.foundry.com/mari/Content/reference_guide/shader_parameters/vraymtl.html) |
| VRayUVWRandomizer stochastic tiling | Confirmed (Tile Blend; not for patterned textures) | [VMAX docs: VRayUVWRandomizer](https://initdc.github.io/VMAX_docs/VRayUVWRandomizer.html), [Novedge tip](https://novedge.com/blogs/design-news/v-ray-tip-v-ray-uv-randomization-and-stochastic-tiling-workflow) |
| Corona randomizer node name | **CoronaUvwRandomizer** (Corona 6) — v4 draft's "CoronaMappingRandomizer" was wrong | [State of Art Academy](https://www.stateofartacademy.com/3ds-max-2021-2-new-osl-maps/) |
| CoronaPhysicalMtl Edge Color + Complex IOR | Confirmed (Corona 7) | [Corona 7 release](https://www.chaos.com/blog/corona-renderer-7-for-3ds-max-released), [Behind the scenes: the Physical Material](https://www.chaos.com/blog/behind-the-scenes-the-physical-material) |
| Corona SSS / volumetric parameters, Thin shell | SSS mode (amount, radius, scatter colour), Volumetric mode (absorption, scattering); Thin shell from an unofficial summary | [Corona materials features](https://corona-renderer.com/features/materials), [Evermotion: Volumetrics and SSS in Corona](https://evermotion.org/tutorials/show/11941/volumetrics-and-sss-in-corona-renderer-for-3ds-max) |
| V-Ray Standalone ships with V-Ray for Max | Confirmed | [V-Ray for 3ds Max application package](https://initdc.github.io/VMAX_docs/V-Ray_for_3ds_Max_Autodesk_application_package.html) |
| Chaos Scans in Cosmos | 3,100+ scans; Corona 12.2 (Apr 2025), V-Ray 7.1 (May 2025); Premium/Enterprise | [Corona 12 Update 2](https://www.chaos.com/blog/corona-12-update-2), [CG Channel: V-Ray 7.1 Scans](https://www.cgchannel.com/2025/05/chaos-adds-chaos-scans-to-cosmos-for-v-ray-7-update-1/), [Chaos Scans](https://www.chaos.com/jp/scans) |
| Chaos service to scan customers' own samples | **No public evidence found** — the gap the capture module targets | (absence across the sources above) |

**Still open for Phase 0 week 1:** official Chaos pages for VRayMtl V-Ray 7 and CoronaPhysicalMtl (SSS, thin film, thin shell naming); Corona command-line batch rendering; current Corona version number; PySide6 version in Max 2026/2027; whether Chaos offers developer/CI licences.

*Carry-over:* detailed physics, statistics and capture derivations are in `plan_v3.md` (audited). Everything specific to 3ds Max, V-Ray and Corona in this document is unaudited until Phase 0 verifies it.
