"""Build the cell table for the day 6-7 bomb watch on GEFSv12 reforecasts (design.md).

Stage 1 (lows): for each 00 UTC reforecast run, every other day from 1 Nov to 31 Mar (Jan-Mar 2000 to Mar
2019), the five members' MSLP at +96..+168 h (rk.fetch.gefs_reforecast) and ERA5 at 00 UTC on each valid day
(rk.truth.era5, a proxy analysis) are reduced at once to lows (rk.bomb.find_lows) and saved as
RK_DATA/bomb-reforecast/lows/YYYYMMDD.npz; fields are not kept. Resumable.
Stage 2 (cells): bombs and the 2 deg ocean-cell table, as the live layer counts them, into
RK_DATA/bomb-reforecast/cells.parquet.
Run: python3 build.py lows [WORKERS]; python3 build.py cells
"""
import datetime as dt
import functools
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from rk import basins, bomb, cases, fetch, paths, truth  # noqa: E402

LEADS = (120, 144, 168)
STEPS = (96, 120, 144, 168)
BASINS = ("natl", "npac")
GRID = {b: basins.grid(b) for b in BASINS}
LOWS = paths.data("bomb-reforecast", "lows", "x").parent
OUT = paths.data("bomb-reforecast", "cells.parquet")


def runs():
    """00 UTC run days: every other day of each 1 Nov - 31 Mar, Jan 2000 to Mar 2019 (the reforecast's span)."""
    out = []
    for y in range(1999, 2019):
        d = max(dt.datetime(y, 11, 1), dt.datetime(2000, 1, 1))
        while d <= dt.datetime(y + 1, 3, 31):
            out.append(d)
            d += dt.timedelta(days=2)
    return out


def _lows(field, b):
    return bomb.find_lows(field, *GRID[b])


@functools.lru_cache(maxsize=4096)
def era5_lows(valid):
    f = truth.era5(valid, cache=False)
    return None if f is None else {b: _lows(f[b], b) for b in BASINS}


def run_lows(day):
    """Lows of the five members at every step and of ERA5 at each valid time -> saved npz path, or None."""
    p = LOWS / (day.strftime("%Y%m%d") + ".npz")
    if p.exists():
        return p
    out = {}
    for m in fetch.REFORECAST_MEMBERS:
        f = fetch.gefs_reforecast(day, m, STEPS)
        if not f or any(s not in f for s in STEPS):
            print(day.date(), m, "missing", flush=True)
            return None
        for s in STEPS:
            for b in BASINS:
                out["m_%s_%s_%d" % (m, b, s)] = _lows(f[s][b], b)
    for s in STEPS:
        e = era5_lows(day + dt.timedelta(hours=s))
        if e is None:
            return None
        for b in BASINS:
            out["a_%s_%d" % (b, s)] = e[b]
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, **out)
    tmp.replace(p)
    return p


def stage_lows(workers=4):
    days = runs()
    done = 0
    with ThreadPoolExecutor(workers) as ex:
        for d, p in zip(days, ex.map(run_lows, days)):
            done += p is not None
            if done % 25 == 0:
                print(d.date(), "runs done", done, "of", len(days), flush=True)
    print("runs with lows:", done, "of", len(days))


def run_cells(p, cl):
    z = np.load(p)
    day = dt.datetime.strptime(p.stem, "%Y%m%d")
    rows = []
    for b, (clat, clon) in cl.items():
        for L in LEADS:
            ab = bomb.bombs(z["a_%s_%d" % (b, L - 24)], z["a_%s_%d" % (b, L)])
            hits = []
            for m in fetch.REFORECAST_MEMBERS:
                mb = bomb.bombs(z["m_%s_%s_%d" % (m, b, L - 24)], z["m_%s_%s_%d" % (m, b, L)])
                hits.append(bomb.near(mb[mb[:, 3] >= 1.0], clat, clon))
            df = pd.DataFrame({"event": bomb.near(ab[ab[:, 3] >= 1.0], clat, clon),
                               "n_anl_bombs": int((ab[:, 3] >= 1.0).sum()),
                               "p_raw": np.mean(hits, axis=0), "cell": np.arange(len(clat)),
                               "lat": clat, "lon": clon})
            df["basin"], df["cycle"], df["lead"] = b, day, L
            df["valid"] = day + dt.timedelta(hours=L)
            rows.append(df)
    return pd.concat(rows)


def stage_cells():
    cl = {b: bomb.ocean_cells(b, *GRID[b]) for b in BASINS}
    t = pd.concat([run_cells(p, cl) for p in sorted(LOWS.glob("*.npz")) if ".tmp" not in p.name], ignore_index=True)
    t["split"] = [cases.split(c) for c in t.cycle]
    t["valid_held"] = [cases.held_out(v) for v in t.valid]
    t["winter"] = [c.year if c.month >= 11 else c.year - 1 for c in t.cycle]
    t.to_parquet(OUT, index=False)
    g = t.groupby(["basin", "lead"])
    print(g.size().rename("cells").to_frame().join(g.event.mean().rename("event_rate")))
    print("runs", t.cycle.nunique(), "held-out runs", t[t.split == "held_out"].cycle.nunique(), "->", OUT)


if __name__ == "__main__":
    if sys.argv[1] == "lows":
        stage_lows(int(sys.argv[2]) if len(sys.argv) > 2 else 4)
    else:
        stage_cells()
