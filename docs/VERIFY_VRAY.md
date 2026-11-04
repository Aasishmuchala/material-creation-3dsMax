# V-Ray builder: UNVERIFIED items added by the physics layer

All existing V-Ray property candidates remain SMOKE_OK on V-Ray 7.30. The
rows below are NEW names or semantics, unverified on a live V-Ray session.
Verify with `showProperties (VRayMtl())` and a test render.

| Property / behaviour | Assumption | How to verify |
|---|---|---|
| `texmap_diffuse_multiplier` (new candidate) | 0-100 percent scale; 30.0 = 30 % albedo map over the F0 swatch | showProperties; render chrome with map and compare against 0 / 100 |
| `reflection` colour = Gulbrandsen edge tint in metalness mode | reflection colour tints grazing reflectance when `reflection_metalness` = 1 | Render a gold sphere, compare 82 degree reflectance against matphys `reflectance_at` |
| `diffuse` / `reflection` / fog swatch storage under gammaMgr / OCIO | Max stores colour params scene-linear; builders write linear F0, edge tint and fog as-is (no display encoding) | In a gamma-2.2 scene run `meditMaterials[1].diffuse = color 128 128 128` and open the picker: ≈187 shown = stored-is-linear (expected); 128 shown = stored-is-display (builders would then need encoding). Render check: chrome sphere under a white dome reads ≈0.556 linear at normal incidence (V-Ray, chrome F0) |
| Fog model | `fog_color^(fog_mult * depth)`; APPROXIMATE vs Beer-Lambert. Colour = transmittance of one pane, mult = mm_per_unit / thickness_mm | Render a 6 mm pane edge-on and a 100 mm slab, compare against `exp(-sigma d)` |
| Thin-walled glass | `refraction_thinWalled` ignores fog entirely, so absorption has no effect for thin panes | Toggle thin-walled on a solid pane and compare tint |
