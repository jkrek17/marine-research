"""Figures: motion-relative composites (HF, storm force, difference) per basin, tuning weeks only.

    python3 studies/2026-10-17-hf-satellite/figures.py "<finding>"                       # pilot IR
    python3 studies/2026-10-17-hf-satellite/figures.py --set full "<finding>"            # IR 2002-2026
    python3 studies/2026-10-17-hf-satellite/figures.py --set full --atl-west 30 "<finding>"   # Atlantic west of 30W
    python3 studies/2026-10-17-hf-satellite/figures.py --set full --atl-west 30 --atl-max-lat 55 "<finding>"   # and both basins south of 55N
    python3 studies/2026-10-17-hf-satellite/figures.py --set airmass "<finding>"         # air-mass RGB
    python3 studies/2026-10-17-hf-satellite/figures.py --set airmass --max-vza 65 "<finding>"   # away from the disc edge
"""
import argparse

import matplotlib.pyplot as plt
import numpy as np

from common import HERE
from features import HALF, RES
from features_airmass import BANDS
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


def airmass_near(max_vza):
    """Air-mass composites over every week (a picture, nothing is fitted) of the fixes the satellite sees within
    max_vza degrees of view angle at the centre, away from the disc edge -> same keys as composites_airmass.npz."""
    import pandas as pd
    d = pd.read_csv(HERE / "features_airmass.csv", parse_dates=["valid"])
    d = d[(d.status == "ok") & (d.am_status == "ok") & d.category.isin(["HF", "S"]) & (d.am_vza <= max_vza)]
    sums, storms = {}, {}
    for _, f in d.iterrows():
        b = satellite.airmass_box(f["basin"], f["valid"].to_pydatetime(), download=False)
        head = None if np.isnan(f["head"]) else float(f["head"])
        c = {k: satellite.crop({"lat": b["lat"], "lon": b["lon"], "tb": b[k]}, f["lat"], f["lon"], HALF, RES, head)
             for k in BANDS}
        ok = np.all([np.isfinite(c[k]) for k in BANDS], 0)
        k = (f["basin"], f["category"])
        s, n = sums.get(k, ({k_: np.zeros(ok.shape) for k_ in BANDS}, np.zeros(ok.shape)))
        for k_ in BANDS:
            s[k_][ok] += c[k_][ok]
        n[ok] += 1
        sums[k] = (s, n)
        storms.setdefault(k, set()).add(f["event_id"])
    z = {}
    for (b, cat), (s, n) in sums.items():
        for k_ in BANDS:
            z["%s_%s_%s" % (b, cat, k_)] = np.where(n > 0, s[k_] / np.maximum(n, 1), np.nan)
        z["%s_%s_n" % (b, cat)] = n
        z["%s_%s_storms" % (b, cat)] = len(storms[(b, cat)])
    return z


def airmass(finding, max_vza=None):
    """Air-mass RGB composites (RGB of the mean bands) and HF minus storm force in the green (ozone) term."""
    if max_vza:
        z, out = airmass_near(max_vza), "composites_airmass_vza%d.png" % max_vza
    else:
        z, out = np.load(paths.cache("extra", "hf-satellite", "composites_airmass.npz")), "composites_airmass.png"
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
            st = z.get("%s_%s_storms" % (b, cat))
            axes[i, j].set_title("%s: %s fixes (n=%d%s)" % (NAMES[b], "HF" if cat == "HF" else "storm-force", n[cat],
                                 ", %d storms" % st if st else ""), fontsize=10)
        dm = axes[i, 2].imshow(oz["HF"] - oz["S"], extent=ext, cmap="PuOr_r", vmin=-4, vmax=4)
        axes[i, 2].set_title("%s: HF minus storm, 9.6-10.3 um" % NAMES[b], fontsize=10)
        for ax in axes[i]:
            _rings(ax)
    axes[1, 0].set_xlabel("km right of track")
    axes[1, 0].set_ylabel("km along track (motion up)")
    fig.colorbar(dm, ax=axes[:, 2], shrink=0.6,
                 label="HF minus storm force, 9.6 - 10.3 um (K)\norange = more high cloud, purple = more dry ozone-rich air at HF")
    fig.suptitle(finding, fontsize=12, fontweight="bold")
    style.save(fig, FIG / out)
    fig.savefig(FIG / out, dpi=110, bbox_inches="tight", facecolor="#ffffff")   # noisy panels: keep < 1 MB
    print("wrote", FIG / out)


