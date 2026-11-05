"""Desk value outside storm and HF: desk grid vs the page blend vs Core Lifted, by wind band and situation.

For each model cycle c (00/12Z), basin and valid time V (00/06/12/18Z, lead 6-120 h) the desk grid is the
NDFD snapshot rk.desk.issue_settled(c) (13Z / 01Z next day; the earlier Atlantic file is sometimes stale), the blend is the live page blend from the store
(rk.features.blend, AIFS half weight, member-spread lean) for the same cycle and lead, and Core Lifted is the
held-out replay in RK_DATA/extra/core-lift-retrain/corelift-heldout (held-out weeks only; storm lift only).
Every method is scored on the same cells: OPC High Seas Forecast area, open ice-free water, desk and blend present.

Truths: ASCAT (rk.truth.ascat, real 10 m, rain dropped; at least MIN_ASCAT matched cells in the basin) at every
valid hour, and the analysis (GFS+IFS mean) at 00/12Z.

Bands (kt): by the blend's value (what the forecaster starts from) and, as a check, by the truth.
Situations, from the analysis nearest V (rk.truth.mask_time): coastal = within COAST_KM of land or ice, open =
the rest; cold air = sea at least 2 K warmer than the 2 m air (t2 - skin <= -2), stable = air as warm as the sea
or warmer (t2 - skin >= 0); near low = within LOW_KM of an analysed low under 1000 hPa, away = the rest.

Rows (one per cycle, basin, valid, truth, band_by, band, situation, method): n, sum_abs, sum_err; and gale
rows (band "gale") with hits/fa/miss at 34 kt over the situation's cells.
Resumable: one part file per cycle under RK_DATA/extra/desk-value-bands/parts/.
Usage: score.py START END [--workers N] [--rebuild]
"""
import argparse
import datetime as dt
import os
import sys
import time
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.ndimage import distance_transform_edt

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from rk import basins, bomb, cases, desk, features, paths, store, truth  # noqa: E402

OUT = paths.data("extra", "desk-value-bands", "x").parent
PARTS = OUT / "parts"
CORE = paths.data("extra", "core-lift-retrain", "corelift-heldout", "x").parent
BASINS = ("natl", "npac")
BANDS = ((0, 20, "<20"), (20, 34, "20-33"), (34, 48, "34-47"), (48, 999, "48+"))
COAST_KM = 185.0   # 100 nm
LOW_KM = 500.0
LOW_BELOW = 1000.0
MIN_ASCAT = 500
GALE_LOWER = (26, 28, 30, 31, 32, 33)   # blend thresholds (kt) for the gale line drawn lower
DET_WEIGHTS = {"aifs": 0.5}   # live page blend (AIFS half weight)


@lru_cache(maxsize=32)
def _desk(issue):
    if not all(desk._path(b, issue).exists() for b in BASINS):
        return None
    return desk.load(issue)


def desk_at(issue, basin, valid):
    d = _desk(issue)
    if d is None or d.get(basin) is None or valid not in d[basin]["valid"]:
        return None
    return d[basin]["speed"][d[basin]["valid"].index(valid)].astype(np.float32)


def corelift(basin, c, lead):
    p = CORE / basin / f"{cases.tag(c)}_f{lead:03d}.npz"
    if not p.exists():
        return None
    with np.load(p) as z:
        return z["corelift"].astype(np.float32)


@lru_cache(maxsize=16)
def situations(basin, t):
    """{name: bool grid} from the analysis at time t (00/12Z)."""
    an = truth.analysis(basin, t)
    if an is None:
        return None
    lats, lons = basins.grid(basin)
    water = np.asarray(an["mask"], bool)
    # distance to land/ice in km, grid spacing at the box's mid latitude (good to ~15% over the box)
    dy = 0.25 * 111.2
    dx = dy * np.cos(np.deg2rad(np.mean(lats)))
    dist = distance_transform_edt(water, sampling=(dy, dx))
    out = {"all": np.ones_like(water), "coastal": dist <= COAST_KM, "open ocean": dist > COAST_KM}
    asea = truth.airsea(basin, t)
    if asea is not None:
        out["cold air"] = asea <= -2.0
        out["stable"] = asea >= 0.0
    lows = bomb.find_lows(np.asarray(an["msl"], float), lats, lons)
    lows = lows[lows[:, 2] < LOW_BELOW] if len(lows) else lows
    lat2, lon2 = np.meshgrid(lats, lons, indexing="ij")
    near = np.zeros(water.shape, bool)
    for la, lo, _ in lows:
        dlat = np.deg2rad(lat2 - la)
        dlon = np.deg2rad(lon2 - lo)
        a = np.sin(dlat / 2) ** 2 + np.cos(np.deg2rad(la)) * np.cos(np.deg2rad(lat2)) * np.sin(dlon / 2) ** 2
        near |= 6371.0 * 2 * np.arcsin(np.sqrt(np.minimum(a, 1))) <= LOW_KM
    out["near low"] = near
    out["away from lows"] = ~near
    return out


def ascat_grid(basin, V):
    a = truth.ascat(basin, V)
    if a is None or len(a["spd_kt"]) == 0:
        return None
    g, _ = truth.ascat_to_grid(basin, a["lat"], a["lon"], a["spd_kt"])
    return g.astype(np.float32)


