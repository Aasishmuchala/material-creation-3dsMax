"""The realism lab's test set: one entry per material, covering every MatForge class.

Each entry: MatForge class, the hero object groups in lab_scene.py, the camera,
the real-world size one texture tile covers (cm), and the Runway prompt that
produced the reference photo (kept so a reference can be regenerated).
"""

COMMON = (" Seamless tileable texture photograph. Perfectly flat, top-down orthographic view: "
          "the camera sensor is parallel to the surface, no perspective, no vanishing point. "
          "Even, soft, shadowless cross-polarized studio lighting: no specular highlights, no "
          "reflections, no glare, no vignetting. The material fills the whole frame edge to edge. "
          "Ultra-sharp, true-to-life colour and real-world texture detail. No objects, no text, "
          "no watermark, no border.")

# id: (class, hero groups, camera, tile_cm, subject, extra)
MATERIALS = {
    # ---------------- flooring
    "oak_floor": ("wood_interior", ["floor"], "floor", 90,
                  "A natural European white oak plank floor: five full-length planks, each 18 cm "
                  "wide, run vertically across the frame (the frame covers 90 x 90 cm), thin dark "
                  "hairline joints between planks and staggered end joints. Matte oiled finish, "
                  "straight grain with cathedral figure, small pin knots, warm honey-beige colour "
                  "varying slightly from plank to plank.", {}),
    "walnut_herringbone": ("wood_interior", ["floor"], "floor", 80,
                           "An American black walnut herringbone parquet floor: 7 x 40 cm blocks "
                           "in a classic herringbone pattern with fine dark joints (the frame covers "
                           "80 x 80 cm). Rich chocolate-brown heartwood with lighter streaks, satin "
                           "oil finish, open grain.", {}),
    "marble_tile_floor": ("marble", ["floor"], "floor", 120,
                          "A polished Carrara marble floor of 60 x 60 cm square tiles, 2 x 2 tiles "
                          "fill the frame (the frame covers 120 x 120 cm), 2 mm light grey grout "
                          "lines. Soft white stone with delicate grey feathered veining, natural "
                          "variation between tiles.", {}),
    "polished_concrete": ("concrete_polished", ["floor"], "floor", 200,
                          "A polished microcement floor: smooth mid-grey cement with subtle cloudy "
                          "trowel marks, faint aggregate specks and fine hairline crazing (the frame "
                          "covers 2 x 2 m).", {}),
    "terrazzo_floor": ("granite", ["floor"], "floor", 100,
                       "A polished terrazzo floor: off-white cement matrix with scattered marble "
                       "chips 3 to 25 mm in terracotta, grey, black and cream (the frame covers "
                       "1 x 1 m).", {}),
    "terracotta_floor": ("terracotta", ["floor"], "floor", 100,
                         "Handmade unglazed terracotta floor tiles, 25 x 25 cm squares, 4 x 4 tiles "
                         "fill the frame (the frame covers 1 x 1 m), 6 mm sandy grout joints. Warm "
                         "orange-red clay with darker fired edges, small pits and colour variation "
                         "from tile to tile.", {}),
    "slate_floor": ("stone", ["floor"], "floor", 150,
                    "A natural slate floor of 40 x 60 cm rectangular slabs in a running bond with "
                    "8 mm dark grout (the frame covers 1.5 x 1.5 m). Charcoal-grey cleft slate with "
                    "subtle rust and green-grey tones and a layered riven texture.", {}),
    "cork_floor": ("cork", ["floor"], "floor", 60,
                   "A natural cork floor: agglomerated cork granules in warm tan and caramel tones, "
                   "fine porous granular texture (the frame covers 60 x 60 cm).", {}),
    "wool_rug": ("carpet", ["rug"], "rug", 60,
                 "A dense cut-pile wool area rug in warm oatmeal and cream: soft fibre tufts with "
                 "subtle heathered colour variation (the frame covers 60 x 60 cm).", {}),
    # ---------------- walls
    "white_paint_wall": ("paint_wall", ["wall"], "wall", 150,
                         "A white interior wall painted with matte eggshell emulsion over plaster: "
                         "very subtle roller stipple and faint undulation, warm white (the frame "
                         "covers 1.5 x 1.5 m).", {}),
    "limewash_wall": ("concrete", ["wall"], "wall", 200,
                      "A hand-applied limewash plaster wall in soft greige: cloudy, mottled brush "
                      "strokes with gentle tonal variation (the frame covers 2 x 2 m).", {}),
    "brick_wall": ("stone", ["wall"], "wall", 120,
                   "An exposed reclaimed red brick wall: 21.5 x 6.5 cm bricks in running bond with "
                   "1 cm recessed lime mortar joints (the frame covers 1.2 x 1.2 m), varied red, "
                   "brown and charred bricks with chipped edges.", {}),
    "board_formed_concrete": ("concrete", ["wall"], "wall", 200,
                              "A board-formed architectural concrete wall: horizontal timber-plank "
                              "imprints 15 cm tall with visible wood grain, small air pockets and "
                              "tie holes, cool mid-grey cement (the frame covers 2 x 2 m).", {}),
    # a 1 m frame of tiles: with 5 x 5 the same tiles stood on a 50 cm lattice
    "zellige_wall": ("ceramic_glazed", ["wall"], "wall", 90,      # 9 x 9 tiles of 10 cm after the re-lay
                     "A glossy handmade zellige tile wall: 10 x 10 cm square glazed tiles, 10 x 10 "
                     "tiles fill the frame (the frame covers 100 x 100 cm). Every tile is different: "
                     "irregular glaze pooling, pinholes, slightly wavy edges and its own shade of "
                     "sage green from pale celadon to deeper olive, 2 mm white grout.", {}),
    "calacatta_wall": ("marble", ["wall"], "wall", 200,
                       "A book-matched Calacatta marble wall slab: bright white stone with bold grey "
                       "and soft gold veins (the frame covers 2 x 2 m).", {}),
    # ---------------- sofa
    "linen_sofa": ("fabric", ["sofa", "cushion"], "sofa", 25,
                   "A natural oatmeal linen upholstery fabric: visible plain weave with irregular "
                   "slub yarns and soft fuzzy fibres (the frame covers 25 x 25 cm).", {}),
    "boucle_sofa": ("fabric", ["sofa", "cushion"], "sofa_close", 20,
                    "A cream boucle upholstery fabric: dense small looped yarn curls forming a "
                    "nubbly, pebbly surface (the frame covers 20 x 20 cm).", {}),
    # flat and even: pressure marks baked into a 30 cm repeat recur across a sofa
    "velvet_sofa": ("velvet", ["sofa", "cushion"], "sofa", 30,
                    "A deep emerald-green cotton velvet upholstery textile: short dense even pile "
                    "with a fine, uniform, soft velvety surface and very subtle tonal shading, "
                    "smooth and flat with no wrinkles (the frame covers 30 x 30 cm).", {}),
    "leather_sofa": ("leather", ["sofa", "cushion"], "sofa", 40,
                     "A cognac-brown full-grain aniline leather hide: natural pebble grain pores, "
                     "fine creases and soft tonal variation (the frame covers 40 x 40 cm).", {}),
    # ---------------- furniture surfaces
    "walnut_table": ("wood_interior", ["table_top"], "table", 120,
                     "A smooth American black walnut tabletop: flat-sawn grain with flame figure, "
                     "colour from dark chocolate to warm brown, fine open pores, satin finish (the "
                     "frame covers 1.2 x 1.2 m).", {}),
    "calacatta_table": ("marble", ["table_top"], "table", 120,
                        "A polished Calacatta marble slab: bright white stone with bold grey and "
                        "soft gold veins (the frame covers 1.2 x 1.2 m).", {}),
    "black_granite": ("granite", ["table_top"], "table", 100,
                      "A polished black galaxy granite slab: deep black stone with dense small "
                      "copper-gold and white mineral flecks (the frame covers 1 x 1 m).", {}),
    "weathered_teak": ("wood_exterior", ["ext_bench"], "ext_bench", 100,
                       "Weathered silver-grey teak boards: sun-bleached grain, raised ridges, fine "
                       "checks and cracks, 14 cm wide boards running horizontally with dark gaps "
                       "(the frame covers 1 x 1 m).", {}),
    # ---------------- metals
    "brushed_steel": ("metal_brushed", ["metal_obj", "table_leg", "lamp"], "table", 30,
                      "A brushed stainless steel sheet: fine straight parallel brushing lines "
                      "running horizontally, even light grey satin metal (the frame covers 30 x 30 "
                      "cm).", {}),
    "chrome": ("metal_chrome", ["metal_obj", "table_leg", "lamp"], "props", 20,
               "A polished chrome-plated metal surface photographed under diffuse light: smooth "
               "bright neutral grey with faint micro-scratches and swirl marks (the frame covers "
               "20 x 20 cm).", {}),
    "satin_stainless": ("metal_satin", ["metal_obj", "table_leg", "lamp"], "props", 20,
                        "A satin-finish stainless steel surface: very fine soft directional grain, "
                        "even light grey (the frame covers 20 x 20 cm).", {}),
    "brass": ("metal_brushed", ["metal_obj", "table_leg", "lamp"], "props", 20,
              "A brushed brass sheet: warm golden yellow metal with fine straight brushing lines "
              "and faint patina (the frame covers 20 x 20 cm).", {"metal": "brass"}),
    "black_powder_coat": ("metal_painted", ["table_leg", "lamp", "metal_obj"], "lamp", 20,
                          "A matte black powder-coated steel surface: fine orange-peel texture, "
                          "deep charcoal black (the frame covers 20 x 20 cm).", {}),
    "corten": ("metal_rust", ["corten"], "corten", 100,
               "A weathered corten steel plate: stable orange-brown rust patina with darker "
               "streaks, mottled oxide layers and fine pitting (the frame covers 1 x 1 m).", {}),
    "car_paint_red": ("car_paint", ["metal_obj", "plastic_obj"], "props", 10,
                      "A deep red metallic automotive paint surface: fine sparkling metallic flakes "
                      "in a candy red base under a smooth clearcoat (the frame covers 10 x 10 cm).",
                      {}),
    # ---------------- glass and liquids
    "clear_glass": ("glass_clear", ["vase", "tumbler"], "props", 30,
                    "A sheet of clear float glass lying on a white background, seen from above: "
                    "almost featureless, faint fingerprints and very fine dust specks (the frame "
                    "covers 30 x 30 cm).", {}),
    "frosted_glass": ("glass_frosted", ["frosted_panel", "vase"], "frosted", 30,
                      "A sheet of acid-etched frosted glass on a white background: soft even milky "
                      "satin translucency with a very fine uniform grain (the frame covers 30 x 30 "
                      "cm).", {}),
    "amethyst": ("gemstone", ["gem"], "gem", 6,
                 "A polished slice of purple amethyst crystal: translucent violet quartz with "
                 "internal veils and colour zoning (the frame covers 6 x 6 cm).", {}),
    "water": ("water", ["water"], "props", 30,
              "Clear still water in a white basin seen from above: very gentle ripples, crystal "
              "clear (the frame covers 30 x 30 cm).", {}),
    # ---------------- plastics and rubber
    "glossy_plastic": ("plastic_glossy", ["plastic_obj", "rubber_obj"], "props", 20,
                       "A smooth glossy injection-moulded ABS plastic surface in signal red: "
                       "flawless apart from a very faint moulding swirl (the frame covers 20 x 20 "
                       "cm).", {}),
    "matte_plastic": ("plastic_matte", ["plastic_matte"], "matte", 20,
                      "A matte light-grey polypropylene plastic surface with a fine bead-blasted "
                      "texture (the frame covers 20 x 20 cm).", {}),
    "rubber": ("rubber", ["rubber_obj"], "floor", 20,
               "A black natural rubber surface with a fine matte micro-texture and a faint dusty "
               "bloom (the frame covers 20 x 20 cm).", {}),
    # ---------------- misc
    "kraft_paper": ("paper", ["book"], "props", 30,
                    "Natural brown kraft paper: visible recycled fibres, subtle mottling and fine "
                    "creases (the frame covers 30 x 30 cm).", {}),
    "beeswax": ("wax", ["candle"], "props", 15,
                "A smooth ivory beeswax candle surface: creamy white wax with faint pour lines and "
                "slight translucency (the frame covers 15 x 15 cm).", {}),
    "led_panel": ("emissive", ["led_panel"], "panel", 90,
                  "A glowing opal LED light panel: even warm-white diffused light with a faint grid "
                  "of LED hotspots (the frame covers 90 x 90 cm).", {}),
    "monstera_leaf": ("foliage", ["leaf"], "plant", None,
                      "A single fresh green monstera deliciosa leaf with its natural splits, "
                      "photographed flat from directly above on a pure white seamless background, "
                      "centred with white space around it, even shadowless lighting, sharp vein "
                      "detail. No other objects, no text.", {"maptype": None, "no_common": True}),
    "asphalt": ("asphalt", ["ext_ground"], "ext", 150,
                "Dry weathered asphalt road surface: dark grey bitumen with exposed light grey "
                "aggregate stones 2 to 10 mm and fine cracks (the frame covers 1 x 1 m).", {}),
    "sand": ("sand", ["ext_ground"], "ext", 100,
             "Fine dry beach sand with gentle wind ripples, warm beige quartz grains with "
             "occasional shell fragments (the frame covers 1 x 1 m).", {}),
}


