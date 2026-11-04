# Verify on-box: Corona (CoronaPhysicalMtl) property names and semantics

**Status: NOTHING here is verified against Corona 14/15.** `maxplugin/corona_props.py`
(`VERIFIED = frozenset()`) and `maxplugin/builder_corona.py` are proven only against the
mock runtime (`tests/mock_pymxs.py`), whose schema is the *first* candidate of every list.
A wrong name shows up on-box as a `MISS:` line in the MaxScript listener, never a crash.

**How to verify (Windows session, 3ds Max 2026/2027 + Corona 14/15):**

1. MAXScript listener: `showProperties (CoronaPhysicalMtl())`, `showProperties (CoronaNormal())`,
   `showProperties (CoronaBitmap())`, `showProperties (CoronaUvwRandomizer())`; paste the output
   next to this file (or into `inspector/tests/fixtures/props_dump.txt`).
2. For each row below, tick the candidate that exists; if none does, append the real name to the
   list in `corona_props.py` (never reorder/remove; the first entry is the mock schema).
3. For enum / scale rows, set the value in the UI and read it back with
   `(meditMaterials[1]).<prop>` in the listener.
4. Run `HEADLESS_SMOKE.py` (Corona section) and confirm zero `corona/<class>` misses; then add the
   confirmed names to `VERIFIED`.

## CoronaPhysicalMtl (`CORONA_MTL`)

