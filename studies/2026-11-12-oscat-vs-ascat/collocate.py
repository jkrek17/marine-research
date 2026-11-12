"""OSCAT-3 and STAR high-res ASCAT (NOAA STAR, as served) against RSS ASCAT (equivalent-neutral, as served),
collocated in 0.25 deg cells with pass times within --dt minutes. One CSV row per collocated cell.

STAR points carry only a time bracket [file start, next start]; the bracket midpoint is used and pairs whose
bracket does not overlap the RSS time +- dt are dropped. Rain-flagged points (STAR q=1, RSS scatterometer rain
flag) are dropped. Run: python3 collocate.py --start 20261013 --end 20261107 --step 2"""
import argparse
import csv
import datetime as dt
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from rk import truth  # noqa: E402


def cells(lat, lon, *vals):
    """Grid points to the RSS 0.25 deg cells (centres x.125): key -> mean of each value."""
    iy = np.floor((lat + 90.0) * 4).astype(np.int64)
    ix = np.floor((lon % 360.0) * 4).astype(np.int64) % 1440
    key = iy * 1440 + ix
    u, inv, cnt = np.unique(key, return_inverse=True, return_counts=True)
    out = [np.bincount(inv, weights=v.astype(np.float64)) / cnt for v in vals]
    return u, cnt, out


def day_rows(day, dt_max, writer):
    a = truth.ascat_day(day)
    if a is None:
        return 0
    keep = a["scat_rain"] == 0
    akey = (np.floor((a["lat"][keep] + 90) * 4).astype(np.int64) * 1440
            + np.floor(a["lon"][keep] * 4).astype(np.int64) % 1440)
    aspd, at, asat = a["spd_enw_kt"][keep], a["t_min"][keep].astype(np.float64), a["sat"][keep]
    n = 0
    for kind in ("oscat", "uhr"):
        s = truth.star_day(kind, day)
        if s is None:
            continue
        for pid in np.unique(s["pass_id"]):
            m = (s["pass_id"] == pid) & (s["q"] == 0)
            if m.sum() < 50:
                continue
            t0, t1 = float(s["t_min"][m][0]), float(s["t_end_min"][m][0])
            tmid = 0.5 * (t0 + t1)
            sat = int(s["sat"][m][0])
            key, cnt, (spd,) = cells(s["lat"][m], s["lon"][m], s["spd_kt"][m])
            # all RSS cells of this day in those keys, within the time window
            idx = np.nonzero(np.isin(akey, key))[0]
            if idx.size == 0:
                continue
            ok = (np.abs(at[idx] - tmid) <= dt_max) & (at[idx] >= t0 - dt_max) & (at[idx] <= t1 + dt_max)
            idx = idx[ok]
            if idx.size == 0:
                continue
            pos = np.searchsorted(key, akey[idx])
            for i, p in zip(idx, pos):
                writer.writerow([day.strftime("%Y%m%d"), kind, sat, int(asat[i]), int(akey[i] // 1440), int(akey[i] % 1440),
                                 round(float(aspd[i]), 2), round(float(spd[p]), 2), int(cnt[p]),
                                 int(round(at[i] - tmid))])
                n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--dt", type=float, default=60.0)
    ap.add_argument("--out", default=os.path.join(HERE, "pairs.csv"))
    a = ap.parse_args()
    d = dt.datetime.strptime(a.start, "%Y%m%d").date()
    end = dt.datetime.strptime(a.end, "%Y%m%d").date()
    new = not os.path.exists(a.out)
    with open(a.out, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["day", "kind", "star_sat", "rss_sat", "iy", "ix", "rss_kt", "star_kt", "star_pts", "dt_min"])
        while d <= end:
            n = day_rows(d, a.dt, w)
            f.flush()
            print(d, n, flush=True)
            d += dt.timedelta(days=a.step)


if __name__ == "__main__":
    main()
