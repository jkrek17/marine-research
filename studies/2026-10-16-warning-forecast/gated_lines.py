"""Core-lift idea for the storm and HF lines: the strongest-model line, kept only where the members back it.

line = max3 + d >= L  AND  share of the 132 members >= L - dT within NBR cells (about 1 deg) >= q
Also the plain max3 + d line for reference. Same truth and scoring as score_warnings.py.

usage: python3 gated_lines.py OUT.csv [natl|npac] ; env NPROC (default 3), HF_KM (default 500)
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

import score_warnings as W  # noqa: E402
from rk import score, store, truth  # noqa: E402
from rk.basins import grid  # noqa: E402

SETS = {48: dict(d=(5, 6, 7, 8, 9), dT=(0, 4, 8)), 64: dict(d=(10, 11, 12, 13, 14, 16), dT=(0, 4, 8, 12))}
QS = (0.02, 0.05, 0.1, 0.15, 0.2, 0.3)


def _case(args):
    basin, f = args
    run, step = os.path.basename(f)[:-4].split("_")
    run, step = dt.datetime.strptime(run, "%Y%m%d%H"), int(step)
    valid = run + dt.timedelta(hours=step)
    an = store.analysis(basin, valid)
    if an is None:
        return []
    dm = W.desk_masks(basin, valid, step)
    if dm is None:
        return []
    sea = W.opc_area(basin) & an["mask"].astype(bool)
    seen, spd = truth.ascat_grid(basin, valid)
    if seen is None:
        seen, spd = np.zeros(sea.shape, bool), np.zeros(sea.shape, np.float32)
    seen &= sea
    hf = truth.hf_fixes(basin, valid)
    lats, lons = grid(basin)
    if hf is not None and len(hf):
        iy = np.clip(np.rint((lats[0] - hf["lat"].values) / 0.25).astype(int), 0, lats.size - 1)
        ix = np.clip(np.rint((hf["lon"].values - lons[0]) / 0.25).astype(int), 0, lons.size - 1)
        hf = hf[W.opc_area(basin)[iy, ix]]
    with np.load(f) as z:
        pr, mem = W.products(z, step)
    base = dict(dom=basin, run=run.strftime("%Y%m%d%H"), step=step, valid=valid.strftime("%Y%m%d%H"), deskok=1)
    rows = []

    def add(rule, setting, L, w):
        if L == 64:
            r = score.warning_points(w, basin, [] if hf is None else hf["lat"].values,
                                     [] if hf is None else hf["lon"].values, W.HF_KM, mask=sea)
        else:
            r = score.warning_events(w, spd, seen, L, mask=sea)
        r["area_nm2"] = float((225 * np.cos(np.radians(lats))[:, None] * (w & sea)).sum())
        r.update(base, rule=rule, setting=setting, L=L)
        rows.append(r)

    for L, s in SETS.items():
        add("desk", 0, L, dm[L])
        nb = {dT: np.array([ndimage.maximum_filter(x, size=2 * W.NBR + 1) for x in (mem >= L - dT)]).mean(0)
              for dT in s["dT"]}
        for d in s["d"]:
            line = pr["max3"] + d >= L
            add("max3", d, L, line)
            for dT in s["dT"]:
                for q in QS:
                    add("gated", "%d/%d/%.2f" % (d, dT, q), L, line & (nb[dT] >= q))
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
    basins = sys.argv[2:] or ["natl", "npac"]
    jobs = [(b, f) for b in basins for f in sorted(glob.glob(str(W.EXTRA / "cases" / b / "*.npz")))]
    print(len(jobs), "cases", flush=True)
    rows = []
    with get_context("spawn").Pool(int(os.environ.get("NPROC", "3"))) as p:
        for i, r in enumerate(p.imap_unordered(run_case, jobs, chunksize=2)):
            rows += r
            if i % 100 == 0:
                print(i, flush=True)
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("wrote", len(rows), flush=True)
