# Chance calibration: gale chance runs low, storm chance far low (pooled ensemble share)

*2026-10-16 · Atlantic 00 and 12 UTC, Pacific 00 UTC · winter 2025-26 cycles in the store (Atlantic 1 Nov to 4 Jan, Pacific 1 Nov to 10 Jan), +24 to +120 h · held-out: 70 Atlantic and 35 Pacific cycles · truth: ASCAT 3x3 box mean (analysis for reference) · chance = the page's pooled GEFS + ECMWF ENS + AIFS ENS member share*

## The answer
- **Gale chance runs low.** Raw 30% gale chance verifies about 40% in ASCAT's box (+24/48 h Atlantic 40.6%, Pacific 38.2%); a true 30% gale line sits at raw 24-25%. The remap fixes the shape (reliability error 0.036 to 0.017 Atlantic, 0.044 to 0.008 Pacific at +24/48) and adds a little skill (Brier skill 0.66 to 0.68, 0.63 to 0.66).
- **Storm chance runs far low against ASCAT.** Atlantic raw 7% verifies 30%; raw 10% verifies about 40%. Remapped on held-out weeks, Atlantic Brier skill goes 0.28 to 0.53 at +24/48 (0.26 to 0.45 at +72, 0.20 to 0.31 at +96/120) and reliability error 0.048 to 0.006.
- **The shared curve does not fully fix the Pacific.** Fitted on both basins' tune weeks added together and scored on Pacific held-out weeks, Pacific storm Brier skill is 0.20 raw, 0.23 own-basin remap, 0.25 shared at +24/48 (0.12, 0.13, 0.15 at +72; 0.08, 0.09, 0.11 at +96/120). Better than own-basin, still small, on only 12 of 35 held-out cycles with a storm event. The shared curve is right for Pacific raw shares of 15% and up but states about double the true chance at raw 5-10% (Pacific raw 5-10% verifies 13%, the shared curve shows 19-41%; reliability error 0.016 vs 0.010 own-basin). **The recommended table therefore keeps the Pacific on its own storm curve** (closer to honest where most Pacific forecasts sit, 0.010 vs 0.016 reliability error; it moves Pacific storm chances little) and uses the shared curve for the Atlantic. The Pacific storm calibration stays provisional until the 06/18 UTC ASCAT passes are in the sample.
- **Hurricane force cannot be calibrated.** Held-out cycles with a 64 kt event in the box: Atlantic 11 to 17 of 70, Pacific 2 to 4 of 35, under the ~30 needed. The recommended 64 kt table is the page's current one, unchanged, and the 90% HF rule stays provisional. A shared 64 kt refit made Pacific held-out Brier skill worse (-0.46 to -3.46 at +24/48 on 2 events), which is why it was not used.
- **Analysis truth says something different, and we use ASCAT.** Against analyses the storm chance is near honest at +24/48 (Atlantic raw 30% verifies 27%; skill 0.40 to 0.49) and the gale chance is honest at +24/48 (raw 30% verifies 30%). Analyses smooth peaks, so they under-count the storm-force winds ASCAT sees; Jason chose the ASCAT box as the truth for chances. The remap below is therefore an ASCAT-box remap: it will read high to anyone checking against analyses.

## The evidence
Held-out weeks only. Fit: `basin` = fitted on that basin's tune weeks; `shared` = 48 and 64 kt fitted on both basins' tune weeks added, scored on this basin's held-out weeks. 34 kt is per basin only.

**ASCAT 3x3 box (the truth used)**

