"""Tests for studies/2026-11-16-mslp-blend-d7/analyze.py helpers. Run: python3 tests/test_mslp_blend_analyze.py"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "studies" / "2026-11-16-mslp-blend-d7"))
import numpy as np
import pandas as pd
import analyze as A


def test_bh():
    q = A.bh([0.001, 0.04, 0.03, 0.9, np.nan], 0.1)
    assert np.allclose(q[:4], [0.004, 0.0533333, 0.0533333, 0.9], atol=1e-6) and np.isnan(q[4])


def test_boot_and_diffs():
    n = 60
    wk = np.repeat(np.arange(20), 3)
    j = pd.DataFrame({"week_c": ["w%d" % w for w in wk], "pos_sum_c": np.full(n, 100.0), "pos_sum_r": np.full(n, 150.0),
                      "n_lows_c": np.ones(n), "rmse_c": np.full(n, 1.0), "rmse_r": np.full(n, 1.2),
                      "false_n_c": np.zeros(n), "false_n_r": np.ones(n), "sd_n_c": np.zeros(n), "sd_n_r": np.zeros(n),
                      "sd_bias_sum_c": np.zeros(n), "sd_bias_sum_r": np.zeros(n)})
    r = A.diffs(j, 300)
    assert abs(r["dpos"] + 50) < 1e-9 and r["dpos_hi"] < 0 and r["p_pos"] < 0.05
    assert abs(r["drmse"] + 0.2) < 1e-9 and r["dfalse"] == -1 and np.isnan(r["ddepth"])


def test_untuned_and_tuned_selection():
    df = pd.DataFrame({"cand": ["al"] * 4 + ["gfs", "off"], "setting": ["cap=300", "cap=450", "default", "cap=600", "base", "off=0"],
                       "lead": 48, "basin": "natl", "split": "tune", "month": "202601"})
    u = A.untuned_rows(df)
    assert sorted(u.cand) == ["al", "gfs"] and set(u.setting) == {"default", "base"}
    ch = pd.DataFrame({"cand": ["al"], "lead": [48], "basin": ["natl"], "fold": ["202601"], "setting": ["cap=600"]})
    t = A.select_tuned(df, ch)
    assert list(t.cand) == ["al_t"] and list(t.setting) == ["cap=600"]


if __name__ == "__main__":
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); print("ok", k)
