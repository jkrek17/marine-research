#!/usr/bin/env python3
"""Write the P(core) grids for every case, from the saved models.

  python3 predict.py [--thr 48] [--cand storm|gale] [--sets live28,live28+basin,store,store+basin] [--root DIR] [--workers 2]
                     [--no-low | --low-root DIR] [--low-models gfs,ifs,aifs] [--final [--held-out-only]]
                     [--start 2025-11-01] [--end 2026-03-31] [--basins natl,npac] [--steps 24,48,72,96,120]
                     [--max-cycles N]

For each case (basin, cycle, step): rk.features.core (same definitions as the table), then
  ROOT/P/base/<basin>/<cycle>_f<step>.npz   r10, p48_nb, p34, p34_nb (float32), cand, cand_gale, ocean (bool),
                                            flags no_low, low_models (p34, p34_nb, cand_gale, ocean added for the
                                            gale-core study; a base file written before has only r10, p48_nb, cand)
  ROOT/P/live/<basin>/...                   P of the live model (core_model.json, storm.core_predict), float16
  ROOT/P/<set>/<basin>/...                  P of the set's CV fold model that did NOT see the case's tune week
                                            (fold = common.fold_of); with --final, HELD-OUT weeks get the final
                                            model (fit on all tune rows). Without --final, held-out weeks are
                                            skipped entirely (base and live too), so nothing can be scored by
                                            accident.
With --thr T (default 48) the sets are the models trained at that target, '<set>@T' (common.target_name), and
--cand picks the candidate rule they were trained with (storm = cand, gale = cand_gale; default storm; must equal
the model's meta.json). P is zero outside the candidate cells of that rule, float16, on the basin grid. Existing files are skipped. The
low-level flags must match the model's meta.json (no_low, low_models) or the set is refused for that run.
Cases with missing inputs are counted and skipped.
"""
import argparse
import datetime as dt
import json
import multiprocessing as mp
import time
from pathlib import Path

import numpy as np

import common as C
from rk import cases, features

_CACHE = {}


def _model(root, name, which):
    import joblib
    key = (root, name, which)
    if key not in _CACHE:
        _CACHE[key] = joblib.load(C.models_dir(root, name) / (("fold%d" % which if which != "final" else "final") + ".joblib"))
    return _CACHE[key]


def _meta(root, name):
    key = (root, name, "meta")
    if key not in _CACHE:
        _CACHE[key] = json.load(open(C.models_dir(root, name) / "meta.json"))
    return _CACHE[key]


