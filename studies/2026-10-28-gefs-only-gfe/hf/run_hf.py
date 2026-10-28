"""HF warning line gated on GEFS only (design card 2026-10-28, section 3), scored per case.

Reuses the warning study's code: the case files, products(), text_masks(), opc_area(), the 150/300/500 km HF-low
scoring (rk.score.warning_points) and the area / reach (+~60 nm ring) billing of hf_gated.py. Same case set as
hf_gated.py: 00/12 UTC runs, +24 and +48 h, every hour that has an issued HSF text, both basins.

rows written per case (rule, res, k):
  live_pooled      strongest of GFS/IFS/AIFS + 20 kt at 64+, kept where >= 1% of the pooled 132 members reach 64
                   within NBR cells (hf_gated.py "gated 20/0/0.01"); the reproduction check and the reference
  live_noaifs      the same with GFS/IFS only (separates the AIFS loss from the ensemble loss)
  gfe_ungated      strongest of GFS/IFS + 20 kt, no gate
  gfe_k<k>         GFS/IFS + 20 kt, kept where >= k GEFS members reach 64 within NBR cells, from the stored GEFS
                   p64 share (rk.store.load_ens): max over the 9x9 neighbourhood of p64 >= (k - 0.5)/n.
                   res 0.25 = as stored; res 0.5 = p64 through rk.features.half_deg first.
  gfe_k1gt0        res 0.5 only: the card's literal "p64_nb > 0"

usage: python3 run_hf.py [OUT.csv] ; env NPROC (default 3)
"""
import csv
import datetime as dt
import glob
import os
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDY = HERE.parents[1] / "2026-10-16-warning-forecast"
sys.path.insert(0, str(HERE.parents[2]))
sys.path.insert(0, str(STUDY))

import numpy as np  # noqa: E402
from scipy import ndimage  # noqa: E402

import ndfd_lines as N  # noqa: E402
import score_warnings as W  # noqa: E402
from rk import cases, features, paths, score, store, truth  # noqa: E402
from rk.basins import grid  # noqa: E402

CACHE = paths.data("extra", "gefs-only-gfe", "hf", "x").parent
D = 20
QPOOL = 0.01
KS = (1, 2, 3)
RING = np.ones((2 * W.NBR + 1, 2 * W.NBR + 1), bool)
SIZE = 2 * W.NBR + 1


def _case(args):
    basin, f = args
    run, step = os.path.basename(f)[:-4].split("_")
    run, step = dt.datetime.strptime(run, "%Y%m%d%H"), int(step)
    valid = run + dt.timedelta(hours=step)
    an = store.analysis(basin, valid)
    if an is None:
        return []
    tm, complete = N.text_masks(basin, valid, step)
    if tm is None:
        return []
    gf, ifs = store.load_det(basin, run, "gfs", step), store.load_det(basin, run, "ifs", step)
    ge = store.load_ens(basin, run, "gefs", step)
    if gf is None or ifs is None or ge is None:
        return [dict(dom=basin, run=run.strftime("%Y%m%d%H"), step=step, rule="MISSING", res="-", k=0)]
    sea = W.opc_area(basin) & an["mask"].astype(bool)
    hf = truth.hf_fixes(basin, valid)
    lats, lons = grid(basin)
    if hf is not None and len(hf):
        iy = np.clip(np.rint((lats[0] - hf["lat"].values) / 0.25).astype(int), 0, lats.size - 1)
        ix = np.clip(np.rint((hf["lon"].values - lons[0]) / 0.25).astype(int), 0, lons.size - 1)
        hf = hf[sea[iy, ix]]
    hla, hlo = ([], []) if hf is None else (hf["lat"].values, hf["lon"].values)
    with np.load(f) as z:
        pr, mem = W.products(z, step)
    cosl = 225 * np.cos(np.radians(lats))[:, None]
    base = dict(dom=basin, run=run.strftime("%Y%m%d%H"), step=step, complete=complete,
                split=cases.split(run))
    rows = []

    def add(rule, res, k, w):
        w = w & sea
        r = dict(base, rule=rule, res=res, k=k, area_nm2=float((cosl * w).sum()),
                 reach_nm2=float((cosl * (ndimage.binary_dilation(w, RING) & sea)).sum()) if w.any() else 0.0)
        for km in (150, 300, 500):
            q = score.warning_points(w, basin, hla, hlo, km, mask=sea)
            r.update({"events": q["events"], "areas": q["areas"], "hits%d" % km: q["hits"],
                      "false%d" % km: q["false"]})
        rows.append(r)

    nbpool = np.array([ndimage.maximum_filter(x, size=SIZE) for x in (mem >= 64)]).mean(0)
    add("live_pooled", "-", 0, (pr["max3"] + D >= 64) & (nbpool >= QPOOL))
    two = np.maximum(gf["speed"], ifs["speed"])
    add("live_noaifs", "-", 0, (two + D >= 64) & (nbpool >= QPOOL))
    line = two + D >= 64
    add("gfe_ungated", "-", 0, line)
    n = float(ge["n"])
    for res, p in (("0.25", ge["p64"]), ("0.5", features.half_deg(ge["p64"]))):
        nb = ndimage.maximum_filter(p, size=SIZE)
        for k in KS:
            add("gfe_k%d" % k, res, k, line & (nb >= (k - 0.5) / n))
        if res == "0.5":
            add("gfe_k1gt0", res, 1, line & (nb > 0))
    return rows


def run_case(args):
    """The disk is shared and small: a cycle pulled only for this case is removed again afterwards."""
    basin, fs = args
    run = dt.datetime.strptime(os.path.basename(fs[0])[:10], "%Y%m%d%H")
    d = store._cache_dir(basin, run)
    fresh = not d.exists()
    try:
        return [r for f in fs for r in _run_case((basin, f))]
    finally:
        if fresh and d.exists():
            shutil.rmtree(d, ignore_errors=True)


def _run_case(args):
    for i in range(4):
        try:
            return _case(args)
        except OSError:
            if i == 3:
                raise
            time.sleep(10 * (i + 1))


if __name__ == "__main__":
    from multiprocessing import get_context
    out = sys.argv[1] if len(sys.argv) > 1 else str(CACHE / "rows_hf.csv")
    jobs = []
    for b in ("natl", "npac"):
        by = {}
        for f in sorted(glob.glob(str(W.EXTRA / "cases" / b / "*.npz"))):
            by.setdefault(os.path.basename(f)[:10], []).append(f)
        jobs += [(b, v) for v in by.values()]
    print(len(jobs), "cases", flush=True)
    rows = []
    with get_context("spawn").Pool(min(int(os.environ.get("NPROC", "3")), 3)) as p:
        for i, r in enumerate(p.imap_unordered(run_case, jobs, chunksize=1)):
            rows += r
            if i % 100 == 0:
                print(i, flush=True)
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print("wrote", len(rows), "rows", sum(r["rule"] == "MISSING" for r in rows), "missing", flush=True)
