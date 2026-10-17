"""Figures: motion-relative IR composites (HF, storm force, difference) per basin, and one example crop.

    python3 studies/2026-10-17-hf-satellite/figures.py "<finding for the composite title>"
"""
import sys

import matplotlib.pyplot as plt
import numpy as np

from common import HERE
from features import HALF
from rk import paths, style

FIG = HERE / "fig"


def main():
    finding = sys.argv[1] if len(sys.argv) > 1 else "Motion-relative IR composites"
    style.use()
    FIG.mkdir(exist_ok=True)
    z = np.load(paths.cache("extra", "hf-satellite", "composites.npz"))
    ext = [-HALF, HALF, -HALF, HALF]
    fig, axes = plt.subplots(2, 3, figsize=(11, 7.6), constrained_layout=True)
    names = {"natl": "Atlantic", "npac": "Pacific"}
    for i, b in enumerate(("natl", "npac")):
        hf, s = z[b + "_HF"] - 273.15, z[b + "_S"] - 273.15
        nh, ns = int(z[b + "_HF_n"].max()), int(z[b + "_S_n"].max())
        for j, (img, lab) in enumerate(((hf, "HF fixes (n=%d)" % nh), (s, "storm-force fixes (n=%d)" % ns))):
            im = axes[i, j].imshow(img, extent=ext, cmap="Greys", vmin=-60, vmax=10)
            axes[i, j].set_title("%s: %s" % (names[b], lab), fontsize=10)
        dm = axes[i, 2].imshow(hf - s, extent=ext, cmap="RdBu_r", vmin=-8, vmax=8)
        axes[i, 2].set_title("%s: HF minus storm force" % names[b], fontsize=10)
        for ax in axes[i]:
            ax.grid(False)
            ax.plot(0, 0, "+", color="#d62728", ms=10, mew=2)
            ax.set_xticks([-1000, 0, 1000])
            ax.set_yticks([-1000, 0, 1000])
            for r in (500, 1000):
                ax.add_patch(plt.Circle((0, 0), r, fill=False, lw=0.6, ls=":", color="#888"))
    axes[1, 0].set_xlabel("km right of track")
    axes[1, 0].set_ylabel("km along track (motion up)")
    fig.colorbar(im, ax=axes[:, :2], shrink=0.6, label="IR brightness temperature (C), cold = white")
    fig.colorbar(dm, ax=axes[:, 2], shrink=0.6, label="HF minus storm force (C); blue = colder at HF")
    fig.suptitle(finding, fontsize=12, fontweight="bold")
    style.save(fig, FIG / "composites.png")
    print("wrote", FIG / "composites.png")


if __name__ == "__main__":
    main()
