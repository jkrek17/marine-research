"""Pattern drill, step 4: the development ingredients around every candidate low at its start time, measured
objectively from the GFS analysis (and the GOES air-mass bands), then scored against what the low did in the
next 24 h (ASCAT category and peak, GFS central pressure).

    python3 ingredients.py measure [--workers 4]   # one row per candidate -> ingredients.csv (resumable per time)
    python3 ingredients.py score                   # reliability table -> ingredients_score.csv, ingredients.json

Ingredients (all within RADIUS_KM of the low unless said):
  eady       max Eady growth rate 850-500 hPa (per day)
  jet        max 250 hPa wind within 1000 km (kt)
  jet_pos    where the low sits relative to that jet maximum: left exit, right entrance, other (jet < 100 kt: weak)
  pva        max 500 hPa absolute vorticity advection (1e-5/s per 6 h) - upper forcing for ascent
  tilt       distance from the surface low to the 500 hPa height minimum within 1000 km (km; small = stacked)
  warm_adv   max 850 hPa warm advection (C/day)
  thk_grad   max 1000-500 hPa thickness gradient (dam per 100 km) - the baroclinic zone
  sea_air    max sea minus 2 m air temperature (C) - mixing of strong winds to the surface
  dry        share of the 500 km disc where the air-mass RGB shows dry upper air (WV6.2 - WV7.3 > -6 K)
  peak0, cat0, hpa0  the low as it is now (ASCAT peak kt, category, GFS central pressure)
Outcome: grew = category up at +24 h; decayed = category down; dpeak = ASCAT peak change (kt); dp = pressure
change (hPa, negative = deepened).
"""
import argparse
import csv
import datetime as dt
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))
from rk import KT, diag, fetch  # noqa: E402
import pick  # noqa: E402

ROOT = pick.ROOT
RADIUS_KM, FAR_KM = 500.0, 1000.0
HALF = 64                     # 0.25 deg cells each side of the low (16 deg)
ING = ["eady", "jet", "pva", "tilt", "warm_adv", "thk_grad", "sea_air", "dry"]
NAMES = {"eady": ("Eady growth", "per day"), "jet": ("250 mb jet speed", "kt"),
         "pva": ("500 mb vorticity advection", "1e-5/s per 6 h"), "tilt": ("Tilt to the 500 mb low", "km"),
         "warm_adv": ("850 mb warm advection", "C/day"), "thk_grad": ("Thickness gradient", "dam/100 km"),
         "sea_air": ("Sea minus air", "C"), "dry": ("Dry upper air (air mass)", "share of disc"),
         "peak0": ("Wind now (ASCAT)", "kt"), "hpa0": ("Central pressure now", "hPa")}


def km_grid(lat0, lon0, lats, lons):
    la, lo = np.meshgrid(np.radians(lats), np.radians(lons), indexing="ij")
    p0, l0 = np.radians(lat0), np.radians(lon0)
    c = np.sin(p0) * np.sin(la) + np.cos(p0) * np.cos(la) * np.cos(lo - l0)
    return 6371.0 * np.arccos(np.clip(c, -1, 1))


def crop(g, lat, lon):
    """0.25 deg crop of the global fields centred on the low -> (fields, lats, lons continuous)."""
    r0 = int(round((90 - lat) / 0.25)) - HALF
    c0 = int(round(lon / 0.25)) - HALF
    rows = np.clip(np.arange(r0, r0 + 2 * HALF + 1), 0, 720)
    cols = np.arange(c0, c0 + 2 * HALF + 1) % 1440
    lats = 90 - rows * 0.25
    lons = (c0 + np.arange(2 * HALF + 1)) * 0.25
    return {k: v[np.ix_(rows, cols)].astype(float) for k, v in g.items()}, lats, lons


