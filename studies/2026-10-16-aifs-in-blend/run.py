#!/usr/bin/env python3
"""AIFS in the blend: per-case counts for variants A, B, C, plain and Core Lifted (design.md).

  python3 run.py [--out DIR] [--workers 4] [--basins natl,npac] [--steps 24,48,72,96,120]
                 [--start 2025-11-01] [--end 2026-03-31] [--max-cycles N]
                 [--no-low | --low-root DIR] [--low-models gfs,ifs,aifs]
                 [--smoke-gfs-only]

Variants (deterministic support weights only; member spread is GEFS + ENS and identical in all three):
  A  gfs + ifs + aifs, as live      B  gfs + ifs      C  gfs + ifs + aifs with the AIFS weight x 0.5
Products per variant: `blend` (r10) and `corelift` (r10 + 5 kt where the LIVE core likelihood >= 0.35). The live
likelihood P is computed ONCE per case from the live model on variant A's features (rk.features.core, the retrain
study's live loader) and the same P is applied to all three variants.
Truth: rk.truth.ascat_target (real 10 m wind, intercal, all passes within 90 min), buoys from rk.truth.obs.

Per (case, variant, product) one row of counts (not ratios), written to OUT/case_counts.csv:
  h34 m34 fa34 nt34, h48 m48 fa48 nt48   5x5 deg tile hits / misses / false alarms / tiles (rk.score.tile_hits,
                                         >= 150 seen cells; forecast event among the SEEN cells)
  fc34 ob34 fc48 ob48                    seen cells with forecast >= thr / ASCAT >= thr (area ratio = fc/ob)
  b_n b_sum_err b_sum_abs                buoy pairs where forecast or buoy >= 34 kt: n, sum of (fc - obs), sum |err|
and a `split` column (rk.cases.split on the cycle). Cases with a missing input (any model, GEFS/ENS, low-level
field, ASCAT day) are skipped and counted; they are not cached, so a rerun picks them up once the data land.
Finished cases are cached in OUT/cache/<basin>/<cycle>_f<step>.json and skipped on a rerun.

--smoke-gfs-only is a PLUMBING TEST ONLY: it pretends ifs = aifs = gfs and ens = gefs (so A, B, C are the same
wind and the live P is not the live P). It refuses to write inside the study folder and labels every row
`smoke_gfs_only`. Its numbers mean nothing about the AIFS.
"""
import argparse
import datetime as dt
import json
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parent / "2026-10-16-core-lift-retrain"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import common as C  # noqa: E402  (the retrain study's: live model loader, case list)
from rk import cases, features, paths, score, store, truth  # noqa: E402
from rk.basins import grid, inside  # noqa: E402

VARIANTS = {
    "A": dict(models=("gfs", "ifs", "aifs"), det_weights=None),
    "B": dict(models=("gfs", "ifs"), det_weights=None),
    "C": dict(models=("gfs", "ifs", "aifs"), det_weights={"aifs": 0.5}),
}
LIFT_KT, LIFT_P = 5.0, 0.35         # the live page
THRS = (34, 48)
WINDOW = (dt.datetime(2025, 11, 1), dt.datetime(2026, 3, 31))
COUNTS = ["nt34", "h34", "m34", "fa34", "nt48", "h48", "m48", "fa48", "fc34", "ob34", "fc48", "ob48",
          "b_n", "b_sum_err", "b_sum_abs"]


def apply_smoke():
    """Pretend ifs = aifs = gfs and ens = gefs (plumbing test only)."""
    ld, le, ll = store.load_det, store.load_ens, store.load_low
    store.load_det = lambda b, c, m, s: ld(b, c, "gfs" if m in ("ifs", "aifs") else m, s)
    store.load_ens = lambda b, c, e, s: le(b, c, "gefs" if e == "ens" else e, s)
    store.load_low = lambda b, c, m, s, root=None: ll(b, c, "gfs" if m in ("ifs", "aifs") else m, s, root=root)


def cache_path(out, basin, cycle, step):
    return Path(out) / "cache" / basin / ("%s_f%03d.json" % (cases.tag(cycle), step))


def live_p(f):
    """Live core likelihood on the basin grid (zero off the candidate cells) from variant A's features."""
    cand = f["cand"]
    P = np.zeros(cand.shape, np.float64)
    ij = np.nonzero(cand)
    if len(ij[0]):
        m, _ = C.live_model()
        P[ij] = C.live_predict(np.column_stack([f[k][ij] for k in m["features"]]))
    return P


def buoy_counts(basin, valid, fc):
    """(ok, n, sum_err, sum_abs_err) of buoy pairs where forecast or buoy >= 34 kt."""
    o = truth.obs(basin, valid, platforms=("buoy",))
    if o is None or len(o["lat"]) == 0:
        return o is not None, 0, 0.0, 0.0
    keep = inside(basin, o["lat"], o["lon"])
    o = {k: np.asarray(v)[keep] for k, v in o.items()}
    p = score.points(fc, basin, o)
    p = p[np.isfinite(p.fc_kt) & np.isfinite(p.obs_kt)]
    p = p[(p.fc_kt >= 34) | (p.obs_kt >= 34)]
    return True, int(len(p)), float(p.err.sum()), float(p.abs_err.sum())


