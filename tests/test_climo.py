"""Tests for rk.climo on a tiny synthetic reference. Run: python3 tests/test_climo.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from rk import climo


def _ref(n=200, lat=55.0, lon=330.0, month=1):
    hpa = np.linspace(950.0, 1009.0, n)
    return {"lat": np.full(n, lat), "lon": np.full(n, lon), "month": np.full(n, month, np.int8),
            "hpa": hpa, "gust_kt": np.zeros(n), "basin": np.zeros(n, np.int8), "season": np.zeros(n, np.int16)}


def test_parse():
    text = ('/* x */\nwindow.HF_ERA5_PEAKS = {"meta":{"fields":["track","basin(0 atl,1 pac)","season","start",'
            '"peak_lat*4","peak_lon*4","gust800_kt*10","minp_hPa*10","n_fix"]},'
            '"ev":[[0,1,1979,1979120100,210,-620,444,9908,9]]};\n')
    r = climo._parse(text)
    assert r["month"][0] == 12 and r["basin"][0] == 1
    assert abs(r["lat"][0] - 52.5) < 1e-9 and abs(r["lon"][0] - 205.0) < 1e-9
    assert abs(r["hpa"][0] - 990.8) < 1e-9 and abs(r["gust_kt"][0] - 44.4) < 1e-9


def test_percentile():
    ref = _ref()
    r = climo.rarity(55.0, -30.0, 1, 950.0, ref=ref)          # -30 == 330: deeper than all but itself
    assert r["n"] == 200 and r["months"] == 0 and r["pct"] == 100 * 199 / 200
    assert climo.rarity(55.0, 330.0, 1, 1010.0, ref=ref)["pct"] == 0.0
    assert abs(climo.rarity(55.0, 330.0, 1, 979.5, ref=ref)["pct"] - 50.0) < 1.0


def test_month_window_and_distance():
    ref = _ref(month=3)                                          # all in March
    r = climo.rarity(55.0, 330.0, 1, 970.0, ref=ref)            # January: needs +-2 months
    assert r["months"] == 2 and r["n"] == 200
    assert climo.rarity(55.0, 330.0, 12, 970.0, ref=ref)["n"] == 0   # Dec is 3 months from March
    assert np.isnan(climo.rarity(55.0, 330.0, 12, 970.0, ref=ref)["pct"])
    far = climo.rarity(30.0, 330.0, 3, 970.0, ref=ref)          # 2,780 km away
    assert far["n"] == 0
    wrap = _ref(month=12)
    assert climo.rarity(55.0, 330.0, 1, 970.0, ref=wrap)["months"] == 1   # Dec-Jan wraps


def test_table():
    t = climo.rarity_table(pd.DataFrame({"lat": [55.0, 55.0], "lon": [330.0, 330.0], "hpa": [950.0, 1010.0]}),
                           1, ref=_ref())
    assert list(t.columns) == ["lat", "lon", "hpa", "pct", "n", "months", "deepest"]
    assert t.pct.iloc[0] > 99 and t.pct.iloc[1] == 0


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
    print("ok")
