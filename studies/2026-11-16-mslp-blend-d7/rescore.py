"""POST HOC re-score for the equal-false-lows analysis (lead's request 2026-11-16, after the first results).

    python3 rescore.py [--limit N] [--workers W] [--cycles ...] [--basins ...]

Rebuilds the main candidates at their untuned settings (plus the weighted-blend presets and four exploratory
post hoc candidates) and re-scores position and false lows with the forecast lows thinned by PROMINENCE: only
lows whose 500 km pressure drop (ring mean minus centre, candidates._drop_hpa, the same definition as
rk.score.pressure_drop) is at least T hPa, T in TS, in both the matching pool (< 1010) and the false-low count
(< 1000). Output per basin-cycle (resumable) under rk.paths.cache("extra","mslp-blend-d7","rescore"):
  case_*.parquet  basin, cycle, lead, truth, cand, setting, rmse, bias, false_0..8, nfc_0..8   (T index k)
  low_*.parquet   one row per analysed low (< 1000 hPa, 3 deg inside the box): lat, lon, an_hpa, water (centre
                  over open water in the analysis mask), pos_k, hung_k, hit_k, dep_k per T index
Matching is the house form (nearest forecast low within 1000 km, a miss costs 1000 km and takes the field at the
analysed centre for its depth); tests/test_mslp_blend_rescore.py checks the vectorised match against
rk.score.low_case at T = 0. Exploratory candidates (POST HOC, default cap 450 km, no tuning): al_gi (aligned
GFS+IFS), al_det (aligned GFS+IFS+AIFS, the ensemble means only place the target and are not blended) and the
depth-fix versions ald_gi, ald_det.
"""
import argparse
import multiprocessing as mp
import os
import sys
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from rk import basins, cases as rkc, paths, score as rks

TS = (0, 1, 2, 3, 4, 5, 6, 8, 10)
LEADS = tuple(range(24, 169, 24))
BASINS = ("natl", "npac")
ROOT = paths.cache("extra", "mslp-blend-d7", "_root").parent
OUT = Path(os.environ.get("MSLP_BLEND_RESCORE") or ROOT / "rescore")
PARTS = OUT / "parts"
WHICH = {"gfs", "ifs", "aifs", "m_gi", "m_gif", "gefs", "ens", "aifsens", "grand", "bowl", "bowl_gfe2", "al", "ald",
         "od", "al_gfe2", "ald_gfe2", "od_gfe2"}
UNTUNED_LABEL = {"bowl", "bowl_gfe2", "al", "ald", "od", "al_gfe2", "ald_gfe2", "od_gfe2"}


def explore(cm, case, p):
    """Post hoc candidates. Returns {name: field}."""
    R = case.runs
    out = {}
    if "gfs" in R and "ifs" in R:
        names = ["gfs", "ifs"]
        w, _ = cm.aligned_runs(case, names, p)
        al = cm._mean(w)
        out["al_gi"] = al
        out["ald_gi"] = cm.depth_fix(case, al, names, p)
    dets = [m for m in ("gfs", "ifs", "aifs") if m in R]
    ens = [e for e in cm.ENSN if e in R]
    if len(dets) == 3 and ens:
        names = dets + ens
        w, _ = cm.aligned_runs(case, names, p)
        al = cm._mean({m: w[m] for m in dets})
        out["al_det"] = al
        out["ald_det"] = cm.depth_fix(case, al, names, p)
    return out


def match_all(D, fc_hpa, drop, an_hpa, field_at, Ts=TS):
    """Vectorised house-form match for every T. D [n_truth, n_pool] km; returns pos, hung, hit, dep each [n_truth, len(Ts)]."""
    n = D.shape[0]
    pos = np.full((n, len(Ts)), 1000.0)
    hung = np.full((n, len(Ts)), 1000.0)
    hit = np.zeros((n, len(Ts)), np.uint8)
    dep = np.zeros((n, len(Ts)), np.float32)
    for k, T in enumerate(Ts):
        sel = np.where(drop >= T)[0] if T > 0 else np.arange(D.shape[1])
        if n == 0:
            continue
        if len(sel):
            Ds = D[:, sel]
            j = Ds.argmin(1)
            d = Ds[np.arange(n), j]
            ok = d <= 1000.0
            pos[:, k] = np.where(ok, d, 1000.0)
            hit[:, k] = ok & (d <= 300.0)
            dep[:, k] = np.where(ok, fc_hpa[sel][j] - an_hpa, field_at - an_hpa)
            r, c = linear_sum_assignment(np.minimum(Ds, 1000.0))
            hung[r, k] = np.minimum(Ds[r, c], 1000.0)
        else:
            dep[:, k] = field_at - an_hpa
    return pos, hung, hit, dep


