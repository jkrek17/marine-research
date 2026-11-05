"""Pattern drill, step 1: every GFS-analysed low (< 1012 hPa) in both basins at 00/06/12/18 UTC over a
period, with what ASCAT saw within 500 km of it.

One small JSON per valid time under rk.paths.data("extra", "pattern-drill", "find"); a time already
written is skipped, so the run resumes after an interruption.

    python3 find_cases.py 2025-11-01 2026-03-31 [--workers 6]

Per low: lat, lon, hpa (GFS f000 PRMSL), cover (share of its open water that ASCAT saw: water within RADIUS_KM
that is nearer this low than any other low found, so a neighbour's winds are not counted;
+-90 min, rain dropped), n (seen cells), peak3 (3rd highest seen cell, kt, real 10 m wind, B/C
intercalibrated: the category speed, so one noisy cell does not set it), vmax (highest cell).
"""
import argparse
import datetime as dt
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from rk import fetch, paths, score, truth  # noqa: E402
from rk.basins import BASINS, grid  # noqa: E402

RADIUS_KM = 500.0
BELOW = 1012.0
OUT = paths.data("extra", "pattern-drill", "find")


def km_from(lat0, lon0, lats, lons):
    """Great-circle distance (km) from one point to a lat x lon grid."""
    la, lo = np.meshgrid(np.radians(lats), np.radians(lons), indexing="ij")
    p0, l0 = np.radians(lat0), np.radians(lon0)
    c = np.sin(p0) * np.sin(la) + np.cos(p0) * np.cos(la) * np.cos(lo - l0)
    return 6371.0 * np.arccos(np.clip(c, -1, 1))


def one(valid):
    p = OUT / (valid.strftime("%Y%m%d%H") + ".json")
    if p.exists():
        return "skip"
    o = fetch._ncep(fetch.gfs_url(valid, 0), {"PRMSL:mean sea level": "msl"})
    if o is None:
        return "no gfs"
    rec = {}
    for b in BASINS:
        msl = o["msl"][b] / 100.0
        lows = score.find_lows(msl, b, below=BELOW, inset_deg=3.0)
        a = truth.ascat(b, valid)
        water = truth.water_mask(b, valid)
        lats, lons = grid(b)
        g = None
        if a is not None and water is not None:
            g, _ = truth.ascat_to_grid(b, a["lat"], a["lon"], a["spd_kt"])
        rows = []
        dist = [km_from(r.lat, r.lon, lats, lons) for _, r in lows.iterrows()]
        nearest = np.argmin(np.stack(dist), axis=0) if dist else None
        for i, (_, r) in enumerate(lows.iterrows()):
            row = {"lat": float(r.lat), "lon": float(r.lon), "hpa": round(float(r.hpa), 1)}
            if g is not None:
                disc = (dist[i] <= RADIUS_KM) & (nearest == i) & water
                seen = disc & np.isfinite(g)
                nw, ns = int(disc.sum()), int(seen.sum())
                v = np.sort(g[seen])[::-1]
                row.update(cover=round(ns / nw, 3) if nw else 0.0, n=ns,
                           peak3=round(float(v[2]), 1) if ns >= 3 else None,
                           vmax=round(float(v[0]), 1) if ns else None)
            rows.append(row)
        rec[b] = {"ascat": a is not None, "lows": rows}
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec))
    tmp.replace(p)
    return "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("start")
    ap.add_argument("end")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    t0 = dt.datetime.fromisoformat(a.start)
    t1 = dt.datetime.fromisoformat(a.end) + dt.timedelta(hours=18)
    times = []
    while t0 <= t1:
        times.append(t0)
        t0 += dt.timedelta(hours=6)
    OUT.mkdir(parents=True, exist_ok=True)
    done = 0
    with ThreadPoolExecutor(a.workers) as ex:
        for t, res in zip(times, ex.map(lambda v: (v, _safe(v)), times)):
            done += 1
            if res[1] != "skip":
                print(done, len(times), res[0].strftime("%Y%m%d%H"), res[1], flush=True)


def _safe(v):
    try:
        return one(v)
    except Exception as e:  # keep going; the time is retried on the next run
        return "error %s" % e


if __name__ == "__main__":
    main()
