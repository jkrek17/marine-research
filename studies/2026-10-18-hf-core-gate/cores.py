#!/usr/bin/env python3
"""Core table: every forecast core (P >= 0.35 area) with an ASCAT pass, both basins, Nov 2025 - Mar 2026.

  AWIPS_TOOLS=<awips-tools checkout> python3 cores.py [--workers 6] [--limit N]

One row per core and forecast (cycle, step): forecast-time predictors and ASCAT truth (design.md).
Writes cores.csv here (small). Store cycles are evicted after use.
"""
import argparse
import datetime as dt
import multiprocessing as mp
import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import ndimage

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parent / "2026-10-17-core-ceiling"))
import ceiling as C  # noqa: E402  (live model, LOW_ROOT, evict, kth)
from rk import basins, features, score, store, truth  # noqa: E402

START, END = dt.datetime(2025, 11, 1), dt.datetime(2026, 4, 1)
STEPS = (24, 30, 48, 54, 72, 78)
P_CORE, MIN_AREA = 0.35, 20
MIN_SEEN, MIN_COVER, GROW = 100, 0.30, 2
HF_CELLS = 3
DEPTH_KM = 300.0
OUT = HERE / "cores.csv"


def jobs(limit=None):
    out, c = [], START
    while c < END:
        for b in ("natl", "npac"):
            out.append((b, c))
        c += dt.timedelta(hours=12)
    return out[:limit] if limit else out


def run_cycle(job):
    basin, cycle = job
    rows = []
    try:
        storm, model = C.live()
        la, lo = basins.grid(basin)
        LA, LO = np.meshgrid(la, lo, indexing="ij")
        for step in STEPS:
            valid = cycle + dt.timedelta(hours=step)
            f = features.core(basin, cycle, step)
            if f is None and C.LOW_ROOT.exists():
                f = features.core(basin, cycle, step, low_root=C.LOW_ROOT)
            det = [store.load_det(basin, cycle, m, step) for m in ("gfs", "ifs", "aifs")]
            ens = {e: store.load_ens(basin, cycle, e, step) for e in ("gefs", "ens")}
            if f is None or any(d is None for d in det):
                rows.append(dict(basin=basin, cycle=cycle, step=step, valid=valid, status="no_forecast"))
                continue
            seen, spd = truth.ascat_grid(basin, valid)
            if seen is None:
                rows.append(dict(basin=basin, cycle=cycle, step=step, valid=valid, status="no_ascat"))
                continue
            P = storm.core_grid(f, f["ocean"], model)
            msl = np.mean([d["msl"] for d in det], axis=0)
            emsl = [e["msl_mean"] for e in ens.values() if e is not None and "msl_mean" in e]
            emsl = np.mean(emsl, axis=0) if emsl else None
            esd = [e["msl_std"] for e in ens.values() if e is not None and "msl_std" in e]
            esd = np.mean(esd, axis=0) if esd else None
            lab, n = ndimage.label((P >= P_CORE) & f["ocean"], structure=np.ones((3, 3)))
            for k in range(1, n + 1):
                core = lab == k
                area = int(core.sum())
                if area < MIN_AREA:
                    continue
                grown = ndimage.binary_dilation(core, iterations=GROW)
                sc = seen & grown
                cover = (seen & core).sum() / area
                r = dict(basin=basin, cycle=cycle, step=step, valid=valid, core=k, area=area,
                         n_seen=int(sc.sum()), cover=float(cover))
                if sc.sum() < MIN_SEEN or cover < MIN_COVER:
                    rows.append(dict(r, status="few_seen"))
                    continue
                iy, ix = np.unravel_index(np.argmax(np.where(core, P, -1)), P.shape)
                near = score.km(LA, LO, LA[iy, ix], LO[iy, ix]) <= DEPTH_KM
                near = near | (ndimage.binary_dilation(core, iterations=12))     # ~300 km around the whole core
                jy, jx = np.unravel_index(np.argmin(np.where(near, msl, np.inf)), msl.shape)
                a = spd[sc]
                r.update(status="ok", lat=float(LA[iy, ix]), lon=float(LO[iy, ix]),
                         p_max=float(P[core].max()), p_mean=float(P[core].mean()),
                         r10_max=float(f["r10"][core].max()), r10_p95=float(np.percentile(f["r10"][core], 95)),
                         mod_max=float(f["mod_max"][core].max()), s925_max=float(np.nanmax(f["s925"][core])),
                         p64_max=float(f["p64"][core].max()),
                         msl_min=float(msl[jy, jx]),
                         drop=float(score.pressure_drop(msl, basin, LA[jy, jx], LO[jy, jx])[0]),
                         ascat_peak=float(a.max()), ascat_k5=C.kth(a, 5), ascat_n64=int((a >= 64).sum()),
                         ascat_n48=int((a >= 48).sum()))
                for e, s in ens.items():
                    r[e + "_p64_max"] = float(s["p64"][core].max()) if s is not None else np.nan
                if emsl is not None:
                    r["ens_msl_min"] = float(np.min(np.where(near, emsl, np.inf)))
                    r["ens_msl_sd"] = float(esd[jy, jx]) if esd is not None else np.nan
                r["hf"] = int(r["ascat_n64"] >= HF_CELLS)
                rows.append(r)
    except Exception:
        traceback.print_exc()
        rows.append(dict(basin=basin, cycle=cycle, status="error"))
    finally:
        C.evict(basin, cycle)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    todo = jobs(a.limit)
    print("cycles: %d" % len(todo), flush=True)
    rows = []
    with mp.get_context("spawn").Pool(a.workers) as pool:
        for n, r in enumerate(pool.imap_unordered(run_cycle, todo), 1):
            rows += r
            if n % 40 == 0 or n == len(todo):
                print("%d/%d" % (n, len(todo)), flush=True)
                pd.DataFrame(rows).to_csv(OUT, index=False, float_format="%.3f")


if __name__ == "__main__":
    main()