| Key | Candidates (first = mock) | Value / scale written by builder_corona | How to verify |
|---|---|---|---|
| `base_color` | `baseColor`, `basecolor`, `colorBase` | `Color` swatch, linear F0 written as-is (Complex IOR fallback only) | `showProperties`; In a gamma-2.2 scene run `meditMaterials[1].diffuse = color 128 128 128` and open the picker: ≈187 shown = stored-is-linear (expected); 128 shown = stored-is-display (builders would then need encoding). Render check: chrome sphere under a white dome reads ≈0.556 linear at normal incidence (Corona, Complex IOR off) |
| `base_texmap` | `baseTexmap`, `texmapBase` | albedo Bitmaptexture (sRGB, default input gamma) | `showProperties`; check the slot in Slate |
| `base_texmap_amount` | `baseTexmapAmount`, `baseMapAmount` | 0.30 in metal F0 mode (assumed 0-1; could be 0-100) | set 30 % in UI, read the stored value |
| `roughness_mode` | `roughnessMode`, `glossinessMode` | int 0 = roughness (assumed enum) | toggle Roughness/Glossiness in UI, read value |
| `roughness` | `baseRoughness`, `roughness` | recipe `base_roughness` 0-1 | `showProperties` |
| `roughness_texmap` | `baseRoughnessTexmap`, `roughnessTexmap` | roughness map, gamma 1.0 | `showProperties`; Slate |
| `ior` | `baseIor`, `ior` | recipe IOR; glass IOR from `matphys.glass_ior` | `showProperties` |
| `metalness_mode` | `metalnessMode`, `metalMode` | int 1 = metal (assumed enum; also written with a metalness map) | toggle Metal in UI, read value |
| `metalness_texmap` | `metalnessTexmap`, `metalnessModeTexmap` | metalness map, gamma 1.0 | `showProperties`; does the map override the mode? |
| `complex_ior_on` | `useComplexIor`, `complexIorEnabled`, `metalComplexIor` | `True` for a named metal (scalar metalness 1.0, no map) | `showProperties`; does Corona 14/15 expose Complex IOR at all? |
| `complex_ior_n` | `complexIorN`, `iorN`, `metalN` | `rt.Color(n·255)` per channel (650/550/450 nm) | type: Color vs Point3 vs float triple; scale (×255?) |
| `complex_ior_k` | `complexIorK`, `iorK`, `metalK` | `rt.Color(k·255)` per channel (k up to ~4 → >255) | as above; check values >255 are not clamped |
| `edge_color` | `edgeColor`, `metalEdgeColor`, `baseEdgeColor` | linear Gulbrandsen g written as-is (fallback only) | `showProperties`; render comparison (see semantics table) |
| `anisotropy` | `baseAnisotropy`, `anisotropy` | recipe `anisotropy` (0.55 brushed), assumed 0-1 | `showProperties`; UI range |
| `refraction_amount` | `refractionAmount`, `refractAmount` | 1.0 for glass/water/gem | `showProperties` |
| `thin_mode` | `useThinMode`, `thinMode`, `refractionThin` | recipe `thin_walled` bool | `showProperties`; does thin mode ignore absorption? |
| `absorption_color` | `volumetricAbsorptionColor`, `absorptionColor` | `matphys.to_corona_absorption` colour (raw linear T, not display-encoded) | `showProperties`; same swatch-storage check as `base_color` |
| `absorption_distance` | `volumetricAbsorptionDistance`, `absorptionDistance` | `thickness_mm / mm_per_scene_unit` (scene units) | 6 mm pane in mm and cm scene; render colour of one pane |
| `sss_mode` | `volumetricMode`, `sssMode`, `scatteringMode` | int 1 = SSS (assumed enum) | set Volumetric+SSS mode in UI, read value |
| `sss_amount` | `sssAmount` | recipe `translucency.amount` (0.15 marble, 0.50 wax) | `showProperties`; 0-1 range |
| `sss_radius` | `sssRadius` | `sss_radius_mm` in scene units (2 mm marble, 5 mm wax) | `showProperties`; units = scene units? |
| `sss_color` | `sssScatterColor`, `sssColor` | recipe translucency colour (`Color`, not encoded) | `showProperties` |
| `translucency_fraction` | `translucencyFraction`, `translucencyAmount` | foliage `two_sided.amount` (0.40) | `showProperties`; 0-1 range |
| `translucency_color` | `translucencyColor` | foliage translucency colour | `showProperties` |
| `clearcoat_amount` | `clearcoatAmount` | recipe `coat.amount` | `showProperties` |
| `clearcoat_roughness` | `clearcoatRoughness` | `1 − coat.glossiness` | `showProperties` |
| `clearcoat_ior` | `clearcoatIor` | 1.5 | `showProperties` |
| `sheen_amount` | `sheenAmount` | 1.0 | `showProperties` |
| `sheen_color` | `sheenColor` | recipe `sheen.color` | `showProperties` |
| `sheen_roughness` | `sheenRoughness` | `1 − sheen.glossiness` | `showProperties` |
| `opacity_texmap` | `opacityTexmap` | opacity map, gamma 1.0 (foliage) | `showProperties` |
| `opacity_cutout` | `opacityCutout`, `opacityClip` | `True` (binary clip) | `showProperties`; render speed vs smooth |
| `bump_texmap` | `baseBumpTexmap`, `bumpTexmap` | `CoronaNormal` node | `showProperties`; Slate |
| `bump_amount` | `baseBumpMapAmount`, `bumpAmount` | recipe `bump_amount / 100` (V-Ray % → assumed 0-1 multiplier) | UI default value and range |
| `displacement_texmap` | `displacementTexmap` | height map, gamma 1.0 | `showProperties` |
| `displacement_min` | `displacementMinimum`, `displacementMin` | 0.0 (scene units) | `showProperties`; units |
| `displacement_max` | `displacementMaximum`, `displacementMax` | `displacement_mm` in scene units (3 mm stone) | 3 mm in an mm and an inch scene; measure render |
| `self_illum_level` | `selfIllumLevel` | recipe multiplier (3.0 emissive) | `showProperties`; Corona self-illum units |
| `self_illum_color` | `selfIllumColor` | white | `showProperties` |
| `self_illum_texmap` | `selfIllumTexmap` | albedo Bitmaptexture (sRGB) | `showProperties` |

## CoronaNormal (`CORONA_NORMAL`)

| Key | Candidates (first = mock) | Value written | How to verify |
|---|---|---|---|
| `input` | `normalMap`, `normal_map` | normal map Bitmaptexture, gamma 1.0 | `showProperties (CoronaNormal())` |
| `flip_green` | `flipGreen`, `flipgreen`, `flip_green` | `False` (MatForge writes OpenGL / +Y maps) | render an OpenGL test map; confirm bumps point outward |
| `add_gamma` | `addGamma` | `False` (bitmap is already linear) | `showProperties`; toggling must change the result on a gamma-2.2 load |

