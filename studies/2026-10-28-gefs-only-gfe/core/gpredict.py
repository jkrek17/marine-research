#!/usr/bin/env python3
"""Per-case grids for scoring: the base wind N, the live Core Lifted, and both variants' core probabilities.

  python3 gpredict.py --split tune [--workers 3] [--max-cycles N]
  python3 gpredict.py --split held_out            (needs core/FINAL_CHOICE.json: only after the tune choice)

For each case (basin, cycle, step) -> <core root>/grids/<basin>/<cycle>_f<step>.npz:
  N                 rk.features.det_blend(models=("gfs","ifs")), float16 kt: the base wind
  live              the live Core Lifted (page blend with all ensembles, blend + 5 where the live model >= 0.35),
                    float16 kt: tune from live.py, held-out from the retrain's corelift-heldout files
  ocean             bool
  for v in q, h:    cand_{v}, candg_{v} (bool, storm / gale candidate cells of the GEFS-only features),
                    Ps_{v} (storm-core probability, float16, 0 off the candidate cells), Pg_{v} (gale-core),
                    p48nb_{v}, p34_{v} (GEFS member shares, 48+ neighbourhood max and 34+ cell)
Tune cases get the fold model that did NOT see the case's tune week (common.fold_of); held-out cases the final
model (fit on all tune rows). A case is written only when everything exists (N, live, both feature sets), so every
product is scored on the same cases; the others are counted as missing and listed.
Cases: 00/12 UTC cycles, +24..+120 (valid at the cycle's hour); the held-out split adds the Pacific +30..+126
(valid 06/18 UTC).
"""
import argparse
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

import numpy as np

import gcommon as G
import common as C
from rk import cases, features

STEPS_B = (30, 54, 78, 102, 126)
BLOCK = 10          # cycles per block (the cached cycle folders are cleared after each)
_M = {}


def init():
    G.install()


def model(half, kind, which):
    import joblib
    thr = 48 if kind == "storm" else 34
    key = (half, kind, which)
    if key not in _M:
        name = C.target_name(G.SET, thr)
        _M[key] = joblib.load(C.models_dir(G.models_root(half), name) / (("fold%d" % which if which != "final" else "final") + ".joblib"))
    return _M[key]


def meta_low(half):
    return json.load(open(C.models_dir(G.models_root(half), C.target_name(G.SET, 48)) / "meta.json"))["low_models"].split("+")


def probs(f, half, kind, which):
    cand = features.cand_mask(f, kind)
    ij = np.nonzero(cand)
    P = np.zeros(cand.shape, np.float16)
    if len(ij[0]):
        X = np.column_stack([np.full(len(ij[0]), f["basin_pac"], np.float64) if k == "basin_pac" else f[k][ij]
                             for k in G.SET_COLS])
        P[ij] = model(half, kind, which).predict_proba(X)[:, 1]
    return cand, P


def job(j):
    basin, cycle, step = j
    p = G.grid_path(basin, cycle, step)
    if p.exists():
        return j, "existing"
    held = cases.held_out(cycle)
    n = features.det_blend(basin, cycle, step, models=G.MODELS)
    if n is None:
        return j, "missing_det"
    lp = G.heldout_live_path(basin, cycle, step) if held else G.live_path(basin, cycle, step)
    if not lp.exists():
        return j, "missing_live"
    with np.load(lp) as z:
        live = z["corelift"]
    out = {"N": n["r10"].astype(np.float16), "live": live.astype(np.float16)}
    which = "final" if held else C.fold_of(cycle)
    for half in (False, True):
        v = G.variant_name(half)
        G.set_variant(half=half, low_models=meta_low(half))
        f = features.core(basin, cycle, step)
        if f is None:
            return j, "missing_core"
        out["ocean"] = f["ocean"]
        cs, Ps = probs(f, half, "storm", which)
        cg, Pg = probs(f, half, "gale", which)
        out.update({"cand_" + v: cs, "candg_" + v: cg, "Ps_" + v: Ps, "Pg_" + v: Pg,
                    "p48nb_" + v: f["p48_nb"].astype(np.float16), "p34_" + v: f["p34"].astype(np.float16)})
    C.save_npz(p, model=np.array(str(which)), **out)
    return j, "done"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", required=True, choices=["tune", "held_out"])
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--max-cycles", type=int, default=None)
    ap.add_argument("--choice-dir", default=str(G.HERE), help="folder holding FINAL_CHOICE.json (tests only)")
    a = ap.parse_args()
    if a.split == "held_out" and not (Path(a.choice_dir) / "FINAL_CHOICE.json").exists():
        sys.exit("refusing held_out: FINAL_CHOICE.json does not exist (written after the tune choice).")
    blocks = []        # [(basin, [(basin, cycle, step), ...], cycle tags to keep for the next block)]
    for b in ("natl", "npac"):
        cyc = sorted(cases.cycles(b, *C.WINDOW, hour=0) + cases.cycles(b, *C.WINDOW, hour=12))
        cyc = [c for c in cyc if cases.split(c) == a.split]
        if a.max_cycles:
            cyc = cyc[:a.max_cycles]
        steps = C.STEPS + (STEPS_B if (b == "npac" and a.split == "held_out") else ())
        for i in range(0, len(cyc), BLOCK):
            blk = cyc[i:i + BLOCK]
            blocks.append((b, [(b, c, s) for c in blk for s in steps], {cases.tag(c) for c in blk[-2:]}))
    print("cases: %d (%s), %d blocks" % (sum(len(x[1]) for x in blocks), a.split, len(blocks)), flush=True)
    tally, miss = {}, []
    t0 = time.time()
    done = 0
    for b, jobs, keep in blocks:
        with mp.get_context("spawn").Pool(a.workers, initializer=init) as pool:
            for j, st in pool.imap_unordered(job, jobs, chunksize=2):
                tally[st] = tally.get(st, 0) + 1
                if st.startswith("missing"):
                    miss.append((j[0], cases.tag(j[1]), j[2], st))
        G.purge(b, keep)
        done += len(jobs)
        print("[%d] %.0fs %s" % (done, time.time() - t0, tally), flush=True)
    print("SUMMARY: %s" % tally, flush=True)
    if miss:
        out = G.HERE / "results" / ("missing_%s.csv" % a.split)
        out.parent.mkdir(parents=True, exist_ok=True)
        import pandas as pd
        pd.DataFrame(miss, columns=["basin", "cycle", "step", "status"]).sort_values(["basin", "cycle", "step"]).to_csv(out, index=False)
        print("missing cases listed in", out)


if __name__ == "__main__":
    main()
