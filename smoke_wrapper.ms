-- 3dsmaxbatch entry point: run the headless MatForge smoke via pymxs.
_root = trimRight (getFilenamePath (getThisScriptFilename())) "\\"
python.Execute ("import os; os.environ['MATFORGE_ROOT']=r'" + _root + "'")
python.ExecuteFile (_root + "\\HEADLESS_SMOKE.py")
