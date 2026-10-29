"""Gale warning line with small pieces removed: does the tidier line still cover the gale water?

The live page gale warning area is the strongest of GFS, ECMWF and AIFS at 30 kt or more (max3 + 0 >= 30, the
same as the study's max3 + 4 >= 34). Drawn on the page it breaks into many small specks. This drops warned pieces
smaller than N cells (8-connected; 16 cells is about 1x1 deg at 0.25 deg) and optionally fills enclosed holes
smaller than N, then scores each version exactly as the warning study's fair_lines.py does (rk.score.warning_events
vs ASCAT, 60 nm reach counted, OPC high seas areas, open water). Tune and held-out weeks reported apart; nothing
is fitted, so held-out is the read.

Preset (2026-10-29, before running): ship the largest N whose held-out coverage of ASCAT gale cells drops by no
more than 1 point and whose events caught drop by no more than 1 point, both basins.

usage: python3 speck_lines.py OUT.csv ; env NPROC (default 3)
"""
import csv
import datetime as dt
import glob
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent / "2026-10-16-warning-forecast"
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(STUDY))

import numpy as np  # noqa: E402
from scipy import ndimage  # noqa: E402

import score_warnings as W  # noqa: E402
from rk import score, store, truth  # noqa: E402
from rk.basins import grid  # noqa: E402

SIZES = (0, 4, 8, 16, 32, 64)
RING = np.ones((2 * W.NBR + 1, 2 * W.NBR + 1), bool)
EIGHT = np.ones((3, 3), bool)


def tidy(w, n, fill):
    """Drop 8-connected warned pieces under n cells; with fill, also fill enclosed gaps under n cells."""
    if n <= 0:
        return w
    lab, k = ndimage.label(w, EIGHT)
    if k:
        sz = np.bincount(lab.ravel())
        keep = sz >= n
        keep[0] = False
        w = keep[lab]
    if fill:
        gap, k = ndimage.label(~w)  # 4-connected gaps, so a gap touching the edge is never "enclosed"
        if k:
            sz = np.bincount(gap.ravel())
            edge = np.unique(np.concatenate([gap[0], gap[-1], gap[:, 0], gap[:, -1]]))
            small = sz < n
            small[0] = False
            small[edge] = False
            w = w | small[gap]
    return w


def _case(args):
    basin, f = args
    run, step = os.path.basename(f)[:-4].split("_")
    run, step = dt.datetime.strptime(run, "%Y%m%d%H"), int(step)
    valid = run + dt.timedelta(hours=step)
    an = store.analysis(basin, valid)
    if an is None:
        return []
    sea = W.opc_area(basin) & an["mask"].astype(bool)
    seen, spd = truth.ascat_grid(basin, valid)
    if seen is None:
        return []
    seen &= sea
    lats, _ = grid(basin)
    with np.load(f) as z:
        s = [z["s10_" + m].astype(np.float32) for m in ("gfs", "ifs", "aifs")]
    raw = (np.maximum(np.maximum(s[0], s[1]), s[2]) >= 30) & sea
    cosl = 225 * np.cos(np.radians(lats))[:, None]
    base = dict(dom=basin, run=run.strftime("%Y%m%d%H"), step=step, valid=valid.strftime("%Y%m%d%H"))
    rows = []
    for n in SIZES:
        for fill in ((0,) if n == 0 else (0, 1)):
            w = tidy(raw, n, fill) & sea
            r = dict(base, n=n, fill=fill, area_nm2=float((cosl * w).sum()),
                     reach_nm2=float((cosl * (ndimage.binary_dilation(w, RING) & sea)).sum()) if w.any() else 0.0,
                     pieces=int(ndimage.label(w, EIGHT)[1]))
            r.update(score.warning_events(w, spd, seen, 34, mask=sea))
            rows.append(r)
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
