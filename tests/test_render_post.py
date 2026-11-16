"""render_post tests - 16-bit renders dither to 8 bits without banding, and
the grade's passes change only what they should."""
import importlib.util
import inspect
import os
import sys
import types
import zlib

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APT = os.path.join(REPO, "tools", "apartment")
sys.path.insert(0, os.path.join(REPO, "tools"))

cv2 = pytest.importorskip("cv2")
import render_post  # noqa: E402


def _ramp16(w=512, h=64):
    """A slow wall-like gradient spanning only ~10 8-bit code values."""
    x = np.linspace(105.0, 115.0, w) * 257.0
    a = np.repeat(x[None, :, None], h, axis=0).repeat(3, axis=2)
    a[:, :, 1] -= 18 * 257.0             # warm white: G and B below R
    a[:, :, 2] -= 31 * 257.0
    return np.clip(np.rint(a), 0, 65535).astype(np.uint16)


def _frame16(w=160, h=96, alpha=False):
    """A small high-key frame, laid out in display values: a warm wall ramp
    across the metered 0.72 (every channel above it from column 91), a dark
    chair, a sunlit white just under both bloom thresholds, a blown window."""
    v = np.repeat(np.linspace(0.66, 0.86, w, dtype=np.float32)[None, :], h, axis=0)
    x = np.dstack([v, v * 0.97, v * 0.93])
    x[50:80, 15:45] = 0.18                       # the chair
    x[55:75, 60:80] = 0.89                       # the sunlit white
    x[10:40, 110:140] = 1.0                      # the window
    if alpha:
        a = np.ones((h, w, 1), np.float32)
        a[:, :8] = 0.5
        x = np.dstack([x, a])
    return np.clip(np.rint(x * 65535.0), 0, 65535).astype(np.uint16)


def _old_to8(a, name, curve=0.0, glow=0.0, vig=0.0):
    """to8's pixels before the toe and halation went in: a frozen copy of its
    body (files aside), the reference for the byte-identical checks."""
    rng = np.random.default_rng(zlib.crc32(name.encode()))
    f = a.astype(np.float32) * np.float32(255.0 / 65535.0)
    if f.ndim == 3 and f.shape[2] == 4:
        alpha = f[:, :, 3].copy()
        f = f[:, :, :3]
    else:
        alpha = None
    if curve or glow or vig:
        x = f / np.float32(255.0)
        if glow:
            x = render_post.bloom(x, glow)
        if curve:
            x = render_post.tone_curve(x, np.float32(curve))
        if vig:
            x = render_post.vignette(x, vig)
        f = x * np.float32(255.0)
    f += rng.random(f.shape, dtype=np.float32) - rng.random(f.shape, dtype=np.float32)
    out = np.clip(np.rint(f), 0, 255).astype(np.uint8)
    if alpha is not None:
        out = np.dstack([out, np.clip(np.rint(alpha), 0, 255).astype(np.uint8)])
    return out


