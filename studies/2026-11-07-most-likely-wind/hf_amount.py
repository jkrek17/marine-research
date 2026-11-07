#!/usr/bin/env python3
"""Whole-winter HF amount and placement: tune + held-out weeks pooled (Jason 18:0xZ, "does best wind make enough HF").

  python3 hf_amount.py   -> hf_amount.csv

Reads hist_gfe_tune.npz and hist_gfe_held_out.npz (gfe_score.py). Per basin and grid: ASCAT 64 kt cells, the grid's
64 kt area over ASCAT's (cells), and equal-area catch at 64 (summarize.eq_area). Pooled because the held-out weeks
alone hold too few HF cells to judge area (held-out HF core On read 1.68x; whole winter 1.13x).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from summarize import DATA, eq_area  # noqa: E402

PRODUCTS = ("best", "gfe_best", "gfe_best_hf", "blend", "det")


def main():
    hs = {}
    for sp in ("tune", "held_out"):
        z = np.load(DATA / ("hist_gfe_%s.npz" % sp))
        for k, h in zip(z["keys"], z["hist"]):
            bn, _, pr = k.split("|")
            hs[(bn, pr)] = hs.get((bn, pr), 0) + h
    rows = []
    for (bn, pr), h in sorted(hs.items()):
        if pr not in PRODUCTS:
            continue
        cf = np.cumsum(h[0][::-1])[::-1]
        n64 = int(h[3].sum())
        T, ca = eq_area(h, 3)
        rows.append({"basin": bn, "product": pr, "ascat64_cells": n64, "area64": cf[64] / n64,
                     "eqT64": T, "eq_catch64": ca})
    pd.DataFrame(rows).round(3).to_csv(HERE / "hf_amount.csv", index=False)
    print(pd.DataFrame(rows).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
