#!/usr/bin/env python3
"""Tune, choose and score the strong-core lifts from the cases build.py wrote (design.md).

  python3 score.py [--workers 3]       TUNE weeks: counts for every grid product, mechanical selection by the win
                                       line, 5-fold whole-week out-of-fold check; writes tune_*.csv and
                                       FINAL_CHOICE.json (must exist before any held-out scoring)
  python3 score.py --final             HELD-OUT weeks, once: refuses to rerun, refuses on missing cases
  python3 score.py --lines             after --final: the storm warning line (>= T kt) on the held-out cases

Products (kt on the basin grid). strongest = max(gfs, ifs); cand = ocean & (base >= 28 | strongest >= 34).
 Page family, baseline CL = gale_lift(r10 + 5 where P >= 0.35, floor 34 where Pg >= 0.6) (core-lift-bias):
  CL8        the same with +8 kt (#70 rival)
  CLS1[L,T]  max(CL, r10 + L where strongest >= T, ocean)           (rk.features.strong_lift)
  CLS2[T]    max(CL, strongest) where strongest >= T, ocean
  CLS3[a]    on cand cells with 925 mb data, base CL: target = s925 x f(sea-air); max(base, base + a (target - base))
 GFE family, baseline D = rk.features.det_blend(gfs, ifs) (PR #95):
  DG         D + 5 where cand & GEFS 48 kt share (0.5 deg, neighbourhood max) >= 0.25   (GEFS-only study lift)
  DC[L]      D + L on cand cells                                       (constant rival)
  DS1[L,T]   D + L where strongest >= T, ocean
  DS2[T]     max(D, strongest) where strongest >= T, ocean
  DS3[a]     CLS3's mix-down on D
  DS13       DS1 then DS3, each with its own tuned parameters
 f(sea-air) = 0.87 (<2 C), 0.94 (2-5), 1.04 (5-8), 1.13 (>=8), sea-air = skin - 2 m air temperature (GFS).
 Grids: L 2..12 step 2; T 36..52 (S1), 40..56 (S2) step 2; a 0.25, 0.5, 0.75. Drill variants (fixed, reported
 whatever the tune says): S1 at T = 44, L = 6 and 8, both families.
Counts per case and product exactly as core-lift-bias fit_score (5x5 deg tiles with >= 150 seen cells for 34/48/64:
nt h m fa; seen cells fc ob cau; analysis afc aob acau at 00/12Z valid). fit_score's Tiles / pooled / passes / paired
are imported.
Selection (per basin, per candidate kind; mechanical): pass = storm area (fc48/ob48) <= 1.5, gale area <= 1.3 or <=
baseline + 0.01, gale tile CSI >= baseline - 0.01; among the passing parameters the highest storm-tile catch
h48/(h48+m48); none passing -> no choice (the candidate is dropped). CLS3 / DS3 are tuned on the cases that have
GFS 925 mb data, against the baseline on those same cases. tune_oof.csv repeats the pick leaving each tune fold out.
"""
import argparse
import gzip
import json
import multiprocessing as mp
import os
import shutil
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parent / "2026-11-05-core-lift-bias"))
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402
from scipy import ndimage  # noqa: E402
import pandas as pd  # noqa: E402

import build as B  # noqa: E402
import fit_score as F  # noqa: E402
from rk import basins as RB, cases, features, paths, score  # noqa: E402

THRS = F.THRS
LS = tuple(range(2, 13, 2))
T1S = tuple(range(36, 53, 2))
T2S = tuple(range(40, 57, 2))
AS = (0.25, 0.5, 0.75)
DRILL_T, DRILL_LS = 44, (6, 8)
GEFS_X, GEFS_LIFT = 0.25, 5.0
CAND_STRONG_KT = 34.0
SA_EDGES, SA_F = (2.0, 5.0, 8.0), (0.87, 0.94, 1.04, 1.13)
PAGE_KINDS, GFE_KINDS = ("CLS1", "CLS2", "CLS3"), ("DC", "DS1", "DS2", "DS3")
BASE_OF = {k: "CL" for k in PAGE_KINDS}
BASE_OF.update({k: "D" for k in GFE_KINDS + ("DS13",)})
# Fixed products (nothing tuned, reported only): gated 925 mb mix-down and the desk's Stability Height
FIXED_PAGE, FIXED_GFE = ("CLS3g",), ("DS3g", "SHs", "SHl", "SHe")
FIXED = FIXED_PAGE + FIXED_GFE
BASE_OF.update({"CLS3g": "CL", "DS3g": "D", "SHs": "D", "SHl": "D", "SHe": "D"})
LIFT_KINDS = ("DS3g", "CLS3g", "SHs", "SHl", "SHe")   # products with per-case "where it lifts" columns
DESK = ("DS3g", "CLS3g", "SHs", "SHl", "SHe", "D", "CL", "DG")
GATE_S925_KT, GATE_SA_C = 34.0, 5.0
SH_EXPONENT, SH_RIM = 0.15, 2        # Stability_Model_Blender: POWER_LAW_EXPONENT, 10 m -> 30 m; mask grown 2 cells
LOW_KINDS = ("CLS3", "DS3", "DS13") + FIXED
LINE_TS, LINE_THR = tuple(range(33, 51)), (48, 64)
LINE_KEYS = ("events", "hits", "obs_cells", "obs_in", "cells", "bad_cells", "warned_cells", "reach_cells")


