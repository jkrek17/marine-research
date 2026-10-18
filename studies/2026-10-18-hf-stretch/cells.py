#!/usr/bin/env python3
"""Cell table for the core stretch test: every cell within 500 km of a core-ceiling case (design.md).

  AWIPS_TOOLS=<awips-tools checkout> python3 cells.py [--workers 6] [--limit N]

Columns per cell: case keys (basin, event_id, valid, lead, step, cycle, category), iy, ix (basin grid index),
seen, ascat (kt, NaN unseen), r10, P, vg (geostrophic speed from the three-model mean MSLP, kt), and per case
drop (hPa, rk.score.pressure_drop at the mean-MSLP low nearest the fix). Only cases with status ok (at least
200 seen cells). Writes RK_CACHE/extra/hf-stretch/cells.parquet and cases.csv here.
"""
import argparse
import multiprocessing as mp
import os
import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import ndimage

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parent / "2026-10-17-core-ceiling"))
import ceiling as C  # noqa: E402
from rk import KT, basins, features, paths, score, store, truth  # noqa: E402

OUT_CELLS = paths.cache("extra", "hf-stretch", "cells.parquet")
OUT_CASES = HERE / "cases.csv"
OMEGA, RHO = 7.292e-5, 1.25


def geostrophic(msl, basin):
    """Geostrophic speed (kt) from MSLP (hPa) on the 0.25 deg basin grid, smoothed one cell."""
    lats, _ = basins.grid(basin)
    p = ndimage.gaussian_filter(np.asarray(msl, float), 1.0) * 100.0
    dy = 0.25 * 111.19e3
    dx = dy * np.cos(np.radians(lats))[:, None]
    gy, gx = np.gradient(p, axis=0) / dy, np.gradient(p, axis=1) / dx
    f = 2 * OMEGA * np.sin(np.radians(lats))[:, None]
    return np.hypot(gx, gy) / (RHO * np.abs(f)) * KT


def low_drop(msl, basin, lat, lon):
    lows = score.find_lows(msl, basin, below=1020.0)
    m = score.match_lows(pd.DataFrame({"lat": [lat], "lon": [lon], "hpa": [np.nan]}), lows, 300.0).iloc[0]
    la, lo = (m.fc_lat, m.fc_lon) if m.matched else (lat, lon)
    return score.pressure_drop(msl, basin, la, lo)[0]


def run_cycle(item):
    (basin, cycle), cases_ = item
    cells, rows = [], []
    try:
        storm, model = C.live()
        for step in sorted({c["step"] for c in cases_}):
            f = features.core(basin, cycle, step)
            if f is None and C.LOW_ROOT.exists():
                f = features.core(basin, cycle, step, low_root=C.LOW_ROOT)
            det = [store.load_det(basin, cycle, m, step) for m in ("gfs", "ifs", "aifs")]
            if f is None or any(d is None for d in det):
                rows += [dict(c, cycle=cycle, status="no_forecast") for c in cases_ if c["step"] == step]
                continue
            P = storm.core_grid(f, f["ocean"], model)
            msl = np.mean([d["msl"] for d in det], axis=0)
            vg = geostrophic(msl, basin)
            for c in (c for c in cases_ if c["step"] == step):
                seen, spd = truth.ascat_grid(basin, c["valid"])
                if seen is None:
                    rows.append(dict(c, cycle=cycle, status="no_ascat"))
                    continue
                circ = C.circle(basin, c["lat"], c["lon"])
                if (seen & circ).sum() < C.MIN_SEEN:
                    rows.append(dict(c, cycle=cycle, status="few_seen"))
                    continue
                drop = low_drop(msl, basin, c["lat"], c["lon"])
                rows.append(dict(c, cycle=cycle, status="ok", drop=drop, n_seen=int((seen & circ).sum())))
                iy, ix = np.where(circ & f["ocean"])
                df = pd.DataFrame({"iy": iy.astype(np.int16), "ix": ix.astype(np.int16), "seen": seen[iy, ix],
                                   "ascat": np.where(seen[iy, ix], spd[iy, ix], np.nan).astype(np.float32),
                                   "r10": f["r10"][iy, ix].astype(np.float32), "P": P[iy, ix].astype(np.float32),
                                   "vg": vg[iy, ix].astype(np.float32)})
                for k in ("basin", "event_id", "valid", "lead", "step", "category"):
                    df[k] = c[k]
                df["cycle"], df["drop"] = cycle, np.float32(drop)
                cells.append(df)
    except Exception:
        traceback.print_exc()
        rows += [dict(c, cycle=cycle, status="error") for c in cases_]
    finally:
        C.evict(basin, cycle)
    return rows, cells


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    todo = C.jobs(["HF", "S"], a.limit)
    print("cycles to do: %d" % len(todo), flush=True)
    rows, cells = [], []
    with mp.get_context("spawn").Pool(a.workers) as pool:
        for n, (r, c) in enumerate(pool.imap_unordered(run_cycle, todo), 1):
            rows += r
            cells += c
            if n % 40 == 0 or n == len(todo):
                print("%d/%d cycles" % (n, len(todo)), flush=True)
    pd.DataFrame(rows).to_csv(OUT_CASES, index=False)
    tab = pd.concat(cells, ignore_index=True)
    OUT_CELLS.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_CELLS.with_suffix(".tmp")
    tab.to_parquet(tmp, index=False)
    os.replace(tmp, OUT_CELLS)
    print("cells: %d (%d seen, %d >= 64 kt in ASCAT) -> %s" % (
        len(tab), int(tab.seen.sum()), int((tab.ascat >= 64).sum()), OUT_CELLS), flush=True)


if __name__ == "__main__":
    main()
