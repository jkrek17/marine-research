#!/usr/bin/env python3
"""Score the desk's Stability Height (30 m) practice beside Best Wind on the held-out cases (design.md).

  python3 score.py [--workers 3]        needs build_cases.py's cases; writes to rk.paths.data("extra", "desk-30m-vs-best-wind"):
                                        case_rows.csv.gz  one row per case x product (counts, error sums, lift columns)
                                        hist.npz          1 kt histograms per basin x product (common cases), for equal-area catch

Cells: open water ASCAT-seen cells (rk.truth.ascat_target, real 10 m), as the most-likely-wind study (score_cells.job).
Cases: held-out weeks, both basins, 00/12Z cycles, +24..+126 h; a case is "common" when every product below could be built
(page core chances, lagged-run GFE blend, GFS and ECMWF low-level fields, GFS 925 mb wind). Summaries use common cases.

Products (kt; GFS / ECMWF = the model's own 10 m wind):
  gfs, ifs         raw 10 m
  sh_gfs           Stability Height on GFS, strict mask: theta925 <= theta of 2 m air, GFS MSLP as surface pressure
  sh_ifs           Stability Height on ECMWF, loose mask: theta925 <= theta of the skin temperature, ECMWF MSLP
  sh_avg           DESK PRACTICE: mean of sh_gfs and sh_ifs
  avg10            mean of GFS and ECMWF 10 m (what sh_avg is before the stability step)
  det              GFE det blend #95 (GFS + ECMWF, lags 12/24 h, agreement weights + 0.3 x run spread)
  sh_blend_strict  6 Nov: the tool on the blend, strict mask (SHs of strong-core-lift)
  sh_blend_loose   6 Nov: the tool on the blend, loose mask (SHl)
  sh_entire        6 Nov: x1.179 on every ocean cell (SHe)
  blend            page blend (support-weighted GFS/ECMWF/AIFS with AIFS half weight + spread term)
  best             Best Wind as the page now draws it (ramps, HF core, gale floor at 80% gale-core chance)
  best60           Best Wind with the 60% gale floor of the 7 Nov study's live page
  gfe_best         Make_BestWind default (HF core off): det + ramps on the stronger of GFS/ECMWF
  gfe_best_hf      Make_BestWind with the HF core option on
The stability step is strong-core-lift/score.py desk_stability_wind (mask grown 2 cells, tapered); Best Wind and
Make_BestWind are most-likely-wind/score_cells.best and gfe_score.products, unchanged.
"""
import argparse
import gzip
import importlib.util
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parent / "2026-11-05-core-lift-bias"))
sys.path.insert(0, str(HERE.parent / "2026-11-07-most-likely-wind"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import fit_score as F  # noqa: E402
import gfe_score as GS  # noqa: E402
import score_cells as SC  # noqa: E402
from rk import cases, paths, score  # noqa: E402

OUT = paths.data("extra", "desk-30m-vs-best-wind")
THRS = F.THRS
OWN_EDGES = (20.0, 34.0, 48.0, 64.0)          # grid's own bands: <20, 20-33, 34-47, 48-63, 64+
NBIN = 120
_SLC = {}


def slc():
    """strong-core-lift/score.py (desk_stability_wind, lift definitions), loaded under its own name."""
    if "m" not in _SLC:
        p = HERE.parent / "2026-11-06-strong-core-lift"
        sys.path.insert(0, str(p))
        spec = importlib.util.spec_from_file_location("slc_score", p / "score.py")
        m = importlib.util.module_from_spec(spec)
        sys.modules["slc_score"] = m
        spec.loader.exec_module(m)
        _SLC["m"] = m
    return _SLC["m"]


PRODUCTS = ["gfs", "ifs", "sh_gfs", "sh_ifs", "sh_avg", "avg10", "det", "sh_blend_strict", "sh_blend_loose", "sh_entire",
            "blend", "best", "best60", "gfe_best", "gfe_best_hf"]
LIFT_BASE = {"sh_gfs": "gfs", "sh_ifs": "ifs", "sh_avg": "avg10", "sh_blend_strict": "det", "sh_blend_loose": "det",
             "sh_entire": "det"}
NEED = ("det", "gfs_msl", "ifs_msl", "g_t2", "g_t925", "i_skt", "i_t925", "s925", "sa")


def products(d):
    """-> ({name: grid}, common: bool). A product whose inputs are missing is left out."""
    S = slc()
    have = {k: (k in d) for k in NEED}
    p = {"gfs": d["gfs"], "ifs": d["ifs"], "avg10": 0.5 * (d["gfs"] + d["ifs"]), "blend": d["base05"] + d["boost"]}
    oc = d["ocean"]
    if have["g_t2"] and have["g_t925"] and have["gfs_msl"]:
        p["sh_gfs"] = S.desk_stability_wind(d["gfs"], d["g_t2"], d["gfs_msl"], d["g_t925"])
    if have["i_skt"] and have["i_t925"] and have["ifs_msl"]:
        p["sh_ifs"] = S.desk_stability_wind(d["ifs"], d["i_skt"], d["ifs_msl"], d["i_t925"])
    if "sh_gfs" in p and "sh_ifs" in p:
        p["sh_avg"] = 0.5 * (p["sh_gfs"] + p["sh_ifs"])
    if have["det"]:
        det = d["det"]
        p["det"] = det
        if have["g_t2"] and have["g_t925"] and have["gfs_msl"]:
            p["sh_blend_strict"] = S.desk_stability_wind(det, d["g_t2"], d["gfs_msl"], d["g_t925"])
        if have["i_skt"] and have["i_t925"] and have["ifs_msl"]:
            p["sh_blend_loose"] = S.desk_stability_wind(det, d["i_skt"], d["ifs_msl"], d["i_t925"])
        p["sh_entire"] = np.where(oc, det * np.float32(3.0 ** S.SH_EXPONENT), det).astype(np.float32)
        g = GS.products(d)                    # det, gfe_best, gfe_best_hf, ...
        p["gfe_best"], p["gfe_best_hf"] = g["gfe_best"], g["gfe_best_hf"]
    pre = SC.best(p["blend"], dict(d, Pg=np.zeros_like(d["Pg"])))   # Best Wind before the gale floor
    p["best"] = np.where(d["Pg"] >= 0.8, np.maximum(pre, 34.0), pre)   # the page now: floor at 80% gale-core chance
    p["best60"] = SC.best(p["blend"], d)       # the 7 Nov live page: floor at 60%
    common = all(k in p for k in PRODUCTS) and have["s925"] and have["sa"]
    return {k: np.asarray(v, np.float32) for k, v in p.items()}, common


def load(basin, cyc, step):
    """mlw case (page pieces, Best Wind inputs) + strong-core-lift case (desk inputs); None without the page core chances."""
    tagf = "%s_f%03d.npz" % (cases.tag(cyc), step)
    pm = paths.cache("extra", "most-likely-wind", basin) / tagf
    ps = paths.cache("extra", "strong-core-lift", basin) / tagf
    if not pm.exists():
        return None
    d = SC.load(pm, basin)
    if d is None:
        return None
    if ps.exists():
        z = np.load(ps)
        for k in NEED:
            if k in z.files:
                d[k] = z[k].astype(np.float32)
    return d


def job(args):
    basin, cyc, step = args
    d = load(basin, cyc, step)
    if d is None:
        return None
    seen = d["seen"] & d["ocean"] & np.isfinite(d["spd"])
    ob = np.where(seen, d["spd"], np.nan)
    tiles = F.Tiles(basin, seen)
    prods, common = products(d)
    hi = np.nan_to_num(np.max(np.stack([prods[k] for k in PRODUCTS if k in prods]), 0), nan=-1)
    dec = seen & ((hi >= 30) | (np.nan_to_num(ob, nan=-1) >= 30))
    obn = np.nan_to_num(ob, nan=-1)
    obi = {t: seen & (obn >= t) for t in THRS}
    spd = np.nan_to_num(d["spd"], nan=-1)
    wk = "%d-%02d" % cyc.isocalendar()[:2]
    rows, hists = [], {}
    for name in PRODUCTS:
        fc = prods.get(name)
        if fc is None:
            continue
        r = dict(basin=basin, cycle=cyc.isoformat(), step=step, week=wk, product=name, common=common)
        fcn = np.nan_to_num(fc, nan=-1)
        for t in THRS:
            nt, h, m, fa = tiles.counts(fc, ob, t)
            f = seen & (fcn >= t)
            r.update({"nt%d" % t: nt, "h%d" % t: h, "m%d" % t: m, "fa%d" % t: fa, "fc%d" % t: int(f.sum()),
                      "ob%d" % t: int(obi[t].sum()), "cau%d" % t: int((f & obi[t]).sum())})
        a = score.band_error(fc, ob, mask=seen, edges=())
        r.update(n_all=int(a["n"][0]), err_all=a["sum_err"][0], abs_all=a["sum_abs"][0])
        a = score.band_error(fc, ob, mask=dec, edges=())
        r.update(n_dec=int(a["n"][0]), err_dec=a["sum_err"][0], abs_dec=a["sum_abs"][0])
        a = score.band_error(fc, ob, mask=seen, edges=OWN_EDGES, by="fc")
        for i in range(len(OWN_EDGES) + 1):
            r["nb%d" % i], r["eb%d" % i] = int(a["n"][i]), a["sum_err"][i]
        if name in LIFT_BASE:                  # where the stability step lifts its base, and how ASCAT sees those cells
            base = prods[LIFT_BASE[name]]
            lift = d["ocean"] & (fc > base + 0.05)
            ls = lift & seen
            low = ls & (base < 34)
            r.update(n_lift=int(lift.sum()), n_lift_seen=int(ls.sum()), n_lift_a34=int((ls & (spd >= 34)).sum()),
                     n_lift_a48=int((ls & (spd >= 48)).sum()), sum_err_low=float((fc - spd)[low].sum()),
                     n_err_low=int(low.sum()))
        rows.append(r)
        if common:
            bins = np.clip(fcn, 0, NBIN - 1).astype(int)
            hists[name] = np.stack([np.bincount(bins[m], minlength=NBIN) for m in (seen, obi[34], obi[48], obi[64])])
    return rows, (basin, hists, common)


def case_list():
    out = []
    for basin in ("natl", "npac"):
        for p in sorted(paths.cache("extra", "most-likely-wind", basin).glob("*_f*.npz")):
            if p.name.endswith(".tmp.npz"):
                continue
            tg, st = p.stem.split("_f")
            c = cases.parse(tg)
            if cases.held_out(c):
                out.append((basin, c, int(st)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    jobs = case_list()
    print("%d cases" % len(jobs), flush=True)
    R, H, skipped, t0 = [], {}, 0, time.time()
    with mp.get_context("spawn").Pool(a.workers) as pool:
        for i, r in enumerate(pool.imap_unordered(job, jobs, chunksize=4), 1):
            if r is None:
                skipped += 1
                continue
            R += r[0]
            basin, hs, common = r[1]
            for k, v in hs.items():
                H[(basin, k)] = H[(basin, k)] + v if (basin, k) in H else v
            if i % 200 == 0 or i == len(jobs):
                print("[%d/%d] %.0fs" % (i, len(jobs), time.time() - t0), flush=True)
    df = pd.DataFrame(R)
    with gzip.open(OUT / "case_rows.csv.gz", "wt") as fh:
        df.to_csv(fh, index=False)
    keys = sorted(H)
    np.savez_compressed(OUT / "hist.npz", keys=np.array(["|".join(k) for k in keys]), hist=np.stack([H[k] for k in keys]))
    c = df[df["product"] == "best"]
    print("scored %d cases (%d without core chances skipped); common %d" % (len(jobs) - skipped, skipped, int(c["common"].sum())))


if __name__ == "__main__":
    main()