def prompt(mid):
    cls, _, _, _, subject, extra = MATERIALS[mid]
    return subject if extra.get("no_common") else subject + COMMON


# Exact prompts used where the first wording hit a content-moderation false
# positive (words such as "powder", "candy", "acid", "blasted", "curls").
_SAFE = (" Seamless tileable texture photograph. Perfectly flat, top-down orthographic view: "
         "the camera sensor is parallel to the surface, no perspective, no vanishing point. "
         "Even, soft, shadowless studio lighting: no specular highlights, no reflections, no "
         "glare, no vignetting. The material fills the whole frame edge to edge. Ultra-sharp, "
         "true-to-life colour and real-world texture detail. No objects, no text, no watermark, "
         "no border.")
PROMPT_OVERRIDES = {
    "boucle_sofa": "A cream boucle upholstery textile: tiny looped wool yarns form a nubbly, "
                   "knotted, pebble-like surface (the frame covers 20 x 20 cm)." + _SAFE,
    "black_powder_coat": "A matte black painted steel surface with a fine orange-peel coating "
                         "texture, deep charcoal black, satin-matte (the frame covers 20 x 20 cm)."
                         + _SAFE,
    "car_paint_red": "A deep red metallic automotive finish: fine glittering metallic particles in "
                     "a rich ruby red base beneath a smooth glossy clear lacquer (the frame covers "
                     "10 x 10 cm)." + _SAFE,
    "frosted_glass": "A sheet of satin frosted glass on a white background: soft, even, "
                     "translucent matte finish with a very fine uniform texture (the frame covers "
                     "30 x 30 cm)." + _SAFE,
    "matte_plastic": "A matte light-grey moulded plastic surface with a fine sand-textured finish "
                     "(the frame covers 20 x 20 cm)." + _SAFE,
    "velvet_sofa": MATERIALS["velvet_sofa"][4] + _SAFE,
}
_prompt_base = prompt


