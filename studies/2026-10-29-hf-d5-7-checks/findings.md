# Hurricane-force lows at day 5-7: more members won't help, the run trend adds nothing, and the desk grid stops at day 5

*2026-10-29 · N Atlantic and N Pacific, 12 UTC runs · Mar 2025 to May 2026, 457 runs, scored on 98 held-out runs in 14 weeks (check 1: 70 runs in 10 weeks with all 133 members) · truth: OPC archive HF storms (T1), and only those ASCAT saw at 64 kt (T2)*

## The answer
At day 5-7, the share of the 133 GEFS, ENS and AIFS ENS members with a deep low near a cell (970 hPa or lower in the Atlantic, 960 hPa in the Pacific) has some skill for "an HF storm passes within 500 km", up to a Brier skill of 0.20 against climatology. **(1) More members would not help.** An unlimited ensemble from the same three systems would add only 0.002 to 0.004 Brier skill over the 133 we have. The bar was 0.02, so a rented-GPU AI ensemble is dropped. **(2) The trend from the run 24 h earlier adds nothing we can measure** (+0.00 to +0.01, every interval crosses zero). **(3) The desk's own grid can't be scored at day 6-7.** The NDFD oceanic wind grid ends near day 5.5 in the Atlantic and day 6.5 in the Pacific. At day 5 it puts 64 kt near 1 of 14 held-out Atlantic HF storms and none of 7 in the Pacific.

## The evidence
Held-out weeks; Brier skill against cell climatology, raw member share; 95% intervals from resampling whole weeks.

| Basin, lead | HF storms (T1 / ASCAT-confirmed) | Member share, 133 (T1 / T2) | Unlimited minus 133 (T2) | Trend gain (T2) |
|---|---|---|---|---|
| Atlantic +120 h | 13 / 7 | +0.10 / +0.13 | +0.004 [+0.003, +0.006] | +0.004 [-0.009, +0.021] |
| Atlantic +144 h | 14 / 10 | +0.16 / +0.20 | +0.004 [+0.003, +0.006] | +0.013 [-0.011, +0.046] |
| Atlantic +168 h | 13 / 8 | +0.15 / +0.18 | +0.004 [+0.002, +0.006] | not stored (+192 h) |
| Pacific +120 h | 6 / 5 | +0.11 / +0.11 | +0.003 [+0.001, +0.005] | +0.001 [-0.002, +0.003] |
| Pacific +144 h | 5 / 3 | +0.07 / +0.04 | +0.004 [+0.001, +0.047] | +0.009 [-0.007, +0.035] |
| Pacific +168 h | 5 / 2 | +0.09 / -0.00 | +0.004 [+0.001, +0.117] | not stored |

The share and unlimited columns use runs with all 133 members (Aug 2025 on); the trend column uses the logistic fits on all 98 held-out runs (`results/check1.csv`, `results/check2.csv`). Going from 8 to 133 members raises the Atlantic day 6 skill from +0.14 to +0.20 (T2). The curve is flat beyond about 64 members.

Desk at day 5 (`results/check3.csv`, T1, cells with a desk value):

| Basin | HF storms | Desk 64 kt near the storm | Desk 48 kt near the storm | Desk 48 kt false alarm (cells) |
|---|---|---|---|---|
| Atlantic +120 h | 14 | 1 (POD 6% of cells, no false cells) | 4 (POD 38%) | 77% |
| Pacific +120 h | 7 | 0 | 2 (POD 15%) | 89% |

At day 5 the member share has a lower Brier score than the desk's 48 kt yes/no in both basins (Atlantic -0.016 [-0.030, 0.000], Pacific -0.004 [-0.009, -0.001]).

## What it does not show
- The sample is small: 13-14 Atlantic and 5-7 Pacific archive HF storms in the held-out weeks, of which 2-10 were ASCAT-confirmed. The Pacific day 6-7 T2 numbers rest on 2-3 storms.
- Check 1 measures more members **from the same three systems**. A different model with stronger cores is a separate question.
- The desk grid covers only part of each box (about half the Atlantic cells and a quarter of the Pacific cells at day 5 have a desk value), so check 3 is scored there only. Its 64 kt Atlantic hits (21 cells) are all one storm.
- The desk grid is a 10 m wind forecast, not a warning. The desk may call HF days ahead in other products, such as the HSF and the outlook text, which were not scored here.
- Above a 30% chance the fitted share over-reads in the Atlantic (stated about 64%, verified about 50%; 360 held-out cells, a handful of storms).
- The depth line (970/960 hPa) and the logistic fits were chosen on training weeks against T1, not on ASCAT.

## How it was done
- Event: an archive HF fix within 500 km of a 2 deg ocean cell within +-12 h of the 12 UTC valid time. T2 keeps storms with ASCAT real 10 m wind of 64 kt or more within 300 km of one of their HF fixes, within +-3 h, at any pass time (Pacific 18 and 00 UTC passes included). In 2025-26, ASCAT confirmed 32 of 71 Atlantic and 9 of 32 Pacific storms. Cells near only unconfirmed storms are left out of T2 (`confirm.py`, `results/storms.csv`).
- Members: stored day 5-7 member lows (`mslpd57_*`) at the valid time; the depth line was picked from 940-990 hPa on training weeks (`build.py`, `score.py`).
- Check 1: 50 random subsets of 8, 16, 32 and 64 members (in proportion across the ensembles), and the fair Brier score (`rk.score.fair_brier`, Ferro 2014) for an unlimited ensemble.
- Check 2: logistic fit on training weeks of the share, against the share plus the change since the run 24 h earlier at the same valid time.
- Check 3: NDFD oceanic wind from the desk issuance made from the same run (`rk.desk`, new days 4-7-only read, ~13 GB streamed, 908 issuances, 7 not posted, 1 unreadable), maximum within 500 km (`desk_join.py`).
- Design: `design.md`. Deviations: the desk grid ends before day 6 in the Atlantic and day 7 in the Pacific, so check 3 is day 5 (and Pacific day 6, where the desk drew no 64 kt and no 48 kt near a storm). The ASCAT confirmation uses any ASCAT cell within 300 km (the same as the neighbourhood maximum named in the card).
- A first build paired archive storms with the wrong times (pandas 3 `Series.dt.to_pydatetime()` returns a re-indexed Series); a count check against the archive caught it before any result was used. `tools/check_repo.py` now flags that call, and a test pins the window match.
- Checked by: a fresh agent with its own code, reading only `design.md` and the saved tables, recomputed the training split, the depth line (970/960 hPa at every lead), every check 1 BSS and fair-minus-raw gap, the check 2 BSS and gains, and the check 3 counts, POD and false alarm ratios. All matched to the last digit shown. Its storm counts were taken over all 98 held-out runs (Atlantic 14/7, 14/10, 13/8; Pacific 7/6, 6/4, 6/3), one or two more than the 70-run subset in the table above. It did not recompute the intervals. It flagged the desk gaps (day 6-7, part of each box) and the one-storm 64 kt Atlantic hits, both stated above.
