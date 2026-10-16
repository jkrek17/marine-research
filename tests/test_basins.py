"""Tests for rk.basins. Run with pytest or `python3 tests/test_basins.py`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from rk import KT, basins  # noqa: E402


def test_kt():
    assert KT == 1.943844


def test_shapes():
    for b, shape in (("natl", (149, 300)), ("npac", (149, 341))):
        lats, lons = basins.grid(b)
        assert (len(lats), len(lons)) == shape
        assert lats[0] == 67 and lats[-1] == 30
        iy, ix = basins.crop(b)
        assert iy.stop - iy.start == shape[0] and len(ix) == shape[1]


def test_edges():
    lats, lons = basins.grid("natl")
    assert lons[0] == 285.0 and lons[-1] == 359.75
    lats, lons = basins.grid("npac")
    assert lons[0] == 160.0 and lons[-1] == 245.0
    iy, ix = basins.crop("npac")
    assert iy.start == 92 and ix[0] == 640 and ix[-1] == 980


def test_hours():
    assert basins.BASINS["natl"]["hour"] == 12 and basins.BASINS["npac"]["hour"] == 0


def test_inside_any_convention():
    assert basins.inside("natl", 50, -30)
    assert basins.inside("natl", 50, 330)
    assert not basins.inside("natl", 50, -80)
    assert not basins.inside("natl", 20, -30)
    assert basins.inside("npac", 50, 180) and basins.inside("npac", 50, -150)
    assert not basins.inside("npac", 50, -100)


def test_sample_linear_field():
    lats, lons = basins.grid("npac")
    f = lats[:, None] * 1.0 + 0.1 * (lons[None, :] - 160.0)   # linear, so bilinear is exact
    v = basins.sample(f, "npac", [50.1, 66.0], [200.13, -160.0])
    assert np.allclose(v, [50.1 + 0.1 * 40.13, 66.0 + 0.1 * 40.0])
    assert np.isnan(basins.sample(f, "npac", 20, 200))
    # grid points reproduce exactly, including the last row and column
    assert np.isclose(basins.sample(f, "npac", 30, 245), f[-1, -1])
    assert np.isclose(basins.sample(f, "npac", 67, 160), f[0, 0])


def test_to_quarter():
    for b in basins.BASINS:
        lats, lons = basins.grid(b)
        LA, LO = np.meshgrid(lats, lons, indexing="ij")
        lin = lambda la, lo: 3.0 + 0.7 * la - 0.2 * lo
        half = lin(LA, LO)[::2, ::2]
        q = basins.to_quarter(half, b)
        assert q.shape == LA.shape
        assert np.array_equal(q[::2, ::2], half)                         # shared points unchanged
        inner = (np.arange(len(lats)) < 2 * (half.shape[0] - 1))[:, None] & (np.arange(len(lons)) < 2 * (half.shape[1] - 1))[None, :]
        assert np.allclose(q[inner], lin(LA, LO)[inner])                 # linear field exact
        # an even-length axis repeats the last half-grid value past it
        if len(lons) % 2 == 0:
            assert np.array_equal(q[:, -1], q[:, -2])
    try:
        basins.to_quarter(np.zeros((3, 3)), "natl")
        assert False
    except ValueError:
        pass


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
