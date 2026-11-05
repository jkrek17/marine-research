"""Figures for the desk value beyond storm and HF write-up, from results/ (summarize.py).

    python3 studies/2026-11-05-desk-value-bands/figures.py
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from rk import style  # noqa: E402

RES = HERE / "results"
BASIN = {"natl": "Atlantic", "npac": "Pacific"}
# page wind colours (rk.style.WIND_COLORS), the darker shade of each band so lines read on white
BANDS = [("<20", "Under 20 kt", "#7aa0c9"), ("20-33", "20-33 kt", "#2b5fa8"), ("34-47", "Gale 34-47 kt", "#e8a93f")]
SITS = [("open ocean", "Open ocean"), ("coastal", "Within 100 nm of land or ice"), ("away from lows", "Away from lows"),
        ("near low", "Within 500 km of a low"), ("stable", "Warm air over cooler sea"),
        ("cold air", "Cold air over warmer sea")]
PERIOD = "13 Jan - 31 Mar 2026, OPC areas"


def zero(ax, horizontal=True):
    (ax.axhline if horizontal else ax.axvline)(0, color=style.INK2, lw=1)


def by_day(d):
    """Desk minus blend error by day and band, ASCAT (top) and analysis (bottom), both basins."""
    d = d[(d.vs == "blend") & (d.subset == "all") & (d.band_by == "blend") & (d.situation == "all")
          & (d.day != "1-3")].copy()
    d["day"] = d.day.astype(int)
    fig, axes = plt.subplots(2, 2, figsize=(10, 7.2), sharex=True, sharey=True)
    for j, b in enumerate(("natl", "npac")):
        for i, t in enumerate(("ascat", "anl")):
            ax = axes[i, j]
            zero(ax)
            for k, (band, lab, col) in enumerate(BANDS):
                r = d[(d.basin == b) & (d.truth == t) & (d.band == band)].sort_values("day")
                r = r[r.n >= 2000]
                x = r.day + (k - 1) * 0.1
                ax.errorbar(x, r["diff"], yerr=[r["diff"] - r.lo, r.hi - r["diff"]], color=col, marker="o",
                            ms=5, lw=2, capsize=0, elinewidth=5, alpha=0.9, label=lab)
            ax.set_xticks(range(1, 6))
            ax.set_ylim(-0.6, 4.2)
            tt = "ASCAT" if t == "ascat" else "analysis"
            ax.set_title(f"{BASIN[b]}, against {tt}", loc="left", fontsize=11)
            if j == 0:
                ax.set_ylabel("Desk error minus blend error (kt)")
            if i == 1:
                ax.set_xlabel("Forecast day")
    axes[0, 0].text(5.4, -0.45, "below 0: desk closer", ha="right", fontsize=8, color=style.INK2)
    axes[0, 0].legend(loc="upper left", ncol=3, fontsize=9)
    fig.suptitle("Below storm force the blend is closer than the desk on every day", x=0.06, ha="left",
                 fontsize=13, color=style.INK)
    fig.text(0.06, 0.935, f"{PERIOD}; wind band = what the blend said; bars = 95% range over weeks",
             fontsize=9, color=style.INK2)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return style.save(fig, RES / "gap_by_day")


def by_situation(d):
    """Desk minus blend error, days 1-3, ASCAT, by situation and band."""
    d = d[(d.vs == "blend") & (d.subset == "all") & (d.band_by == "blend") & (d.day == "1-3")
          & (d.truth == "ascat")]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.6), sharey=True, sharex=True)
    for j, b in enumerate(("natl", "npac")):
        ax = axes[j]
        zero(ax, horizontal=False)
        for k, (band, lab, col) in enumerate(BANDS):
            for i, (s, _) in enumerate(SITS):
                r = d[(d.basin == b) & (d.band == band) & (d.situation == s)]
                if r.empty or r.n.iloc[0] < 2000:
                    continue
                r = r.iloc[0]
                y = i + (1 - k) * 0.22
                ax.plot([r.lo, r.hi], [y, y], color=col, lw=5, alpha=0.45, solid_capstyle="butt")
                ax.plot(r["diff"], y, "o", color=col, ms=6, label=lab if i == 0 else None)
        ax.set_yticks(range(len(SITS)))
        ax.set_yticklabels([s[1] for s in SITS])
        ax.invert_yaxis()
        ax.set_title(BASIN[b], loc="left", fontsize=11)
        ax.set_xlabel("Desk error minus blend error (kt)")
        ax.grid(axis="y", visible=False)
    axes[1].legend(loc="lower right", fontsize=9)
    fig.suptitle("The desk falls furthest behind near lows and in cold air", x=0.02, ha="left", fontsize=13,
                 color=style.INK)
    fig.text(0.02, 0.915, f"Days 1-3 against ASCAT, {PERIOD}; right of 0 = blend closer", fontsize=9,
             color=style.INK2)
    fig.tight_layout(rect=(0, 0, 1, 0.91))
    return style.save(fig, RES / "gap_by_situation")


def gale(g):
    """Gale catch against gale area, days 1-3, ASCAT: desk at 34 kt, the blend drawn at 26-34 kt."""
    g = g[(g.subset == "all") & (g.truth == "ascat") & (g.situation == "all") & (g.day == "1-3")]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.4), sharey=True)
    for j, b in enumerate(("natl", "npac")):
        ax = axes[j]
        r = g[g.basin == b]
        bl = r[r.method.str.startswith("blend")].copy()
        bl["thr"] = bl.method.str[5:].replace("", "34").astype(int)
        bl = bl.sort_values("thr")
        ax.plot(bl.area_ratio, 100 * bl.caught, color=style.METHOD_COLORS["blend"], marker="o", ms=4,
                label="Blend drawn at 26-34 kt")
        for _, q in bl.iterrows():
            if q.thr in (26, 30, 34):
                ax.annotate(f"{q.thr}", (q.area_ratio, 100 * q.caught), textcoords="offset points",
                            xytext=(6, -10), fontsize=8, color=style.METHOD_COLORS["blend"])
        dk = r[r.method == "desk"].iloc[0]
        ax.errorbar(dk.area_ratio, 100 * dk.caught, xerr=[[dk.area_ratio - dk.ratio_lo], [dk.ratio_hi - dk.area_ratio]],
                    yerr=[[100 * (dk.caught - dk.caught_lo)], [100 * (dk.caught_hi - dk.caught)]],
                    color=style.METHOD_COLORS["desk"], marker="s", ms=7, elinewidth=1.5, capsize=0,
                    label="Desk at 34 kt")
        ax.set_title(BASIN[b], loc="left", fontsize=11)
        ax.set_xlabel("Gale area drawn / gale area ASCAT saw")
        if j == 0:
            ax.set_ylabel("ASCAT gale cells caught (%)")
        ax.set_ylim(50, 100)
    axes[0].legend(loc="lower right", fontsize=9)
    fig.suptitle("Desk gale catch vs the blend drawn lower", x=0.02, ha="left", fontsize=13, color=style.INK)
    fig.text(0.02, 0.915, f"Days 1-3, cells against ASCAT, {PERIOD}", fontsize=9, color=style.INK2)
    fig.tight_layout(rect=(0, 0, 1, 0.91))
    return style.save(fig, RES / "gale_trade")


def main():
    style.use()
    d = pd.read_csv(RES / "diff.csv")
    g = pd.read_csv(RES / "gale.csv")
    for f in (by_day(d), by_situation(d), gale(g)):
        print(f)


if __name__ == "__main__":
    main()
