"""Pattern drill, step 3: the map fields and ASCAT for every case in key.csv -> deck/manifest.json and
deck/<id>.bin (format in design.md). Resumable: a case whose .bin exists is skipped (delete it to redo).

    python3 build_deck.py [--out <deck folder>] [--workers 4]

Maps: GFS analysis (f000) through rk.fetch.gfs_global, smoothed on the 0.25 deg grid, then every second
cell (0.5 deg) in a 25 x 40 deg box centred between the low at T and at T+24 h. ASCAT: rk.truth.ascat
(real 10 m wind, B/C intercalibrated, rain dropped), highest cell in each 0.5 deg box with its direction.
"""
import argparse
import csv
import json
import sys
import datetime as dt
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from rk import KT, diag, fetch, paths, truth  # noqa: E402

ROOT = paths.data("extra", "pattern-drill")
RES, NY, NX = 0.5, 51, 81          # 25 x 40 deg
MARGIN = 8                          # 0.25 deg cells kept around the box for smoothing and derivatives

# key, name, units, offset, scale (value = offset + scale x byte, byte 0..254, 255 missing)
FIELDS = [
    ("msl", "Sea level pressure", "hPa", 930.0, 0.5),
    ("thk", "1000-500 hPa thickness", "dam", 470.0, 0.5),
    ("z500", "500 hPa height", "dam", 460.0, 0.5),
    ("vort500", "500 hPa absolute vorticity", "1e-5/s", 0.0, 0.25),
    ("z250", "250 hPa height", "dam", 900.0, 1.0),
    ("wspd250", "250 hPa wind speed", "kt", 0.0, 1.0),
    ("eady", "Eady growth rate 850-500 hPa", "per day", 0.0, 0.0125),
    ("z850", "850 hPa height", "dam", 50.0, 0.5),
    ("t850", "850 hPa temperature", "C", -50.0, 0.4),
    ("tadv850", "850 hPa temperature advection", "C/day", -40.0, 0.32),
    ("sst_air", "Sea minus 2 m air temperature", "C", -10.0, 0.125),
]


def box_index(lat_n, lon_w, margin=MARGIN):
    """Global 0.25 deg row and column indices for the box plus margin (columns wrap at 360)."""
    r0 = int(round((90 - lat_n) / 0.25)) - margin
    c0 = int(round(lon_w / 0.25)) - margin
    rows = np.arange(r0, r0 + (NY - 1) * 2 + 1 + 2 * margin)
    cols = np.arange(c0, c0 + (NX - 1) * 2 + 1 + 2 * margin) % 1440
    return rows, cols


def maps(g, lat_n, lon_w):
    """Global GFS dict -> {key: [NY, NX]} physical units, plus land [NY, NX] bool."""
    rows, cols = box_index(lat_n, lon_w)
    lats = 90 - rows * 0.25
    lons = (lon_w - MARGIN * 0.25) + np.arange(len(cols)) * 0.25
    c = {k: v[np.ix_(rows, cols)].astype(float) for k, v in g.items()}
    sm = {k: diag.smooth(c[k], 2.0) for k in ("z1000", "z850", "z500", "z250", "t850", "t500",
                                               "u850", "v850", "u500", "v500", "u250", "v250")}
    out = {
        "msl": diag.smooth(c["msl"] / 100.0, 1.0),
        "thk": (sm["z500"] - sm["z1000"]) / 10.0,
        "z500": sm["z500"] / 10.0,
        "vort500": diag.smooth(c["vort500"], 1.5) * 1e5,
        "z250": sm["z250"] / 10.0,
        "wspd250": np.hypot(sm["u250"], sm["v250"]) * KT,
        "eady": diag.eady(sm["u850"], sm["v850"], sm["z850"], sm["t850"], 850.0,
                          sm["u500"], sm["v500"], sm["z500"], sm["t500"], 500.0, lats) * diag.DAY,
        "z850": sm["z850"] / 10.0,
        "t850": sm["t850"] - 273.15,
        "tadv850": diag.smooth(diag.advection(sm["t850"], sm["u850"], sm["v850"], lats, lons), 2.0) * diag.DAY,
    }
    water = (c["land"] < 0.5) & (c["ice"] < 0.15)
    out["sst_air"] = np.where(water, diag.smooth(c["tsfc"] - c["t2"], 1.0), np.nan)
    land = ~water
    sl = (slice(MARGIN, -MARGIN), slice(MARGIN, -MARGIN))
    out = {k: diag.subsample(v[sl], 2) for k, v in out.items()}
    out["eady"] = np.where(np.isfinite(out["eady"]), out["eady"], 0.0)   # unstable layer: no baroclinic growth
    return out, diag.subsample(land[sl], 2)