| Truth | Chance | Basin | Lead | Fit | Held-out cycles with event | Brier skill raw | remapped | Reliability err raw | remapped | Raw share = true 30% | True at raw 30% |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASCAT box | 34 kt | Atlantic | +24/48 | basin | 70 of 70 | 0.66 | 0.68 | 0.036 | 0.017 | 24.3% | 40.6% |
| ASCAT box | 34 kt | Atlantic | +72 | basin | 69 of 70 | 0.58 | 0.59 | 0.036 | 0.015 | 23.9% | 39.9% |
| ASCAT box | 34 kt | Atlantic | +96/120 | basin | 70 of 70 | 0.42 | 0.44 | 0.034 | 0.013 | 23.6% | 39.3% |
| ASCAT box | 34 kt | Pacific | +24/48 | basin | 32 of 35 | 0.63 | 0.66 | 0.044 | 0.008 | 25.0% | 38.2% |
| ASCAT box | 34 kt | Pacific | +72 | basin | 24 of 35 | 0.53 | 0.56 | 0.048 | 0.029 | 21.6% | 44.4% |
| ASCAT box | 34 kt | Pacific | +96/120 | basin | 29 of 35 | 0.37 | 0.38 | 0.024 | 0.020 | 23.0% | 37.6% |
| ASCAT box | 48 kt | Atlantic | +24/48 | basin | 55 of 70 | 0.28 | 0.53 | 0.048 | 0.006 | 7.5% | 87.4% |
| ASCAT box | 48 kt | Atlantic | +24/48 | shared | 55 of 70 | 0.28 | 0.53 | 0.048 | 0.006 | 7.5% | 87.4% |
| ASCAT box | 48 kt | Atlantic | +72 | basin | 38 of 70 | 0.26 | 0.45 | 0.046 | 0.006 | 6.9% | 75.8% |
| ASCAT box | 48 kt | Atlantic | +72 | shared | 38 of 70 | 0.26 | 0.45 | 0.046 | 0.006 | 7.0% | 75.6% |
| ASCAT box | 48 kt | Atlantic | +96/120 | basin | 56 of 70 | 0.20 | 0.31 | 0.035 | 0.010 | 7.2% | 65.7% |
| ASCAT box | 48 kt | Atlantic | +96/120 | shared | 56 of 70 | 0.20 | 0.31 | 0.035 | 0.009 | 7.3% | 65.7% |
| ASCAT box | 48 kt | Pacific | +24/48 | basin | 12 of 35 | 0.20 | 0.23 | 0.020 | 0.010 | 25.9% | 32.4% |
| ASCAT box | 48 kt | Pacific | +24/48 | shared | 12 of 35 | 0.20 | 0.25 | 0.020 | 0.016 | 7.5% | 87.4% |
| ASCAT box | 48 kt | Pacific | +72 | basin | 8 of 35 | 0.12 | 0.13 | 0.020 | 0.016 | 29.9% | 30.1% |
| ASCAT box | 48 kt | Pacific | +72 | shared | 8 of 35 | 0.12 | 0.15 | 0.020 | 0.016 | 7.0% | 75.6% |
| ASCAT box | 48 kt | Pacific | +96/120 | basin | 11 of 35 | 0.08 | 0.09 | 0.016 | 0.013 | 29.8% | 30.2% |
| ASCAT box | 48 kt | Pacific | +96/120 | shared | 11 of 35 | 0.08 | 0.11 | 0.016 | 0.012 | 7.3% | 65.7% |

**Hurricane force, ASCAT box (not usable)**

| Truth | Chance | Basin | Lead | Fit | Held-out cycles with event | Brier skill raw | remapped | Reliability err raw | remapped | Raw share = true 30% | True at raw 30% |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASCAT box | 64 kt | Atlantic | +24/48 | basin | 15 of 70 | 0.03 | 0.05 | 0.004 | 0.003 | 22.8% | 36.5% |
| ASCAT box | 64 kt | Atlantic | +24/48 | shared | 15 of 70 | 0.03 | 0.05 | 0.004 | 0.003 | 22.9% | 36.5% |
| ASCAT box | 64 kt | Atlantic | +72 | basin | 11 of 70 | 0.03 | 0.04 | 0.002 | 0.002 | 25.4% | 34.3% |
| ASCAT box | 64 kt | Atlantic | +72 | shared | 11 of 70 | 0.03 | 0.04 | 0.002 | 0.002 | 25.5% | 34.3% |
| ASCAT box | 64 kt | Atlantic | +96/120 | basin | 17 of 70 | 0.04 | 0.01 | 0.002 | 0.003 | 29.5% | 30.4% |
| ASCAT box | 64 kt | Atlantic | +96/120 | shared | 17 of 70 | 0.04 | 0.01 | 0.002 | 0.002 | 29.6% | 30.4% |
| ASCAT box | 64 kt | Pacific | +24/48 | basin | 2 of 35 | -0.47 | -0.46 | 0.002 | 0.002 | 30.0% | 30.0% |
| ASCAT box | 64 kt | Pacific | +24/48 | shared | 2 of 35 | -0.47 | -3.46 | 0.002 | 0.005 | 22.9% | 36.5% |
| ASCAT box | 64 kt | Pacific | +72 | basin | 2 of 35 | -0.01 | -0.01 | 0.001 | 0.001 | 30.1% | 29.9% |
| ASCAT box | 64 kt | Pacific | +72 | shared | 2 of 35 | -0.01 | -0.14 | 0.001 | 0.002 | 25.5% | 34.3% |
| ASCAT box | 64 kt | Pacific | +96/120 | basin | 4 of 35 | -0.00 | -0.00 | 0.000 | 0.000 | 30.0% | 30.0% |
| ASCAT box | 64 kt | Pacific | +96/120 | shared | 4 of 35 | -0.00 | -0.11 | 0.000 | 0.002 | 29.6% | 30.4% |

