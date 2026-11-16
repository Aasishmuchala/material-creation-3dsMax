"""Shim to the shared physics package ``matphys`` (repo root, or next to the package in the bundle).

The Inspector and MatForge read F0, glass absorption and albedo limits from one
place. In the source tree ``matphys/`` sits three levels above this file; in the
Autodesk bundle ``tools/build_bundle.py`` copies it next to ``material_inspector``.
"""
from __future__ import annotations

import os
import sys

try:
    import matphys
except ImportError:  # running from the source tree without the repo root on sys.path
    _ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)
    import matphys

__all__ = ["matphys"]
