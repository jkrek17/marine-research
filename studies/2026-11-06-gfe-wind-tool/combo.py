#!/usr/bin/env python3
"""Follow-up pick (Jason 2026-11-06 16:42Z: "best combo to be good at both storm and HF").

Rule, set before scoring held-out: on tune weeks, among two-step lifts (W_*) and S_L10_T44 whose gales pass (as in
analyze.py) and whose storm area <= 1.0x and storm-tile catch >= the main pick's (S_L6_T42) - 1 pt in BOTH basins,
take the highest Atlantic HF tile catch with Atlantic HF area <= 1.0x (Pacific HF too thin to pick on: 4 tune tiles).
  python3 combo.py --pick     tune -> combo_tune.csv, COMBO.json
  python3 combo.py --report   held-out (scored once) -> combo_heldout.csv
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze as A  # noqa: E402


def pool(split):
    d = pd.read_csv(A.DATA / ("rows_%s_combo.csv.gz" % split), parse_dates=["cycle"])
    keys = d[d["product"] == "D"][["basin", "cycle", "step"]]
    return A.pooled(d.merge(keys, on=["basin", "cycle", "step"]))


def pick():
    p = pool("tune")
    p.to_csv(HERE / "combo_tune.csv", index=False)
    ok = None
    for b in ("natl", "npac"):
        pb = p[p.basin == b].set_index("product")
        ref = pb.loc["S_L6_T42"]
        good = pb[A.passes(pb, pb.loc["D"]) & (pb.storm_area <= 1.0) & (pb.storm_catch >= ref.storm_catch - 0.01)]
        ok = set(good.index) if ok is None else ok & set(good.index)
    ok -= {"D", "S_L6_T42"}
    pa = p[(p.basin == "natl") & p["product"].isin(ok) & (p.hf_area <= 1.0)]
    best = pa.sort_values(["hf_tile_catch", "storm_catch"], ascending=False)
    print(best[["product", "storm_catch", "storm_area", "false_storm_tiles", "hf_tile_catch", "hf_area"]].round(3)
          .head(10).to_string())
    json.dump({"pick": None if best.empty else best.iloc[0]["product"]}, open(HERE / "COMBO.json", "w"))


def report():
    p = pool("held_out")
    p.to_csv(HERE / "combo_heldout.csv", index=False)
    c = ["basin", "product", "n_cases", "storm_catch", "storm_area", "false_storm_tiles", "h48", "m48",
         "hf_tile_catch", "hf_area", "h64", "m64", "fa64", "gale_csi", "gale_area"]
    print(p[c].round(3).to_string())


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pick", action="store_true")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    if a.pick:
        pick()
    if a.report:
        report()
