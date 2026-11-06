#!/usr/bin/env python3
"""Follow-up picks (Jason 18:56Z: move the ramp lift to the web page? better than Core Lifted? with the ensembles?).

Products: tool_score.py --page (page blend r10 + ramps, page gale floor kept). Rule per family, set before held-out,
as selfpick.py: tune weeks, storm area <= 1.0x in both basins and gale area <= 1.3x in both, then most mean
storm-tile catch over the basins; ties to Atlantic HF catch. Families: PM (stronger-model trigger), PO (page blend's
own wind), PE (PM x core likelihood), PG (PM where core likelihood >= p). HF add-ons (PK 925 x stability gate,
PH GEFS P48 gate): most Atlantic HF tile catch with Atlantic HF area <= 1.7x (the GFE HF core's level) among those
that also pass the storm rule. References: CL (page today), CL8 (+8 kt in cores), the GFE tool on the #95 blend.
  python3 pagepick.py --pick     -> page_tune.csv, PAGE.json
  python3 pagepick.py --report   held-out once -> page_heldout.csv
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import combo  # noqa: E402

FAM = {"stronger-model ramp": "PM_", "own-wind ramp": "PO_", "ramp x core likelihood": "PE_",
       "ramp where core likelihood": "PG_"}
HF = {"HF core, 925 x stability gate": "PK_", "HF core, GEFS P48 gate": "PH_"}
REFS = ["D", "CL", "CL8", "R_L6_T40_M4_U50_W4_C1"]
C = ["basin", "product", "n_cases", "storm_catch", "storm_area", "false_storm_tiles", "hf_tile_catch", "hf_area",
     "h64", "m64", "fa64", "gale_csi", "gale_area"]


def table(p):
    return p.pivot_table(index="product", columns="basin", values=["storm_catch", "storm_area", "gale_area",
                                                                    "hf_tile_catch", "hf_area"])


def pick():
    p = combo.pool("tune")
    p.to_csv(HERE / "page_tune.csv", index=False)
    w = table(p)
    ok = w[(w["storm_area"].max(axis=1) <= 1.0) & (w["gale_area"].max(axis=1) <= 1.3)]
    ok = ok.assign(mc=ok["storm_catch"].mean(axis=1), hf=ok[("hf_tile_catch", "natl")])
    out = {}
    for name, pre in FAM.items():
        f = ok[ok.index.str.startswith(pre)]
        out[name] = None if f.empty else f.sort_values(["mc", "hf"], ascending=False).index[0]
    for name, pre in HF.items():
        f = ok[ok.index.str.startswith(pre) & (ok[("hf_area", "natl")] <= 1.7)]
        out[name] = None if f.empty else f.sort_values(["hf", "mc"], ascending=False).index[0]
    json.dump(out, open(HERE / "PAGE.json", "w"), indent=1)
    print(json.dumps(out, indent=1))
    print(p[p["product"].isin(REFS + [v for v in out.values() if v])][C].round(3).to_string())


def report():
    p = combo.pool("held_out")
    p.to_csv(HERE / "page_heldout.csv", index=False)
    out = json.load(open(HERE / "PAGE.json"))
    print(p[p["product"].isin(REFS + [v for v in out.values() if v])][C].round(3).to_string())


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pick", action="store_true")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    combo.SET = "page"
    if a.pick:
        pick()
    if a.report:
        report()