def quant(v, offset, scale):
    b = np.round((np.asarray(v, float) - offset) / scale)
    b = np.clip(b, 0, 254)
    return np.where(np.isfinite(v), b, 255).astype(np.uint8)


def ascat_box(basin, valid, lat_n, lon_w):
    """Highest ASCAT cell in each 0.5 deg box (kt) and its direction (deg from) -> two uint8 [NY, NX]."""
    spd = np.full((NY, NX), 255, np.uint8)
    dirn = np.full((NY, NX), 255, np.uint8)
    a = truth.ascat(basin, valid)
    if a is None:
        return spd, dirn
    iy = np.floor((lat_n - a["lat"]) / RES + 0.5).astype(int)
    ix = np.floor(((a["lon"] - lon_w) % 360) / RES + 0.5).astype(int)
    k = (iy >= 0) & (iy < NY) & (ix >= 0) & (ix < NX) & np.isfinite(a["spd_kt"])
    best = np.full((NY, NX), -1.0)
    for y, x, s, d in zip(iy[k], ix[k], a["spd_kt"][k], a["dir_deg"][k]):
        if s > best[y, x]:
            best[y, x] = s
            spd[y, x] = min(254, int(round(s)))
            dirn[y, x] = int(round((d % 360) / 2)) % 180
    return spd, dirn


def box_for(row):
    """North-west cell centre of the box: centred between the low at T and T+24 h (lon 0-360)."""
    la = (float(row["lat0"]) + float(row["lat24"])) / 2
    l0, l1 = float(row["lon0"]), float(row["lon24"])
    lo = (l0 + ((l1 - l0 + 180) % 360 - 180) / 2) % 360
    lat_n = round(min(max(la + (NY - 1) * RES / 2, 25.0 + (NY - 1) * RES), 85.0) * 2) / 2
    lon_w = round(((lo - (NX - 1) * RES / 2) % 360) * 2) / 2
    return lat_n, lon_w


def gfs(valid):
    return fetch.gfs_global(valid, 0, fetch.DRILL)   # ~75 MB decoded: not kept between snapshots


def one(row, out):
    p = out / (row["id"] + ".bin")
    if p.exists():
        return "skip"
    lat_n, lon_w = box_for(row)
    parts = []
    for key in ("t0", "t24"):
        valid = dt.datetime.strptime(row[key], "%Y%m%d%H")
        g = gfs(valid)
        if g is None:
            return "no gfs %s" % row[key]
        m, land = maps(g, lat_n, lon_w)
        for k, _, _, off, sc in FIELDS:
            parts.append(quant(m[k], off, sc))
        spd, dirn = ascat_box(row["basin"], valid, lat_n, lon_w)
        parts += [spd, dirn, land.astype(np.uint8)]
    tmp = p.with_suffix(".tmp")
    tmp.write_bytes(b"".join(a.tobytes() for a in parts))
    tmp.replace(p)
    return "ok"


def manifest(rows, out):
    cases = []
    for r in rows:
        if not (out / (r["id"] + ".bin")).exists():
            continue
        lat_n, lon_w = box_for(r)
        snap = lambda s: {"lat": float(r["lat" + s]), "lon": float(r["lon" + s]), "hpa": float(r["hpa" + s]),
                          "cat": int(r["cat" + s]), "peak": float(r["peak" + s]), "cover": float(r["cover" + s])}
        cases.append({"id": r["id"], "basin": r["basin"], "lat0": lat_n, "lon0": lon_w,
                      "t0": snap("0"), "t24": snap("24")})
    m = {"version": 1, "res": RES, "ny": NY, "nx": NX,
         "source": "GFS analysis maps; ASCAT (RSS, Metop-B/C) truth within 500 km of the low",
         "fields": [{"key": k, "name": n, "units": u, "offset": o, "scale": s} for k, n, u, o, s in FIELDS],
         "cases": cases}
    (out / "manifest.json").write_text(json.dumps(m, separators=(",", ":")))
    return len(cases)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "page" / "deck"))
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(open(ROOT / "key.csv")))
    with ThreadPoolExecutor(a.workers) as ex:
        for r, res in zip(rows, ex.map(lambda r: _safe(r, out), rows)):
            if res != "skip":
                print(r["id"], res, flush=True)
    print("manifest", manifest(rows, out), "cases")


def _safe(r, out):
    try:
        return one(r, out)
    except Exception as e:
        return "error %r" % e


if __name__ == "__main__":
    main()
