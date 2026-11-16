#!/usr/bin/env python3
"""Case 1, "Best Wind restores a hurricane-force core": North Atlantic, 00Z 9 Dec 2025 run, +24 h, valid 00Z 10 Dec.

  python3 case1_hf_core.py

Picked from tiles_held_out.csv.gz (extra/most-likely-wind, per case x product): the 10 held-out North Atlantic
+24 h forecasts with any ASCAT 64 kt cell, restricted to the 7 with 20+ such cells, ranked by the share of those
cells Best Wind covers at 64 kt; the median (4th of 7) is this case. Panels: ASCAT (seen cells) | plain page blend |
Best Wind | desk Stability Height wind (desk practice: Stability Height on GFS and on ECMWF, then averaged, rescore product sh_avg), same scale, numbers on ASCAT-seen
cells only. Writes case1_hf_core.png/.pdf/.md to RK_SUMMARY_OUT.
"""
import datetime as dt

import numpy as np
import pandas as pd

import cases_common as C
from rk import basins, paths, style

BASIN, CYC, STEP = "natl", dt.datetime(2025, 12, 9, 0), 24


def pick_table():
    t = pd.read_csv(paths.data("extra", "most-likely-wind", "tiles_held_out.csv.gz"))
    t = t[(t.basin == BASIN) & (t.step == STEP) & t["product"].isin(["blend", "best"])]
    p = t.pivot_table(index="cycle", columns="product", values=["cau64", "ob64", "fc64"]).reset_index()
    p.columns = ["_".join(c).strip("_") for c in p.columns]
    p = p[p.ob64_best > 0]
    p["best_catch64"] = p.cau64_best / p.ob64_best
    p["blend_catch64"] = p.cau64_blend / p.ob64_blend
    return p.sort_values("best_catch64").reset_index(drop=True)


