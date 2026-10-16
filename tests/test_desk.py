"""Tests for rk.desk. Run with pytest or `python3 tests/test_desk.py`.
Network tests run only with RK_NET=1 (set RK_DESK to a scratch cache directory)."""
import datetime as dt
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from rk import basins, desk  # noqa: E402


def test_floor_snapping():
    # npac box: row 0 is 67 N, column 0 is 160 E. 66.875 is the edge between rows 0 and 1 of 0.25 boxes
    # centred 67 and 66.75: floor(x + 0.5) puts the half-way point in the lower (southern/eastern) box.
    idx = desk.box_index([67.0, 66.9, 66.875, 66.76, 66.625], [160.0, 160.1, 160.125, 160.0, 160.0], "npac")
    nx = 341
    assert list(idx) == [0, 0, 1 * nx + 1, 1 * nx, 2 * nx]   # np.rint would send 66.875 and 160.125 elsewhere


def test_outside_box():
    idx = desk.box_index([50, 20, 50, 50, 68], [-30, -30, 100, 359.97, 200], "natl")
    assert idx[0] >= 0 and idx[1] == -1 and idx[2] == -1 and idx[3] == -1 and idx[4] == -1   # 359.97 snaps to 360
    lats, lons = basins.grid("natl")
    assert idx[0] == int(np.argmin(abs(lats - 50))) * len(lons) + int(np.argmin(abs(lons - 330)))
    assert desk.box_index([50], [-150], "npac")[0] >= 0             # 0-360 and negative longitudes agree
    assert desk.box_index([50], [210], "npac")[0] == desk.box_index([50], [-150], "npac")[0]


def test_mean_and_missing():
    lat = np.array([50.0, 50.05, 50.1, 50.0, 40.0])
    lon = np.array([200.0, 200.05, 200.1, 201.0, 201.0])
    idx = desk.box_index(lat, lon, "npac")
    assert idx[0] == idx[1] == idx[2] != idx[3]
    n = 149 * 341
    v = np.array([10.0, 20.0, 9999.0, 9999.0, 30.0])
    m = desk.area_mean(v, idx, n)
    assert m.dtype == np.float32 and m.shape == (n,)
    assert m[idx[0]] == 15.0                       # missing cell not counted
    assert np.isnan(m[idx[3]])                     # a box with only missing cells
    assert m[idx[4]] == 30.0
    assert np.isnan(m).sum() == n - 2              # every other box is empty
    assert np.isnan(desk.area_mean(np.array([np.nan, 5.0]), np.array([4, -1], np.int32), 10)[4])


def test_pick_window_logic():
    snaps = [(dt.datetime(2026, 1, 15, h, m), "k%02d%02d" % (h, m), 1) for h, m in ((1, 9), (4, 9), (10, 9), (13, 9), (22, 7))]
    real = desk.issuances
    desk.issuances = lambda day, product="YCYZ98": snaps
    try:
        d = dt.datetime(2026, 1, 15)
        assert desk.pick(d, 10) == "k1009" and desk.pick(d, 22) == "k2207" and desk.pick(d, 16) is None
    finally:
        desk.issuances = real


def test_net():
    if os.environ.get("RK_NET") != "1":
        print("note: RK_NET not set; network test skipped")
        return
    import time
    d = dt.datetime(2026, 1, 15)
    assert desk.pick(d, 10).endswith("202601151009") and desk.pick(d, 22).endswith("202601152207")
    k97 = desk.pick(d, 10, "YCYZ97")
    assert k97 is not None and k97.endswith("202601151009")
    t0 = time.time()
    r = desk.load(dt.datetime(2026, 1, 15, 10))
    print("load took %.1f s" % (time.time() - t0))
    assert set(r) == {"natl", "npac"}
    for b, g in r.items():
        ny, nx = len(basins.grid(b)[0]), len(basins.grid(b)[1])
        assert g["speed"].dtype == np.float16 and g["speed"].shape == (len(g["valid"]), ny, nx)
        assert dt.datetime(2026, 1, 16, 0) in g["valid"]
        assert all(v.hour in (0, 6, 12, 18) for v in g["valid"]) and g["valid"] == sorted(g["valid"])
        assert g["ref"] == dt.datetime(2026, 1, 15, 10)
        assert g["valid"][0] == dt.datetime(2026, 1, 15, 12)
        top = float(np.nanmax(g["speed"]))
        assert 10 < top < 80, top
        assert set(g["product"]) == {"YCYZ98", "YCYZ97"}
        assert g["product"][0] == "YCYZ98" and g["product"][-1] == "YCYZ97"
        assert g["valid"][-1] >= dt.datetime(2026, 1, 21, 0), g["valid"][-1]     # out to day 7
        n98 = g["product"].index("YCYZ97")
        assert all(p == "YCYZ97" for p in g["product"][n98:])
    nat = r["natl"]["speed"][r["natl"]["valid"].index(dt.datetime(2026, 1, 16, 0))]
    assert np.isfinite(nat).mean() > 0.5
    t0 = time.time()
    assert desk.load(dt.datetime(2026, 1, 15, 10))["natl"]["valid"] == r["natl"]["valid"]   # from cache
    print("cached load took %.2f s" % (time.time() - t0))


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
