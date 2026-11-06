"""Offline tests of rk/frontfind.py (TFP front finder). Run: python3 tests/test_frontfind.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from rk import frontfind  # noqa: E402

LAT = 60.0 - 0.5 * np.arange(41)        # 60N..40N, north first like the decks
LON = 300.0 + 0.5 * np.arange(41)       # 300E..320E


def zone(x0=310.0, width=1.0, dtheta=16.0, warm_east=True):
    """A north-south thermal zone at lon x0: warm to the east (or west)."""
    X = np.broadcast_to(LON, (len(LAT), len(LON)))
    s = 1 if warm_east else -1
    return 290.0 + dtheta / 2 * (1 + np.tanh(s * (X - x0) / width))


def test_finds_line_at_zone():
    th = zone()
    u = np.full(th.shape, 8.0)          # westerly: blowing from the cold (west) side toward the warm side
    v = np.zeros(th.shape)
    fr = frontfind.find_fronts(th, u, v, LAT, LON, sigma=0, grad_min=2.0, min_len_nm=300)
    assert len(fr) == 1, fr
    f = fr[0]
    assert f["type"] == "cold"
    assert abs(np.median(f["lon"]) - 310.0) < 0.6, np.median(f["lon"])
    assert f["lat"].max() - f["lat"].min() > 10


def test_typing_by_cross_front_wind():
    th = zone()
    v = np.zeros(th.shape)
    warm = frontfind.find_fronts(th, np.full(th.shape, -8.0), v, LAT, LON, sigma=0, grad_min=2.0)
    stat = frontfind.find_fronts(th, np.full(th.shape, 0.5), v, LAT, LON, sigma=0, grad_min=2.0)
    assert [f["type"] for f in warm] == ["warm"]
    assert [f["type"] for f in stat] == ["stationary"]


def test_shift_moves_to_warm_side_and_threshold_drops_weak():
    th = zone(width=2.0)
    u, v = np.full(th.shape, 8.0), np.zeros(th.shape)
    base = frontfind.find_fronts(th, u, v, LAT, LON, sigma=0, grad_min=1.0)[0]
    moved = frontfind.find_fronts(th, u, v, LAT, LON, sigma=0, grad_min=1.0, shift_cells=2)[0]
    assert np.median(moved["lon"]) > np.median(base["lon"]) + 0.8
    assert frontfind.find_fronts(zone(dtheta=2.0, width=3.0), u, v, LAT, LON, sigma=0, grad_min=4.0) == []


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
