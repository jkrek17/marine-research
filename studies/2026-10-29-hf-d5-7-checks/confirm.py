"""ASCAT confirmation of each archive HF storm (design.md, truth T2).

For every archive HF fix from FIRST to LAST, the largest RSS ASCAT real 10 m wind (rain-free, open water, Metop-B/C
intercalibrated: rk.truth.ascat) within RADIUS_KM of the fix and +-DT_MIN of its time. Every pass time counts, so the
Pacific's 18 and 00 UTC passes and the Atlantic's are all used. A storm is confirmed when any of its HF fixes has
ASCAT >= 64 kt there; it is unseen when ASCAT saw no cell within the radius at any of its fixes.
Writes results/fixes_ascat.csv (one row per fix) and results/storms.csv (one row per storm).
Run: python3 confirm.py [FIRST LAST]   (dates, default 20250301 20260601)
"""
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from rk import basins, score, truth  # noqa: E402

RADIUS_KM = 300.0
DT_MIN = 180
HF_KT = 64.0
RES = HERE / "results"


def fix_rows(basin, first, last):
    a = truth.hf_archive(basin)
    a = a[(a.category == "HF") & (a.valid >= first) & (a.valid < last)]
    return a[basins.inside(basin, a.lat.values, a.lon.values)].reset_index(drop=True)


def ascat_near(basin, t, lat, lon):
    """(largest ASCAT kt within RADIUS_KM, number of cells seen there); (nan, 0) when nothing seen, None when no file."""
    a = truth.ascat(basin, t, max_dt_min=DT_MIN)
    if a is None:
        return None
    d = score.km(lat, lon, np.asarray(a["lat"], float), np.asarray(a["lon"], float) % 360)
    k = d <= RADIUS_KM
    if not k.any():
        return float("nan"), 0
    return float(np.max(np.asarray(a["spd_kt"], float)[k])), int(k.sum())


def main():
    a, b = (sys.argv[1:3] + ["20250301", "20260601"][len(sys.argv[1:3]):])
    first, last = dt.datetime.strptime(a, "%Y%m%d"), dt.datetime.strptime(b, "%Y%m%d")
    rows = []
    for basin in ("natl", "npac"):
        for r in fix_rows(basin, first, last).itertuples():
            t = pd.Timestamp(r.valid).to_pydatetime()
            got = ascat_near(basin, t, r.lat, r.lon)
            rows.append({"basin": basin, "event_id": r.event_id, "valid": t, "lat": r.lat, "lon": r.lon,
                         "hpa": r.hpa, "posted": got is not None,
                         "ascat_max_kt": np.nan if got is None else got[0],
                         "ascat_cells": 0 if got is None else got[1]})
            print(basin, r.event_id, t, rows[-1]["ascat_max_kt"], flush=True)
    f = pd.DataFrame(rows)
    RES.mkdir(exist_ok=True)
    f.to_csv(RES / "fixes_ascat.csv", index=False, float_format="%.2f")
    g = f.groupby(["basin", "event_id"])
    s = pd.DataFrame({"fixes": g.size(), "first": g.valid.min(), "last": g.valid.max(), "hpa_min": g.hpa.min(),
                      "posted_fixes": g.posted.sum(), "seen_fixes": g.ascat_cells.apply(lambda x: int((x > 0).sum())),
                      "ascat_max_kt": g.ascat_max_kt.max()}).reset_index()
    s["status"] = np.where(s.ascat_max_kt >= HF_KT, "confirmed", np.where(s.seen_fixes > 0, "seen_below", "unseen"))
    s.to_csv(RES / "storms.csv", index=False, float_format="%.2f")
    print(s.groupby(["basin", "status"]).size().unstack(fill_value=0))


if __name__ == "__main__":
    main()