**Analysis truth, for reference**

| Truth | Chance | Basin | Lead | Fit | Held-out cycles with event | Brier skill raw | remapped | Reliability err raw | remapped | Raw share = true 30% | True at raw 30% |
|---|---|---|---|---|---|---|---|---|---|---|---|
| analysis | 34 kt | Atlantic | +24/48 | basin | 70 of 70 | 0.69 | 0.72 | 0.041 | 0.003 | 30.1% | 29.8% |
| analysis | 34 kt | Atlantic | +72 | basin | 70 of 70 | 0.57 | 0.59 | 0.035 | 0.007 | 27.6% | 33.9% |
| analysis | 34 kt | Atlantic | +96/120 | basin | 70 of 70 | 0.41 | 0.41 | 0.025 | 0.012 | 26.1% | 35.3% |
| analysis | 34 kt | Pacific | +24/48 | basin | 35 of 35 | 0.64 | 0.68 | 0.039 | 0.006 | 29.2% | 31.7% |
| analysis | 34 kt | Pacific | +72 | basin | 35 of 35 | 0.47 | 0.50 | 0.033 | 0.011 | 26.0% | 36.5% |
| analysis | 34 kt | Pacific | +96/120 | basin | 35 of 35 | 0.34 | 0.36 | 0.024 | 0.008 | 26.0% | 36.3% |
| analysis | 48 kt | Atlantic | +24/48 | basin | 54 of 70 | 0.40 | 0.49 | 0.012 | 0.002 | 31.6% | 26.8% |
| analysis | 48 kt | Atlantic | +24/48 | shared | 54 of 70 | 0.40 | 0.49 | 0.012 | 0.002 | 31.7% | 26.6% |
| analysis | 48 kt | Atlantic | +72 | basin | 38 of 70 | 0.32 | 0.34 | 0.008 | 0.004 | 24.9% | 37.8% |
| analysis | 48 kt | Atlantic | +72 | shared | 38 of 70 | 0.32 | 0.34 | 0.008 | 0.004 | 24.8% | 37.9% |
| analysis | 48 kt | Atlantic | +96/120 | basin | 53 of 70 | 0.24 | 0.25 | 0.006 | 0.005 | 24.6% | 39.9% |
| analysis | 48 kt | Atlantic | +96/120 | shared | 53 of 70 | 0.24 | 0.25 | 0.006 | 0.006 | 23.9% | 40.5% |
| analysis | 48 kt | Pacific | +24/48 | basin | 16 of 35 | 0.28 | 0.34 | 0.008 | 0.006 | 33.3% | 23.9% |
| analysis | 48 kt | Pacific | +24/48 | shared | 16 of 35 | 0.28 | 0.38 | 0.008 | 0.004 | 31.7% | 26.6% |
| analysis | 48 kt | Pacific | +72 | basin | 9 of 35 | 0.08 | 0.11 | 0.005 | 0.004 | 28.8% | 30.9% |
| analysis | 48 kt | Pacific | +72 | shared | 9 of 35 | 0.08 | 0.12 | 0.005 | 0.003 | 24.8% | 37.9% |
| analysis | 48 kt | Pacific | +96/120 | basin | 10 of 35 | 0.03 | 0.07 | 0.003 | 0.001 | 27.1% | 31.2% |
| analysis | 48 kt | Pacific | +96/120 | shared | 10 of 35 | 0.03 | 0.07 | 0.003 | 0.001 | 23.9% | 40.5% |

**What the page shows now vs the recommended table** (percent chance shown at each raw member share; "page now" is the current calibration.json for 48 kt and the raw share for 34 kt, which the page does not calibrate; recommended = per-basin box curve at 34, shared box curve at 48; 64 kt unchanged):

