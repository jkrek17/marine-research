# Bomb watch day 6-7 on 20 winters of GEFS reforecasts

*2026-10-19 · N Atlantic and N Pacific, 30-67N, 00 UTC · Nov-Mar 2000-01 to 2018-19 · 1,491 runs, 308 held out in 89 weeks · truth: ERA5 (a proxy, not the desk's analyses)*

## The answer
No: the 20 winters do not let the lab show percentages at day 6-7, so the capped low/medium/high levels stay. A 5-member reforecast almost never earns a calibrated 30%+ at day 6-7, which is exactly where the live 160-member blend reads low. That leaves only 25 (day 6) and 8 (day 7) held-out cells to test there, and those few over-read badly. What the sample does show is that a day 6-7 member bomb signal carries small but real skill over climatology once it is remapped.

## The evidence
Held-out weeks; remap fitted per lead on training weeks (pooled curve, chosen over the logistic by training-week cross-validation).

| Lead | Raw share BSS | Remapped BSS vs clim | Reliability slope | Stated 30%+: n, stated, verified | Passes |
|---|---|---|---|---|---|
| +120 h | -0.20 [-0.31, -0.11] | +0.045 [+0.017, +0.070] | 0.72 | 539, 41%, 28% | (not in rule) |
| +144 h | -0.09 [-0.18, -0.03] | +0.045 [+0.030, +0.060] | 1.19 | 25, 78%, 24% | No |
| +168 h | -0.22 [-0.30, -0.16] | +0.015 [+0.006, +0.025] | 1.01 | 8, 93%, 38% | No |

*Intervals: 95%, resampling whole weeks.*

The raw 5-member share is over-confident, the opposite of the live blend. On training weeks (cells, events, how often it verified):

| Members bombing | +120 h | +144 h | +168 h |
|---|---|---|---|
| 1 of 5 | 29,709, 7% | 37,208, 6% | 40,714, 5% |
| 2 of 5 | 7,988, 15% | 8,400, 13% | 8,030, 12% |
| 3 of 5 | 3,254, 25% | 2,642, 18% | 1,930, 13% |
| 4 of 5 | 1,125, 37% | 764, 24% | 422, 17% |
| 5 of 5 | 326, 50% | 194, 43% | 39, 10% |

## What it does not show
- Whether the live blend's day 6-7 top end can be trusted. The reforecast has 5 members where the live blend has about 160, so its spread and its top end behave differently, and the curve does not transfer.
- The 30%+ failure comes from the pooled curve's last knot (5 of 5 members), which is set by the logistic prior on 194 and 39 training cases. A different curve would change those few cells, not the answer.
- The slopes of 1.19 and 1.01 pass the rule only because 25 and 8 cells pin them; they are not evidence of good calibration.
- Held-out runs are chosen by init week, as in the day 5-7 study, and training drops every row whose valid time a held-out row also verifies at (LESSONS.md). The first run lacked that drop (29% of held-out +168 h rows shared ERA5 storms with training); adding it moved no BSS by more than 0.001. With held-out chosen by valid week instead, no lead passes either (+144 h: slope 0.86, 15% verified for 77% stated, n=55; +168 h: slope 0.70).

## How it was done
- Truth: ERA5 MSLP at 00 UTC (`rk.truth.era5`), bombs by `rk.bomb` (1 Bergeron in 24 h, within 500 km of a 2 deg ocean cell). ERA5 is a proxy for the desk's GFS+IFS analyses.
- Forecast: GEFSv12 reforecast c00 and p01-p04 (`rk.fetch.gefs_reforecast`), same bomb rule per member.
- Baseline: per-cell bomb frequency over training weeks.
- Cases: 00 UTC every other day, Nov-Mar, 1,490 runs as designed plus one test run (2010-01-03) kept. Held out: `rk.cases.held_out` weeks of the init time, scored once.
- Pass rule (design.md): at +144 and +168 h, slope 0.8-1.25, stated 30%+ within 5 points, BSS lower bound above 0.
- Code: `studies/2026-10-19-bomb-reforecast/` (`build.py lows`, `build.py cells`, `score.py`); data: `RK_DATA/bomb-reforecast/` (lows and cells, not in git).
- Checked by: a second agent recomputed every number in `results/scores.csv` and `results/reliability.csv` from the cell table without reading this write-up. All matched; its bootstrap intervals differed only in the third decimal. It also found the shared-valid-time overlap, which was then removed from training and the scores rerun (BSS changed by 0.001 or less, stated 30%+ by 1 point).
