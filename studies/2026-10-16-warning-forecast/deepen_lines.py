"""Lift the wind core where the low is deepening fast, more at longer lead (Jason, 2026-10-17 07:26Z).

Earlier: the storm-core study tested "low 24 h deepening" and 3 h pressure change as core clues (where the core
is, all leads pooled); neither added skill beyond the models and ensemble. Not tested: a speed lift by lead
where the fall is fast, on the premise that the models run low at longer leads. Preset (written before scoring):

  fall   24 h deepening of the nearest low in the GFS/ECMWF/AIFS mean MSLP: the lowest pressure within ~1000 km
         24 h earlier (the low can move that far) minus the lowest within ~500 km now (step 48: from the same run's
         +24 h; step 24: from the GFS/ECMWF analysis at the run time), scaled to 60N (x sin60 / sin lat). A fixed-
         point tendency was tried first and rejected: a deep low passing a point gives 50-65 hPa "falls".
  deep   fall >= T, T = 12, 18 or 24 hPa (24 = a bomb)
  storm  Core Lifted + d + k where deep (k = 3 or 6 kt), against Core Lifted + d; ASCAT truth
  HF     strongest model + d + k where deep, against strongest model + d; archive truth at 150 km
  win    at equal coverage (storm: >= 90% of ASCAT storm cells on tune weeks) or equal catch (HF: 150 km), the
         lifted line warns less area; checked once on the held-out weeks, and at 24 and 48 h separately.
Also writes one diagnostic row per ASCAT storm event and per HF fix: ASCAT or archive strength, Core Lifted and
strongest-model peak within ~60 nm, fall, lead, so the premise (models lower at longer lead when the fall is
fast) can be read directly.

usage: python3 deepen_lines.py OUT.csv DIAG.csv ; env NPROC (default 3)
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

TS = (12, 18, 24)
KS = (3, 6)
D48 = (0, 3, 6, 8, 9, 10, 12)
D64 = (8, 10, 12, 14, 16, 18)
FALL_NB, PREV_NB = 37, 73   # ~500 km and ~1000 km boxes on the 0.25 deg grid
RING = np.ones((2 * W.NBR + 1, 2 * W.NBR + 1), bool)


def fall_field(basin, run, step, f, lats):
    """24 h deepening of the nearest low (hPa, scaled to 60N): lowest MSLP within ~1000 km 24 h earlier minus the
    lowest within ~500 km now."""
    with np.load(f) as z:
        now = np.mean([z["msl_" + m].astype(np.float32) for m in ("gfs", "ifs", "aifs")], 0)
    if step == 48:
        p = Path(f).parent / ("%s_024.npz" % run.strftime("%Y%m%d%H"))
        if not p.exists():
            return None
        with np.load(p) as z:
            prev = np.mean([z["msl_" + m].astype(np.float32) for m in ("gfs", "ifs", "aifs")], 0)
    else:
        a = store.analysis(basin, run)
        if a is None:
            return None
        prev = a["msl"].astype(np.float32)
    s = np.sin(np.radians(60)) / np.sin(np.radians(np.clip(np.abs(lats), 20, 90)))[:, None]
    big = 1100.0
    prev_min = ndimage.minimum_filter(np.nan_to_num(prev, nan=big), size=PREV_NB)
    now_min = ndimage.minimum_filter(np.nan_to_num(now, nan=big), size=FALL_NB)
    return (prev_min - now_min) * s


def _case(args):
    basin, f = args
    run, step = os.path.basename(f)[:-4].split("_")
    run, step = dt.datetime.strptime(run, "%Y%m%d%H"), int(step)
    valid = run + dt.timedelta(hours=step)
    an = store.analysis(basin, valid)
    if an is None:
        return [], []
    lats, lons = grid(basin)
    fall = fall_field(basin, run, step, f, lats)
    if fall is None:
        return [], []
    sea = W.opc_area(basin) & an["mask"].astype(bool)
    seen, spd = truth.ascat_grid(basin, valid)
    if seen is None:
        seen, spd = np.zeros(sea.shape, bool), np.zeros(sea.shape, np.float32)
    seen &= sea
    hf = truth.hf_fixes(basin, valid)
    if hf is not None and len(hf):
        iy = np.clip(np.rint((lats[0] - hf["lat"].values) / 0.25).astype(int), 0, lats.size - 1)
        ix = np.clip(np.rint((hf["lon"].values - lons[0]) / 0.25).astype(int), 0, lons.size - 1)
        k = sea[iy, ix]
        hf, iy, ix = hf[k], iy[k], ix[k]
    else:
        hf, iy, ix = None, np.zeros(0, int), np.zeros(0, int)
    hla, hlo = ([], []) if hf is None else (hf["lat"].values, hf["lon"].values)
    with np.load(f) as z:
        s = {m: z["s10_" + m].astype(np.float32) for m in ("gfs", "ifs", "aifs")}
        cl = N.page_fields(z, step, lats, an["mask"].astype(bool))["corelift"]
    mx = np.maximum(np.maximum(s["gfs"], s["ifs"]), s["aifs"])
    cosl = 225 * np.cos(np.radians(lats))[:, None]
    base = dict(dom=basin, run=run.strftime("%Y%m%d%H"), step=step, valid=valid.strftime("%Y%m%d%H"))
    rows, diag = [], []

    def add(rule, setting, L, w):
        w = w & sea
        r = dict(base, rule=rule, setting=setting, L=L, area_nm2=float((cosl * w).sum()),
                 reach_nm2=float((cosl * (ndimage.binary_dilation(w, RING) & sea)).sum()) if w.any() else 0.0)
        if L == 64:
            for km in (150, 500):
                q = score.warning_points(w, basin, hla, hlo, km, mask=sea)
                r.update({"events": q["events"], "areas": q["areas"], "hits%d" % km: q["hits"], "false%d" % km: q["false"]})
        else:
            r.update(score.warning_events(w, spd, seen, L, mask=sea))
        rows.append(r)

    deep = {T: fall >= T for T in TS}
    for d in D48:
        add("corelift", "%d" % d, 48, cl + d >= 48)
        for T in TS:
            for k in KS:
                add("cl_deep", "%d/%d/%d" % (d, T, k), 48, cl + d + k * deep[T] >= 48)
    for d in D64:
        add("max3", "%d" % d, 64, mx + d >= 64)
        for T in TS:
            for k in KS:
                add("max3_deep", "%d/%d/%d" % (d, T, k), 64, mx + d + k * deep[T] >= 64)

    # diagnostics: each ASCAT storm event and each HF fix
    near = lambda a: ndimage.maximum_filter(a, size=2 * W.NBR + 1)
    cl_nb, mx_nb = near(np.where(sea, cl, 0)), near(np.where(sea, mx, 0))
    lab, n = ndimage.label(seen & (spd >= 48), structure=np.ones((3, 3)))
    for i in range(1, n + 1):
        m = lab == i
        if m.sum() < 2:
            continue
        diag.append(dict(base, kind="storm", truth_kt=float(spd[m].max()), corelift_kt=float(cl_nb[m].max()),
                         max3_kt=float(mx_nb[m].max()), fall=float(fall[m].max()), cells=int(m.sum())))
    for j in range(len(iy)):
        diag.append(dict(base, kind="hf", truth_kt=np.nan, corelift_kt=float(cl_nb[iy[j], ix[j]]),
                         max3_kt=float(mx_nb[iy[j], ix[j]]), fall=float(fall[iy[j], ix[j]]), cells=0))
    return rows, diag


def run_case(args):
    for i in range(4):
        try:
            return _case(args)
        except OSError:
            if i == 3:
                raise
            time.sleep(10 * (i + 1))


def _write(path, rows):
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    from multiprocessing import get_context
    out, dout = sys.argv[1], sys.argv[2]
    jobs = [(b, f) for b in ("natl", "npac") for f in sorted(glob.glob(str(W.EXTRA / "cases" / b / "*.npz")))]
    print(len(jobs), "cases", flush=True)
    rows, diag = [], []
    with get_context("spawn").Pool(int(os.environ.get("NPROC", "3"))) as p:
        for i, (r, g) in enumerate(p.imap_unordered(run_case, jobs, chunksize=2)):
            rows += r
            diag += g
            if i % 100 == 0:
                print(i, flush=True)
    _write(out, rows)
    _write(dout, diag)
    print("wrote", len(rows), len(diag), flush=True)