def prompt(mid):  # noqa: F811  (overrides first)
    return PROMPT_OVERRIDES.get(mid) or _prompt_base(mid)


# ---- extra references for the apartment model (also tested in the lab)
_APT = {
    "white_porcelain": ("ceramic_glazed", ["bowl"], "props", 20,
                        "Smooth white glazed porcelain ceramic surface: bright clean white glaze with "
                        "very faint micro ripples in the glaze (the frame covers 20 x 20 cm)."),
    "white_cotton": ("fabric", ["sofa", "cushion"], "sofa_close", 25,
                     "Crisp white cotton percale bedding fabric: fine tight plain weave with soft "
                     "natural creases (the frame covers 25 x 25 cm)."),
    "paint_white_joinery": ("generic", ["corten"], "corten", 40,
                            "Satin white painted wooden cabinet door surface: smooth sprayed satin paint "
                            "in warm white, extremely fine even texture (the frame covers 40 x 40 cm)."),
    "paint_sage_joinery": ("generic", ["corten"], "corten", 40,
                           "Satin sage-green painted wooden cabinet front surface: smooth sprayed satin "
                           "paint in a soft muted sage green, extremely fine even texture (the frame "
                           "covers 40 x 40 cm)."),
    "oak_board": ("wood_interior", ["table_top"], "table", 60,
                  "A single clear white oak furniture board: straight vertical grain with gentle "
                  "cathedral figure, no joints, no knots, natural matte oil finish, warm light honey "
                  "tone (the frame covers 60 x 60 cm)."),
    # the first image was a whole tray on a white backdrop (albedo ~110 sRGB, a rim)
    "black_plastic": ("plastic_matte", ["rubber_obj"], "floor", 15,
                      "Extreme close-up of a flat matte black moulded ABS plastic panel: a fine, "
                      "uniform stipple-textured finish in deep charcoal black. The plastic surface "
                      "fills the entire frame edge to edge: no object edges, no rim, no tray, no "
                      "background visible (the frame covers 15 x 15 cm)."),
    "black_screen": ("plastic_glossy", ["plastic_obj"], "props", 30,
                     "A glossy deep black glass panel surface, perfectly smooth and uniform, very "
                     "faint dust specks (the frame covers 30 x 30 cm)."),
    "potting_soil": ("sand", ["soil"], "plant", 30,
                     "Dark brown moist potting soil with small bark pieces and a few white perlite "
                     "grains (the frame covers 30 x 30 cm)."),
    "plant_stem": ("generic", ["stem"], "plant", 5,
                   "Close-up of a smooth fresh green plant stem surface laid flat: even mid green with "
                   "very fine lengthwise lines and a faint waxy sheen (the frame covers 5 x 5 cm)."),
    # the apartment's living walls: the greige limewash read as dirty grey-green there
    "limewash_warm": ("concrete", ["wall"], "wall", 150,
                      "A hand-applied limewash plaster wall in warm chalky off-white: soft, subtle "
                      "cloudy brush marks with gentle, low-contrast tonal variation and a matte "
                      "mineral finish (the frame covers 1.5 x 1.5 m)."),
    # second accent velvet: the scatter cushions were all emerald
    "rust_velvet": ("velvet", ["sofa", "cushion"], "sofa", 30,
                    "A burnt rust-orange cotton velvet upholstery textile: short dense even pile with "
                    "a fine, uniform, soft velvety surface and very subtle tonal shading, smooth and "
                    "flat with no wrinkles (the frame covers 30 x 30 cm)."),
    "terracotta_pot": ("terracotta", ["pot"], "plant", 30,
                       "Unglazed terracotta clay plant pot surface: warm orange-brown fired clay with "
                       "faint horizontal throwing lines, tiny pores and a light white mineral bloom "
                       "(the frame covers 30 x 30 cm)."),
}
for _k, (_c, _h, _cam, _t, _s) in _APT.items():
    MATERIALS[_k] = (_c, _h, _cam, _t, _s, {})
    PROMPT_OVERRIDES[_k] = _s + _SAFE

