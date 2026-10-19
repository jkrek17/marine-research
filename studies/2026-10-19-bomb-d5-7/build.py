"""Build the cell table for the day 5-7 bomb watch: one row per (basin, cycle, lead, ocean cell) with the analysed
event, the raw and equal-weight member shares and each model's yes/no (preregistration.md).

Reads the stored day 5-7 MSLP (mslpd57_*, +96 from fetch96.py) through the pressure study's store_io.
Writes RK_DATA/bomb-d5-7/cells.parquet (too big for git) and prints counts.
Run: python3 build.py [FIRST LAST]   (cycle dates, default 20250301 20261001)
"""
import datetime as dt
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

import bomb
import bfetch as B
import store_io
from rk import paths, truth, cases

LEADS = (120, 144, 168)
ENS = {"gefs": "noaa", "ens": "ec", "aifsens": "ec"}
DETS = {"gfs": "noaa", "ifs": "ec", "aifs": "ec"}
OUT = paths.data("bomb-d5-7", "cells.parquet")


def ocean_cells(basin):
    """Cells whose 2 deg square is at least half open water (analysis mask, one winter day)."""
    a = truth.analysis(basin, dt.datetime(2026, 1, 15, 12))
    m = a["mask"]
    lats, lons = B.LATS[basin], B.LONS[basin]
    clat, clon = bomb.cells(basin)
    keep = np.zeros(clat.shape, bool)
    for i, (la, lo) in enumerate(zip(clat, clon)):
        r = np.abs(lats - la) <= 1.0
        c = np.abs(lons - lo) <= 1.0
        keep[i] = m[np.ix_(r, c)].mean() >= 0.5
    return clat[keep], clon[keep]


def _ymd(d):
    return d.strftime("%Y%m%d")


def load_cycle(ymd):
    fc = {s: store_io.get("fc", s, ymd) for s in ("noaa", "ec")}
    f96 = {s: store_io.get("fc96", s, ymd) for s in ("noaa", "ec")}
    return fc, f96


def arr(fc, f96, src, key):
    for z in (fc.get(src), f96.get(src)):
        if z and key in z:
            return z[key]
    return None


def member_lows(fc, f96, ens, basin, step):
    a = arr(fc, f96, ENS[ens], "low_%s_%s_%d" % (ens, basin, step))
    if a is None:
        return None
    return {int(m): bomb.dedupe(a[a[:, 0] == m][:, 1:].astype(float)) for m in np.unique(a[:, 0])}


def det_lows(fc, f96, model, basin, step):
    a = arr(fc, f96, DETS[model], "det_%s_%s_%d" % (model, basin, step))
    return None if a is None else bomb.find_lows(bomb.dec(a), B.LATS[basin], B.LONS[basin])


def anl_lows(day, basin):
    g = store_io.get("an", "noaa", day)
    i = store_io.get("an", "ec", day)
    f = [bomb.dec(z["an_%s_%s" % (n, basin)]) for z, n in ((g, "gfs"), (i, "ifs")) if z and "an_%s_%s" % (n, basin) in z]
    if len(f) < 2:
        return None
    return bomb.find_lows(0.5 * (f[0] + f[1]), B.LATS[basin], B.LONS[basin])


def one(ymd, cl):
    c0 = dt.datetime.strptime(ymd, "%Y%m%d").replace(hour=12)
    fc, f96 = load_cycle(ymd)
    if not all(fc.values()) or not all(f96.values()):
        return None
    rows = []
    for basin, (clat, clon) in cl.items():
        for L in LEADS:
            v = c0 + dt.timedelta(hours=L)
            a0, a1 = anl_lows(_ymd(v - dt.timedelta(days=1)), basin), anl_lows(_ymd(v), basin)
            if a0 is None or a1 is None:
                continue
            ab = bomb.bombs(a0, a1)
            event = bomb.near(ab[ab[:, 3] >= 1.0], clat, clon)
            out = {"event": event, "n_anl_bombs": np.full(clat.shape, int((ab[:, 3] >= 1.0).sum()))}
            shares, nmem = {}, 0
            for ens in ENS:
                p, n = member_lows(fc, f96, ens, basin, L - 24), member_lows(fc, f96, ens, basin, L)
                if p is None or n is None:
                    continue
                hits = []
                for m in n:
                    b = bomb.bombs(p.get(m, np.zeros((0, 3))), n[m])
                    hits.append(bomb.near(b[b[:, 3] >= 1.0], clat, clon))
                shares[ens] = (np.mean(hits, axis=0), len(hits))
                nmem += len(hits)
            if len(shares) < 3:
                continue
            out["p_raw"] = sum(s * k for s, k in shares.values()) / nmem
            out["p_eq"] = np.mean([s for s, _ in shares.values()], axis=0)
            for e, (s, _) in shares.items():
                out["p_" + e] = s
            for m in DETS:
                p, n = det_lows(fc, f96, m, basin, L - 24), det_lows(fc, f96, m, basin, L)
                if p is None or n is None:
                    out["det_" + m] = np.full(clat.shape, np.nan)
                    continue
                b = bomb.bombs(p, n)
                out["det_" + m] = bomb.near(b[b[:, 3] >= 1.0], clat, clon).astype(float)
            df = pd.DataFrame(out)
            df["cell"] = np.arange(len(clat))
            df["lat"], df["lon"] = clat, clon
            df["basin"], df["cycle"], df["lead"], df["valid"] = basin, c0, L, v
            rows.append(df)
    return pd.concat(rows) if rows else None


def main():
    a, b = (sys.argv[1:3] + ["20250301", "20261001"][len(sys.argv[1:3]):])
    cl = {bs: ocean_cells(bs) for bs in ("natl", "npac")}
    days = pd.date_range(a, b).strftime("%Y%m%d").tolist()
    parts = []
    with ProcessPoolExecutor(8) as ex:
        for d, r in zip(days, ex.map(one, days, [cl] * len(days))):
            if r is not None:
                parts.append(r)
            print(d, "ok" if r is not None else "skip", flush=True)
    t = pd.concat(parts, ignore_index=True)
    t["split"] = [cases.split(c) for c in t.cycle]
    t["valid_held"] = [cases.held_out(v) for v in t.valid]
    for c in ("event",):
        t[c] = t[c].astype(bool)
    t.to_parquet(OUT, index=False)
    g = t.groupby(["basin", "lead"])
    print(g.size().rename("cells").to_frame().join(g.event.mean().rename("event_rate")))
    print("cycles", t.cycle.nunique(), "held-out cycles", t[t.split == "held_out"].cycle.nunique(), "->", OUT)


if __name__ == "__main__":
    main()
