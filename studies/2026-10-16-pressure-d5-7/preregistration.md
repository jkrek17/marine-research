# Day 5-7 lows: fixed before any results (2026-10-16 05:30Z)

Jason's choices (thread, 05:01Z): judge on low position and depth; use all runs; output one best guess plus a confidence score.

## Sample
- 12Z runs, 1 Mar 2025 to 8 Oct 2026, leads +120, +144, +168 h. Basins: N Atlantic 30-67N 75W-0, N Pacific 30-67N 160E-115W.
- Truth: mean of the GFS and IFS 12Z analyses (project standard).
- Held-out set (switched 05:45Z, before any scoring, to the research kit's fixed set shared by all studies): ISO week w of ISO year y is held out when (y*53 + w) % 5 == 0, judged on the run date. That is 18 weeks from Mar 2025 to Oct 2026, 9 of them in Nov-Mar. Tuning uses only runs where neither the run date nor the valid date is in a held-out week, so no tuning case shares weather with a held-out one. Within tuning, choices are made by leave-one-month-out. Held-out results are reported for all 18 weeks and for the winter ones.

## Lows
- Analysed low: local minimum of the analysis mean over 13x13 cells (~3 deg), below 1000 hPa, at least 3 deg inside the box. Deep: below 980 hPa.
- Forecast low (any system): same rule on its field, below 1010 hPa, anywhere in the box.

## Scores, per lead and basin, against GFS, IFS and AIFS each
1. Position error: for each analysed low, the distance to the nearest forecast low, capped at 1000 km (a miss costs 1000 km).
2. Depth error: forecast central pressure of that nearest low minus the analysed one (if within 1000 km; otherwise the forecast pressure at the analysed centre). Mean (bias) and mean absolute.
3. Hits: analysed lows with a forecast low within 300 km. False lows: forecast lows below 1000 hPa with no analysed low below 1005 hPa within 500 km.
4. Significance: paired differences resampled by whole weeks (2000 draws), 95% intervals.

"Beats" a model = position error and depth MAE both lower, with false lows no higher, on the held-out set; reported separately for all lows and deep lows.

## Confidence score
The chance that a forecast low has an analysed low within 300 km, from the share of members that carry it. Judged by reliability on the held-out set.

## Settings locked before the held-out score (2026-10-16 08:10Z)
Chosen on tuning runs only (winter 2025-26 plus Mar-Aug 2025), comparing at equal false-low rates:
- Member-vote lows: GEFS, ENS and AIFS ENS each count as one block; GFS, IFS and AIFS runs 0.3 each. Support radius 450 km. Depth = weighted median of the voters' own central pressures. No lagged runs (no gain), no depth calibration (it deepened lows past 1000 hPa and added false lows for no depth gain).
- Keep threshold per lead set on tuning runs so the vote's false-low rate equals IFS's (the middle model). Reason: Jason's rule that a miss costs more than a false alarm, without over-warning. The held-out report also gives the vote at each model's own false-low rate.
- Confidence: logistic fit on tuning lows of P(analysed low within 300 km) from support, spread, lead and depth.
- Depth error rule kept as preregistered (nearest forecast low within 1000 km, else the field at the analysed centre); rk.score's miss_depth="field" variant differs only for lows matched 300-1000 km away.

## Spread display check (fixed 2026-10-16 12:05Z, before running)
Jason asked for a measure of spread with the best-guess lows. Same locked vote settings and keep thresholds (`results/final.json`).
- Position ellipse per kept low: weighted covariance of the voters' own low centres (east/north km about the vote position), plus a 50 km floor in each direction. One scale factor per lead, fitted on tuning lows so the 50% ellipse holds the verifying analysed low half the time.
- Depth range per kept low: weighted 10th-90th percentile of the voters' own central pressures, widened about the median by one factor per lead fitted on tuning lows to hold the verifying analysed pressure 80% of the time.
- Verifying analysed low: the nearest analysed low below 1005 hPa within 1000 km of the vote low (the confidence score already covers whether the low exists). Also reported with lows that have none counted as outside.
- Pass: on held-out lows, the 50% and 90% ellipses and the 80% (and 50%, 25th-75th) depth ranges hold their stated share within 5 points at each lead.
