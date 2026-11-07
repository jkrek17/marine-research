"""Three-panel maps (blend, ramped blend, ASCAT) for the five worked cases, plus a numbers table.

    python3 reports/2026-11-07-best-wind/cases/figure.py
Needs the case files from build.py. Ramped blend = blend + ramps on the stronger of GFS/ECMWF
(0-6 kt over 36-40, 0-4 over 44-48), HF ramp 0-6 over 52-56 where GEFS P48 (box max) >= 30%,
open water at |lat| >= 25, then 34 kt where the gale-core chance >= 80% (as live since 7 Nov 2026).
"""
import csv
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))
from rk import basins, style  # noqa: E402
import build  # noqa: E402

M = build.bc()


def ramp(x, kt, start, width=4.0):
    return kt * np.clip((x - start) / width, 0.0, 1.0)


def grids(d, lats):
    blend = d["base05"] + d["boost"]
    strong = np.nan_to_num(np.fmax(d["gfs"], d["ifs"]), nan=-1.0)
    add = ramp(strong, 6, 36) + ramp(strong, 4, 44) + np.where(d["p48nb"] >= 0.30, ramp(strong, 6, 52), 0.0)
    on = d["ocean"] & (np.abs(lats)[:, None] >= 25)
    best = np.where(on, blend + add, blend)
    if "Pg" in d:
        best = np.where(d["Pg"] >= 0.80, np.maximum(best, 34.0), best)
    return blend, best


def window(d, lats, lons):
    seen = d["seen"] & d["ocean"]
    spd = np.where(seen, d["spd"], np.nan)
    r, c = np.unravel_index(np.nanargmax(spd), spd.shape)
    la, lo = lats[r], lons[c]
    return la, lo, (max(lats.min(), la - 10), min(lats.max(), la + 10), max(lons.min(), lo - 18), min(lons.max(), lo + 18))


def stats(f, d, box):
    seen = d["seen"] & d["ocean"] & box
    a = d["spd"][seen]
    v = f[seen]
    out = {"peak": float(np.nanmax(np.where(box & d["ocean"], f, np.nan)))}
    for t in (48, 64):
        n_a = int((a >= t).sum())
        out["asc%d" % t] = n_a
        out["hit%d" % t] = int(((a >= t) & (v >= t)).sum())
        out["fc%d" % t] = int((v >= t).sum())
    out["bias48"] = float(np.mean(v[a >= 48] - a[a >= 48])) if (a >= 48).any() else np.nan
    return out


def main():
    style.use()
    cmap, norm = style.wind_cmap(), style.wind_norm()
    rows = []
    for k, (basin, cycle, step) in enumerate(build.CASES, 1):
        z = np.load(M.out_path(basin, cycle, step))
        d = {n: (z[n].astype(np.float32) if z[n].dtype == np.float16 else z[n]) for n in z.files}
        lats, lons = basins.grid(basin)
        blend, best = grids(d, lats)
        la, lo, (s, n, w, e) = window(d, lats, lons)
        box = (lats[:, None] >= s) & (lats[:, None] <= n) & (lons[None] >= w) & (lons[None] <= e)
        valid = cycle + __import__("datetime").timedelta(hours=step)
        asc = np.where(d["seen"] & d["ocean"], d["spd"], np.nan)
        fig, axes = plt.subplots(1, 3, figsize=(13, 4.4))
        b = {"west": w, "east": e, "south": s, "north": n}
        sb, sr = stats(blend, d, box), stats(best, d, box)
        sa = float(np.nanmax(np.where(box, asc, np.nan)))
        for ax, f, name in ((axes[0], blend, "Blend: peak %.0f kt" % sb["peak"]),
                            (axes[1], best, "Ramped blend: peak %.0f kt" % sr["peak"]),
                            (axes[2], asc, "ASCAT (where seen): peak %.0f kt" % sa)):
            style.map_axes(b, ax=ax)
            m = ax.pcolormesh(lons, lats, np.where(d["ocean"], f, np.nan), cmap=cmap, norm=norm,
                              shading="nearest", zorder=1)
            if f is not asc:
                ax.contour(lons, lats, np.where(d["seen"] & d["ocean"], d["spd"], np.nan), levels=[48, 64],
                           colors=["#1f1f1d", "#b5179e"], linewidths=[1.2, 1.4], zorder=4)
            ax.set_title(name, loc="left", fontsize=10.5)
        style.wind_colorbar(fig, m, list(axes))
        basin_name = "Atlantic" if basin == "natl" else "Pacific"
        fig.suptitle("Case %d: %s, valid %s, forecast +%d h (run %s)" % (
            k, basin_name, valid.strftime("%HZ %d %b %Y"), step, cycle.strftime("%HZ %d %b")),
            x=0.06, y=1.06, ha="left", fontsize=12)
        fig.text(0.06, 1.0, "Black / magenta lines: ASCAT 48 / 64 kt where the satellite saw. Held-out week.",
                 fontsize=9, color=style.INK2)
        fig.savefig(HERE / ("case%d.png" % k), dpi=150, bbox_inches="tight", facecolor="#ffffff")  # PNG only: the SVG of a 0.25 deg map is ~25 MB
        plt.close(fig)
        rows.append({"case": k, "basin": basin_name, "valid": valid.isoformat(), "step": step,
                     "ascat_peak": round(sa, 1), "blend_peak": round(sb["peak"], 1), "ramped_peak": round(sr["peak"], 1),
                     "ascat48_cells": sb["asc48"], "blend48_hit": sb["hit48"], "ramped48_hit": sr["hit48"],
                     "blend48_cells": sb["fc48"], "ramped48_cells": sr["fc48"],
                     "ascat64_cells": sb["asc64"], "blend64_hit": sb["hit64"], "ramped64_hit": sr["hit64"],
                     "blend64_cells": sb["fc64"], "ramped64_cells": sr["fc64"],
                     "blend_bias_at_ascat48": round(sb["bias48"], 1), "ramped_bias_at_ascat48": round(sr["bias48"], 1)})
        print(rows[-1], flush=True)
    with open(HERE / "cases.csv", "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)


if __name__ == "__main__":
    main()
