"""The marine wind page's own hazard lines against the strongest-model lines, on the same cases and truth.

Page lines (awips-tools marine_wind/pipeline/storm.py, imported as is, with its core_model.json):
  gale   30%+ of GEFS+ENS members at 34+ kt (smoothed)
  storm  core likelihood 30%+
  HF     core likelihood 90%+ and 30%+ of members at 48+ kt
The cases carry 925 mb wind and temperature but no 850 mb fields, so the core model's 850 mb inputs are
missing (the trees send missing values down their default branch); the core is therefore approximate.
The core model was trained on this winter, so the page lines are scored partly in-sample (in their favour).

usage: python3 page_lines.py OUT.csv [natl|npac] ; env AWIPS_TOOLS (default: a clone beside this repo),
       NPROC (default 3), HF_KM (default 500)
"""
import csv
import datetime as dt
import glob
import os
import sys
import time
import warnings
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))
AT = Path(os.environ.get("AWIPS_TOOLS", HERE.parents[2] / "awips-tools"))
sys.path.insert(0, str(AT / "marine_wind" / "pipeline"))

import numpy as np  # noqa: E402

import score_warnings as W  # noqa: E402
import storm  # noqa: E402
from rk import score, store, truth  # noqa: E402
from rk.basins import grid  # noqa: E402

MODEL = storm.load_model(str(AT / "marine_wind" / "pipeline" / "core_model.json"))
MAX3 = {34: 1, 48: 7, 64: 12}


def _case(args):
    basin, f = args
    run, step = os.path.basename(f)[:-4].split("_")
    run, step = dt.datetime.strptime(run, "%Y%m%d%H"), int(step)
    valid = run + dt.timedelta(hours=step)
    an = store.analysis(basin, valid)
    dm = W.desk_masks(basin, valid, step)
    if an is None or dm is None:
        return []
    ocean = an["mask"].astype(bool)
    sea = W.opc_area(basin) & ocean
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
        n81 = int(z["nsrc"][0] + z["nsrc"][1])
        nan = np.full(pr["blend"].shape, np.nan, np.float32)
        low = {"u925": z["u925"].astype(np.float32), "v925": z["v925"].astype(np.float32),
               "t925": z["t925"].astype(np.float32), "t2": z["t2"].astype(np.float32),
               "skt": z["skt"].astype(np.float32), "u850": nan, "v850": nan, "t850": nan}
    members, aens = mem[:n81], mem[n81:]
    speeds = np.array([pr["gfs"], pr["ifs"], pr["aifs"]])
    base_w = W.support_base(speeds, members)
    boost = pr["blend"] - base_w
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        feats = storm.core_features(np.abs(lats), pr["blend"], boost, speeds, members, aens, low)
        core = storm.core_grid(feats, ocean, MODEL)
    _, hz = storm.products(pr["blend"], core, members)
    page = {34: (hz & 1) > 0, 48: (hz & 2) > 0, 64: (hz & 4) > 0}
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

    for L in (34, 48, 64):
        add("desk", 0, L, dm[L])
        add("page", 0, L, page[L])
        add("max3", MAX3[L], L, pr["max3"] + MAX3[L] >= L)
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
