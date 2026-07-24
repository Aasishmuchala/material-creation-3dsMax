/*  MatForge installer - run ONCE (Scripting > Run Script).
    Registers the MatForge actions, prepares the panel's browser registry
    flags, and opens the plugin. Re-running is safe.

    The ROLLOUT ("MatForge") is the reliable native UI and is what opens by
    default -- pure MAXScript, no browser, works on Max 2022-2027 / any Windows.
    The web PANEL ("MatForge panel") is the fancy dark UI; it needs the embedded
    IE WebBrowser, which is unreliable on some Windows 11 setups. Use the panel
    once the diagnostic passes and the panel renders on your box.

    Note: on 3ds Max 2025+ the classic menuMan main-menu API is a no-op (Qt
    menus), so actions live under Customize > Toolbars, category "MatForge".   */

global MatForgeSimple   = @"C:\Users\aasis\matforge\run_matforge.py"
global MatForgePanel    = @"C:\Users\aasis\matforge\matforge_panel.ms"
global MatForgeDiagnose = @"C:\Users\aasis\matforge\matforge_diagnose.ms"

-- NOTE: each macro bakes its path as a LITERAL @"..." inside `on execute do`.
-- 3ds Max serializes these macros to ...\usermacros\MatForge-*.mcr and reloads
-- them on every startup, but it does NOT save the `global X = @"..."` lines
-- above -- only the handler body. Referencing a session global here would be
-- `undefined` after the next restart and `doesFileExist undefined` THROWS
-- (-- Unable to convert: undefined to type: String). Literals survive the round
-- trip, so the toolbar buttons keep working across restarts.

-- reliable native rollout (RECOMMENDED default)
macroScript MatForge_Open
    category:"MatForge"
    toolTip:"MatForge - reference image to V-Ray material"
    buttonText:"MatForge"
(
    on execute do (
        local p = @"C:\Users\aasis\matforge\run_matforge.py"
        if (doesFileExist p) then python.ExecuteFile p
        else messageBox ("Not found:\n" + p) title:"MatForge"
    )
)

-- fancy dark web panel (Create / Settings / Help chat) -- needs the webview
macroScript MatForge_Panel
    category:"MatForge"
    toolTip:"MatForge - dark web panel (needs the embedded browser)"
    buttonText:"MatForge panel"
(
    on execute do (
        local p = @"C:\Users\aasis\matforge\matforge_panel.ms"
        if (doesFileExist p) then fileIn p
        else messageBox ("Not found:\n" + p) title:"MatForge"
    )
)

-- layer-by-layer self-test (run this if anything looks broken)
macroScript MatForge_Diagnose
    category:"MatForge"
    toolTip:"MatForge - self-test / diagnostic"
    buttonText:"MatForge diagnose"
(
    on execute do (
        local p = @"C:\Users\aasis\matforge\matforge_diagnose.ms"
        if (doesFileExist p) then fileIn p
        else messageBox ("Not found:\n" + p) title:"MatForge"
    )
)

-- prepare the WebBrowser registry flags the panel needs (IE11 mode + unlock
-- local-file JavaScript). Harmless if you only ever use the rollout.
try (
    python.Execute "import sys; repo=r'C:\\Users\\aasis\\matforge'; (repo in sys.path) or sys.path.insert(0,repo)"
    python.Execute "import maxplugin.forge_max as fm; fm.set_ie_emulation()"
) catch()

-- build the message piecewise (no '\' line-continuations -- those are flaky
-- with CRLF files and are a classic MAXScript syntax-error source)
local msg = "MatForge installed  (works on 3ds Max 2022-2027).\n\n"
msg += "Actions under Customize > Toolbars, category 'MatForge':\n"
msg += "  * MatForge           native rollout - START HERE (always works)\n"
msg += "  * MatForge panel      dark web UI (Create / Settings / Help)\n"
msg += "  * MatForge diagnose   self-test if anything looks broken\n\n"
msg += "Drag any of them onto a toolbar for one-click access.\n"
msg += "Opening the native rollout now..."
messageBox msg title:"MatForge"

-- open the RELIABLE rollout by default so you have a working UI immediately;
-- if anything throws, show the ACTUAL error (don't fail silently)
try ( python.ExecuteFile MatForgeSimple )
catch (
    local em = "The rollout hit an error while opening:\n\n"
    em += (getCurrentException())
    em += "\n\nPlease send me that text. Meanwhile run the self-test:\n"
    em += "  Scripting > Run Script > matforge_diagnose.ms"
    messageBox em title:"MatForge - error"
)
