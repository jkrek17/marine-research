"""HF line from the strongest model, kept only where the ensemble gives some chance of HF (Jason, 2026-10-17 07:25Z).

line = max3 + d >= 64  AND  share of the 132 members >= 64 - dT within NBR cells (about 1 deg) >= q
Plain max3 + d, the HSF text and Core Lifted-style member share alone (share >= q, no model line) for reference.
Scored against the HF-low archive at 150, 300 and 500 km on every case-hour with a text, with warned area and the
area with the ~60 nm ring (fair_lines.py). gated_lines.py ran the same gate at 500 km only on desk-complete hours.

usage: python3 hf_gated.py OUT.csv ; env NPROC (default 3)
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
from rk import score, store, truth  # noqa: E402
from rk.basins import grid  # noqa: E402

D = (8, 10, 12, 14, 16, 18, 20)
DT = (0, 4, 8, 12, 16)
QS = (0.01, 0.02, 0.05, 0.1, 0.2)
RING = np.ones((2 * W.NBR + 1, 2 * W.NBR + 1), bool)


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
    base = dict(dom=basin, run=run.strftime("%Y%m%d%H"), step=step, valid=valid.strftime("%Y%m%d%H"),
                complete=complete, L=64)
    rows = []

    def add(rule, setting, w):
        w = w & sea
        r = dict(base, rule=rule, setting=setting, area_nm2=float((cosl * w).sum()),
                 reach_nm2=float((cosl * (ndimage.binary_dilation(w, RING) & sea)).sum()) if w.any() else 0.0)
        for k in (150, 300, 500):
            q = score.warning_points(w, basin, hla, hlo, k, mask=sea)
            r.update({"events": q["events"], "areas": q["areas"], "hits%d" % k: q["hits"], "false%d" % k: q["false"]})
        rows.append(r)

    add("desk", "0", tm[64])
    nb = {dT: np.array([ndimage.maximum_filter(x, size=2 * W.NBR + 1) for x in (mem >= 64 - dT)]).mean(0)
          for dT in DT}
    for dT in DT:
        for q in QS:
            add("share", "%d/%.2f" % (dT, q), nb[dT] >= q)
    for d in D:
        line = pr["max3"] + d >= 64
        add("max3", "%d" % d, line)
        for dT in DT:
            for q in QS:
                add("gated", "%d/%d/%.2f" % (d, dT, q), line & (nb[dT] >= q))
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
