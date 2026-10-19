"""Tests for the day 5-7 bomb rule (studies/2026-10-19-bomb-d5-7/bomb.py). Run: python3 tests/test_bomb_d5_7_study.py"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "studies" / "2026-10-19-bomb-d5-7"))
import numpy as np
import bomb


def test_bergeron_scales_with_latitude():
    prev = np.array([[60.0, 330.0, 1000.0]])
    b = bomb.bombs(prev, np.array([[60.0, 340.0, 976.0]]))          # 24 hPa at 60N, ~550 km away
    assert len(b) == 1 and abs(b[0, 3] - 1.0) < 1e-9
    b = bomb.bombs(np.array([[40.0, 330.0, 1000.0]]), np.array([[40.0, 335.0, 976.0]]))
    assert b[0, 3] > 1.3                                               # same drop at 40N is more than 1 Bergeron


def test_track_limit_and_nearest():
    prev = np.array([[50.0, 300.0, 990.0], [50.0, 330.0, 1005.0]])
    b = bomb.bombs(prev, np.array([[50.0, 332.0, 990.0]]))
    assert abs(b[0, 3] - 15 * np.sin(np.radians(60)) / np.sin(np.radians(50)) / 24) < 1e-9   # nearest, not deepest
    assert len(bomb.bombs(np.array([[50.0, 300.0, 1000.0]]), np.array([[50.0, 340.0, 960.0]]))) == 0  # 2,860 km
    assert len(bomb.bombs(np.zeros((0, 3)), np.array([[50.0, 340.0, 960.0]]))) == 0


def test_find_lows_and_dedupe():
    lats = np.linspace(67, 30, 149)
    lons = np.arange(285, 360, 0.25)
    y, x = np.meshgrid(np.arange(149), np.arange(300), indexing="ij")
    hpa = 1015 - 30 * np.exp(-((y - 70) ** 2 + (x - 150) ** 2) / 200.0)
    hpa[70, 151] = hpa[70, 150] + 0.0                                  # flat bottom: twin minimum
    lows = bomb.find_lows(hpa.astype(np.float32), lats, lons)
    assert len(lows) == 1 and lows[0, 2] < 986
    hpa[2, 2] = 900.0                                                  # edge minimum ignored
    assert len(bomb.find_lows(hpa.astype(np.float32), lats, lons)) == 1


def test_neighbourhood():
    clat, clon = bomb.cells("natl")
    hit = bomb.near(np.array([[51.0, 331.0]]), clat, clon)
    assert hit.sum() > 4 and hit[np.argmin(np.hypot(clat - 51, clon - 331))]
    assert not bomb.near(np.zeros((0, 2)), clat, clon).any()


if __name__ == "__main__":
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); print("ok", k)
