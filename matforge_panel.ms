/*  MatForge panel — hosts the dark REFGRADE-style web UI (ui/panel.html) in a
    dockable 3ds Max dialog and bridges it to the Python backend.

    Bridge protocol (robust, no ActiveX scripting object needed):
      * JS sets document.title = "MATFORGE::<cmd>::<payload>" on an action.
      * A dotNet timer here polls the title, runs the matching Python, and
        pushes results back into the page via InvokeScript.
    Run this file to open the panel (the installer wires it to the menu).     */

global mfPanelHtml = @"C:\Users\aasis\matforge\ui\panel.html"
global mfWB
global mfTimer
global mfLastTitle = ""

python.Execute "import sys; repo=r'C:\\Users\\aasis\\matforge'; (repo in sys.path) or sys.path.insert(0,repo)"
python.Execute "import maxplugin.forge_max as fm; import importlib; importlib.reload(fm)"

fn mfInvoke1 method arg = ( try ( mfWB.Document.InvokeScript method #(arg) ) catch() )
fn mfInvoke2 method a b = ( try ( mfWB.Document.InvokeScript method #(a, b) ) catch() )

fn mfPoll s e = (
    try (
        local t = mfWB.DocumentTitle
        if (t != undefined and t != mfLastTitle and (matchPattern t pattern:"MATFORGE::*")) then (
            mfLastTitle = t
            local parts = filterString t "::"
            local cmd = if parts.count >= 2 then parts[2] else ""
            if (cmd == "browse") then (
                python.Execute "fm._bridge_browse()"
                local p = (try (mfBridgeImage) catch "")
                if (p != undefined and p != "") do mfInvoke1 "mfImage" p
            ) else if (cmd == "create") then (
                global mfBridgePayload = if parts.count >= 3 then parts[3] else ""
                mfInvoke2 "mfStatus" "busy" "Working..."
                python.Execute "fm._bridge_create()"
                local st = (try (mfBridgeState) catch "err")
                local tx = (try (mfBridgeText) catch "no result")
                mfInvoke2 "mfStatus" st tx
            )
        )
    ) catch()
)

fn mfOpenPanel = (
    try (destroyDialog mfPanelRollout) catch()
    rollout mfPanelRollout "MatForge" width:480 height:660 (
        dotNetControl wb "System.Windows.Forms.WebBrowser" pos:[0,0] width:480 height:660
        on mfPanelRollout open do (
            mfWB = wb
            wb.ScrollBarsEnabled = false
            wb.Navigate mfPanelHtml
            mfTimer = dotNetObject "System.Windows.Forms.Timer"
            mfTimer.Interval = 250
            dotNet.addEventHandler mfTimer "Tick" mfPoll
            mfTimer.Start()
        )
        on mfPanelRollout close do ( try (mfTimer.Stop()) catch() )
    )
    createDialog mfPanelRollout 480 660 style:#(#style_titlebar,#style_border,#style_sysmenu,#style_resizing)
    cui.RegisterDialogBar mfPanelRollout minSize:[360,520] maxSize:[720,900]
    cui.DockDialogBar mfPanelRollout #cui_dock_right
)

mfOpenPanel()
