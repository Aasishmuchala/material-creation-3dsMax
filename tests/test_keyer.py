"""Cut-outs keyed off a plain backdrop (core.maps.key_plain_background): a
leaf on white paper or on a grey card, without the card's falloff, the
leaf's shadow or holes where the leaf's tone matches the card."""
import os
import sys

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from core.maps import key_plain_background  # noqa: E402

N = 256


def _card(level=0.55, falloff=0.0):
    yy, xx = np.mgrid[0:N, 0:N].astype(np.float32) / (N - 1) * 2.0 - 1.0
    v = level * (1.0 - falloff * (xx * xx + yy * yy) / 2.0)
    return np.repeat(v[..., None], 3, axis=2).astype(np.float32), xx, yy


def _leaf(xx, yy, cx=0.0, cy=0.0, a=0.35, b=0.6):
    return ((xx - cx) / a) ** 2 + ((yy - cy) / b) ** 2 < 1.0


def test_leaf_on_white_is_cut_out():
    rgb, xx, yy = _card(0.97)
    leaf = _leaf(xx, yy)
    rgb[leaf] = (0.20, 0.42, 0.16)
    alpha = key_plain_background(rgb)
    assert alpha is not None and alpha.dtype == np.float32
    got = alpha > 0.5
    assert (got & leaf).sum() / float((got | leaf).sum()) > 0.95


def test_grey_card_falloff_leaves_no_haze():
    rgb, xx, yy = _card(0.55, falloff=0.45)          # corners 22 % darker than the centre
    leaf = _leaf(xx, yy)
    rgb[leaf] = (0.12, 0.25, 0.10)
    alpha = key_plain_background(rgb)
    assert alpha is not None
    assert float(alpha[~leaf & (np.abs(xx) > 0.6)].max()) < 0.05     # nothing of the card's corners


def test_shadow_on_the_card_is_not_subject():
    rgb, xx, yy = _card(0.55)
    leaf = _leaf(xx, yy)
    shadow = _leaf(xx, yy, cx=0.06, cy=0.05, a=0.40, b=0.65) & ~leaf  # an offset shadow, 28 % less light
    rgb[shadow] *= 0.86
    rgb[leaf] = (0.12, 0.25, 0.10)
    alpha = key_plain_background(rgb)
    got = alpha > 0.5
    assert (got & shadow).sum() < 0.05 * shadow.sum()
    assert (got & leaf).sum() > 0.95 * leaf.sum()


def test_leaf_as_bright_as_the_card_keeps_its_middle():
    rgb, xx, yy = _card(0.50)
    leaf = _leaf(xx, yy)
    rgb[leaf] = (0.56, 0.52, 0.30)                  # olive: the card's tone, another hue
    alpha = key_plain_background(rgb)
    assert alpha is not None
    assert float(alpha[_leaf(xx, yy, a=0.25, b=0.45)].min()) > 0.95


def test_grain_specks_go_and_a_busy_frame_is_no_backdrop():
    rgb, xx, yy = _card(0.55)
    rnd = np.random.default_rng(3)
    leaf = _leaf(xx, yy)
    rgb += rnd.normal(0.0, 0.012, rgb.shape).astype(np.float32)
    specks = (rnd.random((N, N)) < 0.004) & ~leaf
    rgb[specks] = 0.2
    rgb[leaf] = (0.12, 0.25, 0.10)
    alpha = key_plain_background(np.clip(rgb, 0.0, 1.0))
    assert float(alpha[specks & (np.abs(xx) > 0.5)].max(initial=0.0)) < 0.5
    busy = rnd.random((N, N, 3)).astype(np.float32)
    assert key_plain_background(busy) is None
    assert key_plain_background(np.full((N, N, 3), 0.9, np.float32)) is None     # nothing on the card


def test_a_leaf_brighter_than_life_is_darkened_but_a_flower_is_not():
    from core import maps as M
    lum = lambda a, m: float((M._srgb_to_lin(a[m]) @ np.array([0.2126, 0.7152, 0.0722], np.float32)).mean())
    _, xx, yy = _card()
    leaf = _leaf(xx, yy)
    op = leaf.astype(np.float32)
    green = np.full((N, N, 3), 0.95, np.float32)
    green[leaf] = (0.45, 0.72, 0.30)                 # a studio-bright leaf
    out, was = M.dim_bright_leaf(green, op, 0.16)
    assert was > 0.3 and lum(out, leaf) == pytest.approx(0.16, abs=0.01)
    ratio = out[leaf][0] / np.maximum(out[leaf][0, 1], 1e-4)
    assert ratio[1] > ratio[0] > ratio[2]            # still the same green
    dark = np.full((N, N, 3), 0.5, np.float32)
    dark[leaf] = (0.25, 0.38, 0.20)
    assert M.dim_bright_leaf(dark, op, 0.16)[1] is None             # already plausible
    flower = np.full((N, N, 3), 0.95, np.float32)
    flower[leaf] = (0.85, 0.65, 0.15)
    kept, was = M.dim_bright_leaf(flower, op, 0.16)
    assert was is None and kept is flower                            # yellow blossom: left alone
