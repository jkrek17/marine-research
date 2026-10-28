#!/usr/bin/env python3
"""Live Core Lifted (the page's blend, all ensembles, the live core model) on the TUNE cases, the way the retrain
and gale-core studies compute it (retrain predict.py "live": rk.features.core with every model and ensemble, the
live model core_model.json on the live candidate cells, blend + 5 kt where P >= 0.35).

  python3 live.py [--workers 3] [--max-cycles N]
      -> <core root>/live/<basin>/<cycle>_f<step>.npz   blend, corelift (float16 kt), P (float16)

Held-out cases need no run: the retrain wrote them (RK_DATA/extra/core-lift-retrain/corelift-heldout). Tune
cycles are pulled whole (AIFS, ENS and AIFS ENS members too) and the members this study does not read are
removed again, so the cache stays small.
"""
import argparse
import datetime as dt
import multiprocessing as mp
import os
import sys
import time

import gcommon as G
import common as C
import numpy as np
from rk import cases

STEPS = cases.STEPS


def init():
    G.install()
    os.environ["AWIPS_TOOLS"] = str(__import__("pathlib").Path(G.awips_pipeline()).parents[1])
    sys.path.insert(0, G.awips_pipeline())


def job(j):
    basin, cycle = j
    done = missing = 0
    G.pull_full(basin, cycle)
    for step in STEPS:
        p = G.live_path(basin, cycle, step)
        if p.exists():
            continue
        f = G.raw_core(basin, cycle, step)
        if f is None:
            missing += 1
            continue
        m, _ = C.live_model()
        ij = np.nonzero(f["cand"])
        P = np.zeros(f["cand"].shape, np.float16)
        if len(ij[0]):
            X = np.column_stack([f[k][ij] for k in m["features"]])
            P[ij] = C.live_predict(X)
        r10 = f["r10"].astype(np.float16)
        cl = np.where(P.astype(np.float64) >= 0.35, f["r10"] + 5.0, f["r10"]).astype(np.float16)
        C.save_npz(p, blend=r10, corelift=cl, P=P)
        done += 1
    G.trim(basin, cycle)
    return j, done, missing


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--max-cycles", type=int, default=None)
    a = ap.parse_args()
    jobs = []
    for b in ("natl", "npac"):
        cyc = sorted(cases.cycles(b, *C.WINDOW, hour=0) + cases.cycles(b, *C.WINDOW, hour=12))
        cyc = [c for c in cyc if not cases.held_out(c)]
        jobs += [(b, c) for c in (cyc[:a.max_cycles] if a.max_cycles else cyc)]
    print("tune cycles: %d" % len(jobs), flush=True)
    tot = [0, 0]
    t0 = time.time()
    with mp.get_context("spawn").Pool(a.workers, initializer=init) as pool:
        for i, (j, d, m) in enumerate(pool.imap_unordered(job, jobs), 1):
            tot[0] += d
            tot[1] += m
            if i % 20 == 0 or i == len(jobs):
                print("[%d/%d] %.0fs live grids %d, missing inputs %d" % (i, len(jobs), time.time() - t0, *tot), flush=True)
    print("SUMMARY: live grids written %d, cases with missing inputs %d" % tuple(tot))


if __name__ == "__main__":
    main()
