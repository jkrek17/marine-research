"""Pattern drill, step 4: the development ingredients around every candidate low at its start time, measured
objectively from the GFS analysis (and the GOES air-mass bands), then scored against what the low did in the
next 24 h (ASCAT category and peak, GFS central pressure).

    python3 ingredients.py measure [--workers 4]   # one row per candidate -> ingredients.csv (resumable per time)
    python3 ingredients.py score                   # reliability table -> ingredients_score.csv, ingredients.json

Version 2 (after the expert review of 2026-11-05): fields smoothed to about 1.25 deg; a high percentile over a
sector, not the single highest cell; N^2 floored in the Eady rate; dry air must be clear of cold cloud and on
the low's rear side; tilt measured to the 500 hPa vorticity maximum, not the edge of the search circle; jet
quadrants bounded around the streak. Ingredients (P90 = 90th percentile over the area):
  eady       P90 Eady growth rate 850-500 hPa (per day) within 500 km, N^2 floored at 2.5e-5 s^-2
  jet        max 250 hPa wind within 1000 km (kt)
  jet_pos    left exit / right entrance (the two ascent quadrants) when the low is 300-1200 km along the streak
             from its maximum and within 600 km across it; "near streak" otherwise; "weak jet" under 100 kt
  pva        P90 500 hPa absolute vorticity advection (1e-9 s^-2) within 500 km (warm side included)
  tilt       distance from the surface low to the 500 hPa vorticity maximum within 1000 km (km; small = stacked)
  warm_adv   P90 850 hPa warm advection (C/day) within 500 km
  thk_grad   P90 1000-500 hPa thickness gradient (dam per 100 km) within 500 km
  sea_air    P90 sea minus 2 m air temperature (C) over open water within 500 km
  dry        share of the rear (west) half of the 500 km disc where the air-mass RGB shows dry upper air:
             WV6.2 - WV7.3 > -6 K and IR10.3 warmer than 250 K (cold cloud tops pass the WV test too)
  thetae     P90 850 hPa equivalent potential temperature within 500 km (K): warm, moist inflow (diabatic fuel)
  pwat       P90 precipitable water within 500 km (mm)
  trough_dist  distance to the strongest 500 hPa vorticity maximum WEST of the low within 1200 km (km)
  trough_app   500 hPa wind at that maximum toward the low (kt; positive = the trough is closing in)
  thk_anom   1000-500 thickness within 150 km of the low minus the 400-600 km ring mean (dam; negative = the
             low sits in cold air, occluded)
  wind925    P90 925 hPa wind speed over water within 500 km (kt): wind available to mix down
  dp_prev    GFS central pressure change over the previous 12 h (hPa; negative = deepening), from the
             analysed lows 6 and 12 h before, each the nearest within 700 km
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
SIGMA = 5.0                   # smoothing, 0.25 deg cells (about 1.25 deg)
N2_MIN = 2.5e-5               # floor on N^2 for the Eady rate (s^-2)
PCT = 90                      # percentile over an area instead of the single highest cell
CACHE = "ingredients2"        # per-time cache folder under ROOT (version 1 lives in ingredients/)
EXTRA = ["thetae", "pwat", "trough_dist", "trough_app", "thk_anom", "wind925"]
ING = ["eady", "jet", "pva", "tilt", "warm_adv", "thk_grad", "sea_air", "dry", "dp_prev"] + EXTRA
EXTRA_WANT = {k: v for k, v in fetch.DRILL.items() if v in ("z1000", "z500", "u500", "v500", "vort500", "t850",
                                                            "rh850", "pwat", "u925", "v925", "land", "ice")}
NAMES = {"eady": ("Eady growth", "per day"), "jet": ("250 mb jet speed", "kt"),
         "pva": ("500 mb vorticity advection", "1e-9 /s2"), "tilt": ("Distance to the 500 mb vorticity max", "km"),
         "warm_adv": ("850 mb warm advection", "C/day"), "thk_grad": ("Thickness gradient", "dam/100 km"),
         "sea_air": ("Sea minus air", "C"), "dry": ("Dry air behind the low", "share of rear half"),
         "dp_prev": ("Pressure change last 12 h", "hPa"),
         "thetae": ("850 mb theta-e", "K"), "pwat": ("Precipitable water", "mm"),
         "trough_dist": ("Distance to the upstream trough", "km"), "trough_app": ("Upstream trough closing speed", "kt"),
         "thk_anom": ("Thickness at the centre vs around", "dam"), "wind925": ("925 mb wind", "kt"),
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


def pct(a, mask):
    v = a[mask & np.isfinite(a)]
    return float(np.percentile(v, PCT)) if v.size else float("nan")


def jet_class(jet, lat, lon, jlat, jlon, u, v):
    """Where the low sits relative to the jet maximum, in the streak's frame (x downstream, y to its left)."""
    if jet < 100:
        return "weak jet"
    sp = np.hypot(u, v)
    dx = (lon - jlon) * 111.2 * np.cos(np.radians(lat))
    dy = (lat - jlat) * 111.2
    along, left = (dx * u + dy * v) / sp, (-dx * v + dy * u) / sp
    if 300 <= abs(along) <= 1200 and abs(left) <= 600:
        if along > 0 and left > 0:
            return "left exit"
        if along < 0 and left < 0:
            return "right entrance"
        return "right exit" if along > 0 else "left entrance"
    return "near streak"


