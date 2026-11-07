#!/usr/bin/env python3
"""Two figures from the held-out tables (bands_heldout.csv, catch_heldout.csv, paired_heldout.csv).
  fig1_tradeoff.png  decision-cell MAE vs storm-tile catch, per basin
  fig2_own_band.png  bias by the grid's own band (does the grid mean what it says)"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from rk import style  # noqa: E402

LABEL = {"gfs": "GFS", "ifs": "ECMWF", "aifs": "AIFS", "blend": "Blend", "blend_a1": "Blend, AIFS full",
         "CL": "Core Lifted", "best": "Best Wind", "best_x0.5": "Ramps x0.5", "best_x1.5": "Ramps x1.5",
         "best_a1": "Best, AIFS full", "best_s+2": "Ramps 2 kt later", "best_s-2": "Ramps 2 kt earlier",
         "best_x2": "Ramps x2"}
BASIN = {"natl": "Atlantic", "npac": "Pacific"}


def main():
    style.use()
    b = pd.read_csv(HERE / "bands_heldout.csv")
    c = pd.read_csv(HERE / "catch_heldout.csv")
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.6))
    for ax, bn in zip(axs, ("natl", "npac")):
        d = b[(b.basin == bn) & (b.cut == "dec")].set_index("product")["mae"]
        k = c[c.basin == bn].set_index("product")["tile_catch48"]
        for p, lab in LABEL.items():
            hot = p in ("best",)
            ax.scatter(d[p], 100 * k[p], s=60 if hot else 30, color=style.HAZARD_COLORS["storm"] if hot else style.INK,
                       zorder=3)
            off = {"best_s+2": (-8, -12), "best_a1": (5, -11), "best": (6, 5)}.get(p, (5, 3))
            ha = "right" if p == "best_s+2" else "left"
            ax.annotate(lab, (d[p], 100 * k[p]), xytext=off, textcoords="offset points", fontsize=8, ha=ha)
        ax.set_xlabel("Mean abs error vs ASCAT where anything shows 30+ kt (kt)")
        ax.set_ylabel("ASCAT storm tiles caught (%)")
        ax.set_title(BASIN[bn], loc="left")
    fig.suptitle("Lower error and more storm catch pull against each other\n"
                 "held-out weeks, winter 2025-26, +24 to +126 h; left is closer to ASCAT, up catches more storm tiles",
                 x=0.06, ha="left", fontsize=11, y=1.04)
    style.save(fig, HERE / "fig1_tradeoff.png")

    fig, axs = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    bands = ["<30", "30-47", "48-63"]
    for ax, bn in zip(axs, ("natl", "npac")):
        d = b[(b.basin == bn) & (b.cut == "fc")]
        for i, p in enumerate(["blend", "CL", "best", "best_x0.5"]):
            v = d[d["product"] == p].set_index("band").reindex(bands)["bias"]
            ax.bar([j + (i - 1.5) * 0.2 for j in range(3)], v, 0.2, label=LABEL[p],
                   color=["#8a8a85", "#2b4a7a", style.HAZARD_COLORS["storm"], "#c98500"][i])
        ax.axhline(0, color=style.INK, lw=0.8)
        ax.set_xticks(range(3))
        ax.set_xticklabels(["grid < 30 kt", "grid 30-47", "grid 48-63"])
        ax.set_title(BASIN[bn], loc="left")
    axs[0].set_ylabel("Grid minus ASCAT (kt)")
    axs[1].legend(frameon=False, fontsize=8)
    fig.suptitle("Where Best Wind shows storm force, ASCAT averages 5-7 kt less\n"
                 "bias sorted by the grid's own value, held-out weeks", x=0.06, ha="left", fontsize=11, y=1.04)
    style.save(fig, HERE / "fig2_own_band.png")


if __name__ == "__main__":
    main()