def _run_bench():
    """run_bench.py as a module (its `from run_apartment import` wants
    tools/apartment on the path)."""
    if APT not in sys.path:
        sys.path.insert(0, APT)
    spec = importlib.util.spec_from_file_location("run_bench_under_test", os.path.join(APT, "run_bench.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_dither_keeps_mean_and_kills_bands(tmp_path):
    p = str(tmp_path / "wall.png")
    src = _ramp16()
    cv2.imwrite(p, src)
    assert render_post.to8(p, str(tmp_path / "16bit"))
    out = cv2.imread(p, cv2.IMREAD_UNCHANGED)
    assert out.dtype == np.uint8 and out.shape == src.shape
    assert os.path.isfile(str(tmp_path / "16bit" / "wall.png"))
    # column means follow the true 16-bit ramp (no staircase)
    truth = src.astype(float).mean(0) / 257.0
    got = out.astype(float).mean(0)
    assert np.abs(got - truth).max() < 0.35
    # a plain rint would hold flat runs ~50 px wide; dithered columns vary
    plain = np.rint(src.astype(float) / 257.0)
    assert np.abs(plain.mean(0) - truth).max() > 0.4
    # the dither itself stays below one code value of noise
    assert (out.astype(float) - truth).std() < 0.8


def test_8bit_input_untouched(tmp_path):
    p = str(tmp_path / "already8.png")
    img = np.full((8, 8, 3), 120, np.uint8)
    cv2.imwrite(p, img)
    assert not render_post.to8(p, str(tmp_path / "16bit"))
    assert np.array_equal(cv2.imread(p, cv2.IMREAD_UNCHANGED), img)
    assert not os.path.exists(str(tmp_path / "16bit"))


def test_process_dir_skips_exposure_probes(tmp_path):
    for name in ("living.png", "_exp_living_0_1.png"):
        cv2.imwrite(str(tmp_path / name), _ramp16(32, 8))
    assert render_post.process_dir(str(tmp_path)) == 1
    assert cv2.imread(str(tmp_path / "living.png"), cv2.IMREAD_UNCHANGED).dtype == np.uint8
    assert cv2.imread(str(tmp_path / "_exp_living_0_1.png"), cv2.IMREAD_UNCHANGED).dtype == np.uint16


def test_tone_curve_keeps_ends_and_adds_contrast():
    x = np.linspace(0.0, 1.0, 101)
    y = render_post.tone_curve(x, 0.2)
    assert y[0] == 0.0 and y[-1] == pytest.approx(1.0)
    assert np.all(np.diff(y) > 0)                      # monotonic: no tone reversals
    assert y[25] < x[25] and y[75] > x[75]             # toe and shoulder
    assert np.array_equal(render_post.tone_curve(x, 0.0), x)


def test_bloom_glows_round_highlights_only():
    x = np.full((200, 300, 3), 0.4, np.float32)
    flat = render_post.bloom(x, 0.5)
    assert np.allclose(flat, x)                         # nothing above the threshold
    x[95:105, 145:155] = 1.0                            # a bright window
    y = render_post.bloom(x, 0.5)
    assert y[100, 142, 0] > x[100, 142, 0]              # glows into its surroundings
    x[95:105, 20:30] = 0.88                             # a lit white below the threshold
    assert np.allclose(render_post.bloom(x, 0.5)[95:105, 20:30], 0.88)
    assert y[5, 5, 0] == pytest.approx(0.4, abs=1e-3)   # far away: unchanged
    assert y.max() <= 1.0


def test_vignette_darkens_corners_not_centre():
    x = np.full((150, 240, 3), 0.5, np.float32)
    y = render_post.vignette(x, 0.2)
    assert y[75, 120, 0] == pytest.approx(0.5)
    assert y[0, 0, 0] == pytest.approx(0.4, abs=1e-3)


def test_tone_curve_leaves_the_highlights_alone():
    x = np.linspace(0.95, 1.0, 11)
    assert np.allclose(render_post.tone_curve(x, 0.3), x)


def test_toe_is_continuous_and_monotonic():
    x = np.linspace(0.0, 1.0, 100001)
    y = render_post.toe_curve(x, 1.3)
    assert y[0] == 0.0 and y[-1] == 1.0
    assert np.all(np.diff(y) > 0)                          # monotonic: no tone reversals
    assert np.diff(y).max() < 1.31 * (x[1] - x[0])         # no jump: steepest (k) just under the pivot
    p = render_post.TOE_PIVOT
    assert render_post.toe_curve(np.float32(p), 1.3) == np.float32(p)
    assert render_post.toe_curve(p - 1e-7, 1.3) == pytest.approx(p, abs=1e-6)   # both sides meet
    assert render_post.toe_curve(0.36, 1.3) == pytest.approx(0.72 * 0.5 ** 1.3, rel=1e-5)
    under = (x > 0.0) & (x < 0.71)
    assert np.all(y[under] < x[under])                     # deepens everything under the wall


def test_toe_leaves_the_wall_and_above_alone():
    x = np.linspace(render_post.TOE_PIVOT, 1.0, 57, dtype=np.float32)
    y = render_post.toe_curve(x, 1.3)
    assert y.dtype == np.float32 and np.array_equal(y, x)  # bit for bit, the pivot itself included
    x = np.linspace(0.7201, 1.0, 57)
    assert np.array_equal(render_post.toe_curve(x, 1.3, 0.72), x)


def test_halation_leaves_pixels_under_its_threshold_alone():
    x = np.full((120, 300, 3), 0.45, np.float32)
    x[40:80, 20:60] = 0.89                                 # a sunlit white just under 0.90
    x[50:70, 220:250] = 0.10                               # a dark chair
    assert np.array_equal(render_post.halation(x, 0.5), x)
    x[50:70, 140:160] = 1.0                                # a blown window
    y = render_post.halation(x, 0.5)
    assert y[60, 132, 0] > x[60, 132, 0] + 0.02            # its haze reaches 8 px out...
    assert render_post.bloom(x, 0.5)[60, 132, 0] == pytest.approx(0.45, abs=1e-4)  # ...past the bloom
    assert np.array_equal(y[30:90, 10:70], x[30:90, 10:70])   # the white does not glow
    assert y.max() <= 1.0


@pytest.mark.parametrize("alpha", [False, True])
@pytest.mark.parametrize("grade", [{}, {"curve": 0.25, "glow": 0.08, "vig": 0.10}],
                         ids=["plain", "apartment"])
def test_new_defaults_keep_the_old_output_byte_identical(tmp_path, grade, alpha):
    src = _frame16(alpha=alpha)
    want = _old_to8(src, "frame.png", **grade)
    p = str(tmp_path / "frame.png")
    cv2.imwrite(p, src)
    assert render_post.to8(p, str(tmp_path / "16bit"), **grade)
    assert np.array_equal(cv2.imread(p, cv2.IMREAD_UNCHANGED), want)
    d = tmp_path / "renders"                               # and through process_dir, as run_apartment
    d.mkdir()
    cv2.imwrite(str(d / "frame.png"), src)
    assert render_post.process_dir(str(d), **grade) == 1
    assert np.array_equal(cv2.imread(str(d / "frame.png"), cv2.IMREAD_UNCHANGED), want)


def test_to8_threads_the_toe_and_halation_through(tmp_path):
    src = _frame16()
    got = {}
    for name, grade in (("plain", {}), ("bench", {"toe": 1.3, "halo": 0.04})):
        (tmp_path / name).mkdir()
        p = str(tmp_path / name / "frame.png")             # one name: the same dither noise
        cv2.imwrite(p, src)
        assert render_post.to8(p, str(tmp_path / name / "16bit"), **grade)
        got[name] = cv2.imread(p, cv2.IMREAD_UNCHANGED).astype(float)
    plain, bench = got["plain"], got["bench"]
    assert bench[50:80, 15:45].mean() < plain[50:80, 15:45].mean() - 10    # the toe deepens the chair
    assert bench[40:44, 115:135].mean() > plain[40:44, 115:135].mean() + 1  # the window halates
    assert np.array_equal(bench[60:, 95:], plain[60:, 95:])               # the wall over the pivot,
    assert np.array_equal(bench[55:75, 60:80], plain[55:75, 60:80])       # the sunlit white
    assert np.array_equal(bench[10:40, 110:140], plain[10:40, 110:140])   # and the window: as they were


def test_run_bench_grades_with_the_toe_not_the_s_curve(tmp_path, monkeypatch):
    rb = _run_bench()
    takes = inspect.signature(render_post.process_dir)
    seen = {}

    def process_dir(d, **kw):
        takes.bind(d, **kw)          # a name process_dir lacks fails here, not after a render
        seen.update(kw)
        return 0
    monkeypatch.setattr(rb, "HERE", str(tmp_path))
    monkeypatch.setattr(rb.render_post, "process_dir", process_dir)
    monkeypatch.setattr(rb, "subprocess", types.SimpleNamespace(
        run=lambda *a, **kw: types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")))
    monkeypatch.setattr(sys, "argv", ["run_bench.py", "--tag", "t"])
    with pytest.raises(SystemExit):              # no scene log: Max reported dead, after the post
        rb.main()
    assert seen == rb.GRADE
    assert seen.get("toe") and seen.get("halo") and not seen.get("curve")