# ---- products ----

def name(spec):
    kind, L, T, a = spec
    return "_".join([kind] + (["L%d" % L] if L is not None else []) + (["T%d" % T] if T is not None else [])
                    + (["a%.2f" % a] if a is not None else []))


def kind_of(label):
    return label.split("_")[0]


def fixed_specs():
    return [(k, None, None, None) for k in FIXED]


def grid_specs():
    s = [("CL", None, None, None), ("CL8", None, None, None), ("D", None, None, None), ("DG", None, None, None)]
    s += [("CLS1", L, T, None) for L in LS for T in T1S] + [("CLS2", None, T, None) for T in T2S]
    s += [("CLS3", None, None, a) for a in AS]
    s += [("DC", L, None, None) for L in LS]
    s += [("DS1", L, T, None) for L in LS for T in T1S] + [("DS2", None, T, None) for T in T2S]
    s += [("DS3", None, None, a) for a in AS]
    return s


def sea_air_factor(sa):
    return np.select([sa < SA_EDGES[0], sa < SA_EDGES[1], sa < SA_EDGES[2]], SA_F[:3], SA_F[3]).astype(np.float32)


def mixdown(base, strong, s925, sa, ocean, a):
    """On cand cells with 925 mb data: out = max(base, base + a (s925 f(sa) - base)); elsewhere base."""
    hi = base >= features.CAND_R10
    if strong is not None:
        hi = hi | (strong >= CAND_STRONG_KT)
    cand = ocean & hi & np.isfinite(s925) & np.isfinite(sa)
    target = s925 * sea_air_factor(sa)
    return np.where(cand, np.maximum(base, base + np.float32(a) * (target - base)), base).astype(np.float32)


def gated_mixdown(base, s925, sa, ocean):
    """Fixed gated 925 mb mix-down: where ocean & s925 >= 34 kt & sea-air >= 5 C, max(base, s925 f(sa)) at the full
    factor (1.04 for 5-8 C, 1.13 above); base elsewhere. Raise only; NaN inputs fail the gate."""
    with np.errstate(invalid="ignore"):
        gate = ocean & (s925 >= GATE_S925_KT) & (sa >= GATE_SA_C)
    return np.where(gate, np.maximum(base, s925 * sea_air_factor(sa)), base).astype(np.float32)


def desk_stability_wind(base, t_sfc_k, p_sfc_hpa, t925_k, rim=SH_RIM, exponent=SH_EXPONENT):
    """The desk's Stability Height step (GFE Stability_Model_Blender._getStabilityHeightWind / _applyWindWithMask) on
    a speed grid. Unstable where theta925 <= theta_sfc, theta = T (1000 / p)^(2/7) with p = 925 hPa aloft and the
    surface pressure below (the tool: GFS p:SFC, ECMWF pmsl; here the caller passes MSLP, kt-free hPa). Unstable
    wind x (30 / 10)^exponent. The mask is grown `rim` cells (square) and the factor tapers linearly over the rim:
    weight = distance to the edge of the grown mask / (rim + 1), capped at 1, so mask cells keep the full factor.
    (The tool's taper is 4 cells wide, SWATH_EDGE x TAPER_WIDTH_MULTIPLIER; the card asks for the 2-cell rim.)
    Raise only. NaN inputs count as stable."""
    base = np.asarray(base, np.float32)
    with np.errstate(invalid="ignore"):
        th925 = np.asarray(t925_k, np.float64) * (1000.0 / 925.0) ** (2.0 / 7.0)
        th_sfc = np.asarray(t_sfc_k, np.float64) * (1000.0 / np.asarray(p_sfc_hpa, np.float64)) ** (2.0 / 7.0)
        unstable = th925 <= th_sfc
    if not unstable.any():
        return base
    grown = ndimage.binary_dilation(unstable, structure=np.ones((3, 3), bool), iterations=rim)
    w = np.clip(ndimage.distance_transform_edt(grown) / (rim + 1.0), 0.0, 1.0)
    return (base * (1.0 + w * (3.0 ** exponent - 1.0))).astype(np.float32)