def full_west(atl_west, max_lat=None):
    """IR composites 2002-2026 (tuning weeks, status ok, HF and S) recomputed from the boxes, with Atlantic fixes
    kept only at lon <= 360 - atl_west (Pacific unchanged) and, with max_lat, fixes of BOTH basins only at
    lat < max_lat (latitude-matched) -> same keys as composites_full.npz plus _storms, and the counts of fixes cut
    per basin and of fixes skipped for a missing box."""
    import pandas as pd
    d = pd.read_csv(paths.data("hf-satellite") / "features_full.csv", parse_dates=["valid"])
    d = d[(d.status == "ok") & (d.split == "tune") & d.category.isin(["HF", "S"])]
    keep = (d.basin != "natl") | (d.lon <= 360 - atl_west)
    if max_lat is not None:
        keep &= d.lat < max_lat
    cut, d = d[~keep].groupby("basin").size().to_dict(), d[keep]
    sums, storms, missing = {}, {}, 0
    for (basin, t), g in d.groupby(["basin", "valid"]):
        b = satellite.box(basin, t.to_pydatetime(), download=False)
        if b is None:
            missing += len(g)
            continue
        for _, f in g.iterrows():
            head = None if np.isnan(f["head"]) else float(f["head"])
            c = satellite.crop(b, f["lat"], f["lon"], HALF, RES, head)
            k = (basin, f["category"])
            s, n = sums.get(k, (np.zeros(c.shape), np.zeros(c.shape)))
            ok = np.isfinite(c)
            s[ok] += c[ok]
            n[ok] += 1
            sums[k] = (s, n)
            storms.setdefault(k, set()).add(f["event_id"])
    z = {}
    for (b, cat), (s, n) in sums.items():
        z["%s_%s" % (b, cat)] = np.where(n > 0, s / np.maximum(n, 1), np.nan)
        z["%s_%s_n" % (b, cat)] = n
        z["%s_%s_storms" % (b, cat)] = len(storms[(b, cat)])
    return z, cut, missing


def ir(z, finding, out, dpi=None):
    """IR composites (HF, storm force, HF minus storm force) per basin from composites_full.npz-style keys."""
    ext = [-HALF, HALF, -HALF, HALF]
    fig, axes = plt.subplots(2, 3, figsize=(12.5, 7.6), constrained_layout=True)
    for i, b in enumerate(("natl", "npac")):
        hf, s = z[b + "_HF"] - 273.15, z[b + "_S"] - 273.15
        for j, (img, cat) in enumerate(((hf, "HF"), (s, "S"))):
            n, st = int(z["%s_%s_n" % (b, cat)].max()), z.get("%s_%s_storms" % (b, cat))
            lab = "%s fixes (n=%d%s)" % ("HF" if cat == "HF" else "storm-force", n, ", %d storms" % st if st else "")
            im = axes[i, j].imshow(img, extent=ext, cmap="Greys", vmin=-60, vmax=10)
            axes[i, j].set_title("%s: %s" % (NAMES[b], lab), fontsize=9)
        dm = axes[i, 2].imshow(hf - s, extent=ext, cmap="RdBu_r", vmin=-8, vmax=8)
        axes[i, 2].set_title("%s: HF minus storm force" % NAMES[b], fontsize=10)
        for ax in axes[i]:
            _rings(ax)
    axes[1, 0].set_xlabel("km right of track")
    axes[1, 0].set_ylabel("km along track (motion up)")
    fig.colorbar(im, ax=axes[:, :2], shrink=0.6, label="IR brightness temperature (C), cold = white")
    fig.colorbar(dm, ax=axes[:, 2], shrink=0.6, label="HF minus storm force (C); blue = colder at HF")
    fig.suptitle(finding, fontsize=12, fontweight="bold")
    style.save(fig, FIG / out)
    if dpi:
        fig.savefig(FIG / out, dpi=dpi, bbox_inches="tight", facecolor="#ffffff")   # keep < 1 MB
        (FIG / out).with_suffix(".svg").unlink(missing_ok=True)
    print("wrote", FIG / out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="pilot", choices=("pilot", "full", "airmass"))
    ap.add_argument("--max-vza", type=float, default=None, help="airmass only: fixes seen within this view angle")
    ap.add_argument("--atl-west", type=float, default=None,
                    help="full only: Atlantic fixes west of this longitude (degrees W) only, recomputed from the boxes")
    ap.add_argument("--atl-max-lat", type=float, default=None,
                    help="with --atl-west: fixes of both basins south of this latitude only (latitude-matched)")
    ap.add_argument("finding", nargs="?", default="Motion-relative composites")
    a = ap.parse_args()
    finding = a.finding
    style.use()
    FIG.mkdir(exist_ok=True)
    if a.set == "airmass":
        return airmass(finding, a.max_vza and int(a.max_vza))
    if a.set == "full" and a.atl_west is not None:
        z, cut, missing = full_west(a.atl_west, a.atl_max_lat)
        print("fixes cut per basin: %s; fixes skipped, box not in cache: %d" % (cut, missing))
        for k in sorted(z):
            if k.endswith("_n") or k.endswith("_storms"):
                print(k, int(np.max(z[k])))
        out = "composites_full_w%d%s.png" % (a.atl_west, "_s%d" % a.atl_max_lat if a.atl_max_lat is not None else "")
        return ir(z, finding, out, dpi=110)
    src, out = {"pilot": ("composites.npz", "composites.png"), "full": ("composites_full.npz", "composites_full.png")}[a.set]
    ir(np.load(paths.cache("extra", "hf-satellite", src)), finding, out)


if __name__ == "__main__":
    main()
