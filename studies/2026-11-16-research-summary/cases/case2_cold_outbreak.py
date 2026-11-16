#!/usr/bin/env python3
"""Case 2, "30 m desk practice nearly doubles the gale area": North Atlantic, 12Z 10 Dec 2025 run, +24 h, valid 12Z 11 Dec.

  python3 case2_cold_outbreak.py

Picked from the held-out +24 h North Atlantic forecasts with 300+ ASCAT gale cells (61 cases both basins; 51 North
Atlantic with 300+ ASCAT gale cells in the rescore's case_picks.csv.gz): the one whose desk-practice gale-area ratio is
nearest the median. Panels: ASCAT | Best Wind (page, 80% floor) | desk practice (30 m stability wind on GFS and ECMWF,
averaged) | right / missed / too much at 34 kt for desk practice (ASCAT-seen cells). Writes case2_cold_outbreak.png/.pdf/.md to RK_SUMMARY_OUT.
"""
import datetime as dt

import numpy as np
import pandas as pd
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch

import cases_common as C
from rk import basins, paths, style

BASIN, CYC, STEP = "natl", dt.datetime(2025, 12, 10, 12), 24
RIGHT, MISS, OVER = "#7fb88f", style.DIV_LOW, style.DIV_HIGH


def pick_check():
    """Atlantic held-out +24 h cases (rescore case_picks.csv.gz) with 300+ ASCAT gale cells: the one whose desk practice
    (sh_avg) gale-area ratio is nearest the median; a tie goes to the case with more ASCAT gale cells."""
    r = pd.read_csv(paths.REPO / "studies" / "2026-11-16-desk-30m-vs-best-wind" / "case_picks.csv.gz")
    r = r[(r.basin == BASIN) & (r.step == STEP) & (r.ascat_cellsob34 >= 300)].dropna(subset=["gale_area__sh_avg"]).copy()
    med = r.gale_area__sh_avg.median()
    r["gap"] = (r.gale_area__sh_avg - med).abs().round(3)
    best = r.sort_values(["gap", "ascat_cellsob34"], ascending=[True, False]).iloc[0]
    assert pd.Timestamp(best.cycle) == pd.Timestamp(CYC), best.cycle
    return med, len(r), best