def prep(path):
    z = np.load(path)
    d = {k: z[k] for k in z.files}
    for k in ("r10", "P", "Pg", "spd", "anl", "det", "gfs", "ifs", "p48nb_h", "s925", "sa", "st925"):
        if k in d:
            d[k] = d[k].astype(np.float32)
    d["has_low"] = "s925" in d and "sa" in d
    d["strong"] = np.fmax(d["gfs"], d["ifs"]) if "gfs" in d and "ifs" in d else None
    if "r10" in d:
        d["CL"] = F.corelift(d["r10"], d["P"], d["Pg"])
        d["CL8"] = F.corelift(d["r10"], d["P"], d["Pg"], 8.0)
    return d


def make_fixed(kind, d):
    oc = d["ocean"]
    if kind == "CLS3g":
        return gated_mixdown(d["CL"], d["s925"], d["sa"], oc) if "CL" in d and d["has_low"] else None
    if "det" not in d:
        return None
    if kind == "DS3g":
        return gated_mixdown(d["det"], d["s925"], d["sa"], oc) if d["has_low"] else None
    if kind == "SHe":      # reference: the tool's "Entire" mode, the factor on every ocean cell
        return np.where(oc, d["det"] * np.float32(3.0 ** SH_EXPONENT), d["det"]).astype(np.float32)
    if kind == "SHs":      # strict, GFS style: 2 m air temperature and GFS MSLP
        if not all(k in d for k in ("g_t2", "g_t925", "gfs_msl")):
            return None
        return desk_stability_wind(d["det"], d["g_t2"], d["gfs_msl"], d["g_t925"])
    if all(k in d for k in ("i_skt", "i_t925", "ifs_msl")):      # SHl, loose, ECMWF style: IFS skin temperature
        return desk_stability_wind(d["det"], d["i_skt"], d["ifs_msl"], d["i_t925"])
    if all(k in d for k in ("g_skt", "g_t925", "gfs_msl")):      # no IFS low file: GFS skin temperature
        d["_fb"] = True
        return desk_stability_wind(d["det"], d["g_skt"], d["gfs_msl"], d["g_t925"])
    return None


def make(spec, d):
    """The product grid for spec on case d, or None when the case lacks an input of it."""
    kind, L, T, a = spec
    if kind in FIXED:
        return make_fixed(kind, d)
    oc, s = d["ocean"], d["strong"]
    if kind in ("CL", "CL8"):
        return d.get(kind)
    if kind in ("D", "DG", "DC", "DS1", "DS2", "DS3", "DS13"):
        if "det" not in d:
            return None
        D = d["det"]
        if kind == "D":
            return D
        if kind == "DG":
            if "p48nb_h" not in d:
                return None
            cand = oc & ((D >= features.CAND_R10) | ((s >= CAND_STRONG_KT) if s is not None else False))
            return np.where(cand & (d["p48nb_h"] >= GEFS_X), D + np.float32(GEFS_LIFT), D).astype(np.float32)
        if kind == "DC":
            cand = oc & ((D >= features.CAND_R10) | ((s >= CAND_STRONG_KT) if s is not None else False))
            return np.where(cand, D + np.float32(L), D).astype(np.float32)
        if s is None:
            return None
        if kind == "DS2":
            return np.where(oc & (s >= T), np.maximum(D, s), D).astype(np.float32)
        if kind == "DS1":
            return features.strong_lift(D, [s], L, T, oc)
        if not d["has_low"]:
            return None
        if kind == "DS3":
            return mixdown(D, s, d["s925"], d["sa"], oc, a)
        return mixdown(features.strong_lift(D, [s], L, T, oc), s, d["s925"], d["sa"], oc, a)    # DS13
    if "CL" not in d or s is None:
        return None
    CL = d["CL"]
    if kind == "CLS1":
        return np.maximum(CL, features.strong_lift(d["r10"], [s], L, T, oc))
    if kind == "CLS2":
        return np.where(oc & (s >= T), np.maximum(CL, s), CL).astype(np.float32)
    if kind == "CLS3" and d["has_low"]:
        return mixdown(CL, s, d["s925"], d["sa"], oc, a)
    return None


# ---- counts (fit_score's definitions, observed-side work done once per case) ----