def case_job(job):
    """-> (job, status, rows). status: done, existing, missing_inputs, missing_ascat."""
    basin, cycle, step, out, low_root, no_low, low_models, smoke = job
    cp = cache_path(out, basin, cycle, step)
    if cp.exists():
        return job, "existing", json.load(open(cp))
    if smoke:
        apply_smoke()
    valid = cycle + dt.timedelta(hours=step)
    fa = features.core(basin, cycle, step, low_root=low_root, low=not no_low, low_models=low_models)
    if fa is None:
        return job, "missing_inputs", []
    blends = {}
    for v, spec in VARIANTS.items():
        b = features.blend(basin, cycle, step, models=spec["models"], det_weights=spec["det_weights"])
        if b is None:
            return job, "missing_inputs", []
        blends[v] = b["r10"]
    t = truth.ascat_target(basin, valid)
    if t is None:
        return job, "missing_ascat", []
    P = live_p(fa)
    lift = P >= LIFT_P
    lats, lons = grid(basin)
    seen, spd = t["seen"], t["spd"]
    key = {"basin": basin, "cycle": cases.tag(cycle), "step": step, "split": cases.split(cycle),
           "mode": "smoke_gfs_only" if smoke else "real"}
    rows, nobuoy = [], 0
    for v, r10 in blends.items():
        for prod, f in (("blend", r10), ("corelift", np.where(lift, r10 + LIFT_KT, r10).astype(np.float32))):
            r = dict(key, variant=v, product=prod)
            for thr in THRS:
                h, m, fl = score.tile_counts(tl := score.tile_hits(f, spd, seen, lats, lons, thr))
                r.update({"nt%d" % thr: len(tl), "h%d" % thr: h, "m%d" % thr: m, "fa%d" % thr: fl,
                          "fc%d" % thr: int(((f >= thr) & seen).sum()),
                          "ob%d" % thr: int(((spd >= thr) & seen).sum())})
            ok, n, se, sa = buoy_counts(basin, valid, f)
            nobuoy += not ok
            r.update(b_n=n, b_sum_err=se, b_sum_abs=sa, buoy_ok=int(ok))
            rows.append(r)
    cp.parent.mkdir(parents=True, exist_ok=True)
    tmp = cp.with_suffix(".tmp")
    json.dump(rows, open(tmp, "w"))
    os.replace(tmp, cp)
    return job, "done", rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None, help="folder for case_counts.csv and the cache "
                    "(default RK_DATA/extra/aifs-in-blend; smoke runs need an explicit folder outside the study)")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--basins", default="natl,npac")
    ap.add_argument("--steps", default=",".join(map(str, cases.STEPS)))
    ap.add_argument("--start", default="2025-11-01")
    ap.add_argument("--end", default="2026-03-31")
    ap.add_argument("--max-cycles", type=int, default=None, help="first N cycles per basin (small run)")
    ap.add_argument("--no-low", action="store_true")
    ap.add_argument("--low-root", default=None)
    ap.add_argument("--low-models", default="gfs,ifs,aifs")
    ap.add_argument("--smoke-gfs-only", action="store_true")
    a = ap.parse_args()
    if a.smoke_gfs_only:
        if not a.out:
            sys.exit("--smoke-gfs-only needs --out (a scratch folder outside the study folder)")
        if HERE in Path(a.out).resolve().parents or Path(a.out).resolve() == HERE:
            sys.exit("--smoke-gfs-only must not write inside the study folder")
        print("SMOKE TEST: ifs = aifs = gfs, ens = gefs. Plumbing only; the numbers say nothing about the AIFS.",
              flush=True)
    out = Path(a.out) if a.out else paths.data("extra", "aifs-in-blend")
    out.mkdir(parents=True, exist_ok=True)
    start, end = (dt.datetime.strptime(x, "%Y-%m-%d") for x in (a.start, a.end))
    steps = tuple(int(s) for s in a.steps.split(","))
    allc = C.all_cases(a.basins.split(","), steps, start, end)
    if a.max_cycles:
        keep = {}
        for b, c, s in allc:
            keep.setdefault(b, [])
            if c not in keep[b] and len(keep[b]) < a.max_cycles:
                keep[b].append(c)
        allc = [(b, c, s) for b, c, s in allc if c in keep[b]]
    low_models = tuple(a.low_models.split(","))
    jobs = [(b, c, s, str(out), a.low_root, a.no_low, low_models, a.smoke_gfs_only) for b, c, s in allc]
    print("cases: %d -> %s" % (len(jobs), out), flush=True)
    tally = {"done": 0, "existing": 0, "missing_inputs": 0, "missing_ascat": 0}
    rows, t0 = [], time.time()
    with mp.get_context("spawn").Pool(a.workers) as pool:
        for i, (job, status, r) in enumerate(pool.imap_unordered(case_job, jobs, chunksize=2), 1):
            tally[status] += 1
            rows += r
            if i % 50 == 0 or i == len(jobs):
                print("[%d/%d] %.0fs %s" % (i, len(jobs), time.time() - t0, tally), flush=True)
    if rows:
        df = pd.DataFrame(rows).sort_values(["basin", "cycle", "step", "variant", "product"])
        df.to_csv(out / "case_counts.csv", index=False)
        print("wrote %s (%d rows, %d cases)" % (out / "case_counts.csv", len(df), len(df) // 6))
        nb = int((df.buoy_ok == 0).sum())
        if nb:
            print("note: %d rows had no buoy table (buoy counts are zero there)" % nb)
    print("SUMMARY: cases %d %s" % (len(jobs), tally), flush=True)


if __name__ == "__main__":
    main()
