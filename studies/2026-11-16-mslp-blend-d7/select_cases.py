"""Worked-case selection for the briefing (rule fixed in design.md "Worked cases"; operational form below).

Rule: per basin, per month Nov-Mar, the deepest analysed low (mean of the GFS and IFS analyses, < 1000 hPa,
3 deg inside the box, over open water) among all 00/12Z valid times; and per basin the largest day-5 model split
(12Z cycles, +120 h: for each GFS low deeper than 985 hPa, the distance to ECMWF's nearest low (< 1005 hPa), and the
same the other way round, kept only when within 1500 km so both runs have the same storm; the largest such distance).
Writes results/worked_cases.csv. Reads only the MSLP-only extract files and the Part B case files.
"""
import pickle, sys
from datetime import datetime, timedelta
from pathlib import Path
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
import numpy as np, pandas as pd
from rk import paths, score as rks

ROOT = paths.cache("extra", "mslp-blend-d7", "_root").parent
CASES = ROOT / "partb" / "cases"
OUT = HERE / "results" / "worked_cases.csv"


def km(a, b, c, d):
    return float(rks.km(a, b, c, d))


def scan():
    deep, split = [], []
    for basin in ("natl", "npac"):
        for p in sorted((ROOT / basin).glob("*.npz")):
            cyc = datetime.strptime(p.stem, "%Y%m%d%H")
            z = np.load(p)
            if "an_gfs_v024" in z.files and "an_ifs_v024" in z.files:
                an = (z["an_gfs_v024"] + z["an_ifs_v024"]) / 2
                mask = z["mask_v024"]
                from rk.basins import grid
                lats, lons = grid(basin)
                L = rks.find_lows(an.astype(np.float32), basin, below=1000.0, inset_deg=3.0)
                for _, r in L.iterrows():
                    iy, ix = np.abs(lats - r.lat).argmin(), np.abs(lons - r.lon).argmin()
                    if mask[iy, ix]:
                        deep.append(dict(basin=basin, valid=cyc + timedelta(hours=24), lat=r.lat, lon=r.lon, hpa=r.hpa))
                        break
            if cyc.hour == 12 and "gfs_f120" in z.files and "ifs_f120" in z.files and datetime(2025, 11, 1) <= cyc:
                Lg = rks.find_lows(z["gfs_f120"], basin, below=1005.0)
                Li = rks.find_lows(z["ifs_f120"], basin, below=1005.0)
                best = None
                for A, B, na, nb in ((Lg, Li, "gfs", "ifs"), (Li, Lg, "ifs", "gfs")):
                    for _, a in A[A.hpa < 985.0].iterrows():
                        if not len(B):
                            continue
                        d = np.array([km(a.lat, a.lon, b.lat, b.lon) for _, b in B.iterrows()])
                        j = int(d.argmin())
                        if d[j] <= 1500.0 and (best is None or d[j] > best["km"]):
                            b = B.iloc[j]
                            best = dict(km=float(d[j]), gfs_hpa=a.hpa if na == "gfs" else b.hpa, ifs_hpa=a.hpa if na == "ifs" else b.hpa,
                                        gfs_lat=a.lat if na == "gfs" else b.lat, gfs_lon=a.lon if na == "gfs" else b.lon,
                                        ifs_lat=a.lat if na == "ifs" else b.lat, ifs_lon=a.lon if na == "ifs" else b.lon)
                if best:
                    split.append(dict(basin=basin, cycle=cyc, **best))
    return pd.DataFrame(deep), pd.DataFrame(split)


def main():
    D, S = scan()
    D["month"] = D.valid.dt.month
    rows = []
    for (b, m), g in D[D.month.isin([11, 12, 1, 2, 3])].groupby(["basin", "month"]):
        r = g.sort_values("hpa").iloc[0]
        rows.append(dict(kind="deep", basin=b, valid=r.valid, cycle5=r.valid - timedelta(hours=120), lat=r.lat, lon=r.lon,
                         hpa=r.hpa, split_km=np.nan))
    for b, g in S.groupby("basin"):
        r = g.sort_values("km", ascending=False).iloc[0]
        rows.append(dict(kind="split", basin=b, valid=r.cycle + timedelta(hours=120), cycle5=r.cycle, lat=(r.gfs_lat + r.ifs_lat) / 2, lon=(r.gfs_lon + r.ifs_lon) / 2,
                         hpa=min(r.gfs_hpa, r.ifs_hpa), split_km=r.km))
    R = pd.DataFrame(rows)
    R["members"] = [c.hour == 12 for c in R.cycle5]
    R.to_csv(OUT, index=False)
    S.sort_values("km", ascending=False).groupby("basin").head(3).to_csv(HERE / "results" / "worked_split_top3.csv", index=False)
    print(R.to_string())
    print(S.sort_values("km", ascending=False).groupby("basin").head(3).to_string())


if __name__ == "__main__":
    main()
