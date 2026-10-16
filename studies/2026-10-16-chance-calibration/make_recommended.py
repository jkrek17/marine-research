"""Recommended page table and the page-vs-recommended comparison, from the saved report outputs.

    python3 make_recommended.py [--out DIR] [--page-json PATH]

34 kt: per-basin ASCAT-box curves (curves.json from `run_first_look.py report`). 48 kt: the shared ASCAT-box curve
(curves_shared.json, both basins' tune weeks added), same curve under natl and npac. 64 kt: copied unchanged from
the page's current file (too few hurricane-force cases to refit). The page's current file is read from
--page-json (default: calibration_page_current.json in the output folder, a copy of awips-tools
marine_wind/pipeline/calibration.json on origin/main).
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from rk import calibrate as C, paths  # noqa: E402

RAW_PCT = (5, 10, 20, 30, 50)
NOTE = ("Recommended chance calibration, winter 2025-26 hindcast vs ASCAT 3x3 box, pooled GEFS+ENS+AIFS ENS member share. "
        "34 kt: per basin. 48 kt: one shared curve fitted on both basins' tune weeks (same under natl and npac). "
        "64 kt: UNCHANGED from the current page file (too few hurricane-force cases to refit). Provisional, not yet agreed.")


def knots(d, thr, basin, g):
    c = d["thresholds"][str(thr)][basin][g]
    return c["raw"], c["cal"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(paths.DATA.parent / "chance-calibration" / "pooled"))
    ap.add_argument("--page-json", default=None)
    a = ap.parse_args()
    out = Path(a.out)
    page = json.load(open(a.page_json or out / "calibration_page_current.json"))
    per = json.load(open(out / "curves.json"))
    sh = json.load(open(out / "curves_shared.json"))
    r1 = lambda v: [round(float(x), 1) for x in v]  # noqa: E731
    curves = {}
    for basin in ("natl", "npac"):
        for g in C.LEAD_GROUPS:
            curves[(34, basin, g)] = tuple(map(r1, knots(per, 34, basin, g)))
            curves[(48, basin, g)] = tuple(map(r1, knots(sh, 48, basin, g)))
            curves[(64, basin, g)] = knots(page, 64, basin, g)
    C.to_page_json(curves, note=NOTE, path=out / "calibration_recommended.json")
    rec = json.load(open(out / "calibration_recommended.json"))
    rows = []
    for thr in (34, 48):
        for basin in ("natl", "npac"):
            for g in C.LEAD_GROUPS:
                rr, rc = knots(rec, thr, basin, g)
                if thr == 48:
                    pr, pc = knots(page, 48, basin, g)
                for x in RAW_PCT:
                    now = float(C.cal_at(x, *knots(page, 48, basin, g))) if thr == 48 else float(x)
                    rows.append(dict(thr=thr, basin=basin, lead=g, raw_share_pct=x, page_now_pct=round(now, 1),
                                     recommended_pct=round(float(C.cal_at(x, rr, rc)), 1),
                                     page_now_is="current calibration.json" if thr == 48 else "raw (no 34 kt table on the page)"))
    df = pd.DataFrame(rows)
    df.to_csv(out / "calibration_compare.csv", index=False)
    lines = ["| Chance | Basin | Lead | " + " | ".join("raw %d%%" % x for x in RAW_PCT) + " |", "|---|---|---|" + "---|" * len(RAW_PCT)]
    for (thr, basin, g), d in df.groupby(["thr", "basin", "lead"], sort=False):
        lines.append("| %s | %s | %s | %s |" % ("gale 34" if thr == 34 else "storm 48", {"natl": "Atlantic", "npac": "Pacific"}[basin],
                     {"le48": "+24/48", "72": "+72", "ge96": "+96/120"}[g],
                     " | ".join("%g to %g" % (r.page_now_pct, r.recommended_pct) for r in d.itertuples())))
    (out / "calibration_compare.md").write_text("Page now to recommended (percent), at each raw member share.\n\n" + "\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
