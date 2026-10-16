"""Storm-force truth: SMAP (L-band) against ASCAT at storm and hurricane force, winter 2025-26.

Extraction step (this file): one task per UTC day, methods 1, 2 and 4. Writes work/day_results.pkl (not committed).
summarize.py turns that into the CSVs, numbers.md and the figure; obs_pairs.py does method 3.
Run: python3 compare.py [--days N] [--procs 4]
Everything is on the RSS 0.25 deg cell centres (snap with floor(x + 0.5)), equivalent-neutral wind, kt.
"""
import argparse
import os
import datetime as dt
import pickle
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from rk import paths  # noqa: E402

WORK = Path(os.environ.get("STORM_WORK") or paths.data("extra", "storm-force-truth", "work"))  # intermediates, not committed

from scipy import ndimage  # noqa: E402

from rk import cases, truth  # noqa: E402
from rk.basins import BASINS, inside  # noqa: E402

START, END = dt.date(2025, 11, 1), dt.date(2026, 3, 31)
R0, R1 = 416, 648                      # rows 15-70N of the global 720-row grid (lat -89.875 + 0.25 i)
NY, NX = R1 - R0, 1440
LAT = (-89.875 + 0.25 * np.arange(R0, R1)).astype(np.float32)
LON = (0.125 + 0.25 * np.arange(NX)).astype(np.float32)
LATG, LONG = np.meshgrid(LAT, LON, indexing="ij")
BASIN_ID = np.zeros((NY, NX), np.uint8)             # 1 natl, 2 npac, only 30-67N
for _i, _b in enumerate(("natl", "npac"), 1):
    BASIN_ID[inside(_b, LATG, LONG)] = _i
BASIN_NAME = {1: "natl", 2: "npac"}
R_EARTH = 6371.0
KM_PER_DEG = np.pi * R_EARTH / 180.0
W40 = np.array([[0.25, 0.5, 0.25], [0.5, 1.0, 0.5], [0.25, 0.5, 0.25]])
STRUCT8 = np.ones((3, 3), int)
BANDS_CELL = [25, 34, 48, 56, 64, 1e9]
HIST_BINS = np.arange(0, 100.01, 0.1)


def snap(lat, lon):
    """Grid indices (row in the 15-70N block, column) of RSS cell centres; floor(x + 0.5), never rint."""
    iy = np.floor((lat.astype(np.float64) + 89.875) / 0.25 + 0.5).astype(int) - R0
    ix = np.floor((lon.astype(np.float64) - 0.125) / 0.25 + 0.5).astype(int)
    return iy, ix


def _grid(c, val, off):
    """Scatter cell lists onto a [NY, NX] array of values and one of absolute minutes (NaN where empty)."""
    iy, ix = snap(c["lat"], c["lon"])
    g = np.full((NY, NX), np.nan, np.float32)
    t = np.full((NY, NX), np.nan, np.float32)
    g[iy, ix] = val
    t[iy, ix] = c["t_min"].astype(np.float32) + off
    return g, t


_CACHE = {}


def day_arrays(day, off):
    """Gridded pass arrays of one UTC day; absolute time = minutes after 00 UTC of the day plus off.
    ascat: list of dict(sat, ptype, day, raw (rain-free, intercal), any (any rain flag, intercal), rain (bool grid), t)
    smap: list of dict(node, day, v, t)."""
    if (day, off) in _CACHE:
        return _CACHE[(day, off)]
    a, s = truth.ascat_day(day), truth.smap_day(day)
    out = {"ascat": [], "smap": []}
    if a is not None:
        v = truth._intercal(a["spd_enw_kt"], a["sat"])
        rain = (a["scat_rain"] == 1) | (a["rad_rain"] >= 2)
        lt = (a["t_min"] / 60.0 + a["lon"] / 15.0) % 24
        pt = np.where((lt >= 3) & (lt < 15), 0, 1)
        for sat in (2, 3):
            for p in (0, 1):
                k = (a["sat"] == sat) & (pt == p)
                if k.sum() < 100:
                    continue
                c = {f: a[f][k] for f in ("lat", "lon", "t_min")}
                g_any, t = _grid(c, v[k], off)
                r = np.zeros((NY, NX), bool)
                iy, ix = snap(c["lat"], c["lon"])
                r[iy, ix] = rain[k]
                g_raw = np.where(r, np.nan, g_any)
                out["ascat"].append(dict(sat=sat, ptype=p, day=day, raw=g_raw, any=g_any, rain=r, t=t))
    if s is not None:
        for n in (0, 1):
            k = s["node"] == n
            if k.sum() < 100:
                continue
            c = {f: s[f][k] for f in ("lat", "lon", "t_min")}
            g, t = _grid(c, s["spd_enw_kt"][k], off)
            out["smap"].append(dict(node=n, day=day, v=g, t=t))
    if len(_CACHE) > 8:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[(day, off)] = out
    return out


