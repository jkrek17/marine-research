# Bomb watch, day 5-7: the member share is skilful at every lead and beats every model, but above ~35% it reads too low at day 6-7

*2026-10-19 · N Atlantic and N Pacific 30-67N, 12 UTC runs · 580 runs Mar 2025 to Oct 2026, scored on 119 held-out runs in 17 weeks · truth: anl (GFS+IFS analysis mean)*

## The answer
Counting the GEFS, ENS and AIFS ENS members that bomb a low (at least 1 Bergeron in 24 h) within 500 km gives a useful day 5-7 bomb chance. On held-out weeks it beats climatology by a Brier skill of **0.31 at day 5, 0.22 at day 6 and 0.14 at day 7** (all intervals above zero), and it beats GFS, ECMWF and AIFS's own yes/no at every lead. The single models do worse than climatology: a deterministic run that bombs a low at day 5-7 is wrong more often than right.

By the pre-set rule, **day 5 passes and days 6-7 do not.** The chances are reliable up to about 35%, but above that they read too low: at day 6, stated 40-50% verified 81%, and at day 7, stated 30-40% verified 69%. The two-number calibration fitted on training weeks did not fix that top end (reliability slope 1.33 at day 6 and 1.43 at day 7, against a 0.8-1.25 rule).

## The evidence
Held-out runs, 2 deg ocean cells, event = an analysed bomb ending within 500 km. Brier skill against climatology, with 95% intervals from resampling whole weeks.

| Lead | Calibrated share | Raw share | GFS yes/no | ECMWF yes/no | AIFS yes/no | ROC area (share) | Reliability slope | Event cells |
|---|---|---|---|---|---|---|---|---|
| +120 h | +0.31 [+0.08, +0.42] | +0.32 [+0.11, +0.42] | -0.87 | -0.41 | -0.03 | 0.98 | 1.15 | 617 |
| +144 h | +0.22 [+0.05, +0.30] | +0.22 [+0.06, +0.30] | -0.89 | -0.59 | -0.36 | 0.97 | 1.33 | 641 |
| +168 h | +0.14 [+0.05, +0.20] | +0.14 [+0.06, +0.19] | -0.77 | -0.68 | -0.23 | 0.93 | 1.43 | 707 |

The calibrated share's Brier score is lower than every model's at every lead, and the interval excludes zero each time (`results/scores.csv`). Analysed bombs per year: about 63 in the Atlantic box and 59 in the Pacific box, most of them October to April.

Reliability of the calibrated share, held-out (`results/reliability.csv`):

| Stated | Day 5 verified | Day 6 verified | Day 7 verified |
|---|---|---|---|
| 10-20% | 12% | 15% | 12% |
| 20-30% | 21% | 26% | 33% |
| 30-40% | 36% | 48% | 69% |
| 40-50% | 60% | 81% | 96% (24 cells) |
| 50%+ | 69-100% (129 cells) | 89-100% (40 cells) | none |

## What it does not show
- 34 held-out valid times also sit in the training rows used for climatology and calibration (truth only; see below).
- The top bins are thin (24 to 130 cells, a few storms each) and neighbouring cells share a storm, so the size of the under-reading above 35% is loosely known.
- One year and a half; 17 held-out weeks, about 6 of them winter.
- The analysis-mean low is the truth, and the analyses smooth the deepest lows a little, so some real bombs may be missing from the truth.
- Equal-weight pooling of the three ensembles (`p_eq`) was no better than counting members (`p_raw`, chosen on training weeks).

## How it was done
- Rules fixed before scoring: `preregistration.md` (one note added before scoring: AIFS ENS is optional because it is not archived before mid-2025).
- Lows: 13-cell MSLP minima below 1012 hPa, deduplicated within 150 km. 24 h track: nearest low of the same member within 1,200 km. Bomb: (p(t-24) - p(t)) x sin 60 / sin(mean lat) >= 24 hPa (`bomb.py`, `tests/test_bomb_d5_7_study.py`).
- Data: the day 5-7 study's stored member MSLP plus +96 h (`fetch96.py`). Cell table: `RK_DATA/bomb-d5-7/cells.parquet` (`build.py`). Scores: `score.py`.
- Checked by: a fresh agent with its own code from `preregistration.md` and the cell table recomputed the counts, climatology, Brier scores, raw-share BSS and intervals, ROC areas and reliability bins: all match to rounding. It found no duplicate rows or split overlap. One small leak: `valid_held` marks only valid times inside a held-out week, so +144/+168 h held-out runs spilling into the next week share 34 valid times with training rows (truth only, no forecasts). That favours climatology and the calibration fit slightly, so the skill above is if anything conservative.
