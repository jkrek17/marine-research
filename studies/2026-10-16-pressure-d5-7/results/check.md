# Independent check: findings.md (day 5-7 lows, held-out winter)

Checker recomputed from lows_heldout.csv / maps_heldout.csv before reading findings.md. Truth = anl (GFS+IFS analysis mean).

## 1. Recomputation vs comparisons.csv (held_out_winter, vote == 'vote')
- Runs: 42 distinct cycles (7 per month: 2025-03, 2025-11, 2025-12, 2026-01, 2026-02, 2026-03). ISO weeks: 6. Lows <1000 hPa per lead: 348/338/334; deep <980: 75/68/65.
- All 84 rows (pos_km, depth_abs_hpa, hit300 for all<1000 and deep<980, plus false_lows; steps 120/144/168; gfs/ifs/aifs/gmean): model_mean, vote_minus_model and n match exactly (max abs diff 1e-13). No mismatch.
- Week-block bootstrap (6 ISO weeks, 2000 draws, my seed) for all pos_km rows: agrees with lo/hi within Monte Carlo noise (typically 0-5 km; worst deep<980 GFS +120 lo -147.5 vs -137.4, +168 hi +7.3 vs +2.8). No significance flag changes. ECMWF all<1000: +120 [-57.9,+19.5] vs csv [-54.8,+19.6]; +144 [-102.2,-36.3] vs [-103.1,-37.3]; +168 [-84.2,-21.3] vs [-81.7,-20.7].
- Caveat: only 6 resampling blocks; percentile intervals from 6 clusters are rough and likely too narrow.

## 2. fig_confidence.csv
n = 1306+896+544+288+21 = 3,055 (matches). Bins stated->verified: 13.9->13.6%, 28.3->29.2%, 49.5->49.8%, 67.8->69.1%, 84.4->90.5% (n=21). These are ALL held-out weeks (report.py title), not winter only.

## 3. equal_false_lows_heldout_check.csv (held_out_winter)
Position vote-minus-model: ECMWF -2.4/-45.4/-37.1, GFS -48.0/-33.4/-29.3, AIFS -31.5/-23.3/-39.1 km; 6 of 9 exclude zero (ECMWF+120, GFS+144, GFS+168 do not). Depth: -0.45 to -4.06 hPa, 8 of 9 (AIFS +144 hi = +0.006 crosses zero). Ranges quoted in findings are correct.

## 4. findings.md: numbers and claims
Numbers off (minor):
- L6 "45-65 km closer than ECMWF" at day 6-7: actual 46-63 km (-63.0, -45.8).
- L27 deep lows "2-4 hPa closer [than ECMWF] in central pressure" at day 6-7: actual 3.2-4.1 hPa.
- L35 confidence bins: "14% -> 13%" is 13.9 -> 13.6 (both ~14%); "50% -> 50%" is 49.5 -> 49.8; "85% -> 90%" is 84.4 -> 90.5. Also L6 "lows stated at 50% verified 50%" fine. The 3,055 lows are all held-out weeks, not the winter sample the page is about; say so.
- L3 "winter result (Nov 2025-Mar 2026)": the held-out winter set includes 7 runs from March 2025 (one of the 6 weeks). Fix the date span.
Claims not supported / oversold:
- Title "a member vote beats GFS, ECMWF and AIFS": not on every metric. vs ECMWF +120 position ties (-9 [-55,+20]); vs GFS +144 position ties (-33 [-93,+2]); hit-within-300 km vs ECMWF +120 the vote is significantly WORSE (-0.069 [-0.101,-0.025]), +168 -0.042 [-0.077,+0.009]; deep lows +120 vs ECMWF/GFS tie. Hit300 is not reported anywhere in findings.md although it is in the CSV; the position metric (misses capped at 1000 km) is standing in for both detection and placement.
- L6 "33-39 km closer than GFS" at day 6-7: +144 interval [-93,+2] crosses zero; only +168 is significant.
- L6 "It draws as many false lows as ECMWF, within 0.3 per map": the vote draws significantly MORE at +120 (+0.19 [+0.04,+0.31]) and +144 (+0.21 [+0.12,+0.31]). Say "0.2-0.25 more per map".
- L6 "Held to AIFS's false-low count ... central pressure 0.5-1.5 hPa closer": +144 is 0.45 [-1.12,+0.006], not significant.
- L25 "It still placed lows closer than every model at every lead": 3 of 9 intervals cross zero (stated in the same sentence, so the lead clause oversells). "The one tie is ECMWF at +120 h on position" is false: GFS +144 (-33 [-92,+3]) and GFS +168 (-29 [-81,+8]) also cross zero in that check, and AIFS +144 depth too.
- L8 "misses three quarters of them": grand-mean hit300 is 32/28/22% (misses within 300 km 68-78%; three quarters only at day 6-7). Under the page's own miss definition (nothing within 1000 km, L11) it misses 16-21%. State the 300 km radius. "10 hPa too shallow by day 7": signed error +10.2 hPa at +168, correct.
- L27 mixes leads: ECMWF range is day 6-7, AIFS "67-117 km" includes day 5 (-66.6). "same central pressure error" vs AIFS OK (all intervals cross zero).
- L38 "all weeks ... agree with winter": broadly true for position/depth, but all-weeks ECMWF false-low differences at +144/+168 are not significant and GFS +144 position becomes significant; fine as stated, no change required.
Table (L15-23): every entry matches comparisons.csv to rounding.