# second rewording (Gemini blocked the first two; Gen-4 returned unusable images)
PROMPT_OVERRIDES["boucle_sofa"] = ("A cream textured wool upholstery fabric with a dense nubby surface of "
                                   "tiny yarn knots and bumps, soft, cosy and slightly fuzzy (the frame "
                                   "covers 20 x 20 cm)." + _SAFE)
PROMPT_OVERRIDES["matte_plastic"] = ("The flat side of a light grey moulded polymer storage box: smooth "
                                     "matte surface with a fine even stippled texture, uniform colour "
                                     "(the frame covers 20 x 20 cm)." + _SAFE)


# ---- art prints for the apartment walls (mapped once on a framed plane)
MATERIALS["art_canvas"] = ("paper", ["book"], "props", 30,
                           "Flat scan of an original abstract minimalist painting on textured canvas: large "
                           "soft organic shapes in warm sand, terracotta and muted olive on an off-white "
                           "ground, visible brush strokes and canvas weave, gallery quality.", {"no_common": True, "no_seamless": True})
MATERIALS["art_paper"] = ("paper", ["book"], "props", 30,
                          "Flat scan of an original minimalist line-and-wash artwork on cotton rag paper: a "
                          "single calm horizon of soft grey-blue watercolour washes with a thin charcoal line, "
                          "lots of warm white paper, subtle paper texture, fine art print quality.", {"no_common": True, "no_seamless": True})