def run_one(args):
    basin, cycle = args
    import candidates as cm
    import run as R
    tag = rkc.tag(cycle)
    out_dir = PARTS / basin
    out_dir.mkdir(parents=True, exist_ok=True)
    done = out_dir / (tag + ".done")
    if done.exists():
        return basin, tag, "skip", 0.0
    t0 = time.time()
    zf = paths.cache("extra", "mslp-blend-d7", basin, tag + ".npz")
    with np.load(zf) as zz:
        z = {k: zz[k] for k in zz.files}
    members = R.load_members(basin, tag) if cycle.hour == 12 else None
    lats, lons = basins.grid(basin)
    g = cm.geo(basin)
    gw = cm.grid_values()["w"]
    base = cm._params(None)
    cs, ls = [], []
    for lead in LEADS:
        if "an_gfs_v%03d" % lead not in z or "an_ifs_v%03d" % lead not in z:
            continue
        mask = z["mask_v%03d" % lead].astype(bool)
        ans = {"gfs": z["an_gfs_v%03d" % lead], "ifs": z["an_ifs_v%03d" % lead]}
        ans["mean"] = ((ans["gfs"].astype(np.float64) + ans["ifs"]) / 2).astype(np.float32)
        tr = {}
        for t, a in ans.items():
            tl = rks.find_lows(a, basin, 1000.0, inset_deg=3.0)
            ta = rks.find_lows(a, basin, 1005.0)
            iy = np.clip(np.rint((lats[0] - tl.lat.to_numpy()) / 0.25).astype(int), 0, len(lats) - 1)
            ix = np.clip(np.rint((tl.lon.to_numpy() - lons[0]) / 0.25).astype(int), 0, len(lons) - 1)
            tr[t] = (a, tl, ta, mask[iy, ix])
        case = cm.prepare(basin, cycle, lead, z, members)
        fields = {}
        for name, f in cm._emit(case, base, which=WHICH).items():
            fields[(name, "default" if name in UNTUNED_LABEL else "base")] = f
        for preset, w in gw.items():
            for name, f in cm._emit(case, dict(base, w=w, w_gfe=w), which={"wb", "wb_gfe2"}).items():
                fields[(name, "w=" + preset)] = f
                if preset == "eq":
                    fields[(name, "default")] = f
        for name, f in explore(cm, case, base).items():
            fields[(name, "default")] = f
        for (name, setting), f in fields.items():
            f = np.asarray(f, np.float32)
            lw = rks.find_lows(f, basin, 1010.0)
            lat_, lon_, hp = lw.lat.to_numpy(), lw.lon.to_numpy(), lw.hpa.to_numpy()
            drop = np.array([cm._drop_hpa(f, g, la, lo) for la, lo in zip(lat_, lon_)]) if len(lw) else np.zeros(0)
            drop = np.nan_to_num(drop, nan=-1.0)
            for t, (a, tl, ta, water) in tr.items():
                e = rks.field_error(f, a, lats, mask)
                row = {"basin": basin, "cycle": pd.Timestamp(cycle), "lead": lead, "truth": t, "cand": name,
                       "setting": setting, "rmse": e["rmse"], "bias": e["bias"]}
                dmin = (rks.km(lat_[:, None], lon_[:, None], ta.lat.to_numpy()[None, :], ta.lon.to_numpy()[None, :]).min(1)
                        if len(lw) and len(ta) else np.full(len(lw), np.inf))
                for k, T in enumerate(TS):
                    deep = (hp < 1000.0) & ((drop >= T) | (T == 0))
                    row["false_%d" % k] = int((deep & (dmin > 500.0)).sum())
                    row["nfc_%d" % k] = int(deep.sum())
                cs.append(row)
                if len(tl):
                    D = rks.km(tl.lat.to_numpy()[:, None], tl.lon.to_numpy()[:, None], lat_[None, :], lon_[None, :]) \
                        if len(lw) else np.zeros((len(tl), 0))
                    an_h = tl.hpa.to_numpy()
                    fat = np.asarray(basins.sample(f, basin, tl.lat.to_numpy(), tl.lon.to_numpy()), float)
                    pos, hung, hit, dep = match_all(D, hp, drop, an_h, fat)
                    d = {"basin": basin, "cycle": pd.Timestamp(cycle), "lead": lead, "truth": t, "cand": name,
                         "setting": setting, "lat": tl.lat.to_numpy(), "lon": tl.lon.to_numpy(), "an_hpa": an_h,
                         "water": water}
                    for k in range(len(TS)):
                        d["pos_%d" % k], d["hung_%d" % k], d["hit_%d" % k], d["dep_%d" % k] = \
                            pos[:, k].astype(np.float32), hung[:, k].astype(np.float32), hit[:, k], dep[:, k]
                    ls.append(pd.DataFrame(d))
    for nm, parts in (("case", cs), ("low", ls)):
        if parts:
            df = pd.DataFrame(parts) if nm == "case" else pd.concat(parts, ignore_index=True)
            tmp = out_dir / ("%s_%s.tmp" % (nm, tag))
            df.to_parquet(tmp, index=False)
            os.replace(tmp, out_dir / ("%s_%s.parquet" % (nm, tag)))
    done.write_text("%.1f\n" % (time.time() - t0))
    return basin, tag, "ok", time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--cycles", nargs="*")
    ap.add_argument("--basins", nargs="*", default=list(BASINS))
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = []
    t, end = datetime(2025, 11, 1), datetime(2026, 3, 31, 12)
    while t <= end:
        for b in a.basins:
            tg = rkc.tag(t)
            if (a.cycles is None or tg in a.cycles) and paths.cache("extra", "mslp-blend-d7", b, tg + ".npz").exists() \
                    and not (PARTS / b / (tg + ".done")).exists():
                jobs.append((b, t))
        t += timedelta(hours=12)
    if a.limit:
        jobs = jobs[:a.limit]
    print(len(jobs), "basin-cycles", flush=True)
    t0 = time.time()
    with mp.get_context("spawn").Pool(a.workers) as pool:
        for i, (b, tg, st, dt_) in enumerate(pool.imap_unordered(run_one, jobs), 1):
            print("%s %s %s %s %.0fs [%d/%d, %.0f min]" % (time.strftime("%H:%M:%S"), b, tg, st, dt_, i, len(jobs),
                                                         (time.time() - t0) / 60), flush=True)
    print("finished", flush=True)


if __name__ == "__main__":
    main()
