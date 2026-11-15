#!/usr/bin/env python3
"""fig1_decay: warning-line coverage and storm placement by lead (from lines_by_lead.csv, grid_by_lead.csv)."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from rk import style  # noqa: E402

LEADS = [24, 48, 72, 96, 120]
BASIN = {"natl": "Atlantic", "npac": "Pacific"}


def main():
    style.use()
    L = pd.read_csv(HERE / "lines_by_lead.csv")
    G = pd.read_csv(HERE / "grid_by_lead.csv")
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6))
    ax = axes[0]
    for b, ls in (("natl", "-"), ("npac", "--")):
        for line in ("gale", "storm", "hf"):
            if b == "npac" and line == "hf":
                continue   # one ASCAT HF event all winter
            s = L[(L.basin == b) & (L.line == line) & (L.lead <= 96)]
            ax.plot(s.lead, 100 * s.covered, ls, color=style.HAZARD_COLORS[line], marker="o", ms=4,
                    label="%s %s line" % (BASIN[b], line if line != "hf" else "HF"))
    ax.set_ylim(40, 100)
    ax.set_xticks(LEADS[:4])
    ax.set_xlabel("lead (h)")
    ax.set_ylabel("% of ASCAT water at the line's level inside it")
    ax.legend(fontsize=8, frameon=False, loc="lower left")
    style.title(ax, "Lines: storm and HF lose a quarter to a third by 96 h", "winter 2025-26, OPC areas, ASCAT")
    for k, b in enumerate(("natl", "npac")):
        ax = axes[k + 1]
        for prod in ("best", "blend", "gfs", "ifs", "aifs"):
            s = G[(G.basin == b) & (G["product"] == prod) & (G.lead <= 96)]
            ax.plot(s.lead, 100 * s.eq48, color=style.METHOD_COLORS.get(prod, "#1d3557" if prod == "best" else None),
                    lw=2.4 if prod == "best" else 1.4, marker="o", ms=4,
                    label={"best": "Best Wind", "blend": "blend", "gfs": "GFS", "ifs": "ECMWF", "aifs": "AIFS"}[prod])
        ax.set_ylim(0, 80)
        ax.set_xticks(LEADS[:4])
        ax.set_xlabel("lead (h)")
        ax.set_ylabel("% of ASCAT storm cells caught, grid at equal area")
        ax.legend(fontsize=8, frameon=False, loc="lower left")
        style.title(ax, "%s storm placement: about a third lost by 96 h" % BASIN[b] if b == "natl"
                    else "Pacific storm placement: half lost by 96 h", "equal-area catch at 48 kt (size taken out)")
    fig.tight_layout()
    style.save(fig, HERE / "fig1_decay")


if __name__ == "__main__":
    main()
