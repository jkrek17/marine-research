"""rk.features.strong_lift: lift where the strongest model is strong."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rk import features  # noqa: E402


def _grids():
    base = np.full((2, 3), 40.0, np.float32)
    a = np.array([[30, 44, 50], [43.9, 20, 20]], np.float32)
    b = np.array([[46, 10, 20], [20, 20, 44]], np.float32)
    return base, a, b


def test_lift_where_strongest_reaches_threshold():
    base, a, b = _grids()
    out = features.strong_lift(base, [a, b], 6, 44)
    assert out.dtype == np.float32
    assert np.array_equal(out, np.array([[46, 46, 46], [40, 40, 46]], np.float32))


def test_ocean_mask_and_stacked_input():
    base, a, b = _grids()
    ocean = np.array([[True, False, True], [True, True, False]])
    out = features.strong_lift(base, np.stack([a, b]), 8, 44, ocean)
    assert np.array_equal(out, np.array([[48, 40, 48], [40, 40, 40]], np.float32))


def test_nan_model_ignored_all_nan_not_lifted():
    base, a, b = _grids()
    a[0, 1] = np.nan
    b[0, 1] = np.nan
    b[0, 0] = np.nan
    out = features.strong_lift(base, [a, b], 6, 44)
    assert out[0, 1] == 40.0       # every model NaN: no lift
    assert out[0, 0] == 40.0       # a = 30, b NaN: strongest 30
    assert out[0, 2] == 46.0       # a = 50, b = 20
    assert not np.isnan(out).any()


def test_input_not_modified():
    base, a, b = _grids()
    keep = base.copy()
    features.strong_lift(base, [a, b], 6, 44)
    assert np.array_equal(base, keep)


def test_hf_ceiling_flag():
    wind = np.array([[70, 70, 70, 50, 70]], np.float32)
    s925 = np.array([[80, 80, 70, 60, np.nan]], np.float32)
    sa = np.array([[1.0, 6.0, 3.0, 1.0, 6.0]], np.float32)
    flag, ceil = features.hf_ceiling(wind, s925, sa)
    assert np.allclose(ceil[0, :4], [56.0, 66.4, 55.3, 42.0], atol=0.05)
    assert flag.tolist() == [[True, False, True, False, False]]   # 50 kt not HF; NaN 925 not flagged


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
