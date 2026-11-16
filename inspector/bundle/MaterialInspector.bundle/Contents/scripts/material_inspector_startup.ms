-- Material Inspector startup: puts the Python package on sys.path and registers the macroscript.
(
    local here = getFilenamePath (getSourceFileName())
    global MaterialInspector_PyRoot = here
    -- Read the path from the MAXScript global instead of splicing it into a Python
    -- string: `here` ends in "\", and r'...\' is a Python syntax error.
    python.Execute "import sys, pymxs\nroot = str(pymxs.runtime.MaterialInspector_PyRoot).rstrip('\\\\/')\nif root not in sys.path: sys.path.insert(0, root)"
)
macroScript MaterialInspector
    category:"Measured Light"
    buttonText:"Material Inspector"
    tooltip:"Check V-Ray / Corona materials for physical plausibility"
(
    python.Execute "import importlib, material_inspector.max_adapter.ui as ui\nui.show()"
)
