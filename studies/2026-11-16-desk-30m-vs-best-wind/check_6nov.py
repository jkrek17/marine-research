#!/usr/bin/env python3
"""Continuity check: the 6 Nov tool-on-blend rows rescored with strong-core-lift's own score_job on the rebuilt held-out
cases (no page-core-chance requirement, so the case set is the 6 Nov one, not the common set of score.py).
  python3 check_6nov.py   -> check_6nov.csv beside the published final_summary.csv numbers"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parent / "2026-11-05-core-lift-bias"))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import score as S  # noqa: E402  (this study's score.py, for slc())
from rk import cases, paths  # noqa: E402

M = S.slc()
SPECS = [(k, (k, None, None, None)) for k in ("D", "SHs", "SHl", "SHe")]


def main():
    ref = pd.read_csv(paths.data("extra", "strong-core-lift", "final_summary.csv"))
    rows = []
    for basin in ("natl", "npac"):
        acc = {}
        for p in sorted(paths.cache("extra", "strong-core-lift", basin).glob("*_f*.npz")):
            if p.name.endswith(".tmp.npz"):
                continue
            tg, st = p.stem.split("_f")
            cyc = cases.parse(tg)
            if not cases.held_out(cyc):
                continue
            meta, labels, Mx, _ = M.score_job((basin, cyc, int(st), p, SPECS))
            for lab, r in zip(labels, Mx):
                a = acc.setdefault(lab, [0, np.zeros(len(M.COLS))])
                a[0] += 1
                a[1] += r
        for lab, (n, v) in acc.items():
            c = dict(zip(M.COLS, v))
            r = ref[(ref.basin == basin) & (ref["product"] == lab)].iloc[0]
            rows.append(dict(basin=basin, product=lab, cases_here=n, cases_6nov=int(r.n_cases),
                             storm_tile_catch=c["h48"] / (c["h48"] + c["m48"]), storm_tile_catch_6nov=r.pod48,
                             gale_area=c["fc34"] / c["ob34"], gale_area_6nov=r.area34,
                             storm_area=c["fc48"] / c["ob48"], storm_area_6nov=r.area48))
    out = pd.DataFrame(rows).round(4)
    out.to_csv(HERE / "check_6nov.csv", index=False)
    print(out.to_string())


if __name__ == "__main__":
    main()
