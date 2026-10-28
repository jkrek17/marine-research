# GEFS-only chances: verdict

*Win line (design card, preset): on held-out weeks, in both basins and at each lead group, the remapped chance has a lower reliability error than raw GEFS and a Brier skill not lower than raw by more than 0.01. The 0.5 deg result decides. Truth: ASCAT 3x3 box. Fit: tune weeks, `rk.calibrate.fit_pooled` per basin, prior = both-basin logistic (the 10-16 refit method). Held-out weeks scored once. Pacific held-out = 00 UTC plus 06/18 UTC valid times; Pacific fit = 00 UTC valid times.*

## Verdict

| Resolution | Chance | Basin x lead cells passing | Verdict | Failing cells |
|---|---|---|---|---|
| 0.25 deg | gale 34 kt | 6 of 6 | WIN | none |
| 0.25 deg | storm 48 kt | 3 of 6 | NOT MET | Pacific +24/48 (rel err), Pacific +72 (rel err), Pacific +96/120 (skill) |
| 0.5 deg | gale 34 kt | 6 of 6 | WIN | none |
| 0.5 deg | storm 48 kt | 4 of 6 | NOT MET | Pacific +72 (rel err + skill), Pacific +96/120 (rel err + skill) |

64 kt: raw GEFS p64 only, **not calibrated** (too few events); see the table below.

## Held-out scores, 0.5 deg

| Chance | Basin | Lead | Held-out cycles with event | Brier skill raw | remapped | Rel. error raw | remapped | Win | Raw 30% = true | Remapped says at raw 30% | Pooled page: Brier skill raw | page table | refit table | Pooled rel. error raw | page | refit |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gale 34 | Atlantic | +24/48 | 70 of 70 | 0.58 | 0.60 | 0.040 | 0.017 | yes | 17% | 22% | 0.66 | 0.66 | 0.68 | 0.036 | 0.036 | 0.017 |
| gale 34 | Atlantic | +72 | 69 of 70 | 0.48 | 0.49 | 0.032 | 0.014 | yes | 20% | 25% | 0.58 | 0.58 | 0.59 | 0.036 | 0.036 | 0.015 |
| gale 34 | Atlantic | +96/120 | 70 of 70 | 0.32 | 0.32 | 0.017 | 0.012 | yes | 24% | 25% | 0.42 | 0.42 | 0.44 | 0.034 | 0.034 | 0.013 |
| gale 34 | Pacific | +24/48 | 96 of 105 | 0.46 | 0.50 | 0.037 | 0.012 | yes | 16% | 22% | 0.56 | 0.56 | 0.59 | 0.032 | 0.032 | 0.012 |
| gale 34 | Pacific | +72 | 75 of 105 | 0.28 | 0.33 | 0.043 | 0.021 | yes | 15% | 24% | 0.40 | 0.40 | 0.41 | 0.026 | 0.026 | 0.022 |
| gale 34 | Pacific | +96/120 | 90 of 105 | 0.15 | 0.20 | 0.043 | 0.022 | yes | 15% | 25% | 0.27 | 0.27 | 0.26 | 0.015 | 0.015 | 0.022 |
| storm 48 | Atlantic | +24/48 | 55 of 70 | 0.41 | 0.47 | 0.023 | 0.006 | yes | 56% | 50% | 0.28 | 0.16 | 0.53 | 0.048 | 0.055 | 0.006 |
| storm 48 | Atlantic | +72 | 38 of 70 | 0.32 | 0.36 | 0.022 | 0.003 | yes | 45% | 51% | 0.26 | 0.21 | 0.46 | 0.046 | 0.052 | 0.005 |
| storm 48 | Atlantic | +96/120 | 56 of 70 | 0.24 | 0.26 | 0.015 | 0.007 | yes | 37% | 41% | 0.20 | 0.16 | 0.32 | 0.035 | 0.039 | 0.010 |
| storm 48 | Pacific | +24/48 | 28 of 105 | 0.27 | 0.28 | 0.006 | 0.005 | yes | 45% | 40% | 0.19 | 0.08 | 0.34 | 0.015 | 0.019 | 0.005 |
| storm 48 | Pacific | +72 | 17 of 105 | 0.13 | 0.11 | 0.007 | 0.008 | NO | 22% | 37% | 0.10 | 0.05 | 0.17 | 0.011 | 0.014 | 0.005 |
| storm 48 | Pacific | +96/120 | 26 of 105 | 0.07 | 0.01 | 0.006 | 0.010 | NO | 64% | 91% | 0.05 | 0.03 | 0.07 | 0.006 | 0.008 | 0.004 |

## Held-out scores, 0.25 deg

