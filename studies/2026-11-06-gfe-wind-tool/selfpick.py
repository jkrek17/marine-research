#!/usr/bin/env python3
"""Follow-up picks (Jason 16:54Z: "simple tool to run on any model or blend"; "highest model, then the ramp above 42").

Families (tool_score.py --self): Q_B0 blend / Q_B1 GFS / Q_B2 ECMWF / Q_B3 stronger of GFS/ECMWF, each lifted by
ramps triggered by its own wind; Y = blend below, stronger model + ramps above. Rule per family, tune weeks: storm
area <= 1.0x in both basins and gale area <= 1.3x in both, then most mean storm-tile catch over the basins; ties to
Atlantic HF catch. Reference: the current tool R_L6_T40_M4_U50_W4_C1.
  python3 selfpick.py --pick     -> self_tune.csv, SELF.json
  python3 selfpick.py --report   held-out once -> self_heldout.csv
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import combo  # noqa: E402

FAM = {"blend": "Q_B0_", "GFS": "Q_B1_", "ECMWF": "Q_B2_", "stronger": "Q_B3_", "blend+stronger": "Y_"}
C = ["basin", "product", "n_cases", "storm_catch", "storm_area", "false_storm_tiles", "hf_tile_catch", "hf_area",
     "h64", "m64", "fa64", "gale_csi", "gale_area"]


def pick():
    p = combo.pool("tune")
    p.to_csv(HERE / "self_tune.csv", index=False)
    w = p.pivot_table(index="product", columns="basin", values=["storm_catch", "storm_area", "gale_area",
                                                                  "hf_tile_catch"])
    out = {}
    for name, pre in FAM.items():
        f = w[w.index.str.startswith(pre) & ~w.index.str.contains("A99")]
        f = f[(f["storm_area"].max(axis=1) <= 1.0) & (f["gale_area"].max(axis=1) <= 1.3)]
        if f.empty:
            out[name] = None
            continue
        f = f.assign(mc=f["storm_catch"].mean(axis=1), hf=f[("hf_tile_catch", "natl")])
        out[name] = f.sort_values(["mc", "hf"], ascending=False).index[0]
    json.dump(out, open(HERE / "SELF.json", "w"), indent=1)
    show = ["D", "R_L6_T40_M4_U50_W4_C1"] + [pre + "A99_U99" for pre in FAM.values() if pre != "Y_"]
    show += [v for v in out.values() if v]
    print(json.dumps(out))
    print(p[p["product"].isin(show)][C].round(3).to_string())


def report():
    p = combo.pool("held_out")
    p.to_csv(HERE / "self_heldout.csv", index=False)
    out = json.load(open(HERE / "SELF.json"))
    show = ["D", "R_L6_T40_M4_U50_W4_C1"] + [pre + "A99_U99" for pre in FAM.values() if pre != "Y_"]
    show += [v for v in out.values() if v]
    print(p[p["product"].isin(show)][C].round(3).to_string())


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pick", action="store_true")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    combo.SET = "self"
    if a.pick:
        pick()
    if a.report:
        report()
