# Warning forecast experiment

*2026-10-16 · Atlantic and Pacific high seas areas, 00 and 12 UTC · winter 2025-26 (1 Nov to 31 Mar), 24 and 48 h forecasts · 836 case-hours with a fully parsed desk text in 22 weeks (192 in the 5 held-out weeks) · truth: ASCAT for gale and storm, the OPC hurricane-force low archive for HF*

## The answer
Taking the strongest of GFS, ECMWF and AIFS 10 m wind at each point and adding a fixed offset clears the 80% mark in every category. With +1 kt it catches 96% of gale events, with +7 kt 97% of storm events, and with +12 kt 91% of hurricane-force lows. The desk caught 97%, 83% and 56%. The warned area is about a sixth (gale) to a quarter (storm, HF) of the desk's, and far less of it is false.

Two limits apply. Hurricane force rests on 86 lows, only 15 of them in held-out weeks. And the model areas are grid outlines, not the boxes and quadrants the High Seas text must use, which would make them larger.

## The evidence
Held-out weeks (5 weeks, 192 case-hours), desk-parsed hours only:

| Category | Method | Events caught [95%] | Warned area with no verifying wind | Warned areas with no verifying wind | Mean warned area, nm2 |
|---|---|---|---|---|---|
| Gale (516 events) | Desk (issued HSF) | 98% [96-99] | 70% | 22% | 1,461,000 |
| | Page blend, no offset | 77% [72-84] | 2% | 1% | 140,000 |
| | **Strongest model +1 kt** | **97% [95-98]** | **10%** | 19% | 246,000 |
| Storm (105 events) | Desk | 92% [80-97] | 69% | 41% | 142,000 |
| | Page blend, no offset | 40% [28-48] | 0% | 0% | 2,200 |
| | **Strongest model +7 kt** | **98% [97-100]** | **23%** | 41% | 37,000 |
| Hurricane force (15 lows) | Desk | 67% [58-83] | 62% | 37% | 6,400 |
| | Page blend, no offset | 13% [0-22] | 0% | 0% | 3 |
| | **Strongest model +12 kt** | **100%** | **59%** | **70%** | 1,700 |

*Intervals: 95%, resampling whole weeks (only 5, so they are rough). The rules were chosen on the other 17 weeks. There they caught 96%, 98% and 89% (desk 97%, 81%, 54%).*

Whole winter, by month (strongest model + offset vs desk, events caught):

| Month | Gale | Storm | Hurricane force |
|---|---|---|---|
| Nov | 96% vs 97% (358) | 97% vs 86% (71) | 73% vs 53% (15) |
| Dec | 96% vs 97% (590) | 97% vs 88% (145) | 97% vs 62% (29) |
| Jan | 94% vs 98% (395) | 95% vs 81% (129) | 96% vs 58% (24) |
| Feb | 98% vs 98% (408) | 100% vs 79% (100) | 100% vs 50% (10) |
| Mar | 95% vs 96% (339) | 99% vs 81% (74) | 75% vs 38% (8) |

Detection by lead time is 97% at 24 h and 94% at 48 h for gale (desk 98% and 96%), 99% and 95% for storm (desk 89% and 78%), and 93% and 88% for HF (desk 67% and 44%).

![The strongest model plus an offset catches as many gales as the desk and more storms and HF lows, with a fraction of the warned area](fig1.png)

## What it does not show
- **Hurricane force is a small sample.** It has 86 lows all winter and 15 in held-out weeks. November and March are weaker (73% and 75%, on 15 and 8 lows).
- **"Caught" for HF is generous.** It counts any warned cell within 500 km of the low centre. At 300 km, the +12 kt rule drops from 89% to 87% on the tune weeks, and the desk stays at 54%.
- **HF false alarms by count of areas are worse than the desk.** 70% of the rule's separate HF areas have no HF low within 500 km, against 37% for the desk. By area the rule matches the desk (59% vs 62%), which is the test that was set. But a forecaster would see more small false HF blobs.
- **The desk's 56% HF catch counts only areas whose wind range reaches 64 kt.** About two thirds of the desk's misses are lows the desk did carry under a HURRICANE FORCE WIND WARNING header, but with the wind range topped at 55-60 kt at that hour. Counting instead any HF fix within 500 km of a low under an HF header, the desk catches 66% (82% at 24 h, 49% at 48 h; held-out 60%). Either way the desk is below 80%.
- **Grid areas are not text areas.** The model areas are drawn cell by cell. Drawn as HSF boxes and quadrants they would grow; the "High seas text from the grids" thread measures that.
- **The Pacific sample is thin.** At 00 and 12 UTC inside HSFEP1 there are 113 gale, 13 storm and 6 HF events, against 1,977, 506 and 80 in the Atlantic. This is mostly an Atlantic result.
- **Not tested:** other lead times, other seasons, and 06 or 18 UTC.
- **ASCAT reads low in the strongest winds**, so storm events near HF strength may count as storm.

## How it was done
- **Truth.** Gale and storm events are 8-connected ASCAT areas of 2 or more cells at or above the level (`rk.truth.ascat_grid`, Metop-B/C intercalibrated, ±90 min, rain dropped). An event is caught when a warned cell lies within 4 cells (about 60 nm). HF events are archive fixes with category HF at the valid time (`rk.truth.hf_fixes`), caught within 500 km. A false warned cell is one ASCAT saw with no wind at the level within 60 nm, or, for HF, one more than 500 km from an HF low. Scoring is inside the OPC high seas areas over open water: the Atlantic 31-67N west of 35W (cut at 75W), and the Pacific east of the Bering Strait-53N172E-50N180W-30N180W line.
- **Baseline.** The issued HSFAT1/HSFEP1 at 0430 and 1630 UTC (valid 00 and 12 UTC), parsed to grids by `desk_masks.py`. Warned at level L means the union of blocks whose wind range reaches L. Only hours where every 34 kt+ block parsed are used, about two thirds of them.
- **Methods swept** (`score_warnings.py`):
  - each model and the strongest of the three, with an offset from -4 to +12 kt;
  - the page blend, with an offset and as a core lift;
  - member chances at the cell and within about 1 degree, at the level and 4/8/12 kt below it (132 members: GEFS, ENS, AIFS ENS).
- **Choosing.** A rule qualifies on the tune weeks when it catches at least 80% and has a false area and mean area no worse than the desk. The pre-set pick, the lowest false area, landed on rules just above 80% (gale lift0.3: 82% held-out). The table shows the qualifying rule with the most margin instead, which keeps one simple family across all three levels. `results.md` has the pre-set picks.
- **Cases.** 604 model cases per basin (GEFS 31, ENS 51 and AIFS ENS 51 members, plus the three deterministic models). Held-out weeks are from `rk.cases.held_out` (2025-W45, W50, 2026-W02, W07, W12).
- **Code and data.** Code is in `studies/2026-10-16-warning-forecast/`. Cases and scored rows are in `RK_DATA/extra/warning-experiment/` (`results/rows_winter.csv` and `rows_winter_hf300.csv`).
- **Checked by:** an independent agent recomputed every headline number from the scored rows with its own code, and all matched within 1 point. It re-scored three storm cases from the raw files; the rows were identical. It read five desk HF misses against the issued text and found no parser drop: the desk ranges topped out at 60 kt, or the low was only under a STORM header. Only 3 of 78 HF hits come from cases with under 1,000 nm2 warned; the median warned area in a hit case is 7,700 nm2.
