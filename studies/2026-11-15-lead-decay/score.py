#!/usr/bin/env python3
"""Score Best Wind, the raw models, the blend and the three warning lines against ASCAT by lead (design.md).

  python3 score.py [--workers 3]

Cases: the most-likely-wind case build (studies/2026-11-07-most-likely-wind/build_cases.py), winter 2025-26, both
basins, every 00/12Z run, steps 24..120 (+ 06/18Z-valid steps 30/54/78/102). All weeks (nothing is tuned here).

Products (kt), as live in the winter build:
  gfs ifs aifs   raw deterministic
  blend          page blend (support-weighted GFS/ECMWF/AIFS, AIFS x0.5, + spread term)
  best           Best Wind: blend + ramps + HF core (most-likely-wind score_cells.best) with the 80% gale-core floor
                 (awips-tools storm.BEST_GALE_P, live since 7 Nov 2026)
Lines (awips-tools storm.warning_areas), clipped to open water inside the OPC High Seas area:
  gale   strongest of GFS/ECMWF/AIFS >= 30, pieces under 32 cells dropped
  storm  Core Lifted >= 39
  hf     strongest >= 44 and >= 1% of all GEFS+ENS+AIFS ENS members at 64 kt within +-4 cells (9x9 max)
Truth: RSS ASCAT real 10 m (rk.truth.ascat_target via the case files), seen open-water cells.

Writes (study folder, small):
  grid_cases.csv.gz   per case x product: tile counts and cell counts at 34/48/64 (fit_score.Tiles)
  line_cases.csv.gz   per case x line: rk.score.warning_events counts at the line's own level
  hist.npz            per basin x step x product, cases with the core chances only: 1 kt histograms of the grid over
                      seen cells and over seen cells with ASCAT >= 34/48/64 (equal-area catch)
Cases without the core chances (P, Pg) still score raw models, blend, gale and HF lines; best and storm need them.
"""
import argparse
import gzip
import multiprocessing as mp
import os
import shutil
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parent / "2026-11-05-core-lift-bias"))
sys.path.insert(0, str(HERE.parent / "2026-11-07-most-likely-wind"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import ndimage  # noqa: E402

import fit_score as F  # noqa: E402
import score_cells as S  # noqa: E402
from rk import basins, cases, paths, score, store  # noqa: E402

BEST_GALE_P = 0.80
GALE_KT, GALE_MIN, STORM_KT, HF_KT, HF_M64, HF_NB = 30.0, 32, 39.0, 44.0, 0.01, 9
LINES = {"gale": 34, "storm": 48, "hf": 64}
GRID = ("gfs", "ifs", "aifs", "blend", "best")
NBIN = 120
KEYS = ("events", "hits", "hits_on", "obs_cells", "obs_in", "cells", "bad_cells", "warned_cells")


def drop_small(m, nmin):
    lab, n = ndimage.label(m, structure=np.ones((3, 3)))
    if n == 0:
        return m
    size = np.bincount(lab.ravel())
    keep = size >= nmin
    keep[0] = False
    return keep[lab]


def p64_all(basin, cyc, step):
    """Share of all GEFS + ENS + AIFS ENS members at 64+ kt (store member statistics, weighted by member count)."""
    num, den = None, 0
    for e in store.ENS:
        for attempt in range(4):
            try:
                z = store.load_ens(basin, cyc, e, step)
                break
            except Exception:   # connection reset on the release download; retry, then give up on the HF line
                if attempt == 3:
                    raise
                time.sleep(5 * (attempt + 1))
        if z is None:
            continue
        n = int(np.asarray(z["n"]).ravel()[0])
        p = np.nan_to_num(np.asarray(z["p64"], np.float32))
        num = p * n if num is None else num + p * n
        den += n
    return None if den == 0 else num / den


def load(path, basin):
    z = np.load(path)
    d = {k: (z[k].astype(np.float32) if z[k].dtype == np.float16 else z[k]) for k in z.files}
    lats, _ = basins.grid(basin)
    d["lift_on"] = d["ocean"] & (np.abs(lats)[:, None] >= S.MIN_LAT)
    return d


def job(args):
    basin, cyc, step, path = args
    d = load(path, basin)
    seen = d["seen"] & d["ocean"] & np.isfinite(d["spd"])
    ob = np.where(seen, d["spd"], np.nan)
    obn = np.nan_to_num(ob, nan=-1)
    has_core = "P" in d
    blend = d["base05"] + d["boost"]
    prods = {"gfs": d["gfs"], "ifs": d["ifs"], "aifs": d["aifs"], "blend": blend}
    if has_core:
        raw = S.best(blend, dict(d, Pg=np.zeros_like(d["Pg"])))   # S.best floors at 60%; live floor is 80%
        prods["best"] = np.where(d["Pg"] >= BEST_GALE_P, np.maximum(raw, 34.0), raw)
    wk = "%d-%02d" % cyc.isocalendar()[:2]
    meta = dict(basin=basin, cycle=cyc.isoformat(), step=step, week=wk, core=int(has_core))
    tiles = F.Tiles(basin, seen)
    obi = {t: seen & (obn >= t) for t in F.THRS}
    grows, hists = [], {}
    for name, fc in prods.items():
        fcn = np.nan_to_num(np.asarray(fc, np.float32), nan=-1)
        r = dict(meta, product=name)
        for t in F.THRS:
            nt, h, m, fa = tiles.counts(fc, ob, t)
            f = seen & (fcn >= t)
            r.update({"nt%d" % t: nt, "h%d" % t: h, "m%d" % t: m, "fa%d" % t: fa, "fc%d" % t: int(f.sum()),
                      "ob%d" % t: int(obi[t].sum()), "cau%d" % t: int((f & obi[t]).sum())})
        grows.append(r)
        if not has_core:   # equal-area catch on the same cases for every product (Best Wind needs the core)
            continue
        bins = np.clip(fcn, 0, NBIN - 1).astype(int)
        hists[name] = np.stack([np.bincount(bins[m], minlength=NBIN) for m in (seen, obi[34], obi[48], obi[64])])
    opc = basins.opc_mask(basin) & d["ocean"]
    mx = np.fmax(np.fmax(np.nan_to_num(d["gfs"], nan=-1), np.nan_to_num(d["ifs"], nan=-1)),
                 np.nan_to_num(d["aifs"], nan=-1))
    lines = {"gale": drop_small((mx >= GALE_KT) & d["ocean"], GALE_MIN)}
    if has_core:
        lines["storm"] = np.nan_to_num(F.corelift(blend, d["P"], d["Pg"]), nan=-1) >= STORM_KT
    p64 = p64_all(basin, cyc, step)
    if p64 is not None:
        m64 = ndimage.maximum_filter(p64, size=HF_NB, mode="nearest")
        lines["hf"] = (mx >= HF_KT) & (m64 >= HF_M64)
    lrows = []
    for name, w in lines.items():
        r = score.warning_events(w, d["spd"], seen, LINES[name], mask=opc)
        lrows.append(dict(meta, line=name, **{k: int(r[k]) for k in KEYS}))
    return grows, lrows, (basin, step, hists)


def cycle_job(args):
    """All steps of one basin-cycle, then drop the cycle's unpacked store files (published, re-downloadable;
    a whole winter of them does not fit on the session disk)."""
    basin, cyc, items = args
    out = [job((basin, cyc, st, p)) for st, p in items]
    d = store._cache_dir(basin, cyc)
    if d.exists() and not (d / ".dirty").exists():
        shutil.rmtree(d, ignore_errors=True)
    return out


def all_cases():
    out = []
    for basin in ("natl", "npac"):
        for p in sorted(paths.cache("extra", "most-likely-wind", basin).glob("*.npz")):
            if p.name.endswith(".tmp.npz"):
                continue
            tg, st = p.stem.split("_f")
            out.append((basin, cases.parse(tg), int(st), p))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--max-cases", type=int, default=None, help="first N cases per basin (a smoke test)")
    a = ap.parse_args()
    jobs = all_cases()
    if a.max_cases:
        jobs = [j for b in ("natl", "npac") for j in [x for x in jobs if x[0] == b][:a.max_cases]]
    print("%d cases" % len(jobs), flush=True)
    by = {}
    for b, c, st, p in jobs:
        by.setdefault((b, c), []).append((st, p))
    cjobs = [(b, c, v) for (b, c), v in sorted(by.items())]
    G, L, H, t0 = [], [], {}, time.time()
    with mp.get_context("spawn").Pool(a.workers) as pool:
        for i, res in enumerate(pool.imap_unordered(cycle_job, cjobs), 1):
            for g, l, (b, st, hs) in res:
                G += g
                L += l
                for k, v in hs.items():
                    key = (b, str(st), k)
                    H[key] = H[key] + v if key in H else v
            if i % 50 == 0 or i == len(cjobs):
                print("[%d/%d cycles] %.0fs" % (i, len(cjobs), time.time() - t0), flush=True)
    for nm, rows in (("grid_cases", G), ("line_cases", L)):
        with gzip.open(HERE / ("%s.csv.gz" % nm), "wt") as fh:
            pd.DataFrame(rows).to_csv(fh, index=False)
    keys = sorted(H)
    np.savez_compressed(HERE / "hist.npz", keys=np.array(["|".join(k) for k in keys]),
                        hist=np.stack([H[k] for k in keys]))


if __name__ == "__main__":
    main()
