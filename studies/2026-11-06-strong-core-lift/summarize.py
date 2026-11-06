#!/usr/bin/env python3
"""Headline paired comparisons from final_case_counts.csv.gz (held-out weeks; whole-week 95% intervals).

Adds what score.py's paired table leaves out: the equal-area picks, and storm-tile CSI (catch with the false tiles
counted). -> headline_paired.csv"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import pandas as pd  # noqa: E402

from rk import compare  # noqa: E402

PAIRS = [("DS1_drill_L6_T44", "DG"), ("DS1_drill_L6_T44", "D"), ("DS1_drill_L8_T44", "DG"),
         ("EA_DS1_vs_DG", "DG"), ("DS1_drill_L6_T44", "CL"), ("EA_DS1_vs_CL", "CL"), ("EA_DS1_vs_CL8", "CL8"),
         ("EA_CLS1_vs_CL8", "CL8"), ("CLS1_drill_L8_T44", "CL8"), ("CLS1_drill_L6_T44", "CL")]
MET = {"storm_tile_catch": (["h48", "m48"], lambda c: c["h48"] / (c["h48"] + c["m48"])),
       "storm_tile_csi": (["h48", "m48", "fa48"], lambda c: c["h48"] / (c["h48"] + c["m48"] + c["fa48"])),
       "storm_area": (["fc48", "ob48"], lambda c: c["fc48"] / c["ob48"]),
       "gale_tile_csi": (["h34", "m34", "fa34"], lambda c: c["h34"] / (c["h34"] + c["m34"] + c["fa34"])),
       "gale_area": (["fc34", "ob34"], lambda c: c["fc34"] / c["ob34"]),
       "hf_cell_catch": (["cau64", "ob64"], lambda c: c["cau64"] / c["ob64"]),
       "hf_area": (["fc64", "ob64"], lambda c: c["fc64"] / c["ob64"])}
d = pd.read_csv(HERE / "final_case_counts.csv.gz", parse_dates=["cycle"])
CNT = sorted({k for v in MET.values() for k in v[0]})
out = []
for b in ("natl", "npac"):
    x = d[d.basin == b]
    for m, base in PAIRS:
        y = x[x["product"].isin([m, base])][["cycle", "step", "product"] + CNT]
        for name, (cols, f) in MET.items():
            r = compare.paired_counts(y, m, base, f, cols, method_col="product", case_cols=["step"])
            r.insert(0, "metric", name)
            r.insert(0, "basin", b)
            out.append(r)
res = pd.concat(out, ignore_index=True)
res.to_csv(HERE / "headline_paired.csv", index=False)
with pd.option_context("display.width", 200):
    print(res.round(3).to_string())
