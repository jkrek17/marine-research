"""Score the day 5-7 bomb share on the GEFSv12 reforecast cell table (build.py) against ERA5 (proxy): raw share,
the live logistic remap and the pooled remap (design.md). Methods are compared on training weeks (10-fold
by week); held-out weeks are scored once. Writes results/scores.csv, results/reliability.csv,
results/cv.csv and results/calibration.json, and prints the pass/fail of the design's rule.
Run: python3 score.py
"""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from rk import calibrate, paths, score  # noqa: E402

# reuse the day 5-7 study's whole-week bootstrap and reliability slope
_spec = importlib.util.spec_from_file_location("d57", HERE.parent / "2026-10-19-bomb-d5-7" / "score.py")
d57 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(d57)

RES = HERE / "results"
METHODS = ("logistic", "pooled")


def fit(method, d):
    tab = calibrate.table(d.p_raw, d.event)
    lg = calibrate.fit_logistic(tab)
    return lg if method == "logistic" else calibrate.fit_pooled(tab, prior=lg, nmin=500)


def add_climatology(t):
    """Event frequency per basin and cell over training weeks (winter only); basin-pooled where < 20 cases."""
    tr = t[(t.split == "tune") & ~t.valid_held]
    g = tr.groupby(["basin", "cell"]).event.agg(["mean", "size"]).rename(columns={"mean": "c", "size": "k"})
    b = tr.groupby("basin").event.mean().rename("cb")
    t = t.join(g, on=["basin", "cell"]).join(b, on="basin")
    t["clim"] = np.where(t.k.fillna(0) >= 20, t.c, t.cb)
    return t.drop(columns=["c", "k", "cb"])


def top(p, y, lo=0.3):
    k = p >= lo
    return int(k.sum()), float(p[k].mean()) if k.any() else np.nan, float(y[k].mean()) if k.any() else np.nan


def main():
    t = add_climatology(pd.read_parquet(paths.data("bomb-reforecast", "cells.parquet")))
    RES.mkdir(exist_ok=True)
    tune = t[(t.split == "tune") & ~t.valid_held].copy()
    held = t[t.split == "held_out"].copy()
    wk = d57.week(tune.cycle)
    u = np.unique(wk)
    fold = dict(zip(u, np.random.default_rng(0).permutation(len(u)) % 10))
    tune["fold"] = [fold[w] for w in wk]
    cv = []
    for L, g in tune.groupby("lead"):
        y = g.event.values.astype(float)
        row = {"lead": L, "raw_brier": np.mean((g.p_raw.values - y) ** 2), "raw_slope": d57.slope(g.p_raw.values, y)}
        for m in METHODS:
            pc = np.zeros(len(g))
            for f in range(10):
                k = (g.fold == f).values
                pc[k] = calibrate.apply(g.p_raw.values[k], *fit(m, g[~k]))
            n, s, o = top(pc, y)
            row.update({m + "_brier": np.mean((pc - y) ** 2), m + "_slope": d57.slope(pc, y),
                        m + "_top_n": n, m + "_top_stated": s, m + "_top_obs": o})
        cv.append(row)
    cv = pd.DataFrame(cv)
    cv.to_csv(RES / "cv.csv", index=False, float_format="%.5f")
    # simplest first: pooled stays in only if it beats logistic on training-week CV at both day 6 and day 7
    d67 = cv[cv.lead > 120]
    pick = "pooled" if (d67.pooled_brier < d67.logistic_brier).all() else "logistic"
    cal, rows, rel = {}, [], []
    for L, g in tune.groupby("lead"):
        cal[int(L)] = fit(pick, g)
        m = held.lead == L
        held.loc[m, "p_cal"] = calibrate.apply(held.loc[m, "p_raw"], *cal[int(L)])
    json.dump({"method": pick, "knots": cal}, open(RES / "calibration.json", "w"), indent=1)
    for L, d in held.groupby("lead"):
        for col in ("clim", "p_raw", "p_cal"):
            bss, lo, hi, nw = d57.boot_bss(d, col, "clim")
            n, s, o = top(d[col].values, d.event.values.astype(float))
            rows.append({"lead": L, "method": col, "brier": calibrate.brier(d[col], d.event), "bss": bss,
                         "bss_lo": lo, "bss_hi": hi, "auc": score.auc(d[col], d.event),
                         "slope": d57.slope(d[col].values, d.event.values) if col != "clim" else np.nan,
                         "top_n": n, "top_stated": s, "top_obs": o, "cells": len(d),
                         "events": int(d.event.sum()), "weeks": nw, "runs": d.cycle.nunique()})
        r = score.reliability(d.p_cal, d.event, bins=10)
        r["lead"] = L
        rel.append(r)
    s = pd.DataFrame(rows)
    s.to_csv(RES / "scores.csv", index=False, float_format="%.5f")
    pd.concat(rel).to_csv(RES / "reliability.csv", index=False, float_format="%.5f")
    with pd.option_context("display.width", 220, "display.max_columns", 40):
        print(cv.round(4))
        print("chosen remap:", pick)
        print(s.round(4))
    c = s[s.method == "p_cal"]
    ok = (c.bss_lo > 0) & c.slope.between(0.8, 1.25) & ((c.top_obs - c.top_stated).abs() <= 0.05)
    print("pass by lead:", dict(zip(c.lead, ok)))


if __name__ == "__main__":
    main()
