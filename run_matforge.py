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


def _is_root(path):
    return bool(path) and os.path.isfile(
        os.path.join(path, "maxplugin", "forge_max.py"))


def _find_root():
    """Repo / bundle folder, never a user-specific literal. Order:
    __file__ (when python.ExecuteFile defines it) -> env MATFORGE_ROOT ->
    a MATFORGE_ROOT Python global -> the MatForgeRoot MAXScript global that
    the installer / macros / panel set before ExecuteFile. Each candidate is
    checked, since a stale __file__ from an earlier script can linger in
    __main__."""
    cands = []
    try:
        cands.append(os.path.dirname(os.path.abspath(__file__)))
    except NameError:
        pass
    cands.append(os.environ.get("MATFORGE_ROOT"))
    cands.append(globals().get("MATFORGE_ROOT"))
    try:
        from pymxs import runtime as rt
        v = getattr(rt, "MatForgeRoot", None)
        if v:
            cands.append(str(v))
    except Exception:
        pass
    for c in cands:
        if _is_root(c):
            return os.path.abspath(c)
    raise RuntimeError(
        "MatForge could not find its own folder. Run install_matforge.ms "
        "from the MatForge folder, or set the MATFORGE_ROOT environment "
        "variable to it. Tried: %r" % ([c for c in cands if c],))


def _main():
    repo = _find_root()
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
