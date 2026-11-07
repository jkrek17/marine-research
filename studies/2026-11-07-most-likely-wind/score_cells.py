#!/usr/bin/env python3
"""Score every candidate grid against ASCAT on the cases build_cases.py wrote (design.md).

  python3 score_cells.py --split tune|held_out [--workers 3]

Writes to rk.paths.data("extra", "most-likely-wind"):
  err_<split>.csv.gz    one row per case x product x cut: basin cycle step week product cut band n sum_err sum_abs
                        sum_sq.  cut = "truth" (ASCAT band), "fc" (the grid's own band), "all" (band "all").
                        Bands (kt) <30, 30-47, 48-63, 64+ (rk.score.band_error).
  tiles_<split>.csv.gz  one row per case x product: 5x5 deg tile counts nt/h/m/fa and cell counts fc/ob/cau at
                        34/48/64 kt (core-lift-bias fit_score.Tiles, the strong-core-lift counting)
  hist_<split>.npz      per basin x ISO week x product: 1 kt histograms (0..119, last bin open) of the grid over
                        seen cells, and over seen cells with ASCAT >= 34 / 48 / 64, for equal-area catch
Cells: open water (GFS land/ice), ASCAT-seen. Only cases with the core chances (P, Pg) are scored, so every
product is on the same cells.
Products (kt):
  gfs ifs aifs        raw deterministic
  blend               page blend: support-weighted GFS/ECMWF/AIFS (AIFS x0.5) + spread term
  blend_nospread      the same without the spread term
  blend_a0 blend_a1   AIFS weight 0 / 1 (with the spread term)
  floor               blend + the gale-core floor (34 where gale-core chance >= 60%), no lift
  CL                  Core Lifted: blend + 5 where core likelihood >= 35%, then the floor
  best                Best Wind exactly as awips-tools storm.best_wind + the floor (ramps 0->6 over 36-40, 0->4
                      over 44-48 of max(GFS, ECMWF); HF 0->6 over 52-56 where GEFS 48 kt share (NB max) >= 30%;
                      open water |lat| >= 25)
  best_x<s>           ramps and HF core sizes x s (0.5, 1.5, 2)
  best_s<d>           ramp and HF starts moved d kt (-4, -2, +2, +4)
  best_nohf           ramps only
  best_a0 best_a1     Best Wind on blend_a0 / blend_a1
  best_nospread       Best Wind on blend_nospread
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
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parent / "2026-11-05-core-lift-bias"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import fit_score as F  # noqa: E402
from rk import basins, cases, paths, score  # noqa: E402

OUT = paths.data("extra", "most-likely-wind")
BAND_NAMES = ("<30", "30-47", "48-63", "64+")
NBIN = 120
RAMPS, HF, HF_P, WIDTH, MIN_LAT = ((6.0, 36.0), (4.0, 44.0)), (6.0, 52.0), 0.30, 4.0, 25.0
LIFT_P, LIFT_KT, GALE_P, GALE_KT = F.LIFT_P, F.LIFT_KT, F.GALE_P, F.GALE_KT

PRODUCTS = (["gfs", "ifs", "aifs", "blend", "blend_nospread", "blend_a0", "blend_a1", "floor", "CL", "best",
             "best_nohf", "best_nospread", "best_a0", "best_a1"]
            + ["best_x%g" % s for s in (0.5, 1.5, 2)] + ["best_s%+d" % d for d in (-4, -2, 2, 4)])


def ramp(x, kt, start):
    return kt * np.clip((x - start) / WIDTH, 0.0, 1.0)


def floor(w, Pg):
    return np.where(Pg >= GALE_P, np.maximum(w, GALE_KT), w)


def best(base, d, scale=1.0, shift=0.0, hf=True):
    strong = np.nan_to_num(np.fmax(d["gfs"], d["ifs"]), nan=-1.0)
    add = sum(ramp(strong, kt * scale, st + shift) for kt, st in RAMPS)
    if hf:
        add = add + np.where(d["p48nb"] >= HF_P, ramp(strong, HF[0] * scale, HF[1] + shift), 0.0)
    w = np.where(d["lift_on"], base + add, base)
    return floor(w, d["Pg"])


def products(d):
    b = {"blend": d["base05"] + d["boost"], "blend_nospread": d["base05"], "blend_a0": d["base0"] + d["boost"],
         "blend_a1": d["base1"] + d["boost"]}
    p = {"gfs": d["gfs"], "ifs": d["ifs"], "aifs": d["aifs"], **b}
    p["floor"] = floor(b["blend"], d["Pg"])
    p["CL"] = F.corelift(b["blend"], d["P"], d["Pg"])
    p["best"] = best(b["blend"], d)
    p["best_nohf"] = best(b["blend"], d, hf=False)
    p["best_nospread"] = best(b["blend_nospread"], d)
    p["best_a0"] = best(b["blend_a0"], d)
    p["best_a1"] = best(b["blend_a1"], d)
    for s in (0.5, 1.5, 2):
        p["best_x%g" % s] = best(b["blend"], d, scale=s)
    for s in (-4, -2, 2, 4):
        p["best_s%+d" % s] = best(b["blend"], d, shift=s)
    return p


def load(path, basin):
    z = np.load(path)
    d = {k: z[k] for k in z.files}
    for k in d:
        if d[k].dtype == np.float16:
            d[k] = d[k].astype(np.float32)
    if "P" not in d:
        return None
    lats, _ = basins.grid(basin)
    d["lift_on"] = d["ocean"] & (np.abs(lats)[:, None] >= MIN_LAT)
    return d


def job(args):
    basin, cyc, step, path = args
    d = load(path, basin)
    if d is None:
        return None
    seen = d["seen"] & d["ocean"] & np.isfinite(d["spd"])
    ob = np.where(seen, d["spd"], np.nan)
    tiles = F.Tiles(basin, seen)
    wk = "%d-%02d" % cyc.isocalendar()[:2]
    meta = dict(basin=basin, cycle=cyc.isoformat(), step=step, week=wk)
    erows, trows, hists = [], [], {}
    obi = {t: seen & (np.nan_to_num(ob, nan=-1) >= t) for t in F.THRS}
    for name, fc in products(d).items():
        fc = np.asarray(fc, np.float32)
        for cut in ("truth", "fc"):
            r = score.band_error(fc, ob, mask=seen, by=cut)
            for i, bn in enumerate(BAND_NAMES):
                erows.append(dict(meta, product=name, cut=cut, band=bn, n=int(r["n"][i]), sum_err=r["sum_err"][i],
                                  sum_abs=r["sum_abs"][i], sum_sq=r["sum_sq"][i]))
        r = score.band_error(fc, ob, mask=seen, edges=())
        erows.append(dict(meta, product=name, cut="all", band="all", n=int(r["n"][0]), sum_err=r["sum_err"][0],
                          sum_abs=r["sum_abs"][0], sum_sq=r["sum_sq"][0]))
        tr = dict(meta, product=name)
        fcn = np.nan_to_num(fc, nan=-1)
        for t in F.THRS:
            nt, h, m, fa = tiles.counts(fc, ob, t)
            f = seen & (fcn >= t)
            tr.update({"nt%d" % t: nt, "h%d" % t: h, "m%d" % t: m, "fa%d" % t: fa, "fc%d" % t: int(f.sum()),
                       "ob%d" % t: int(obi[t].sum()), "cau%d" % t: int((f & obi[t]).sum())})
        trows.append(tr)
        bins = np.clip(fcn, 0, NBIN - 1).astype(int)
        hists[name] = np.stack([np.bincount(bins[m], minlength=NBIN) for m in (seen, obi[34], obi[48], obi[64])])
    return erows, trows, (basin, wk, hists)


def cases_for(basin, split):
    root = paths.cache("extra", "most-likely-wind", basin)
    out = []
    for p in sorted(root.glob("*.npz")):
        if p.name.endswith(".tmp.npz"):
            continue
        tg, st = p.stem.split("_f")
        cyc = cases.parse(tg)
        if cases.split(cyc) == split:
            out.append((basin, cyc, int(st), p))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", required=True, choices=("tune", "held_out"))
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    jobs = cases_for("natl", a.split) + cases_for("npac", a.split)
    print("%d cases, %d products" % (len(jobs), len(PRODUCTS)), flush=True)
    E, T, H, skipped, t0 = [], [], {}, 0, time.time()
    with mp.get_context("spawn").Pool(a.workers) as pool:
        for i, r in enumerate(pool.imap_unordered(job, jobs, chunksize=4), 1):
            if r is None:
                skipped += 1
                continue
            E += r[0]
            T += r[1]
            b, wk, hs = r[2]
            for k, v in hs.items():
                key = (b, wk, k)
                H[key] = H[key] + v if key in H else v
            if i % 500 == 0 or i == len(jobs):
                print("[%d/%d] %.0fs" % (i, len(jobs), time.time() - t0), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for nm, rows in (("err", E), ("tiles", T)):
        with gzip.open(OUT / ("%s_%s.csv.gz" % (nm, a.split)), "wt") as fh:
            pd.DataFrame(rows).to_csv(fh, index=False)
    keys = sorted(H)
    np.savez_compressed(OUT / ("hist_%s.npz" % a.split), keys=np.array(["|".join(k) for k in keys]),
                        hist=np.stack([H[k] for k in keys]))
    print("scored %d cases, skipped %d without core chances" % (len(jobs) - skipped, skipped), flush=True)


if __name__ == "__main__":
    main()