COLS = ["%s%d" % (c, t) for t in THRS for c in ("nt", "h", "m", "fa", "fc", "ob", "cau", "afc", "aob", "acau")] + ["anl_ok"]


class Counter:
    def __init__(self, basin, d):
        self.tiles = F.Tiles(basin, d["seen"])
        self.seen = d["seen"]
        spd, anl = np.nan_to_num(d["spd"], nan=-1), np.nan_to_num(d["anl"], nan=-1)
        self.aw = np.isfinite(d["anl"])
        self.o = {t: self.seen & (spd >= t) for t in THRS}
        self.ao = {t: self.aw & (anl >= t) for t in THRS}
        self.tile_o = {}
        if self.tiles.ok:
            for t in THRS:
                self.tile_o[t] = np.bincount(self.tiles.inv, weights=self.o[t][self.seen])[self.tiles.keep] > 0

    def counts(self, fc):
        r = {}
        fcn = np.nan_to_num(fc, nan=-1)
        for t in THRS:
            f = self.seen & (fcn >= t)
            af = self.aw & (fcn >= t)
            if self.tiles.ok:
                ft = np.bincount(self.tiles.inv, weights=f[self.seen])[self.tiles.keep] > 0
                o = self.tile_o[t]
                nt, h, m, fa = int(self.tiles.keep.sum()), int((o & ft).sum()), int((o & ~ft).sum()), int((~o & ft).sum())
            else:
                nt = h = m = fa = 0
            r.update({"nt%d" % t: nt, "h%d" % t: h, "m%d" % t: m, "fa%d" % t: fa, "fc%d" % t: int(f.sum()),
                      "ob%d" % t: int(self.o[t].sum()), "cau%d" % t: int((f & self.o[t]).sum()),
                      "afc%d" % t: int(af.sum()), "aob%d" % t: int(self.ao[t].sum()),
                      "acau%d" % t: int((af & self.ao[t]).sum())})
        r["anl_ok"] = int(self.aw.any())
        return [r[c] for c in COLS]


LIFT_COLS = ["n_lift", "n_lift_seen", "n_lift_a34", "n_lift_a48", "sum_err_low", "n_err_low"]


def lift_columns(f, base, d):
    """Where a product lifts its base (ocean cells, product > base + 0.05) and how ASCAT sees those cells."""
    lift = d["ocean"] & (f > base + 0.05)
    ls = lift & d["seen"]
    spd = np.nan_to_num(d["spd"], nan=-1)
    low = ls & (base < 34)
    return [int(lift.sum()), int(ls.sum()), int((ls & (spd >= 34)).sum()), int((ls & (spd >= 48)).sum()),
            float((f - spd)[low].sum()), int(low.sum())]


def lift_summary(desk):
    """Pooled per basin and product: share of seen lifted cells at ASCAT 34+ / 48+, mean (product - ASCAT) where base < 34."""
    x = desk[desk["product"].isin(LIFT_KINDS)]
    g = x.groupby(["basin", "product"])[LIFT_COLS].sum().reset_index()
    g["share_a34"] = g.n_lift_a34 / g.n_lift_seen.replace(0, np.nan)
    g["share_a48"] = g.n_lift_a48 / g.n_lift_seen.replace(0, np.nan)
    g["mean_err_base_lt34"] = g.sum_err_low / g.n_err_low.replace(0, np.nan)
    return g


def score_job(args):
    basin, cyc, step, path, specs = args
    d = prep(path)
    cnt = Counter(basin, d)
    labels, rows, lifts = [], [], []
    for label, spec in specs:
        f = make(spec, d)
        if f is not None:
            labels.append(label)
            rows.append(cnt.counts(f))
            lifts.append(dict(zip(LIFT_COLS, lift_columns(f, d["CL"] if spec[0] == "CLS3g" else d["det"], d)))
                         if spec[0] in LIFT_KINDS else {})
    meta = dict(basin=basin, cycle=cyc, step=step, group=F.group_of(step), fold=F.folds(cyc), has_low=d["has_low"],
                shl_fallback=bool(d.get("_fb", False)))
    return meta, labels, np.array(rows, np.int64).reshape(-1, len(COLS)), lifts


def load_cases(basin, split):
    root = paths.cache("extra", "strong-core-lift", basin)
    out = []
    for p in sorted(root.glob("*.npz")):
        tag, step = p.stem.split("_f")
        cyc = cases.parse(tag)
        if cases.split(cyc) == split:
            out.append((cyc, int(step), p))
    return out


