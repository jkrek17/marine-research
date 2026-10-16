"""Tests for rk.score and rk.compare on tiny synthetic data. Run: python3 tests/test_score.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from rk import score, compare


def test_counts_and_csi():
    ob = np.array([[40., 40., 10.], [10., 36., 10.]])
    fc = np.array([[40., 10., 40.], [10., 36., 10.]])
    assert score.contingency(fc, ob, 34) == (2, 1, 1)
    assert abs(score.csi(fc, ob, 34) - 0.5) < 1e-12
    assert abs(score.pod(fc, ob, 34) - 2 / 3) < 1e-12
    assert abs(score.far(fc, ob, 34) - 1 / 3) < 1e-12
    assert abs(score.area_ratio(fc, ob, 34) - 1.0) < 1e-12
    assert score.csi(ob, ob, 34) == 1.0
    m = np.zeros(ob.shape, bool); m[1] = True
    assert score.contingency(fc, ob, 34, mask=m) == (1, 0, 0)


def test_nan_on_empty():
    z = np.zeros((4, 4))
    for f in (score.csi, score.pod, score.far, score.area_ratio):
        assert np.isnan(f(z, z, 34))
    assert np.isnan(score.fss(z, z, 34))
    e = score.error(z, z, 25)
    assert e["n"] == 0 and np.isnan(e["bias"])


def test_fss_and_error():
    ob = np.zeros((20, 20)); ob[8:12, 8:12] = 40
    assert abs(score.fss(ob, ob, 34) - 1.0) < 1e-12
    assert abs(score.fss(np.roll(ob, 8, 1), ob, 34, n=3)) < 1e-9
    e = score.error(ob + 3, ob, 25)
    assert e["n"] == 16 and abs(e["bias"] - 3) < 1e-9 and abs(e["rmse"] - 3) < 1e-9


def test_tile_peaks():
    rng = np.random.default_rng(0)
    lat = rng.uniform(40, 44.99, 400); lon = rng.uniform(300, 304.99, 400)
    ob = rng.uniform(10, 30, 400); ob[0] = 50
    fc = ob - 5
    t = score.tile_peaks(fc, ob, lat, lon)
    assert len(t) == 1 and abs(t.err_max[0] + 5) < 1e-9 and t.n[0] == 400
    assert len(score.tile_peaks(fc, ob, lat, lon, min_n=500)) == 0


def test_paired_bootstrap():
    rng = np.random.default_rng(1)
    days = pd.date_range("2025-11-01", periods=140, freq="D")
    rows = []
    for d in days:
        base = rng.normal(5, 1)
        rows += [dict(cycle=d, step=24, method="a", v=base),
                 dict(cycle=d, step=24, method="b", v=base + 0.5 + rng.normal(0, 0.3))]
    df = pd.DataFrame(rows)
    r = compare.paired(df, "b", "a", "v", by="step", seed=3)
    row = r.iloc[0]
    assert row.lo < 0.5 < row.hi and row.significant and row.n_cases == 140 and row.n_weeks >= 20
    z = compare.paired(df, "a", "a", "v")
    assert z.iloc[0]["mean"] == 0 and not z.iloc[0]["significant"]
    t = compare.table(df, ["b"], "a", "v", by="step")
    assert t.loc[24, "b"].startswith("+0.5") and t.loc[24, "b"].endswith("*")


if __name__ == "__main__":
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); print("ok", k)
