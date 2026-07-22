# MatForge Material-Creation Research & Finalized Roadmap

**Created**: 2026-07-21 · **Method**: 6-dimension parallel research workflow
(web + Chaos docs) → synthesis → adversarial TD critique → reconciliation.
**Purpose**: establish what matters in V-Ray 7 → Chaos Vantage archviz material
creation and lock the 002+ roadmap.

---

## 0. Executive summary

Material realism decomposes into **six dimensions**. Ranked by leverage for
*this* pipeline (archviz, deterministic-first, Vantage-terminal):

1. **Base-shader correctness** — metalness/dielectric fork, per-channel color
   space, IOR/Fresnel, roughness-mode, bump/normal/displacement choice. *Mostly
   done in v1; a few silent-correctness gaps remain.*
2. **Output accuracy** — de-lighting the reference before it becomes albedo,
   and physical-plausibility guardrails on derived values. *The base color
   everything else is wired around — must be right early.*
3. **Real-world scale, texel density & tiling** — wrong physical scale and
   visible repetition are the two fastest "this is CG" tells. *Highest-impact
   deterministic gap v1 left.*
4. **Vantage parity by construction** — every dangerous divergence is silent; a
   clean V-Ray render is **not** proof. This is the moat and must be enforced.
5. **Photoreal "last-15%" layers** — edges, dirt, wear, per-element variation,
   built on a VRayBlendMtl layering foundation. *Almost all deterministic.*
6. **Advanced material families & workflow** — velvet/glaze/emissive/wet/water,
   plus lookdev validation and library reuse.

**Reconciliation headline (from the critique):** the first synthesis
over-indexed on scale/tiling/wear and under-indexed on *base-shader correctness
and output accuracy*. De-lighting, plausibility guardrails, and color-swatch
working-space were deferred too late; the lookdev parity gate — the only thing
that *proves* the moat — was wrongly in backlog. The roadmap below fixes that.

---

## 1. What v1 already gets right (validated against the code)

These were flagged as gaps but are **already wired** in `builder.py` /
`recipes.py` — the foundation is sound:

| Factor | Status in v1 |
|---|---|
| Roughness-mode (`brdf_useRoughness`=ON, no invert) | ✅ wired |
| Metalness workflow (Reflection=white, tint in Diffuse, binary metalness=1) | ✅ correct |
| Anisotropy for brushed metal | ✅ recipe + wired (rotation map still TODO) |
| Fresnel + per-class IOR from table | ✅ wired, locked reflection↔refraction IOR |
| Data maps linear / albedo sRGB | ✅ (post-review fix) |
| AO exported but **not** baked into albedo (no GI double-darken) | ✅ correct |
| Deterministic luminance-only de-light with clamped gain | ✅ (partial — see §2) |
| Foliage 2-sided + clip opacity, never refraction | ✅ enforced by test |
| Glass thin-walled + near-white clamped fog | ✅ enforced by test |
| Seamless tiling incl. normal map | ✅ (post-review fix) |

---

## 2. The six dimensions (key factors, impact, who owns it)

Impact = archviz importance. Owner = **det**erministic-code · **ai**-pixels ·
**ret**rieval-from-scans · **hyb**rid.

### D1 — PBR channel completeness & correctness
- **HIGH·det** Metalness vs dielectric fork — *biggest cause of CG metals*
  (grey-plastic chrome). Tint in Diffuse, Reflection white, metalness binary.
- **HIGH·det** Per-channel color space — data = Raw/linear, color = sRGB. The
  most frequent *silent* correctness bug.
- **HIGH·det** IOR/Fresnel per class (V-Ray default 1.6 is too high for most
  dielectrics).
- **HIGH·det** Roughness vs glossiness + `Use Roughness` toggle (inverse
  conventions).
- **HIGH·hyb** Bump vs Normal vs Displacement + **normal-map slot TYPE** and
  **DirectX→OpenGL green flip** (a flipped green silently inverts all relief).
- **HIGH·ret** Height/displacement **16-bit** + world-unit Amount (8-bit
  terraces on close-ups).
- **MED·det** AO (never pre-multiply into albedo over GI). Translucency/SSS,
  Sheen, Coat, Anisotropy+rotation, Opacity/cutout, Glass correctness,
  Self-illum.