def avg40(v, t):
    """ASCAT to SMAP's ~40 km footprint: 3x3 weighted mean (centre 1, edge 0.5, corner 0.25) over cells of the
    same pass (|dt| <= 20 min), at least 6 of 9 valid; NaN elsewhere and where the centre is empty."""
    vp = np.pad(v, 1, constant_values=np.nan)
    tp = np.pad(t, 1, constant_values=np.nan)
    num = np.zeros_like(v, np.float64)
    wsum = np.zeros_like(v, np.float64)
    cnt = np.zeros(v.shape, int)
    with np.errstate(invalid="ignore"):
        for dy in range(3):
            for dx in range(3):
                vs, ts = vp[dy:dy + NY, dx:dx + NX], tp[dy:dy + NY, dx:dx + NX]
                ok = np.isfinite(vs) & (np.abs(ts - t) <= 20.0)
                w = W40[dy, dx]
                num += np.where(ok, vs, 0.0) * w
                wsum += ok * w
                cnt += ok
        out = np.where(np.isfinite(v) & (cnt >= 6), num / np.maximum(wsum, 1e-9), np.nan)
    return out.astype(np.float32)


def dist_km(lat0, lon0, lat, lon):
    p0, p = np.radians(lat0), np.radians(lat)
    dl = np.radians(lon - lon0)
    c = np.sin(p0) * np.sin(p) + np.cos(p0) * np.cos(p) * np.cos(dl)
    return R_EARTH * np.arccos(np.clip(c, -1, 1))


def disk_window(iy, ix, lat0):
    """Index slices generously covering a 300 km disk around a cell."""
    dr = int(300 / KM_PER_DEG / 0.25) + 2
    dc = int(300 / (KM_PER_DEG * np.cos(np.radians(min(abs(lat0), 80)))) / 0.25) + 2
    return slice(max(iy - dr, 0), min(iy + dr + 1, NY)), slice(max(ix - dc, 0), min(ix + dc + 1, NX))


def objects(field):
    """Connected regions (8-connectivity) of field >= 40 whose max >= 48 -> list of dict(mask-slice info)."""
    f = np.where(np.isfinite(field) & (BASIN_ID > 0), field, np.nan)
    lab, n = ndimage.label(np.nan_to_num(f, nan=0.0) >= 40, structure=STRUCT8)
    out = []
    if n == 0:
        return out
    idx = np.arange(1, n + 1)
    mx = ndimage.maximum(np.nan_to_num(f, nan=0.0), lab, idx)
    pos = ndimage.maximum_position(np.nan_to_num(f, nan=0.0), lab, idx)
    for k, m, p in zip(idx, mx, pos):
        if m >= 48:
            out.append(dict(cells=(lab == k), peak=float(m), iy=int(p[0]), ix=int(p[1])))
    return out


def match_disk(obj, cand, field_key, t_peak):
    """Best candidate pass for an object's peak: cells within 300 km and 180 min of the peak time, pass with the
    smallest median |dt|. Returns dict or None (fewer than 50 valid cells in the disk, or coverage < 70%)."""
    iy, ix = obj["iy"], obj["ix"]
    ys, xs = disk_window(iy, ix, float(LAT[iy]))
    d = dist_km(float(LAT[iy]), float(LON[ix]), LATG[ys, xs], LONG[ys, xs])
    disk = d <= 300.0
    best = None
    for c in cand:
        v, t = c[field_key][ys, xs], c["t"][ys, xs]
        ok = disk & np.isfinite(v) & (np.abs(t - t_peak) <= 180.0)
        if ok.sum() == 0:
            continue
        gap = float(np.median(np.abs(t[ok] - t_peak)))
        if best is None or gap < best[0]:
            best = (gap, c, ok, v, t)
    if best is None:
        return "no_pass"
    gap, c, ok, v, t = best
    if ok.sum() < 50:
        return "few_cells"
    full_v, full_t = c[field_key], c["t"]
    cov = float(np.mean(np.isfinite(full_v[obj["cells"]]) & (np.abs(full_t[obj["cells"]] - t_peak) <= 180.0)))
    if cov < 0.70:
        return "coverage"
    vv = v[ok]
    k = int(np.argmax(vv))
    yy, xx = np.nonzero(ok)
    return dict(c=c, gap=gap, n_disk=int(ok.sum()), cov=cov, peak=float(vv[k]), p95=float(np.percentile(vv, 95)),
                lat=float(LATG[ys, xs][yy[k], xx[k]]), lon=float(LONG[ys, xs][yy[k], xx[k]]),
                t_peak=float(t[ok][k]), ok=ok, ys=ys, xs=xs)


