#!/usr/bin/env python3
"""Cell table: every ASCAT-seen cell near an archive low with >= 64 kt at 925 mb, with its physical inputs.

  AWIPS_TOOLS=<awips-tools checkout> python3 cells.py [--workers 6] [--limit N]

Cases are the core-ceiling cases (studies/2026-10-17-core-ceiling/ceiling.py: archive HF and S fixes, every
synoptic hour, Nov 2025 - Mar 2026, +24/+48/+72 h, at least 200 ASCAT cells within 500 km). Candidate cells:
seen and within 500 km of the fix and three-model mean 925 mb speed s925 >= 64 kt. Columns: case keys, the
28 core features at the cell, the live core probability P, distance (km) and bearing (deg from north) from the
fix, ASCAT speed (kt) and y = ASCAT >= 64. Also one summary row per case in cases.csv (n_seen, n_cand).
Writes RK_CACHE/extra/hf-mixing/cells.parquet (too big for git) and cases.csv here.
"""
import argparse
import multiprocessing as mp
import os
import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parent / "2026-10-17-core-ceiling"))
import ceiling as C  # noqa: E402  (case list, live model, circle, filled low-level files)
from rk import basins, features, paths, score, truth  # noqa: E402

THR_ALOFT = 64.0
OUT_CELLS = paths.cache("extra", "hf-mixing", "cells.parquet")
OUT_CASES = HERE / "cases.csv"


def bearing(lat0, lon0, lat, lon):
    p0, p1, dl = np.radians(lat0), np.radians(lat), np.radians(lon - lon0)
    x = np.sin(dl) * np.cos(p1)
    y = np.cos(p0) * np.sin(p1) - np.sin(p0) * np.cos(p1) * np.cos(dl)
    return (np.degrees(np.arctan2(x, y)) + 360) % 360


def run_cycle(item):
    (basin, cycle), cases_ = item
    cells, rows = [], []
    try:
        storm, model = C.live()
        la, lo = basins.grid(basin)
        LA, LO = np.meshgrid(la, lo, indexing="ij")
        for step in sorted({c["step"] for c in cases_}):
            f = features.core(basin, cycle, step)
            if f is None and C.LOW_ROOT.exists():
                f = features.core(basin, cycle, step, low_root=C.LOW_ROOT)
            if f is None:
                rows += [dict(c, cycle=cycle, status="no_forecast") for c in cases_ if c["step"] == step]
                continue
            P = storm.core_grid(f, f["ocean"], model)
            for c in (c for c in cases_ if c["step"] == step):
                seen, spd = truth.ascat_grid(basin, c["valid"])
                if seen is None:
                    rows.append(dict(c, cycle=cycle, status="no_ascat"))
                    continue
                circ = C.circle(basin, c["lat"], c["lon"])
                sc = seen & circ
                if sc.sum() < C.MIN_SEEN:
                    rows.append(dict(c, cycle=cycle, status="few_seen", n_seen=int(sc.sum())))
                    continue
                cand = sc & (f["s925"] >= THR_ALOFT)
                rows.append(dict(c, cycle=cycle, status="ok", n_seen=int(sc.sum()), n_cand=int(cand.sum()),
                                 n64=int((sc & (spd >= 64)).sum()), n64_cand=int((cand & (spd >= 64)).sum())))
                if not cand.any():
                    continue
                d = {k: np.asarray(f[k], np.float32)[cand] for k in features.FEATURES}
                d["P"] = P[cand]
                d["dist_km"] = score.km(LA[cand], LO[cand], c["lat"], c["lon"]).astype(np.float32)
                d["bearing"] = bearing(c["lat"], c["lon"], LA[cand], LO[cand]).astype(np.float32)
                d["ascat"] = spd[cand].astype(np.float32)
                df = pd.DataFrame(d)
                for k in ("basin", "event_id", "valid", "lead", "step", "category", "hpa"):
                    df[k] = c[k]
                df["cycle"] = cycle
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
    tmp = OUT_CELLS.with_suffix(".tmp")
    tab.to_parquet(tmp, index=False)
    os.replace(tmp, OUT_CELLS)
    print("cells: %d (%d >= 64 kt in ASCAT) -> %s" % (len(tab), int((tab.ascat >= 64).sum()), OUT_CELLS), flush=True)


if __name__ == "__main__":
    main()
