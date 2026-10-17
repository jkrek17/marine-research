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

## Follow-up: lines kept only where the members back them (Jason, 2026-10-16 19:40Z)
This applies the Core Lifted idea to the warning lines. The line is the strongest model plus an offset, kept only where at least q of the 132 members reach the level minus dT within about 1 degree (`gated_lines.py`). Settings were picked on the tune weeks, as before; the results below are from the held-out weeks.

| Line | Events caught | False warned area | False warned areas (by count) | Mean area, nm2 |
|---|---|---|---|---|
| Storm, strongest model +7 kt | 98% | 23% | 41% | 36,800 |
| Storm, +5 kt where 20%+ of members reach 44 kt nearby | 90% | 12% | 28% | 20,700 |
| Storm, +7 kt where 30%+ of members reach 44 kt nearby | 87% | 15% | 20% | 28,700 |
| HF, strongest model +12 kt | 100% (15) | 59% | 70% | 1,700 |
| HF, +16 kt where 15%+ of members reach 56 kt nearby | 100% (15) | 62% | 62% | 3,400 |
| Desk, storm / HF | 92% / 67% | 69% / 62% | 41% / 37% | 142,000 / 6,400 |

**Storm:** member backing halves the false area, with detection still near 90%. This is a real choice between catching every storm and drawing about half as much false storm warning.

**HF:** member backing does not help. The false HF patches sit where the members agree too. They are deep lows with 52 kt or more in a model that the archive did not log as HF within 500 km. The cause could be the forecast or gaps in the archive; this test cannot tell which.

## Head-to-head with the page's own hazard lines (2026-10-17)
The marine wind page's lines are gale where 30%+ of GEFS+ENS members reach 34 kt, storm where core likelihood is 30%+, and HF where core is 90%+ and 30%+ of members reach 48 kt. They were scored with awips-tools `storm.py` and `core_model.json` on the same cases (`page_lines.py`). The core here lacks its 850 mb inputs and was trained on this winter, so the page lines are approximate and partly in-sample, both in their favour.

| Line | Page lines: caught / false area / area nm2 | Strongest model +1/+7/+12 kt | Desk |
|---|---|---|---|
| Gale, whole winter (2,090 events) | 84% / 5% / 198k | 96% / 9% / 232k | 97% / 67% / 1,315k |
| Storm, whole winter (519) | 78% / 9% / 30k | 97% / 23% / 41k | 83% / 67% / 144k |
| HF, whole winter (86 lows) | 81% / 66% / 5k | 91% / 50% / 2k | 56% / 59% / 8k |
| Storm, held-out (105) | 85% [78-90] / 11% / 27k | 98% [98-100] / 23% / 37k | 92% / 69% / 142k |
| HF, held-out (15) | 87% / 76% / 4k | 100% / 59% / 2k | 67% / 62% / 6k |

The page lines are tighter for gale and storm but miss about 1 in 8 gales and 1 in 5 storms that the strongest-model lines catch. In the Pacific the page storm line caught 54% against 92% (13 events). For HF the strongest-model line catches more lows with less false area and a smaller area. Jason's call (2026-10-17): a miss costs more than a false alarm; Core Lifted stays the most likely wind and the strongest-model lines become the hazard area, shown beside the current lines first ("Beside current lines").

## Page spec: strongest-model warning areas (for the page owner; nothing changed yet)
1. **New layer**, beside today's "possible" hazard lines, with a toggle. It is called "Warning areas (strongest model)" and has three bits: gale where max(GFS, ECMWF, AIFS 10 m) >= 33 kt, storm where it is >= 41 kt, HF where it is >= 52 kt. It covers ocean cells only, with no smoothing and no padding.
2. **Payload.** A new grid field (for example `warnmax`, same bit layout as `hazard`) appended to the wire format; nothing is reordered. It also goes into the saved forecast record so verification can read it.
3. **Leads.** Draw it at every lead the page shows, but mark it tested at 24-48 h, 30-67N, winter. Outside that it is unscored.
4. **Verification.** From the first live cycle, the nightly storm verification scores `warnmax` exactly as it scores `hazard`: the cell table vs ASCAT at all four synoptic hours, both basins, plus events caught as in this study (`rk.score.warning_events`, `warning_points` for HF against the hf-low archive). Both lines are reported side by side by month.
5. **High Seas text.** No change yet. Drafts keep using the page grids (gale at 30 kt, storm at 44 kt). A "strongest model" draft source can be added later as one more source in the grid-source switch.
6. **Review** after about six weeks of live winter verification, before either line replaces the other. Thresholds stay put until then.

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
