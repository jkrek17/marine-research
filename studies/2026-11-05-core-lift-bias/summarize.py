#!/usr/bin/env python3
"""Recompute the held-out tables from final_case_counts.csv (no new scoring): paired differences against Core
Lifted and against the constant lift, the verdict lines of FINAL_CHOICE.json, the by-lead table and the figure.

  python3 summarize.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import pandas as pd  # noqa: E402

import fit_score as F  # noqa: E402


def main():
    df = pd.read_csv(HERE / "final_case_counts.csv")
    ch = json.load(open(HERE / "FINAL_CHOICE.json"))
    prods = [p for p in df["product"].unique() if p != "base"]
    pr = pd.concat([F.paired(df, prods, "base"), F.paired(df, ["qmap_up"], "constL")], ignore_index=True)
    pr = pr.rename(columns={"method": "product_value", "baseline": "vs_value"})
    pr.to_csv(HERE / "final_paired.csv", index=False)
    summ = F.pooled(df, ["basin", "product"])
    lines = []
    for b, g in summ.groupby("basin"):
        base = g[g["product"] == "base"].iloc[0]
        for prod in ("qmap_up", "constL", "leadL"):
            r = g[g["product"] == prod].iloc[0]
            d = pr[(pr.basin == b) & (pr["product"] == prod) & (pr.vs == "base") & (pr.metric == "pod48")].iloc[0]
            c = g[g["product"] == "constL"].iloc[0]
            l1 = d["diff"] >= 0.05 and d["lo"] > 0
            l2 = r.area48 <= F.STORM_AREA_CAP
            l3 = r.area34 <= max(F.GALE_AREA_CAP, base.area34 + 0.01) and r.csi34 >= base.csi34 - F.GALE_CSI_TOL
            l4 = (r.pod48 - c.pod48 >= 0.02) if prod == "qmap_up" else None
            lines.append({"basin": b, "product": prod, "storm_catch": r.pod48, "gain": d["diff"], "lo": d["lo"],
                          "hi": d["hi"], "line1": l1, "storm_area": r.area48, "line2": l2, "line3": l3,
                          "vs_constL": r.pod48 - c.pod48, "line4": l4,
                          "false_storm_tiles": int(r.fa48), "base_false_storm_tiles": int(base.fa48)})
    v = pd.DataFrame(lines)
    v.to_csv(HERE / "final_verdict.csv", index=False)
    print(v.round(3).to_string())
    bl = F.pooled(df, ["basin", "group", "product"])
    bl = bl[bl["product"].isin(["base", "constL", "qmap_up"])]
    bl[["basin", "group", "product", "nt48", "pod48", "far48", "area48", "catch48", "ob48", "csi34", "area34"]].round(3).to_csv(
        HERE / "final_by_lead.csv", index=False)
    print(bl[["basin", "group", "product", "pod48", "far48", "area48", "ob48"]].round(3).to_string())
    print("choice:", ch["candidate"])


if __name__ == "__main__":
    main()
