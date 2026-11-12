"""Material recipe table — the deterministic heart of MatForge.

Every value here is a physical constant or a studio-standard convention,
never an AI guess. Class recipes drive both map derivation (core/maps.py)
and V-Ray wiring (maxplugin/builder.py).

Units:
  * ior           dimensionless
  * bump_amount   VRayMtl bump *percentage*, 0-100 scale (V-Ray default 30,
                  ~100 = full strength). NOT a 0-1 multiplier — 0.3 would be
                  ~0.3% bump, i.e. effectively flat. Verified against Chaos
                  docs / forum ("Default value of bumps", default 30).
  * displacement_mm  world-unit height fed to the VRayDisplacementMod .amount
                     (applied per-object on assign, not via the material's
                     displacement percentage). 0 = no displacement.
Colors are 0-1 RGB floats.
  * relief        how much photo luminance detail is real relief: "full"
                  (grain, joints, weave), "fine" (micro-texture only: polished
                  stone, glaze, paint) or "flat" (glass, chrome); see core/maps.py.
  * stationary    True when the texture is uniform at large scale (weave, pile,
                  paint, brushing), so drift across the tile is lighting and is
                  evened out; see flatten_drift() in core/maps.py.
  * grid          True for laid tiles: a photo with a regular grout grid is
                  re-laid whole tile by tile so it repeats on grout, with no
                  lattice of identical tiles; see grid_plan() in core/maps.py.
  * coat / sheen glossiness  stated as GLOSSINESS (1 = mirror); the V-Ray
                  builder converts to roughness when Use roughness is on.
"""
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import matphys  # noqa: E402

RESOLUTIONS = {"2k": 2048, "4k": 4096, "8k": 8192}

