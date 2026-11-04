"""forgeui: the shared Qt UI kit for the MatForge and Material Inspector docks.

Python 3.7 syntax, stdlib + Qt only. Importing it raises ImportError when neither PySide6 nor
PySide2 is available, so callers can fall back to the MAXScript rollout.
"""
__version__ = "1.0"

from . import compat, tokens, qss, a11y, widgets  # noqa: F401
from .compat import (QtCore, QtGui, QtWidgets, IS_PYSIDE6, QAction, QShortcut,  # noqa: F401
                     QRegularExpression, Signal, Slot, exec_dialog, font_families,
                     fixed_font, enum)
from .tokens import (ACCENT, RADIUS, SPACE, FONT_TITLE, FONT_BODY, FONT_SMALL,  # noqa: F401
                     Tokens, max_dark, from_palette, contrast)
from .qss import build_qss, apply  # noqa: F401
from .a11y import label, tab_order, enter_triggers, esc_triggers  # noqa: F401
from .widgets import (PrimaryButton, SecondaryButton, GhostButton, Title, Muted,  # noqa: F401
                      Card, SectionHeader, DropZone, StatusBanner, SeverityChip,
                      SkeletonRows, MoreOptions, EmptyState, Thumb, SegmentedChoice,
                      TileGrid)
