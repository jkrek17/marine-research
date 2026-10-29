"""Desk column for check 3 (design.md): for each (basin, 12 UTC run, lead, ocean cell) the highest NDFD oceanic wind
(rk.desk, days 4-7 read) within 500 km of the cell at the valid time, from the desk issuance made from that run
(rk.desk.issue_for). NaN where the issuance or the valid time is missing or the posted file is unreadable.
Writes CACHE/extra/hf-d5-7-checks/desk.parquet. Run after build.py and the desk fill: python3 desk_join.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from rk import basins, bomb, desk, paths, score  # noqa: E402
import build  # noqa: E402

OUT = paths.cache("extra", "hf-d5-7-checks", "desk.parquet")


def footprints(basin):
    """Per ocean cell, the flat grid indices within NBR_KM."""
    lats, lons = basins.grid(basin)
    clat, clon = bomb.ocean_cells(basin, lats, lons)
    LA, LO = np.meshgrid(lats, lons, indexing="ij")
    la, lo = LA.ravel(), LO.ravel()
    return [np.flatnonzero(score.km(a, b, la, lo) <= build.NBR_KM) for a, b in zip(clat, clon)]


def main():
    t = pd.read_parquet(build.OUT, columns=["basin", "cycle", "lead", "cell", "valid"])
    rows = []
    for b in basins.BASINS:
        fp = footprints(b)
        for c, g in t[t.basin == b].groupby("cycle"):
            try:
                r = desk.load(desk.issue_for(b, c.to_pydatetime()), desk.DAYS47)
            except Exception as e:      # a truncated posted file (2026022401): left out, counted below
                print(b, c, "unreadable:", repr(e), flush=True)
                continue
            if r is None:
                continue
            valid = r[b]["valid"]
            for (L, v), h in g.groupby(["lead", "valid"]):
                if v.to_pydatetime() not in valid:
                    continue
                s = r[b]["speed"][valid.index(v.to_pydatetime())].astype(np.float32).ravel()
                with np.errstate(all="ignore"):
                    mx = np.array([np.nanmax(s[ix]) if np.isfinite(s[ix]).any() else np.nan for ix in fp])
                rows.append(pd.DataFrame({"basin": b, "cycle": c, "lead": L, "cell": h.cell.values,
                                          "desk_max": mx[h.cell.values]}))
            print(b, c, flush=True)
    d = pd.concat(rows, ignore_index=True)
    d.to_parquet(OUT, index=False)
    print(d.groupby(["basin", "lead"]).desk_max.agg(["size", "max", lambda x: (x >= 64).mean()]))


if __name__ == "__main__":
    main()
