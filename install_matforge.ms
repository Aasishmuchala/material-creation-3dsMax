/*  MatForge installer — run ONCE (Scripting > Run Script).
    Registers persistent MatForge actions, sets the IE emulation the web panel
    needs, and opens the panel. Re-running is safe.

    Note: on 3ds Max 2025+ the classic menuMan main-menu API is a no-op (Qt
    menus), so we don't rely on it. Add the button yourself once via
    Customize > Customize User Interface > Toolbars, category "MatForge" — or
    just re-run this script / this line to open the panel again:
        fileIn @"C:\Users\aasis\matforge\matforge_panel.ms"                    */

global MatForgePanel  = @"C:\Users\aasis\matforge\matforge_panel.ms"
global MatForgeSimple = @"C:\Users\aasis\matforge\run_matforge.py"

-- premium dark web panel (Create / Settings / Help chat)
macroScript MatForge_Open
    category:"MatForge"
    toolTip:"MatForge — reference image to V-Ray material (panel)"
    buttonText:"MatForge"
(
    on execute do (
        if (doesFileExist MatForgePanel) then fileIn MatForgePanel
        else messageBox ("Not found:\n" + MatForgePanel) title:"MatForge"
    )
)

-- reliable fallback rollout (if the embedded browser won't render on your box)
macroScript MatForge_Simple
    category:"MatForge"
    toolTip:"MatForge — simple rollout (fallback)"
    buttonText:"MatForge (simple)"
(
    on execute do (
        if (doesFileExist MatForgeSimple) then python.ExecuteFile MatForgeSimple
        else messageBox ("Not found:\n" + MatForgeSimple) title:"MatForge"
    )
)

-- set the IE11 emulation the WebBrowser control needs, then open the panel
try (
    python.Execute "import sys; repo=r'C:\\Users\\aasis\\matforge'; (repo in sys.path) or sys.path.insert(0,repo)"
    python.Execute "import maxplugin.forge_max as fm; fm.set_ie_emulation()"
) catch()

messageBox ("MatForge installed.\n\n" + \
    "Actions registered under Customize > Toolbars, category 'MatForge':\n" + \
    "  • MatForge          (the panel)\n" + \
    "  • MatForge (simple)  (fallback rollout)\n\n" + \
    "Drag either onto a toolbar for one-click access.\n" + \
    "Opening the panel now...") title:"MatForge"

if (doesFileExist MatForgePanel) do fileIn MatForgePanel