## CoronaBitmap (`CORONA_BITMAP`, opt-in `use_corona_bitmap=True`)

| Key | Candidates (first = mock) | Value written | How to verify |
|---|---|---|---|
| `filename` | `filename`, `fileName` | map path | `showProperties (CoronaBitmap())` |
| `gamma` | `gamma` | 1.0 data maps / 2.2 albedo | is gamma a float or a colour-space enum in Corona 14/15? OCIO? |
| `uvw` | `uvwRandomizer`, `uvw`, `mapping` | one shared `CoronaUvwRandomizer` per material | which slot takes the randomizer (likely a UVW input, not a property) — a MISS is expected until verified |

## Semantics / behaviour rows

| # | Assumption | Where | How to verify |
|---|---|---|---|
| S1 | Complex IOR n,k type (Color vs Point3) and scale (n·255 as Color channels) | `builder_corona._wire_metal` | Set n=0.2, k=3.2 in UI; read the property type and stored value |
| S2 | Edge colour semantics vs Gulbrandsen g (Open question 2: g vs reflectance at 82°) | `_wire_metal` fallback | Render chrome/gold spheres: Complex IOR vs base F0 + edge g vs base F0 + edge R(82°); pick the closest |
| S3 | `roughnessMode` 0 = roughness, `metalnessMode` 1 = metal, `volumetricMode` 1 = SSS (`ENUM_ASSUMPTIONS`) | `corona_props.ENUM_ASSUMPTIONS` | Toggle each in the UI, read the int |
| S4 | Bump amount scale: Corona multiplier vs V-Ray percentage (recipe % / 100) | `build_material` bump block | Compare a 30 % V-Ray bump to Corona 0.30 on the same normal map |
| S5 | Base texmap amount scale (0.30 assumed 0-1) | `_wire_metal` | Read UI value after the write |
| S6 | CoronaNormal `flipGreen=False` is right for OpenGL (+Y) normal maps | normal block | Render an OpenGL test map (see inspector VERIFY #6) |
| S7 | Displacement min/max are in scene units (not cm/mm fixed) | displacement block | 3 mm in mm/cm/inch scenes; measure in render |
| S8 | `opacityCutout=True` gives binary clip on foliage (no grey fringes, faster) | opacity block | Render leaves; compare with cutout off |
| S9 | `CoronaUvwRandomizer` slot on `CoronaBitmap` | `_TexFactory` | `showProperties` on both; plug in UI and read back |
| S10 | Foliage: CoronaPhysicalMtl is two-sided; translucency fraction alone (no wrapper) lights the back face | translucency block | Backlit leaf render; compare with V-Ray 2-sided result |
| S11 | Recipe metalness is bimodal: car paint and rust are now 0.0 (dielectric, coat carries car paint), so V-Ray scalar metalness == Corona `metalnessMode` for all 35 classes (off-Max parity test). A metalness map carries exposed metal | `_wire_metal` | Render car_paint in both renderers; compare |
| S12 | All colour swatches (F0, edge colour, absorption) written raw linear, same as V-Ray fog; Max stores colour params scene-linear | metal + refraction blocks | In a gamma-2.2 scene run `meditMaterials[1].diffuse = color 128 128 128` and open the picker: ≈187 shown = stored-is-linear (expected); 128 shown = stored-is-display (builders would then need encoding). Render check: chrome sphere under a white dome reads ≈0.556 linear at normal incidence; 6 mm soda-lime pane render vs measured T |
| S13 | Gemstone (no named glass): recipe fog colour = T over `thickness_mm` (10 mm), routed through matphys (`sigma_from_transmittance` → `to_corona_absorption`): colour = T, distance = 10 mm / mm_per_unit. Same sigma as the V-Ray fog, so T at 10 mm matches V-Ray to 1e-6 in mm/cm/m/inch off-Max | refraction block | Render a 10 mm gem slab in mm and m scenes; compare with V-Ray |
| S14 | Metalness map present → `metalnessMode` 1 plus `metalnessTexmap` (map overrides mode) | `_wire_metal` | PATINA metalness map on a wood class; render |
| S15 | Thin mode ignores volumetric absorption | refraction block | Toggle thin mode on a tinted pane |
