#!/usr/bin/env python3
"""Held-out products with the gap read the way Make_BestWind would see it: 10 m test on the #95 blend (or ECMWF)
instead of GFS. Grid: max(blend, 34) in gap cells. Warning: line 30 (strongest of GFS/ECMWF) OR gap.
Cell counts at ASCAT-seen cells, pooled over held-out cases. Writes gap_blend_products.csv."""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np, pandas as pd  # noqa: E402
import analyze as A  # noqa: E402
from rk import features  # noqa: E402

df = A.load().dropna(subset=["det", "ifs"])
df = df[df.split == "held_out"]
ob = df.asc.to_numpy() >= 34
det, strong = df.det.to_numpy(), np.fmax(df.gfs.to_numpy(), df.ifs.to_numpy())
rows = []
for gname, ten in (("gap on blend", df.det), ("gap on ECMWF", df.ifs), ("gap on GFS", df.gfs)):
    for sa in (5.0, 8.0):
        g = features.mixdown_gap(df.s925.to_numpy(), ten.to_numpy(), df.sa.to_numpy(), sea_air_c=sa)
        for b in ("natl", "npac"):
            mb = (df.basin == b).to_numpy()
            gl = g & mb
            new_grid = gl & (det < 34)                  # cells the grid lift turns to gale
            new_warn = gl & (strong < 30)               # cells the trigger adds to the warning area
            rows.append(dict(gap=gname, sa_min=sa, basin=b, gap_cells=int(gl.sum()), gap_gale=float(ob[gl].mean()) if gl.any() else np.nan,
                             grid_new_cells=int(new_grid.sum()), grid_new_hits=int((new_grid & ob).sum()),
                             grid_blend_gale_cells=int(((det >= 34) & mb).sum()), ascat_gale_cells=int((ob & mb).sum()),
                             blend_hits=int(((det >= 34) & ob & mb).sum()),
                             warn_new_cells=int(new_warn.sum()), warn_new_hits=int((new_warn & ob).sum()),
                             line30_cells=int(((strong >= 30) & mb).sum()), line30_hits=int(((strong >= 30) & ob & mb).sum()),
                             line30_misses=int(((strong < 30) & ob & mb).sum())))
out = pd.DataFrame(rows)
out["grid_new_hit_rate"] = out.grid_new_hits / out.grid_new_cells
out["warn_new_hit_rate"] = out.warn_new_hits / out.warn_new_cells
out["warn_catch_gain_pts"] = 100 * out.warn_new_hits / out.ascat_gale_cells
out["warn_area_gain_pct"] = 100 * out.warn_new_cells / out.line30_cells
out.to_csv(HERE / "gap_blend_products.csv", index=False, float_format="%.4f")
# reference: the hit rate of the cells a lower line (28 kt) would add, to compare like with like
for b in ("natl", "npac"):
    mb = (df.basin == b).to_numpy()
    add = mb & (strong >= 28) & (strong < 30)
    print(b, "line 28 adds", int(add.sum()), "cells, hit rate %.3f" % ob[add].mean(), "catch +%.2f pts" % (100 * (add & ob).sum() / (ob & mb).sum()))
pd.set_option("display.width", 250)
print(out.to_string())
