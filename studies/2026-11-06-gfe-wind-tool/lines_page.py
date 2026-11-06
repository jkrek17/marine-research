#!/usr/bin/env python3
"""Re-score the storm warning line and HSF storm draft on the proposed page field (Jason 2026-11-06 19:31Z: replace
Core Lifted with ramp + HF core, "Yes, re-score lines first").

  python3 lines_page.py [--workers 4]

Products (tool_score.py page_make, page blend r10 + gale floor): CL (today's Core Lifted), PM_A36_U44 (ramps on
the stronger of GFS/ECMWF), PH_A36_U46_p30 (ramps + HF core where GEFS P48 >= 30%: the proposed field).
Line = open OPC water (rk.basins.opc_mask) where the product >= T, T = 33..50; scored as core-lift-bias lines.py
with rk.score.warning_events against ASCAT 48 kt, 60 nm reach. The HSF storm draft is drawn from the same
>= 39 kt line, so this scores it too. The gale and HF lines do not read Core Lifted and are unchanged.
Rule, set before held-out: the new line threshold is the highest T whose TUNE coverage is at least CL's at 39 kt
in that basin. Held-out at that T and at 39 kt, pooled and by valid hour (Pacific 06/18Z: ASCAT's main passes).
Writes lines_page_counts.csv.gz (per case) and lines_page_heldout.csv.
"""
import argparse
import multiprocessing as mp
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import tool_score as TS  # noqa: E402  (puts the repo and strong-core-lift on the path)

import pandas as pd  # noqa: E402

from rk import basins, score  # noqa: E402

PRODUCTS = ("CL", "PM_A36_U44", "PH_A36_U46_p30")
THRESH = tuple(range(33, 51))
TODAY = 39
KEYS = ("events", "hits", "obs_cells", "obs_in", "cells", "bad_cells", "warned_cells", "reach_cells")


def job(args):
    basin, cyc, step, path, split = args
    d = TS.S.prep(path)
    opc = basins.opc_mask(basin) & d["ocean"]
    rows = []
    fields = {p: TS.make(p, d, {}) for p in PRODUCTS}
    if any(f is None for f in fields.values()):
        return rows
    for name, f in fields.items():
        for T in THRESH:
            r = score.warning_events(f >= T, d["spd"], d["seen"], 48, mask=opc)
            rows.append(dict(basin=basin, cycle=cyc.isoformat(), step=step, split=split, vh=(cyc.hour + step) % 24,
                             product=name, T=T, **{k: r[k] for k in KEYS}))
    return rows


def pooled(df, by):
    s = df.groupby(by)[list(KEYS)].sum().reset_index()
    s["covered"] = s.obs_in / s.obs_cells
    s["area"] = s.cells / s.obs_cells
    s["caught"] = s.hits / s.events
    s["false_cells"] = s.bad_cells / s.cells
    return s


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    jobs = [(b, c, s, p, sp) for b in ("natl", "npac") for sp in ("tune", "held_out")
            for c, s, p in TS.S.load_cases(b, sp)]
    print("cases %d" % len(jobs), flush=True)
    rows = []
    with mp.get_context("spawn").Pool(a.workers) as pool:
        for i, r in enumerate(pool.imap_unordered(job, jobs, chunksize=4), 1):
            rows += r
    df = pd.DataFrame(rows)
    df.to_csv(TS.paths.data("extra", "gfe-wind-tool") / "lines_page_counts.csv.gz", index=False)
    s = pooled(df, ["split", "basin", "product", "T"])
    sv = pooled(df.assign(hours=df.vh.isin((6, 18)).map({True: "06/18Z", False: "00/12Z"})),
                ["split", "basin", "hours", "product", "T"])
    out = []
    for b in ("natl", "npac"):
        tune = s[(s.split == "tune") & (s.basin == b)]
        target = tune[(tune["product"] == "CL") & (tune["T"] == TODAY)].covered.iloc[0]
        for prod in PRODUCTS:
            t = tune[(tune["product"] == prod) & (tune.covered >= target - 1e-9)]
            T = int(t["T"].max())
            for TT, why in ((T, "same coverage as today's line (tune)"), (TODAY, "39 kt as today")):
                for hours, src in (("all", s), ("00/12Z", sv), ("06/18Z", sv)):
                    h = src[(src.split == "held_out") & (src.basin == b) & (src["product"] == prod) & (src["T"] == TT)]
                    if hours != "all":
                        h = h[h.hours == hours]
                    if h.empty:
                        continue
                    h = h.iloc[0]
                    out.append(dict(basin=b, hours=hours, product=prod, T=TT, why=why, covered=h.covered,
                                    area=h.area, caught=h.caught, events=int(h.events), false_cells=h.false_cells,
                                    reach_cells=int(h.reach_cells)))
    o = pd.DataFrame(out).drop_duplicates(["basin", "hours", "product", "T"])
    o.to_csv(HERE / "lines_page_heldout.csv", index=False)
    print(o.round(3).to_string())


if __name__ == "__main__":
    main()
