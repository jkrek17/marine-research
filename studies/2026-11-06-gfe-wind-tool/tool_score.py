#!/usr/bin/env python3
"""Per-case counts for every GFE wind tool candidate (design.md), on the strong-core-lift cases + sidecars.

  python3 tool_score.py --split tune      [--workers 3]   -> RK_DATA/extra/gfe-wind-tool/rows_tune.csv.gz
  python3 tool_score.py --split held_out  [--workers 3]   -> rows_held_out.csv.gz (refuses if it exists: held-out once)

Counting is strong-core-lift score.py's (imported): 5x5 deg tiles with >= 150 ASCAT-seen cells, per threshold
34/48/64: nt h m fa (tiles), fc ob cau (seen cells), afc aob acau (analysis cells, 00/12Z valid).
Products (kt). D = #95 blend; s = max(GFS, ECMWF) 10 m; oc = ocean:
  D, DG, CL, CL8                  baselines as strong-core-lift (DG = #95 + GEFS 48 kt lift; CL = page Core Lifted)
  S_L{L}_T{T}                     D + L where s >= T                          (rk.features.strong_lift)
  G_L{L}_T{T}_g{g}                as S, only where GEFS P48 (0.5 deg, nb max) >= g/100
  W_L{L}_T{T}_M{L2}_U{T2}         as S, plus L2 more where s >= T2 (two tier)
  X_L{L}_T{T}                     max(D, s + L) where s >= T: the strongest model plus L at storm force
                                  (Jason's ranking: "+8 kt where a model shows 44+; when they disagree take the strongest")
  F_L{L}_T{T}_g{g}                S, then at least 48 kt where GEFS P48 (0.5 deg cell) >= g/100 (storm floor)
  A_L{L}_T{T}                     as S with s = max(GFS, ECMWF, AI-GFS)       (held-out only: AI-GFS stored there)
  H_L{L}_T{T}                     as S on det_ah (#95 with AI-GFS at half weight)  (held-out only)
HF ceiling flag (every product, no wind change): flagged = product >= 64 & GFS 925 wind x f(sea-air) < 60 kt,
f = 0.70 / 0.79 / 0.83 for sea-air < 2 / 2-5 / 5+ C (drill map-wide factors, rule925.json "f"). Columns over
ASCAT-seen cells: hf_fc (product 64+ with 925 data), hf_flag, hf_flag_a64 (flagged but ASCAT 64+),
hf_flag_a48 (flagged and ASCAT 48+), hf_unfl_a64.
"""
import argparse
import gzip
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
HERE = Path(__file__).resolve().parent
SCL = HERE.parent / "2026-11-06-strong-core-lift"
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parent / "2026-11-05-core-lift-bias"))
sys.path.insert(0, str(SCL))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import score as S  # noqa: E402  (strong-core-lift score.py)
from rk import cases, features, paths  # noqa: E402

LS, TS, GS = (4, 6, 8, 10), (40, 42, 44, 46), (5, 10, 15, 25)
TIER_LS, TIER_T, TIER_L2S, TIER_T2S = (6, 8), 44, (4, 8), (52, 56, 60)
HF_COLS = ["hf_fc", "hf_flag", "hf_flag_a64", "hf_flag_a48", "hf_unfl_a64"]


def specs():
    s = ["D", "DG", "CL", "CL8"]
    s += ["S_L%d_T%d" % (L, T) for L in LS for T in TS]
    s += ["G_L%d_T%d_g%d" % (L, T, g) for L in LS for T in TS for g in GS]
    s += ["W_L%d_T%d_M%d_U%d" % (L, TIER_T, L2, T2) for L in TIER_LS for L2 in TIER_L2S for T2 in TIER_T2S]
    s += ["X_L%d_T%d" % (L, T) for L in (0,) + LS for T in TS]
    s += ["F_L%d_T%d_g%d" % (L, T, g) for L in LS for T in TS for g in (50,)] + ["F_L0_T99_g50"]
    s += ["A_L%d_T%d" % (L, T) for L in LS for T in TS] + ["H_L%d_T%d" % (L, T) for L in LS for T in TS]
    return s


def parse(label):
    kind, *rest = label.split("_")
    p = {r[0]: int(r[1:]) for r in rest}
    return kind, p