def run_pool(jobs, workers):
    t0 = time.time()
    with mp.get_context("spawn").Pool(workers) as pool:
        for i, r in enumerate(pool.imap_unordered(score_job, jobs, chunksize=4), 1):
            if i % 500 == 0 or i == len(jobs):
                print("[%d/%d cases] %.0fs" % (i, len(jobs), time.time() - t0), flush=True)
            yield r


# ---- selection ----

def pick(summ, kind, order):
    """Passing parameters and the best (max storm-tile catch) for one candidate kind. summ: pooled by product."""
    bl = summ[summ["product"] == BASE_OF[kind]]
    if bl.empty:
        return [], None
    base = bl.iloc[0]
    ok, best = [], None
    for lab in order:
        r = summ[summ["product"] == lab]
        if r.empty:
            continue
        r = r.iloc[0]
        if F.passes(r, base):
            ok.append(lab)
            if best is None or r.pod48 > best[1] + 1e-12:
                best = (lab, r.pod48)
    return ok, (best[0] if best else None)


def pooled_for(df, kind, by=("product",)):
    """Pooled counts of the rows a kind is judged on: all cases, or only those with 925 mb data."""
    sub = df[df["has_low"]] if kind in LOW_KINDS else df
    return F.pooled(sub, list(by))


def spec_of(label):
    kind = kind_of(label)
    p = {x[0]: x[1:] for x in label.split("_")[1:]}
    return (kind, int(p["L"]) if "L" in p else None, int(p["T"]) if "T" in p else None,
            float(p["a"]) if "a" in p else None)


