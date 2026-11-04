"""Plain-English headlines for findings: what will look wrong, and what the fix does.

Pure data plus three small functions. Copy rules: no dashes (U+2014 / U+2013), no trailing
period, no rule ids inside a headline.
"""
from __future__ import annotations

from .model import Finding, Severity

#: rule id -> (what looks wrong, what the fix does / manual advice)
HEADLINES: dict[str, tuple[str, str]] = {
    "R001": ("Shading will look washed out: a data map is read as colour", "Reads it as linear data"),
    "R002": ("Colours will look too dark: a colour map is read as linear", "Reads it as sRGB colour"),
    "R003": ("Colour space could not be read", "Check the bitmap's colour space"),
    "R004": ("Texture file is missing: the slot renders black or flat", "Relink the file"),
    "R005": ("Rough and shiny are swapped on this surface", "Flips the roughness setting to match the map"),
    "R006": ("Normal map plugged in without a normal node: bumps render flat", "Adds the normal node"),
    "R007": ("Texture graph is very deep; renders slowly", "Simplify the graph"),
    "R008": ("A value is not a number; the render may fail", "Reset the value"),
    "R010": ("Base colour is darker or brighter than any real surface", "Moves it into the measured range"),
    "R011": ("This metal is darker than any real metal", "Sets the measured colour"),
    "R012": ("Half-metal surfaces render as a smear", "Sets metalness to 0 or 1"),
    "R013": ("IOR is outside the physical range", "Sets a plausible IOR"),
    "R014": ("Glass with no absorption looks like air", "Adds a light tint"),
    "R015": ("Reflections use an old model and look plasticky", "Switches to GGX"),
    "R016": ("Perfectly smooth surface: highlights become pinpoints", "Lower glossiness"),
    "R017": ("Legacy material type", "Convert to the physical material"),
    "R018": ("Named metal does not match its measured colour", "Sets the measured colour"),
    "R020": ("These maps look AI-generated", "Replace with scanned maps if accuracy matters"),
    "R999": ("A check crashed on this material", "See the log"),
    "M001": ("Colour map is too dark to be a real surface", "Brighten the map"),
    "M002": ("Colour map is too bright", "Darken the map"),
    "M003": ("Roughness map is one flat value", "Use a map with variation"),
    "M004": ("Metalness map is grey: parts render as a smear", "Make it black and white"),
    "M005": ("Tiling seam will show", "Make the map seamless"),
    "M006": ("Normal and height maps disagree", "Rebake one of them"),
    "M007": ("Normal map convention is wrong: bumps look inverted", "Flip green"),
    "M008": ("Normal map convention detected", ""),
    "M009": ("Convention check is off until it is set", "Set it in Settings"),
    "M010": ("Lighting is baked into the colour map", "Use a de-lit map"),
    "M012": ("Height map is inverted: bumps become dents", "Inverts the map"),
    "M013": ("Map looks upscaled", ""),
    "M900": ("Map could not be read", "Check the file"),
}

#: Rows the contract marks "(manual)": no automatic fix exists, the second string is advice.
MANUAL = frozenset({
    "R003", "R004", "R007", "R008", "R016", "R017", "R020", "R999",
    "M001", "M002", "M003", "M004", "M005", "M006", "M007", "M010", "M900",
})


def headline(f: Finding) -> str:
    row = HEADLINES.get(f.rule_id)
    return row[0] if row else f.message


def fix_sentence(f: Finding) -> str:
    row = HEADLINES.get(f.rule_id)
    if f.fix is not None:
        return row[1] if row else f.fix.description
    if row and f.rule_id in MANUAL:
        return row[1]
    return ""


def group(f: Finding) -> str:
    if f.severity == Severity.ERROR:
        return "Will render wrong"
    if f.severity == Severity.WARNING:
        return "Worth a look"
    return "Notes"


# No em-dash (U+2014) or en-dash (U+2013) in any UI string; chr() keeps this file dash-free.
_DASHES = (chr(0x2014), chr(0x2013))
assert not any(ch in s for row in HEADLINES.values() for s in row for ch in _DASHES)
