#!/usr/bin/env python3
"""Does the time-lagged part of the GFE deterministic blend earn its place? (Jason 2026-10-29)

  python3 run.py [--split held_out] [--workers 4] [--out DIR]

Base wind from GFS + ECMWF only (the AI-GFS study's winner), four ways, each also with the GEFS storm lift:
  L0     latest runs only, support-weighted between the two (lags none), no spread term
  L0s    latest runs only + min(0.3 x SD of the 2 runs, 5 kt)
  LAG    support counted over current + 12 h + 24 h older runs (6 runs), no spread term
  LAGs   the PR #95 recipe: LAG + min(0.3 x SD of the 6 runs, 5 kt)            (= "N" in the AI-GFS study)
  *+g    + 5 kt where the GEFS 48 kt share (neighbourhood max, rk.features NB box) >= 0.25 on candidate cells
         (base >= 28 kt or either model >= 34 kt); the no-model lift of the GEFS-only study (x set there on tune).
Cases, truth and counts as studies/2026-10-28-aigfs-in-gfe-blend/run.py (whose helpers this imports): natl 12 UTC
cycles +24..+120, npac 00/12 UTC cycles +24..+120 and +30..+126; ASCAT real 10 m, 5x5 deg tiles. Nothing is fitted.
"""
import argparse
import datetime as dt
import importlib.util
import json
import multiprocessing as mp
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import ndimage  # noqa: E402

from rk import cases, features, paths, score, store, truth  # noqa: E402
from rk.basins import grid  # noqa: E402

_spec = importlib.util.spec_from_file_location("aig", HERE.parent / "2026-10-28-aigfs-in-gfe-blend" / "run.py")
aig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(aig)

MODELS = ("gfs", "ifs")
BASES = {"L0": dict(lags=(), k=0.0), "L0s": dict(lags=(), k=features.NOMEM_K),
         "LAG": dict(lags=(12, 24), k=0.0), "LAGs": dict(lags=(12, 24), k=features.NOMEM_K)}
LIFT_KT, GEFS_X = 5.0, 0.25


def case_job(job):
    basin, cycle, step, out = job
    cp = aig.cache_path(out, basin, cycle, step)
    if cp.exists():
        return job, "existing", json.load(open(cp))
    valid = cycle + dt.timedelta(hours=step)
    bases = {}
    for v, kw in BASES.items():
        b = features.det_blend(basin, cycle, step, models=MODELS, **kw)
        if b is None:
            return job, "missing_inputs", []
        bases[v] = b["r10"]
    g = store.load_ens(basin, cycle, "gefs", step)
    dets = [store.load_det(basin, cycle, m, step) for m in MODELS]
    if g is None or any(d is None for d in dets):
        return job, "missing_inputs", []
    p48nb = ndimage.maximum_filter(np.asarray(g["p48"], np.float32), size=features.NB, mode="nearest")
    modmax = np.max([d["speed"] for d in dets], axis=0)
    t = truth.ascat_target(basin, valid)
    if t is None:
        return job, "missing_ascat", []
    lats, lons = grid(basin)
    seen, spd = t["seen"], t["spd"]
    key = {"basin": basin, "cycle": cases.tag(cycle), "step": step, "valid_hr": valid.hour,
           "split": cases.split(cycle)}
    rows = []
    for v, base in bases.items():
        lift = (p48nb >= GEFS_X) & ((base >= 28) | (modmax >= 34))
        for name, f in ((v, base), (v + "+g", np.where(lift, base + LIFT_KT, base).astype(np.float32))):
            r = dict(key, variant=name)
            for thr in aig.THRS:
                h, m, fl = score.tile_counts(score.tile_hits(f, spd, seen, lats, lons, thr))
                r.update({"h%d" % thr: h, "m%d" % thr: m, "fa%d" % thr: fl,
                          "fc%d" % thr: int(((f >= thr) & seen).sum()),
                          "ob%d" % thr: int(((spd >= thr) & seen).sum())})
            rows.append(r)
    cp.parent.mkdir(parents=True, exist_ok=True)
    tmp = cp.with_suffix(".tmp")
    json.dump(rows, open(tmp, "w"))
    os.replace(tmp, cp)
    return job, "done", rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    ap.add_argument("--split", default="held_out", choices=["held_out", "tune", "all"])
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    out = Path(a.out) if a.out else paths.data("extra", "lagged-runs")
    out.mkdir(parents=True, exist_ok=True)
    jobs = [(b, c, s, str(out)) for b, c, s in aig.case_list(("natl", "npac"), *aig.WINDOW, a.split)]
    tally, rows = {}, []
    with mp.get_context("spawn").Pool(a.workers) as pool:
        for job, st, r in pool.imap_unordered(case_job, jobs, chunksize=2):
            tally[st] = tally.get(st, 0) + 1
            rows += r
    print("cases", len(jobs), tally, flush=True)
    pd.DataFrame(rows).to_csv(out / "case_counts.csv", index=False)


if __name__ == "__main__":
    main()
