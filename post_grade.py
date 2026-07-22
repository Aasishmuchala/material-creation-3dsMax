"""Cinematic finishing pass on a V-Ray render (the 'last 15%').
Deterministic PIL/numpy grade: auto white-balance (grey-world) to neutralise a
colour cast, gentle filmic S-curve contrast, subtle saturation, a soft
vignette, and fine film grain. Run on system Python.
  py -3.12 post_grade.py render_scene.png render_scene_final.png
"""
import sys

import numpy as np
from PIL import Image


def grey_world_wb(rgb, strength=0.8):
    """Neutralise a colour cast toward grey-world, blended by `strength`."""
    mean = rgb.reshape(-1, 3).mean(axis=0)
    g = mean.mean()
    gain = g / np.maximum(mean, 1e-4)
    gain = 1.0 + (gain - 1.0) * strength
    return np.clip(rgb * gain[None, None, :], 0, 1)


def filmic_contrast(x, a=0.9):
    """Gentle S-curve around 0.5 for filmic contrast."""
    return np.clip(0.5 + (x - 0.5) * (1.0 + a * (1.0 - np.abs(x - 0.5) * 2.0)),
                   0, 1)


def saturate(rgb, s=1.12):
    lum = (rgb * np.array([0.299, 0.587, 0.114])).sum(-1, keepdims=True)
    return np.clip(lum + (rgb - lum) * s, 0, 1)


def vignette(rgb, amount=0.28):
    h, w = rgb.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = w / 2.0, h / 2.0
    r = np.sqrt(((xx - cx) / cx) ** 2 + ((yy - cy) / cy) ** 2)
    mask = 1.0 - amount * np.clip((r - 0.5) / 0.7, 0, 1) ** 2
    return np.clip(rgb * mask[..., None], 0, 1)


def grain(rgb, sigma=0.012, seed=7):
    rng = np.random.default_rng(seed)
    n = rng.normal(0, sigma, rgb.shape[:2])[..., None]
    return np.clip(rgb + n, 0, 1)


def main(src, dst):
    img = Image.open(src).convert("RGB")
    rgb = np.asarray(img, dtype=np.float32) / 255.0
    rgb = grey_world_wb(rgb, strength=0.7)      # neutralise the warm cast
    rgb = filmic_contrast(rgb, a=0.85)          # filmic pop
    rgb = saturate(rgb, s=1.1)                  # a touch richer
    rgb = vignette(rgb, amount=0.25)            # draw the eye in
    rgb = grain(rgb, sigma=0.010)               # fine sensor grain
    Image.fromarray((np.clip(rgb, 0, 1) * 255 + 0.5).astype(np.uint8)).save(dst)
    print("graded ->", dst)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