def score_cycle(c):
    rows = []
    wk = c.isocalendar()
    base = dict(cycle=cases.tag(c), iso_week=f"{wk[0]}-W{wk[1]:02d}", held_out=bool(cases.held_out(c)))
    for basin in BASINS:
        I = desk.issue_settled(c)
        if _desk(I) is None or _desk(I).get(basin) is None:
            continue
        opc = basins.opc_mask(basin)
        for V in _desk(I)[basin]["valid"]:
            lead = int((V - c).total_seconds() // 3600)
            if lead < 6 or lead > 120 or V.hour % 6:
                continue
            dk = desk_at(I, basin, V)
            b = features.blend(basin, c, lead, det_weights=DET_WEIGHTS)
            if dk is None or b is None:
                continue
            bl = b["r10"]
            mt = truth.mask_time(basin, V)
            if mt is None:
                continue
            sit = situations(basin, mt)
            if sit is None:
                continue
            water = np.asarray(truth.analysis(basin, mt)["mask"], bool)
            common = opc & water & np.isfinite(dk) & np.isfinite(bl)
            grids = {"desk": dk, "blend": bl}
            cl = corelift(basin, c, lead)
            if cl is not None:
                grids["corelift"] = cl
                common &= np.isfinite(cl)
            truths = []
            if V.hour in (0, 12):
                an = truth.analysis(basin, V)
                if an is not None:
                    truths.append(("anl", an["mean_speed"].astype(np.float32)))
            asc = ascat_grid(basin, V)
            if asc is not None and int((common & np.isfinite(asc)).sum()) >= MIN_ASCAT:
                truths.append(("ascat", asc))
            key = dict(base, basin=basin, valid=cases.tag(V), lead=lead, day=(lead - 1) // 24 + 1,
                       hour=V.hour)
            for tname, ob in truths:
                ok = common & np.isfinite(ob)
                for sname, smask in sit.items():
                    sel = ok & smask
                    if not sel.any():
                        continue
                    o = ob[sel]
                    gs = {m: g[sel] for m, g in grids.items()}
                    # gale catch over the situation's cells
                    # (the blend also drawn lower, GALE_LOWER, for an equal-catch comparison with the desk)
                    for m, f in gs.items():
                        for thr in ((34,) + GALE_LOWER if m == "blend" else (34,)):
                            h = int(((f >= thr) & (o >= 34)).sum())
                            fa = int(((f >= thr) & (o < 34)).sum())
                            mi = int(((f < thr) & (o >= 34)).sum())
                            rows.append(dict(key, truth=tname, band_by="gale", band="gale", situation=sname,
                                             method=m if thr == 34 else f"{m}{thr}", n=int(len(o)), hits=h,
                                             fa=fa, miss=mi))
                    for band_by, ref in (("blend", gs["blend"]), ("truth", o)):
                        for lo, hi, bname in BANDS:
                            bs = (ref >= lo) & (ref < hi)
                            if not bs.any():
                                continue
                            for m, f in gs.items():
                                d = f[bs] - o[bs]
                                rows.append(dict(key, truth=tname, band_by=band_by, band=bname, situation=sname,
                                                 method=m, n=int(bs.sum()), sum_abs=float(np.abs(d).sum()),
                                                 sum_err=float(d.sum())))
    return rows


def part(c):
    return PARTS / f"{cases.tag(c)}.csv.gz"


def run_one(c):
    t0 = time.time()
    for attempt in range(4):
        try:
            rows = score_cycle(c)
            break
        except Exception as ex:  # noqa: BLE001
            print(f"{cases.tag(c)} attempt {attempt + 1} failed: {ex!r}", flush=True)
            if attempt == 3:
                return cases.tag(c), -1, time.time() - t0
            time.sleep(10 * (attempt + 1))
    p = part(c)
    tmp = p.with_name(p.name + ".tmp")
    pd.DataFrame(rows).to_csv(tmp, index=False, compression="gzip")
    os.replace(tmp, p)
    return cases.tag(c), len(rows), time.time() - t0


def combine():
    dfs = []
    for f in sorted(PARTS.glob("*.csv.gz")):
        try:
            dfs.append(pd.read_csv(f))
        except pd.errors.EmptyDataError:
            pass
    df = pd.concat(dfs, ignore_index=True)
    tmp = OUT / "rows.csv.gz.tmp"
    df.to_csv(tmp, index=False, compression="gzip")
    os.replace(tmp, OUT / "rows.csv.gz")
    print(f"rows.csv.gz: {len(df)} rows from {len(dfs)} cycles", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("start")
    ap.add_argument("end")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args()
    PARTS.mkdir(parents=True, exist_ok=True)
    d0, d1 = (dt.datetime.strptime(x, "%Y-%m-%d") for x in (a.start, a.end))
    todo = []
    d = d0
    while d <= d1:
        for h in (0, 12):
            c = d.replace(hour=h)
            if all(desk._path(b, desk.issue_settled(c)).exists() for b in BASINS):
                if a.rebuild or not part(c).exists():
                    todo.append(c)
        d += dt.timedelta(days=1)
    print(f"{len(todo)} cycles to score", flush=True)
    t0 = time.time()
    if a.workers > 1:
        import multiprocessing as mp
        with mp.get_context("spawn").Pool(a.workers) as pool:
            for k, r in enumerate(pool.imap_unordered(run_one, todo), 1):
                print(f"[{k}/{len(todo)}] {r[0]} rows={r[1]} {r[2]:.0f}s", flush=True)
    else:
        for k, c in enumerate(todo, 1):
            r = run_one(c)
            print(f"[{k}/{len(todo)}] {r[0]} rows={r[1]} {r[2]:.0f}s", flush=True)
    combine()
    print(f"done in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