def run_day(day):
    t0 = time.time()
    D = (day - START).days
    one = dt.timedelta(days=1)
    prev, cur, nxt = day_arrays(day - one, -1440), day_arrays(day, 0), day_arrays(day + one, 1440)
    asc_all = prev["ascat"] + cur["ascat"] + nxt["ascat"]
    smp_all = prev["smap"] + cur["smap"] + nxt["smap"]
    for a in asc_all:
        if "a40" not in a:
            a["a40"] = avg40(a["raw"], a["t"])
    ho = bool(cases.held_out(day))
    iso = day.isocalendar()
    wk = iso[0] * 100 + iso[1]
    rows, diag = [], {}

    # ---- method 1, direction ASCAT: objects of ASCAT40 in today's passes, matched to one SMAP pass ----
    for a in cur["ascat"]:
        for ob in objects(a["a40"]):
            iy, ix = ob["iy"], ob["ix"]
            tp = float(a["t"][iy, ix])
            m = match_disk(ob, smp_all, "v", tp)
            diag[("ascat", m if isinstance(m, str) else "matched")] = diag.get(("ascat", m if isinstance(m, str) else "matched"), 0) + 1
            if isinstance(m, str):
                continue
            raw = a["raw"][ob["cells"]]
            raw = raw[np.isfinite(raw)]
            rows.append(dict(
                date=str(day), week=wk, held_out=ho, basin=BASIN_NAME[int(BASIN_ID[iy, ix])], sat=a["sat"],
                ptype=a["ptype"], node=m["c"]["node"], direction="ascat", gap_min=m["gap"],
                lat=float(LAT[iy]), lon=float(LON[ix]), t_peak=tp, other_lat=m["lat"], other_lon=m["lon"], other_t=m["t_peak"],
                ascat40_peak=ob["peak"], ascat_raw_max=float(raw.max()), ascat_p95=float(np.percentile(raw, 95)),
                smap_peak=m["peak"], smap_p95=m["p95"], n_obj=int(ob["cells"].sum()), n_disk=m["n_disk"], cov=m["cov"]))

    # ---- method 1, direction SMAP: objects of SMAP in today's passes, matched to ASCAT40 ----
    for s in cur["smap"]:
        for ob in objects(s["v"]):
            iy, ix = ob["iy"], ob["ix"]
            tp = float(s["t"][iy, ix])
            m = match_disk(ob, asc_all, "a40", tp)
            diag[("smap", m if isinstance(m, str) else "matched")] = diag.get(("smap", m if isinstance(m, str) else "matched"), 0) + 1
            if isinstance(m, str):
                continue
            c = m["c"]
            rawd = c["raw"][m["ys"], m["xs"]][m["ok"]]
            rawd = rawd[np.isfinite(rawd)]
            sv = s["v"][ob["cells"]]
            sv = sv[np.isfinite(sv)]
            rows.append(dict(
                date=str(day), week=wk, held_out=ho, basin=BASIN_NAME[int(BASIN_ID[iy, ix])], sat=c["sat"],
                ptype=c["ptype"], node=s["node"], direction="smap", gap_min=m["gap"],
                lat=float(LAT[iy]), lon=float(LON[ix]), t_peak=tp, other_lat=m["lat"], other_lon=m["lon"], other_t=m["t_peak"],
                ascat40_peak=m["peak"], ascat_raw_max=float(rawd.max()) if len(rawd) else np.nan,
                ascat_p95=float(np.percentile(rawd, 95)) if len(rawd) else np.nan,
                smap_peak=ob["peak"], smap_p95=float(np.percentile(sv, 95)),
                n_obj=int(ob["cells"].sum()), n_disk=m["n_disk"], cov=m["cov"]))

    # ---- method 2: cell pairs, today's ASCAT40 passes against SMAP passes of days -1..+1 ----
    cells = {}
    dom = BASIN_ID
    for a in cur["ascat"]:
        for s in smp_all:
            with np.errstate(invalid="ignore"):
                dtm = np.abs(a["t"] - s["t"])
                base = np.isfinite(a["a40"]) & np.isfinite(s["v"]) & (dom > 0) & (dtm <= 180.0)
            if not base.any():
                continue
            x, y, dd, bid = a["a40"][base], s["v"][base], dtm[base], dom[base]
            for win in (90, 180):
                k = dd <= win
                if not k.any():
                    continue
                for bname, bsel in (("natl", bid == 1), ("npac", bid == 2)):
                    kk = k & bsel
                    if not kk.any():
                        continue
                    key = (win, bname, a["sat"])
                    xs_, ys_ = x[kk].astype(np.float64), y[kk].astype(np.float64)
                    mean = 0.5 * (xs_ + ys_)
                    band = np.digitize(mean, BANDS_CELL) - 1       # -1 below 25
                    ok = band >= 0
                    ent = cells.setdefault(key, dict(
                        n=np.zeros(5), sd=np.zeros(5), sx=np.zeros(5), sy=np.zeros(5), sdd=np.zeros(5),
                        hx=np.zeros(len(HIST_BINS) - 1), hy=np.zeros(len(HIST_BINS) - 1), nall=0))
                    for b in range(5):
                        kb = band == b
                        ent["n"][b] += kb.sum()
                        ent["sd"][b] += (ys_ - xs_)[kb].sum()
                        ent["sdd"][b] += ((ys_ - xs_)[kb] ** 2).sum()
                        ent["sx"][b] += xs_[kb].sum()
                        ent["sy"][b] += ys_[kb].sum()
                    ent["hx"] += np.histogram(xs_, HIST_BINS)[0]
                    ent["hy"] += np.histogram(ys_, HIST_BINS)[0]
                    ent["nall"] += kk.sum()

    # ---- method 4: SMAP >= 48 kt cells (today's passes) with any ASCAT cell within 180 min ----
    rain = []
    for s in cur["smap"]:
        sel = np.isfinite(s["v"]) & (s["v"] >= 48) & (dom > 0)
        if not sel.any():
            continue
        iy, ix = np.nonzero(sel)
        sv, st = s["v"][sel], s["t"][sel]
        best = np.full(sv.shape, 1e9)
        aspd = np.full(sv.shape, np.nan)
        arain = np.zeros(sv.shape, bool)
        for a in asc_all:
            av, at, ar = a["any"][iy, ix], a["t"][iy, ix], a["rain"][iy, ix]
            with np.errstate(invalid="ignore"):
                d = np.abs(at - st)
                upd = np.isfinite(av) & (d <= 180.0) & (d < best)
            best = np.where(upd, d, best)
            aspd = np.where(upd, av, aspd)
            arain = np.where(upd, ar, arain)
        has = np.isfinite(aspd)
        rain.append(dict(basin=dom[sel], smap=sv, has=has, aspd=aspd, arain=arain, week=np.full(sv.shape, wk),
                         held_out=np.full(sv.shape, ho), dt=best))
    rain = {k: np.concatenate([r[k] for r in rain]) for k in rain[0]} if rain else None
    return dict(day=str(day), week=wk, held_out=ho, rows=rows, diag=diag, cells=cells, rain=rain, secs=time.time() - t0)


def _worker(day):
    return run_day(day)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=0, help="limit to the first N days (testing)")
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--out", default=str(WORK / "day_results.pkl"))
    a = ap.parse_args()
    days = [START + dt.timedelta(days=i) for i in range((END - START).days + 1)]
    if a.days:
        days = days[:a.days]
    t0 = time.time()
    if a.procs > 1:
        import multiprocessing as mp
        with mp.get_context("spawn").Pool(a.procs) as pool:
            res = pool.map(_worker, days, chunksize=1)
    else:
        res = [run_day(d) for d in days]
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "wb") as f:
        pickle.dump(res, f)
    print("days %d  pairs %d  %.1f s (sum of day times %.1f s)" % (
        len(res), sum(len(r["rows"]) for r in res), time.time() - t0, sum(r["secs"] for r in res)))


if __name__ == "__main__":
    main()