# Gemini blocks plastic wordings; these came from Ideogram P-Image
PROMPT_OVERRIDES["black_plastic"] = ("Seamless texture photo, top-down and perfectly flat: deep "
                                     "charcoal-black matte moulded polymer surface with a fine even "
                                     "stippled grain, uniform colour, soft shadowless lighting, fills the "
                                     "frame edge to edge, no objects, no text.")
PROMPT_OVERRIDES["matte_plastic"] = ("Seamless texture photo, top-down and perfectly flat: light grey matte "
                                     "moulded polymer surface with a fine even stippled grain, uniform "
                                     "colour, soft shadowless lighting, fills the frame edge to edge, no "
                                     "objects, no text.")

# ---- benchmark scene 1 (bright white room): new references, generic material
# descriptions in the lab's own template (2026-11-05)
_BENCH1 = {
    # (the first take, "whitewashed", came out near white with faint grain and
    # rendered flat; this one is amber and the scene's per-board variants
    # pull it back to the reference's pale pine)
    "pine_board": ("wood_floor", ["floor"], "floor", 60,
                   "Natural pale pine floorboard wood with straight grain running vertically from the "
                   "top to the bottom of the frame: warm honey-beige to light amber tones with darker "
                   "growth-ring lines, a few small knots, matte oiled finish, no joints and no gaps (the "
                   "frame covers 60 x 60 cm)."),
    # the reference's floor is old flat-sawn pine: bold cathedral grain and dark
    # knots (pine_board's rift-sawn pinstripes averaged out to flat colour)
    "pine_flatsawn": ("wood_floor_oiled", ["floor"], "floor", 60,
                      "Old flat-sawn Nordic pine floorboard wood with the grain running vertically from "
                      "the top to the bottom of the frame: bold cathedral growth-ring arches with darker "
                      "amber latewood, two or three dark round knots 1.5 to 3 cm across, soap-washed pale "
                      "honey colour with a faint grey cast, matte, one continuous board face, no joints "
                      "and no gaps (the frame covers 60 x 60 cm)."),
    "black_leather": ("leather", ["sofa", "cushion"], "sofa", 40,
                      # (the first take asked for "soft creases" and the photo's fold
                      # highlights ended up baked into the albedo as bright streaks; four
                      # flatter wordings with "black leather" were blocked by the image
                      # model's moderation, Seedream 5 gave a coarse rubbery grain with
                      # white specks; this one is Seedream 5 Pro)
                      "Smooth black nappa leather upholstery surface, close-up material swatch: very "
                      "fine, subtle natural grain and tiny pores, uniform deep black colour, flat and "
                      "smooth with no folds or creases, diffuse even lighting with no highlights (the "
                      "frame covers 40 x 40 cm)."),
    # (the first take rendered as a crisp printed graphic, saturated blue)
    "kilim_rug": ("carpet", ["rug"], "rug", 120,
                  "A vintage hand-woven flat-weave wool kilim rug, faded and sun-washed: a soft slate "
                  "blue-grey ground with large irregular cream and pale grey stepped diamond motifs in "
                  "rows, low contrast, uneven abrash colour bands, visible weft weave and slight wear "
                  "(the frame covers 120 x 120 cm)."),
    # the kilim photo came out crisp and saturated whatever the prompt said; the
    # reference's rug is a heathered hand-woven wool with a few soft motifs
    "melange_rug": ("carpet", ["rug"], "rug", 120,
                    "A modern hand-woven flat-weave wool rug in heathered melange yarns: the ground is "
                    "fine horizontal streaks of charcoal, slate grey, dusty blue-grey, oatmeal and cream "
                    "yarn that vary in density like space-dyed wool, with three large soft-edged cream and "
                    "pale tan elongated hexagon motifs scattered sparsely across it, thick hand-spun yarn "
                    "texture, visible weft rows, matte natural wool (the frame covers 120 x 120 cm)."),
    "sheer_voile": ("fabric_sheer", ["sofa", "cushion"], "sofa_close", 20,
                    "Sheer white linen voile curtain fabric: fine open plain weave with thin irregular "
                    "slub threads (the frame covers 20 x 20 cm)."),
    "matte_stoneware": ("ceramic_matte", ["bowl"], "props", 25,
                        "Matte white stoneware ceramic surface: soft chalky off-white glaze with fine "
                        "dark iron speckles and faint horizontal throwing lines (the frame covers 25 x "
                        "25 cm)."),
    # (the first wording, "plaster wall ... roller stipple", hit a moderation false positive)
    "white_plaster": ("paint_wall", ["wall"], "wall", 150,
                      "A smooth white painted interior wall surface: matte paint with a very fine even "
                      "texture and faint soft tonal variation, clean and unmarked (the frame covers 150 "
                      "x 150 cm)."),
    "waxed_canvas": ("fabric", ["sofa", "cushion"], "sofa_close", 25,
                     "Tan waxed cotton canvas fabric: tight plain weave, soft creases and slightly "
                     "darker waxed patches (the frame covers 25 x 25 cm)."),
    # waxed_canvas asked for creases and blotches: they baked into the albedo
    # and the tote read as cork
    "waxed_canvas_flat": ("canvas_waxed", ["sofa", "cushion"], "sofa_close", 25,
                          "Muted olive-tan waxed cotton canvas fabric: a tight plain weave, flat and uniform "
                          "with faint waxy tone variation, matte with a subtle soft waxy lustre, no creases "
                          "and no folds (the frame covers 25 x 25 cm)."),
    # the rug's woven end bands and fringe (the white bedding cotton read as a
    # bright comb)
    "ecru_cotton": ("fabric", ["sofa", "cushion"], "sofa_close", 15,
                    "Undyed ecru cotton yarn in a tight hand-woven plain weave: natural off-white with a "
                    "faint warm grey cast, slightly irregular thick and thin threads, soft matte fibres, "
                    "laid perfectly flat (the frame covers 15 x 15 cm)."),
}
for _k, (_c, _h, _cam, _t, _s) in _BENCH1.items():
    MATERIALS[_k] = (_c, _h, _cam, _t, _s, {})
    PROMPT_OVERRIDES[_k] = _s + _SAFE
