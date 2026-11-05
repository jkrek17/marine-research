#!/usr/bin/env python3
"""Held-out storm-tile catch and storm area by lead (final_by_lead.csv) -> storm_catch_by_lead.png/.svg."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from rk import style  # noqa: E402

PRODS = [("base", "Core Lifted today (+5 kt)", style.METHOD_COLORS["corelift"]),
         ("constL", "Bigger lift (+8 kt)", "#eb6834"),
         ("qmap_up", "Matched to ASCAT by lead", "#6250d6")]
GROUPS = ["d1", "d2", "d3", "d45"]
LABELS = ["Day 1", "Day 2", "Day 3", "Day 4-5"]


def main():
    style.use()
    d = pd.read_csv(HERE / "final_by_lead.csv")
    fig, axes = plt.subplots(2, 2, figsize=(10, 7), sharex=True)
    for j, (b, name) in enumerate((("natl", "Atlantic"), ("npac", "Pacific"))):
        for prod, lab, col in PRODS:
            g = d[(d.basin == b) & (d["product"] == prod)].set_index("group").loc[GROUPS]
            axes[0, j].plot(LABELS, 100 * g.pod48, "-o", color=col, label=lab)
            axes[1, j].plot(LABELS, g.area48, "-o", color=col, label=lab)
        axes[1, j].axhline(1.0, color="#e34948", lw=1, ls="--")
        axes[1, j].text(0, 1.03, "ASCAT's own area", color="#e34948", ha="left", fontsize=8)
        axes[0, j].set_ylim(0, 100)
        axes[1, j].set_ylim(0, 2)
        axes[0, j].set_title(name, loc="left", fontsize=11)
    axes[0, 0].set_ylabel("Storm-force tiles caught (%)")
    axes[1, 0].set_ylabel("Storm-force area / ASCAT's")
    axes[0, 0].legend(frameon=False, fontsize=8, loc="lower left")
    fig.suptitle("Core Lifted draws storm force over too little water; matching ASCAT catches more, mostly at day 4-5",
                 x=0.02, ha="left", fontsize=12)
    fig.text(0.02, 0.925, "Held-out weeks, winter 2025-26, ASCAT referee (all passes), 700 Atlantic / 630 Pacific forecasts",
             ha="left", fontsize=9, color="#5f5e5a")
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    style.save(fig, HERE / "storm_catch_by_lead")


if __name__ == "__main__":
    main()