### D2 — Photoreal "last-15%" realism layers (almost all deterministic)
- **HIGH·det** Rounded edges (VRayEdgesTex→bump) — *single most common CG tell*.
- **HIGH·det** Curvature edge wear (VRayCurvature); **HIGH·hyb** cavity dirt
  (VRayDirt); **HIGH·hyb** world-space directional weathering (dust/rain/gravity).
- **HIGH·det** Per-element variation (VRayMultiSubTex) + **UV randomization /
  stochastic tiling** (VRayUVWRandomizer).
- **HIGH·hyb** Micro-roughness/smudge breakup; **HIGH·det** VRayBlendMtl coat
  stack as the assembly primitive.

### D3 — Real-world scale, texel density, tiling
- **HIGH·det** Real-world scale mapping (physical footprint) — v1 binds no
  physical size at all.
- **HIGH·det** Texel-density (px/m budget) — makes the 2K/4K/8K slider *mean*
  something.
- **HIGH·hyb** Mapping/projection choice; **HIGH·hyb** VRayTriplanarTex for
  un-UV'd CAD/proxy/terrain.
- **HIGH·det** Tiling repetition = #1 CG tell → stochastic/UVWRandomizer.
- **MED·det** Scale-couple bump/displacement amounts to the same physical size.

### D4 — Advanced material types & layering
- **HIGH·hyb** VRayBlendMtl foundation; wet/puddles; **HIGH·hyb** velvet
  (Sheen), water/liquids (IOR 1.33), glazed ceramic (coat), SSS solids
  (onyx/wax/alabaster via VRayMtl translucency — **not** VRaySkinMtl);
  emissive fixtures; cutout/perforated; decals.
- **MED·ret** Spectral metals (measured n,k → F0 tint); car paint
  (VRayCarPaintMtl2).

### D5 — Color management + Vantage parity + performance
- **HIGH·det** Per-slot color-space tags; **HIGH·hyb** **ACEScg/OCIO scene
  working-space** match + swatch conversion + Vantage OCIO config parity.
- **HIGH·det** VRayBitmap/VRayHDRI (never native Bitmaptexture — intent doesn't
  reach GPU/Vantage).
- **HIGH·ret** Vantage feature-support matrix — silent no-ops: procedural
  opacity→solid, refraction<0.1→opaque, glossy refraction→mirror, >10 blend
  layers dropped, >16K clamped, UVWRandomizer **not applied to bump**,
  `Auto` color space re-interpreted, absolute paths broken.
- **HIGH·det** Tiled/mip `.tx` streaming; resolution discipline (16K cap);
  displacement **2D-vs-3D mode** (2D re-tessellates poorly in Vantage);
  VRayProxy↔material binding.

### D6 — Workflow: libraries, lookdev, generation-vs-retrieval
- **HIGH·det** Deterministic naming/taxonomy + node stamp (the handle Vantage &
  VRayProxy read after export).
- **HIGH·det** **Physical-plausibility guardrails** (albedo luminance ~30–240
  sRGB, roughness never exactly 0/1, diffuse+reflection ≤ 1 energy).
- **HIGH·hyb** **De-lighting** (highlight/shadow suppression) — *the* reason
  generated albedo looks flat/double-lit.
- **HIGH·det** Calibrated lookdev scene (grey/chrome/ColorChecker/neutral HDRI)
  + turntable/grazing/tiled-swatch — the render-based **Vantage-parity proof**.
- **HIGH·ret** Library reality: **Cosmos/Megascans/Poliigon have no license-clean
  API**; **Poly Haven CC0 is the only programmatic measured source.**
- **HIGH·det** Library format that survives Vantage (.vrmat vs maps+recipe);
  dedup/relink.

---

## 3. Finalized roadmap (reconciled with the critique)

Sequencing rule: **base-shader correctness + output accuracy → scale/parity →
deterministic families → realism layers → AI backend**, with the render-based
lookdev gate pulled forward because it *proves* the moat.

### v1-gap — Correctness & Vantage-safety hardening (all deterministic, small)
- Normal via VRayNormalMap with **DirectX↔OpenGL green-flip toggle** + confirm
  Raw tag (critical once external/AI normals arrive at v4; cheap now).
- **16-bit** height/displacement output (kill terracing).
- **Physical-plausibility clamps** in derivation: albedo luminance ~30–240 sRGB,
  roughness ∈ [~0.04, 0.98] (never 0/1), diffuse+reflection energy ≤ 1, metals
  forced metalness=1 + non-elevated diffuse.
