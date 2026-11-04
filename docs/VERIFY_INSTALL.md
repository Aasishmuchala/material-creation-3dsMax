# Verify on-box: MatForge install paths and the ApplicationPlugins bundle

**Status: NOTHING here is verified inside 3ds Max.** Path resolution is covered on macOS/Linux only by
`tests/test_packaging.py` (bundle layout, PackageContents.xml, no secrets/user paths, Python 3.7 syntax,
`run_matforge._find_root` without `__file__`, `_keys.json` fallback). The MAXScript side has never run.

Use a Windows user that is **not** the original dev account, and a folder whose path contains a space
(e.g. `D:\Tools\Mat Forge\`), so a leftover user-specific path or a quoting bug shows up.

| # | Check | How | Expected |
|---|---|---|---|
| 1 | `__file__` under `python.ExecuteFile` (Max 2022 / Py3.7, 2024, 2026/2027) | Listener: `python.Execute "globals().pop('__file__', None)"`, then `python.ExecuteFile @"<root>\run_matforge.py"` with a `print(repr(globals().get('__file__')))` temporarily added at the top | Either the real path or `None`; both must open the rollout (fallback = `MatForgeRoot` global) |
| 2 | Stale `__file__` | Run any other `.py` from a different folder via `python.ExecuteFile`, then the MatForge toolbar button | Rollout opens (candidates are validated by `maxplugin/forge_max.py` existing) |
| 3 | `getThisScriptFilename()` in a fileIn'd script | Scripting > Run Script > `install_matforge.ms`; then the **MatForge** / **MatForge diagnose** buttons | `MatForgeRoot` in the Listener = the folder, no trailing `\`; diagnose dialog opens |
| 4 | Macros generated via `execute` are serialized to usermacros | After the installer, open `%LOCALAPPDATA%\Autodesk\3dsMax\<ver>\ENU\usermacros\MatForge-MatForge_Open.mcr` | Contains `@"<root>\run_matforge.py"` as a literal; restart Max, button still works |
| 5 | Run-from-repo after a move | Move the folder, re-run `install_matforge.ms` | Buttons point at the new folder (old `.mcr` overwritten) |
| 6 | Bundle loads on 2022 → 2027 | `python tools/build_matforge_bundle.py`; copy `dist\MatForge.bundle` to `%ProgramData%\Autodesk\ApplicationPlugins\`; restart | Listener shows no `[MatForge] startup:` error; Toolbars category **MatForge** has 3 actions pointing at `...\MatForge.bundle\Contents\scripts` |
| 7 | `post-start-up scripts parts` timing | On each version, right after start, click **MatForge** | Rollout opens; Python available when the startup script ran |
| 8 | Bundle + old repo install side by side | Install via repo, then add the bundle, restart | Bundle startup re-registers the same macro names → buttons point at the bundle |
| 9 | Keys on a bundle install | Settings tab → save a dummy fal key | Written to `%APPDATA%\MatForge\_keys.json` (ProgramData stays untouched); diagnose shows key set |
| 10 | Keys run-from-repo | With an existing `<repo>\_keys.json`, save again | That file is updated (folder-local wins when present) |
| 11 | Map generation from the bundle | Create (Fast) from a reference outside the bundle | `forge_cli.py` runs from `Contents\scripts` under system Python; maps land in `<image dir>\<name>_maps` |
| 12 | Qt dock opens on Max 2025/2026 | Toolbar button `MatForge` | The MatForge dock appears on the right; drop a photo and it shows the type tiles and **Make material** |
| 13 | PySide2 path on Max 2022-2024 | Toolbar button `MatForge` | The dock opens, or the classic rollout opens and the Listener shows `[MatForge] Qt dock unavailable` |
| 14 | QProcess from 3dsmax.exe | Press **Make material** and move the viewport while it runs | No console window appears and Max stays responsive until the Done screen |
| 15 | Cancel kills the child | Press **Make material** with Best, then **Cancel** | `tasklist \| findstr python` shows no leftover python process |
| 16 | `FAL_KEY` stays private | Run Best once, then search the Listener output and `<name>_maps\manifest.json` | The key text appears in neither |
| 17 | Dock is dark inside Max | Open the dock docked, then float it (drag the title bar) | Surfaces stay Max-dark in both; if the dock turns light, `qtmax.GetQMaxMainWindow()` failed and `qss.apply` ran on the app palette |
| 18 | Enter and Esc in a docked vs floating dock | Docked: load a photo, Tab to Name, press Enter; floating: same; while working press Esc | Enter starts Make material in both; Esc cancels in both (shortcut context depends on the active window) |
| 19 | PySide2 (Max 2022-2024) widget construction | Open the dock on Max 2022 | No `TypeError` about multiple inheritance from shiboken2 (`forgeui/widgets.py` lists the Python mixin before the Qt base); tiles, segments and the drop zone render |
| 20 | First click freeze | Fresh Max session, press **Make material** once | The working page appears within a few seconds; if it takes 20 s or more, `_python()` is probing missing interpreters (up to 4 x 20 s) and needs a cached result |
| 21 | Closing Max mid-build | Press **Make material**, then close Max while the working page shows | The child python process is gone afterwards (`tasklist \| findstr python`) |
| 22 | Max's embedded Python does not leak into the child | Press **Make material** (Standard) | `forge_cli.py` imports the SYSTEM numpy and Pillow; if it fails with an import error, `PYTHONHOME`/`PYTHONPATH` from Max reached the child and must be cleared in `build_command` |

Known limits: running `install_matforge.ms` from an unsaved editor tab ("Evaluate All") has no file name,
so `getThisScriptFilename()` is `undefined` and the installer throws; save it / run it from disk.

A `"` in the install path would close the `@"..."` verbatim literal that `matforge_macros.ms` writes into the persisted macroScript (STRESS-D13); NTFS forbids `"` in file and folder names, so this cannot happen on Windows and no code guard is needed.
