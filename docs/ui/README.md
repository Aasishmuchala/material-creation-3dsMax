# UI state gallery

Screenshots of every state of the two native Qt docks (MatForge and Material Inspector),
rendered headlessly so a change to the look can be reviewed without opening 3ds Max.

## Regenerate

From the repo root:

    .venv-qt/bin/python tools/ui_screens.py

It prints `wrote 45 screens` and exits 0. It exits 1 if any state raises or any PNG is
larger than 80 KB. The script clears and rewrites `docs/ui/screens/*.png` and
`docs/ui/screens/index.md`. Nothing is hand-tuned, so a layout change shows up as a diff
on the next run.

States: 8 MatForge (idle, loaded, loaded_more, working, done, done_miss, error_nokey,
settings) and 7 Inspector (idle, scanning, results, results_why, empty, error, fixed), each
at widths 320, 400 and 560 px and height 700 px. File names are
`<panel>_<state>_<width>.png`. `screens/index.md` lists them all.

The renders use the Max-dark token set (the offscreen palette is light, so the kit falls
back to its dark defaults). The Inspector "empty" screen comes from a scene with no
materials, so its second line reads "No materials found in this scene."

## What to look for

Check each screenshot, especially the 320 px column, against the ten hard rules:

- [ ] 1. Native Qt only: no web view, no HTML look; one compat module for PySide6 and PySide2.
- [ ] 2. Both docks come from the shared kit `forgeui/`; no private one-off widgets that drift in look.
- [ ] 3. Exactly one accent (`#5FB89A`). Semantic colours are chip fills with dark text and always carry a word ("Error", "Warning", "Fixed", "Done"). No glows, gradients, pure black or pure white.
- [ ] 4. Radius 4 px everywhere, spacing on 4/8/12/16/24/32 only, 1 px hairline borders, no drop shadows.
- [ ] 5. Host UI font, title 15 px bold, body 13 px, secondary 11 px muted. Monospace only for file paths.
- [ ] 6. Plain English, verbs first, no jargon on the first screen. No em-dashes or en-dashes. No "Step 1". Rule ids appear only as small muted text. Every finding headline says what will look wrong and what the fix does.
- [ ] 7. Every screen has a clear idle, loading, empty, error and success state. Loading shows skeleton rows, a phase sentence and Cancel, never a bare spinner. Errors are inline with one recovery action.
- [ ] 8. Controls look at least 28 px tall, the primary button 44 px, and the focus ring is a 2 px accent border.
- [ ] 9. Exactly one primary button per screen, labels of three words or fewer, nothing wraps or clips at 320 px.
- [ ] 10. No motion in the stills; hover and pressed states live in QSS only and the skeleton pulse is off.
