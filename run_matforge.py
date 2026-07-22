"""Launcher — run this file from 3ds Max: Scripting > Run Script..."""
import os
import sys

_REPO = os.path.dirname(os.path.abspath(__file__))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import importlib

import maxplugin.forge_max as forge_max

importlib.reload(forge_max)
forge_max.show()
