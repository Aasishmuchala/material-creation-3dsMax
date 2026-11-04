_root = trimRight (getFilenamePath (getThisScriptFilename())) "\\"
python.Execute ("import os; os.environ['MATFORGE_ROOT']=r'" + _root + "'")
python.ExecuteFile (_root + "\\RENDER_SCENE.py")
