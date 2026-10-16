"""Score warning rules against ASCAT (gale, storm) and the OPC hurricane-force archive (HF), case by case.

Truth (all from rk):
  gale, storm  rk.truth.ascat_grid: RSS ASCAT real 10 m wind, Metop-B/C intercalibrated, rain dropped, open
               water, +-90 min of the valid time; events and false areas by rk.score.warning_events
               (event = >= 2 connected cells at or above the level; hit = warned cell within 4 cells ~60 nm).
  HF           rk.truth.hf_fixes: archive fixes with Category HF at the valid time; rk.score.warning_points
               (hit = warned cell within HF_KM of the low centre).
Scored only inside the OPC high seas areas (Atlantic 31-67N west of 35W, cut at 75W by the basin box;
Pacific east of the Bering Strait-53N172E-50N180W-30N180W line) over open, ice-free water (analysis mask).

Forecasts: the full-member cases in DATA/extra/warning-experiment/cases (build_cases.py). Rules, each swept:
  model_<m>, max3, blend   wind + d >= L (blend = the live page blend: member-support weights + spread lean)
  max3nbr                  strongest of the three within NBR cells + d >= L
  lift<q>                  blend >= L, or blend + d >= L where the member chance of >= L is at least q
  pmem, pnbr               share of the 132 members >= L (at the cell / within NBR cells) >= p
  pmem-<dT>, pnbr-<dT>     the same with members >= L - dT
  pnbr2deg-<dT>            HF only: within 2 * NBR cells
  desk                     the issued High Seas Forecast areas (desk_masks.py); only hours parsed completely

usage: python3 score_warnings.py OUT.csv [natl|npac] ; env NPROC (default 2), HF_KM (default 500)
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
import shapely  # noqa: E402
from scipy import ndimage  # noqa: E402

from rk import score, store, truth  # noqa: E402
from rk.basins import grid  # noqa: E402
from rk.paths import data  # noqa: E402
from hsf_parse_wx import AREAS  # noqa: E402

# HSFEP1 area per its header ("E OF A LINE FROM THE BERING STRAIT TO 53N172E TO 50N180W TO 30N180W"),
# as in awips-tools marine_wind/hsf/areas.py; the parser's own Pacific outline starts at 160E and is too big
PAC = shapely.Polygon([(180, 30), (180, 50), (172, 53), (191.2, 65.7), (191.2, 67), (250, 67), (250, 30)])

EXTRA = data("extra", "warning-experiment", "x").parent
HF_KM = float(os.environ.get("HF_KM", "500"))
DELTAS = list(range(-4, 13))
PS = [0.02, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.7]
LIFT_Q = [0.1, 0.2, 0.3, 0.5]
NBR = 4
_AREA = {}


def opc_area(basin):
    if basin not in _AREA:
        lats, lons = grid(basin)
        lon2, lat2 = np.meshgrid(lons, lats)
        _AREA[basin] = (shapely.contains_xy(AREAS["atl"], lon2 - 360, lat2) if basin == "natl"
                        else shapely.contains_xy(PAC, lon2, lat2))
    return _AREA[basin]


def support_base(speeds, members, skt=5.0):
    """Live page blend weights: each model weighted by the share of members within ~5 kt of it."""
    w = np.array([np.exp(-0.5 * ((members - s[None]) / skt) ** 2).mean(0) for s in speeds]) + 1e-6
    return (w * speeds).sum(0) / w.sum(0)


def products(z, step):
    s = {m: z["s10_" + m].astype(np.float32) for m in ("gfs", "ifs", "aifs")}
    mem = z["mem"].astype(np.float32) / 2
    m81 = mem[:int(z["nsrc"][0] + z["nsrc"][1])]
    k = 0.15 if step <= 24 else 0.25
    out = dict(s)
    out["max3"] = np.maximum(np.maximum(s["gfs"], s["ifs"]), s["aifs"])
    out["blend"] = support_base(np.array([s["gfs"], s["ifs"], s["aifs"]]), m81) + np.minimum(k * m81.std(0), 5.0)
    return out, mem


def desk_masks(basin, valid, hour):
    iss = valid - dt.timedelta(hours=hour) + dt.timedelta(hours=4, minutes=30)
    p = EXTRA / "desk" / basin / ("%s_h%02d.npz" % (iss.strftime("%Y%m%d%H%M"), hour))
    if not p.exists():
        return None
    with np.load(p) as z:
        if not int(z["complete"]):
            return None
        return {L: z["w%d" % L].astype(bool) for L in (34, 48, 64)}


def run_case(args):
    """Score one case; the shared folder is a network mount, so a read error is retried a few times."""
    for i in range(4):
        try:
            return _run_case(args)
        except OSError:
            if i == 3:
                raise
            time.sleep(10 * (i + 1))


def _run_case(args):
    basin, f = args
    run, step = os.path.basename(f)[:-4].split("_")
    run, step = dt.datetime.strptime(run, "%Y%m%d%H"), int(step)
    valid = run + dt.timedelta(hours=step)
    an = store.analysis(basin, valid)
    if an is None:
        return []
    sea = opc_area(basin) & an["mask"].astype(bool)
    seen, spd = truth.ascat_grid(basin, valid)
    ok_ascat = seen is not None
    if not ok_ascat:
        seen, spd = np.zeros(sea.shape, bool), np.zeros(sea.shape, np.float32)
    seen &= sea
    hf = truth.hf_fixes(basin, valid)
    am = opc_area(basin)
    lats, lons = grid(basin)
    if hf is not None and len(hf):
        iy = np.clip(np.rint((lats[0] - hf["lat"].values) / 0.25).astype(int), 0, lats.size - 1)
        ix = np.clip(np.rint((hf["lon"].values - lons[0]) / 0.25).astype(int), 0, lons.size - 1)
        hf = hf[am[iy, ix]]
    with np.load(f) as z:
        pr, mem = products(z, step)
    dm = desk_masks(basin, valid, step)
    base = dict(dom=basin, run=run.strftime("%Y%m%d%H"), step=step, valid=valid.strftime("%Y%m%d%H"),
                ascat=int(ok_ascat), seen=int(seen.sum()), hf_n=0 if hf is None else len(hf), deskok=int(dm is not None))
    rows = []

    def add(rule, setting, L, w):
        if L == 64:
            r = score.warning_points(w, basin, [] if hf is None else hf["lat"].values,
                                     [] if hf is None else hf["lon"].values, HF_KM, mask=sea)
        else:
            r = score.warning_events(w, spd, seen, L, mask=sea)
        r["area_nm2"] = float((225 * np.cos(np.radians(lats))[:, None] * (w & sea)).sum())
        r.update(base, rule=rule, setting=setting, L=L)
        rows.append(r)

    for L in (34, 48, 64):
        nL = mem >= L
        P = nL.mean(0)
        for m in ("gfs", "ifs", "aifs", "max3", "blend"):
            for d in DELTAS:
                add(m if m in ("max3", "blend") else "model_" + m, d, L, pr[m] + d >= L)
        mx = ndimage.maximum_filter(pr["max3"], size=2 * NBR + 1)
        for d in DELTAS:
            add("max3nbr", d, L, mx + d >= L)
        for q in LIFT_Q:
            for d in (2, 3, 5, 8, 10, 12):
                add("lift%.1f" % q, d, L, (pr["blend"] >= L) | ((pr["blend"] + d >= L) & (P >= q)))
        for dT in (0, 4, 8, 12):
            mt = mem >= L - dT
            Pt = mt.mean(0)
            nb = np.array([ndimage.maximum_filter(x, size=2 * NBR + 1) for x in mt]).mean(0)
            sfx = "" if dT == 0 else "-%d" % dT
            for p in PS:
                add("pmem" + sfx, p, L, Pt >= p)
                add("pnbr" + sfx, p, L, nb >= p)
            if L == 64 and dT in (0, 8):
                nb2 = np.array([ndimage.maximum_filter(x, size=4 * NBR + 1) for x in mt]).mean(0)
                for p in PS:
                    add("pnbr2deg-%d" % dT, p, L, nb2 >= p)
        if dm is not None:
            add("desk", 0, L, dm[L])
    return rows


if __name__ == "__main__":
    from multiprocessing import get_context
    out = sys.argv[1]
    basins = sys.argv[2:] or ["natl", "npac"]
    jobs = [(b, f) for b in basins for f in sorted(glob.glob(str(EXTRA / "cases" / b / "*.npz")))]
    print(len(jobs), "cases", flush=True)
    rows = []
    with get_context("spawn").Pool(int(os.environ.get("NPROC", "2"))) as p:
        for i, r in enumerate(p.imap_unordered(run_case, jobs, chunksize=2)):
            rows += r
            if i % 50 == 0:
                print(i, flush=True)
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("wrote", len(rows), flush=True)