def tune(a):
    res = Path(a.results)
    if (res / "FINAL_RUN.json").exists():
        sys.exit("the held-out run has been made; FINAL_CHOICE.json is frozen")
    basins = a.basins.split(",")
    specs = [(name(s), s) for s in grid_specs() + fixed_specs()]
    order = {k: [name(s) for s in grid_specs() if s[0] == k] for k in PAGE_KINDS + GFE_KINDS}
    jobs, sizes = [], {}
    for b in basins:
        cs = load_cases(b, "tune")
        sizes[b] = len(cs)
        jobs += [(b, c, s, p, specs) for c, s, p in cs]
    print("tune cases: %s" % sizes, flush=True)
    acc, ncase, desk = {}, {}, []
    for meta, labels, M, lifts in run_pool(jobs, a.workers):
        for lab, row, lf in zip(labels, M, lifts):
            fb = meta["shl_fallback"] and lab == "SHl"
            k = (meta["basin"], meta["fold"], meta["group"], meta["has_low"], fb, lab)
            acc[k] = acc.get(k, 0) + row
            ncase[k] = ncase.get(k, 0) + 1
            if lab in DESK:
                desk.append(dict(meta, product=lab, **dict(zip(COLS, row)), **lf))
    if not acc:
        sys.exit("no tune cases scored: run build.py first")
    df = pd.DataFrame([dict(zip(["basin", "fold", "group", "has_low", "fb", "product"], k), n=ncase[k], **dict(zip(COLS, v)))
                       for k, v in acc.items()])
    df.to_csv(res / "tune_counts.csv", index=False)
    pd.DataFrame(desk).to_csv(res / "tune_desk_rows.csv", index=False)
    lift_summary(pd.DataFrame(desk)).to_csv(res / "tune_lift_summary.csv", index=False)
    choice, sel, oof = {}, [], []
    for b in basins:
        db = df[df.basin == b]
        ch = {"page": {}, "gfe": {}, "passed": {}}
        for kind in PAGE_KINDS + GFE_KINDS:
            summ = pooled_for(db, kind)
            ok, best = pick(summ, kind, order[kind])
            fam = "page" if kind in PAGE_KINDS else "gfe"
            ch[fam][kind] = None if best is None else dict(zip("LTa", spec_of(best)[1:]), name=best)
            ch["passed"][kind] = ok
            base = summ[summ["product"] == BASE_OF[kind]]
            if base.empty:
                continue
            base = base.iloc[0]
            for lab in order[kind]:
                r = summ[summ["product"] == lab]
                if r.empty:
                    continue
                r = r.iloc[0]
                sel.append(dict(basin=b, kind=kind, product=lab, passes_line=bool(F.passes(r, base)),
                                chosen=lab == best, pod48=r.pod48, pod48_gain=r.pod48 - base.pod48, area48=r.area48,
                                area34=r.area34, csi34_change=r.csi34 - base.csi34, catch48=r.catch48,
                                catch64=r.catch64, area64=r.area64, far48=r.far48))
            # out of fold: pick on the other folds, count the left-out fold with that pick
            tot = {"kind": kind, "basin": b}
            sub = db[db.has_low] if kind in LOW_KINDS else db
            picks = []
            cs = [c for c in COLS]
            agg_c, agg_b = np.zeros(len(COLS)), np.zeros(len(COLS))
            for k in range(F.FOLDS):
                s_k = F.pooled(sub[sub.fold != k], ["product"])
                _, bk = pick(s_k, kind, order[kind])
                picks.append(bk)
                held = sub[sub.fold == k]
                agg_b += held[held["product"] == BASE_OF[kind]][cs].sum().to_numpy()
                agg_c += held[held["product"] == (bk or BASE_OF[kind])][cs].sum().to_numpy()
            ci, bi = dict(zip(cs, agg_c)), dict(zip(cs, agg_b))
            pod = lambda c: c["h48"] / max(c["h48"] + c["m48"], 1)
            oof.append(dict(tot, folds_with_pick=sum(p is not None for p in picks), picks=";".join(str(p) for p in picks),
                            oof_pod48=pod(ci), base_pod48=pod(bi), oof_gain=pod(ci) - pod(bi),
                            oof_area48=ci["fc48"] / max(ci["ob48"], 1), oof_area34=ci["fc34"] / max(ci["ob34"], 1)))
        choice[b] = ch
        # fixed products: reported against their baseline on the same cases, never selected
        for kind in FIXED:
            summ = pooled_for(db, kind)
            lab = kind
            base, r = summ[summ["product"] == BASE_OF[kind]], summ[summ["product"] == lab]
            if base.empty or r.empty:
                continue
            base, r = base.iloc[0], r.iloc[0]
            sel.append(dict(basin=b, kind=kind, product=lab, passes_line=bool(F.passes(r, base)), chosen=False,
                            pod48=r.pod48, pod48_gain=r.pod48 - base.pod48, area48=r.area48, area34=r.area34,
                            csi34_change=r.csi34 - base.csi34, catch48=r.catch48, catch64=r.catch64, area64=r.area64,
                            far48=r.far48))
        shl = db[db["product"] == "SHl"]
        ch["shl_cases"] = int(shl["n"].sum())
        ch["shl_gfs_skin_fallback_cases"] = int(shl[shl["fb"]]["n"].sum())
    # DS13: the two tuned pieces together, on the tune cases that have 925 mb data
    d13 = []
    for b in basins:
        c1, c3 = choice[b]["gfe"].get("DS1"), choice[b]["gfe"].get("DS3")
        choice[b]["gfe"]["DS13"] = None
        if c1 and c3:
            sp = ("DS13", c1["L"], c1["T"], c3["a"])
            d13.append((b, sp, [(name(sp), sp), ("D", ("D", None, None, None))]))
    if d13:
        jobs = [(b, c, s, p, sps) for b, sp, sps in d13 for c, s, p in load_cases(b, "tune")]
        acc13 = {}
        for meta, labels, M, _ in run_pool(jobs, a.workers):
            if not meta["has_low"]:
                continue
            for lab, row in zip(labels, M):
                k = (meta["basin"], lab)
                acc13[k] = acc13.get(k, 0) + row
        for b, sp, _ in d13:
            if (b, "D") not in acc13:
                continue
            t = pd.DataFrame([dict(product=l, **dict(zip(COLS, acc13[(b, l)]))) for l in (name(sp), "D")])
            s = F.pooled(t.assign(has_low=True), ["product"])
            r, base = s[s["product"] == name(sp)].iloc[0], s[s["product"] == "D"].iloc[0]
            choice[b]["gfe"]["DS13"] = dict(L=sp[1], T=sp[2], a=sp[3], name=name(sp), passes_line=bool(F.passes(r, base)))
            sel.append(dict(basin=b, kind="DS13", product=name(sp), passes_line=bool(F.passes(r, base)), chosen=True,
                            pod48=r.pod48, pod48_gain=r.pod48 - base.pod48, area48=r.area48, area34=r.area34,
                            csi34_change=r.csi34 - base.csi34, catch48=r.catch48, catch64=r.catch64, area64=r.area64,
                            far48=r.far48))
    pd.DataFrame(sel).to_csv(res / "tune_selection.csv", index=False)
    pd.DataFrame(oof).to_csv(res / "tune_oof.csv", index=False)
    F.pooled(df, ["basin", "product"]).to_csv(res / "tune_summary.csv", index=False)   # DS3 / CLS3 rows only exist where 925 mb data do
    choice["note"] = ("tune weeks only (cases per basin %s); chosen = passing parameter with the highest storm-tile catch; "
                      "tune_oof.csv has the out-of-fold check; drill variants S1 T=%d L=%s are scored whatever this says"
                      % (sizes, DRILL_T, DRILL_LS))
    json.dump(choice, open(res / "FINAL_CHOICE.json", "w"), indent=1)
    print(pd.DataFrame(sel).query("chosen").round(3).to_string())
    print(pd.DataFrame(oof).round(3).to_string())
    print("chosen:", json.dumps({b: {f: choice[b][f] for f in ("page", "gfe")} for b in basins}))


