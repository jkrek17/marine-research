"""Render two demo figures with the house style. Usage: python3 tools/style_demo.py OUT_DIR"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from rk import style
from rk.basins import BASINS


def lead_chart(out):
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    leads = np.arange(24, 121, 24)
    base = {"gfs": 4.2, "ecmwf": 3.7, "aifs": 3.9, "blend": 3.5, "corelift": 3.3}
    for m, b in base.items():
        key = "ifs" if m == "ecmwf" else m
        y = b + 0.022 * (leads - 24) + (0.2 if m == "gfs" else 0)
        style.method_line(ax, leads, y, key)
        ax.annotate(style.METHOD_LABELS[key], (leads[-1], y[-1]), xytext=(6, 0),
                    textcoords="offset points", va="center", fontsize=9, color=style.METHOD_COLORS[key])
    ax.set_xticks(leads); ax.set_xlim(20, 138)
    ax.set_xlabel("Lead time (h)"); ax.set_ylabel("Wind MAE where 25+ kt (kt)")
    style.title(ax, "Core Lifted has the lowest error at every lead",
                "142 cases, Nov 2025-Mar 2026, N Atlantic 12 UTC (synthetic)")
    style.save(fig, Path(out) / "lead_chart.png")


def wind_map(out):
    b = BASINS["natl"]
    lat = np.arange(b["north"], b["south"] - 0.01, -0.5)
    lon = np.arange(b["west"], b["east"] + 0.01, 0.5)
    X, Y = np.meshgrid(lon, lat)
    w = 70 * np.exp(-(((X - 322) / 11) ** 2 + ((Y - 50) / 6) ** 2) / 2)
    fig, ax = style.map_axes("natl")
    cs = ax.pcolormesh(X, Y, w, cmap=style.wind_cmap(), norm=style.wind_norm(), zorder=1, shading="auto")
    for name, thr in style.HAZARD_THRESHOLDS.items():
        ax.contour(X, Y, w, levels=[thr], colors=style.HAZARD_COLORS[name], linewidths=2, zorder=4)
    from matplotlib.lines import Line2D
    ax.legend(handles=[Line2D([], [], color=style.HAZARD_COLORS[n], lw=2, label=f"{n.upper() if n == 'hf' else n.capitalize()} {t} kt")
                       for n, t in style.HAZARD_THRESHOLDS.items()], loc="lower left", frameon=True,
              facecolor="#ffffff", edgecolor=style.SPINE, framealpha=0.9, fontsize=8).set_zorder(6)
    style.wind_colorbar(fig, cs, ax)
    style.title(ax, "Synthetic low with 34, 48 and 64 kt contours", "Gaussian 0-70 kt, N Atlantic")
    style.save(fig, Path(out) / "wind_map.png")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "style_demo_out"
    style.use()
    lead_chart(out); wind_map(out)
    print("wrote", out)
