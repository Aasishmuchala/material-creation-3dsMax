# Production & Working Plan — 3ds Max material plugin (V-Ray & Corona)

Companion to `1_product_spec.md`. Durations, prices, shares and targets are estimates [Guessing] unless tagged otherwise; re-plan after Gate 1 with real velocity.

# Part II — Production plan

## The plan on one page
- **What:** material creation for 3ds Max — perfect colour, roughness, metal, normal, height, opacity, glass and translucency maps, built as native VRayMtl and CoronaPhysicalMtl.
- **Who:** three engineers (plugin, imaging, maps/ML), a part-time material artist, the founder on product and sales.
- **When:** 30 calendar weeks with three people, 46 solo. Revenue from week 10.
- **How:** two-week sprints, one self-hosted Windows test PC with Max + V-Ray + Corona, every material through the same production line.

| Milestone | Week (team) | Meaning |
|---|---|---|
| M1 | 2 | Spec verified against current Chaos / Autodesk docs |
| M2 · **Gate 1** | 10 | Inspector beta — ≥ 5 of 10 studios would pay, or rethink |
| M3 | 16 | Builder + 150 presets |
| M4 · **Gate 2** | 19 | Capture beats existing workflows on accuracy or turnaround, or drop capture |
| M5 | 26 | AI beta |
| M6 | 30 | v1.0 launch |

## Team
| Role | Skills | Owns |
|---|---|---|
| A · Plugin engineer | 3ds Max, pymxs, PySide6 | Inspector, Builder UI, node construction, packaging, licensing, installer |
| B · Imaging engineer | colour science, photometry | Rig, RAW ingest, polarisation split, photometric stereo, parameter mapping, glass & SSS |
| C · Maps & ML engineer | PyTorch, procedural | Reference tables, procedural wear, tiling, preset pipeline, AI generator |
| D · Material artist (2 d/wk) | capture, look-dev | Captures samples, reviews every material, flagship presets |
| E · Founder / product | sales, interviews | Interviews, beta, pricing, gates, Chaos partner contact, launch |

Minimum viable team: A + B (AI can follow v1.0). Solo: A → B → C in sequence, hire D from week 8.

## Master schedule (team of three, weeks)
| Lane | Work |
|---|---|
| A · Plugin | Verify docs 0–2 · Inspector MVP 2–10 · Builder UI 10–16 · Hardening & licences 16–26 · Ship 26–30 |
| B · Imaging | Rig + 20 samples 0–2 · Ingest + solve 2–8 · Mapping 8–11 · Capture pipeline 11–19 · Glass/SSS/fabric 19–24 · Capture app polish 24–30 |
| C · Maps & ML | Reference tables 2–8 · 150 presets + procedural 8–16 · AI generator 14–26 |
| D · Artist | Samples 0–2 · Capture ops + art review 8–30 |
| E · Product | Interviews 0–2 · Beta 8–10 · Sales & pricing 10–19 · Launch 26–30 |

**Critical path:** rig + samples → ingest/solve → mapping → capture pipeline → Gate 2. The Inspector lane never waits on imaging.

## First 10 weeks — Inspector MVP
| Sprint | Weeks | Work | Exit |
|---|---|---|---|
| S1 Skeleton | 3–4 | pymxs + PySide6 panel (qtmax), .bundle packaging, scene walker for VRayMtl / CoronaPhysicalMtl / legacy / bitmaps, data model + JSON | Panel lists every material in a real scene |
| S2 Rules | 5–6 | Data maps loaded as sRGB, albedo luminance, metal F0, IOR tiers, normal flip vs height, gloss/roughness swap, glass without absorption | Flags real errors in 10 downloaded scenes |
| S3 Fixes + report | 7–8 | One-click undoable fixes, batch over .max folders, report export, 50-scene false-positive test | False-positive rate < 5 % |
| S4 Beta | 9–10 | Licence keys + installer, crash reporting, 3-minute onboarding, 10 studios | **Gate 1** |

## Phases 2–7
| # | Phase | Owner | Weeks | Exit criterion |
|---|---|---|---|---|
| 2 | Parameter mapping (internal) | B | 3 | Same map set, same look in V-Ray and Corona |
| 3 | Builder + presets | A · C | 6 | Every preset passes map QA; imports fixed automatically |
| 4 | Capture pipeline | B · D | 8 | ≥ 10 new samples: albedo ΔE ≤ 2, normals/height verified — Gate 2 |
| 5 | Glass, SSS, fabric | B | 5 | Back-lit and slab checks pass in both renderers |
| 6 | AI generator | C | 10 | ≥ 60 % pass map QA before correction; licence manifest clean |
| 7 | Ship v1.0 | A · E | 4 | 15 artists through blind test; crash-free ≥ 99 % |

## Capture kit (check current prices)
Camera with RAW or RAW-capable phone $0–1,200 · lens $200–500 · copy stand or tripod + arm $150–300 · LED + polariser film $80–150 · lens polariser $40–80 · ColorChecker Classic $90–120 · chrome + black spheres $30–60 · scale markers + white card $20 · colorimeter (optional) $500–2,000. **Total ≈ $1,100–4,400.**