def main():
    style.use()
    med, n_nat, row = pick_check()
    pa, pb = C.ensure_case(BASIN, CYC, STEP)
    R = C.rescore()
    d = R.load(BASIN, CYC, STEP)
    P, common = R.products(d)
    assert common
    sh = P["sh_avg"]            # desk practice
    desk = P["avg10"]           # its base: GFS and ECMWF 10 m averaged
    seen = d["seen"] & d["ocean"] & np.isfinite(d["spd"])
    asc = np.where(seen, d["spd"], np.nan)
    z = lambda f: np.nan_to_num(np.where(seen, f, np.nan), nan=-1)
    area = C.cell_area_nm2(BASIN)
    lats, _ = basins.grid(BASIN)
    o34 = z(asc) >= 34
    prods = {"ASCAT": asc, "Plain blend": P["blend"], "Best Wind": P["best"], "GFS+ECMWF mean 10 m": desk, "Desk practice": sh}
    st = {}
    for k, f in prods.items():
        st[k] = dict(a34=C.area_k(z(f) >= 34, area), c34=int((z(f) >= 34).sum()), peak=float(np.nanmax(np.where(seen, f, np.nan))),
                     a48=C.area_k(z(f) >= 48, area))
    A = st["ASCAT"]
    ratio = {k: v["c34"] / A["c34"] for k, v in st.items()}   # cell counts, as the studies score it
    aratio = {k: v["a34"] / A["a34"] for k, v in st.items()}
    # verdict at 34 kt for the stability wind on seen cells
    f34 = z(sh) >= 34
    right, missed, over = seen & f34 & o34, seen & ~f34 & o34, seen & f34 & ~o34
    vcls = np.full(seen.shape, np.nan)
    vcls[right], vcls[missed], vcls[over] = 0, 1, 2
    nr, nm, no = (int(x.sum()) for x in (right, missed, over))
    # lifted water: cells where the stability step raised the desk blend by more than 0.05 kt
    lift = d["ocean"] & (sh > desk + 0.05)
    ls = lift & seen
    new = seen & (z(desk) < 34) & f34          # gale water the step created on seen cells
    share_lift = float((ls & o34).sum() / ls.sum())
    share_new = float((new & o34).sum() / max(new.sum(), 1))
    unst_all = int(lift.sum())
    # cold outbreak: sea minus 2 m air temperature (K) where the step lifts
    sa = d["sa"]
    sa_med, sa_p90 = float(np.nanmedian(sa[lift])), float(np.nanpercentile(sa[lift], 90))
    # check against the study's rows
    rr = pd.read_csv(paths.data("extra", "desk-30m-vs-best-wind", "case_rows.csv.gz"))
    rr = rr[(rr.basin == BASIN) & (rr.step == STEP) & (pd.to_datetime(rr.cycle) == pd.Timestamp(CYC)) & (rr["product"] == "sh_avg")].iloc[0]
    assert abs(rr.fc34 / rr.ob34 - ratio["Desk practice"]) < 1e-6, (rr.fc34, rr.ob34)
    assert abs(rr.n_lift_a34 / rr.n_lift_seen - share_lift) < 1e-6
    unseen_gale = C.area_k(lift & ~seen & (np.nan_to_num(sh, nan=0) >= 34), area)

    lat2 = np.repeat(lats[:, None], len(lats) and seen.shape[1], 1)
    box = C.crop_box(BASIN, ((seen & o34) | (lift & (sh >= 34))) & (lat2 < 60), pad_lat=3, pad_lon=6)
    fig, axes = C.plt.subplots(1, 4, figsize=(17.2, 4.7))
    fig.subplots_adjust(wspace=0.14, top=0.74, bottom=0.2)
    heads = [("ASCAT (seen cells)", "ASCAT"), ("Best Wind", "Best Wind"), ("Desk practice: 30 m stability wind", "Desk practice")]
    for ax, (name, key) in zip(axes[:3], heads):
        C.base_map(BASIN, ax, box)
        m = C.draw_wind(ax, BASIN, prods[key], seen=seen, faint=None if key == "ASCAT" else d["ocean"])
        s = st[key]
        ax.set_title(name, fontsize=11, color=style.INK, loc="left", pad=22)
        ax.text(0, 1.015, "34+ kt: %.0fk nm² (%s)   peak %.0f kt" % (
            s["a34"], "ref" if key == "ASCAT" else "%.2fx ASCAT" % ratio[key], s["peak"]), transform=ax.transAxes,
            fontsize=8.5, color=style.INK2, va="bottom")
    ax = axes[3]
    C.base_map(BASIN, ax, box)
    lons = basins.grid(BASIN)[1]
    ax.pcolormesh(lons, lats, vcls, cmap=ListedColormap([RIGHT, MISS, OVER]), vmin=-0.5, vmax=2.5, shading="nearest",
                  zorder=2, rasterized=True)
    ax.set_title("Desk practice at 34 kt: right, missed, too much", fontsize=11, color=style.INK, loc="left", pad=22)
    ax.text(0, 1.015, "right %d, missed %d, too much %d cells (%.0f%%)" % (nr, nm, no, 100 * no / (nr + no)),
            transform=ax.transAxes, fontsize=8.5, color=style.INK2, va="bottom")
    ax.legend(handles=[Patch(fc=RIGHT, label="right: both at gale"), Patch(fc=MISS, label="missed: ASCAT gale, wind below"),
                       Patch(fc=OVER, label="too much: wind gale, ASCAT below")], loc="upper left", bbox_to_anchor=(0.0, -0.1), fontsize=7.8,
              frameon=True, framealpha=0.9, edgecolor=style.SPINE).set_zorder(10)
    C.wind_legend(fig, m, list(axes[:3]))
    fig.suptitle("Desk practice (30 m) draws %.2fx the gale area ASCAT saw; Best Wind %.2fx, plain blend %.2fx"
                 % (ratio["Desk practice"], ratio["Best Wind"], ratio["Plain blend"]), x=0.01, ha="left", fontsize=13.5,
                 y=1.0, color=style.INK)
    fig.text(0.01, 0.915, ("North Atlantic, +24 h from the 12Z 10 Dec 2025 run, valid 12Z 11 Dec 2025 (held-out week); cold air over warmer water "
                           "(sea minus air %.1f K median where lifted).  Truth: ASCAT real 10 m wind, rain removed, within 90 min; numbers on ASCAT-seen cells.") % sa_med,
             fontsize=8.6,
             color=style.INK2, ha="left")
    C.contour_note(fig, y=0.0)
    C.save_all(fig, "case2_cold_outbreak")

    cap = f"""# Case 2: 30 m desk practice draws about {ratio['Desk practice']:.1f}x the gale area ASCAT saw

**Valid:** 12Z 11 Dec 2025.  **Run:** 12Z 10 Dec 2025 (+24 h).  **Basin:** North Atlantic (30-67N).  **Week:** ISO 2025-W50, held out (`rk.cases.held_out`).
**Truth:** RSS ASCAT real 10 m wind (`rk.truth.ascat_target`, rain dropped, within 90 min); {A['c34']} seen cells at gale.
**Models:** plain blend = page blend; Best Wind = page recipe with the 80% gale-core floor (as in case 1, built by the rescore's `score.products`); desk practice = Stability Height on GFS (strict mask) and on ECMWF (loose mask), each 10 m wind x 1.179 where theta(925 mb) <= theta(surface), edge tapered over 2 cells, then the two averaged (rescore `sh_avg`; mirrors `GFE/smarttools/Stability_Model_Blender.py`). The panel "GFS+ECMWF mean 10 m" in the table is desk practice before the step.

## How the case was picked
Rescore `case_picks.csv.gz`: the {n_nat} North Atlantic +24 h held-out cases with 300 or more ASCAT gale cells have a median desk-practice gale ratio of {med:.2f}x. This case ({ratio['Desk practice']:.2f}x) is the nearest to the median; two cases tied within 0.001, and the one with more ASCAT gale cells ({A['c34']}, against 391) was taken. Its plain blend ({ratio['Plain blend']:.2f}x) and Best Wind ({ratio['Best Wind']:.2f}x) are near the held-out medians for those products (0.91x and 1.15x).
**Is it a cold-air outbreak?** Not a strong one. Where the step lifts the wind, sea minus 2 m air temperature (GFS) has a median of {sa_med:.1f} K and a 90th percentile of {sa_p90:.1f} K, so the caption says cold air over warmer water, not an outbreak.

## Numbers, ASCAT-seen cells (ratios are cell counts, as in the studies; area-weighted by cos(lat): desk practice {aratio['Desk practice']:.2f}x, Best Wind {aratio['Best Wind']:.2f}x, blend {aratio['Plain blend']:.2f}x) (gale = 34+ kt; areas in thousand square nautical miles)
| Panel | Gale area | Ratio to ASCAT | Peak (kt) | Storm (48+) area |
|---|---|---|---|---|
| ASCAT | {A['a34']:.0f} | 1.00x | {A['peak']:.1f} | {A['a48']:.1f} |
| Plain blend | {st['Plain blend']['a34']:.0f} | {ratio['Plain blend']:.2f}x | {st['Plain blend']['peak']:.1f} | {st['Plain blend']['a48']:.1f} |
| Best Wind (page, 80% floor) | {st['Best Wind']['a34']:.0f} | {ratio['Best Wind']:.2f}x | {st['Best Wind']['peak']:.1f} | {st['Best Wind']['a48']:.1f} |
| GFS+ECMWF mean 10 m (desk practice's base) | {st['GFS+ECMWF mean 10 m']['a34']:.0f} | {ratio['GFS+ECMWF mean 10 m']:.2f}x | {st['GFS+ECMWF mean 10 m']['peak']:.1f} | {st['GFS+ECMWF mean 10 m']['a48']:.1f} |
| Desk practice (30 m) | {st['Desk practice']['a34']:.0f} | {ratio['Desk practice']:.2f}x | {st['Desk practice']['peak']:.1f} | {st['Desk practice']['a48']:.1f} |

Right / missed / too much at 34 kt for desk practice: {nr} cells right, {nm} missed, {no} too much (0.25 deg cells, seen only). Of the {int(ls.sum())} seen cells the step lifted above its base, ASCAT had gale in **{share_lift:.1%}** (matches the rescore's n_lift_a34 / n_lift_seen for this case). Of the {int(new.sum())} seen cells that crossed 34 kt only because of the lift, ASCAT had gale in {share_new:.1%}. The step lifts {int(lift.sum())} ocean cells in all, {int(lift.sum()-ls.sum())} outside the swath (unscored; {unseen_gale:.0f}k nm\u00b2 of extra gale water there).

## Caveats
- One forecast; the median rule makes it typical of held-out cases, not a measure of them.
- The 1.179 factor estimates 30 m wind; ASCAT is a 10 m wind. If the desk reads the product as 30 m wind, the extra water is wind aloft, not an error of the step; as a 10 m grid it draws about twice the gale water ASCAT saw.
- ASCAT reads a few kt low in the strongest cores, but the gale edge dominates this ratio and is well sampled except where the swath has gaps.
**Code:** `studies/2026-11-16-research-summary/cases/case2_cold_outbreak.py`; products from `studies/2026-11-16-desk-30m-vs-best-wind/score.py` (read only).
"""
    C.write_caption("case2_cold_outbreak", cap)
    print(st, ratio, nr, nm, no, share_lift, share_new, sa_med, sa_p90)


if __name__ == "__main__":
    main()
