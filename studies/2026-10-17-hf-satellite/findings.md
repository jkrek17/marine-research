# HF satellite pilot

*2026-10-17 · North Atlantic and North Pacific boxes · seasons 2024-25 and 2025-26 · 616 HF and storm-force fixes of 165 storms; held out 100 fixes, 31 storms, 12 weeks · truth: hf-low archive category (OPC), ASCAT as referee for 2025-26*

## The answer
Not passed, but close: infrared imagery separates the analysts' HF label from storm force a little better than central pressure and latitude, and the pilot does not show that it sees wind the pressure does not. Seven simple IR measures raised the held-out ROC area from 0.59 to 0.67 (+0.08, interval +0.02 to +0.13), but the pre-set rule also needed the Brier gain's interval below zero, and it reaches +0.001 (-0.012, interval -0.027 to +0.001). The gain comes from the Pacific (33 held-out fixes); the Atlantic shows none on the tuning weeks and an uncertain +0.04 held out. Against ASCAT the imagery ranked the peak wind no better than pressure (rank correlation 0.22 vs 0.34, 88 fixes, difference not significant). What differs on average: at hurricane force colder cloud tops wrap around the left of track and behind the centre within about 500 km.

## The evidence
| Method (held-out weeks) | ROC area | Brier | vs baseline |
|---|---|---|---|
| Baseline: logistic on central pressure and latitude | 0.593 | 0.203 | — |
| Pressure, latitude and seven IR measures (logistic) | 0.671 | 0.191 | ROC +0.078 [+0.022, +0.126]; Brier -0.012 [-0.027, +0.001] |
| Same inputs, gradient boosting | 0.587 | 0.218 | worse than the logistic, dropped |

| Basin, held out | Fixes (HF / storm) | Baseline ROC | With IR ROC |
|---|---|---|---|
| Atlantic | 49 / 18 | 0.590 | 0.629 |
| Pacific | 22 / 11 | 0.612 | 0.748 |

*Intervals: 95%, resampling whole ISO weeks (12 held-out weeks; Brier with 10,000 draws, see Checked by). Tuning weeks, 5-fold by storm: baseline 0.634, with IR 0.665 (Atlantic 0.644 vs 0.645, Pacific 0.627 vs 0.693).*

ASCAT referee, winter 2025-26 (Nov-Mar, fixes with at least 300 ASCAT cells within 500 km and 90 min, rain dropped, real 10 m wind): 88 fixes (74 HF, 14 storm) of 50 storms. The archive label is consistent with ASCAT, on only 14 storm-force fixes: median ASCAT peak 62.7 kt at HF fixes vs 55.9 kt at storm-force fixes; 45% vs 7% reach 64 kt (ASCAT reads low at hurricane force, so most HF fixes stay under 64 kt). 70 of the 88 are tuning-week fixes scored out of fold, so this is not a held-out test. Rank correlation of each model's HF chance with the ASCAT peak: baseline 0.34, with IR 0.22 (difference -0.12, interval -0.31 to +0.06, 22 weeks).

![At hurricane force, colder cloud wraps around the left of track and behind the centre than at storm force](fig/composites.png)

Tuning-week medians, HF vs storm-force fixes: coldest 5% of cloud tops within 500 km 236.6 vs 240.4 K; share of cloud tops below -40 C within 500 km 1.8% vs 0.5%; centre (< 150 km) warmer than the 150-500 km ring by 4.9 vs 3.2 K; 12-sector asymmetry 12.0 vs 10.4 K.

## What it does not show
- Wind. The label is the analysts' call, made partly from the same imagery and from ASCAT; on the ASCAT-seen fixes the IR model ranked the peaks no better than pressure. 88 fixes is thin.
- Anything ahead of time. This scores fixes already at storm or hurricane force, not whether a low will reach HF in 12-24 h.
- Storms that never reached HF: every storm-force fix here belongs to a storm that was HF at some point (before or after), so the contrast mixes development and decay stages.
- Water vapour and visible: GridSat's water-vapour channel is empty in these years, so the dry slot is seen only in IR.
- High latitude: geostationary view angles are 63-75 deg at 55-60N; 20 HF and storm-force fixes were dropped for a partial view (crop under 90% seen within 1000 km), 39 HF fixes have no central pressure in the archive and were dropped, and the western Pacific outside the basin box is not in the sample (of 506 HF and 169 storm-force fixes in the boxes, 452 and 164 were scored; the design's 555 and 197 counted fixes outside the basin boxes).

## How it was done
- Truth: hf-low archive (`rk.truth.hf_archive`), HF fixes positive, S fixes negative; ASCAT (`rk.truth.ascat`) as referee only.
- Imagery: GridSat-B1 v02r01 11 um IR (`irwin_cdr`), all geostationary satellites merged, read by byte range with the new `rk/satellite.py` (710 times, about 9 GB streamed, 1.4 GB stored as truth kind `gridsat`, published to the data releases). Crops: 1200 km half-width, 10 km pixels, motion up (heading from the neighbouring archive fixes).
- Features (fixed in `design.md` before the pull): cold-cloud share within 500 and 1000 km, 5th-percentile Tb within 500 km, centre minus ring, warm share right-rear (dry slot), cold share left half (cloud head), sector asymmetry.
- Cases: seasons 2024-25 and 2025-26; a storm is held out when its first fix falls in a held-out week (`rk.cases.held_out`), scored once with `run.py --final`. Composites from tuning weeks only.
- Code: `studies/2026-10-17-hf-satellite/` (`pull.py`, `features.py`, `run.py`, `ascat_check.py`, `figures.py`); results `features.csv`, `results.csv`, `scores.csv`, `ascat.csv`.
- Checked by: an independent agent recomputed every headline number from `results.csv`, `ascat.csv` and `features.csv` without reading this write-up, and refit the logistic model (identical probabilities). All point estimates matched. It found the first draft's 'passes the rule' rested on one bootstrap seed: with 2,000 draws the Brier interval's upper end was -0.00003 at seed 0 and +0.001 to +0.002 at other seeds; with 10,000 draws it is +0.001 at every seed tried, so the rule is not passed. It also corrected the view-angle range and the partial-view count, and flagged that the left-of-track cold band is not clearly stronger in the Pacific in the feature medians; both fixed here.