def main():
    style.use()
    pk = pick_table()
    big = pk[pk.ob64_best >= 20].reset_index(drop=True)
    med = big.iloc[len(big) // 2]
    assert pd.Timestamp(med.cycle) == pd.Timestamp(CYC), med.cycle
    big.to_csv(C.OUT / "case1_pick_table.csv", index=False) if C.OUT.exists() else None
    pa, pb = C.ensure_case(BASIN, CYC, STEP)
    R = C.rescore()
    d = R.load(BASIN, CYC, STEP)
    P, common = R.products(d)
    assert common
    prods = {"blend": P["blend"], "best": P["best"]}       # best = page Best Wind, gale floor at 80%
    sh = P["sh_avg"]                                         # desk practice
    seen = d["seen"] & d["ocean"] & np.isfinite(d["spd"])
    asc = np.where(seen, d["spd"], np.nan)
    panels = [("ASCAT (seen cells)", asc, False),
              ("Plain blend", prods["blend"], True),
              ("Best Wind", prods["best"], True),
              ("Desk practice: 30 m stability wind", sh, True)]
    area = C.cell_area_nm2(BASIN)
    valid = CYC + dt.timedelta(hours=STEP)
    stats = {}
    for name, f, _ in panels:
        v = np.where(seen, f, np.nan)
        z = np.nan_to_num(v, nan=-1)
        stats[name] = dict(peak=float(np.nanmax(v)), a34=C.area_k(z >= 34, area), a48=C.area_k(z >= 48, area),
                           a64=C.area_k(z >= 64, area), c34=int((z >= 34).sum()), c48=int((z >= 48).sum()),
                           c64=int((z >= 64).sum()))
    box = C.crop_box(BASIN, seen & (np.nan_to_num(asc, nan=0) >= 64), pad_lat=10, pad_lon=14)
    fig, axes = plt_grid(4, box)
    for ax, (name, f, model) in zip(axes, panels):
        C.base_map(BASIN, ax, box)
        m = C.draw_wind(ax, BASIN, f, seen=seen, faint=(d["ocean"] if model else None))
        s, a = stats[name], stats["ASCAT (seen cells)"]
        ax.set_title(name, fontsize=11, color=style.INK, loc="left", pad=26)
        ax.text(0, 1.015, "peak %.0f kt\n48+ kt %.1fk nm² (%.2fx)   64+ kt %.1fk nm² (%s)" % (
            s["peak"], s["a48"], s["a48"] / a["a48"], s["a64"],
            "ref" if not model else "%.2fx" % (s["a64"] / a["a64"])), transform=ax.transAxes, fontsize=7.8,
            color=style.INK2, va="bottom", linespacing=1.25)
    C.wind_legend(fig, m, list(axes))
    A, B, W, S = (stats[k] for k in ("ASCAT (seen cells)", "Plain blend", "Best Wind", "Desk practice: 30 m stability wind"))
    fig.suptitle("Best Wind puts the hurricane-force core back: %d ASCAT-seen cells at 64 kt, plain blend %d"
                 % (W["c64"], B["c64"]), x=0.01, ha="left", fontsize=13.5, y=1.06, color=style.INK)
    fig.text(0.01, 0.99, "North Atlantic, +24 h from the 00Z 9 Dec 2025 run, valid 00Z 10 Dec 2025 (held-out week)."
             "  Truth: ASCAT real 10 m wind, rain removed, within 90 min.  Models drawn pale outside the ASCAT swath;"
             " numbers on seen cells only.", fontsize=8.6, color=style.INK2, ha="left")
    C.contour_note(fig, y=-0.02)
    png, pdf = C.save_all(fig, "case1_hf_core")

    n = len(big)
    cap = f"""# Case 1: Best Wind restores a hurricane-force core

**Valid:** 00Z 10 Dec 2025.  **Run:** 00Z 9 Dec 2025 (+24 h).  **Basin:** North Atlantic (tested area 30-67N).  **Week:** ISO 2025-W50, a held-out week (`rk.cases.held_out`).
**Truth:** RSS ASCAT real 10 m wind (`rk.truth.ascat_target`: intercalibrated Metop-B/C, rain-flagged cells dropped, passes within 90 min of valid time); {A['c34']} seen cells at 34 kt or more.
**Models (written to match `awips-tools/marine_wind/pipeline/storm.py` and the rescore builder `studies/2026-11-16-desk-30m-vs-best-wind/score.py`):** plain blend = the page blend (GFS, ECMWF, AIFS at half weight, plus the ensemble-spread term). Best Wind = that blend plus ramps on the stronger of GFS and ECMWF (+6 kt rising over 36-40 kt, +4 kt more over 44-48 kt), plus the HF core (+6 kt rising over 52-56 kt where 30% or more of GEFS members show 48 kt within the ~100 km box), open water at 25N and north only, then raised to 34 kt where the gale-core chance is 80% or more (the page's current floor). Desk practice = the Stability Height tool applied to GFS (strict mask: theta at 925 mb <= theta of 2 m air) and to ECMWF (loose mask: skin temperature), each 10 m wind x 1.179 (3^0.15, 10 m to 30 m) where unstable, mask grown 2 cells and tapered, then the two averaged (rescore product `sh_avg`).

## How the case was picked
Not by eye and not the best one. Of the 10 held-out North Atlantic +24 h forecasts with any ASCAT 64 kt cell (`extra/most-likely-wind/tiles_held_out.csv.gz`), 7 have 20 or more 64 kt cells. Ranked by the share of those cells Best Wind covers at 64 kt (0%, 33%, 40%, **45%**, 60%, 71%, 72%), this is the median, the 4th of {n}. The plain blend covered none of the 64 kt cells in six of the seven cases. Table: `case1_pick_table.csv`.

## Numbers, ASCAT-seen cells only (areas in thousand square nautical miles; ratio to ASCAT in brackets)
| Panel | Peak (kt) | 34+ kt | 48+ kt | 64+ kt (cells) |
|---|---|---|---|---|
| ASCAT | {A['peak']:.1f} | {A['a34']:.1f} | {A['a48']:.1f} | {A['a64']:.1f} ({A['c64']}) |
| Plain blend | {B['peak']:.1f} | {B['a34']:.1f} ({B['a34']/A['a34']:.2f}x) | {B['a48']:.1f} ({B['a48']/A['a48']:.2f}x) | {B['a64']:.1f} ({B['c64']}) |
| Best Wind | {W['peak']:.1f} | {W['a34']:.1f} ({W['a34']/A['a34']:.2f}x) | {W['a48']:.1f} ({W['a48']/A['a48']:.2f}x) | {W['a64']:.1f} ({W['c64']}; {W['a64']/A['a64']:.2f}x) |
| Desk practice (30 m) | {S['peak']:.1f} | {S['a34']:.1f} ({S['a34']/A['a34']:.2f}x) | {S['a48']:.1f} ({S['a48']/A['a48']:.2f}x) | {S['a64']:.1f} ({S['c64']}; {S['a64']/A['a64']:.2f}x) |

Forecaster reading: ASCAT saw {A['peak']:.0f} kt and {A['c64']} cells at hurricane force. The plain blend peaked at {B['peak']:.0f} kt on those cells, storm force but not hurricane force, and drew {B['a48']/A['a48']:.0%} of ASCAT's 48 kt water. Best Wind drew {W['a48']/A['a48']:.0%} of it with a {W['peak']:.0f} kt peak and {W['c64']} cells at 64 kt (ASCAT {A['c64']}, so about {W['c64']/A['c64']:.0%} of the cell count; the 64 kt area is {W['a64']/A['a64']:.2f}x). In the case-pick table, Best Wind sits on 45% of ASCAT's 64 kt cells (65 of 146) and the blend on none; Best Wind's 98 cells include some outside ASCAT's 64 kt cells, but on ASCAT-seen water only.

## Caveats
- One forecast. The median rule says the case is typical of the held-out cases with real HF cores, not that Best Wind always does this; six of seven cases had the blend at zero HF cells and Best Wind covered 0-72% of them.
- The brief's "plain blend well under storm force" does not hold for this case at the peak: the blend peaks at {B['peak']:.0f} kt (storm force), but it covers under a third of ASCAT's storm-force water and none of its hurricane-force water.
- ASCAT reads a few kt low in the strongest cores. The ERA5 record plays no part here.
- Best Wind also draws more gale water than ASCAT ({W['a34']/A['a34']:.2f}x); gale water outside the swath is not scored.
- Desk practice (30 m stability wind on GFS and ECMWF, averaged) is a different product from Best Wind: here it peaks at {S['peak']:.0f} kt and draws {S['a48']/A['a48']:.2f}x the ASCAT storm area.
**Code:** `studies/2026-11-16-research-summary/cases/case1_hf_core.py` (inputs: `extra/most-likely-wind` and `extra/strong-core-lift` case builders; no new pull).
"""
    C.write_caption("case1_hf_core", cap)
    pk.to_csv(C.OUT / "case1_pick_table.csv", index=False)
    print(stats)


def plt_grid(n, box):
    w = (box[1] - box[0]) * np.cos(np.radians((box[2] + box[3]) / 2))
    h = box[3] - box[2]
    pw = 4.3
    fig, axes = C.plt.subplots(1, n, figsize=(pw * n, pw * h / w + 1.6))
    fig.subplots_adjust(wspace=0.12, top=0.84, bottom=0.17)
    return fig, axes


if __name__ == "__main__":
    main()