# ---- final ----

def final_specs(ch):
    """[(label, spec)] for one basin: baselines, chosen candidates, drill variants."""
    out = [("CL", ("CL", None, None, None)), ("CL8", ("CL8", None, None, None)), ("D", ("D", None, None, None)),
           ("DG", ("DG", None, None, None))]
    for fam in ("page", "gfe"):
        for kind, c in ch[fam].items():
            if c:
                out.append((kind, (kind, c.get("L"), c.get("T"), c.get("a"))))
    out += [(k, (k, None, None, None)) for k in FIXED]
    for label, c in (ch.get("equal_area") or {}).items():   # equal-area picks (tune), added before --final
        out.append((label, (c["kind"], c.get("L"), c.get("T"), c.get("a"))))
    for kind in ("CLS1", "DS1"):
        for L in DRILL_LS:
            out.append(("%s_drill_L%d_T%d" % (kind, L, DRILL_T), (kind, L, DRILL_T, None)))
    return out


def held_out_jobs(res, basins, steps):
    exp = [(b, c, s) for b, c, s in B.C.all_cases(basins, steps) if cases.held_out(c)]
    have = [e for e in exp if B.out_path(*e).exists()]
    return exp, have


def check_held_out(basins, steps, allow):
    exp, have = held_out_jobs(None, basins, steps)
    print("held-out cases expected %d, present %d" % (len(exp), len(have)), flush=True)
    flags = {"missing_file": len(exp) - len(have)}
    for b, c, s in have:
        z = np.load(B.out_path(b, c, s))
        for k, miss in (("r10", "missing_page"), ("det", "missing_det"), ("gfs", "missing_gfs"), ("ifs", "missing_ifs"),
                        ("p48nb_h", "missing_gefs"), ("s925", "no_low")):
            if k not in z.files:
                flags[miss] = flags.get(miss, 0) + 1
    print("held-out missing_* counts:", flags, flush=True)
    if any(flags.values()) and not allow:
        sys.exit("refusing: held-out inputs are missing (truth or fields); rebuild, or pass --allow-missing to score "
                 "what exists and say so")
    return have


def final(a):
    res = Path(a.results)
    basins = a.basins.split(",")
    steps = tuple(int(s) for s in a.steps.split(","))
    if not (res / "FINAL_CHOICE.json").exists():
        sys.exit("FINAL_CHOICE.json missing: run the tune step first")
    if (res / "FINAL_RUN.json").exists() or list(res.glob("final_case_counts.csv*")):
        sys.exit("the held-out run has already been made; it is a one-time gate")
    choice = json.load(open(res / "FINAL_CHOICE.json"))
    have = check_held_out(basins, steps, a.allow_missing)
    jobs, params = [], {}
    for b, c, s in have:
        sp = final_specs(choice[b])
        params.update({(b, l): name(x) for l, x in sp})
        jobs.append((b, c, s, B.out_path(b, c, s), sp))
    json.dump({"ran": pd.Timestamp.now("UTC").isoformat(), "cases": len(jobs)}, open(res / "FINAL_RUN.json", "w"))
    rows = []
    for meta, labels, M, lifts in run_pool(jobs, a.workers):
        for lab, r, lf in zip(labels, M, lifts):
            rows.append(dict(meta, product=lab, params=params[(meta["basin"], lab)], **dict(zip(COLS, r)), **lf))
    df = pd.DataFrame(rows)
    out = res / "final_case_counts.csv"
    df.to_csv(out, index=False)
    if out.stat().st_size > 1e6:
        with open(out, "rb") as fi, gzip.open(str(out) + ".gz", "wb") as fo:
            shutil.copyfileobj(fi, fo)
        out.unlink()
    summ = F.pooled(df, ["basin", "product"])
    summ["n_cases"] = df.groupby(["basin", "product"]).size().to_numpy()
    summ = summ.merge(df[["basin", "product", "params"]].drop_duplicates(), on=["basin", "product"])
    fb = df[df["product"] == "SHl"].groupby("basin")["shl_fallback"].sum()
    summ["n_shl_gfs_skin_fallback"] = [int(fb.get(b, 0)) if p == "SHl" else 0 for b, p in zip(summ.basin, summ["product"])]
    desk = df[df["product"].isin(DESK)]
    desk.to_csv(res / "final_desk_rows.csv", index=False)
    ls = lift_summary(desk)
    summ = summ.merge(ls[["basin", "product", "share_a34", "share_a48", "mean_err_base_lt34"]], on=["basin", "product"],
                      how="left")
    print("case counts per product:", summ.groupby("product")["n_cases"].sum().to_dict(),
          "SHl cases on the GFS skin fallback:", fb.to_dict())
    summ.to_csv(res / "final_summary.csv", index=False)
    F.pooled(df, ["basin", "group", "product"]).to_csv(res / "final_by_lead.csv", index=False)
    present = set(df["product"])
    pairs = []
    for p in sorted(present):
        k = kind_of(p)
        if k in PAGE_KINDS + FIXED_PAGE:
            pairs += [(p, "CL"), (p, "CL8")]
        elif k in GFE_KINDS + FIXED_GFE + ("DS13",):
            pairs += [(p, "D"), (p, "DG")] + ([(p, "DC")] if (k.startswith("DS") and "DC" in present) else [])
    pairs += [("CL8", "CL"), ("DG", "D")]
    pr = []
    for base in sorted({b for _, b in pairs}):
        prods = [p for p, b in pairs if b == base and base in present]
        if prods:
            pr.append(F.paired(df, prods, baseline=base))
    pr = pd.concat(pr, ignore_index=True)
    pr.to_csv(res / "final_paired.csv", index=False)
    cols = ["basin", "product", "n_cases", "pod48", "far48", "csi48", "catch48", "area48", "csi34", "catch34", "area34",
            "catch64", "area64", "acatch48", "aarea48"]
    print(summ[cols].round(3).to_string())
    print(pr[pr.metric.isin(["pod48", "area48", "csi34"])].round(3).to_string())


