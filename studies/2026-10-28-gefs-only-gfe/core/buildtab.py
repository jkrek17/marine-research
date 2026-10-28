#!/usr/bin/env python3
"""Training tables for the GEFS-only core models: the retrain's build_table.build_case (same rows, thinning,
weights and ASCAT target) with rk.features.core patched to the GFE inputs (gcommon.install).

  python3 buildtab.py --low-models gfs,ifs [--workers 3] [--max-cycles N]

Four tables under <core root>/table/: q-storm, q-gale, h-storm, h-gale (q = GEFS at 0.25 deg, h = GEFS
subsampled to 0.5 deg and interpolated back, rk.features.half_deg; storm = ASCAT 48+ target on the live candidate
cells, gale = ASCAT 34+ target on the gale candidate cells). TUNE cycles only (00/12 UTC cycles, +24..+120): the
held-out weeks are not read here. The two variants and two targets of a case share one feature computation per
variant (gcommon keeps the last core result).
"""
import argparse
import multiprocessing as mp
import time

import gcommon as G
import common as C
from rk import cases

KINDS = (("storm", 48, "storm"), ("gale", 34, "gale"))


def init():
    G.install()


def job(j):
    basin, cycle, step, half, low_models = j
    import build_table as BT
    G.set_variant(half=half, low_models=low_models)
    out = {}
    for kind, thr, cand in KINDS:
        _, status, n, npos = BT.build_case((basin, cycle, step, str(G.table_dir(half, kind)), None, False,
                                            tuple(low_models), thr, cand))
        out[kind] = (status, n, npos)
    return j, out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--low-models", default="gfs,ifs")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--max-cycles", type=int, default=None)
    a = ap.parse_args()
    lm = tuple(a.low_models.split(","))
    jobs = []
    for b in ("natl", "npac"):
        cyc = sorted(cases.cycles(b, *C.WINDOW, hour=0) + cases.cycles(b, *C.WINDOW, hour=12))
        cyc = [c for c in cyc if not cases.held_out(c)]
        if a.max_cycles:
            cyc = cyc[:a.max_cycles]
        jobs += [(b, c, s, h, lm) for c in cyc for s in C.STEPS for h in (False, True)]
    print("jobs: %d (case x variant), low_models %s" % (len(jobs), lm), flush=True)
    tally = {}
    rows = {}
    t0 = time.time()
    with mp.get_context("spawn").Pool(a.workers, initializer=init) as pool:
        for i, (j, out) in enumerate(pool.imap_unordered(job, jobs, chunksize=4), 1):
            for kind, (st, n, npos) in out.items():
                k = (G.variant_name(j[3]), kind, st)
                tally[k] = tally.get(k, 0) + 1
                rows[k[:2]] = rows.get(k[:2], 0) + n
            if i % 100 == 0 or i == len(jobs):
                print("[%d/%d] %.0fs %s" % (i, len(jobs), time.time() - t0, tally), flush=True)
    print("SUMMARY: %s; new rows %s" % (tally, rows), flush=True)


if __name__ == "__main__":
    main()
