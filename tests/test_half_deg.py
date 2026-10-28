"""rk.features.half_deg: 0.5 deg subsample + bilinear back."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rk import features  # noqa: E402
from rk.basins import grid  # noqa: E402


def test_points_kept_and_midpoints_averaged():
    a = np.arange(5 * 7, dtype=np.float32).reshape(5, 7) ** 1.5
    h = features.half_deg(a)
    assert h.shape == a.shape
    assert np.allclose(h[::2, ::2], a[::2, ::2])
    assert np.isclose(h[0, 1], (a[0, 0] + a[0, 2]) / 2)
    assert np.isclose(h[1, 1], (a[0, 0] + a[0, 2] + a[2, 0] + a[2, 2]) / 4)


def test_linear_field_unchanged_inside():
    lats, lons = grid("natl")
    a = (lats[:, None] * 2 + lons[None, :]).astype(np.float32)
    h = features.half_deg(a)
    assert np.allclose(h[:-1, :-1], a[:-1, :-1], atol=1e-3)


def test_single_peak_is_lowered():
    a = np.zeros((9, 9), np.float32)
    a[3, 3] = 64.0          # off the 0.5 deg points
    assert features.half_deg(a).max() == 0.0


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
