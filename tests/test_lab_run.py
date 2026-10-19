"""Tests for the lab job's pieces (tools/lab_run.py) on synthetic input. Run: python3 tests/test_lab_run.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from rk import basins, bomb
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import lab_run as L


def test_levels():
    assert [L.level(p) for p in (0.0, 0.099, 0.10, 0.19, 0.20, 0.349, 0.35, 0.9)] == [0, 0, 1, 1, 2, 2, 3, 3]


def test_basin_lows_open_water_and_depth():
    msl = np.full((721, 1440), 101500.0)
    for b in basins.BASINS:
        lats, lons = basins.grid(b)
        bomb._MASK[b] = np.ones((len(lats), len(lons)), bool)
    lat_i, lon_i = int((90 - 50) * 4), int(330 * 4)                    # 50N 30W
    y, x = np.mgrid[-40:41, -40:41]
    msl[lat_i - 40:lat_i + 41, lon_i - 40:lon_i + 41] -= 3000 * np.exp(-(y ** 2 + x ** 2) / 300.0)
    got = L.basin_lows(msl)
    assert len(got) == 1 and got[0][0] == "natl" and abs(got[0][1] - 50) < 0.3 and got[0][3] < 986
    lats, lons = basins.grid("natl")
    bomb._MASK["natl"][np.argmin(np.abs(lats - 50)), np.argmin(np.abs(lons - 330))] = False   # over land
    assert L.basin_lows(msl) == []
    bomb._MASK["natl"][:, :] = True
    msl[lat_i - 40:lat_i + 41, lon_i - 40:lon_i + 41] = 101500.0 - 1000 * np.exp(-(y ** 2 + x ** 2) / 300.0)
    assert L.basin_lows(msl) == []                                                 # 1005 hPa: not deep enough
    bomb._MASK.clear()


def test_bomb_shares_pool_members():
    clat, clon = bomb.cells("natl")
    deep = [np.array([[50.0, 330.0, 1000.0]]), np.array([[52.0, 335.0, 970.0]])]   # 30 hPa at ~51N: a bomb
    flat = [np.array([[50.0, 330.0, 1000.0]]), np.array([[52.0, 335.0, 995.0]])]
    ens = {"gefs": {96: [deep[0], flat[0]], 120: [deep[1], flat[1]]},
           "ens": {96: [flat[0], flat[0]], 120: [flat[1], flat[1]]}}
    p, n = L.bomb_shares(ens, clat, clon, 120)
    i = np.argmin(np.hypot(clat - 52, clon - 335))
    assert n == 4 and abs(p[i] - 0.25) < 1e-9 and p.max() == 0.25
    ens["ens"][120] = [flat[1]]                                                    # members no longer line up
    p, n = L.bomb_shares(ens, clat, clon, 120)
    assert n == 2 and abs(p[i] - 0.5) < 1e-9


def test_twin_card():
    lib = {"pcs": np.array([[0.0, 0], [1, 0], [5, 0], [6, 0]], np.float32), "track": np.array([1, 1, 2, 3]),
           "season": np.array([2015, 2015, 2016, 2017]), "gcls": np.array([3, 3, 0, 1], np.int8),
           "time": np.array(["2015120100", "2015120112", "2016010100", "2017020100"]), "basin": np.array(["atl"] * 4),
           "lat": np.array([50.0, 51, 40, 45]), "lon": np.array([330.0, 331, 200, 210]), "msl": np.array([960.0, 958, 990, 980])}
    c = L.twin_card(lib, np.array([0.2, 0.0]))                     # library smaller than k: all four are twins
    assert c["hf"] == 2 and c["counts"] == [1, 1, 0, 2]
    assert [x["time"] for x in c["closest"]] == ["2015120100", "2016010100", "2017020100"]       # one per storm
    assert c["closest"][0] == {"time": "2015120100", "basin": "atl", "lat": 50.0, "lon": 330.0, "hpa": 960.0, "cls": 3}


if __name__ == "__main__":
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); print("ok", k)
