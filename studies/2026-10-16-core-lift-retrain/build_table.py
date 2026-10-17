#!/usr/bin/env python3
"""Build the core-lift training table: one parquet per (basin, cycle, step).

  python3 build_table.py [--thr 48] [--cand storm|gale] [--out DIR] [--low-root DIR | --no-low] [--workers 4]
         [--low-models gfs,ifs,aifs] [--start 2025-11-01] [--end 2026-03-31] [--basins natl,npac] [--steps 24,48,72,96,120]
         [--max-cycles N]   (first N cycles per basin that have every model, for a small run)

For each basin, each 00Z and 12Z cycle in the window, each step: the 28 live core features
(rk.features.core) and the ASCAT --thr kt target (rk.truth.ascat_target, default 48) at valid = cycle + step.
Rows: candidate cells that ASCAT saw (--cand storm, default: ocean & (blend >= 28 kt | a model >= 34 kt);
--cand gale: ocean & (blend >= 24 | a model >= 30), rk.features.cand_mask), thinned to every 2nd
row and column; of those, every cell with r10 >= 40 (30 for --thr other than 48) or y == 1 is kept (weight 1)
and a random 15% of the rest (weight 1/0.15). The columns thr and cand_rule record the target; the default
48 / storm table is the one built before the options existed (same rows, same draw). The random draw is seeded from (seed, basin, cycle, step), so a rerun reproduces it.
Columns: basin, cycle, step, valid (YYYYMMDDHH), row, col, split (rk.cases.split on the CYCLE date), y, w,
asc (ASCAT cell speed kt), asc_nb (max in the 5x7 box), basin_pac, no_low, low_models ("gfs+ifs+aifs", "gfs", ...; "" with --no-low: which
models' lower-level fields formed the low-level means), then the 28 features.

Files already present are skipped; cases whose inputs are missing (a model, an ensemble, the low-level
cache, ASCAT or the analysis for the valid day) are counted and left for a rerun as the store fills.
--no-low builds WITHOUT the lower-level features (the eight low-level columns are NaN, the ocean mask is the
analysis mask); that table goes to DIR + "-nolow" and its rows carry no_low = 1. It is a stand-in for
checking the plumbing, not for training the full model.
"""
import argparse
import datetime as dt
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402

import common as C  # noqa: E402
from rk import cases, features, paths, store  # noqa: E402
from rk.basins import BASINS  # noqa: E402

SEED = 20261016
KEEP_FRAC = 0.15
THIN = 2


def case_path(out, basin, cycle, step):
    return Path(out) / basin / ("%s_%s_f%03d.parquet" % (basin, cases.tag(cycle), step))


def build_case(job):
    """One (basin, cycle, step) -> (job, status, nrows, npos); status in done, existing, missing_inputs,
    missing_ascat."""
    basin, cycle, step, out, low_root, no_low, low_models, thr, cand_rule = job
    p = case_path(out, basin, cycle, step)
    if p.exists():
        return job, "existing", 0, 0
    import pandas as pd
    from rk import features, truth
    f = features.core(basin, cycle, step, low_root=low_root, low=not no_low, low_models=low_models)
    if f is None:
        return job, "missing_inputs", 0, 0
    valid = cycle + dt.timedelta(hours=step)
    try:
        t = truth.ascat_target(basin, valid, thr=float(thr))
    except Exception as e:  # network or decode trouble: leave the case for a rerun
        print("ascat error %s %s +%d: %s" % (basin, cases.tag(cycle), step, e), flush=True)
        return job, "missing_ascat", 0, 0
    if t is None:
        return job, "missing_ascat", 0, 0
    ny, nx = f["r10"].shape
    rr, cc = np.meshgrid(np.arange(ny), np.arange(nx), indexing="ij")
    sel = features.cand_mask(f, cand_rule) & t["seen"] & (rr % THIN == 0) & (cc % THIN == 0)
    y = t["y"]
    must = sel & ((f["r10"] >= C.r10_keep(thr)) | y)
    rest = sel & ~must
    key = [SEED, int(cases.tag(cycle)), step, list(BASINS).index(basin)] + ([] if thr == C.THR_DEFAULT else [int(thr)])
    rng = np.random.default_rng(key)
    draw = rng.random((ny, nx)) < KEEP_FRAC
    keep = must | (rest & draw)
    w = np.where(rest, 1.0 / KEEP_FRAC, 1.0)
    r, c = np.nonzero(keep)
    n = len(r)
    df = pd.DataFrame({"basin": basin, "cycle": cases.tag(cycle), "step": np.int16(step),
                       "valid": cases.tag(valid), "row": r.astype(np.int16), "col": c.astype(np.int16),
                       "split": cases.split(cycle), "y": y[r, c].astype(np.int8), "w": w[r, c].astype(np.float32),
                       "asc": t["spd"][r, c], "asc_nb": t["max_nb"][r, c],
                       "basin_pac": np.int8(f["basin_pac"]), "no_low": np.int8(f["no_low"]),
                       "low_models": "+".join(f["low_models"]), "thr": np.int16(thr), "cand_rule": cand_rule})
    for k in features.FEATURES:
        df[k] = f[k][r, c].astype(np.float32)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, p)
    return job, "done", n, int(df.y.sum())


