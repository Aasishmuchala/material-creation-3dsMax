"""Measured complex IOR (n, k) of common metals at 650 / 550 / 450 nm (R, G, B).

Each entry was linearly interpolated to the three wavelengths from the
named refractiveindex.info dataset (raw YAML from the
polyanskiy/refractiveindex.info-database repository, fetched 2026-11-04).
Where the plan's first-choice dataset fell outside the Lagarde 2011 F0
acceptance band, the closest-matching measured dataset on the same shelf
was used instead and the source string names it.
"""
from .fresnel import rgb_f0, rgb_edge_tint

_S = "refractiveindex.info: %s, sampled 650/550/450 nm"

# Key order is part of the contract (metal_choices / UI dropdowns).
_TABLE = (
    ("gold", {
        "label": "Gold",
        "nk": ((0.1556, 3.6024), (0.4241, 2.4721), (1.3831, 1.9155)),
        "source": _S % "main/Au/Johnson (Johnson & Christy 1972)",
        "approx": False}),
    ("silver", {
        "label": "Silver",
        "nk": ((0.0522, 4.4094), (0.0596, 3.5974), (0.0400, 2.6484)),
        "source": _S % "main/Ag/Johnson (Johnson & Christy 1972)",
        "approx": False}),
    ("copper", {
        "label": "Copper",
        "nk": ((0.2378, 3.6264), (1.0066, 2.5823), (1.2404, 2.3929)),
        "source": _S % "main/Cu/Johnson (Johnson & Christy 1972)",
        "approx": False}),
    ("aluminium", {
        "label": "Aluminium",
        "nk": ((1.5580, 7.7124), (1.0152, 6.6273), (0.6332, 5.4544)),
        "source": _S % "main/Al/Rakic (Rakic 1995)",
        "approx": False}),
    ("chrome", {
        "label": "Chrome",
        "nk": ((3.1071, 3.3314), (3.1812, 3.3291), (2.3230, 3.1350)),
        "source": _S % "main/Cr/Johnson (Johnson & Christy 1974)",
        "approx": False}),
    # Johnson & Christy 1974 Fe gives F0 B = 0.496 (band 0.578 +/- 0.08), so
    # Querry 1985 (F0 0.579/0.567/0.564) is used.
    ("iron", {
        "label": "Iron",
        "nk": ((2.4270, 3.3610), (2.1890, 3.1710), (1.7360, 2.9060)),
        "source": _S % "main/Fe/Querry (Querry 1985)",
        "approx": False}),
    # Johnson & Christy 1974 Ti gives F0 0.616/0.582/0.544 (outside the band
    # on G and B); Mash & Motulevich 1973 gives 0.546/0.529/0.504.
    ("titanium", {
        "label": "Titanium",
        "nk": ((2.5350, 3.1400), (2.2450, 2.9250), (1.9050, 2.6300)),
        "source": _S % "main/Ti/Mash (Mash & Motulevich 1973)",
        "approx": False}),
    ("nickel", {
        "label": "Nickel",
        "nk": ((1.9900, 4.2086), (1.9212, 3.6158), (1.7290, 2.9435)),
        "source": _S % "main/Ni/Johnson (Johnson & Christy 1974)",
        "approx": False}),
    # Werner 2009 REELS (experimental) gives luminance 0.869 (band 0.55-0.85);
    # the Werner 2009 DFT set (0.802/0.844/0.863) is used. Calculated, not measured.
    ("zinc", {
        "label": "Zinc",
        "nk": ((3.4161, 7.0325), (1.9286, 6.3963), (1.0424, 5.1250)),
        "source": _S % "main/Zn/Werner-DFT (Werner et al. 2009, DFT calculation)",
        "approx": True}),
    ("brass", {
        "label": "Brass",
        "nk": ((0.4440, 3.6950), (0.5270, 2.7650), (1.0940, 1.8290)),
        "source": _S % "other/alloys/Cu-Zn/Querry-Cu70Zn30 (Querry 1985, 70% Cu 30% Zn)",
        "approx": False}),
    # No visible-range Sn data exists on refractiveindex.info, so tin bronze is
    # approximated by the measured Cu90Zn10 alloy ("commercial bronze", C22000).
    ("bronze", {
        "label": "Bronze",
        "nk": ((0.3200, 3.3960), (0.5190, 2.4150), (0.9800, 1.9450)),
        "source": _S % "other/alloys/Cu-Zn/Querry-Cu90Zn10 (Querry 1985, 90% Cu 10% Zn "
                       "'commercial bronze'; approx for tin bronze, no visible Sn data)",
        "approx": True}),
    # Werner 2009 Pt gives F0 0.955/0.934/0.849 (far above Lagarde 0.672/0.637/0.585);
    # Rakic 1998 Brendel-Bormann fit is used.
    ("platinum", {
        "label": "Platinum",
        "nk": ((2.3757, 4.2655), (2.0847, 3.7153), (1.8453, 3.1365)),
        "source": _S % "main/Pt/Rakic-BB (Rakic et al. 1998, Brendel-Bormann model)",
        "approx": False}),
    ("stainless_steel", {
        "label": "Stainless steel",
        "nk": ((2.4270, 3.3610), (2.1890, 3.1710), (1.7360, 2.9060)),
        "source": "approx: iron n,k (" + _S % "main/Fe/Querry (Querry 1985)" + ")",
        "approx": True}),
)

METALS = dict(_TABLE)
_ORDER = tuple(k for k, _ in _TABLE)


def _get(key):
    try:
        return METALS[key]
    except KeyError:
        raise KeyError("unknown metal %r" % (key,))


def metal_nk(key):
    return _get(key)["nk"]


def metal_f0(key):
    """Linear RGB normal-incidence reflectance."""
    return rgb_f0(metal_nk(key))


def metal_edge_tint(key):
    """Gulbrandsen edge tint g per channel (0-1)."""
    return rgb_edge_tint(metal_nk(key))


def metal_choices():
    return [(k, METALS[k]["label"]) for k in _ORDER]
