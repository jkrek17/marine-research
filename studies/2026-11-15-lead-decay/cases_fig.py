#!/usr/bin/env python3
"""Worked cases: one valid time seen at four leads (design.md). Writes fig2_cases.png.

  python3 cases_fig.py

Shading: ASCAT seen water (light), ASCAT 48+ kt (orange) and 64+ kt (magenta). Outlines: storm line (Core Lifted
>= 39, navy) and HF line (strongest model >= 44 and 1%+ of members at 64 nearby, magenta dashed).
"""
import datetime as dt
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402
from scipy import ndimage  # noqa: E402

import score as M  # noqa: E402
import fit_score as F  # noqa: E402
from rk import basins, paths, style  # noqa: E402

CASES = [("natl", dt.datetime(2026, 3, 14, 12), (24, 48, 72, 96), "Atlantic, valid 12Z 14 Mar 2026"),
         ("npac", dt.datetime(2026, 2, 12, 6), (30, 54, 78), "Pacific, valid 06Z 12 Feb 2026")]


def panel(ax, basin, valid, step):
    cyc = valid - dt.timedelta(hours=step)
    p = paths.cache("extra", "most-likely-wind", basin) / ("%s_f%03d.npz" % (cyc.strftime("%Y%m%d%H"), step))
    d = M.load(p, basin)
    lats, lons = basins.grid(basin)
    seen = d["seen"] & d["ocean"] & np.isfinite(d["spd"])
    spd = np.where(seen, d["spd"], np.nan)
    cls = np.where(~seen, np.nan, np.where(spd >= 64, 3, np.where(spd >= 48, 2, 1)))
    style.map_axes(basin, ax=ax)
    ax.pcolormesh(lons, lats, cls, cmap=ListedColormap(["#e6ebf0", "#f08c3c", "#c2187a"]), vmin=0.5, vmax=3.5,
                  shading="nearest", zorder=1)
    opc = basins.opc_mask(basin) & d["ocean"]
    blend = d["base05"] + d["boost"]
    storm = (np.nan_to_num(F.corelift(blend, d["P"], d["Pg"]), nan=-1) >= M.STORM_KT) & opc
    ax.contour(lons, lats, storm.astype(float), [0.5], colors="#1d3557", linewidths=1.6, zorder=4)
    mx = np.fmax(np.fmax(d["gfs"], d["ifs"]), d["aifs"])
    p64 = M.p64_all(basin, cyc, step)
    if p64 is not None:
        hf = (mx >= M.HF_KT) & (ndimage.maximum_filter(p64, size=M.HF_NB, mode="nearest") >= M.HF_M64) & opc
        if hf.any():
            ax.contour(lons, lats, hf.astype(float), [0.5], colors="#b5179e", linewidths=1.4, linestyles="--",
                       zorder=5)
    ob48 = seen & (spd >= 48) & opc   # lines are scored inside the OPC High Seas area only
    ax.contour(lons, lats, basins.opc_mask(basin).astype(float), [0.5], colors="#7a7a74", linewidths=0.8,
               linestyles=":", zorder=4)
    cov = (ob48 & storm).sum() / max(ob48.sum(), 1)
    ax.set_title("%d h (run %s)  storm water in line %d%%" % (step, cyc.strftime("%HZ %d %b"), round(100 * cov)),
                 fontsize=9, loc="left")
    return ob48, lats, lons


def main():
    style.use()
    fig, axes = plt.subplots(2, 4, figsize=(17, 7.5))
    for r, (basin, valid, steps, label) in enumerate(CASES):
        boxes = []
        for c, st in enumerate(steps):
            ob48, lats, lons = panel(axes[r, c], basin, valid, st)
            if ob48.any():
                iy, ix = np.where(ob48)
                boxes.append((lats[iy].mean(), lons[ix].mean()))
        la, lo = np.mean(boxes, axis=0)
        for c in range(len(steps)):
            axes[r, c].set_xlim(lo - 22, lo + 22)
            axes[r, c].set_ylim(max(la - 11, 25), la + 11)
        for c in range(len(steps), 4):
            axes[r, c].axis("off")
        axes[r, 0].text(0, 1.16, label, transform=axes[r, 0].transAxes, fontsize=11, weight="bold")
    axes[1, 3].text(0.02, 0.6, "Shading: ASCAT seen water (grey),\nASCAT 48+ kt (orange), 64+ kt (magenta)\n\n"
                    "Navy: storm line (Core Lifted >= 39)\nMagenta dashed: HF line\nGrey dotted: OPC High Seas area edge\n(scored inside it only)", transform=axes[1, 3].transAxes,
                    fontsize=10, va="top")
    fig.suptitle("Same storm, earlier runs: the storm line drifts off the storm water and the HF line fades",
                 x=0.01, ha="left", fontsize=13)
    fig.tight_layout()
    fig.savefig(HERE / "fig2_cases.png", dpi=150, bbox_inches="tight", facecolor="#ffffff")   # PNG only: the SVG of the
    # ASCAT cell maps is ~60 MB


if __name__ == "__main__":
    main()