def measure_low(g, am, lat, lon):
    c, lats, lons = crop(g, lat, lon)
    sm = {k: diag.smooth(c[k], SIGMA) for k in ("z1000", "z850", "z500", "z250", "t850", "t500", "u850", "v850",
                                                 "u500", "v500", "u250", "v250", "vort500")}
    d = km_grid(lat, lon, lats, lons)
    near, far = d <= RADIUS_KM, d <= FAR_KM
    out = {}
    eady = diag.eady(sm["u850"], sm["v850"], sm["z850"], sm["t850"], 850.0, sm["u500"], sm["v500"], sm["z500"],
                     sm["t500"], 500.0, lats, n2_min=N2_MIN) * diag.DAY
    out["eady"] = pct(eady, near)
    w250 = np.hypot(sm["u250"], sm["v250"]) * KT
    wf = np.where(far, w250, -1)
    j = np.unravel_index(np.argmax(wf), wf.shape)
    out["jet"] = float(w250[j])
    out["jet_pos"] = jet_class(out["jet"], lat, lon, lats[j[0]], lons[j[1]], sm["u250"][j], sm["v250"][j])
    pva = diag.advection(sm["vort500"], sm["u500"], sm["v500"], lats, lons) * 1e9
    out["pva"] = pct(pva, near)
    vf = np.where(far, sm["vort500"], -np.inf)
    k = np.unravel_index(np.argmax(vf), vf.shape)
    out["tilt"] = float(d[k])
    tadv = diag.advection(sm["t850"], sm["u850"], sm["v850"], lats, lons) * diag.DAY
    out["warm_adv"] = pct(tadv, near)
    thk = (sm["z500"] - sm["z1000"]) / 10.0
    grad = np.hypot(diag.ddx(thk, lats, lons), diag.ddy(thk, lats)) * 1e5
    out["thk_grad"] = pct(grad, near)
    water = (c["land"] < 0.5) & (c["ice"] < 0.15)
    out["sea_air"] = pct(diag.smooth(c["tsfc"] - c["t2"], 2.0), water & near)
    out["dry"] = float("nan")
    if am is not None:
        lo_low = lon if lon >= am["lon"][0] else lon + 360
        dd = km_grid(lat, lo_low, am["lat"], am["lon"])
        rear = (dd <= RADIUS_KM) & (am["lon"][None, :] < lo_low)
        ok = rear & np.isfinite(am["b08"]) & np.isfinite(am["b10"]) & np.isfinite(am["b13"])
        if ok.sum() > 50:
            dry = ((am["b08"] - am["b10"]) > -6.0) & (am["b13"] > 250.0)
            out["dry"] = float(dry[ok].mean())
    return out


