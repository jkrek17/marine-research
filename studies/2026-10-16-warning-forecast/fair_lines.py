"""Strongest-model lines re-picked on fair scores (adversarial audit 2026-10-17, items 2, 3 and 7).

Scores each offset with the slack ring counted: events caught with a warned cell on the event, the share of
observed-at-level ASCAT cells inside the line, warned area and area including the 60 nm ring, and false cells
with no slack. HF at 150, 300 and 500 km. Two model sets:
  max3   GFS, ECMWF and AIFS from the same run (what the study used)
  avail  what the 0430/1630 UTC desk had: the same GFS run, ECMWF and AIFS from the run a day older
         (+48 h fields for a +24 h valid time; a day older than the 12 h-old runs the desk really had,
         so a conservative bound). +24 h only.

usage: python3 fair_lines.py OUT.csv ; env NPROC (default 3)
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

OFFSETS = {34: range(-2, 13), 48: range(0, 15), 64: range(6, 21, 2)}
RING = np.ones((2 * W.NBR + 1, 2 * W.NBR + 1), bool)


def _case(args):
    basin, f = args
    run, step = os.path.basename(f)[:-4].split("_")
    run, step = dt.datetime.strptime(run, "%Y%m%d%H"), int(step)
    valid = run + dt.timedelta(hours=step)
    an = store.analysis(basin, valid)
    dm = W.desk_masks(basin, valid, step)
    if an is None or dm is None:
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
    hla = [] if hf is None else hf["lat"].values
    hlo = [] if hf is None else hf["lon"].values
    with np.load(f) as z:
        s = {m: z["s10_" + m].astype(np.float32) for m in ("gfs", "ifs", "aifs")}
    sets = {"max3": np.maximum(np.maximum(s["gfs"], s["ifs"]), s["aifs"])}
    prev = Path(f).parent / ("%s_048.npz" % (run - dt.timedelta(hours=24)).strftime("%Y%m%d%H"))
    if step == 24 and prev.exists():
        with np.load(prev) as z:
            sets["avail"] = np.maximum(np.maximum(s["gfs"], z["s10_ifs"].astype(np.float32)), z["s10_aifs"].astype(np.float32))
    cosl = 225 * np.cos(np.radians(lats))[:, None]
    base = dict(dom=basin, run=run.strftime("%Y%m%d%H"), step=step, valid=valid.strftime("%Y%m%d%H"), deskok=1,
                has_avail=int("avail" in sets))
    rows = []

    def add(rule, setting, L, w):
        w = w & sea
        r = dict(base, rule=rule, setting=setting, L=L, area_nm2=float((cosl * w).sum()),
                 reach_nm2=float((cosl * (ndimage.binary_dilation(w, RING) & sea)).sum()) if w.any() else 0.0)
        if L == 64:
            for k in (150, 300, 500):
                q = score.warning_points(w, basin, hla, hlo, k, mask=sea)
                r.update({"events": q["events"], "areas": q["areas"], "hits%d" % k: q["hits"], "false%d" % k: q["false"]})
        else:
            r.update(score.warning_events(w, spd, seen, L, mask=sea))
        rows.append(r)

    for L, offs in OFFSETS.items():
        add("desk", 0, L, dm[L])
        for name, field in sets.items():
            for d in offs:
                add(name, d, L, field + d >= L)
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
