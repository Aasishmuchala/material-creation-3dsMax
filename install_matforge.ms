/*  MatForge installer — run ONCE (Scripting > Run Script).
    Registers a persistent MatForge action + adds it to the main menu, so
    afterwards you just click Menu > MatForge (or drag the button from
    Customize > Toolbars, category "MatForge"). Re-running is safe.       */

global MatForgePanel  = @"C:\Users\aasis\matforge\matforge_panel.ms"
global MatForgeSimple = @"C:\Users\aasis\matforge\run_matforge.py"

-- premium dark web panel (the DaVinci-style UI)
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

-- reliable fallback rollout (if the web panel doesn't render on your box)
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

-- add a "MatForge" item to the main menu bar (idempotent)
try (
    local mm = menuMan.getMainMenuBar()
    local existing = mm.getItem 1
    local already = false
    for i = 1 to mm.numItems() do (
        local it = mm.getItem i
        if (it != undefined and it.getTitle() == "MatForge") do already = true
    )
    if (not already) then (
        local sub = menuMan.createMenu "MatForge"
        sub.addItem (menuMan.createActionItem "MatForge_Open" "MatForge") -1
        sub.addItem (menuMan.createActionItem "MatForge_Simple" "MatForge") -1
        local topItem = menuMan.createSubMenuItem "MatForge" sub
        mm.addItem topItem -1
        menuMan.updateMenuBar()
        format "MatForge: menu added.\n"
    ) else (
        format "MatForge: menu already present.\n"
    )
) catch (
    format "MatForge: menu add skipped (%). Find the button in Customize > Toolbars, category 'MatForge'.\n" (getCurrentException())
)

messageBox "MatForge installed.\n\nOpen it from the main menu: MatForge > MatForge,\nor add the button from Customize > Toolbars (category: MatForge)." title:"MatForge"
