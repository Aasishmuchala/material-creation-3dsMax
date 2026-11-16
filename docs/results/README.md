# Realism pass: tests and results

State of the `feat/runway-realism-pass` branch on 2026-11-16.

## Tests

`py -3.12 -m pytest tests -q` on Windows 11, Python 3.12:
**1268 passed, 4 skipped** in 5 min 36 s. Full output: [test_results.txt](test_results.txt).

The four skips need things this machine does not have (PySide6 outside 3ds Max,
CPython 3.8).

## Close-up swatches

Every library material on the same set: a ball on a slab at real-world scale,
one metered exposure, 3ds Max 2026 + V-Ray 7. All textures are Runway photos
forged by MatForge. Rendered after the last forge change.

- [swatches_library_1.jpg](swatches_library_1.jpg), [2](swatches_library_2.jpg), [3](swatches_library_3.jpg): the whole library (90 materials).
- [swatches_fixed_eight.jpg](swatches_fixed_eight.jpg): the materials this round fixed
  (three velvets, loop rug, amethyst, boucle, linen, wool rug).

Regenerate with `py -3.12 tools/realism_lab/swatch_run.py --tag <name>`.

## What this round changed

- **Crease at every repeat** (velvet, boucle, plaster): a uniform texture now
  tiles by running its end on into its start instead of bending the borders to
  meet. A photo's own border (off-tone last rows, an edge glow) is trimmed first.
- **Seam lines in weaves and loop pile**: the photo is cut where the weave runs
  on into itself, found by matching the start strip further on, so drifting rows
  still meet in step.
- **Uneven texture strength** across a tile is levelled for uniform classes.
- **Velvet looked like felt**: the albedo sits in a view falloff, dark looking
  down the pile and lighter across it, in any light.
- **Amethyst turned bright blue when thick**: a coloured transparent body now
  absorbs a little in its strongest channel too and keeps a two-channel hue, so
  a thick stone goes dark purple.

## Benchmark rooms

[benchmark1.jpg](benchmark1.jpg), [benchmark2.jpg](benchmark2.jpg),
[benchmark3.jpg](benchmark3.jpg): own compositions in the style of three
reference photos. These renders predate this round's forge changes and have
not been re-rendered since.

## Known gaps

- White cotton is a fine sheet cotton: right at room scale, plain close up.
- Benchmarks 1 and 3 are brighter and lower in contrast than their references.
- The two street backdrop photos the benchmark scenes use are not in the
  repository (51 MB); the scenes need them under `tools/apartment/assets/`.