| Chance | Basin | Lead | raw 5% | raw 10% | raw 20% | raw 30% | raw 50% |
|---|---|---|---|---|---|---|---|
| gale 34 | Atlantic | +24/48 | 5 to 2.4 | 10 to 7.3 | 20 to 22.7 | 30 to 40.6 | 50 to 71.1 |
| gale 34 | Atlantic | +72 | 5 to 3.2 | 10 to 8.4 | 20 to 23.2 | 30 to 39.9 | 50 to 69 |
| gale 34 | Atlantic | +96/120 | 5 to 4.2 | 10 to 9.9 | 20 to 24.4 | 30 to 39.3 | 50 to 66.6 |
| gale 34 | Pacific | +24/48 | 5 to 2.9 | 10 to 7.9 | 20 to 22 | 30 to 38.2 | 50 to 68.2 |
| gale 34 | Pacific | +72 | 5 to 3.1 | 10 to 8.8 | 20 to 26.9 | 30 to 44.4 | 50 to 63.7 |
| gale 34 | Pacific | +96/120 | 5 to 3.8 | 10 to 10.6 | 20 to 26.5 | 30 to 37.6 | 50 to 58.5 |
| storm 48 | Atlantic | +24/48 | 0.4 to 18.6 | 1.4 to 40.7 | 7.1 to 72.1 | 19.3 to 87.4 | 55.6 to 95.6 |
| storm 48 | Atlantic | +72 | 1.8 to 19.9 | 4.2 to 40.5 | 14.1 to 66.5 | 32.9 to 75.6 | 51.4 to 75.6 |
| storm 48 | Atlantic | +96/120 | 1.7 to 19.3 | 4.9 to 44.3 | 14.8 to 64.2 | 26 to 65.7 | 52 to 65.7 |
| storm 48 | Pacific | +24/48 | 0.6 to 18.6 | 1.8 to 40.7 | 8.6 to 72.1 | 27.1 to 87.4 | 53.4 to 95.6 |
| storm 48 | Pacific | +72 | 1.3 to 19.9 | 3.8 to 40.5 | 19.4 to 66.5 | 29.8 to 75.6 | 49.6 to 75.6 |
| storm 48 | Pacific | +96/120 | 1.4 to 19.3 | 4.4 to 44.3 | 17.6 to 64.2 | 28.9 to 65.7 | 48.8 to 65.7 |

![48 kt reliability, ASCAT box: Atlantic remap works, Pacific barely moves, shared curve overshoots low Pacific shares](reliability_box_48.png)

Other figures: `reliability_box_34.png`, `reliability_box_64.png`, analysis and single-cell versions alongside. Numbers behind them: `results.csv`, `reliability_bins.csv`.

*Intervals were not computed. Weeks, not cells, are the independent sample, so cell counts overstate the evidence.*

## What it does not show
- One winter. Cycles in the store only: Atlantic to 4 Jan, Pacific to 10 Jan. The tune and held-out split is by week, but the held-out weeks are the same winter.
- Pacific is 00 UTC only (06 and 18 UTC are not in the store yet). 12 of 35 held-out Pacific cycles have a 48 kt event, 2 to 4 have a 64 kt event.
- The shared 48 kt curve is dominated by the Atlantic (66.6k tune events vs 2.5k Pacific at +24/48). It helps the Pacific only a little and over-states its low chances.
- Core likelihood (the Core Lifted layer) is not checked here; the page's nightly verification rows started 10-16.
- The ASCAT box is the best truth we have for peaks, not a perfect one: it is a 3x3 mean of satellite cells and misses between passes.
- No independent recompute of these numbers has been done.

## How it was done
- Truth: ASCAT 3x3 box mean (`rk.truth.ascat_box`, real 10 m wind, Metop offset handled there), event = box mean at or above the threshold; analysis and single-cell truth for reference.
- Chance: sum of p x n over GEFS, ECMWF ENS and AIFS ENS over sum of n, as on the page. Fitter: `rk.calibrate.fit` (the page's, shrinkage min(1, n/2000)); shared fit = the same fitter on both basins' summed tables.
- Cases: all winter 2025-26 cycles in the store, +24 to +120 h; tune and held-out split by `rk.cases.split`.
- Code: `studies/2026-10-16-chance-calibration/run_first_look.py accumulate|report --mode pooled [--shared]`, `make_recommended.py`; data: `/mnt/project-files/chance-calibration/pooled/` (`calibration_recommended.json`, `calibration_compare.csv`).
- Checked by: not independently recomputed.
