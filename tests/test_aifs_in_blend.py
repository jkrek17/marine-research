"""Offline tests of the AIFS-in-blend study: the preset win line on synthetic counts, and the smoke guard.
Run: python3 tests/test_aifs_in_blend.py"""
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "studies" / "2026-10-16-aifs-in-blend"))

import pandas as pd  # noqa: E402

import summarize as S  # noqa: E402
from rk import cases  # noqa: E402


def _counts(b_gain=(2, 0), c_gain=(0, 0), b_pod_loss=0, b_area=0):
    """Long table: A has 10 hits / 5 misses / 5 false alarms per case at 34 and 6/4/2 at 48. B adds `b_gain`
    hits and false alarms removed (hits+, fa-); C is identical to A unless c_gain; b_pod_loss moves storm hits
    to misses; b_area adds forecast cells."""
    days = [dt.datetime(2025, 11, 1) + dt.timedelta(days=i) for i in range(150)]
    held = [d for d in days if cases.held_out(d)]
    assert len(held) > 20
    rows = []
    for basin in ("natl", "npac"):
        for d in held:
            for step in (24, 48):
                for v in "ABC":
                    gh, gf = b_gain if v == "B" else c_gain if v == "C" else (0, 0)
                    loss = b_pod_loss if v == "B" else 0
                    rows.append(dict(basin=basin, cycle=pd.Timestamp(d), step=step, split="held_out", variant=v,
                                     product="corelift", mode="real", nt34=30, h34=10 + gh, m34=5 - gh,
                                     fa34=5 - gf, nt48=12, h48=6 - loss, m48=4 + loss, fa48=2, fc34=1000,
                                     ob34=1000 if v != "B" else 1000 + b_area, fc48=100, ob48=100,
                                     b_n=3, b_sum_err=1.0, b_sum_abs=3.0))
    d = pd.DataFrame(rows)
    d["method"] = d["variant"] + "|" + d["product"]
    return d


def _verdict(d):
    lv = S.levels(d)
    df = S.differences(d, 200)
    return S.win_line(lv, df, "corelift"), lv


def test_win_line_passes_and_picks_b():
    (w, chk, why), lv = _verdict(_counts())
    assert w == "B" and chk[chk.variant == "B"].passed.all(), why
    assert not chk[chk.variant == "C"].passed.all()      # C equals A: CSI not higher


def test_win_line_storm_pod_margin_blocks():
    # storm hits drop 6 -> 5 of 10 per case: POD down 10 points, more than the 2-point margin
    (w, chk, why), _ = _verdict(_counts(b_pod_loss=1))
    assert w == "A" and "neither" in why


def test_win_line_area_blocks():
    # A's gale area ratio is exactly 1; B's is off 1 -> test 3 fails
    (w, chk, why), _ = _verdict(_counts(b_area=500))
    assert w == "A"


def test_both_pass_higher_csi_wins():
    (w, _, why), _ = _verdict(_counts(b_gain=(1, 0), c_gain=(3, 0)))
    assert w == "C" and "higher gale CSI" in why


def test_levels_ratios():
    lv = S.levels(_counts())
    r = lv[(lv.basin == "natl") & (lv.variant == "A") & (lv["step"] == "all")].iloc[0]
    assert abs(r.csi34 - 10 / 20) < 1e-9 and abs(r.pod48 - 0.6) < 1e-9 and abs(r.far48 - 2 / 8) < 1e-9
    assert abs(r.buoy_bias - 1 / 3) < 1e-9 and abs(r.area34 - 1) < 1e-9


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
