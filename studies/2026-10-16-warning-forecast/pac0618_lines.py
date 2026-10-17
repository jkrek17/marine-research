"""Pacific warning lines at 06 and 18 UTC, when ASCAT passes over the HSFEP1 water (at 00/12 UTC it sees ~4%).

Valid times 06/18 UTC from the 00/12 UTC runs at +30 and +54 h, against the 1030/2230 UTC HSF text at +24 and
+48 h (the text written from those runs), the desk's NDFD grids and ASCAT. Model fields come from the kit store
(rk.store.load_det), which keeps ensemble statistics but not members, so the page blend and Core Lifted are not
built here. Open-water mask: the nearest 00/12 UTC analysis (rk.truth.mask_time). Rows as ndfd_lines.py (truth
ascat and archive only; there is no ECMWF analysis at 06/18 UTC).

usage: python3 pac0618_lines.py OUT.csv ; env NPROC (default 3)
"""
import csv
import datetime as dt
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402

import ndfd_lines as N  # noqa: E402
import score_warnings as W  # noqa: E402
from rk import cases, store, truth  # noqa: E402

BASIN = "npac"
STEPS = (30, 54)
RULES = ("desk", "ndfd", "mean2", "max3")


def _case(args):
    run, step = args
    valid = run + dt.timedelta(hours=step)
    tmask = truth.mask_time(BASIN, valid)
    if tmask is None:
        return []
    s = {m: store.load_det(BASIN, run, m, step) for m in ("gfs", "ifs", "aifs")}
    if any(v is None for v in s.values()):
        return []
    s = {m: v["speed"] for m, v in s.items()}
    sea = W.opc_area(BASIN) & store.analysis(BASIN, tmask)["mask"].astype(bool)
    seen, spd = truth.ascat_grid(BASIN, valid)
    if seen is None:
        return []
    fields = {"max3": np.maximum(np.maximum(s["gfs"], s["ifs"]), s["aifs"]), "mean2": 0.5 * (s["gfs"] + s["ifs"])}
    tm, complete = N.text_masks(BASIN, valid, step - 6)
    nd = N.ndfd_at(BASIN, run, valid)
    return N.score_rows(BASIN, run, step, valid, sea, fields, {"ascat": (seen, spd)}, tm, complete, nd, RULES)


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
    runs = []
    t = dt.datetime(2025, 11, 1)
    while t <= dt.datetime(2026, 3, 31, 12):
        runs.append(t)
        t += dt.timedelta(hours=12)
    jobs = [(r, st) for r in runs for st in STEPS if cases.winter(r + dt.timedelta(hours=st))]
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
