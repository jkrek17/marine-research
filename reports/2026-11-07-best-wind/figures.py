"""Figures for the Best Wind report. Every number comes from a committed study table;
the CSV beside each PNG lists them with their source.

    python3 reports/2026-11-07-best-wind/figures.py
"""
import csv
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from rk import style  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402

BEST = style.HAZARD_COLORS["storm"]
GFE = "#2b4a7a"


def ramp(x, a, b, size):
    return size * np.clip((x - a) / (b - a), 0, 1)


def fig_ramp():
    """How much Best Wind adds, as a function of the stronger of GFS and ECMWF."""
    x = np.linspace(30, 62, 641)
    page = ramp(x, 36, 40, 6) + ramp(x, 44, 48, 4)
    page_hf = page + ramp(x, 52, 56, 6)
    gfe = ramp(x, 38, 42, 6) + ramp(x, 48, 52, 4)
    gfe_hf = gfe + ramp(x, 52, 56, 6)
    style.use()
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    ax.plot(x, page_hf, color=BEST, lw=2, ls=(0, (4, 2)))
    ax.plot(x, page, color=BEST, lw=2)
    ax.plot(x, gfe_hf, color=GFE, lw=2, ls=(0, (4, 2)))
    ax.plot(x, gfe, color=GFE, lw=2)
    ax.text(45.2, 7.4, "page Best Wind", color=BEST, fontsize=9, ha="right")
    ax.text(49.6, 6.9, "GFE Make_BestWind", color=GFE, fontsize=9, ha="left")
    ax.text(57, 15.4, "with HF core (dashed;\nonly where its gate says so)", color=style.INK2, fontsize=8.5, ha="center")
    for lo, hi, lab in ((34, 48, "gale"), (48, 64, "storm")):
        ax.axvspan(lo, hi, color=style.HAZARD_COLORS[lab], alpha=0.06, lw=0)
    ax.set_xlim(30, 62)
    ax.set_ylim(0, 17)
    ax.set_xlabel("Stronger of GFS and ECMWF 10 m wind at the cell (kt)")
    ax.set_ylabel("Wind added to the blend (kt)")
    style.title(ax, "The lift ramps in with the stronger model: none below 36 kt, 10 kt above 48",
                "page: 0-6 kt over 36-40, 0-4 over 44-48; GFE: 38-42 and 48-52; HF core 0-6 over 52-56")
    png, _ = style.save(fig, HERE / "fig_ramp.png")
    with open(HERE / "fig_ramp.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["stronger_model_kt", "page_lift", "page_lift_hf", "gfe_lift", "gfe_lift_hf"])
        for v in range(30, 63):
            w.writerow([v, *(round(float(r), 2) for r in (
                ramp(v, 36, 40, 6) + ramp(v, 44, 48, 4),
                ramp(v, 36, 40, 6) + ramp(v, 44, 48, 4) + ramp(v, 52, 56, 6),
                ramp(v, 38, 42, 6) + ramp(v, 48, 52, 4),
                ramp(v, 38, 42, 6) + ramp(v, 48, 52, 4) + ramp(v, 52, 56, 6)))])
    return png


# Held-out storm and HF tile catch (%), Atlantic / Pacific.
# Page grids: studies/2026-11-07-most-likely-wind/findings.md, "The evidence" table.
# Make_BestWind: same file, "Follow-up: the GFE method" table (default settings).
CATCH = [
    ("Blend (page)", "blend", 28, 12, 2, 0),
    ("Core Lifted", "corelift", 62, 40, 16, 7),
    ("Best Wind (page)", "best", 74, 58, 61, 40),
    ("Make_BestWind (GFE)", "gfe", 75, 63, 57, 20),
]


def fig_catch():
    colors = {"blend": style.METHOD_COLORS["blend"], "corelift": style.METHOD_COLORS["corelift"],
              "best": BEST, "gfe": GFE}
    style.use()
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6), sharey=True)
    for ax, (cat, i) in zip(axes, (("Storm force (48 kt)", 2), ("Hurricane force (64 kt)", 4))):
        xs = np.arange(2)
        for j, row in enumerate(CATCH):
            vals = [row[i], row[i + 1]]
            bars = ax.bar(xs + (j - 1.5) * 0.2, vals, 0.19, color=colors[row[1]], label=row[0])
            for b, v in zip(bars, vals):
                ax.text(b.get_x() + b.get_width() / 2, v + 1.5, str(v), ha="center", fontsize=8, color=style.INK2)
        ax.set_xticks(xs, ["Atlantic", "Pacific"])
        ax.set_title(cat, loc="left", fontsize=11)
        ax.set_ylim(0, 90)
    axes[0].set_ylabel("ASCAT tiles caught (%)")
    axes[1].legend(loc="upper right", fontsize=8)
    fig.suptitle("Lifting the cores takes storm catch from about a quarter to about three quarters",
                 x=0.06, ha="left", fontsize=12)
    fig.text(0.06, 0.9, "held-out weeks, winter 2025-26, +24 to +126 h; 741 Atl / 181 Pac storm tiles, "
             "122 Atl / 15 Pac HF tiles; truth ASCAT", fontsize=9, color=style.INK2)
    fig.subplots_adjust(top=0.78)
    png, _ = style.save(fig, HERE / "fig_catch.png")
    with open(HERE / "fig_catch.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["grid", "storm_atl", "storm_pac", "hf_atl", "hf_pac", "source"])
        for row in CATCH:
            w.writerow([row[0], *row[2:], "studies/2026-11-07-most-likely-wind/findings.md"])
    return png


if __name__ == "__main__":
    print(fig_ramp(), fig_catch())