def measure_extra(g, lat, lon):
    c, lats, lons = crop(g, lat, lon)
    sm = {k: diag.smooth(c[k], SIGMA) for k in ("z1000", "z500", "u500", "v500", "vort500", "t850", "rh850", "pwat")}
    d = km_grid(lat, lon, lats, lons)
    near = d <= RADIUS_KM
    out = {"thetae": pct(diag.theta_e(sm["t850"], sm["rh850"], 850.0), near), "pwat": pct(sm["pwat"], near)}
    west = (lons[None, :] < lon) & (d <= 1200.0) & (d > 150.0)
    vf = np.where(west, sm["vort500"], -np.inf)
    if np.isfinite(vf).any() and vf.max() > -np.inf:
        k = np.unravel_index(np.argmax(vf), vf.shape)
        out["trough_dist"] = float(d[k])
        dx = (lon - lons[k[1]]) * 111.2 * np.cos(np.radians(lats[k[0]]))
        dy = (lat - lats[k[0]]) * 111.2
        n = np.hypot(dx, dy)
        out["trough_app"] = float((sm["u500"][k] * dx + sm["v500"][k] * dy) / n * KT)
    else:
        out["trough_dist"] = out["trough_app"] = float("nan")
    thk = (sm["z500"] - sm["z1000"]) / 10.0
    ring = (d >= 400) & (d <= 600)
    out["thk_anom"] = float(np.nanmean(thk[d <= 150]) - np.nanmean(thk[ring]))
    water = (c["land"] < 0.5) & (c["ice"] < 0.15)
    w925 = np.hypot(diag.smooth(c["u925"], 2.0), diag.smooth(c["v925"], 2.0)) * KT
    out["wind925"] = pct(w925, near & water)
    return out


def dp_prev(rec, basin, t0, lat, lon, hpa0):
    """Central pressure change over the previous 12 h, following the analysed lows back in 6 h steps."""
    la, lo = lat, lon
    hpa = None
    for h in (6, 12):
        t = t0 - dt.timedelta(hours=h)
        rows = rec.get(t, {}).get(basin, {}).get("lows", [])
        if not rows:
            return float("nan")
        r = min(rows, key=lambda r: pick.km(r["lat"], r["lon"], la, lo))
        if pick.km(r["lat"], r["lon"], la, lo) > 700:
            return float("nan")
        la, lo, hpa = r["lat"], r["lon"], r["hpa"]
    return float(hpa0 - hpa)


def measure(workers):
    from rk import satellite
    rec = pick.load()          # version 2 truth (find2: the low's own pressure basin)
    cands = pick.candidates(rec)
    by_t = {}
    for x in cands:
        by_t.setdefault(x["t0"], []).append(x)
    cache = ROOT / CACHE
    cache.mkdir(exist_ok=True)

    def label(r, x):
        """Outcomes from the current candidate (version 2: the low's own pressure basin), not the cached ones."""
        r.update(basin=x["basin"], t0=x["t0"].strftime("%Y%m%d%H"), lat=x["r0"]["lat"], lon=x["r0"]["lon"],
                 hpa0=x["r0"]["hpa"], peak0=x["r0"]["peak3"], cat0=x["c0"], hpa24=x["r1"]["hpa"],
                 peak24=x["r1"]["peak3"], cat24=x["c1"])
        return r

    def one(t):
        p = cache / (t.strftime("%Y%m%d%H") + ".json")
        rows = json.loads(p.read_text()) if p.exists() else []
        have = {(r["basin"], round(r["lat"], 2), round(r["lon"], 2)): r for r in rows}
        look = lambda x: have.get((x["basin"], round(x["r0"]["lat"], 2), round(x["r0"]["lon"], 2)))
        missing = [x for x in by_t[t] if look(x) is None]
        stale = [r for r in rows if not all(k in r for k in EXTRA)]
        if missing:
            g = fetch.gfs_global(t, 0, fetch.DRILL)
            if g is None:
                return [label(dict(look(x)), x) for x in by_t[t] if look(x) is not None]
            ams = {}
            for x in missing:
                b = x["basin"]
                if b not in ams:
                    try:
                        ams[b] = satellite.airmass_box(b, t)
                    except Exception:
                        ams[b] = None
                r = measure_low(g, ams[b], x["r0"]["lat"], x["r0"]["lon"])
                r.update(measure_extra(g, x["r0"]["lat"], x["r0"]["lon"]))
                r["dp_prev"] = dp_prev(rec, b, t, x["r0"]["lat"], x["r0"]["lon"], x["r0"]["hpa"])
                rows.append(label(r, x))
            for r in stale:
                r.update(measure_extra(g, r["lat"], r["lon"]))
        elif stale:
            g = fetch.gfs_global(t, 0, EXTRA_WANT)
            if g is not None:
                for r in stale:
                    r.update(measure_extra(g, r["lat"], r["lon"]))
        if missing or stale:
            p.write_text(json.dumps(rows))
            have = {(r["basin"], round(r["lat"], 2), round(r["lon"], 2)): r for r in rows}
        return [label(dict(look(x)), x) for x in by_t[t] if look(x) is not None]

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