def case_job(job):
    """-> (job, status, counts) status in done, existing, missing_inputs; counts = grids written."""
    basin, cycle, step, root, sets, low_root, no_low, low_models, final, cand_rule = job
    held = cases.held_out(cycle)
    if held and not final:
        return job, "skipped_held_out", 0
    names = ["base", "live"] + list(sets)
    need = [n for n in names if not C.p_path(root, n, basin, cycle, step).exists()]
    if not need:
        return job, "existing", 0
    f = features.core(basin, cycle, step, low_root=low_root, low=not no_low, low_models=low_models)
    if f is None:
        return job, "missing_inputs", 0
    cand = features.cand_mask(f, cand_rule)
    flags = dict(no_low=np.int8(f["no_low"]), low_models=np.array("+".join(f["low_models"])))
    n = 0
    if "base" in need:
        C.save_npz(C.p_path(root, "base", basin, cycle, step), r10=f["r10"], p48_nb=f["p48_nb"], cand=f["cand"],
                   p34=f["p34"], p34_nb=f["p34_nb"], cand_gale=f["cand_gale"], ocean=f["ocean"], **flags)
        n += 1
    ij = np.nonzero(cand)
    if "live" in need:
        m, _ = C.live_model()
        ijl = np.nonzero(f["cand"])        # the live model scores the live (storm) candidate cells
        X = np.column_stack([f[k][ijl] for k in m["features"]]) if len(ijl[0]) else np.zeros((0, 28))
        P = np.zeros(cand.shape, np.float16)
        if len(X):
            P[ijl] = C.live_predict(X)
        C.save_npz(C.p_path(root, "live", basin, cycle, step), P=P, **flags)
        n += 1
    for name in sets:
        if name not in need:
            continue
        meta = _meta(root, name)
        if bool(meta["no_low"]) != bool(f["no_low"]) or meta["low_models"] != "+".join(f["low_models"]):
            raise RuntimeError("set %s was trained with no_low=%s low_models=%r but the features here are "
                               "no_low=%s low_models=%r" % (name, meta["no_low"], meta["low_models"], f["no_low"],
                                                           "+".join(f["low_models"])))
        if meta.get("cand_rule", "storm") != cand_rule:
            raise RuntimeError("set %s was trained on cand_rule=%s, asked for %s" % (name, meta.get("cand_rule", "storm"), cand_rule))
        which = "final" if held else C.fold_of(cycle)
        P = np.zeros(cand.shape, np.float16)
        if len(ij[0]):
            if which != "final" and not (C.models_dir(root, name) / ("fold%d.joblib" % which)).exists():
                raise RuntimeError("fold %s model of %s missing" % (which, name))
            cols = C.SETS[C.split_target(name)[0]]
            X = np.column_stack([np.full(len(ij[0]), f["basin_pac"], np.float64) if k == "basin_pac"
                                 else f[k][ij] for k in cols])
            P[ij] = _model(root, name, which).predict_proba(X)[:, 1]
        C.save_npz(C.p_path(root, name, basin, cycle, step), P=P, model=np.array(str(which)), **flags)
        n += 1
    return job, "done", n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--thr", type=int, default=C.THR_DEFAULT, help="target threshold the models were trained at")
    ap.add_argument("--cand", default="storm", choices=C.CAND_RULES, help="candidate rule of the models")
    ap.add_argument("--sets", default=",".join(C.SETS))
    ap.add_argument("--root", default=None)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--no-low", action="store_true")
    ap.add_argument("--low-root", default=None)
    ap.add_argument("--low-models", default="gfs,ifs,aifs")
    ap.add_argument("--final", action="store_true",
                    help="also write held-out weeks (final model). The held-out SCORE is a separate gate in score.py")
    ap.add_argument("--start", default="2025-11-01")
    ap.add_argument("--end", default="2026-03-31")
    ap.add_argument("--basins", default="natl,npac")
    ap.add_argument("--steps", default=",".join(map(str, cases.STEPS)))
    ap.add_argument("--held-out-only", action="store_true",
                    help="with --final: only the held-out weeks (tune grids already written)")
    ap.add_argument("--max-cycles", type=int, default=None, help="first N cycles per basin (small run)")
    a = ap.parse_args()
    root = Path(a.root) if a.root else C.default_root()
    want = [C.target_name(s, a.thr) for s in a.sets.split(",")]
    sets = [s for s in want if (C.models_dir(root, s) / "meta.json").exists()]
    for s in want:
        if s not in sets:
            print("no trained model for set %s under %s: skipped" % (s, root), flush=True)
    start, end = (dt.datetime.strptime(x, "%Y-%m-%d") for x in (a.start, a.end))
    steps = tuple(int(s) for s in a.steps.split(","))
    low_models = tuple(a.low_models.split(","))
    allc = C.all_cases(a.basins.split(","), steps, start, end)
    if a.held_out_only:
        if not a.final:
            raise SystemExit("--held-out-only needs --final")
        allc = [(b, c, s) for b, c, s in allc if cases.held_out(c)]
    if a.max_cycles:
        keep = {}
        for b, c, s in allc:
            keep.setdefault(b, [])
            if c not in keep[b] and len(keep[b]) < a.max_cycles:
                keep[b].append(c)
        allc = [(b, c, s) for b, c, s in allc if c in keep[b]]
    jobs = [(b, c, s, str(root), tuple(sets), a.low_root, a.no_low, low_models, a.final, a.cand) for b, c, s in allc]
    print("cases: %d, sets %s, final=%s -> %s" % (len(jobs), sets, a.final, root), flush=True)
    tally = {"done": 0, "existing": 0, "missing_inputs": 0, "skipped_held_out": 0}
    grids = 0
    t0 = time.time()
    with mp.get_context("spawn").Pool(a.workers) as pool:
        for i, (job, status, n) in enumerate(pool.imap_unordered(case_job, jobs, chunksize=2), 1):
            tally[status] += 1
            grids += n
            if i % 50 == 0 or i == len(jobs):
                print("[%d/%d] %.0fs %s" % (i, len(jobs), time.time() - t0, tally), flush=True)
    print("SUMMARY: cases %d %s, grids written %d" % (len(jobs), tally, grids), flush=True)


if __name__ == "__main__":
    main()
