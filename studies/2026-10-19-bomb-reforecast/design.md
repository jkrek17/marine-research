# Bomb watch day 6-7 on 20 winters of GEFS reforecasts: design card

**Question** (Jason's words): "Do we calibrate the ensembles bomb probability", "Can you fix it", "Pre 2005 era data?", "Go ahead".

**What would change if the answer is yes:** the lab's day 6-7 bomb watch shows calibrated percentages (as day 5 does) instead of capped low/medium/high levels, with the top of its curve set from 20 winters instead of a few storms.

**Truth:** ERA5 mean sea-level pressure at 00 UTC (a reanalysis, used here as a proxy analysis), with the same low finder and bomb rule as the live layer (`rk.bomb`): an analysed bomb ending within 500 km of a 2 deg ocean cell.

**Baseline to beat:** the live recipe, a two-number logistic remap of the member share per lead (`rk.calibrate.fit_logistic`), which on the 2025-26 held-out weeks read low above ~35% at day 6-7.

**Win means (decided now):** on held-out seasons, at +144 h and +168 h:
- The chosen remap has a reliability slope of 0.8-1.25, and stated 30%+ verifies within 5 points on average.
- Its Brier skill against climatology is above zero (lower bound > 0).
If the plain logistic already does this, the 2025-26 shortfall was a few storms, and days 6-7 can show numbers. If only a more flexible top end (pooled curve, `fit_pooled` with the logistic as prior) does it, that curve shape goes to the live remap. If neither does, the levels stay.

**Cases:** GEFSv12 reforecast, 00 UTC runs every other day, 1 Nov to 31 Mar, winters 2000-01 to 2018-19 (about 1,450 runs). Leads +120, +144 and +168 h (plus +96 h for the 24 h window). N Atlantic and N Pacific boxes, 30-67N. Held out: the fixed `rk.cases.held_out` ISO weeks (about 1 in 5).

**Data:** nothing in the store yet. GEFS reforecast MSLP (AWS `noaa-gefs-retrospective`, byte ranges per lead): 5 members x 4 leads x 0.9 MB = 18 MB a run, about 26 GB. ERA5 MSLP (ARCO zarr, 2.2 MB a time), 00 UTC every winter day, about 7 GB. About 33 GB in all, under the 50 GB line. Fields are reduced to lows straight away; only the lows (small) are kept, in `RK_DATA/bomb-reforecast/`. Pulls go through `rk.fetch` (build windows waited out).

**Reused / new:**
- Reused: `rk.bomb` (lows, 24 h tracking, Bergeron rule, cells, ocean mask), `rk.calibrate`, `rk.compare`, `rk.cases.held_out`, and the scoring of `studies/2026-10-19-bomb-d5-7/score.py`.
- New in `rk/`, with tests: `rk.fetch.gefs_reforecast` (any reforecast field and lead) and `rk.truth.era5` (any ARCO ERA5 single-level field). Both are useful beyond this study.

**Methods tried, simplest first:**
1. Raw member share.
2. Logistic remap per lead, fitted on training weeks (the live recipe).
3. Pooled remap with the logistic as prior (more freedom at the top end).

**Known traps:**
- Five members make a coarse share (0/20/40/60/80/100%). The reforecast can set the shape of the curve, but not the live 132-member numbers one for one.
- ERA5 smooths the deepest lows a little.
- Neighbouring cells share a storm, so intervals resample whole weeks.

**Out of scope:** ECMWF reforecasts (not open); changing the 500 km radius or the bomb rule.