## Toolchain
Monorepo (`plugin/ engine/ capture-app/ presets/ tests/`) · plugin in Python 3.11 + pymxs + PySide6 (Max 2025–2027) · engine Python + PyTorch in its own process · capture app Swift (Bayer RAW) and Kotlin (Camera2 RAW_SENSOR) · **self-hosted Windows test PC** (cloud CI can't run 3ds Max) · nightly 50-scene Inspector regression + preset map QA + both-renderer look check · signed .bundle installer · support each V-Ray / Corona update within 2 weeks.

## Budget shape and risks
People ≈ 86 % (90 person-weeks + artist) · licences ≈ 7 % · test PC ≈ 4 % · kit ≈ 2 % · other ≈ 1 %. Inspector revenue should cover licences before Gate 2.

| Risk | Trigger → response |
|---|---|
| Chaos builds the same | Announcement of scene QA or customer scanning → lean on both-renderer support and same-day capture |
| Renderer update breaks mapping | Nightly look check fails → re-fit tables within 2 weeks |
| Gate 1 fails | < 5 of 10 would pay → stop capture work, rethink |
| Capture too fiddly | > 60 min per sample → guided live-view UI, or support a light box |
| Key person leaves | Documented solver, paired work from week 4 |
| Training-data licence | Unclear source → drop asset; CC0 + own captures only |

# Part III — Working plan

## Sample to finished material
| Step | What | Who | Time |
|---|---|---|---|
| 01 Sample | flat, clean, ≥ 30 cm | artist | 5 min |
| 02 Capture | 18 RAW frames | artist | 25–35 min |
| 03 Ingest | linearise, calibrate | automatic | 2 min |
| 04 Solve | albedo, normal, height, roughness | automatic | 5–15 min |
| 05 Map QA | 12 checks | automatic | 1 min |
| 06 Build | VRayMtl + CoronaPhysicalMtl | automatic | < 1 min |
| 07 Review | artist approves or returns | artist | 5 min |
| 08 Publish | library + material.json | automatic | < 1 min |

QA failure loops back to capture or solve. Presets, imports and AI output join at step 05 — no shortcut for any source. Target: 8–10 captured materials per operator per day once tuned.

## Capture session protocol
1. Prepare the sample — flat, clean, dry, ≥ 30 × 30 cm; note finish and direction.
2. Set the camera — straight down, manual focus locked, base ISO, manual exposure, fixed white balance, RAW only.
3. Place ColorChecker, scale marker, chrome and black spheres at the frame edge.
4. Shoot the flat-field — white card at the sample plane, once per session.
5. Light at position 1 — null the light's polariser on the black sphere; shoot crossed, then parallel.
6. Positions 2–8 — 45° steps, same height and distance, re-null each time.
7. Co-located flash frame — the frame that measures roughness.
8. Optional passes — rotated light (brushed metal), grazing light (fabric sheen).
9. Check the set — 18 frames, nothing clipped, every reference visible; re-shoot now.
10. Log and ingest — sample ID, finish, notes; ingest rejects non-Bayer-RAW files.

Elevation 45–60° · distance ≥ 3× sample · same exposure on every frame.

## Which source makes which map
| Source | Measured / produced | From preset or optional |
|---|---|---|
| Capture | base colour, roughness, metalness, normal, height, opacity | glass/IOR, absorption, SSS, coat from presets; anisotropy and sheen via optional passes |
| Preset | metal colour, IOR, absorption, SSS, anisotropy, coat, sheen (measured tables) | base maps from preset values |
| Import | base, roughness, metal, normal, height, opacity — fixed on import | — |
| Procedural | base, roughness, metal, normal, height, opacity, anisotropy, coat | — |
| AI | base, metal, normal, height, opacity (roughness = prior only) | — |

A material is badged **Captured** only for the maps the rig measured; others are **Preset**, **Generated** or **Imported** in material.json. Every map: 16-bit, tileable, 2048 px/m (4096 close-up), physical scale; colour maps sRGB, data maps linear.

## Definition of done
Status: Draft → Solved → QA passed → Built → Reviewed → Published.
1. Albedo ΔE2000 ≤ 2 vs calibrated photo · 2. Albedo luminance 30/50–240 sRGB · 3. Metal ≥ 95 % at 0 or 1 · 4. Metal colour matches measured F0 · 5. Roughness has real spread tied to height detail · 6. Roughness and gloss not swapped · 7. Normal agrees with height (convention checked) · 8. Height in mm, scale stored · 9. Seamless, no visible repetition · 10. Colour space right on every map · 11. Glass carries a measured absorption colour · 12. Builds in V-Ray and Corona with native nodes only.
Then the artist's look on a standard shader ball in both renderers (internal); rejections logged so the rules improve.

## Weekly rhythm
Daily 15-min stand-up · Mon sprint planning (week 1) · Tue & Thu capture days · Wed build day, no meetings · Fri material review (45 min, every week) and demo + retro (week 2). Any V-Ray or Corona release is absorbed within two weeks.

| Metric | Proposed target |
|---|---|
| Materials published / week | 8+ after Phase 4 |
| QA first-pass rate | ≥ 80 % |
| Albedo accuracy (mean ΔE2000 vs instrument) | ≤ 2.0 |
| Inspector false positives (50-scene set) | < 5 % |
| Crash-free sessions in 3ds Max | ≥ 99 % |
| Days to support a new renderer release | ≤ 14 |
