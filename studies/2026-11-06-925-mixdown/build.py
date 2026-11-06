#!/usr/bin/env python3
"""Per-case ASCAT-seen cells for the 925 mix-down study (design.md).

  python3 build.py [--workers 3] [--basins natl,npac] [--block 8] [--max-cycles N]

Case list = strong-core-lift (every 00/12Z cycle 1 Nov 2025 - 31 Mar 2026, steps 24..126 incl. 06/18Z valid).
Per case one small npz in rk.paths.cache("extra", "925-mixdown", basin), one entry per open-water cell ASCAT saw:
  iy ix int16  grid row/column;  asc float16 ASCAT real 10 m (kt)
  gfs ifs det float16  GFS, ECMWF 10 m and the GFE #95 blend (rk.features.det_blend GFS+ECMWF, lags 12/24) (kt; NaN absent)
  s925 sa float16  GFS 925 mb wind (kt), GFS skin minus 2 m air (C) (NaN when the low file is missing)
Resumable. Reuses strong-core-lift build.py's ocean mask and cache dropping (imported, not copied).
"""
import argparse, datetime as dt, importlib.util, multiprocessing as mp, os, sys, time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE.parent / "2026-10-16-core-lift-retrain"))
import numpy as np  # noqa: E402
import common as C  # noqa: E402
from rk import KT, cases, features, paths, store, truth  # noqa: E402

STEPS = (24, 30, 48, 54, 72, 78, 96, 102, 120, 126)
LAGS = (12, 24)
_M = {}


def scl():
    if "m" not in _M:
        spec = importlib.util.spec_from_file_location("scl_build", HERE.parent / "2026-11-06-strong-core-lift" / "build.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        _M["m"] = m
    return _M["m"]


def out_path(basin, cycle, step):
    return paths.cache("extra", "925-mixdown", basin) / ("%s_f%03d.npz" % (cases.tag(cycle), step))


def case_job(basin, cycle, step):
    op = out_path(basin, cycle, step)
    if op.exists():
        return "existing"
    t = truth.ascat_target(basin, cycle + dt.timedelta(hours=step))
    if t is None:
        return "missing_ascat"
    ocean, _ = scl().ocean_mask(basin, cycle, step)
    if ocean is None:
        return "missing_ocean"
    m = t["seen"] & ocean
    iy, ix = np.nonzero(m)
    out = dict(iy=iy.astype(np.int16), ix=ix.astype(np.int16), asc=t["spd"][m].astype(np.float16))
    nan = np.full(iy.size, np.nan, np.float16)
    for mod in ("gfs", "ifs"):
        d = store.load_det(basin, cycle, mod, step)
        out[mod] = nan if d is None else d["speed"][m].astype(np.float16)
    det = features.det_blend(basin, cycle, step, models=("gfs", "ifs"), lags=LAGS)
    out["det"] = nan if det is None else det["r10"][m].astype(np.float16)
    low = store.load_low(basin, cycle, "gfs", step)
    if low is None:
        out["s925"], out["sa"] = nan, nan
    else:
        out["s925"] = (np.hypot(low["u925"], low["v925"]) * KT)[m].astype(np.float16)
        out["sa"] = (low["skt"] - low["t2"])[m].astype(np.float16)
    op.parent.mkdir(parents=True, exist_ok=True)
    tmp = op.with_name(op.stem + ".tmp.npz")
    np.savez_compressed(tmp, **out)
    os.replace(tmp, op)
    return "done" + ("" if low is not None else "_nolow") + ("" if det is not None else "_nodet")


def block_job(job):
    basin, cycs, steps = job
    tally, touched = {}, set()
    for cyc in cycs:
        for step in steps:
            for attempt in range(3):
                try:
                    s = case_job(basin, cyc, step)
                    break
                except Exception as e:
                    s = "error"
                    if attempt == 2:
                        print("error %s %s f%03d: %r" % (basin, cases.tag(cyc), step, e), flush=True)
                    time.sleep(5 * (attempt + 1))
            tally[s] = tally.get(s, 0) + 1
        touched.update(cyc - dt.timedelta(hours=h) for h in (0,) + LAGS)
        for c in [c for c in touched if c < cyc - dt.timedelta(hours=LAGS[0])]:
            scl().drop_cycle(basin, c)
            touched.discard(c)
    for c in touched:
        scl().drop_cycle(basin, c)
    return basin, len(cycs), tally


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--basins", default="natl,npac")
    ap.add_argument("--block", type=int, default=8)
    ap.add_argument("--max-cycles", type=int, default=None)
    a = ap.parse_args()
    jobs = C.all_cases(a.basins.split(","), STEPS)
    bycyc = {}
    for b, c, _ in jobs:
        bycyc.setdefault(b, set()).add(c)
    tasks = []
    for b, cs in bycyc.items():
        cs = sorted(cs)[: a.max_cycles] if a.max_cycles else sorted(cs)
        tasks += [(b, tuple(cs[i:i + a.block]), STEPS) for i in range(0, len(cs), a.block)]
    ncyc, done, tally, t0 = sum(len(t[1]) for t in tasks), 0, {}, time.time()
    print("%d basin-cycles, %d tasks" % (ncyc, len(tasks)), flush=True)
    with mp.get_context("spawn").Pool(a.workers) as pool:
        for b, n, tl in pool.imap_unordered(block_job, tasks, chunksize=1):
            done += n
            for k, v in tl.items():
                tally[k] = tally.get(k, 0) + v
            print("[%d/%d] %.0fs %s" % (done, ncyc, time.time() - t0, tally), flush=True)
    print("SUMMARY", tally, flush=True)


if __name__ == "__main__":
    main()
