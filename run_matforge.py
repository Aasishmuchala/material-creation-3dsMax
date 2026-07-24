"""Launcher -- run from 3ds Max: Scripting > Run Script... (or the MatForge
toolbar button / installer).

Why the self-reporting wrapper: python.ExecuteFile (how the installer and the
toolbar button launch this) does NOT reliably re-raise a Python exception as a
catchable MAXScript error on some Max builds (notably 2024). It just prints a
traceback to the -- often hidden -- MAXScript Listener, so a real failure looks
like "nothing happened". Catching here and showing a message box makes the
error visible regardless of how the file was launched.
"""
import os
import sys
import traceback


def _main():
    try:
        repo = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        # python.ExecuteFile may not define __file__ -> fall back to install path
        repo = r"C:\Users\aasis\matforge"
    if repo not in sys.path:
        sys.path.insert(0, repo)

    import importlib

    import maxplugin.forge_max as forge_max

    importlib.reload(forge_max)
    forge_max.show()


try:
    _main()
except Exception:
    _tb = traceback.format_exc()
    try:
        from pymxs import runtime as rt
        rt.messageBox(_tb, title="MatForge - startup error")
    except Exception:
        print("[MatForge] startup error:\n" + _tb)
