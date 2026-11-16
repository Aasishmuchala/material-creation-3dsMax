# PATINA endpoints on fal (verified against fal docs)

Fetched 2026-11-04 via WebFetch (summaries of the pages, not raw OpenAPI JSON).

Sources:
- https://fal.ai/models/fal-ai/patina/material/extract
- https://fal.ai/models/fal-ai/patina/material
- https://fal.ai/models/fal-ai/patina/material/extract/api
- https://blog.fal.ai/introducing-patina

## fal-ai/patina/material/extract  (MatForge default, `--mode extract`)

Input: `prompt` (string, REQUIRED; which texture to extract, e.g. "the wall"),
`image_url` (string, REQUIRED), `image_size` (enum `square_hd` default / `square` /
`portrait_4_3` / `portrait_16_9` / `landscape_4_3` / `landscape_16_9`, or
`{width,height}`), `num_inference_steps` (int 1-8, default 8), `seed`, `num_images`
(1-4, default 1), `strength` (float; page says 0.75, /api tab says 0.6 - unresolved),
`enable_prompt_expansion` (bool, default true, adds ~$0.0025), `enable_safety_checker`
(default true), `tiling_mode` (`both`|`horizontal`|`vertical`, default both),
`tile_size` (32-256, default 128), `tile_stride` (16-128, default 64), `maps`
(subset of basecolor/normal/roughness/metalness/height, default all five),
`upscale_factor` (0|2|4, default 0; SeedVR seamless), `output_format`
(jpeg|png|webp, default png).

So the extract schema DOES have `upscale_factor`; MatForge passes it.

Output: `images` (list), `seed` (int), `prompt` (str), `timings` (object, optional).
Item 0 has no `map_type` (the flat seamless extracted texture); the rest are
`MapImageFile` with `map_type` in {basecolor, height, normal, roughness, metalness}.
Item fields: `url` (required); `content_type`, `file_name`, `file_size`, `width`,
`height` are optional (the /api tab lists them as optional, the model page omits
them) - forge_fal.py falls back to reading the PNG header.

Price: $0.10 per call + $0.02/MP + $0.01/MP per map type; upscaling adds
$0.004 (2x) or $0.016 (4x) per pre-upscale MP per map. 1024x1024 with 5 maps, no
upscale = $0.17.

## fal-ai/patina/material  (`--mode generate`)

Same fields as above except: only `prompt` is required; adds optional `image_url`
(image-to-image) and `mask_url` (needs `image_url`; the page text also says
`mask_image_url` - inconsistent, unverified; MatForge does not use it). Output
shape identical. Price: $0.01 per call + $0.02/MP + $0.01/MP per map; 1024x1024
with 5 maps = $0.08; 2048x2048 with 5 maps and 4x upscale = $0.61.

## Commercial use

Both pages show only a "Commercial use" label; no licence or terms wording is on
the pages, and the blog post does not address licensing (it notes the training data
came from "CC0 material libraries", which describes inputs, not output terms). The
binding terms are fal's Terms of Service (https://fal.ai/legal/terms-of-service),
NOT read here. Treat commercial use as "labelled yes, terms unread" until checked.

## Blog notes

Blog describes extract as taking "an image and a simple label for the texture you
want", flattening, de-occluding, tiling, upscaling and returning a full material set.
Material endpoint quoted "up to 8K"; no extract resolution given.

## Open items

- `strength` default conflict (0.75 vs 0.6) - check live OpenAPI at
  https://fal.run/openapi/fal-ai/patina/material/extract/openapi.json (not fetched).
- No paid call has been made; `fal_patina_probe.py` now calls both endpoints for the
  first live run.