# Fresnel IOR for dielectrics is ~1.5 across the board; refraction IOR only
# matters for transmissive classes. Metals use metalness=1 + reflect color.
RECIPES = {
    "wood_interior": {
        "label": "Wood (interior / lacquered)",
        "relief": "full",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.45, "roughness_variation": 0.20,
        "bump_amount": 30.0, "displacement_mm": 0.8,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": {"amount": 0.18, "glossiness": 0.85},
        "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "wood_floor": {
        "label": "Wood floor (lacquered boards)",
        "relief": "full",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.45, "roughness_variation": 0.20,
        "bump_amount": 30.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        # a satin lacquer film mirrors the windows in long streaks (the photo's
        # roughness alone read dead-matte); bevels and gaps are geometry
        "coat": {"amount": 0.75, "glossiness": 0.85},
        "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "wood_floor_oiled": {
        "label": "Wood floor (oiled / soaped boards)",
        "relief": "full",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.50, "roughness_variation": 0.20,
        "bump_amount": 30.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        # oil or soap leaves a broad glancing sheen toward the light, not the
        # lacquer's crisp window streaks
        "coat": {"amount": 0.50, "glossiness": 0.68},
        "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "wood_exterior": {
        "label": "Wood (exterior / weathered)",
        "relief": "full",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.65, "roughness_variation": 0.30,
        "bump_amount": 45.0, "displacement_mm": 1.5,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "concrete": {
        "label": "Concrete / plaster",
        "relief": "full",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.75, "roughness_variation": 0.15,
        "bump_amount": 40.0, "displacement_mm": 2.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "stone": {
        "label": "Stone / paver / brick",
        "relief": "full",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.70, "roughness_variation": 0.20,
        "bump_amount": 45.0, "displacement_mm": 3.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "stone_honed": {
        "label": "Stone, honed (limestone, travertine, sandstone floors)",
        "relief": "fine",
        "ior": 1.5, "metalness": 0.0,
        # ground flat and left matte: a soft broad sheen, pores and fossils
        # as fine tooth only (the paver class gave a honed floor the relief
        # of roughcast)
        "base_roughness": 0.52, "roughness_variation": 0.10,
        "bump_amount": 14.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "marble": {
        "label": "Marble / polished stone",
        "relief": "flat",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.10, "roughness_variation": 0.04,
        "bump_amount": 4.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        # thin translucency sells marble; wired as VRayMtl translucency
        # SSS radius from Jensen et al. 2001 (R/G/B 8.5/5.6/4.0 mm)
        "translucency": {"color": (0.93, 0.91, 0.88), "amount": 0.15,
                         "sss_radius_mm": 8.5, "sss_amount": 0.8,
                         "sss_rgb": (1.0, 0.655, 0.464)},
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "metal_brushed": {
        "label": "Metal (brushed / raw)",
        "relief": "fine",
        "stationary": True,
        "ior": 1.5, "metalness": 1.0,
        # +-0.15 of cloudy variation on a metal read as dented foil: every
        # patch of the reflection sharpened or blurred by itself. A brushed
        # sheet is even; smudges are faint
        "base_roughness": 0.35, "roughness_variation": 0.05,
        "bump_amount": 20.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "anisotropy": 0.55,
        "metal": None,  # named metal (matphys.METALS key) or None = from image
        "coat": None, "sheen": None, "self_illum": False,
        # albedo map drives the tint for metals
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "metal_painted": {
        "label": "Metal (painted / powder-coated)",
        "relief": "fine",
        "stationary": True,
        "ior": 1.5, "metalness": 0.0,
        # powder coat is satin-matte: with a 0.35 coat at 0.90 a matte black
        # console mirrored its books and the wall crisply, like gloss enamel
        "base_roughness": 0.48, "roughness_variation": 0.10,
        "bump_amount": 15.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": {"amount": 0.12, "glossiness": 0.70},
        "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "glass_clear": {
        "label": "Glass (clear / glazing)",
        "roughness_broad": 0.0,      # mirror-smooth: no cloudy gloss patches
        "relief": "flat",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.02, "roughness_variation": 0.02,
        "bump_amount": 4.0, "displacement_mm": 0.0,
        # fog is deliberately near-white with a tiny multiplier — the
        # saturated-fog trap turns glass into opaque paint.
        "refraction": {"ior": 1.52, "thin_walled": True,
                       "fog_color": (0.98, 1.0, 0.985), "fog_mult": 0.05,
                       "affect_shadows": True,
                       "glass": "soda_lime", "thickness_mm": 6.0},
        "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "glass_object": {
        "label": "Glass (solid objects: vases, tumblers, jars)",
        "roughness_broad": 0.0,      # mirror-smooth: no cloudy gloss patches
        "relief": "flat",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.02, "roughness_variation": 0.02,
        "bump_amount": 2.0, "displacement_mm": 0.0,
        # modelled walls refract for real. Thin-walled glazing on a vase put
        # the pane's tint on at every wall crossing and cast a mint shadow;
        # here low-iron absorption over the walls' own thickness.
        "refraction": {"ior": 1.52, "thin_walled": False,
                       "fog_color": (0.99, 0.995, 0.99), "fog_mult": 0.05,
                       "affect_shadows": True,
                       "glass": "low_iron", "thickness_mm": 4.0},
        "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "fabric": {
        "label": "Fabric / linen / upholstery",
        "relief": "full",
        "stationary": True,
        "ior": 1.3, "metalness": 0.0,     # cellulose/wool fibre: F0 1.7 %, not glassy 4 %
        "base_roughness": 0.85, "roughness_variation": 0.10,
        "bump_amount": 35.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "sheen": {"color": (0.85, 0.85, 0.85), "glossiness": 0.40},
        "coat": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "canvas_waxed": {
        "label": "Waxed canvas / oilcloth",
        "relief": "full",
        "stationary": True,
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.55, "roughness_variation": 0.12,
        "bump_amount": 30.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        # the wax closes the weave: a soft low lustre and no fibre sheen (the
        # cloth class's 0.85 grey sheen made a waxed tote read as felt or cork)
        "coat": {"amount": 0.15, "glossiness": 0.60},
        "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "fabric_sheer": {
        "label": "Fabric (thin: curtains, lamp shades)",
        "relief": "full",
        "stationary": True,
        "ior": 1.3, "metalness": 0.0,
        "base_roughness": 0.85, "roughness_variation": 0.10,
        "bump_amount": 30.0, "displacement_mm": 0.0,
        "refraction": None,
        # thin cloth passes light, tinted by its own colour: backlit curtains
        # and lit shades glow (an opaque upholstery cloth hung like board)
        "two_sided": {"translucency": (1.0, 1.0, 1.0), "amount": 0.45, "mult_front": True},
        "opacity": False,
        "sheen": {"color": (0.85, 0.85, 0.85), "glossiness": 0.40},
        "coat": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "fabric_voile": {
        "label": "Fabric (sheer voile: see-through curtains)",
        "relief": "full",
        "stationary": True,
        "ior": 1.3, "metalness": 0.0,
        "base_roughness": 0.85, "roughness_variation": 0.10,
        "bump_amount": 30.0, "displacement_mm": 0.0,
        "refraction": None,
        # the threads glow with the light behind them (less than a lamp
        # shade's denser cloth: most of the light goes through the gaps)
        "two_sided": {"translucency": (1.0, 1.0, 1.0), "amount": 0.26, "mult_front": True},
        # the open weave: this fraction of the light goes straight through
        # the gaps between the threads, so the window frame shows through
        # (as fabric_sheer, translucency alone, a voile rendered as an opaque
        # white sheet). Thin-walled, so nothing bends; the IOR's Fresnel
        # still closes the weave up at grazing angles, as the gaps do in
        # projection.
        # (0.62, once the see-through really worked, all but hid the curtain
        # against a bright window; a voile is about a third open)
        "see_through": 0.36,
        "opacity": False,
        "sheen": {"color": (0.85, 0.85, 0.85), "glossiness": 0.40},
        "coat": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "boucle": {
        "label": "Boucle / loop-pile upholstery",
        "relief": "full",
        "stationary": True,
        "ior": 1.3, "metalness": 0.0,
        "base_roughness": 0.9, "roughness_variation": 0.08,
        # the loops are relief: with bump alone it rendered as smooth fleece
        "bump_amount": 60.0, "displacement_mm": 3.5,
        "refraction": None, "two_sided": False, "opacity": False,
        "sheen": {"color": (0.6, 0.6, 0.6), "glossiness": 0.45},
        "coat": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "leather": {
        "label": "Leather",
        "relief": "full",
        "stationary": True,
        "ior": 1.5, "metalness": 0.0,
        # semi-aniline upholstery: at 0.60 (and a 0.12 coat) the window
        # left no highlight on a black seat and the leather read as rubber;
        # at 0.46 with +-15 % cloudy variation and bump 40 the room still
        # spread over the black as a grey veil and the seat marbled and
        # pebbled. A tighter, even satin with a firmer finish coat lets the
        # body stay black and the window roll over the crowns.
        "base_roughness": 0.38, "roughness_variation": 0.08,
        "bump_amount": 25.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": {"amount": 0.30, "glossiness": 0.80},
        # a faint neutral grazing lift, not cloth's fibre sheen: the forged
        # sheen map (sqrt of the albedo) lifted black leather's 0.036 to
        # 0.19 and a 0.6 grey veiled it, so a black chair rendered 8x
        # brighter than in the reference photo (map False: colour only)
        "sheen": {"color": (0.05, 0.05, 0.05), "glossiness": 0.50, "map": False},
        "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "paint_wall": {
        "label": "Painted wall",
        "relief": "fine",
        "stationary": True,
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.62, "roughness_variation": 0.06,
        "bump_amount": 8.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "foliage": {
        "label": "Foliage / leaves",
        "relief": "full",
        "ior": 1.45, "metalness": 0.0,
        "base_roughness": 0.35, "roughness_variation": 0.20,
        "bump_amount": 25.0, "displacement_mm": 0.0,
        # NO refraction — thin-surface translucency via VRay2SidedMtl.
        "refraction": None,
        "two_sided": {"translucency": (0.55, 0.68, 0.38), "amount": 0.40},
        # a living green leaf reflects 5-15 %: a brighter cut-out (a studio
        # shot exposed for its white paper) is darkened to this mean
        "leaf_lum_max": 0.16,
        # clip-mode opacity: binary cutout, several-x faster than smooth
        "opacity": True,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "foliage_thick": {
        "label": "Foliage, thick leaves (banana, rubber plant)",
        "relief": "full",
        "ior": 1.45, "metalness": 0.0,
        # a waxy cuticle: tighter highlights than thin leaves'
        "base_roughness": 0.28, "roughness_variation": 0.15,
        "bump_amount": 25.0, "displacement_mm": 0.0,
        "refraction": None,
        # a thick blade passes little light: at thin leaves' 0.40 a north
        # window lit every banana blade lime from behind
        "two_sided": {"translucency": (0.55, 0.68, 0.38), "amount": 0.15},
        "leaf_lum_max": 0.12,
        "opacity": True,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },

    # ---- STONE / MASONRY ----
    "stone_backlit": {
        # alabaster lamps, backlit onyx bars: the stone glows from a light
        # behind or inside it, its veins showing through. Marble's polish and
        # SSS for the room light falling on it, plus a soft self-illumination
        # in the stone's own colours (the albedo drives it, compensated for
        # the camera exposure, emitting GI); 1.0 keeps the veining - the LED
        # panel's 3.0 burns it out to white
        "label": "Stone, backlit (alabaster / onyx)",
        "relief": "flat",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.18, "roughness_variation": 0.05,
        "bump_amount": 4.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "translucency": {"color": (0.95, 0.93, 0.88), "amount": 0.4,
                         "sss_radius_mm": 15.0, "sss_amount": 0.9,
                         "sss_rgb": (1.0, 0.8, 0.62)},
        "coat": None, "sheen": None,
        "self_illum": {"multiplier": 1.0},
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "granite": {
        "label": "Granite / terrazzo (polished)",
        "relief": "flat",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.12, "roughness_variation": 0.05,
        "bump_amount": 4.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "concrete_polished": {
        "label": "Concrete (polished / microcement)",
        "relief": "flat",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.30, "roughness_variation": 0.10,
        "bump_amount": 5.0, "displacement_mm": 0.3,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "terracotta": {
        "label": "Terracotta / clay / unglazed brick",
        "plain_unless_tiled": True,
        "relief": "full",
        "grid": True,
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.62, "roughness_variation": 0.18,
        "bump_amount": 45.0, "displacement_mm": 1.5,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },

    "ceramic_matte": {
        "label": "Ceramic, matte glaze (stoneware, planters)",
        "stationary": True,
        "relief": "fine",
        "ior": 1.5, "metalness": 0.0,
        # a satin-matte glaze over the clay: smooth to the hand, a soft broad
        # highlight, the iron specks as colour not pits (as unglazed clay a
        # planter read as cast concrete)
        "base_roughness": 0.45, "roughness_variation": 0.06,
        "bump_amount": 8.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },

    # ---- CERAMIC / GLASS / TRANSMISSIVE ----
    "ceramic_glazed": {
        "label": "Ceramic / porcelain (glazed tile)",
        "plain_unless_tiled": True,   # one glaze: tile-wide drift is lighting (a laid grid is not)
        "roughness_broad": 0.0,      # mirror-smooth: no cloudy gloss patches
        "relief": "fine",
        "grid": True,
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.08, "roughness_variation": 0.05,
        "bump_amount": 10.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": {"amount": 0.40, "glossiness": 0.97},
        "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "glass_frosted": {
        "label": "Glass (frosted / etched)",
        "roughness_broad": 0.0,      # mirror-smooth: no cloudy gloss patches
        "relief": "flat",        # the frost is rough refraction; a pane's photo has no relief to read
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.30, "roughness_variation": 0.05,
        "bump_amount": 6.0, "displacement_mm": 0.0,
        "refraction": {"ior": 1.52, "thin_walled": True,
                       "fog_color": (0.98, 1.0, 0.99), "fog_mult": 0.04,
                       "affect_shadows": True, "glossiness": 0.50,
                       "glass": "soda_lime", "thickness_mm": 6.0},
        "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "gemstone": {
        "label": "Gemstone / crystal",
        "relief": "flat",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.02, "roughness_variation": 0.02,
        "bump_amount": 2.0, "displacement_mm": 0.0,
        "refraction": {"ior": 1.80, "thin_walled": False,
                       "fog_color": (0.97, 0.99, 1.0), "fog_mult": 0.06,
                       "affect_shadows": True, "thickness_mm": 10.0},
        "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "water": {
        "label": "Water / liquid",
        "roughness_broad": 0.0,      # mirror-smooth: no cloudy gloss patches
        "relief": "fine",
        "ior": 1.33, "metalness": 0.0,
        "base_roughness": 0.02, "roughness_variation": 0.02,
        "bump_amount": 8.0, "displacement_mm": 0.0,
        "refraction": {"ior": 1.33, "thin_walled": False,
                       "fog_color": (0.96, 0.99, 1.0), "fog_mult": 0.02,
                       "affect_shadows": True,
                       "glass": "water", "thickness_mm": 1000.0},
        "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },

    # ---- METAL ----
    "metal_chrome": {
        "label": "Metal (chrome / mirror polished)",
        "roughness_broad": 0.0,      # mirror-smooth: no cloudy gloss patches
        "relief": "flat",
        "stationary": True,
        "ior": 1.5, "metalness": 1.0,
        "base_roughness": 0.03, "roughness_variation": 0.02,
        "bump_amount": 2.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "metal": "chrome",
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "metal_satin": {
        "label": "Metal (satin / stainless steel)",
        "relief": "fine",
        "stationary": True,
        "ior": 1.5, "metalness": 1.0,
        "base_roughness": 0.20, "roughness_variation": 0.08,
        "bump_amount": 8.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "metal": "stainless_steel",
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "metal_rust": {
        "label": "Metal (rusted / corten steel)",
        "relief": "full",
        # rust/oxide is dielectric; metalness is bimodal (spec 2b) -- a
        # metalness MAP carries any exposed bare metal
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.65, "roughness_variation": 0.25,
        "bump_amount": 40.0, "displacement_mm": 0.5,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "car_paint": {
        "label": "Car paint (metallic + clearcoat)",
        "roughness_broad": 0.0,      # mirror-smooth: no cloudy gloss patches
        "relief": "fine",
        "stationary": True,
        # paint binder is dielectric (metalness bimodal, spec 2b); the
        # clearcoat carries the look, flakes are not modelled as metal
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.30, "roughness_variation": 0.05,
        "bump_amount": 3.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": {"amount": 0.70, "glossiness": 0.98},
        "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },

    # ---- PLASTIC / RUBBER ----
    "plastic_glossy": {
        "label": "Plastic (glossy)",
        "roughness_broad": 0.0,      # mirror-smooth: no cloudy gloss patches
        "relief": "fine",
        "stationary": True,
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.10, "roughness_variation": 0.04,
        "bump_amount": 3.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "plastic_matte": {
        "label": "Plastic (matte)",
        "relief": "fine",
        "stationary": True,
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.55, "roughness_variation": 0.08,
        "bump_amount": 8.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "rubber": {
        "label": "Rubber",
        "relief": "fine",
        "stationary": True,
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.72, "roughness_variation": 0.08,
        "bump_amount": 20.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },

    # ---- SOFT / TEXTILE ----
    "velvet": {
        "label": "Velvet",
        "relief": "full",
        "stationary": True,
        "ior": 1.3, "metalness": 0.0,     # cellulose/wool fibre: F0 1.7 %, not glassy 4 %
        "base_roughness": 0.90, "roughness_variation": 0.05,
        "bump_amount": 15.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        # pile scatters light wide: at 0.85 (roughness 0.15) the sheen was a
        # razor-thin grazing rim and a velvet throw rendered as matte felt
        # from_albedo: the sheen is the albedo's hue lifted to that luminance
        # and partly desaturated (emerald -> mint, about sRGB 97/157/128; rust ->
        # terracotta about 195/128/100):
        # 4.5x the albedo stayed dark and saturated and read as felt. mottle:
        # +/-25 % over 25 cm, the crushed-pile blotching
        # (0.45 lum / 0.5 desat at roughness 0.45 washed rust to dusty pink and
        # emerald to pale teal: the sheen covered every angle)
        "sheen": {"color": (0.70, 0.70, 0.70), "glossiness": 0.65,
                  "from_albedo": 0.28, "desat": 0.35, "mottle": 0.25, "mottle_cm": 25.0},
        # photo velvet comes out darker and more saturated than sRGB holds
        # (emerald red channel ~0), which swallowed any sheen
        "albedo_cc": {"saturation": -10.0, "brightness": 4.0},
        "coat": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "carpet": {
        "label": "Carpet / rug",
        "relief": "full",
        "stationary": True,
        "ior": 1.3, "metalness": 0.0,     # cellulose/wool fibre: F0 1.7 %, not glassy 4 %
        "base_roughness": 0.92, "roughness_variation": 0.10,
        "bump_amount": 55.0, "displacement_mm": 1.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "sheen": {"color": (0.50, 0.50, 0.50), "glossiness": 0.30},
        "coat": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },

    # ---- MISC ARCHITECTURAL / ORGANIC / SPECIAL ----
    "paper": {
        "label": "Paper / cardboard",
        "stationary": True,
        "relief": "fine",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.72, "roughness_variation": 0.10,
        "bump_amount": 10.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "cork": {
        "label": "Cork",
        "relief": "full",
        "stationary": True,
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.68, "roughness_variation": 0.15,
        "bump_amount": 35.0, "displacement_mm": 0.5,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "asphalt": {
        "label": "Asphalt / tarmac",
        "relief": "full",
        "stationary": True,
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.82, "roughness_variation": 0.12,
        "bump_amount": 45.0, "displacement_mm": 1.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "sand": {
        "label": "Sand / gravel / soil",
        "relief": "full",
        "stationary": True,
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.90, "roughness_variation": 0.15,
        "bump_amount": 60.0, "displacement_mm": 2.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "wax": {
        "label": "Wax / candle / soap (SSS)",
        "relief": "fine",
        "stationary": True,
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.35, "roughness_variation": 0.10,
        "bump_amount": 10.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "translucency": {"color": (0.95, 0.90, 0.80), "amount": 0.50,
                         "sss_radius_mm": 20.0, "sss_amount": 1.0,
                         "sss_rgb": (1.0, 0.78, 0.55)},
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
    "emissive": {
        "label": "Emissive / LED panel",
        "stationary": True,
        "roughness_broad": 0.0,      # mirror-smooth: no cloudy gloss patches
        "relief": "flat",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.50, "roughness_variation": 0.10,
        "bump_amount": 0.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None,
        "self_illum": {"multiplier": 3.0},
        "reflect_color": (1.0, 1.0, 1.0),
    },

    "generic": {
        "label": "Generic dielectric",
        "relief": "full",
        "ior": 1.5, "metalness": 0.0,
        "base_roughness": 0.55, "roughness_variation": 0.20,
        "bump_amount": 30.0, "displacement_mm": 0.0,
        "refraction": None, "two_sided": False, "opacity": False,
        "coat": None, "sheen": None, "self_illum": False,
        "reflect_color": (1.0, 1.0, 1.0),
    },
}

# Physical reference constants kept alongside for future classes / validation.
# Dielectric IORs come from matphys.glass; the rest are literal.
IOR_TABLE = {
    "water": matphys.glass_ior("water"), "ice": matphys.glass_ior("ice"),
    "glass_window": matphys.glass_ior("soda_lime"),
    "glass_crystal": matphys.glass_ior("lead_crystal"),
    "acrylic": 1.49, "diamond": 2.42, "sapphire": 1.77, "olive_oil": 1.47,
}

# Measured linear F0 per metal (650/550/450 nm), one source: matphys.metals.
METAL_TINTS = {k: matphys.metal_f0(k)
               for k in ("gold", "silver", "copper", "aluminium", "iron")}
METAL_TINTS["aluminum"] = METAL_TINTS["aluminium"]


def get_recipe(mclass):
    if mclass not in RECIPES:
        raise KeyError(
            f"Unknown material class '{mclass}'. Valid: {', '.join(RECIPES)}")
    return RECIPES[mclass]


def class_choices():
    """(key, label) pairs in stable order for UI dropdowns."""
    return [(k, v["label"]) for k, v in RECIPES.items()]


CLASS_GROUPS = [
    ("Wood", ["wood_interior", "wood_floor", "wood_floor_oiled", "wood_exterior", "cork"]),
    ("Stone", ["concrete", "concrete_polished", "stone", "stone_honed", "marble", "stone_backlit", "granite",
               "terracotta", "ceramic_glazed", "ceramic_matte", "asphalt", "sand"]),
    ("Metal", ["metal_brushed", "metal_painted", "metal_chrome", "metal_satin",
               "metal_rust", "car_paint"]),
    ("Glass", ["glass_clear", "glass_object", "glass_frosted", "gemstone", "water"]),
    ("Fabric", ["fabric", "fabric_sheer", "fabric_voile", "canvas_waxed", "boucle", "leather", "velvet", "carpet",
                "paper"]),
    ("Plastic", ["plastic_glossy", "plastic_matte", "rubber"]),
    ("Other", ["paint_wall", "foliage", "foliage_thick", "wax", "emissive", "generic"]),
]


def grouped_class_choices():
    """[(group, [(key, label), ...]), ...] for the dock's class tiles."""
    return [(group, [(k, RECIPES[k]["label"]) for k in keys])
            for group, keys in CLASS_GROUPS]


def wants_metal_picker(key):
    """True when the class is a metal, so the UI shows the metal picker."""
    return key.startswith("metal_")