def window_cycles(basin, start, end):
    return sorted(cases.cycles(basin, start, end, hour=0) + cases.cycles(basin, start, end, hour=12))


def complete(basin, cycle, steps):
    """Cheap pre-check: every deterministic and ensemble file for the last step exists (steps fill in
    order, so the last one present means the cycle is whole for the store models)."""
    for m in store.DET + ("gefs", "ens"):
        if not store._path(basin, cycle, m, steps[-1]).exists():
            return False
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    ap.add_argument("--low-root", default=None, help="root of a local low-level cache (fields/... under it)")
    ap.add_argument("--low-models", default="gfs,ifs,aifs",
                    help="models whose lower-level fields are averaged (gfs while only GFS low fields exist; "
                         "a GFS-only mean is not the live feature and is labelled in the low_models column)")
    ap.add_argument("--thr", type=int, default=C.THR_DEFAULT, help="ASCAT target threshold, kt (default 48)")
    ap.add_argument("--cand", default="storm", choices=C.CAND_RULES,
                    help="candidate cells: storm (live rule) or gale (ocean & (r10 >= 24 | a model >= 30))")
    ap.add_argument("--no-low", action="store_true", help="build without lower-level features (labelled)")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--start", default="2025-11-01")
    ap.add_argument("--end", default="2026-03-31")
    ap.add_argument("--basins", default="natl,npac")
    ap.add_argument("--steps", default=",".join(map(str, cases.STEPS)))
    ap.add_argument("--max-cycles", type=int, default=None,
                    help="only the first N cycles per basin that have every store model (small run)")
    a = ap.parse_args()
    out = Path(a.out) if a.out else paths.data("extra", "core-lift-retrain", "table")
    if a.no_low:
        out = out.with_name(out.name + "-nolow")
        print("*** --no-low: lower-level features are NaN and the ocean mask is the analysis mask; "
              "output %s is NOT a full-feature table ***" % out, flush=True)
    start, end = (dt.datetime.strptime(x, "%Y-%m-%d") for x in (a.start, a.end))
    steps = tuple(int(s) for s in a.steps.split(","))
    low_models = tuple(a.low_models.split(","))
    if low_models != features.MODELS and not a.no_low:
        out = out.with_name(out.name + "-" + "+".join(low_models))
        print("*** low-level means over %s only (not the live three): output %s ***" % (low_models, out), flush=True)
    jobs = []
    for b in a.basins.split(","):
        cyc = window_cycles(b, start, end)
        if a.max_cycles:
            cyc = [c for c in cyc if complete(b, c, steps)][:a.max_cycles]
        jobs += [(b, c, s, str(out), a.low_root, a.no_low, low_models, a.thr, a.cand) for c in cyc for s in steps]
    print("cases: %d (%s) -> %s" % (len(jobs), a.basins, out), flush=True)
    tally = {"done": 0, "existing": 0, "missing_inputs": 0, "missing_ascat": 0}
    rows = pos = 0
    t0 = time.time()
    ctx = mp.get_context("spawn")
    with ctx.Pool(a.workers) as pool:
        for i, (job, status, n, npos) in enumerate(pool.imap_unordered(build_case, jobs, chunksize=1), 1):
            tally[status] += 1
            rows += n
            pos += npos
            if i % 25 == 0 or i == len(jobs):
                print("[%d/%d] %.0fs %s" % (i, len(jobs), time.time() - t0, tally), flush=True)
    print("SUMMARY%s: cases %d, built %d, existing %d, skipped missing inputs %d, skipped no ASCAT %d; "
          "new rows %d, positives %d" % (" (NO-LOW)" if a.no_low else "", len(jobs), tally["done"],
                                          tally["existing"], tally["missing_inputs"], tally["missing_ascat"],
                                          rows, pos), flush=True)


if __name__ == "__main__":
    main()
