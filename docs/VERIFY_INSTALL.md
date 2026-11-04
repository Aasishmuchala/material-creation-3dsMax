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
| 3 | `getThisScriptFilename()` in a fileIn'd script | Scripting > Run Script > `install_matforge.ms`; then the **MatForge panel** / **diagnose** buttons | `MatForgeRoot` in the Listener = the folder, no trailing `\`; panel HTML loads |
| 4 | Macros generated via `execute` are serialized to usermacros | After the installer, open `%LOCALAPPDATA%\Autodesk\3dsMax\<ver>\ENU\usermacros\MatForge-MatForge_Open.mcr` | Contains `@"<root>\run_matforge.py"` as a literal; restart Max, button still works |
| 5 | Run-from-repo after a move | Move the folder, re-run `install_matforge.ms` | Buttons point at the new folder (old `.mcr` overwritten) |
| 6 | Bundle loads on 2022 → 2027 | `python tools/build_matforge_bundle.py`; copy `dist\MatForge.bundle` to `%ProgramData%\Autodesk\ApplicationPlugins\`; restart | Listener shows no `[MatForge] startup:` error; Toolbars category **MatForge** has 3 actions pointing at `...\MatForge.bundle\Contents\scripts` |
| 7 | `post-start-up scripts parts` timing | On each version, right after start, click **MatForge** | Rollout opens; Python available when the startup script ran |
| 8 | Bundle + old repo install side by side | Install via repo, then add the bundle, restart | Bundle startup re-registers the same macro names → buttons point at the bundle |
| 9 | Keys on a bundle install | Settings tab → save a dummy fal key | Written to `%APPDATA%\MatForge\_keys.json` (ProgramData stays untouched); diagnose shows key set |
| 10 | Keys run-from-repo | With an existing `<repo>\_keys.json`, save again | That file is updated (folder-local wins when present) |
| 11 | Map generation from the bundle | Create (Fast) from a reference outside the bundle | `forge_cli.py` runs from `Contents\scripts` under system Python; maps land in `<image dir>\<name>_maps` |

Known limits: running `install_matforge.ms` from an unsaved editor tab ("Evaluate All") has no file name,
so `getThisScriptFilename()` is `undefined` and the installer throws; save it / run it from disk.
