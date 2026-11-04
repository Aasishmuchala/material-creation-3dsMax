-- 3dsmaxbatch entry point: build MatForge materials on geometry and render.
_root = trimRight (getFilenamePath (getThisScriptFilename())) "\\"
global MatForgeRoot = _root   -- read by Python via pymxs, never spliced into a literal
python.Execute "import os; from pymxs import runtime as _rt; os.environ['MATFORGE_ROOT']=str(_rt.MatForgeRoot)"
python.ExecuteFile (_root + "\\RENDER_CHECK.py")