MATERIALS["strelitzia_leaf"] = ("foliage", ["leaf"], "plant", None,
                                "A single large fresh green bird of paradise plant leaf, long paddle "
                                "shape with a pale central midrib, fine parallel side veins and a few "
                                "natural tears along the edge, photographed flat from directly above on "
                                "a pure white seamless background, centred with white space around it, "
                                "even shadowless lighting, sharp vein detail. No other objects, no text.",
                                {"maptype": None, "no_common": True})
# the first leaf photos were bright lime blades exposed for a white backdrop:
# inside the cut-out the strelitzia read lum 0.42 and the rubber leaf 0.23,
# 3-5x a real leaf, and rendered neon against the reference's dark foliage.
# These are dark waxy leaves on a mid-grey card, exposed for the leaf.
MATERIALS["strelitzia_dark"] = ("foliage_thick", ["leaf"], "plant", None,
                                "A single mature bird of paradise (Strelitzia) plant leaf, deep dark green "
                                "and waxy with a soft satin sheen, long paddle shape with a paler olive "
                                "central midrib, fine parallel side veins and two or three natural splits "
                                "along the edge, photographed flat from directly above on a plain "
                                "medium-grey card, exposed for the leaf, the leaf running from the bottom "
                                "centre of the frame to the top with grey space all around it, even soft "
                                "shadowless light, no hotspots, no reflections, sharp vein detail. No other "
                                "objects, no text.",
                                {"maptype": None, "no_common": True})
MATERIALS["rubber_dark"] = ("foliage_thick", ["leaf"], "plant", None,
                            "A single glossy dark olive-green rubber plant leaf (Ficus elastica): thick smooth "
                            "oval blade with a short pointed tip, a pale central midrib running straight up "
                            "from the short leaf stalk at the bottom of the frame to the tip at the top, faint "
                            "side veins, natural subtle colour variation, photographed flat from directly "
                            "above on a plain medium-grey card, exposed for the leaf, centred and upright with "
                            "grey space all around it, even soft shadowless light, no hotspots, no "
                            "reflections, sharp detail. No other objects, no text.",
                            {"maptype": None, "no_common": True})
