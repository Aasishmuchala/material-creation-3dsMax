# Feature Specification: MatForge Core — Reference Image to Render-Ready V-Ray Material

**Feature Branch**: `001-matforge-core`

**Created**: 2026-07-21

**Status**: **Validated (headless)** — smoke ran on real 3ds Max 2026 + V-Ray
7.30 via `3dsmaxbatch`: all 13 classes wire with **`SMOKE_OK`, 0 property
misses** (one drift, marble `translucency_on`, was caught + fixed). 52/52 off-Max
tests green (core map math + full builder wiring via mock-pymxs); 9 review
findings + 35 completeness-audit gaps addressed. Remaining: T021 interactive GUI
pass (Material-Editor sphere + test render) — needs a live UI session.

**Input**: User description: "A perfect material creation plugin for the archviz
pipeline (3ds Max + V-Ray 7 + Vantage). I give it a reference image and name it
myself; it must produce the material wired correctly for what it is (patio decking
vs. chair leather get different wiring), offer 2K/4K/8K output, and put the
finished material directly on a Material Editor sphere."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - One-Click Material from a Reference Image (Priority: P1)

An archviz artist has a reference photo of teak decking. They open MatForge in
3ds Max, pick the image, type "Patio_Teak", choose "Wood (exterior / weathered)"
and 4K, and click Create. Seconds-to-minutes later a finished, physically
correct V-Ray material named Patio_Teak sits on a Material Editor sphere, ready
to drag onto geometry.

**Why this priority**: This is the entire product promise. Every other story
decorates it.

**Independent Test**: Run the dialog against any JPEG/PNG; confirm a named
material appears in the Compact editor with diffuse/roughness/normal/height
maps wired and class physics applied.

**Acceptance Scenarios**:

1. **Given** a valid reference image and a chosen class, **When** the user
   clicks Create, **Then** a full map set (albedo, roughness, normal, height,
   AO) exists on disk at the chosen resolution and a VRayMtl carrying the
   user's exact name occupies a Material Editor slot.
2. **Given** the user typed no name, **When** they browse to an image, **Then**
   the name field pre-fills from the filename (sanitized) but remains editable
   — the user's text is always final.
3. **Given** map generation fails (bad image, missing Python), **When** Create
   is clicked, **Then** the dialog reports failure in its status line and no
   partial material is placed in the editor.

---

### User Story 2 - Class-Correct Wiring (Patio ≠ Chair) (Priority: P1)

The same click produces *different* node graphs depending on the declared
material type: exterior wood gets displacement and high roughness variation;
clear glass gets thin-walled refraction with clamped fog; foliage gets
clip-mode opacity wrapped in a two-sided translucent material with refraction
forbidden; brushed metal gets metalness 1.0 and anisotropy; fabric gets sheen;
leather and lacquered wood get a coat layer; marble gets translucency.

**Why this priority**: Wrong-class wiring is what makes hand-built materials
silently bad — this determinism is the plugin's reason to exist.

**Independent Test**: Build one material per class from the same map set and
inspect wiring (automated in `MAX_SMOKE.py` for representative classes).

**Acceptance Scenarios**:

1. **Given** class = foliage, **When** the material is built, **Then** the top
   material is a VRay2SidedMtl, opacity is in clip mode, and no refraction is
   enabled anywhere in the graph.
2. **Given** class = glass_clear, **When** built, **Then** refraction is on at
   IOR 1.52, thin-walled is enabled, and fog color's minimum channel exceeds
   0.9 with multiplier ≤ 0.5.
3. **Given** any class, **When** built, **Then** normal/roughness/height maps
   are loaded linear (gamma 1.0), Fresnel is on, and the roughness map is
   plugged without inversion via roughness mode.

---

### User Story 3 - Resolution Choice: 2K / 4K / 8K (Priority: P2)

The artist chooses output resolution per material — 2K for background assets,
4K default, 8K for hero close-ups — and the generated maps arrive at exactly
2048/4096/8192 square.

**Why this priority**: Memory and render-time economics differ per shot;
resolution control is required but doesn't change wiring.

**Independent Test**: Generate the same image at each setting; verify file
dimensions (covered by pytest).

**Acceptance Scenarios**:

1. **Given** resolution 8K selected, **When** maps generate, **Then** every
   output map measures 8192×8192.

---

### User Story 4 - Assign to Selection with Displacement (Priority: P2)

With geometry selected and "Assign to selected objects" checked, Create also
assigns the new material to every selected node and, where the class recipe
specifies real displacement (stone, concrete, exterior wood), adds a
VRayDisplacementMod at the recipe's amount.

**Why this priority**: Removes the last manual step for the common case, but
the editor-sphere flow already delivers value without it.

**Acceptance Scenarios**:

1. **Given** three objects selected and class = stone, **When** Create runs
   with assign checked, **Then** all three carry the material and a
   VRayDisplacementMod.
