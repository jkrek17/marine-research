#!/usr/bin/env python3
"""Follow-up rows: how often the gap exists at all, and the gap defined on ECMWF 10 m or the #95 blend instead of GFS.
Reads analyze.py's cells.parquet (RK_CACHE); writes gap_variants.csv here."""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np, pandas as pd  # noqa: E402
import analyze as A  # noqa: E402

df = A.load()
rows = []
s9 = df.s925 >= 35
for lab, m in (("925>=35, sa>=5 (any 10 m)", s9 & (df.sa >= 5)),
               ("925>=35, sa>=8 (any 10 m)", s9 & (df.sa >= 8)),
               ("925>=35, sa<2 (any 10 m)", s9 & (df.sa < 2)),
               ("gap on GFS 10 m (study)", s9 & (df.gfs < 25) & (df.sa >= 5)),
               ("gap on ECMWF 10 m", s9 & (df.ifs < 25) & (df.sa >= 5)),
               ("gap on ECMWF 10 m, sa 8+", s9 & (df.ifs < 25) & (df.sa >= 8)),
               ("gap on #95 blend", s9 & (df.det < 25) & (df.sa >= 5)),
               ("Jason's case: 925>=40, GFS 10 m<20, sa>=8", (df.s925 >= 40) & (df.gfs < 20) & (df.sa >= 8)),
               ("Jason's case on ECMWF: 925>=40, ECMWF<20, sa>=8", (df.s925 >= 40) & (df.ifs < 20) & (df.sa >= 8))):
    for b in ("natl", "npac", "both"):
        g = df[m & ((df.basin == b) if b != "both" else True)]
        r = A.describe(g, lab) if len(g) else dict(group=lab, cells=0)
        if len(g):
            r.update(gfs_over_925=float(np.median(g.gfs / g.s925)), ifs_median=float(g.ifs.median()),
                     ifs_bias=float((g.ifs - g.asc).mean()), gfs_bias=float((g.gfs - g.asc).mean()),
                     share_of_all_cells=len(g) / len(df[(df.basin == b) if b != "both" else slice(None)]))
        rows.append(dict(basin=b, **r))
out = pd.DataFrame(rows)
out.to_csv(HERE / "gap_variants.csv", index=False, float_format="%.4f")
pd.set_option("display.width", 250)
print(out[["basin", "group", "cells", "cell_times", "cases", "gale_frac", "asc_median", "s925_median", "gfs_median", "ifs_median", "det_median",
           "gfs_bias", "ifs_bias", "det_bias", "ratio_p50", "gfs_over_925", "share_of_all_cells"]].to_string())