# ---- benchmark 2 (moody contemporary: copper plaster, black marble, olive tree)
_BENCH2 = {
    # (the first take came out orange, albedo r/g 2.42 b/g 0.50: the reference's copper
    # reads about 1.9 / 0.7 against its ceiling; this one forges to 2.02 / 0.64)
    "copper_plaster": ("concrete_polished", ["wall"], "wall", 200,
                       "A hand-troweled metallic Venetian plaster wall in muted burnt copper and warm "
                       "clay-brown tones: a soft brown base with a copper sheen, burnished satin finish, "
                       "cloudy overlapping trowel strokes, scattered fine pale-gold metallic flecks and "
                       "thin crackle veins, subdued and earthy rather than orange (the frame covers 2 x "
                       "2 m)."),
    "grey_microcement": ("concrete_polished", ["wall"], "wall", 200,
                         "A hand-troweled grey microcement wall: soft cloudy mid-grey and warm grey "
                         "trowel marks with faint darker flecks and a matte-satin finish (the frame "
                         "covers 2 x 2 m)."),
    "nero_marquina": ("marble", ["table_top"], "table", 100,
                      "A polished Nero Marquina black marble slab: deep jet-black stone with crisp "
                      "white veins and a fine web of thin white crackle lines (the frame covers 1 x "
                      "1 m)."),
    "grey_loop_rug": ("carpet", ["rug"], "rug", 60,
                      "A dense hand-loomed wool loop-pile rug in charcoal and warm grey: tight rows of "
                      "small looped yarns forming a fine ribbed texture with heathered black, grey "
                      "and taupe flecks (the frame covers 60 x 60 cm)."),
    "beige_chenille": ("fabric", ["sofa", "cushion"], "sofa", 25,
                       "A warm sand-beige chenille upholstery fabric: soft nubby woven texture of "
                       "thick fuzzy yarns with subtle tonal flecks (the frame covers 25 x 25 cm)."),
    "taupe_lacquer": ("plastic_matte", ["table_top", "plastic_obj"], "table", 100,
                      "A smooth matte taupe-beige lacquered joinery panel: fine even satin-matte "
                      "paint finish over smooth wood, faint brush-free surface (the frame covers 1 x "
                      "1 m)."),
}
# ---- benchmark 3 (curved boucle sofa, tapestry, onyx, alabaster)
_BENCH3 = {
    # the coffee tables' legs and pedestals (benchmarks 2 and 3): the named metal
    # "bronze" on the brass photo rendered as polished gold (its F0 is as bright as
    # brass); this photo's own dark albedo is the base colour (no named metal)
    "dark_bronze": ("metal_brushed", ["metal_obj", "table_leg", "lamp"], "props", 25,
                    "A dark patinated bronze metal surface: deep chocolate-brown to blackened bronze "
                    "with a fine directional brushed grain running horizontally, faint warm coppery "
                    "glints along the grain, a soft satin finish and slightly uneven darker patina "
                    "mottling (the frame covers 25 x 25 cm)."),
    "green_onyx": ("marble", ["table_top"], "table", 100,
                   "A polished green onyx marble slab: banded translucent layers of sage green, "
                   "grey-green and cream with soft white streaks and darker moss veins (the frame "
                   "covers 1 x 1 m)."),
    "alabaster": ("marble", ["bowl", "vase"], "props", 40,
                  "A honed slab of white alabaster stone: milky translucent white with soft cloudy "
                  "cream and pale grey veining, smooth waxy surface (the frame covers 40 x 40 cm)."),
    "striped_rug": ("carpet", ["rug"], "rug", 60,
                    "A low-pile hand-woven wool rug in pale grey and greige with fine horizontal "
                    "ribbed stripes of slightly different tones, soft fibres (the frame covers 60 x "
                    "60 cm)."),
    "slate_velvet": ("velvet", ["sofa", "cushion"], "sofa", 30,
                     "A slate-blue cotton velvet upholstery textile: short dense even pile with a "
                     "fine, uniform, soft velvety surface and very subtle tonal shading (the frame "
                     "covers 30 x 30 cm)."),
    "limestone_floor": ("stone_honed", ["floor"], "floor", 180,
                        "A honed light beige limestone slab: soft cream and pale sand tones with faint tiny "
                        "fossil flecks and subtle cloudy variation, smooth matte stone surface (the frame "
                        "covers 180 x 180 cm)."),
    "knit_stripe": ("fabric", ["sofa", "cushion"], "sofa_close", 30,
                    "A chunky knitted wool upholstery fabric in grey and charcoal horizontal stripes: "
                    "plump knit stitches in neat rows, soft fuzzy yarn (the frame covers 30 x 30 "
                    "cm)."),
}
for _k, (_c, _h, _cam, _t, _s) in list(_BENCH2.items()) + list(_BENCH3.items()):
    MATERIALS[_k] = (_c, _h, _cam, _t, _s, {})
    PROMPT_OVERRIDES[_k] = _s + _SAFE
# original artwork and plant cards (no tiling)
MATERIALS["tapestry_art"] = ("carpet", ["rug"], "rug", 240,
                             "A large hand-tufted wool wall tapestry, an original abstract composition: "
                             "sweeping organic shapes like giant leaves, roots and feathers in charcoal "
                             "black, rust, burnt ochre, sage grey-green and cream, with areas of cut "
                             "pile and loop pile at different heights and visible yarn tufts, "
                             "photographed flat and straight-on under even soft light, the artwork "
                             "fills the whole frame edge to edge. No frame, no wall, no text.",
                             {"no_common": True, "no_seamless": True})
