"""Score the day 5-7 bomb watch on held-out weeks (preregistration.md). Reads RK_DATA/bomb-d5-7/cells.parquet
(build.py); writes results/scores.csv, results/reliability.csv and results/calibration.json, prints the table.
Run once the cell table is complete: python3 score.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from rk import calibrate, paths, score  # noqa: E402

RES = HERE / "results"
DETS = ("det_gfs", "det_ifs", "det_aifs")
N_BOOT = 2000


def half(t):
    return np.where(pd.to_datetime(t.valid).dt.month.isin([11, 12, 1, 2, 3]), "winter", "summer")


def add_climatology(t):
    """Event frequency per basin, cell and half-year over training weeks; basin-pooled where < 20 cases."""
    t["half"] = half(t)
    tr = t[(t.split == "tune") & ~t.valid_held]
    g = tr.groupby(["basin", "cell", "half"]).event.agg(["mean", "size"]).rename(columns={"mean": "c", "size": "k"})
    b = tr.groupby(["basin", "half"]).event.mean().rename("cb")
    t = t.join(g, on=["basin", "cell", "half"]).join(b, on=["basin", "half"])
    t["clim"] = np.where(t.k.fillna(0) >= 20, t.c, t.cb)
    return t.drop(columns=["c", "k", "cb"])


def week(c):
    iso = pd.to_datetime(c).dt.isocalendar()
    return (iso.year * 100 + iso.week).values


def boot_bss(d, col, ref, seed=0):
    """BSS of col against ref with a 95% interval from resampling whole ISO weeks."""
    w = week(d.cycle)
    se = (d[col].values - d.event.values) ** 2
    sr = (d[ref].values - d.event.values) ** 2
    u, inv = np.unique(w, return_inverse=True)
    a, b = np.bincount(inv, se), np.bincount(inv, sr)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(u), (N_BOOT, len(u)))
    draws = 1 - a[idx].sum(1) / b[idx].sum(1)
    return 1 - a.sum() / b.sum(), np.percentile(draws, 2.5), np.percentile(draws, 97.5), len(u)


def boot_diff(d, col, other, seed=0):
    """Brier of col minus Brier of other, 95% whole-week interval."""
    w = week(d.cycle)
    x = (d[col].values - d.event.values) ** 2 - (d[other].values - d.event.values) ** 2
    u, inv = np.unique(w, return_inverse=True)
    s, n = np.bincount(inv, x), np.bincount(inv)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(u), (N_BOOT, len(u)))
    draws = s[idx].sum(1) / n[idx].sum(1)
    return s.sum() / n.sum(), np.percentile(draws, 2.5), np.percentile(draws, 97.5)


def slope(p, y):
    r = score.reliability(p, y, bins=10)
    r = r[r.n > 0]
    w = r.n.values
    x, f = r.mean_p.values, r.freq.values
    xm, fm = np.average(x, weights=w), np.average(f, weights=w)
    return float(np.sum(w * (x - xm) * (f - fm)) / np.sum(w * (x - xm) ** 2))


def main():
    t = pd.read_parquet(paths.data("bomb-d5-7", "cells.parquet"))
    t = add_climatology(t)
    RES.mkdir(exist_ok=True)
    tune = t[(t.split == "tune") & ~t.valid_held]
    held = t[t.split == "held_out"].copy()
    # method 2 vs 3 chosen on training weeks, then calibrated per lead on training weeks (method 4)
    pick = min(("p_raw", "p_eq"), key=lambda c: calibrate.brier(tune[c], tune.event))
    cal = {}
    for L, g in tune.groupby("lead"):
        cal[int(L)] = calibrate.fit_logistic(calibrate.table(g[pick], g.event))
        m = held.lead == L
        held.loc[m, "p_cal"] = calibrate.apply(held.loc[m, pick], *cal[int(L)])
    json.dump({"method": pick, "knots": cal}, open(RES / "calibration.json", "w"), indent=1)
    rows, rel = [], []
    for L, d in held.groupby("lead"):
        d = d.dropna(subset=list(DETS))
        for col in ("clim", "p_raw", "p_eq", "p_cal") + DETS:
            bss, lo, hi, nw = boot_bss(d, col, "clim")
            row = {"lead": L, "method": col, "brier": calibrate.brier(d[col], d.event), "bss": bss,
                   "bss_lo": lo, "bss_hi": hi, "auc": score.auc(d[col], d.event),
                   "slope": slope(d[col], d.event) if col.startswith("p_") else np.nan,
                   "cells": len(d), "events": int(d.event.sum()), "weeks": nw, "cycles": d.cycle.nunique()}
            if col == "p_cal":
                for det in DETS:
                    row["minus_" + det], row["lo_" + det], row["hi_" + det] = boot_diff(d, "p_cal", det)
            rows.append(row)
        r = score.reliability(d.p_cal, d.event, bins=10)
        r["lead"] = L
        rel.append(r)
    s = pd.DataFrame(rows)
    s.to_csv(RES / "scores.csv", index=False, float_format="%.5f")
    pd.concat(rel).to_csv(RES / "reliability.csv", index=False, float_format="%.5f")
    with pd.option_context("display.width", 200, "display.max_columns", 30):
        print("chosen share:", pick)
        print(s.round(4))
    c = s[s.method == "p_cal"]
    ok = (c.bss_lo > 0) & c.slope.between(0.8, 1.25) & \
        (c[["minus_" + x for x in DETS]].max(axis=1) < 0)
    print("pass by lead:", dict(zip(c.lead, ok)))


if __name__ == "__main__":
    main()