# ---- warning lines ----

def line_job(args):
    basin, cyc, step, path, specs = args
    d = prep(path)
    opc = RB.opc_mask(basin) & d["ocean"]
    rows = []
    for label, spec in specs:
        f = make(spec, d)
        if f is None:
            continue
        for thr in LINE_THR:
            for T in LINE_TS:
                r = score.warning_events(f >= T, d["spd"], d["seen"], thr, mask=opc)
                rows.append(dict(basin=basin, cycle=cyc, step=step, product=label, T=T, obs_thr=thr,
                                 **{k: r[k] for k in LINE_KEYS}))
    return rows


def lines(a):
    res = Path(a.results)
    if not (res / "FINAL_RUN.json").exists():
        sys.exit("run --final first")
    choice = json.load(open(res / "FINAL_CHOICE.json"))
    basins = a.basins.split(",")
    steps = tuple(int(s) for s in a.steps.split(","))
    _, have = held_out_jobs(res, basins, steps)
    jobs = []
    for b, c, s in have:
        sp = [x for x in final_specs(choice[b]) if x[0] not in FIXED]
        jobs.append((b, c, s, B.out_path(b, c, s), sp))
    rows, t0 = [], time.time()
    with mp.get_context("spawn").Pool(a.workers) as pool:
        for i, r in enumerate(pool.imap_unordered(line_job, jobs, chunksize=4), 1):
            rows += r
            if i % 200 == 0:
                print("[%d/%d] %.0fs" % (i, len(jobs), time.time() - t0), flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(res / "lines_case_counts.csv.gz", index=False)
    s = df.groupby(["basin", "product", "obs_thr", "T"])[list(LINE_KEYS)].sum().reset_index()
    s["covered"] = s.obs_in / s.obs_cells
    s["area"] = s.cells / s.obs_cells
    s["caught"] = s.hits / s.events
    s["false_cells"] = s.bad_cells / s.cells
    s.to_csv(res / "lines_summary.csv", index=False)
    print(s[s["T"] == 39].round(3).to_string())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--lines", action="store_true")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--basins", default="natl,npac")
    ap.add_argument("--steps", default=",".join(map(str, B.STEPS_ALL)), help="step set build.py used (held-out check)")
    ap.add_argument("--allow-missing", action="store_true", help="--final: score what exists although inputs are missing")
    ap.add_argument("--results", default=str(HERE), help="folder for outputs and FINAL_CHOICE / FINAL_RUN")
    a = ap.parse_args()
    if a.final and a.lines:
        sys.exit("--final and --lines are separate runs")
    (final if a.final else lines if a.lines else tune)(a)


if __name__ == "__main__":
    main()
