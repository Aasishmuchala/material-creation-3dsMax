# MatForge commercial competitor landscape (3ds Max + V-Ray/Corona), as of 2026-11-04

Scope note: ~28 tool calls, mostly search snippets plus ~10 page fetches. Many vendor pages were not fetchable. Anything not directly confirmed is labelled UNVERIFIED. Dates are attached to every claim.

## 1. Chaos's own offering (Cosmos, Scans, AI Material Generator, Enhancer, Converters)

### Takeaway
Chaos is the main threat. Its AI Material Generator (photo to PBR material, up to 4K) shipped in V-Ray 7.2 (Aug 2025, beta) and Corona 14 (Nov 2025), and was still described as improving in V-Ray 7.3 (Apr 2026) and Corona 15 (May 2026). It outputs only albedo, normal and roughness. It is cloud-based and bundled into subscriptions. I found no evidence of a scene-wide material audit/validator from Chaos, and no V-Ray 8 as of Nov 2026.

### Cited Findings
- V-Ray 7 Update 2 for 3ds Max (Aug 2025) introduced the AI Material Generator and AI Enhancer. The Material Generator takes a real-world reference photo uploaded to the Chaos Cloud library and produces a PBR material and texture maps. Options: resolution, tileable, de-light the image, normal and roughness intensity. Status: experimental beta via Chaos Cloud, included with all V-Ray subscriptions. No generation quotas and no post-beta pricing were stated; CG Channel says it asked Chaos and reported no answer. — [CG Channel, 7 Aug 2025](https://www.cgchannel.com/2025/08/chaos-adds-new-ai-tools-to-v-ray-in-v-ray-7-for-3ds-max-update-2/)
- AI Enhancer stays free, but some advanced features may require V-Ray Premium or a Collection plan (update dated 27 Aug 2025). — [CG Channel](https://www.cgchannel.com/2025/08/chaos-adds-new-ai-tools-to-v-ray-in-v-ray-7-for-3ds-max-update-2/)
- Digital Engineering reported planned advanced Enhancer controls and an "AI Material Recommender" for Cosmos search. This is a roadmap statement, not confirmed shipped. — [Digital Engineering 24/7](https://www.digitalengineering247.com/article/chaos-debuts-several-ai-tools)
- Corona 14 (released 12 Nov 2025, 3ds Max and Cinema 4D) added the AI Material Generator (in Chaos Cosmos, "available with Corona subscriptions"), AI Image Enhancer, AI Upscaler, Gaussian splats, Night Sky, procedural fabric material. The generator outputs albedo, normal and roughness. AI features can be disabled by organisations with AI-use policies. — [CG Channel, 17 Nov 2025](https://www.cgchannel.com/2025/11/chaos-releases-corona-14-for-3ds-max-and-cinema-4d/); [Chaos press](https://www.chaos.com/press/corona-14-faster-more-expressive-storytelling-with-ai); [Architosh](https://architosh.com/2025/11/chaos-launches-corona-14-with-ai-material-tools-and-gaussian-splat-support/)
- One third-party review claims max 2K resolution at launch, cloud-run. Reviewer claim, not independent testing. — [IllustrArch](https://illustrarch.com/articles/design-softwares/73964-chaos-ai-material-generator.html)
- V-Ray 7 Update 3 for 3ds Max (23 Apr 2026): AI Material Generator max resolution raised to 4K; AI Enhancer accuracy improved on large surfaces; 3ds Max 2021+ (docs list 2027 support); also Quick Sun Caustics, VRayParallaxTex. Rental only. Beta status not stated in that article. — [CG Channel, Apr 2026](https://www.cgchannel.com/2026/04/chaos-releases-v-ray-7-update-3-for-3ds-max/); [Digital Production](https://digitalproduction.com/2026/04/16/chaos-v-ray-7-update-3-goes-real-time/)
- Corona 15 (late May 2026, CG Channel article dated 27 May 2026; 3ds Max, Cinema 4D, headline says Blender): AI Material Generator up to 4K, improved AI Enhancer, Veras (generative AI ideation) bundled free, new Glints layer in CoronaPhysicalMtl, Light Override material. Pricing: Corona Solo (named user) $62.90/mo or $414/yr; Corona Premium (floating) $72.90/mo or $514.80/yr; 3ds Max 2016+. — [CG Channel, 27 May 2026](https://www.cgchannel.com/2026/05/chaos-releases-corona-15-for-3ds-max-and-blender/)
- No V-Ray 8 for 3ds Max found; latest is V-Ray 7.3 (Apr 2026). — search of [chaos.com whats-new](https://www.chaos.com/vray/whats-new) and CG Channel (negative result)
- Chaos Scans: Chaos page states "over 2,500" in one place and "3,000+" elsewhere (internal inconsistency). Described as "generated from thousands of real-world images", not described as BRDF-measured. Tiers and price not shown on the page. Cosmos integrates with V-Ray, Corona, Vantage, Envision, Enscape. — [chaos.com/scans](https://www.chaos.com/scans)
- Cosmos: July 2025 press release adds ~30,000 assets "at no extra cost", with asset access depending on suite/tier. A Chinese Chaos page lists 6,800+ real-time and 20,000+ high-quality assets, with 7,000+ and 10,000+ more "coming in 2026" (UNVERIFIED current totals). — [Chaos press](https://www.chaos.com/press/chaos-adds-30000-assets-to-chaos-cosmos-making-it-the-largest-smartest-curated-3d-asset-library-for-aec-professionals); [chaos.com/cn/cosmos](https://www.chaos.com/cn/cosmos)
- Chaos added Twinbru textile digital replicas to Cosmos (date not captured). — [MCAD Cafe](https://mcadcafe.com/nbc/articles/1/1912831/Chaos-Adds-Digital-Replicas-Twinbru-Textiles-Haworth-Furniture-Chaos-Cosmos-3D-Library)

### Inferences
- Chaos covers the "photo to material" half of MatForge for free inside the subscription, so MatForge cannot compete on that alone. Differentiators open to MatForge: more maps (metalness, height, AO, IOR/absorption, SSS), both engines with correct native parameters, offline/no-cloud, and the audit/fix half.
- Output limited to albedo/normal/roughness means metalness, glass absorption, IOR, etc. are not produced by the Chaos tool (from the stated output list; UNVERIFIED for V-Ray 7.3).

### Gaps
- Corona Converter and V-Ray Scene Converter: I found no official docs; searches returned only third-party converters. Scope, correctness, and whether either audits colour space is unknown.
- Chaos Scans tiers, price, and exact count (2,500 vs 3,000+ conflict). Not fetched: Chaos pricing pages.
- Whether the AI Material Generator is still labelled beta in Nov 2026, and any quota/credit limits.
- Official Chaos "AI Material Recommender" shipping status.

## 2. Third-party 3ds Max plugins and scripts (conversion, creation, QA)

### Takeaway
No dedicated "material linter/validator" for V-Ray/Corona turned up. The nearest are scene-fix/asset-relink utilities and converters. One AI material script (MatSnap AI) exists, Corona-focused, BYO Gemini key. This suggests the Material Inspector is a real white space, subject to a limited search.

### Cited Findings
- MatSnap AI (ArchCG Studio, Gumroad). 3ds Max script, announced 10 Apr 2026. One-time purchase (price not captured), BYO Google Cloud/Gemini API key, billed by provider. Analyses screen captures or imported images, generates diffuse, normal, roughness, displacement; builds Corona-compatible materials; seam correction; text-to-material; Fresnel setup; mapping randomisation. ScriptSpot lists 3ds Max 2023 to 2026; a reader asks for 2027. ScriptSpot also says it derives Normal, Bump, Roughness, Displacement and AO from the diffuse. Only Corona is stated as supported in the CGPress article. No validation function mentioned. — [CGPress](https://cgpress.org/archives/matsnap-ai-material-generator-for-3ds-max.html); [ScriptSpot](https://scriptspot.com/3ds-max/scripts/matsnap-ai) (via search snippet, fetch returned 429)
- Scene Fix (obaidaviz, Gumroad): paid MAXScript to fix crash/slow-render causes, supports Corona and V-Ray, includes an "Albedo Check" that renders an albedo pass for inspection (a render-based check, not a rules-based audit). Price not captured. — [Gumroad](https://obaidaviz.gumroad.com/l/qfMOo)
- HQ AssetsTracker (Gumroad): checks, collects and relinks maps, proxies and xrefs across renderers. Asset-path QA, not physical-correctness QA. — [Gumroad](https://hnq1994.gumroad.com/l/HQ_AssetsTracker)
- V-RayMax Converter PRO (3DZver, ScriptSpot): converts V-Ray/Corona/finalRender/Arnold/Brazil materials, lights, cameras, proxies etc.; targets include Standard, Physical, PBR, OpenPBR, glTF, Corona. 3ds Max 2018 to 2027, V-Ray 5 to 7; v4.0061/4.0062 (updated ~Feb 2026 per listing). Has "save state" undo; author advises not saving over the original scene. Users report gaps (e.g. VRayDisplacementMtl). Price not captured. — [ScriptSpot](https://www.scriptspot.com/3ds-max/scripts/v-raymax-converter-pro)
- JV's 3dsmax-scripts (GitHub): utilities for Corona Physical/Legacy, e.g. V-Ray roughness to gloss conversion, metalness switching. Free, individual scripts. — [GitHub](https://github.com/jmdvella/3dsmax-scripts)
- Superellipse PBR Importer: loads PBR packs as wired CoronaPhysicalMtl; requires Max 2025+ and Corona 15+; Windows only. Importer, not AI. — [Superellipse](https://superellipse.co/blogs/software-guides/3ds-max-corona-pbr-importer-2-click-material-setup)
- A23D plugin v2.0.1 (March 2026) auto-wires its PBR textures to V-Ray, Corona and Arnold materials; asset import, not generation. — [A23D](https://www.a23d.co/integrations/3ds-max)

### Inferences
- Competitor set is fragmented single-purpose tools. A combined generator + inspector is a different product shape from all found.

### Gaps
- Siger Studio converters, Kstudio Scene Converter / Project Manager, 3dground, Pro-Optimizer, Relink Bitmaps, Bitmap Tools: searches returned nothing; not verified to exist in current form, so their price, version and features are UNVERIFIED.
- Prices for MatSnap AI, Scene Fix, V-RayMax Converter PRO.
- No Evermotion, CGArchitect, Autodesk App Store listing review was possible. Absence of a validator is not proven.
- 2025-26 AI material plugins beyond MatSnap: none found in limited search.

## 3. Image-to-material tools artists pair with Max

### Takeaway
Adobe Sampler remains the incumbent standalone, but its 2026 release adds no V-Ray/Corona export. Open or cheap AI models (CHORD, PATINA) produce full 5-map sets but need glue code; CHORD is research-only licensed.

### Cited Findings
- Adobe Substance 3D Sampler 6.0 (article 30 Jun 2026; 6.0.2 dated 25 Jun 2026 per same article, unexplained): OpenPBR default material preset, material templates, dynamic Auto Tiling / Content Aware Fill / Height & Normal Blend, up to 8K render, USD/USDA/USDZ export, HP Z Captis auto scan. The article mentions no AI features and no V-Ray/Corona export. Sold only via Substance 3D Collection, US$59.99/mo individuals; teams US$119.99/mo per licence; education free (per article). — [Digital Production, 30 Jun 2026](https://digitalproduction.com/2026/06/30/adobe-sampler-6-0-adds-openpbr/); [Adobe pricing post, Feb 2025](https://blog.adobe.com/en/publish/2025/02/20/substance-3d-innovations-pricing-updates)
- Quixel Mixer discontinued; final free offline version 2023.1 released Feb 2026 (CG Channel, 20 Feb 2026), no future updates, bundled 800+ free assets. — [CG Channel](https://www.cgchannel.com/2026/02/quixel-mixer-has-been-discontinued-get-the-final-version-for-free/); [Digital Production](https://digitalproduction.com/2026/02/24/quixel-mixer-dead-final-offline-version-released/)
- Megascans moved to Fab (Oct 2024). Pricing per asset; sources conflict on what is free in 2026. A forum user calls 3-5 EUR per surface high. — [Unreal forum](https://forums.unrealengine.com/t/how-is-a-newcomer-supposed-to-build-environments-megascans-pricing-a-request-for-a-subscription/2844972); [CG Channel, Oct 2024](https://www.cgchannel.com/2024/10/epic-games-has-made-megascans-free-to-all-but-only-until-the-end-of-2024/)
- Ubisoft CHORD (La Forge): open-sourced with ComfyUI nodes; predicts base colour, normal, height, roughness, metalness from a single texture; works best at 1024 then upscaled; weights/code Research-Only licence (commercial use blocked). Release date not captured. — [Comfy blog](https://blog.comfy.org/p/ubisoft-open-sources-the-chord-model)
- fal PATINA (~April 2026, date from aggregators only): `fal-ai/patina` makes normal, roughness, basecolor, height, metalness maps from an image; `/patina/material` generates tiling PBR up to 8K from text or image, from ~$0.08 to $0.10 per material set; `/material/extract` pulls material from a scene photo. Trained on CC0 data (AmbientCG, Poly Haven) per aggregator. Also offered via Scenario. — [fal blog](https://blog.fal.ai/introducing-patina); [fal docs](https://fal.ai/models/fal-ai/patina/material)

### Inferences
- PATINA/CHORD show that 5-map generation is cheap commodity; MatForge value must come from engine-correct assembly and QA, not map generation.
- PATINA is an API a competitor (or MatForge itself) could wrap with Max glue code in days.

### Gaps
- Not researched: Materialize, ArmorLab, NVIDIA RTX Remix/PBRify, Meshy/Tripo/Polycam/Scenario texture modes, Leonardo/Krea. Their status in 2026 is UNVERIFIED.
- Whether any of these tools has a V-Ray/Corona export path.

## 4. Material libraries

### Takeaway
Libraries are plentiful; what they ship for V-Ray/Corona is mostly texture sets plus occasionally engine-specific materials. Quality varies and conventions (OpenGL vs DirectX, roughness vs gloss) are the user's problem.

### Cited Findings
- Poliigon: pricing in flux; its help centre says subscriptions now give assets per month instead of credits; third-party aggregators quote conflicting starting prices ($6, $7, $23/mo), all UNVERIFIED. Offers 100+ free items. Max/V-Ray/Corona add-on details not found. — [Poliigon help](https://help.poliigon.com/en/articles/8749917-new-asset-pricing); [toolradar](https://toolradar.com/tools/poliigon/pricing)
- Chaos Cosmos / Scans: see section 1.
- Lightbeans (vendor): maps are OpenGL format, Corona roughness mode default. — [Lightbeans](https://lightbeans.com/en/blog/tutorials/how-to-use-lightbeans-textures-in-corona)
- Many Gumroad/CGTrader packs sell per-engine material files (e.g. visualiarchviz, 3drush). Quality not assessed. — [3drush](https://3drush.com/materials/)

### Gaps
- ambientCG, Poly Haven (both CC0 per general knowledge, unverified here), Vizoo, TwinBru, Swatchbook: not searched. Vendor V-Ray/Corona support unknown.

## 5. Forum complaints (archviz users)

### Takeaway
Evidence found is thin; user complaints are dominated by convention mismatches, which are exactly what the Material Inspector targets. I did not retrieve any actual thread complaining about AI-generated materials.

### Cited Findings
- Normal maps: Max/DirectX vs OpenGL; fix is flipping green; Corona Normal Map node has Flip Green; plugging a normal map directly (not via Normal Map node) gives incorrect results. — [CGTrader forum](https://cgtrader.com/forum/technical-q-a/please-help-i-have-a-problem-with-exporting-textures-from-substance-painter-to-3ds-max-corona); [Corona forum, roughness thread](https://forum.corona-renderer.com/index.php/topic,11530.0.html)
- Roughness vs glossiness: a map labelled roughness may actually be an inverted gloss map; Corona defaults to roughness mode. — [Corona forum thread 11530](https://forum.corona-renderer.com/index.php/topic,11530.0.html)
- Converters: user comments on V-RayMax Converter PRO report unsupported material types (VRayDisplacementMtl). — [ScriptSpot](https://www.scriptspot.com/3ds-max/scripts/v-raymax-converter-pro)
- Chaos AI generator sentiment: positive first-person accounts only (Chaos-hosted blog); no independent critical thread found. — [Chaos blog](https://blog.chaos.com/corona-ai-archviz-workflow-efficiency)
- Cost complaints about Megascans-per-asset pricing (Unreal forum, link above).

### Gaps
- No Reddit r/3dsmax, r/archviz, CGArchitect, or forums.chaos.com thread was successfully retrieved about downloaded materials, conversions or AI materials. Impossible to quantify frequency. Recommend a targeted follow-up.
- Impossible albedo, glass absorption, IOR complaints: no sources found.

---

## Competitor matrix (condensed)

| Tool | What it does | Price / licence | Renderers / Max | Method | Validates? | Latest release | Weaknesses |
|---|---|---|---|---|---|---|---|
| Chaos AI Material Generator (V-Ray) | Photo to albedo/normal/roughness material, tileable, de-light | Included in V-Ray subscription via Chaos Cloud; post-beta pricing unknown | V-Ray 7.2+, Max 2021+ (7.3) | AI (cloud) | No evidence | 7.3, 23 Apr 2026 (4K) | 3 maps only; beta status/quota unclear; cloud-dependent |
| Chaos AI Material Generator (Corona) | Same, in Cosmos | Corona Solo $414/yr, Premium $514.80/yr | Corona 14/15, Max 2016+ | AI (cloud) | No evidence | Corona 15, May 2026 (4K) | Same; cannot disable? Yes can be disabled by org |
| Chaos Scans | 2,500-3,000+ scanned materials | Tiered by suite, not retrieved | V-Ray, Corona | Photographic scanning ("thousands of images"), not stated BRDF-measured | n/a | n/a | Fixed catalogue; not reference-driven |
| Chaos Cosmos | Assets/materials library | Included, quantity by tier | V-Ray, Corona, Vantage etc. | Curated | n/a | ongoing | Generic content |
| V-RayMax Converter PRO | Cross-engine scene conversion | ScriptSpot, price unverified | Max 2018-2027, V-Ray 5-7 | Heuristic mapping | No | v4.0062 (~Feb 2026) | Unsupported types; destructive if saved |
| Scene Fix | Crash/render-time fixer, albedo check | Gumroad, price unverified | V-Ray, Corona | Heuristic + render | Partial (albedo pass) | unknown | Render-based, not rules-based |
| HQ AssetsTracker | Relink/collect assets | Gumroad | Multi-renderer | Utility | Paths only | unknown | No physical checks |
| MatSnap AI | Photo/text to maps and Corona material | One-time purchase + BYO Gemini key | Corona (stated); Max 2023-2026 | AI | No | Apr 2026 | Per-use API cost; Corona-only; Max 2027? |
| Superellipse PBR Importer | Pack to wired Corona material | unknown | Corona 15+, Max 2025+ | Heuristic | No | 2026 | Own packs only |
| A23D plugin | Imports its textures to V-Ray/Corona/Arnold | unknown | multi | Library | No | v2.0.1 Mar 2026 | Library-bound |
| Substance 3D Sampler 6 | Photo/scan to material | $59.99/mo (Collection) | USD export, no V-Ray/Corona export noted | Heuristic/ML (AI not mentioned) | No | 6.0, Jun 2026 | No native VRayMtl/Corona output |
| Quixel Mixer | Material authoring | Free, abandoned | n/a | n/a | No | 2023.1, Feb 2026 final | Discontinued |
| Ubisoft CHORD | Single texture to 5 PBR maps | Free, research-only licence | ComfyUI | AI | No | date not captured | Not commercial; 1024 native |
| fal PATINA | Image/text to 5 maps up to 8K | ~$0.08-0.10 per set | API | AI | No | ~Apr 2026 | API only; no Max integration |
| Poliigon | Texture/model library | Subscription, unverified | Max plugin existence unverified | Scanned/authored | No | n/a | Convention mismatches left to user |

Not in matrix because not verified: Siger Studio, Kstudio Scene Converter/Project Manager, 3dground, Pro-Optimizer, Relink Bitmaps, Bitmap Tools, Materialize, ArmorLab, RTX Remix/PBRify, Meshy/Tripo/Polycam/Scenario/Leonardo/Krea, ambientCG, Poly Haven, Vizoo, Swatchbook.
