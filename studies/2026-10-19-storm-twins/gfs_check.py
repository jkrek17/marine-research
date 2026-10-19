"""Do Storm Twins found from a GFS forecast patch give an honest chance of hurricane force? (design.md, "Win means")

For each of hf-low's 18,167 matched GFS lead 24 h fixes (gfs/results/gfs_fixes_lead24.csv.gz, 2021-22..2025-26):
the GFS f024 patch (HGT 500, PRMSL, UGRD/VGRD 250 from noaa-gfs-bdp-pds, byte ranges) -> frozen 15 components ->
the 30 nearest library fixes from other seasons -> share that reached hurricane force (ERA5 proxy gust class 3).
Scored against the fix's own ERA5 proxy class over hours 24-48 (column y), against the basin-month climatology in
hf-low gfs_outlook/results/outlook_models_full.json (what score_gfs.py uses).

  HF_RESEARCH=<hf-low research checkout> python3 gfs_check.py pull [NPROC]   -> RK_DATA/lab/twins_gfs/<cycle>.npz
  HF_RESEARCH=... python3 gfs_check.py score                               -> results/gfs_check.csv, printed table
"""
import datetime as dt
import glob
import json
import os
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from rk import paths, score, twins  # noqa: E402
from nwp import grib, http, index, sources  # noqa: E402

HF = Path(os.environ["HF_RESEARCH"]) / "research" / "era5" / "storm_patch_analogs"
OUT = paths.data("lab", "twins_gfs", "x").parent
RECS = (("HGT:500 mb", "z"), ("PRMSL:mean sea level", "m"), ("UGRD:250 mb", "u"), ("VGRD:250 mb", "v"))
_CLIM = _PCA = None


def _init():
    global _CLIM, _PCA
    if _CLIM is None:
        z = np.load(paths.data("lab", "twins_clim0012.npz"))
        _CLIM = {k: z[k] for k in z.files}
        _PCA = twins.Frozen(HF / "gfs" / "results" / "frozen_pca_full.npz")


def gfs_fields(cycle, step):
    """GFS 0.25 degree f{step} -> {z500 m, msl hPa, u250, v250} on the 1.5 degree grid, and bytes read; None if absent."""
    url = sources.gfs(cycle[:8], cycle[8:], step)
    ix = index.ncep_index(url)
    if ix is None:
        return None, 0
    f, nb = {}, 0
    for key, tag in RECS:
        if key not in ix:
            return None, nb
        r = http.get(url, ix[key])
        if r is None:
            return None, nb
        nb += len(r.content)
        f[tag] = twins.coarsen(grib.decode(r.content))
    return {"z500": f["z"], "msl": f["m"] / 100.0, "u250": f["u"], "v250": f["v"]}, nb


def job(args):
    cycle, rows = args
    p = OUT / ("%s.npz" % cycle)
    if p.exists():
        return cycle, 0
    _init()
    f, nb = gfs_fields(cycle, 24)
    if f is None:
        return cycle, -1
    valid = dt.datetime.strptime(cycle, "%Y%m%d%H") + dt.timedelta(hours=24)
    a = twins.anomalies(f["z500"], f["msl"], f["u250"], f["v250"], _CLIM, valid)
    X = np.stack([twins.patch(a, r.lat, r.lon) for r in rows.itertuples()])
    np.savez_compressed(str(p) + ".tmp.npz", track=rows.track.values, pcs=_PCA.pcs(X).astype(np.float32))
    os.replace(str(p) + ".tmp.npz", p)
    return cycle, nb


def fixes():
    s = pd.read_csv(HF / "gfs" / "results" / "gfs_fixes_lead24.csv.gz", dtype={"cycle": str})
    return s[s.ok].reset_index(drop=True)


def pull(nproc):
    s = fixes()
    jobs = [(c, g) for c, g in s.groupby("cycle")]
    tot, miss = 0, 0
    with Pool(nproc) as pool:
        for i, (c, nb) in enumerate(pool.imap_unordered(job, jobs)):
            tot += max(nb, 0)
            miss += nb < 0
            if i % 100 == 0:
                print(i + 1, "/", len(jobs), c, "%.2f GB" % (tot / 1e9), "missing", miss, flush=True)
    print("done", "%.2f GB" % (tot / 1e9), "missing cycles", miss)


def main_score():
    s = fixes()
    lib = dict(np.load(paths.data("lab", "twins_library.npz")))
    m = json.load(open(HF.parent / "gfs_outlook" / "results" / "outlook_models_full.json"))
    clim = {(r["basin"], r["month"]): r["probs_smoothed"][3] for r in m["climatology_gcls"]}
    rows = []
    for c, g in s.groupby("cycle"):
        p = OUT / ("%s.npz" % c)
        if not p.exists():
            continue
        z = np.load(p)
        for r, pcs in zip(g.itertuples(), z["pcs"]):
            t = twins.twins(lib, pcs, k=30, exclude_season=r.season)
            month = int(r.valid_time // 10000 % 100)
            rows.append((c, r.track, r.basin, r.season, month, int(r.y == 3), t["hf_share"],
                         clim[(r.basin, month)]))
    d = pd.DataFrame(rows, columns=["cycle", "track", "basin", "season", "month", "hf", "p_twins", "p_clim"])
    (HERE / "results").mkdir(exist_ok=True)
    d.to_csv(HERE / "results" / "gfs_check.csv.gz", index=False, float_format="%.4f")
    bs = lambda p: float(np.mean((d[p] - d.hf) ** 2))  # noqa: E731
    bss = 1 - bs("p_twins") / bs("p_clim")
    by = d.groupby("season").apply(lambda x: 1 - np.mean((x.p_twins - x.hf) ** 2) / np.mean((x.p_clim - x.hf) ** 2))
    r = score.reliability(d.p_twins, d.hf, bins=10)
    r = r[r.n > 0]
    w, x, f = r.n.values, r.mean_p.values, r.freq.values
    xm, fm = np.average(x, weights=w), np.average(f, weights=w)
    slope = np.sum(w * (x - xm) * (f - fm)) / np.sum(w * (x - xm) ** 2)
    print("fixes", len(d), "cycles", d.cycle.nunique(), "HF outcomes", int(d.hf.sum()))
    print("Brier skill vs climatology %.3f; by season" % bss, by.round(3).to_dict())
    print("ROC area %.3f; reliability slope %.2f" % (score.auc(d.p_twins, d.hf), slope))
    print(r[["lo", "hi", "n", "mean_p", "freq"]].round(3).to_string(index=False))
    r.to_csv(HERE / "results" / "gfs_check_reliability.csv", index=False, float_format="%.4f")


if __name__ == "__main__":
    if sys.argv[1] == "pull":
        pull(int(sys.argv[2]) if len(sys.argv) > 2 else 8)
    else:
        main_score()
