#!/usr/bin/env python3
"""Re-score the storm warning line (Core Lifted >= T kt) with the bigger lifts (Jason, 2026-11-05 17:14Z:
"Re-score the warning lines first").

  python3 lines.py [--workers 4]

Products as in fit_score.py: base (today's Core Lifted), constL (+8 kt in cores), qmap_up (matched to ASCAT by
lead, raise only; out-of-fold maps on tune weeks, all-tune-week maps on held-out weeks).
Line = open water inside the OPC High Seas area (rk.basins.opc_mask) where the product >= T, T = 33..50 kt.
Scored with rk.score.warning_events against ASCAT 48 kt (seen cells, 60 nm reach), as the warning experiment:
  covered = ASCAT 48+ cells inside the line / all ASCAT 48+ cells     (share of the storm water covered)
  area    = seen warned cells / ASCAT 48+ cells                       (warned area x ASCAT's, seen water)
  caught  = storm events (8-connected 48+ areas) with a warned cell within 60 nm
  false_cells = seen warned cells with no ASCAT 48+ within 60 nm, share of seen warned cells
  reach   = warned cells + 60 nm ring, over the basin's OPC water (all water, seen or not)
Writes lines_case_counts.csv.gz (per case, product, T: summed counts) and lines_summary.csv (pooled, per
split / basin / product / T). The line threshold for each product is the highest T whose TUNE-week coverage is
at least that of today's line (base at 39 kt) - the same coverage, so the areas can be compared fairly; the
held-out rows at that T and at 39 kt are the answer.
"""
import argparse
import multiprocessing as mp
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import json  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import fit_score as F  # noqa: E402
from rk import basins, score  # noqa: E402

TS = tuple(range(33, 51))
TODAY = 39
KEYS = ("events", "hits", "obs_cells", "obs_in", "cells", "bad_cells", "warned_cells", "reach_cells")
_MAPS = {}


def job(args):
    basin, cyc, step, path, split, maps_key = args
    choice = json.load(open(HERE / "FINAL_CHOICE.json"))
    d = F.read(path)
    g = F.group_of(step)
    opc = basins.opc_mask(basin) & d["ocean"]
    prods = {"base": d["CL"], "constL": F.corelift(d["r10"], d["P"], d["Pg"], choice["constL"][basin])}
    q = F.mapped(d, g, _MAPS[maps_key], "qmap_up")
    if q is not None:
        prods["qmap_up"] = q
    rows = []
    for name, f in prods.items():
        for T in TS:
            r = score.warning_events(f >= T, d["spd"], d["seen"], 48, mask=opc)
            rows.append(dict(basin=basin, cycle=cyc, step=step, split=split, product=name, T=T,
                             **{k: r[k] for k in KEYS}))
    return rows


def init(maps):
    _MAPS.update(maps)


def pooled(df, by):
    s = df.groupby(by)[list(KEYS)].sum().reset_index()
    s["covered"] = s.obs_in / s.obs_cells
    s["area"] = s.cells / s.obs_cells
    s["caught"] = s.hits / s.events
    s["false_cells"] = s.bad_cells / s.cells
    return s


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    maps, jobs = {}, []
    for b in ("natl", "npac"):
        tc = F.load_cases(b, "tune")
        pairs = F.collect_pairs(b, tc)
        for k in range(F.FOLDS):
            maps[(b, "fold", k)] = F.fit_maps(pairs, pairs.fold != k)
        maps[(b, "all")] = F.fit_maps(pairs, np.ones(len(pairs), bool))
        jobs += [(b, c, s, p, "tune", (b, "fold", F.folds(c))) for c, s, p in tc]
        jobs += [(b, c, s, p, "held_out", (b, "all")) for c, s, p in F.load_cases(b, "held_out")]
    print("cases %d" % len(jobs), flush=True)
    rows = []
    with mp.get_context("spawn").Pool(a.workers, initializer=init, initargs=(maps,)) as pool:
        for i, r in enumerate(pool.imap_unordered(job, jobs, chunksize=4), 1):
            rows += r
            if i % 500 == 0:
                print("[%d/%d]" % (i, len(jobs)), flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(HERE / "lines_case_counts.csv.gz", index=False)
    s = pooled(df, ["split", "basin", "product", "T"])
    s.to_csv(HERE / "lines_summary.csv", index=False)
    out = []
    for b in ("natl", "npac"):
        tune = s[(s.split == "tune") & (s.basin == b)]
        target = tune[(tune["product"] == "base") & (tune["T"] == TODAY)].covered.iloc[0]
        for prod in ("base", "constL", "qmap_up"):
            t = tune[(tune["product"] == prod) & (tune.covered >= target - 1e-9)]
            T = int(t["T"].max())
            for TT, why in ((T, "same coverage as today's line (tune)"), (TODAY, "39 kt as today")):
                h = s[(s.split == "held_out") & (s.basin == b) & (s["product"] == prod) & (s["T"] == TT)].iloc[0]
                out.append(dict(basin=b, product=prod, T=TT, why=why, covered=h.covered, area=h.area,
                                caught=h.caught, events=int(h.events), false_cells=h.false_cells,
                                reach_cells=int(h.reach_cells)))
    o = pd.DataFrame(out).drop_duplicates(["basin", "product", "T"])
    o.to_csv(HERE / "lines_heldout.csv", index=False)
    print(o.round(3).to_string())


if __name__ == "__main__":
    main()