def make(label, d, x):
    kind, p = parse(label)
    if kind in ("D", "DG", "CL", "CL8"):
        return S.make((kind, None, None, None), d)
    oc = d["ocean"]
    if kind == "H":
        if "det_ah" not in x or d["strong"] is None:
            return None
        return features.strong_lift(x["det_ah"], [d["strong"]], p["L"], p["T"], oc)
    if "det" not in d or d["strong"] is None:
        return None
    D, s = d["det"], d["strong"]
    if kind == "S":
        return features.strong_lift(D, [s], p["L"], p["T"], oc)
    if kind == "A":
        return features.strong_lift(D, [s, x["aigfs"]], p["L"], p["T"], oc) if "aigfs" in x else None
    if kind == "G":
        if "p48nb_h" not in d:
            return None
        return features.strong_lift(D, [s], p["L"], p["T"], oc & (d["p48nb_h"] >= p["g"] / 100.0))
    if kind == "X":
        on = oc & (s >= p["T"])
        return np.where(on, np.maximum(D, s + np.float32(p["L"])), D).astype(np.float32)
    if kind == "F":
        if "p48c_h" not in x:
            return None
        f = features.strong_lift(D, [s], p["L"], p["T"], oc)
        return np.where(oc & (x["p48c_h"] >= p["g"] / 100.0), np.maximum(f, 48.0), f).astype(np.float32)
    if kind == "W":
        f = features.strong_lift(D, [s], p["L"], p["T"], oc)
        return features.strong_lift(f, [s], p["M"], p["U"], oc)
    raise ValueError(label)


def hf_cols(fc, d):
    """HF ceiling flag counts (rk.features.hf_ceiling) over ASCAT-seen cells with 925 mb data."""
    if not d["has_low"]:
        return [0] * len(HF_COLS)
    flag, ceil = features.hf_ceiling(fc, d["s925"], d["sa"])
    seen = d["seen"]
    spd = np.nan_to_num(d["spd"], nan=-1)
    hf = seen & (np.nan_to_num(fc, nan=-1) >= 64) & np.isfinite(ceil)
    fl = hf & flag
    un = hf & ~fl
    return [int(hf.sum()), int(fl.sum()), int((fl & (spd >= 64)).sum()), int((fl & (spd >= 48)).sum()),
            int((un & (spd >= 64)).sum())]


def side(basin, path):
    sp = paths.cache("extra", "gfe-wind-tool", basin) / path.name
    if not sp.exists():
        return {}
    z = np.load(sp)
    return {k: z[k].astype(np.float32) for k in z.files}


def job(args):
    basin, cyc, step, path, labels = args
    d = S.prep(path)
    x = side(basin, path)
    cnt = S.Counter(basin, d)
    rows = []
    meta = dict(basin=basin, cycle=cyc.isoformat(), step=step, fold=S.F.folds(cyc), has_low=d["has_low"],
                has_side=bool(x), has_aigfs="aigfs" in x)
    for lab in labels:
        f = make(lab, d, x)
        if f is not None:
            rows.append(dict(meta, product=lab, **dict(zip(S.COLS, cnt.counts(f))),
                             **dict(zip(HF_COLS, hf_cols(f, d)))))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", required=True, choices=("tune", "held_out"))
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--basins", default="natl,npac")
    a = ap.parse_args()
    out = paths.data("extra", "gfe-wind-tool") / ("rows_%s.csv.gz" % a.split)
    if a.split == "held_out" and out.exists():
        sys.exit("held-out rows exist (%s): scored once already" % out)
    labels = specs()
    jobs = [(b, c, s, p, labels) for b in a.basins.split(",") for c, s, p in S.load_cases(b, a.split)]
    print("%d cases, %d products" % (len(jobs), len(labels)), flush=True)
    t0, allrows = time.time(), []
    with mp.get_context("spawn").Pool(a.workers) as pool:
        for i, r in enumerate(pool.imap_unordered(job, jobs, chunksize=4), 1):
            allrows += r
            if i % 200 == 0 or i == len(jobs):
                print("[%d/%d] %.0fs" % (i, len(jobs), time.time() - t0), flush=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(allrows)
    with gzip.open(out, "wt") as fh:
        df.to_csv(fh, index=False)
    print("wrote %s: %d rows" % (out, len(df)))


if __name__ == "__main__":
    main()
