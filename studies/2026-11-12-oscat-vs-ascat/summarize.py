"""Summary tables from pairs.csv (collocate.py output, kept outside git: RK_DATA or a scratch path).
Usage: python3 summarize.py PAIRS.csv -> results.csv beside this file."""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
d = pd.read_csv(sys.argv[1])
d["diff"] = d.star_kt - d.rss_kt
same = ((d.star_sat == 1) & (d.rss_sat == 2)) | ((d.star_sat == 2) & (d.rss_sat == 3))
sets = {"STAR high-res ASCAT, same Metop, |dt|<=30": d[(d.kind == "uhr") & same & (d.dt_min.abs() <= 30)]}
for w in (15, 30, 60):
    sets["OSCAT-3, |dt|<=%d" % w] = d[(d.kind == "oscat") & (d.dt_min.abs() <= w)]
rows = []
for name, x in sets.items():
    m = (x.rss_kt + x.star_kt) / 2
    for lo, hi in [(0, 20), (20, 34), (34, 48), (48, 99), (0, 99)]:
        s = x[(m >= lo) & (m < hi)]
        rows.append(dict(set=name, band="%d-%d" % (lo, hi) if hi < 99 else ("all" if lo == 0 else "%d+" % lo), n=len(s),
                         bias_kt=round(s["diff"].mean(), 2), sd_kt=round(s["diff"].std(), 2)))
    for t in (34, 48, 64):
        rows.append(dict(set=name, band="area>=%d" % t, n=int((x.rss_kt >= t).sum()),
                         star_cells=int((x.star_kt >= t).sum()),
                         ratio=round((x.star_kt >= t).sum() / max(1, (x.rss_kt >= t).sum()), 2)))
pd.DataFrame(rows).to_csv(os.path.join(HERE, "results.csv"), index=False)
print(pd.DataFrame(rows).to_string())
