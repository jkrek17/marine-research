# AI-GFS in the GFE blend: findings

**Answer:** in the deterministic GFE blend, GFS + ECMWF on their own did best on the preset win line. Adding AI-GFS, at full or half weight, kept gale scores the same (CSI within 0.007, not significant) but caught 2-5 points fewer storm-force areas. AI-GFS is still a much better AI member than AIFS. With AIFS in the slot the blend lost about 10 points of storm catch against GFS + ECMWF; with AI-GFS it lost 2-5. Recommendation for GFE (PR #95): run the deterministic blend on GFS + ECMWF. AI-GFS at half weight is the option if false gale areas matter more than storm catch.

Truth: ASCAT real 10 m wind (intercal), 5x5 deg tiles. Held-out weeks only: ISO weeks 2025-45, 2025-50, 2026-02, 2026-07 and 2026-12. Atlantic: 33 cycles at 12 UTC, +24..+120 h, 165 cases. Pacific: 67 cycles at 00 and 12 UTC, +24..+120 h and the 06/18 UTC valid times +30..+126 h, 670 cases. Every case has all four blends and all four single models. Recipe: build.py `nomem` (support among the current, 12 h and 24 h earlier runs, + min(0.3 x SD, 5 kt)), via `rk.features.det_blend`.

| basin | blend | gale CSI | gale false alarm share | storm catch | gale area / ASCAT | buoy bias (kt) |
|---|---|---|---|---|---|---|
| Atlantic | GFS + ECMWF (N) | .614 | .230 | .372 | 0.95 | -0.2 |
| Atlantic | + AI-GFS half (Gh) | .609 | .201 | .338 | 0.95 | -0.2 |
| Atlantic | + AI-GFS full (G1) | .607 | .196 | .324 | 0.96 | +0.1 |
| Atlantic | + AIFS half (A) | .605 | .166 | .273 | 0.84 | -1.8 |
| Pacific | GFS + ECMWF (N) | .546 | .314 | .216 | 1.02 | +0.6 |
| Pacific | + AI-GFS half (Gh) | .542 | .270 | .192 | 0.96 | +0.8 |
| Pacific | + AI-GFS full (G1) | .543 | .249 | .173 | 0.95 | +1.0 |
| Pacific | + AIFS half (A) | .549 | .209 | .120 | 0.84 | -1.0 |

These are differences against N with whole-week 95% intervals. There are only 5 weeks, so the intervals are rough.

| difference | gale CSI, Atlantic | gale CSI, Pacific | storm catch, Atlantic | storm catch, Pacific |
|---|---|---|---|---|
| G1 - N | -.007 [-.019, +.008] | -.003 [-.032, +.016] | -4.8 pts [-7.1, -0.4] | -4.3 [-8.0, -2.1] |
| Gh - N | -.005 [-.015, +.004] | -.004 [-.024, +.007] | -3.4 [-5.5, 0.0] | -2.4 [-5.8, +0.5] |
| A - N | -.008 [-.024, +.010] | +.003 [-.024, +.018] | -9.9 [-14.1, -5.4] | -9.6 [-13.9, -6.9] |

Win line (design.md, G1/Gh against N, both basins): both fail test 1 (gale CSI is not higher) and test 2 (storm catch is down more than 2 points). In the Pacific both also fail test 3 (gale area further from 1). That leaves GFE on N. Gh in the Pacific missed test 2 by 0.4 points.

**AI-GFS on its own, against ASCAT at 34+ kt:**
- Bias: AI-GFS runs 6.0 kt low in the Atlantic and 5.4 kt low in the Pacific. That is less low than ECMWF (6.8 / 6.4) or AIFS (7.4 / 7.3), and about the same as GFS (6.2 / 4.9).
- Storm-tile catch: AI-GFS 32% Atlantic and 21% Pacific; GFS 41 / 37; ECMWF 36 / 20; AIFS 7 / 1.
- Cold air (GFS t2 - skt < -3 K): AI-GFS runs no lower than in other air (Atlantic -5.6 cold vs -6.4 not cold). It does not share AIFS's cold-air shortfall.
- All the models run 4-8 kt below ASCAT in gale water. That is the known shortfall of grids against ASCAT peaks, not something specific to AI-GFS.

**Why AI-GFS does not earn its place (a reading, not tested):** most likely it pulls the support-weighted base toward the middle where GFS or ECMWF has the strongest core, so storm areas shrink. It also trims false gale areas (Pacific false-alarm share .31 down to .25-.27), but by the rule we set that trade does not pay. Jason favours over-warning.

**Not tested:** the tune weeks as a second look; that needs about 36 GB more of AI-GFS and the extra GFS/ECMWF lead times. Also not tested: the AI-GFS ensemble (Jason is looking for the members), other global models, and whether the AWIPS AI-GFS feed is the operational AWS `aigfs` run (assumed).

**Missing data:** AWS has no AI-GFS run for 2026-02-13 12 UTC, so 10 cases were skipped.

**Check:** a second agent recomputed every number above from `case_counts.csv` without reading this write-up or summarize.py. Its numbers matched to the third decimal, including the week-bootstrap intervals (same seed and method), the pairing (835 keys, all 8 products) and the verdict.

Files: `verdict.md`, `summary.csv`, `differences.csv` and `singles.csv` here. Per-case counts are in `RK_DATA/extra/aigfs-in-gfe-blend/case_counts.csv`.
