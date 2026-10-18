"""Figures: motion-relative composites (HF, storm force, difference) per basin, tuning weeks only.

    python3 studies/2026-10-17-hf-satellite/figures.py "<finding>"                       # pilot IR
    python3 studies/2026-10-17-hf-satellite/figures.py --set full "<finding>"            # IR 2002-2026
    python3 studies/2026-10-17-hf-satellite/figures.py --set airmass "<finding>"         # air-mass RGB
"""
import argparse

import matplotlib.pyplot as plt
import numpy as np

from common import HERE
from features import HALF
from rk import paths, satellite, style

FIG = HERE / "fig"


NAMES = {"natl": "Atlantic", "npac": "Pacific"}


def _rings(ax):
    ax.grid(False)
    ax.plot(0, 0, "+", color="#d62728", ms=10, mew=2)
    ax.set_xticks([-1000, 0, 1000])
    ax.set_yticks([-1000, 0, 1000])
    for r in (500, 1000):
        ax.add_patch(plt.Circle((0, 0), r, fill=False, lw=0.6, ls=":", color="#888"))


def airmass(finding):
    """Air-mass RGB composites (RGB of the mean bands) and HF minus storm force in the green (ozone) term."""
    z = np.load(paths.cache("extra", "hf-satellite", "composites_airmass.npz"))
    ext = [-HALF, HALF, -HALF, HALF]
    fig, axes = plt.subplots(2, 3, figsize=(11, 7.6), constrained_layout=True)
    for i, b in enumerate(("natl", "npac")):
        rgb, oz, n = {}, {}, {}
        for cat in ("HF", "S"):
            bands = [z["%s_%s_%s" % (b, cat, k)] for k in ("b08", "b10", "b12", "b13")]
            rgb[cat] = np.nan_to_num(satellite.airmass_rgb(*bands), nan=1.0)
            oz[cat] = bands[2] - bands[3]
            n[cat] = int(z["%s_%s_n" % (b, cat)].max())
        for j, cat in enumerate(("HF", "S")):
            axes[i, j].imshow(rgb[cat], extent=ext)
            axes[i, j].set_title("%s: %s fixes (n=%d)" % (NAMES[b], "HF" if cat == "HF" else "storm-force", n[cat]),
                                 fontsize=10)
        dm = axes[i, 2].imshow(oz["HF"] - oz["S"], extent=ext, cmap="PuOr_r", vmin=-4, vmax=4)
        axes[i, 2].set_title("%s: HF minus storm, 9.6-10.3 um" % NAMES[b], fontsize=10)
        for ax in axes[i]:
            _rings(ax)
    axes[1, 0].set_xlabel("km right of track")
    axes[1, 0].set_ylabel("km along track (motion up)")
    fig.colorbar(dm, ax=axes[:, 2], shrink=0.6,
                 label="HF minus storm force, 9.6 - 10.3 um (K)\norange = more high cloud, purple = more dry ozone-rich air at HF")
    fig.suptitle(finding, fontsize=12, fontweight="bold")
    style.save(fig, FIG / "composites_airmass.png")
    fig.savefig(FIG / "composites_airmass.png", dpi=110, bbox_inches="tight", facecolor="#ffffff")   # noisy panels: keep < 1 MB
    print("wrote", FIG / "composites_airmass.png")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="pilot", choices=("pilot", "full", "airmass"))
    ap.add_argument("finding", nargs="?", default="Motion-relative composites")
    a = ap.parse_args()
    finding = a.finding
    style.use()
    FIG.mkdir(exist_ok=True)
    if a.set == "airmass":
        return airmass(finding)
    src, out = {"pilot": ("composites.npz", "composites.png"), "full": ("composites_full.npz", "composites_full.png")}[a.set]
    z = np.load(paths.cache("extra", "hf-satellite", src))
    ext = [-HALF, HALF, -HALF, HALF]
    fig, axes = plt.subplots(2, 3, figsize=(11, 7.6), constrained_layout=True)
    names = NAMES
    for i, b in enumerate(("natl", "npac")):
        hf, s = z[b + "_HF"] - 273.15, z[b + "_S"] - 273.15
        nh, ns = int(z[b + "_HF_n"].max()), int(z[b + "_S_n"].max())
        for j, (img, lab) in enumerate(((hf, "HF fixes (n=%d)" % nh), (s, "storm-force fixes (n=%d)" % ns))):
            im = axes[i, j].imshow(img, extent=ext, cmap="Greys", vmin=-60, vmax=10)
            axes[i, j].set_title("%s: %s" % (names[b], lab), fontsize=10)
        dm = axes[i, 2].imshow(hf - s, extent=ext, cmap="RdBu_r", vmin=-8, vmax=8)
        axes[i, 2].set_title("%s: HF minus storm force" % names[b], fontsize=10)
        for ax in axes[i]:
            _rings(ax)
    axes[1, 0].set_xlabel("km right of track")
    axes[1, 0].set_ylabel("km along track (motion up)")
    fig.colorbar(im, ax=axes[:, :2], shrink=0.6, label="IR brightness temperature (C), cold = white")
    fig.colorbar(dm, ax=axes[:, 2], shrink=0.6, label="HF minus storm force (C); blue = colder at HF")
    fig.suptitle(finding, fontsize=12, fontweight="bold")
    style.save(fig, FIG / out)
    print("wrote", FIG / out)


if __name__ == "__main__":
    main()