- **Relative texture paths** + **explicit per-slot color space** (never `Auto`).
- **Color-swatch working-space**: detect ACEScg/OCIO scene and convert VRayColor
  swatches (diffuse/fog/sheen/translucency) so tints don't hue-shift.
- Confirm every slot loads via **VRayBitmap** (never native Bitmap).
- **Canonical naming** `CLASS_substrate_finish_res_ver` + stamp
  class/IOR/source-image-hash on the node.
- `.tx` tiled/mip conversion pass; downtier height one step below albedo;
  hard-cap 16K.

### v2 — Scale truth, repeat-breaking & Vantage parity (100% deterministic)
- **Real-world scale**: `real_world_mm` per recipe → VRayBitmap real-world scale
  + UVWMap Real-World Map Size; reconcile res×tile into a **px/m budget**
  (single-material scope — no cross-scene assumption).
- **VRayUVWRandomizer** stochastic tiling + constrained rotation/offset per
  class (pair with a baked breakup for the bump, which Vantage doesn't
  randomize).
- **VRayTriplanarTex** projection option for un-UV'd geometry (Size synced to
  real-world scale).
- **Deterministic de-light v2**: highlight/shadow-suppression + AO-split pass on
  the reference (the pre-AI upgrade to today's luminance de-light).
- **Vantage-safe pre-emit validator**: relative paths, explicit color space,
  refraction ≥ 0.1, ≤10 blend layers, ≤8 UV sets, ≤16K, procedural-opacity→bake,
  **displacement 2D-vs-3D decision** — emits a per-material parity report.

### v2.5 — Deterministic material families (no AI, no blend needed)
*(Pulled ahead of v3 per critique — these are single-lobe VRayMtl adds, HIGH
impact for luxury interiors, and don't need the blend foundation.)*
- Velvet/suede (Sheen), glazed ceramic/tile & sanitaryware (coat glaze), water &
  liquids (IOR 1.33 volume vs thin sheet), SSS solids (onyx/wax/alabaster),
  emissive fixtures (VRayLightMtl vs self-illum), cutout/perforated (clip
  opacity), anisotropy **rotation** map for brushed metal.

### v3 — Photoreal last-15% realism layers (deterministic masks; grunge gated)
- **VRayBlendMtl** layering foundation (base+coat+mask, Additive off, ≤10).
- VRayEdgesTex rounded edges **with a bake-or-accept-sharp Vantage fallback**
  (round-edge Vantage support is unconfirmed).
- VRayDirt cavity dirt (Vantage 2.7+), VRayCurvature edge wear, VRayMultiSubTex
  per-element variation (Vantage 1.4+), micro-roughness/smudge + micro-normal.
- **Wet-surface blend** (puddle mask derived from the height map — deps exist
  here, pulled from v4).
- Bake-to-bitmap fallback for Vantage-unsafe procedurals (world-space
  weathering, VRayDistanceTex, gradient/falloff). Grunge/leak bitmaps = the only
  AI/retrieval hook, gated behind the manifest.

### v3-gate — Lookdev calibrated-scene + turntable QA *(promoted from backlog)*
- Neutral lookdev scene (grey/chrome/ColorChecker/HDRI, locked view transform) +
  turntable/grazing/tiled-swatch pass, **Max-preview vs Vantage side-by-side** —
  the render-based parity proof the moat depends on.

### v4 — AI/measured backend + remaining families (gated behind the manifest)
- Swap map derivation for the pbr-texture-app/Substance-class engine behind
  `manifest.json` (real AI de-light, AI upscale) — user still names/classifies.
- **Poly Haven CC0 REST** measured-retrieval fallback (only license-clean source).
- Spectral metals (measured F0 table + complex-IOR toggle); car paint
  (VRayCarPaintMtl2); decals (validate Vantage round-trip first).

### backlog
- 004 multi-material segmentation of one photo (needs AI segmentation — gated).
- Library management (.vrmat export, pixel-hash dedup/relink, browser
  categories); explicit editor-slot picker + Slate view.

---

## 3b. Completeness audit — the engineering/product layer

A second adversarial workflow (5 hunt axes → verify) was run specifically to
find what the *material-science* research never framed. It hunted 50 candidates
and **confirmed 35 real gaps** — proving the science-only research was NOT
complete. The gaps clustered in plugin engineering, UX, and product, not
material physics.

**Fixed immediately in code (this pass) — genuine bugs / cheap correctness:**
- **Scene-units conversion (was a bug-now).** `displacement_mm` was written raw
  into `VRayDisplacementMod.amount`, which is in the scene's *system* units — so
  a 3 mm paver displaced 3 *inches*/*cm*/*m* in any non-mm scene. Now converted
  via `rt.units.decodeValue`.
- **Undo transaction** wrapping the create+place+assign path (Ctrl-Z reverts as
  one step — matches lightmatch-max).
- **Idempotent displacement** — re-assign replaces the MatForge modifier instead
  of stacking (was silently doubling displacement).
- **Manifest validation** — schema version, known-class check, and **map-path
  existence** (prevents silent black/pink swatches); `forge_max` success-path
  stdout parse no longer crashes on stray output.
- **Foliage opacity honesty** — palette/`PA` alpha now read; an opaque RGB leaf
  photo **warns** ("needs a pre-cut alpha") instead of silently emitting a solid
  quad. Warnings + wiring MISSes now surface in the dialog, not just the listener.
- **Roughness decoupled from specular highlights** (measured on the de-lit
  albedo); **AO** now derives from the seamless height (consistent with normal);
  finite decompression-bomb cap; pinned `requirements.txt`. +8 tests → 52 green.

**Scheduled into the roadmap (real, but larger):**
- *v1-gap*: async generation with progress + cancel (8K freezes Max for
  minutes); install/packaging (macroscript/menu/toolbar — not "Run Script");
  **bring-your-own-maps on-ramp** (wire existing Megascans/Poliigon sets — near-
  zero code, opens the paying-studio market); iterate/re-edit with per-material
  overrides; capture spec + input-quality pre-flight gate; class-picker tooltips
  + "unsure → generic".
- *v2*: **batch mode** (a scene needs 30–60 materials, not one); optional
  auto white-balance (de-light preserves the capture light's color cast).
- *v2.5*: **taxonomy expansion** — chrome/mirror, glossy/matte plastic, rubber,
  carpet, corten, terracotta, glazed ceramic, water (everyday archviz materials
  with no class today; "generic" mis-serves them).
- *business*: commercialization layer (license/activation/pricing/channel) and
  CI — tracked as a parallel workstream, not blocking the material roadmap.

**Honest limitation surfaced:** the deterministic quality ceiling is set by the
input photo. De-light removes low-frequency luminance only — it cannot fix blown
highlights, hard cast shadows, keystone perspective, or color cast. Hence the
capture spec + input gate (v1-gap) and auto white-balance (v2).

## 4. Moat (softened per critique)

> MatForge turns a **user-named, user-classified** reference image into a
> **deterministically-wired, physically-correct V-Ray 7 material that is
> conservative-by-construction for the Chaos Vantage handoff — and
> render-verified at the lookdev gate.** The artist classifies; code (not AI)
> wires; every node is chosen to survive Vantage. Substance classifies *for* you
> and has no V-Ray/Vantage awareness; Poliigon/Quixel are measured tiles you
> still hand-wire with no license-clean API. None deliver Vantage-safe,
> deterministic, per-class wiring from one reference.

"Provably safe" is only claimed **once the v3-gate render comparison exists**;
until then the guarantee is "conservative by construction" (static validator).

---

## 5. Explicitly out of scope
- **AI material classification** — Constitution VI; the class is the contract.
- **VRaySkinMtl** — no native Vantage skin node; route flesh through Vantage-safe
  VRayMtl SSS. People are entourage/proxies in archviz (low ROI).
- **Runtime pull/redistribution of Cosmos/Megascans/Poliigon** — no license-clean
  API; only Poly Haven CC0 qualifies (v4).
- **Live Vantage-unsafe procedurals** (VRayDistanceTex, world-space
  gradient/falloff/noise, procedural opacity) — permitted only as bake inputs.

---

## 6. Primary sources
Chaos: `blog.chaos.com/understanding-metalness`, `documentation.chaos.com`
(VRayMtl/VMAX, Color Management, Vantage support), `support.chaos.com`
(Substance→V-Ray PBR workflow), `forums.chaos.com` (VRayBitmap color space).
Poly Haven API (CC0). Substance/Quixel/Poliigon licensing pages. VFX lookdev
references (grey/chrome/ColorChecker calibration).
