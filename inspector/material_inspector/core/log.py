"""Rotating log file so crashes inside 3ds Max can be diagnosed after the fact."""
from __future__ import annotations

import logging
import logging.handlers
import os

_LOGGER = None
_LOG_PATH = None


def log_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(base, "MeasuredLight", "logs")


def get_logger() -> logging.Logger:
    """Return the shared logger; re-targets the file if the log folder changed."""
    global _LOGGER, _LOG_PATH
    path = os.path.join(log_dir(), "inspector.log")
    if _LOGGER is not None and _LOG_PATH == path:
        return _LOGGER
    lg = logging.getLogger("material_inspector")
    lg.setLevel(logging.INFO)
    for h in list(lg.handlers):
        lg.removeHandler(h); h.close()
    _LOG_PATH = path
    try:
        os.makedirs(log_dir(), exist_ok=True)
        h = logging.handlers.RotatingFileHandler(path,
                                                 maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        lg.addHandler(h)
    except OSError:
        lg.addHandler(logging.NullHandler())
    _LOGGER = lg
    return lg
