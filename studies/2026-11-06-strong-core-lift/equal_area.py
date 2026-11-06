#!/usr/bin/env python3
"""Add equal-area picks to FINAL_CHOICE.json, from the tune weeks only, before --final (design.md run notes).

The win-line pick takes the most storm-tile catch under the 1.5x area cap, so it rides the cap. To compare at the
same drawn storm area, for each basin this picks the S1 parameters (lift L, switch T) whose TUNE storm area
(fc48/ob48) is nearest a reference product's tune area, among parameters that pass the gale part of the line:
  EA_CLS1_vs_CL8   page:  CLS1 at CL8's area   (is a strong-model switch a better +8 kt?)
  EA_DS1_vs_DG     GFE:   DS1 at the GEFS lift's area
  EA_DS1_vs_CL     GFE:   DS1 at today's Core Lifted's area (can GFE match the page without members?)
  EA_DS1_vs_CL8    GFE:   DS1 at +8 kt Core Lifted's area
Refuses once FINAL_RUN.json exists."""
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
if (HERE / "FINAL_RUN.json").exists():
    raise SystemExit("FINAL_RUN.json exists: equal-area picks must be made before the held-out run")
ch = json.load(open(HERE / "FINAL_CHOICE.json"))
sel = pd.read_csv(HERE / "tune_selection.csv")
summ = pd.read_csv(HERE / "tune_summary.csv").set_index(["basin", "product"])
REFS = {"EA_CLS1_vs_CL8": ("CLS1", "CL8"), "EA_DS1_vs_DG": ("DS1", "DG"), "EA_DS1_vs_CL": ("DS1", "CL"),
        "EA_DS1_vs_CL8": ("DS1", "CL8")}
for b in ("natl", "npac"):
    ea = {}
    for label, (kind, ref) in REFS.items():
        r = summ.loc[(b, ref)]
        target = r["fc48"] / r["ob48"]
        x = sel[(sel.basin == b) & (sel.kind == kind) & (sel.csi34_change >= -0.01)].copy()
        x["gap"] = (x.area48 - target).abs()
        best = x.sort_values(["gap", "pod48"], ascending=[True, False]).iloc[0]
        L, T = (int(v) for v in best["product"].split("_L")[1].split("_T"))
        ea[label] = dict(kind=kind, L=L, T=T, a=None, name=best["product"], ref=ref, ref_area48=round(float(target), 3),
                         area48=round(float(best.area48), 3), pod48=round(float(best.pod48), 3))
        print(b, label, ea[label])
    ch[b]["equal_area"] = ea
json.dump(ch, open(HERE / "FINAL_CHOICE.json", "w"), indent=1)
