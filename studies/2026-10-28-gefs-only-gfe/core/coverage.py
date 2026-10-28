#!/usr/bin/env python3
"""Which inputs exist for each case (basin, cycle, step): GFS, IFS, GEFS, GFS and IFS low-level files, and the
lag runs det_blend needs. Pulls (only the gfs/ifs/gefs members of) every cycle zip it touches into RK_CACHE.

  python3 coverage.py [--workers 3]   -> RK_DATA/extra/gefs-only-gfe/core/coverage.csv
"""
import argparse
import datetime as dt
import multiprocessing as mp
import sys
from pathlib import Path

import gcommon as G
from rk import cases, store
import pandas as pd

WINDOW = (dt.datetime(2025, 11, 1), dt.datetime(2026, 3, 31))
STEPS_A = (24, 48, 72, 96, 120)
STEPS_B = (30, 54, 78, 102, 126)


def one(job):
    G.install()
    basin, cycle, step = job
    ok = lambda m, c, s: store._locate(basin, c, "%s_f%03d" % (m, s)) is not None
    lk = lambda m: store._locate(basin, cycle, "%s_low_f%03d" % (m, step)) is not None
    r = {"basin": basin, "cycle": cases.tag(cycle), "step": step, "split": cases.split(cycle),
         "gfs": ok("gfs", cycle, step), "ifs": ok("ifs", cycle, step), "gefs": ok("gefs", cycle, step),
         "gfs_low": lk("gfs"), "ifs_low": lk("ifs")}
    lag = True
    for L in (12, 24):
        c = cycle - dt.timedelta(hours=L)
        lag = lag and ok("gfs", c, step + L) and ok("ifs", c, step + L)
    r["lags"] = lag
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    jobs = []
    for b in ("natl", "npac"):
        for h in (0, 12):
            for c in cases.cycles(b, *WINDOW, hour=h):
                for s in STEPS_A + STEPS_B:
                    jobs.append((b, c, s))
    G.install()
    with mp.get_context("spawn").Pool(a.workers) as pool:
        rows = pool.map(one, jobs, chunksize=10)
    df = pd.DataFrame(rows)
    out = G.root() / "coverage.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print("wrote", out, len(df))


if __name__ == "__main__":
    main()
