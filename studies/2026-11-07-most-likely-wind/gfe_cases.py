#!/usr/bin/env python3
"""Sidecar for the GFE follow-up (Jason 17:45Z "score the GFE method"): per case already built by build_cases.py,
the GFE Make_BestWind inputs, saved in rk.paths.cache("extra", "most-likely-wind-gfe", basin):
  det   float16  rk.features.det_blend(models=("gfs", "ifs"), lags=(12, 24)): the GFE blend (#95 recipe, as
                 Make_BestWind: lagged runs weighted by agreement + 0.3 x run spread, cap 5)
  s925 sa float16  GFS 925 mb wind (kt) and sea minus 2 m air (C), for the HF core option; absent without the
                 GFS lower-level file
  python3 gfe_cases.py --split tune|held_out [--workers 4]
"""
import argparse
import multiprocessing as mp
import os
import shutil
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import numpy as np  # noqa: E402

from rk import KT, cases, features, paths, store  # noqa: E402

LAGS = (12, 24)


def out_path(basin, cycle, step):
    return paths.cache("extra", "most-likely-wind-gfe", basin) / ("%s_f%03d.npz" % (cases.tag(cycle), step))


def case(basin, cyc, step):
    op = out_path(basin, cyc, step)
    if op.exists():
        return "existing"
    det = features.det_blend(basin, cyc, step, models=("gfs", "ifs"), lags=LAGS)
    if det is None:
        return "missing_det"
    out = {"det": det["r10"].astype(np.float16)}
    low = store.load_low(basin, cyc, "gfs", step)
    if low is not None:
        out["s925"] = (np.hypot(low["u925"], low["v925"]) * KT).astype(np.float16)
        out["sa"] = (low["skt"] - low["t2"]).astype(np.float16)
    op.parent.mkdir(parents=True, exist_ok=True)
    tmp = op.with_name(op.stem + ".tmp.npz")
    np.savez_compressed(tmp, **out)
    os.replace(tmp, op)
    return "done"


def block(job):
    basin, cycs = job
    res, touched = [], set()
    for cyc, steps in cycs:
        for st in steps:
            for att in range(3):
                try:
                    res.append(case(basin, cyc, st))
                    break
                except Exception as e:
                    if att == 2:
                        res.append("error")
                        print("error", basin, cyc, st, repr(e), flush=True)
                    time.sleep(5 * (att + 1))
        touched.update(cyc - __import__("datetime").timedelta(hours=h) for h in (0,) + LAGS)
        for c in [c for c in touched if c < cyc - __import__("datetime").timedelta(hours=LAGS[0])]:
            d = store._cache_dir(basin, c)
            if d.exists() and not (d / ".dirty").exists():
                shutil.rmtree(d, ignore_errors=True)
            touched.discard(c)
    for c in touched:
        d = store._cache_dir(basin, c)
        if d.exists() and not (d / ".dirty").exists():
            shutil.rmtree(d, ignore_errors=True)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True, choices=("tune", "held_out"))
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    tasks = []
    for b in ("natl", "npac"):
        byc = {}
        for p in sorted(paths.cache("extra", "most-likely-wind", b).glob("*_f*.npz")):
            tg, st = p.stem.split("_f")
            c = cases.parse(tg)
            if cases.split(c) == a.split:
                byc.setdefault(c, []).append(int(st))
        cs = sorted(byc.items())
        tasks += [(b, cs[i:i + 8]) for i in range(0, len(cs), 8)]
    tally, t0 = {}, time.time()
    with mp.get_context("spawn").Pool(a.workers) as pool:
        for i, r in enumerate(pool.imap_unordered(block, tasks), 1):
            for s in r:
                tally[s] = tally.get(s, 0) + 1
            print("[%d/%d blocks] %.0fs %s" % (i, len(tasks), time.time() - t0, tally), flush=True)
    print("SUMMARY", tally, flush=True)


if __name__ == "__main__":
    main()