2. **Given** nothing selected and assign checked, **When** Create runs,
   **Then** the material still lands in the editor and the log notes that
   assignment was skipped.

---

### User Story 5 - Seamless / Tileable Output (Priority: P3)

A checkbox (default on) makes generated maps tile: opposite edges match after
the edge cross-blend, with the interior untouched.

**Acceptance Scenarios**:

1. **Given** seamless on, **When** maps generate, **Then** left/right and
   top/bottom edge rows match within tolerance and normals are derived after
   blending so lighting agrees across the seam.

---

### Edge Cases

- Reference image smaller than the chosen resolution → upscaled (Lanczos);
  quality warning is a v2 concern (AI upscale backend).
- Non-square reference → center-cropped to square before resize.
- Reference with alpha channel + foliage class → alpha becomes the opacity
  map; without alpha, opacity is fully opaque white.
- V-Ray not installed → builder aborts with a clear message (smoke script
  checks for VRayMtl class before anything else).
- V-Ray property name drift between builds → candidate lists + logged misses;
  never a crash.
- All 24 editor slots hold scene materials → first slot is overwritten
  (documented behavior; explicit slot choice is a backlog item).
- System Python missing Pillow/numpy → CLI exits nonzero; dialog surfaces the
  failure and points to PYTHON_CMD.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The user MUST provide image path, material name, class, and
  resolution; the system MUST NOT auto-classify or rename (Constitution VI).
- **FR-002**: The system MUST derive albedo (de-lit), roughness (base ±
  variation from the class recipe), tangent-space normal, height, and AO from
  the reference image, at 2048/4096/8192 square.
- **FR-003**: The system MUST wire a VRayMtl (or VRay2SidedMtl wrapper for
  foliage) per the class recipe in `core/recipes.py`, covering the 13 v1
  classes: wood_interior, wood_exterior, concrete, stone, marble,
  metal_brushed, metal_painted, glass_clear, fabric, leather, paint_wall,
  foliage, generic.
- **FR-004**: The finished material MUST be placed on a Compact Material
  Editor sphere (first free slot) and the editor opened/focused on it.
- **FR-005**: Optional assignment MUST apply the material to all selected
  nodes and add VRayDisplacementMod where `displacement_mm > 0`.
- **FR-006**: Map generation and Max wiring MUST communicate solely through
  `manifest.json` + fixed map filenames (Constitution V).
- **FR-007**: The AO map MUST be exported to disk and MUST NOT be wired into
  the material.
- **FR-008**: All data maps MUST load linear; albedo loads sRGB.
- **FR-009**: Physics guards MUST be test-enforced: foliage never refracts;
  glass fog near-white with small multiplier; IOR within [1.0, 2.5];
  metalness within [0, 1].
- **FR-010**: All V-Ray property writes MUST use candidate-name fallback with
  logged misses (Constitution IV).

### Key Entities

- **Recipe**: per-class wiring contract — IOR, metalness, base roughness +
  variation, bump %, displacement mm, refraction block, sheen/coat/
  translucency/anisotropy extras, two-sided block, opacity flag.
- **Map Set / Manifest**: named PNG files + manifest.json binding name, class,
  resolution, and absolute map paths.
- **Material**: the built VRayMtl (optionally wrapped) carrying the user's
  name, placed in an editor slot.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Reference image → material-on-sphere in a single dialog
  interaction (one Create click), with zero manual node wiring.
- **SC-002**: De-lighting measurably flattens baked illumination: left/right
  luminance gap of albedo < 50% of the source image's gap (pytest-enforced).
- **SC-003**: Seamless maps: opposite edges match within 2/255 tolerance;
  interior pixels untouched (pytest-enforced).
- **SC-004**: 100% of class recipes pass physics-sanity tests; foliage and
  glass guards can never regress silently.
- **SC-005**: `MAX_SMOKE.py` prints SMOKE_OK (or SMOKE_OK_WITH_MISSES with an
  actionable property list) in Max 2026 + V-Ray 7 — the release gate.
- **SC-006**: Time from click to 4K material on sphere ≤ 2 minutes on the
  target machine (8K may take longer; no timeout below 30 minutes).

## Assumptions

- Target environment: 3ds Max 2026, V-Ray 7.30, Windows 11; system Python
  3.12 with Pillow + numpy available as `py -3.12`.
- v1 map derivation is deterministic/heuristic (Materialize-class quality);
  an AI generator (pbr-texture-app engine / Substance Sampler) is a planned
  backend swap behind the same manifest — out of scope for 001.
- Single material per reference image; multi-material segmentation of one
  photo (patio → several materials) is explicitly out of scope for 001.
- Compact editor's 24 slots are sufficient; Slate view of the same material
  is available natively once it exists.
- Vantage compatibility is satisfied by wiring only mainstream VRayMtl /
  VRay2SidedMtl features (no exotic nodes) in v1.
