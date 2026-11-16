# Findings: best MSLP forecast to day 7 (2026-11-16)

Winter 2025-26 (1 Nov - 31 Mar), 00Z and 12Z, N Atlantic and N Pacific, 604 basin-cycles. Truth = mean of GFS and IFS analyses; every sign checked against each analysis alone. Noise floor (GFS vs IFS analysis): RMSE 0.56 hPa, low position 119-130 km mean / ~59 km median. Headline numbers recomputed independently (`verify.py`): match to rounding.

## Part A: most likely field
Mean low position error, km (analysed lows < 1000 hPa; miss = 1000 km), +24..+168:

| | 24 | 48 | 72 | 96 | 120 | 144 | 168 |
|---|---|---|---|---|---|---|---|
| ECMWF (IFS) | 116 | 177 | 228 | 285 | 325 | 392 | 439 |
| GFS | 126 | 183 | 242 | 300 | 358 | 408 | 468 |
| GFS+ECMWF mean | 119 | 193 | 237 | 300 | 345 | 393 | 448 |
| AIFS | 171 | 233 | 280 | 336 | 392 | 437 | 489 |
| ENS mean | 176 | 274 | 344 | 409 | 467 | 512 | 573 |
| GEFS mean | 309 | 373 | 436 | 509 | 561 | 613 | 669 |
| Aligned blend, all runs | 182 | 258 | 317 | 377 | 429 | 447 | 503 |
| Outlier-drop blend | 185 | 269 | 325 | 396 | 440 | 494 | 535 |
| Member vote (12Z) | | | | | 297 | 328 | 365 |

Median position: IFS 68 121 174 233 267 345 390; GFS+ECMWF 64 127 179 234 284 338 401 (a tie).
RMSE hPa: IFS 0.70 1.32 2.17 3.20 4.46 5.88 7.38; GFS+ECMWF 0.62 1.24 2.04 2.99 4.10 5.36 6.71; GFS+ECMWF+AIFS 0.54 .. 6.03; aligned 0.53 .. 5.92.
Strong lows (analysed < 980, misses charged field depth) forecast-minus-analysed bias at +168: IFS +8.0, GFS+ECMWF +11.7, aligned +12.4, aligned + depth fix (det runs) +8.7 hPa; GFS+ECMWF mean + depth fix +11.0 hPa (fix recovers only 0.2-0.8 hPa on a two-run blend).
False lows per map: IFS 0.52 -> 2.50 (+24 -> +168); GFS+ECMWF 0.20 -> 1.75; aligned 0.06 -> 0.88.

1. No blend beats ECMWF on mean position at any lead (win rule: none passes at raw thresholds, best possible or AWIPS set). GFS+ECMWF ties ECMWF at +24 (+3.2 km, interval -6 to +12), +144 and +168; it is 9-20 km worse at +48 to +120 (intervals exclude 0). Medians are close (no interval). Days 1-2 depend on the truth: against the GFS analysis alone GFS beats ECMWF by 22 / 11 km; against the IFS analysis ECMWF wins by ~50 km at day 1. ECMWF draws more lows (5.8 per map, 0.5-2.5 false) and a miss costs 1000 km.
2. Blends are closest on the whole field (RMSE), but smoother (sharpness 0.73-0.82 at +168 vs 0.93) and shallower on strong lows.
3. Warping each run's low to the consensus spot before averaging: within +-5 km of the plain mean of the same runs (`warp_effect.csv`). Ensemble means in the field lower RMSE but cost ~60 km in position at +24 (they wash out weaker lows: GEFS mean finds 2.6 lows per map vs IFS 5.8).
4. Depth fix (median of runs' own depths, 250 km bowl, deepen only <= 8 hPa): cuts strong-low bias 1.7-2.7 hPa at day 7 on blends of 3+ runs, only 0.2-0.8 hPa on the GFS+ECMWF mean; does not move lows. Every source is shallow on strong lows at day 7 (ECMWF +8.0, GFS +10.0, vote +7.6 hPa; misses charged field depth).
5. Outlier drop (desk habit): the dropped run was the closest to the analysed low in 7-13% of drops (X = 300 km, by lead). The drop is usually right, but the blend left behind (which keeps the ensemble means) loses to ECMWF by 69-115 km. Tested on GFS, ECMWF, AIFS, AI-GFS; CMC and UKMET not in the store.
6. Member vote (day 5-7, 12Z): 34 / 67 / 64 km better than ECMWF at +120/144/168 (intervals exclude 0; same sign on held-out weeks; Pacific +120 mixed), with +0.18-0.19 false lows per map. Not blind (its settings were chosen on overlapping full-year weeks). Needs ENS and AIFS-ENS members: not on AWIPS.
7. Equal-false-low check: prominence thinning strips ECMWF's real lows as fast as its false ones (+24: 116 -> 307 km), so ECMWF's extra lows are mostly real secondary lows; that comparison is reported, not used as the headline. Over-water-only lows: same conclusions.
8. AI-GFS: 158 basin-cycles, mostly held-out weeks; scored but too few for a choice. The AWIPS answer rests on GFS + ECMWF + GEFS mean.

## Part B: what probability says (day 5-7, 12Z, members; calibrated on Mar 2025 - Oct 2026 tune weeks)
- Chance the low exists (isotonic on vote support): Brier skill vs base rate +0.21 / +0.17 / +0.10 winter (held-out +0.22 / +0.19 / +0.13). Reliable at +120 in winter; thin top bins miss at +144/+168; winter under-forecast 4-6 points overall (no season term).
- Depth chance < 990 / < 980: direct product fails reliability (winter 2-6 points low overall, larger in mid bins; deep lows are also likelier to exist); recalibrated per threshold passes only at some leads, so no depth-threshold chance is ready to show; < 970 skill ~0; < 960 not verifiable.
- 10-90% depth range: covers 80 / 84 / 82% in winter (target 72-88). Analysis runs 1.0-1.7 hPa (winter) / 1.7-3.0 hPa (year) deeper than the vote median; a bias shift is needed to beat climatology on CRPS (+0.05 / +0.07 / +0.03).
- Position circles (50% / 80%): 391/751, 440/764, 480/777 km at +120/144/168; by member support, high-support lows 231-327 km (50%), low-support 634-642 km. Tercile circles beat lead-only circles.
- Alternative scenarios (>= 20% of members, > 300 km away): position alternatives shown on 11 / 9 / 7% of lows; verified 37 / 34 / 28% in winter (placebo 7-9%; main low base rate 14-20%).
