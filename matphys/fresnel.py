"""Conductor Fresnel and the Gulbrandsen (2014) artist-friendly edge tint.

All inputs are the complex index n + ik of the metal against air (n0 = 1).
"""
import math


def f0(n, k):
    """Normal-incidence reflectance ((n-1)^2 + k^2) / ((n+1)^2 + k^2)."""
    return ((n - 1.0) ** 2 + k * k) / ((n + 1.0) ** 2 + k * k)


def fresnel_conductor(n, k, cos_theta):
    """Exact unpolarised reflectance of a conductor (Born & Wolf form).

    Rs = (a^2 + b^2 - 2a cos + cos^2) / (a^2 + b^2 + 2a cos + cos^2)
    Rp = Rs * (a^2 + b^2 - 2a sin tan + sin^2 tan^2) / (a^2 + b^2 + 2a sin tan + sin^2 tan^2)
    with 2a^2 = sqrt((n^2-k^2-sin^2)^2 + 4n^2k^2) + (n^2-k^2-sin^2)
         2b^2 = sqrt((n^2-k^2-sin^2)^2 + 4n^2k^2) - (n^2-k^2-sin^2)
    """
    c = min(max(float(cos_theta), 0.0), 1.0)
    if c <= 0.0:
        return 1.0
    s2 = 1.0 - c * c
    t = n * n - k * k - s2
    root = math.sqrt(t * t + 4.0 * n * n * k * k)
    a2 = max(0.5 * (root + t), 0.0)
    b2 = max(0.5 * (root - t), 0.0)
    a = math.sqrt(a2)
    rs = (a2 + b2 - 2.0 * a * c + c * c) / (a2 + b2 + 2.0 * a * c + c * c)
    st = s2 / c                       # sin * tan
    st2 = st * st
    rp = rs * (a2 + b2 - 2.0 * a * st + st2) / (a2 + b2 + 2.0 * a * st + st2)
    return 0.5 * (rs + rp)


def reflectance_at(n, k, degrees):
    """Unpolarised reflectance at an incidence angle in degrees (90 = grazing)."""
    return fresnel_conductor(n, k, math.cos(math.radians(degrees)))


def edge_tint(n, k):
    """Gulbrandsen 2014 edge tint g, found by inverting his n(r, g) mapping.

    r = f0; n_min = (1-r)/(1+r); n_max = (1+sqrt r)/(1-sqrt r);
    n = g*n_min + (1-g)*n_max  =>  g = (n_max - n) / (n_max - n_min), clamped 0-1.
    """
    r = min(max(f0(n, k), 0.0), 0.999999)
    sr = math.sqrt(r)
    n_min = (1.0 - r) / (1.0 + r)
    n_max = (1.0 + sr) / (1.0 - sr)
    den = n_max - n_min
    if den <= 1e-12:
        return 0.0
    g = (n_max - n) / den
    return min(max(g, 0.0), 1.0)


def rgb_f0(nk):
    return tuple(f0(n, k) for n, k in nk)


def rgb_edge_tint(nk):
    return tuple(edge_tint(n, k) for n, k in nk)


def rgb_reflectance_at(nk, degrees):
    return tuple(reflectance_at(n, k, degrees) for n, k in nk)