| Chance | Basin | Lead | Held-out cycles with event | Brier skill raw | remapped | Rel. error raw | remapped | Win | Raw 30% = true | Remapped says at raw 30% | Pooled page: Brier skill raw | page table | refit table | Pooled rel. error raw | page | refit |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gale 34 | Atlantic | +24/48 | 70 of 70 | 0.57 | 0.59 | 0.041 | 0.017 | yes | 17% | 22% | 0.66 | 0.66 | 0.68 | 0.036 | 0.036 | 0.017 |
| gale 34 | Atlantic | +72 | 69 of 70 | 0.48 | 0.49 | 0.033 | 0.014 | yes | 19% | 25% | 0.58 | 0.58 | 0.59 | 0.036 | 0.036 | 0.015 |
| gale 34 | Atlantic | +96/120 | 70 of 70 | 0.32 | 0.32 | 0.018 | 0.012 | yes | 24% | 25% | 0.42 | 0.42 | 0.44 | 0.034 | 0.034 | 0.013 |
| gale 34 | Pacific | +24/48 | 96 of 105 | 0.46 | 0.50 | 0.038 | 0.012 | yes | 15% | 22% | 0.56 | 0.56 | 0.59 | 0.032 | 0.032 | 0.012 |
| gale 34 | Pacific | +72 | 75 of 105 | 0.28 | 0.33 | 0.044 | 0.021 | yes | 15% | 23% | 0.40 | 0.40 | 0.41 | 0.026 | 0.026 | 0.022 |
| gale 34 | Pacific | +96/120 | 90 of 105 | 0.14 | 0.20 | 0.044 | 0.023 | yes | 14% | 24% | 0.27 | 0.27 | 0.26 | 0.015 | 0.015 | 0.022 |
| storm 48 | Atlantic | +24/48 | 55 of 70 | 0.41 | 0.46 | 0.022 | 0.006 | yes | 55% | 50% | 0.28 | 0.16 | 0.53 | 0.048 | 0.055 | 0.006 |
| storm 48 | Atlantic | +72 | 38 of 70 | 0.32 | 0.36 | 0.021 | 0.002 | yes | 44% | 50% | 0.26 | 0.21 | 0.46 | 0.046 | 0.052 | 0.005 |
| storm 48 | Atlantic | +96/120 | 56 of 70 | 0.24 | 0.26 | 0.014 | 0.006 | yes | 37% | 40% | 0.20 | 0.16 | 0.32 | 0.035 | 0.039 | 0.010 |
| storm 48 | Pacific | +24/48 | 28 of 105 | 0.27 | 0.27 | 0.005 | 0.005 | NO | 41% | 39% | 0.19 | 0.08 | 0.34 | 0.015 | 0.019 | 0.005 |
| storm 48 | Pacific | +72 | 17 of 105 | 0.12 | 0.11 | 0.007 | 0.008 | NO | 24% | 36% | 0.10 | 0.05 | 0.17 | 0.011 | 0.014 | 0.005 |
| storm 48 | Pacific | +96/120 | 26 of 105 | 0.06 | 0.04 | 0.005 | 0.003 | NO | 56% | 5% | 0.05 | 0.03 | 0.07 | 0.006 | 0.008 | 0.004 |

## 64 kt, raw GEFS p64, NOT calibrated

| Resolution | Basin | Lead | Held-out cycles with event | Brier skill raw | Reliability error raw | Observed at raw 25-35% |
|---|---|---|---|---|---|---|
| 0.25 deg | Atlantic | +24/48 | 15 of 70 | 0.02 | 0.004 | 12% (138 cells) |
| 0.25 deg | Atlantic | +72 | 11 of 70 | 0.00 | 0.004 | 0% (50 cells) |
| 0.25 deg | Atlantic | +96/120 | 17 of 70 | 0.02 | 0.002 | n/a (29 cells) |
| 0.25 deg | Pacific | +24/48 | 4 of 105 | -0.10 | 0.002 | n/a (16 cells) |
| 0.25 deg | Pacific | +72 | 2 of 105 | -0.20 | 0.001 | n/a (0 cells) |
| 0.25 deg | Pacific | +96/120 | 4 of 105 | -0.08 | 0.001 | n/a (0 cells) |
| 0.5 deg | Atlantic | +24/48 | 15 of 70 | 0.03 | 0.005 | 8% (130 cells) |
| 0.5 deg | Atlantic | +72 | 11 of 70 | 0.01 | 0.004 | 2% (50 cells) |
| 0.5 deg | Atlantic | +96/120 | 17 of 70 | 0.02 | 0.002 | n/a (19 cells) |
| 0.5 deg | Pacific | +24/48 | 4 of 105 | -0.08 | 0.002 | n/a (15 cells) |
| 0.5 deg | Pacific | +72 | 2 of 105 | -0.16 | 0.001 | n/a (0 cells) |
| 0.5 deg | Pacific | +96/120 | 4 of 105 | -0.06 | 0.001 | n/a (0 cells) |

## Notes

- Pooled page columns are for comparison only (the 10-16 counts of GEFS+ENS+AIFS ENS share, 133 members, same held-out cycles and steps where all three ensembles exist; `page table` = `calibration_page_current.json` (34 kt raw), `refit table` = `calibration_refit.json`, approved 10-17).
- Cell counts overstate the evidence: weeks are the independent sample, and no intervals are computed.
- One winter; the fit and the held-out weeks are both winter 2025-26.
- Truth is the ASCAT box mean, not an analysis; analyses read storm force lower (10-16).
