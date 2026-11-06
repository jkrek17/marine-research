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


def combo_specs():
    """Follow-up (Jason 16:42Z, "best combo to be good at both storm and HF"): +L where stronger >= T, then +M more
    where stronger >= U. Scored after the main pick; rows go to rows_<split>_combo.csv.gz."""
    s = ["D", "S_L6_T42", "S_L10_T44"]
    s += ["W_L%d_T%d_M%d_U%d" % (L, T, M, U) for L, T in ((6, 42), (6, 40), (8, 42))
          for M in (2, 4, 6) for U in (44, 46, 48, 50) if U > T]
    return s


def ramp_specs():
    """Follow-up (Jason 16:49Z: the step lift jumps 41 -> 47 and 48 -> 52): lift ramps linearly with the stronger
    model wind over W kt instead of stepping. C0: ramp ends at the threshold (0 at T-W, full at T); C1: centred
    (0 at T-W/2, full at T+W/2). Rows go to rows_<split>_ramp.csv.gz."""
    s = ["D", "S_L6_T42", "W_L6_T42_M4_U48"]
    s += ["R_L6_T42_M4_U48_W%d_C%d" % (w, c) for w in (2, 4, 6, 8) for c in (0, 1)]
    s += ["R_L6_T%d_M4_U%d_W%d_C1" % (t, u, w) for t in (40, 44) for u in (46, 50) for w in (4, 6)]
    return s


SELF_BASES = {0: "det", 1: "gfs", 2: "ifs", 3: "strong"}


def self_specs():
    """Follow-up (Jason 16:54Z: "could this be a simple tool to run on any model or blend"): the ramps triggered by
    the grid being lifted itself, no other model. Q_B<b>_A<a>_U<u>: base b (0 #95 blend, 1 GFS, 2 ECMWF), lift
    0 -> 6 kt over a..a+4 kt of the base's own wind, plus 0 -> 4 kt more over u..u+4. A99/U99 = the base as is.
    Rows go to rows_<split>_self.csv.gz."""
    s = ["D", "R_L6_T40_M4_U50_W4_C1"]
    # Y (Jason 16:54Z "highest model, then the ramp above 42"): blend below A, moving linearly to the stronger of
    # GFS/ECMWF over A..A+4 of that stronger wind, plus the same ramps (6 kt over A..A+4, 4 kt over U..U+4).
    s += ["Y_A%d_U%d" % (a, u) for a in (36, 38, 40, 42) for u in (44, 46, 48, 50)]
    for b in SELF_BASES:
        s += ["Q_B%d_A99_U99" % b]
        s += ["Q_B%d_A%d_U%d" % (b, a, u) for a in (30, 32, 34, 36, 38, 40) for u in (40, 42, 44, 46, 48) if u >= a + 4]
    return s


def hf_specs():
    """Follow-up (Jason 17:23Z: "additional HF core ... targeted to the right areas, we dont want to blanket HF"): on
    top of the current tool (R_L6_T40_M4_U50_W4_C1), an extra 0 -> E kt over U..U+4 kt of the stronger of GFS/ECMWF,
    only where GFS 925 mb wind x drill stability factor (rk.features.hf_ceiling) >= G kt (G0 = no gate). Cases
    without 925 mb data are skipped for every K product so all pair. Rows go to rows_<split>_hf.csv.gz."""
    s = ["D", "R_L6_T40_M4_U50_W4_C1"]
    s += ["K_E%d_U%d_G%d" % (e, u, g) for e in (4, 6, 8, 10) for u in (48, 52, 56) for g in (0, 55, 60, 65, 70)]
    return s


def ramp(s, lift, t, w, centred):
    lo = t - (w / 2.0 if centred else w)
    return np.float32(lift) * np.clip((s - lo) / float(w), 0, 1)


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
    if kind == "K":
        if "det" not in d or d["strong"] is None or not d["has_low"]:
            return None
        base = make("R_L6_T40_M4_U50_W4_C1", d, x)
        sf = np.nan_to_num(d["strong"], nan=-1.0)
        add = ramp(sf, p["E"], p["U"] + 4, 4, 0)
        if p["G"] > 0:
            ceil = features.hf_ceiling(base, d["s925"], d["sa"])[1]
            add = np.where(np.nan_to_num(ceil, nan=-1.0) >= p["G"], add, 0)
        return np.where(oc, base + add, base).astype(np.float32)
    if kind == "Y":
        if "det" not in d or d["strong"] is None:
            return None
        D, sf = d["det"], np.nan_to_num(d["strong"], nan=-1.0)
        w = np.clip((sf - p["A"]) / 4.0, 0, 1)
        top = (1 - w) * D + w * np.maximum(D, sf) + ramp(sf, 6, p["A"] + 4, 4, 0) + ramp(sf, 4, p["U"] + 4, 4, 0)
        return np.where(oc, top, D).astype(np.float32)
    if kind == "Q":
        B = d.get(SELF_BASES[p["B"]])
        if B is None:
            return None
        if p["A"] == 99:
            return B.astype(np.float32)
        bf = np.nan_to_num(B, nan=-1.0)
        add = ramp(bf, 6, p["A"] + 4, 4, 0) + ramp(bf, 4, p["U"] + 4, 4, 0)
        return np.where(oc, B + add, B).astype(np.float32)
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
    if kind == "R":
        sf = np.nan_to_num(s, nan=-1.0)
        add = ramp(sf, p["L"], p["T"], p["W"], p["C"]) + ramp(sf, p["M"], p["U"], p["W"], p["C"])
        return np.where(oc, D + add, D).astype(np.float32)
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
    ap.add_argument("--combo", action="store_true", help="score combo_specs() into rows_<split>_combo.csv.gz")
    ap.add_argument("--ramp", action="store_true", help="score ramp_specs() into rows_<split>_ramp.csv.gz")
    ap.add_argument("--hf", action="store_true", help="score hf_specs() into rows_<split>_hf.csv.gz")
    ap.add_argument("--self", dest="selfq", action="store_true", help="score self_specs() into rows_<split>_self.csv.gz")
    a = ap.parse_args()
    tag = "_combo" if a.combo else "_ramp" if a.ramp else "_self" if a.selfq else "_hf" if a.hf else ""
    out = paths.data("extra", "gfe-wind-tool") / ("rows_%s%s.csv.gz" % (a.split, tag))
    if a.split == "held_out" and out.exists():  # once per product set
        sys.exit("held-out rows exist (%s): scored once already" % out)
    labels = (combo_specs() if a.combo else ramp_specs() if a.ramp else self_specs() if a.selfq else hf_specs() if a.hf else specs())
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
