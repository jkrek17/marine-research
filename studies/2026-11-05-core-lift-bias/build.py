#!/usr/bin/env python3
"""Rebuild today's Core Lifted inputs for every winter case and save them small (design.md).

  python3 build.py [--workers 3] [--basins natl,npac] [--steps 24,30,...] [--max-cycles N]

Per case (basin, 00/12Z cycle, step) one npz in rk.paths.cache("extra", "core-lift-bias", basin):
  r10   float16  the page blend: support-weighted GFS/ECMWF/AIFS with AIFS at half weight + member spread bump
                 (rk.features.core(..., det_weights={"aifs": 0.5}), the same r10 the page draws)
  P     float16  storm-core likelihood from the LIVE awips-tools core_model.json (storm.core_grid, 28/34 kt cands)
  Pg    float16  gale-core chance from the LIVE gale_core_model.json (storm.core_grid, 24/30 kt cands)
  ocean bool     open, ice-free water
  seen  bool     an ASCAT cell landed here (rk.truth.ascat_target: real 10 m, intercalibrated, rain dropped,
                 all passes within 90 min of the valid time)
  spd   float16  ASCAT wind (kt), NaN where unseen
  anl   float16  GFS+IFS analysis mean wind (kt) where the store has it (00/12Z valid), else all NaN
Core Lifted is then r10 + 5 where P >= 0.35, raised to 34 where Pg >= 0.6 (awips-tools storm.products and
storm.gale_lift; the page limits the gale floor to the OPC boxes, the basin grids sit inside them).
Resumable: a case already written is skipped. Cases with missing inputs or no ASCAT day are counted, not written.
"""
import argparse
import datetime as dt
import json
import multiprocessing as mp
import os
import shutil
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parent / "2026-10-16-core-lift-retrain"))

import numpy as np  # noqa: E402

import common as C  # noqa: E402  (live model loader, case list)
from rk import cases, features, paths, store, truth  # noqa: E402

DET_WEIGHTS = {"aifs": 0.5}


def out_path(basin, cycle, step):
    return paths.cache("extra", "core-lift-bias", basin) / ("%s_f%03d.npz" % (cases.tag(cycle), step))


def live_models():
    _, storm = C.live_model()
    pipe = C.find_awips()
    core = storm.load_model(str(pipe / "core_model.json"))
    gale = storm.load_model(str(pipe / "gale_core_model.json"))
    return storm, core, gale


def cycle_job(job):
    """All steps of one basin-cycle, then drop that cycle's unpacked store files (published, re-downloadable)
    so a whole winter fits on the session disk. -> (job, [(step, status)])."""
    basin, cycle, steps = job
    res = []
    for step in steps:
        for attempt in range(3):
            try:
                res.append((step, case_job((basin, cycle, step))[1]))
                break
            except Exception as e:  # network resets from the release host: retry, then count as missing
                if attempt == 2:
                    res.append((step, "missing_inputs"))
                    print("error %s %s f%03d: %r" % (basin, cases.tag(cycle), step, e), flush=True)
                time.sleep(5 * (attempt + 1))
    d = store._cache_dir(basin, cycle)
    if d.exists() and not (d / ".dirty").exists():
        shutil.rmtree(d, ignore_errors=True)
    return job, res


def case_job(job, det_weights=DET_WEIGHTS, write=True):
    basin, cycle, step = job
    op = out_path(basin, cycle, step)
    if write and op.exists():
        return job, "existing"
    f = features.core(basin, cycle, step, det_weights=det_weights)
    if f is None:
        return job, "missing_inputs"
    valid = cycle + dt.timedelta(hours=step)
    t = truth.ascat_target(basin, valid)
    if t is None:
        return job, "missing_ascat"
    storm, core_m, gale_m = live_models()
    feats = {k: v for k, v in f.items() if isinstance(v, np.ndarray) and v.shape == f["r10"].shape}
    feats["basin_pac"] = np.full(f["r10"].shape, float(f["basin_pac"]))
    P = storm.core_grid(feats, f["ocean"], core_m)
    Pg = storm.core_grid(feats, f["ocean"], gale_m, r10_min=24, mod_min=30)
    if not write:
        return job, {"r10": f["r10"], "P": P, "Pg": Pg}
    an = store.analysis(basin, valid) if valid.hour in (0, 12) else None
    anl = np.full(P.shape, np.nan, np.float16) if an is None else np.where(an["mask"], an["mean_speed"], np.nan)
    op.parent.mkdir(parents=True, exist_ok=True)
    tmp = op.with_name(op.stem + ".tmp.npz")
    np.savez_compressed(tmp, r10=f["r10"].astype(np.float16), P=P.astype(np.float16), Pg=Pg.astype(np.float16),
                        ocean=f["ocean"], seen=t["seen"], spd=t["spd"].astype(np.float16),
                        anl=anl.astype(np.float16))
    os.replace(tmp, op)
    return job, "done"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--basins", default="natl,npac")
    ap.add_argument("--steps", default=",".join(map(str, cases.STEPS)))
    ap.add_argument("--max-cycles", type=int, default=None)
    a = ap.parse_args()
    steps = tuple(int(s) for s in a.steps.split(","))
    jobs = C.all_cases(a.basins.split(","), steps)
    if a.max_cycles:
        keep = {}
        for b, c, s in jobs:
            keep.setdefault(b, [])
            if c not in keep[b] and len(keep[b]) < a.max_cycles:
                keep[b].append(c)
        jobs = [(b, c, s) for b, c, s in jobs if c in keep[b]]
    bycyc = {}
    for b, c, st in jobs:
        bycyc.setdefault((b, c), []).append(st)
    cjobs = [(b, c, tuple(st)) for (b, c), st in bycyc.items()]
    print("cases: %d in %d basin-cycles" % (len(jobs), len(cjobs)), flush=True)
    tally, t0 = {"done": 0, "existing": 0, "missing_inputs": 0, "missing_ascat": 0}, time.time()
    missing = []
    with mp.get_context("spawn").Pool(a.workers) as pool:
        for i, (job, res) in enumerate(pool.imap_unordered(cycle_job, cjobs, chunksize=1), 1):
            for st, status in res:
                tally[status] += 1
                if status.startswith("missing"):
                    missing.append([job[0], cases.tag(job[1]), st, status])
            if i % 10 == 0 or i == len(cjobs):
                print("[%d/%d cycles] %.0fs %s" % (i, len(cjobs), time.time() - t0, tally), flush=True)
    mp_ = paths.cache("extra", "core-lift-bias") / "missing.json"
    json.dump(missing, open(mp_, "w"))
    print("SUMMARY %s; missing list %s" % (tally, mp_), flush=True)


if __name__ == "__main__":
    main()
