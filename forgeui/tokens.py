"""Design tokens: Max-dark defaults, or derived from a dark host QPalette (plan D7).

Pure stdlib apart from from_palette(), which reads a QPalette handed in by the caller.
"""
import colorsys

ACCENT = "#5FB89A"
RADIUS = 4
SPACE = (4, 8, 12, 16, 24, 32)
FONT_TITLE = 15
FONT_BODY = 13
FONT_SMALL = 11

FIELDS = ("window", "base", "raised", "hover", "text", "muted", "hairline",
          "accent", "accent_hover", "accent_pressed", "on_accent",
          "error", "warning", "ok", "on_semantic")


class Tokens(object):
    """Plain bag of '#rrggbb' strings, one per name in FIELDS."""

    def __init__(self, **kw):
        for name in FIELDS:
            setattr(self, name, kw.get(name, ""))

    def as_dict(self):
        return dict((name, getattr(self, name)) for name in FIELDS)

    def __eq__(self, other):
        return isinstance(other, Tokens) and self.as_dict() == other.as_dict()

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return "Tokens(%s)" % ", ".join("%s=%s" % (k, getattr(self, k)) for k in FIELDS)


def _fixed():
    """Accent and semantic colours: never derived from the host."""
    return dict(accent=ACCENT, accent_hover="#6FC4A8", accent_pressed="#4FA88A",
                on_accent="#1e1e1e", error="#D06A6A", warning="#D9A441", ok=ACCENT,
                on_semantic="#1e1e1e")


def max_dark():
    """The 3ds Max 2025 dark theme values from the design contract."""
    kw = dict(window="#444444", base="#3a3a3a", raised="#4f4f4f", hover="#585858",
              text="#e6e6e6", muted="#a6a6a6", hairline="#2e2e2e")
    kw.update(_fixed())
    return Tokens(**kw)


# -- colour helpers ----------------------------------------------------------

def _rgb(hex_str):
    h = hex_str.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex(r, g, b):
    clamp = lambda v: max(0, min(255, int(round(v))))
    return "#%02x%02x%02x" % (clamp(r), clamp(g), clamp(b))


def _shift_lightness(hex_str, delta):
    """Move HLS lightness by delta (absolute, -1..1), keeping hue and saturation."""
    r, g, b = [c / 255.0 for c in _rgb(hex_str)]
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    l = max(0.0, min(1.0, l + delta))
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return _hex(r * 255, g * 255, b * 255)


def lighten(hex_str, pct):
    """Lighten by pct percent of the lightness range (8 -> +0.08)."""
    return _shift_lightness(hex_str, pct / 100.0)


def darken(hex_str, pct):
    return _shift_lightness(hex_str, -pct / 100.0)


def blend(hex_a, hex_b, t):
    """Linear mix: t=0 -> a, t=1 -> b."""
    a, b = _rgb(hex_a), _rgb(hex_b)
    return _hex(*[a[i] + (b[i] - a[i]) * t for i in range(3)])


def _luminance(hex_str):
    out = []
    for c in _rgb(hex_str):
        c = c / 255.0
        out.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]


def contrast(hex_a, hex_b):
    """WCAG 2 contrast ratio between two '#rrggbb' colours (1.0 .. 21.0)."""
    la, lb = _luminance(hex_a), _luminance(hex_b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# -- palette derivation (D7) ---------------------------------------------------

def from_palette(palette=None):
    """Tokens from a dark host palette; None or a light palette -> max_dark()."""
    if palette is None:
        return max_dark()
    from .compat import QtGui, enum
    role = lambda name: enum(QtGui.QPalette, "ColorRole", name)
    window_c = palette.color(role("Window"))
    if window_c.lightnessF() >= 0.5:
        return max_dark()
    window = window_c.name()
    raised = lighten(window, 8)
    text = palette.color(role("WindowText")).name()
    kw = dict(window=window,
              base=palette.color(role("Base")).name(),
              raised=raised,
              hover=lighten(raised, 6),
              text=text,
              muted=blend(text, window, 0.30),
              hairline=darken(window, 10))
    kw.update(_fixed())
    return Tokens(**kw)
