# Which hurricane-force winds aloft reach the surface? No physical input adds to the live core model

*2026-10-18 · winter Nov 2025 - Mar 2026 · the core-ceiling cases (hf-low archive HF and S fixes, every synoptic hour, +24/+48/+72 h, at least 200 ASCAT cells seen within 500 km) · truth: ASCAT real 10 m wind, intercalibrated, rain dropped · pre-set rule: `design.md`*

## The answer
Jason asked for a downscaling that makes physical sense. The idea was to cap the 10 m wind by the 925 mb wind and let stability, cold advection and position in the low decide how much of it mixes down. This tested whether those inputs can tell which cells with 64 kt at 925 mb have 64 kt at the surface.

**It fails the pre-set rule.** On the held-out weeks the physical model ranks those cells no better than the live core probability P, which already sees most of the same inputs. At day 1-2 P is clearly better; the physical model's own skill comes mostly from the blend wind r10, which P also uses.

| Held-out weeks | ROC area |
|---|---|
| Physical model (logistic, fit on tune weeks) | 0.801 |
| Live core probability P | 0.805 |
| 925 mb speed alone | 0.653 |

- Physical model minus P: -0.004, 95% interval [-0.106, +0.064].
- Physical model minus 925 mb speed: +0.149 [-0.069, +0.189].
- Brier skill 0.09 (positive, but the rule needs both intervals above zero).
- It rests on 5 held-out weeks (4 with any 64 kt cell), 13 storms, 7 of them with ASCAT hurricane force, and 504 distinct 64 kt cell-times. Each cell is scored once per lead, so the table counts 5,515 cells and 1,146 at 64 kt. Intervals resample whole weeks.

By lead (held-out, same fit; an independent recheck):

| Lead | Physical model | P | 925 mb speed | Model minus P |
|---|---|---|---|---|
| +24 | 0.824 | 0.878 | 0.644 | -0.054 [-0.085, -0.009] |
| +48 | 0.784 | 0.850 | 0.624 | -0.066 [-0.191, +0.004] |
| +72 | 0.788 | 0.660 | 0.730 | +0.129 [-0.070, +0.255] |

The pooled tie is P ahead at day 1-2 and P falling off at day 3. That day 3 drop is a lead for later, not a finding: it rests on 4 informative weeks.

- The blend r10 alone scores 0.780 held-out, steady across leads. The full physical model adds +0.021 [-0.115, +0.058] to it.

The tune weeks said the same before the held-out score: P alone 0.829, the blend r10 alone 0.795, the physical model 0.747 in week-grouped cross-validation (the boosted version 0.722).

## What it means for the downscaling
- **The 925 mb wind alone sorts these cells weakly** (0.65 held-out pooled: 0.64 / 0.62 / 0.73 by lead; 0.77 tune). Momentum aloft is necessary, as the core-ceiling check found, and it is a poor guide to where it reaches the surface.
- **The stability signal is real but small.** Unstable air (SST minus T850) and cold advection lean the right way one at a time (ROC 0.60 and 0.58-0.63 on tune weeks). In a reduced model (925 mb speed, SST-T850, 850 mb advection, distance) momentum and stability keep physical signs in 100% and 97% of week bootstraps, cold advection adds nothing once stability is in, and it scores 0.779 held-out, under P. These inputs are already inside the core model.
- **The core model already knows which cells are the strongest.** It was trained for 48 kt, yet it ranks the 64 kt cells as well as anything tried here. So a hurricane-force tier would start from P, not from a new physical mixing model.
- **A 925 mb cap would also clip real hurricane force.** A quarter of ASCAT's 64 kt cells near these lows (1,286 of 5,208) have a three-model mean 925 mb speed under 64 kt, so a strict cap built on the mean would remove them before any mixing rule ran.

A physically bounded downscaler as designed is not worth building on this evidence. No page change follows from this study.

## The coefficients
Fit on all tune weeks, standardised. Signs of single inputs are all physical (more 925 mb wind, more instability, colder advection, more hurricane force; hurricane force favours the southwest side of the low). Together they are not readable, so the full model also fails the design's sign rule:
- 925 mb speed, its excess over r10, and r10 are exactly linked (excess = s925 - r10), so their three weights cannot be told apart.
- SST-T850 (+3.4) and SST-T925 (-2.5) correlate at 0.95 and oppose each other; dT flips to +0.38.
- 850 mb advection takes the warm-advection sign (+0.59) against 925 mb (-0.54), in 90% of week bootstraps.

That is one more reason not to read a mixing law from this model.

## How it was done
- **Cells:** every seen ASCAT cell within 500 km of a fix where the three-model mean 925 mb speed (as the core model uses it) is at least 64 kt. 303 cases scored; 543 skipped for too few seen cells and 12 for no forecast (`cases.csv`). 24,567 cells, 3,922 at 64 kt in ASCAT; 258 of the 303 cases are HF fixes, 276 Atlantic.
- **Predictors, set before fitting:** 925 mb speed, its excess over the blend, SST-T850, SST-T925, dT, 850 and 925 mb temperature advection, the 850 mb temperature gradient, distance and bearing from the fix, and the blend.
- **Methods:** logistic regression and a shallow boosted model monotone in 925 mb speed and SST-T850. The one with the higher week-grouped cross-validation ROC area on tune weeks (logistic) was scored once on held-out weeks (`rk.cases.held_out`).
- **Code:** `cells.py` (cell table, reuses the core-ceiling case loop; writes `RK_CACHE/extra/hf-mixing/cells.parquet`), `fit.py` (tune results, then `--final` once). Results: `tune_results.md`, `final_results.md`, `final_results.json`.

## Limits
- Five held-out weeks (four informative) is thin; the intervals are wide. The tune weeks point the same way.
- The split is by valid week, so some held-out cells come from cycles started in tune weeks (shared forecast runs, not shared truth). One storm spans both; dropping it changes nothing (0.805 vs 0.805).
- Cells near one low are not independent. Whole weeks are resampled for that.
- ASCAT is unsettled above 56 kt, and the "64 kt" line sits in that range.
- It is a North Atlantic result. The Pacific has 3 tune and 11 held-out 64 kt cells, too few to say anything, limited by ASCAT sampling as in the core-ceiling check.
