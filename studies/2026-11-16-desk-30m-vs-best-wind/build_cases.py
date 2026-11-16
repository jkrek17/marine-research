#!/usr/bin/env python3
"""Held-out per-case inputs for the desk-30m-vs-best-wind study (design.md): two existing builders run together so
each store cycle is downloaded once.

  python3 build_cases.py [--workers 3] [--basins natl,npac] [--max-cycles N]

For every held-out case (both basins, every 00/12Z cycle in the 5 held-out ISO weeks, steps 24..126 h, 06/18Z-valid
steps included) it calls, unchanged:
  2026-11-07-most-likely-wind/build_cases.case_job   -> rk.paths.cache("extra", "most-likely-wind", basin)
        gfs ifs aifs, base0/05/1, boost, P Pg, p48nb (page blend pieces and Best Wind inputs), ocean seen spd
  2026-11-06-strong-core-lift/build.case_job         -> rk.paths.cache("extra", "strong-core-lift", basin)
        det (GFE #95 blend), gfs ifs and their MSLP, GFS t2/skt/t925, IFS skt/t925 (Stability Height inputs),
        s925 sa (HF core), r10 P Pg, ocean seen spd anl
Nothing is pulled from NOAA or ECMWF: every input is in the rk.store releases (cycle zips) and the truth releases.
A worker walks consecutive cycles and drops each unpacked store cycle once no later cycle needs it as a lag run.
Resumable (written cases are skipped).
"""
import argparse
import importlib.util
import json
import multiprocessing as mp
import os
import sys
import time
import datetime as dt
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE.parent / "2026-10-16-core-lift-retrain"))

import numpy as np  # noqa: E402

import common as C  # noqa: E402
from rk import cases, paths  # noqa: E402

def _skip_ifs_06_18_analysis():
    """rk.store.analysis tries an ECMWF f000 analysis at every valid time; at 06/18Z there is none (ECMWF open data
    has no 06/18Z analysis fields: the read returns None after ~37 s of retries, checked 2025-12-05 18Z), and
    rk.truth.water_mask then falls back to the GFS land/ice mask. Answer None at once for exactly that read, so the
    result is the same and each 06/18Z valid time costs 1 s, not 40 s."""
    from rk import fetch
    orig = fetch.det

    def det(model, cycle, step, *a, **k):
        if model == "ifs" and step == 0 and cycle.hour not in (0, 12):
            return None
        return orig(model, cycle, step, *a, **k)
    fetch.det = det


_skip_ifs_06_18_analysis()

STEPS = (24, 30, 48, 54, 72, 78, 96, 102, 120, 126)
LAGS = (12, 24)
_M = {}


def _load(name, rel):
    if name not in _M:
        spec = importlib.util.spec_from_file_location(name, HERE.parent / rel)
        m = importlib.util.module_from_spec(spec)
        sys.modules[name] = m
        spec.loader.exec_module(m)
        _M[name] = m
    return _M[name]


def mlw():
    return _load("mlw_build_cases", "2026-11-07-most-likely-wind/build_cases.py")


def slc():
    return _load("slc_build", "2026-11-06-strong-core-lift/build.py")


def block_job(job):
    basin, cycs, steps = job
    out, touched = [], set()
    for cyc in cycs:
        res = []
        for step in steps:
            for attempt in range(3):
                try:
                    a = mlw().case_job((basin, cyc, step))
                    b = slc().case_job((basin, cyc, step))
                    res.append((step, a[0], a[1], b[1], b[2]))
                    break
                except Exception as e:
                    if attempt == 2:
                        res.append((step, "missing_inputs", ["error"], "missing_inputs", ["error"]))
                        print("error %s %s f%03d: %r" % (basin, cases.tag(cyc), step, e), flush=True)
                    time.sleep(5 * (attempt + 1))
        touched.update(cyc - dt.timedelta(hours=h) for h in (0,) + LAGS)
        for c in [c for c in touched if c < cyc - dt.timedelta(hours=LAGS[0])]:
            slc().drop_cycle(basin, c)
            touched.discard(c)
        out.append((cyc, res))
    for c in touched:
        slc().drop_cycle(basin, c)
    return basin, out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--basins", default="natl,npac")
    ap.add_argument("--max-cycles", type=int, default=None)
    ap.add_argument("--block", type=int, default=8)
    a = ap.parse_args()
    jobs = [j for j in C.all_cases(a.basins.split(","), STEPS) if cases.held_out(j[1])]
    bycyc = {}
    for b, c, s in jobs:
        bycyc.setdefault(b, set()).add(c)
    tasks = []
    for b, cs in bycyc.items():
        cs = sorted(cs)[:a.max_cycles] if a.max_cycles else sorted(cs)
        tasks += [(b, tuple(cs[i:i + a.block]), STEPS) for i in range(0, len(cs), a.block)]
    print("held-out basin-cycles: %d, cases %d" % (sum(len(t[1]) for t in tasks), sum(len(t[1]) for t in tasks) * len(STEPS)),
          flush=True)
    tally, t0, n, missing = {"mlw": {}, "slc": {}}, time.time(), 0, []
    with mp.get_context("spawn").Pool(a.workers) as pool:
        for basin, out in pool.imap_unordered(block_job, tasks, chunksize=1):
            for cyc, res in out:
                n += 1
                for step, sa, fa, sb, fb in res:
                    for k in [sa] + fa:
                        tally["mlw"][k] = tally["mlw"].get(k, 0) + 1
                    for k in [sb] + fb:
                        tally["slc"][k] = tally["slc"].get(k, 0) + 1
                    if sa.startswith("missing") or sb.startswith("missing") or fa or fb:
                        missing.append([basin, cases.tag(cyc), step, sa] + fa + [sb] + fb)
            print("[%d cycles] %.0fs %s" % (n, time.time() - t0, tally), flush=True)
    out = paths.data("extra", "desk-30m-vs-best-wind", "build_missing.json")
    json.dump(missing, open(out, "w"))
    print("SUMMARY %s; missing/flag list %s" % (tally, out), flush=True)


if __name__ == "__main__":
    main()