def measure_low(g, am, lat, lon):
    c, lats, lons = crop(g, lat, lon)
    sm = {k: diag.smooth(c[k], 2.0) for k in ("z1000", "z850", "z500", "z250", "t850", "t500", "u850", "v850",
                                               "u500", "v500", "u250", "v250")}
    d = km_grid(lat, lon, lats, lons)
    near, far = d <= RADIUS_KM, d <= FAR_KM
    out = {}
    eady = diag.eady(sm["u850"], sm["v850"], sm["z850"], sm["t850"], 850.0, sm["u500"], sm["v500"], sm["z500"],
                     sm["t500"], 500.0, lats) * diag.DAY
    out["eady"] = float(np.nanmax(np.where(near, eady, np.nan)))
    w250 = np.hypot(sm["u250"], sm["v250"]) * KT
    wf = np.where(far, w250, -1)
    j = np.unravel_index(np.argmax(wf), wf.shape)
    out["jet"] = float(w250[j])
    # low position relative to the jet maximum, in the jet's own frame (x downstream, y to its left)
    ux, vy = sm["u250"][j], sm["v250"][j]
    sp = np.hypot(ux, vy)
    dx = (lon - lons[j[1]]) * 111.2 * np.cos(np.radians(lat))
    dy = (lat - lats[j[0]]) * 111.2
    along, left = (dx * ux + dy * vy) / sp, (-dx * vy + dy * ux) / sp
    if out["jet"] < 100:
        out["jet_pos"] = "weak jet"
    elif along > 0 and left > 0:
        out["jet_pos"] = "left exit"
    elif along < 0 and left < 0:
        out["jet_pos"] = "right entrance"
    else:
        out["jet_pos"] = "other"
    vort = diag.smooth(c["vort500"], 2.0)
    pva = diag.advection(vort, sm["u500"], sm["v500"], lats, lons) * 6 * 3600 * 1e5
    out["pva"] = float(np.nanmax(np.where(near, pva, np.nan)))
    zf = np.where(far, sm["z500"], np.inf)
    k = np.unravel_index(np.argmin(zf), zf.shape)
    out["tilt"] = float(d[k])
    tadv = diag.advection(sm["t850"], sm["u850"], sm["v850"], lats, lons) * diag.DAY
    out["warm_adv"] = float(np.nanmax(np.where(near, tadv, np.nan)))
    thk = (sm["z500"] - sm["z1000"]) / 10.0
    grad = np.hypot(diag.ddx(thk, lats, lons), diag.ddy(thk, lats)) * 1e5
    out["thk_grad"] = float(np.nanmax(np.where(near, grad, np.nan)))
    water = (c["land"] < 0.5) & (c["ice"] < 0.15)
    sa = np.where(water & near, diag.smooth(c["tsfc"] - c["t2"], 1.0), np.nan)
    out["sea_air"] = float(np.nanmax(sa)) if np.isfinite(sa).any() else float("nan")
    out["dry"] = float("nan")
    if am is not None:
        la2, lo2 = np.meshgrid(am["lat"], am["lon"], indexing="ij")
        lo_low = lon if lon >= am["lon"][0] else lon + 360
        sel = (np.abs(la2 - lat) < 5) & (np.abs(lo2 - lo_low) < 9)
        if sel.any():
            dd = km_grid(lat, lo_low, am["lat"], am["lon"]) <= RADIUS_KM
            ok = dd & np.isfinite(am["b08"]) & np.isfinite(am["b10"])
            if ok.sum() > 100:
                out["dry"] = float(((am["b08"] - am["b10"])[ok] > -6.0).mean())
    return out


def measure(workers):
    from rk import satellite
    cands = pick.candidates(pick.load())
    by_t = {}
    for x in cands:
        by_t.setdefault(x["t0"], []).append(x)
    cache = ROOT / "ingredients"
    cache.mkdir(exist_ok=True)

    def one(t):
        p = cache / (t.strftime("%Y%m%d%H") + ".json")
        if p.exists():
            return json.loads(p.read_text())
        g = fetch.gfs_global(t, 0, fetch.DRILL)
        if g is None:
            return []
        rows = []
        ams = {}
        for x in by_t[t]:
            b = x["basin"]
            if b not in ams:
                try:
                    ams[b] = satellite.airmass_box(b, t)
                except Exception:
                    ams[b] = None
            r = measure_low(g, ams[b], x["r0"]["lat"], x["r0"]["lon"])
            r.update(basin=b, t0=t.strftime("%Y%m%d%H"), lat=x["r0"]["lat"], lon=x["r0"]["lon"],
                     hpa0=x["r0"]["hpa"], peak0=x["r0"]["peak3"], cat0=x["c0"], hpa24=x["r1"]["hpa"],
                     peak24=x["r1"]["peak3"], cat24=x["c1"])
            rows.append(r)
        p.write_text(json.dumps(rows))
        return rows

    times = sorted(by_t)
    allrows = []
    with ThreadPoolExecutor(workers) as ex:
        for i, rows in enumerate(ex.map(one, times)):
            allrows += rows
            if i % 50 == 0:
                print(i, len(times), flush=True)
    keys = ["basin", "t0", "lat", "lon", "hpa0", "peak0", "cat0", "hpa24", "peak24", "cat24", "jet_pos"] + ING
    with open(ROOT / "ingredients.csv", "w", newline="") as f:
        w = csv.DictWriter(f, keys)
        w.writeheader()
        for r in allrows:
            w.writerow({k: r.get(k) for k in keys})
    print("rows", len(allrows))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["measure", "score"])
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    if a.what == "measure":
        measure(a.workers)
    else:
        import score_ingredients
        score_ingredients.main()