MATERIALS["olive_sprig"] = ("foliage", ["leaf"], "plant", None,
                            "A single small olive tree sprig: a thin grey-brown twig carrying about "
                            "twenty narrow lance-shaped silvery grey-green leaves, photographed flat "
                            "from directly above on a pure white seamless background, the twig "
                            "running from the bottom centre of the frame to the top, white space "
                            "around it, even shadowless lighting, sharp detail. No other objects, no "
                            "text.",
                            {"maptype": None, "no_common": True})
MATERIALS["yellow_blossom"] = ("foliage", ["leaf"], "plant", None,
                               "A single small flowering branch tip: clusters of tiny golden-yellow "
                               "blossoms and a few small green leaves on a thin brown twig, "
                               "photographed flat from directly above on a pure white seamless "
                               "background, the twig running from the bottom centre of the frame to "
                               "the top, white space around it, even shadowless lighting, sharp "
                               "detail. No other objects, no text.",
                               {"maptype": None, "no_common": True})
# the bushy plant's smaller leaves (12-25 cm): a banana leaf shrunk to that size
# read as a miniature banana with its tears
MATERIALS["rubber_leaf"] = ("foliage", ["leaf"], "plant", None,
                            "A single glossy dark green rubber plant leaf (Ficus elastica): smooth oval "
                            "blade with a short pointed tip, a pale central midrib running straight up "
                            "from the short leaf stalk at the bottom of the frame to the tip at the top, "
                            "fine faint side veins, natural subtle colour variation, photographed flat "
                            "from directly above on a pure white seamless background, centred and upright "
                            "with white space all around it, even shadowless lighting, sharp detail. No "
                            "other objects, no text.",
                            {"maptype": None, "no_common": True})

# The audit of 2026-11-11: these references asked for creases (their fold shading baked into the
# albedo) or came out off-colour (oak more orange than oak is); flat, neutral photos replace them.
PROMPT_OVERRIDES['leather_sofa'] = ('A cognac-brown full-grain aniline leather hide: natural fine pebble grain pores and soft tonal variation, stretched perfectly flat and smooth, no creases, no folds, no wrinkles (the frame covers 40 x 40 cm).'
    + _SAFE)
PROMPT_OVERRIDES['kraft_paper'] = ('Natural brown kraft paper: visible recycled fibres and subtle mottling, lying perfectly flat and smooth, no creases, no folds, no wrinkles (the frame covers 30 x 30 cm).'
    + _SAFE)
PROMPT_OVERRIDES['white_cotton'] = ('White cotton percale bedding fabric: a fine tight plain weave with clearly visible individual threads, soft natural off-white, ironed perfectly flat and smooth, no creases, no folds, no wrinkles, exposed light grey-white and not blown out (the frame covers 25 x 25 cm).'
    + _SAFE)
PROMPT_OVERRIDES['oak_board'] = ('A single clear European white oak furniture board: straight vertical grain with gentle cathedral figure and fine open pores, no joints, no knots, natural matte oil finish, pale neutral straw-beige colour with a slightly greyish cast, not orange, not yellow (the frame covers 60 x 60 cm).'
    + _SAFE)

# A warm honey oak beside the pale oak_board (benchmark 3's fluted panelling is a
# honey-brown oak; the first oak photo, replaced above for being too orange for
# pale furniture oak, is right for it).
MATERIALS["oak_honey"] = ("wood_interior", ["table_top"], "table", 60,
                          "A single clear white oak furniture board: straight vertical grain with gentle "
                          "cathedral figure, no joints, no knots, natural matte oil finish, warm light honey "
                          "tone (the frame covers 60 x 60 cm).", {})
PROMPT_OVERRIDES["oak_honey"] = MATERIALS["oak_honey"][4] + _SAFE
PROMPT_OVERRIDES["plant_stem"] = ("The skin of one thick green plant stalk laid open and flat as a continuous surface: "
                                  "smooth waxy mid-green with fine straight vertical fibre lines, faint paler and darker "
                                  "green streaks and a few tiny brown flecks, one uniform surface with no separate "
                                  "stems, no gaps and no ridges (the frame covers 10 x 10 cm)." + _SAFE)

# Woody trunks and twigs (the olive and the flowering tree of benchmarks 2 and 3
# carried the green stalk material on their trunks).
MATERIALS["tree_bark"] = ("wood_exterior", ["table_leg"], "props", 15,
                          "The bark of a young olive tree trunk as a continuous flat surface: smooth to lightly "
                          "fissured grey-brown bark with fine vertical cracks, small lenticels and faint "
                          "silvery-grey and warm brown patches, matte, uniform, no branches and no leaves (the "
                          "frame covers 15 x 15 cm).", {})
PROMPT_OVERRIDES["tree_bark"] = MATERIALS["tree_bark"][4] + _SAFE

