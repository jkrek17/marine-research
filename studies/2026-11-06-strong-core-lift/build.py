#!/usr/bin/env python3
"""Per-case inputs of the strong-core-lift study (design.md): the page blend pieces of core-lift-bias plus the
GFE deterministic pieces, saved small.

  python3 build.py [--workers 3] [--basins natl,npac] [--steps 24,30,...] [--max-cycles N]
                   [--heldout-only | --tune-only] [--block 8]

Same case list as core-lift-bias (common.all_cases: both basins, every 00/12Z cycle 1 Nov 2025 - 31 Mar 2026,
every step in --steps; default the 24..126 h set of core-lift-bias, 06/18Z-valid steps included).
Per case one npz in rk.paths.cache("extra", "strong-core-lift", basin):
  From core-lift-bias build.case_job(write=False) (imported, not copied), page blend with AIFS at half weight:
    r10 P Pg   float16  page blend, storm-core likelihood, gale-core chance (absent when the page inputs are
                        missing: the 06/18Z-valid steps of tune cycles have no low-level files)
  ocean seen spd anl as core-lift-bias (ocean from the GFS land/ice of the lower-level file; where a case has
                        none, the file of the step 6 h earlier of the same cycle: land is static, ice nearly)
  det   float16  rk.features.det_blend(models=("gfs","ifs")) r10: the GFE PR #95 recipe (lags 12/24, k=NOMEM_K);
                 absent (status "missing_det") when any of its runs is missing
  gfs ifs float16  deterministic 10 m speeds (kt) of the current runs
  gfs_msl ifs_msl float32 MSLP (hPa); g_t2 g_skt g_t925 (GFS) and i_skt i_t925 (IFS, where stored) float32 K:
                 inputs of the desk's Stability_Model_Blender "Stability Height" mask
  p48nb_h float16  GEFS 48 kt member share, 0.5 deg inputs (rk.features.half_deg), neighbourhood max over
                 rk.features.NB: the GEFS-only study's "h" variant (gpredict.py: core()["p48_nb"] with GEFS at 0.5 deg)
  s925 sa st925  float16  GFS 925 mb wind (kt), sea minus 2 m air (skt - t2, C), skin minus 925 mb air (skt - t925);
                 absent when the GFS lower-level file is
Statuses per case: done / existing / missing_ascat / missing_inputs (nothing written: no ASCAT day, or neither
the page inputs nor the deterministic runs nor an ocean mask). A written case also counts the flags
missing_page, missing_det, missing_gefs, no_low for the keys it lacks. Resumable: a written case is skipped.
Disk: a worker processes a block of consecutive cycles and drops the unpacked store files (published,
re-downloadable) of each cycle once no later cycle of the block can need it as a lag run.
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
CLB = HERE.parent / "2026-11-05-core-lift-bias"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE.parent / "2026-10-16-core-lift-retrain"))

import numpy as np  # noqa: E402
from scipy import ndimage  # noqa: E402

import common as C  # noqa: E402  (case list)
from rk import KT, cases, features, paths, store, truth  # noqa: E402

STEPS_ALL = (24, 30, 48, 54, 72, 78, 96, 102, 120, 126)
LAGS = (12, 24)
_CLB = {}


def clb():
    """core-lift-bias build.py, loaded under another name (this file is also called build)."""
    if "m" not in _CLB:
        spec = importlib.util.spec_from_file_location("clb_build", CLB / "build.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        _CLB["m"] = m
    return _CLB["m"]


def out_path(basin, cycle, step):
    return paths.cache("extra", "strong-core-lift", basin) / ("%s_f%03d.npz" % (cases.tag(cycle), step))


def ocean_mask(basin, cycle, step):
    """(ocean, from_adjacent_step) from the GFS land/ice of the lower-level file, as rk.features.core builds it."""
    for s, adj in ((step, False), (step - 6, True)):
        if s < 6:
            continue
        low = store.load_low(basin, cycle, "gfs", s)
        if low is not None and "land" in low:
            return (~low["land"]) & ~(low["ice"] >= 0.5), adj
    return None, False


def p48nb_half(basin, cycle, step):
    """GEFS 48 kt share on the 0.5 deg points, neighbourhood max (the GEFS-only study's h variant)."""
    g = store.load_ens(basin, cycle, "gefs", step)
    if g is None:
        return None
    return ndimage.maximum_filter(features.half_deg(g["p48"]), size=features.NB, mode="nearest")


def case_job(job):
    """-> (job, status, flags)."""
    basin, cycle, step = job
    op = out_path(basin, cycle, step)
    if op.exists():
        return job, "existing", []
    valid = cycle + dt.timedelta(hours=step)
    t = truth.ascat_target(basin, valid)
    if t is None:
        return job, "missing_ascat", []
    flags, out = [], {}
    page = clb().case_job(job, write=False)[1]
    if isinstance(page, dict):
        out.update({k: page[k].astype(np.float16) for k in ("r10", "P", "Pg")})
    elif page == "missing_ascat":
        return job, "missing_ascat", []
    else:
        flags.append("missing_page")
    ocean, adj = ocean_mask(basin, cycle, step)
    dets = {m: store.load_det(basin, cycle, m, step) for m in ("gfs", "ifs")}
    for m, d in dets.items():
        if d is not None:
            out[m] = d["speed"].astype(np.float16)
            out[m + "_msl"] = d["msl"].astype(np.float32)   # hPa, for the desk Stability Height mask
    det = features.det_blend(basin, cycle, step, models=("gfs", "ifs"), lags=LAGS)
    if det is None:
        flags.append("missing_det")
    else:
        out["det"] = det["r10"].astype(np.float16)
    if ocean is None or ("r10" not in out and "det" not in out):
        return job, "missing_inputs", flags
    p48 = p48nb_half(basin, cycle, step)
    if p48 is None:
        flags.append("missing_gefs")
    else:
        out["p48nb_h"] = p48.astype(np.float16)
    low = store.load_low(basin, cycle, "gfs", step)
    if low is None:
        flags.append("no_low")
    else:
        out["s925"] = (np.hypot(low["u925"], low["v925"]) * KT).astype(np.float16)
        out["sa"] = (low["skt"] - low["t2"]).astype(np.float16)
        out["st925"] = (low["skt"] - low["t925"]).astype(np.float16)
        for k in ("t2", "skt", "t925"):   # K, for the desk Stability Height mask (theta925 <= theta_sfc)
            out["g_" + k] = np.asarray(low[k], np.float32)
    ilow = store.load_low(basin, cycle, "ifs", step)
    if ilow is not None:
        for k in ("skt", "t925"):
            out["i_" + k] = np.asarray(ilow[k], np.float32)
    an = store.analysis(basin, valid) if valid.hour in (0, 12) else None
    anl = np.full(ocean.shape, np.nan, np.float32) if an is None else np.where(an["mask"], an["mean_speed"], np.nan)
    op.parent.mkdir(parents=True, exist_ok=True)
    tmp = op.with_name(op.stem + ".tmp.npz")
    np.savez_compressed(tmp, ocean=ocean, ocean_adj=np.array(adj), seen=t["seen"], spd=t["spd"].astype(np.float16),
                        anl=anl.astype(np.float16), **out)
    os.replace(tmp, op)
    return job, "done", flags


def drop_cycle(basin, cycle):
    d = store._cache_dir(basin, cycle)
    if d.exists() and not (d / ".dirty").exists():
        shutil.rmtree(d, ignore_errors=True)


def block_job(job):
    """One basin, consecutive cycles, all steps. -> (basin, [(cycle, seconds, [(step, status, flags)])])."""
    basin, cycs, steps = job
    out, touched = [], set()
    for cyc in cycs:
        t0, res = time.time(), []
        for step in steps:
            for attempt in range(3):
                try:
                    res.append((step,) + case_job((basin, cyc, step))[1:])
                    break
                except Exception as e:  # network resets from the release host: retry, then count as missing
                    if attempt == 2:
                        res.append((step, "missing_inputs", ["error"]))
                        print("error %s %s f%03d: %r" % (basin, cases.tag(cyc), step, e), flush=True)
                    time.sleep(5 * (attempt + 1))
        touched.update(cyc - dt.timedelta(hours=h) for h in (0,) + LAGS)
        # later cycles of the block need only cycle - 12 h and the cycle itself as lag runs
        for c in [c for c in touched if c < cyc - dt.timedelta(hours=LAGS[0])]:
            drop_cycle(basin, c)
            touched.discard(c)
        out.append((cyc, time.time() - t0, res))
    for c in touched:
        drop_cycle(basin, c)
    return basin, out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--basins", default="natl,npac")
    ap.add_argument("--steps", default=",".join(map(str, STEPS_ALL)))
    ap.add_argument("--max-cycles", type=int, default=None)
    ap.add_argument("--start", default=None, help="first cycle date YYYY-MM-DD (default the window start; the "
                    "first two cycles have no 12/24 h lag runs in the store, so no det)")
    ap.add_argument("--block", type=int, default=8, help="consecutive cycles per worker task")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--heldout-only", action="store_true")
    g.add_argument("--tune-only", action="store_true")
    a = ap.parse_args()
    steps = tuple(int(s) for s in a.steps.split(","))
    start = dt.datetime.strptime(a.start, "%Y-%m-%d") if a.start else None
    jobs = C.all_cases(a.basins.split(","), steps, start=start)
    if a.heldout_only:
        jobs = [j for j in jobs if cases.held_out(j[1])]
    if a.tune_only:
        jobs = [j for j in jobs if not cases.held_out(j[1])]
    if a.max_cycles:
        keep = {}
        for b, c, s in jobs:
            keep.setdefault(b, [])
            if c not in keep[b] and len(keep[b]) < a.max_cycles:
                keep[b].append(c)
        jobs = [(b, c, s) for b, c, s in jobs if c in keep[b]]
    bycyc = {}
    for b, c, st in jobs:
        bycyc.setdefault(b, {}).setdefault(c, []).append(st)
    tasks = []
    for b, d in bycyc.items():
        cs = sorted(d)
        for i in range(0, len(cs), a.block):
            tasks.append((b, tuple(cs[i:i + a.block]), tuple(steps)))
    ncyc = sum(len(t[1]) for t in tasks)
    print("cases: %d in %d basin-cycles, %d tasks" % (len(jobs), ncyc, len(tasks)), flush=True)
    tally, t0, ncd, missing, secs = {}, time.time(), 0, [], []
    with mp.get_context("spawn").Pool(a.workers) as pool:
        for basin, out in pool.imap_unordered(block_job, tasks, chunksize=1):
            for cyc, sec, res in out:
                ncd += 1
                secs.append(sec)
                for step, status, flags in res:
                    for k in [status] + flags:
                        tally[k] = tally.get(k, 0) + 1
                    if status.startswith("missing") or flags:
                        missing.append([basin, cases.tag(cyc), step, status] + flags)
            print("[%d/%d cycles] %.0fs %s" % (ncd, ncyc, time.time() - t0, tally), flush=True)
    mp_ = paths.cache("extra", "strong-core-lift") / "missing.json"
    json.dump(missing, open(mp_, "w"))
    print("SUMMARY %s; mean %.0f s per cycle in a worker (%d steps each); missing/flag list %s"
          % (tally, np.mean(secs) if secs else 0, len(steps), mp_), flush=True)


if __name__ == "__main__":
    main()
