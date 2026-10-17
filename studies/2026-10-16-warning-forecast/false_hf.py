"""What are the HF areas with no archived HF low within 150 km? (Jason, 2026-10-17 08:09Z: tip jets?)

One row per warned HF area (>= 3 cells) for the gated line (strongest model + 20 kt >= 64 where >= 1% of
members reach 64 kt within NBR cells, hf_gated.py 20/0/0.01) and the HSF text: where it is, its peak, what
ASCAT saw in it (+-90 min), the distance to the nearest archived HF fix and to the nearest low in the 3-model
mean MSLP (lowest value within ~1000 km of the area's peak, and its pressure), and whether it touches the
Cape Farewell or Denmark Strait tip-jet water.

usage: python3 false_hf.py OUT.csv ; env NPROC (default 3)
"""
import csv
import datetime as dt
import glob
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402
from scipy import ndimage  # noqa: E402

import ndfd_lines as N  # noqa: E402
import score_warnings as W  # noqa: E402
from rk import store, truth  # noqa: E402
from rk.basins import grid  # noqa: E402
from rk.score import km  # noqa: E402

# tip-jet water (lat0, lat1, lon0, lon1 in 0..360): Cape Farewell, Denmark Strait
JETS = {"farewell": (57, 62, 312, 322), "denmark": (63, 67, 325, 338)}
LOW_NB = 73   # ~1000 km box on the 0.25 deg grid


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
    sea = W.opc_area(basin) & an["mask"].astype(bool)
    lats, lons = grid(basin)
    la2, lo2 = np.meshgrid(lats, lons, indexing="ij")
    hf = truth.hf_fixes(basin, valid)
    hla, hlo = (np.zeros(0), np.zeros(0)) if hf is None or not len(hf) else (hf["lat"].values, hf["lon"].values)
    seen, spd = truth.ascat_grid(basin, valid)
    if seen is None:
        seen, spd = np.zeros(sea.shape, bool), np.zeros(sea.shape, np.float32)
    with np.load(f) as z:
        pr, mem = W.products(z, step)
        msl = np.mean([z["msl_" + m].astype(np.float32) for m in ("gfs", "ifs", "aifs")], 0)
    nb = np.array([ndimage.maximum_filter(x, size=2 * W.NBR + 1) for x in (mem >= 64)]).mean(0)
    lines = {"gated": (pr["max3"] + 20 >= 64) & (nb >= 0.01) & sea, "desk": tm[64] & sea}
    msl = np.nan_to_num(msl, nan=1100.0)
    base = dict(dom=basin, run=run.strftime("%Y%m%d%H"), step=step, valid=valid.strftime("%Y%m%d%H"),
                complete=complete, n_fixes=len(hla))
    rows = []
    for rule, w in lines.items():
        lab, n = ndimage.label(w, structure=np.ones((3, 3)))
        for i in range(1, n + 1):
            m = lab == i
            if m.sum() < 3:
                continue
            pk = np.unravel_index(np.argmax(np.where(m, pr["max3"], -1)), m.shape)
            plat, plon = float(lats[pk[0]]), float(lons[pk[1]])
            d_fix = min((km(la2[m], lo2[m], a, o).min() for a, o in zip(hla, hlo)), default=np.inf)
            h = LOW_NB // 2
            y0, y1, x0, x1 = max(pk[0] - h, 0), pk[0] + h + 1, max(pk[1] - h, 0), pk[1] + h + 1
            box = msl[y0:y1, x0:x1]
            ly, lx = np.unravel_index(np.argmin(box), box.shape)
            llat, llon = float(lats[y0 + ly]), float(lons[x0 + lx])
            jet = [k for k, (a0, a1, o0, o1) in JETS.items()
                   if basin == "natl" and (m & (la2 >= a0) & (la2 <= a1) & (lo2 >= o0) & (lo2 <= o1)).any()]
            sm = m & seen
            rows.append(dict(base, rule=rule, cells=int(m.sum()), lat=plat, lon=plon,
                             max3_kt=float(pr["max3"][pk]), share64=float(nb[m].max()),
                             d_fix_km=float(d_fix), false150=int(d_fix > 150),
                             low_hpa=float(box[ly, lx]), d_low_km=float(km(plat, plon, llat, llon)),
                             jet="|".join(jet), ascat_cells=int(sm.sum()),
                             ascat_max=float(spd[sm].max()) if sm.any() else np.nan,
                             ascat64=int((sm & (spd >= 64)).sum()), ascat48=int((sm & (spd >= 48)).sum())))
    return rows


def run_case(args):
    for i in range(4):
        try:
            return _case(args)
        except OSError:
            if i == 3:
                raise
            time.sleep(10 * (i + 1))


if __name__ == "__main__":
    from multiprocessing import get_context
    out = sys.argv[1]
    jobs = [(b, f) for b in ("natl", "npac") for f in sorted(glob.glob(str(W.EXTRA / "cases" / b / "*.npz")))]
    print(len(jobs), "cases", flush=True)
    rows = []
    with get_context("spawn").Pool(int(os.environ.get("NPROC", "3"))) as p:
        for i, r in enumerate(p.imap_unordered(run_case, jobs, chunksize=2)):
            rows += r
            if i % 100 == 0:
                print(i, flush=True)
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print("wrote", len(rows), flush=True)
