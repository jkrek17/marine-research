"""Figures for the desk added value write-up, from the tables in results/.

    python3 studies/2026-10-16-desk-value/figures.py
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from rk import style  # noqa: E402

RES = HERE / "results"


def storm_catch():
    """Atlantic winter: share of ASCAT 48+ kt cells each method caught, by day."""
    m = pd.read_csv(RES / "by_method.csv")
    m = m[(m.period == "janmar") & (m["class"] == "all") & (m.truth == "ascat")
          & (m.basin == "natl") & (m.leadday <= 5)]
    fig, ax = plt.subplots(figsize=(7, 4))
    for meth in ["desk", "gfs", "ifs", "aifs", "mean3", "blend"]:
        r = m[m.method == meth].sort_values("leadday")
        style.method_line(ax, r.leadday, 100 * r.pod48, meth, marker="o")
    r = m[m.method == "prev12"].sort_values("leadday")
    ax.plot(r.leadday, 100 * r.pod48, color=style.INK2, dashes=(2, 2), label="Previous grid")
    ax.set_xlabel("Forecast day")
    ax.set_ylabel("ASCAT 48+ kt cells caught (%)")
    ax.set_xticks(range(1, 6))
    ax.set_ylim(0, 70)
    ax.legend(ncol=2)
    style.title(ax, "The desk catches storm force the models smooth away",
                "Atlantic OPC areas, 14 Jan - 31 Mar 2026, 146 issuances, truth ASCAT")
    return style.save(fig, RES / "storm_catch_atlantic")


def class_gain():
    """Desk minus automatic update and minus blend, by page class, Atlantic winter."""
    p = pd.read_csv(RES / "paired.csv")
    p = p[(p.period == "janmar") & (p.metric == "mae25") & (p.basin == "natl")
          & (p.leadday <= 5)]
    classes = ["ride", "agree", "focus", "high impact"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    for ax, base, label in [(axes[0], "auto12", "automatic update"),
                            (axes[1], "blend", "blend")]:
        for i, c in enumerate(classes):
            r = p[(p.baseline == base) & (p["class"] == c)].sort_values("leadday")
            x = r.leadday + (i - 1.5) * 0.12
            col = ["#7a7974", "#5683b5", "#c98500", "#d9480f"][i]
            ax.errorbar(x, r["mean"], yerr=[r["mean"] - r.lo, r.hi - r["mean"]],
                        fmt="o", color=col, label=c.capitalize(), capsize=0, lw=1.2)
        ax.axhline(0, color=style.SPINE, lw=1)
        ax.set_xticks(range(1, 6))
        ax.set_xlabel("Forecast day")
        ax.set_title(f"Desk minus {label}", loc="left", fontsize=10)
    axes[0].set_ylabel("Change in wind error at 25+ kt (kt)\nbelow 0 = desk closer to ASCAT")
    axes[0].set_ylim(-4, 4)
    axes[1].legend(title="Page class", ncol=2)
    fig.subplots_adjust(top=0.80)
    fig.suptitle("Shifts beat an automatic update in ride water, not in focus; the blend beats "
                 "the desk except in high-impact water", x=0.01, y=0.99, ha="left", fontsize=11)
    fig.text(0.01, 0.91, "Atlantic OPC areas, 14 Jan - 31 Mar 2026, 95% intervals from whole weeks",
             fontsize=9, color=style.INK2)
    return style.save(fig, RES / "class_gain_atlantic")


if __name__ == "__main__":
    style.use()
    for f in (storm_catch(), class_gain()):
        print(*f)
