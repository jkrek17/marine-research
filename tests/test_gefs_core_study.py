"""Offline tests of the GEFS-only core-lift study (studies/2026-10-28-gefs-only-gfe/core): the feature set, the
products and the storm-area threshold choice. Run: python3 tests/test_gefs_core_study.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "studies" / "2026-10-28-gefs-only-gfe" / "core"))

import numpy as np  # noqa: E402

import gcommon as G  # noqa: E402
import gscore as S  # noqa: E402
from rk import features  # noqa: E402


def test_feature_set():
    assert "s10_aifs" not in G.SET_COLS and "pa48" not in G.SET_COLS
    assert len(G.SET_COLS) == 27 and G.SET_COLS[-1] == "basin_pac"
    assert set(features.FEATURES) - set(G.SET_COLS) == {"s10_aifs", "pa48"}


def test_products():
    n = np.array([[40.0, 44.0], [30.0, 50.0]], np.float32)
    p = np.array([[0.9, 0.9], [0.1, 0.9]])
    lift = S.lift_wind(n, p, 0.5)
    assert lift.tolist() == [[45.0, 49.0], [30.0, 55.0]]
    g = S.gale_wind(lift, np.array([[0.0, 0.0], [0.8, 0.8]]), 0.6)
    assert g.tolist() == [[45.0, 49.0], [34.0, 55.0]]       # raised to 34 where the gale chance is high, never lowered


def test_choose_sweep_matches_live_area():
    ts = S.TS_SWEEP
    rows = []
    for b in ("natl", "npac"):
        # 100 lift-eligible cells with P uniform in 0..1, 100 ASCAT 48+ cells, live area 0.4, N area 0.1
        ps = np.linspace(0.0, 1.0, 100)
        cnt = (ps[:, None] >= ts[None, :]).sum(0)
        rows.append({"basin": b, "ob48": 100, "fc48_N": 10, "fc48_live": 40, "lift_q": cnt, "nm_q": cnt,
                     "lift_h": cnt, "nm_h": cnt})
    choice, audit = S.choose_sweep(rows)
    assert abs(choice["q"]["lift_ratio"] - 0.4) < 0.02 and 0.6 < choice["q"]["t"] < 0.8
    assert len(audit) == 4


if __name__ == "__main__":
    for k, v in sorted(globals().items()):
        if k.startswith("test_"):
            v()
            print("ok", k)
