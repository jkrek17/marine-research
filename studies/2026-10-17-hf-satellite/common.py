"""Shared pieces of the HF satellite pilot: the case table (archive fixes with motion) and the split."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from rk import cases, truth  # noqa: E402
from rk.basins import inside  # noqa: E402
from rk.satellite import heading  # noqa: E402

SEASONS = (2024, 2025)            # season = year of its 1 June start
CATS = ("HF", "S", "DHF", "DS")


def season(t):
    return t.year if t.month >= 6 else t.year - 1


def fixes():
    """Archive fixes of the pilot seasons in the basin boxes -> DataFrame with basin, event_id, valid, lat,
    lon (0-360), hpa, category, head (motion heading from the neighbouring fixes, NaN for a one-fix event),
    split (held_out when the event's first fix is in a held-out week)."""
    out = []
    for b in ("natl", "npac"):
        a = truth.hf_archive(b)
        a = a[a["category"].isin(CATS)].copy()
        a["basin"] = b
        a["event_id"] = b + "_" + a["event_id"].astype(str)     # ids repeat across the two basin sheets
        a["season"] = [season(t) for t in a["valid"]]
        a = a[a["season"].isin(SEASONS)]
        a = a.sort_values(["event_id", "valid"]).drop_duplicates(["event_id", "valid"])
        heads = []
        for _, g in a.groupby("event_id", sort=False):
            la, lo = g["lat"].values, g["lon"].values
            for i in range(len(g)):
                i0, i1 = max(i - 1, 0), min(i + 1, len(g) - 1)
                heads.append(np.nan if i0 == i1 else heading(la[i0], lo[i0], la[i1], lo[i1]))
        a["head"] = heads
        first = a.groupby("event_id")["valid"].transform("min")
        a["split"] = [cases.split(t.to_pydatetime()) for t in first]
        a = a[inside(b, a["lat"].values, a["lon"].values)]
        out.append(a)
    d = pd.concat(out, ignore_index=True)
    d = d[d["valid"].dt.hour % 6 == 0]
    return d.reset_index(drop=True)
