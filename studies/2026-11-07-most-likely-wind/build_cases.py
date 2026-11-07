#!/usr/bin/env python3
"""Per-case inputs for the most-likely-wind study (design.md), saved small.

  python3 build_cases.py [--workers 3] [--basins natl,npac] [--split held_out|tune|all] [--max-cycles N]

Case list: core-lift-retrain common.all_cases (both basins, every 00/12Z cycle 1 Nov 2025 - 31 Mar 2026) at the
steps of strong-core-lift (24..126 h, 06/18Z-valid steps included). One npz per case in
rk.paths.cache("extra", "most-likely-wind", basin):
  gfs ifs aifs        float16  deterministic 10 m speeds (kt), current runs
  base0 base05 base1  float16  support-weighted model mean (rk.features.support_closed_form, the page's base) with
                               AIFS weight 0 / 0.5 (live page) / 1
  boost               float16  the page's spread term min(k x GEFS+ENS member SD, 5 kt) (rk.features.k_for)
  P Pg                float16  live storm-core likelihood / gale-core chance (core-lift-bias build.case_job, on
                               the live page r10); absent where the lower-level files are (some 06/18Z steps)
  p48nb               float16  GEFS 48 kt member share, max over storm.NB, as the page's Best Wind HF core reads it
  ocean seen spd      as core-lift-bias (ASCAT rk.truth.ascat_target: real 10 m, rain dropped, +-90 min)
Page blend = base05 + boost (identical to features.blend(det_weights={"aifs": 0.5})["r10"]).
Resumable; a worker drops each cycle's unpacked store files when done (published, re-downloadable).
"""
import argparse
import datetime as dt
import importlib.util
import json
import multiprocessing as mp
import os
import shutil
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE.parent / "2026-10-16-core-lift-retrain"))

import numpy as np  # noqa: E402
from scipy import ndimage  # noqa: E402

import common as C  # noqa: E402
from rk import cases, features, paths, store, truth  # noqa: E402

STEPS_ALL = (24, 30, 48, 54, 72, 78, 96, 102, 120, 126)
MODELS, ENS = ("gfs", "ifs", "aifs"), ("gefs", "ens")
_M = {}


def clb():
    if "m" not in _M:
        spec = importlib.util.spec_from_file_location("clb_build", HERE.parent / "2026-11-05-core-lift-bias" / "build.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        _M["m"] = m
    return _M["m"]


def out_path(basin, cycle, step):
    return paths.cache("extra", "most-likely-wind", basin) / ("%s_f%03d.npz" % (cases.tag(cycle), step))


def ocean_mask(basin, cycle, step):
    for s in (step, step - 6):
        low = store.load_low(basin, cycle, "gfs", s) if s >= 6 else None
        if low is not None and "land" in low:
            return (~low["land"]) & ~(low["ice"] >= 0.5)
    return None


def case_job(job):
    basin, cycle, step = job
    op = out_path(basin, cycle, step)
    if op.exists():
        return "existing", []
    valid = cycle + dt.timedelta(hours=step)
    t = truth.ascat_target(basin, valid)
    if t is None:
        return "missing_ascat", []
    dets = [store.load_det(basin, cycle, m, step) for m in MODELS]
    stats = [store.load_ens(basin, cycle, e, step) for e in ENS]
    if any(d is None for d in dets) or any(s is None or s["n"] < store.MIN_MEMBERS for s in stats):
        return "missing_inputs", []
    ocean = ocean_mask(basin, cycle, step)
    if ocean is None:
        return "missing_inputs", ["no_ocean"]
    speeds = np.array([d["speed"] for d in dets], np.float32)
    out = {m: speeds[i].astype(np.float16) for i, m in enumerate(MODELS)}
    for tagw, w in (("base0", 0.0), ("base05", 0.5), ("base1", 1.0)):
        out[tagw] = features.support_closed_form(speeds, stats, weights=features._weights(MODELS, {"aifs": w}))
    out["boost"] = np.minimum(features.k_for(step) * features.pool(stats)["sd"], features.CAP_KT)
    flags = []
    page = clb().case_job(job, write=False)[1]
    if isinstance(page, dict):
        r10 = out["base05"] + out["boost"]
        if np.nanmax(np.abs(page["r10"] - r10)) > 0.05:
            flags.append("r10_mismatch")
        out["P"], out["Pg"] = page["P"], page["Pg"]
    else:
        flags.append("no_core")
    g = stats[0]
    out["p48nb"] = ndimage.maximum_filter(np.nan_to_num(g["p48"], nan=0.0), size=features.NB, mode="nearest")
    out = {k: np.asarray(v).astype(np.float16) for k, v in out.items()}
    op.parent.mkdir(parents=True, exist_ok=True)
    tmp = op.with_name(op.stem + ".tmp.npz")
    np.savez_compressed(tmp, ocean=ocean, seen=t["seen"], spd=t["spd"].astype(np.float16), **out)
    os.replace(tmp, op)
    return "done", flags


def cycle_job(job):
    basin, cyc, steps = job
    t0, res = time.time(), []
    for step in steps:
        for attempt in range(3):
            try:
                res.append((step,) + case_job((basin, cyc, step)))
                break
            except Exception as e:
                if attempt == 2:
                    res.append((step, "missing_inputs", ["error"]))
                    print("error %s %s f%03d: %r" % (basin, cases.tag(cyc), step, e), flush=True)
                time.sleep(5 * (attempt + 1))
    d = store._cache_dir(basin, cyc)
    if d.exists() and not (d / ".dirty").exists():
        shutil.rmtree(d, ignore_errors=True)
    return basin, cyc, time.time() - t0, res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--basins", default="natl,npac")
    ap.add_argument("--steps", default=",".join(map(str, STEPS_ALL)))
    ap.add_argument("--split", default="all", choices=("all", "held_out", "tune"))
    ap.add_argument("--max-cycles", type=int, default=None)
    a = ap.parse_args()
    steps = tuple(int(s) for s in a.steps.split(","))
    jobs = C.all_cases(a.basins.split(","), steps)
    if a.split != "all":
        jobs = [j for j in jobs if cases.split(j[1]) == a.split]
    bycyc = {}
    for b, c, s in jobs:
        bycyc.setdefault((b, c), []).append(s)
    tasks = [(b, c, tuple(s)) for (b, c), s in sorted(bycyc.items(), key=lambda x: (x[0][1], x[0][0]))]
    if a.max_cycles:
        tasks = tasks[:a.max_cycles]
    print("cases: %d in %d basin-cycles" % (sum(len(t[2]) for t in tasks), len(tasks)), flush=True)
    tally, t0, missing = {}, time.time(), []
    with mp.get_context("spawn").Pool(a.workers) as pool:
        for i, (b, cyc, sec, res) in enumerate(pool.imap_unordered(cycle_job, tasks, chunksize=1), 1):
            for step, status, flags in res:
                for k in [status] + flags:
                    tally[k] = tally.get(k, 0) + 1
                if status.startswith("missing") or flags:
                    missing.append([b, cases.tag(cyc), step, status] + flags)
            if i % 5 == 0 or i == len(tasks):
                print("[%d/%d cycles] %.0fs %s" % (i, len(tasks), time.time() - t0, tally), flush=True)
    mp_ = paths.cache("extra", "most-likely-wind") / ("missing_%s.json" % a.split)
    mp_.parent.mkdir(parents=True, exist_ok=True)
    json.dump(missing, open(mp_, "w"))
    print("SUMMARY %s" % tally, flush=True)


if __name__ == "__main__":
    main()
