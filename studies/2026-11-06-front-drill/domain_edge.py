"""Front drill: the old (before frontlib.COVERAGE_FULL_FROM) domain edge of WPC's coded bulletin.

    python3 domain_edge.py

Per 1-degree latitude band (25-70N), the easternmost Atlantic point (fronts and lows, longitude 250-360E) of each
analysis valid 2024-11-01 to 2026-07-31; the plain maximum over all analyses is "max_lon"; the edge is its 5-band running median (a stray
point or two beyond the edge do not move it: three warm-front points in July and September 2025 reach 13-16W at 55-57N)
then a 3-band running mean. Writes old_edge.csv next to this file (small,
committed; frontlib.old_edge reads it). Also prints the coverage-change search (easternmost point at 28-42N per day).
"""
import csv
import datetime as dt
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from rk import fronts  # noqa: E402

T0, T1 = dt.date(2024, 11, 1), dt.date(2026, 7, 31)


def one(d):
    best = {}
    allv = {}
    try:
        for a in fronts.day(d):
            pts = [(la, lo) for f in a["fronts"] for la, lo in zip(f["lat"], f["lon"])] + [(la, lo) for _, la, lo in a["lows"]]
            cur = {}
            for la, lo in pts:
                if 250.0 <= lo <= 360.0 and 25 <= la < 70:
                    b = int(np.floor(la))
                    cur[b] = max(cur.get(b, 0.0), float(lo))
            for b, lo in cur.items():
                allv.setdefault(b, []).append(lo)
    except Exception as e:
        print("day", d, "error", e, flush=True)
    return allv


def main():
    days = [T0 + dt.timedelta(days=i) for i in range((T1 - T0).days + 1)]
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(one, days))
    vals = {}
    for r in res:
        for b, v in r.items():
            vals.setdefault(b, []).extend(v)
    raw = np.array([max(vals[b]) if b in vals else np.nan for b in range(25, 70)])
    ok = np.isfinite(raw)
    q = np.interp(np.arange(45), np.where(ok)[0], raw[ok])
    pq = np.pad(q, 2, mode="edge")
    med = np.array([np.median(pq[i:i + 5]) for i in range(45)])       # kills a stray point or two
    sm = np.convolve(np.pad(med, 1, mode="edge"), np.ones(3) / 3, mode="valid")
    with open(HERE / "old_edge.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["lat_band_south", "max_lon", "edge_lon"])
        for i in range(45):
            w.writerow([25 + i, "%.1f" % raw[i], "%.1f" % sm[i]])
    for i in range(0, 45, 5):
        print(25 + i, "%.1f" % raw[i], "%.1f" % sm[i])


if __name__ == "__main__":
    main()
