# Strong-core lift for the blends

*2026-11-06 · Atlantic and Pacific, 00/12Z cycles, +24 to +126 h · winter 2025-26 · held-out: 5 weeks, 686-700 forecasts per basin · truth: ASCAT (real 10 m, all passes; Pacific with its 06/18Z passes)*

## The answer
**For GFE, yes.** The drill rule ports into a deterministic blend step: add **6 kt to the #95 blend wherever the stronger of GFS and ECMWF shows 44 kt or more**. It needs no ensemble at all. On held-out weeks it beats the GEFS 48 kt lift tested for GFE last week. On storm force it catches more than the page's Core Lifted (+7 pts Atlantic [+3, +11], +16 Pacific [+12, +22]), with storm-tile CSI a statistical tie (more false tiles). The GFE blend's gale scores stay below the page's (gale CSI 3.5 / 1.8 pts lower), which is the #95 blend's own gale behaviour, not the lift's:

- **Atlantic:** catches 69% of storm-force tiles. That compares with 57% for #95 + GEFS lift (+12 pts, [+9, +16]) and 35% for plain #95. It draws storm force over 0.82x ASCAT's storm water. Today's Core Lifted on the page catches 62% at 0.72x.
- **Pacific:** catches 57% of storm-force tiles. That compares with 38% for #95 + GEFS lift (+19 pts, [+17, +24]) and 22% for plain #95, at 0.87x area. Core Lifted catches 40% at 0.51x.
- **Gales do not move.** Gale tile CSI is within 0.001 and gale area within 1%.
- **The price is false storm tiles,** as with every lift so far. Atlantic false tiles go from 93 (GEFS lift) to 210, Pacific from 33 to 105. Counting false tiles, the storm-tile CSI is still a little higher than the GEFS lift's: +0.03 Atlantic (not significant), +0.05 Pacific ([+0.005, +0.14]; the interval rests on 5 weeks).
- **It is not just more area.** Picked on the training weeks to draw the same storm area as the GEFS lift (+4 kt at 42 kt), it still catches 6 pts more in the Atlantic ([+2, +11]). The Pacific version at equal area switched on too low (36 kt) and nudged the gale area up, so it fails there.
- **Hurricane force: a small step only.** 12% of ASCAT 64 kt cells caught in the Atlantic, against 10% for the GEFS lift. This is not the HF fix. The Pacific had too few 64 kt cells to say anything.

**For the page, no.** On top of Core Lifted, the same lift does not beat the +8 kt core lift from #70:
- **Atlantic:** catch 72% vs 77% and tile CSI .564 vs .614 (+8 kt in cores wins).
- **Pacific:** about the same on CSI (.400 vs .393), with more catch at lower area.
- **Recommendation:** keep the #70 choice (+8 kt in cores) as the page candidate.

**Desk products and the storm line:**
- **The 39 kt storm warning line and the HSF storm draft** barely move with the lift on Core Lifted (Atlantic coverage 83% either way, area 2.07x -> 2.13x; Pacific 67% -> 70%, area 3.45x -> 3.82x). On the GFE blend the 39 kt line covers 78% / 71% with the lift vs 81% / 74% with the GEFS lift, at 2.06x / 4.38x vs 2.27x / 4.41x.
- **The 925 mb mix-down** (cold air over warm sea, part way toward 925 mb wind x stability factor) failed the gale part of the win line on the training weeks, so it was dropped.
- **The gated version for the desk stability tool thread** (full factor where 925 >= 34 kt and sea-air >= 5 C) runs 10-13 kt hot outside storms. It draws 64 kt over 3.3-3.6x ASCAT's area.

**Ports to Jason's AWIPS:** yes, trivially. It needs only the deterministic GFS and ECMWF 10 m winds already in the #95 procedure: one max, one threshold, one add. No GEFS, no ENS, no AIFS.

## The evidence
| Held-out, storm force (48 kt) | Atl catch | Atl area / ASCAT | Atl false tiles | Atl tile CSI | Pac catch | Pac area | Pac false tiles | Pac tile CSI |
|---|---|---|---|---|---|---|---|---|
| GFE #95 blend (GFS + ECMWF, lagged) | 35% | 0.25 | 29 | .340 | 22% | 0.16 | 18 | .199 |
| #95 + GEFS 48 kt lift (last week's GFE candidate) | 57% | 0.66 | 93 | .507 | 38% | 0.51 | 33 | .324 |
| **#95 + 6 kt where stronger model >= 44 kt** | **69%** | 0.82 | 210 | .534 | **57%** | 0.87 | 105 | .377 |
| #95 + 8 kt where stronger model >= 44 kt | 72% | 0.91 | 272 | .520 | 61% | 1.07 | 141 | .361 |
| Page: Core Lifted today | 62% | 0.72 | 78 | .560 | 40% | 0.51 | 26 | .353 |
| Page: +8 kt in cores (#70) | 77% | 1.25 | 190 | .614 | 53% | 1.03 | 61 | .393 |
| Page: Core Lifted + 8 kt where stronger model >= 44 | 72% | 0.94 | 198 | .564 | 58% | 0.94 | 79 | .400 |

*Catch = storm-force 5x5 deg tiles (ASCAT 48+ seen) where the forecast also has 48+ among the seen cells: 722-741 Atlantic and 181-208 Pacific events (the GFE and page rows differ by a few cases, see below). Intervals are 95% from resampling whole weeks (5 weeks), in `headline_paired.csv`. Gale tile CSI and gale area move by at most 0.002 and 1% for every lift in the table.*

The tune-week win-line picks rode the 1.5x storm-area cap: +10 to +12 kt at 42-44 kt. On held-out weeks they drew 1.53x (Atlantic GFE) and 1.85x (Pacific page), so they fail the area line. The drill's +6-8 kt is the better-behaved size. Bigger lifts buy catch with area at the same rate the +8 kt study saw.

## What it does not show
- **Outside check from the drill (peaks, not grids):** on 2021-24 lows the drill never used, "GFS +8 kt where GFS has 44+" got 76% of map-peak categories right and caught 27 of 35 HF peaks (GFS raw 54%, 7 of 35); a 925 mb x stability peak did worse (70%, 22 of 35). `studies/2026-11-05-pattern-drill/rule925.json`.
- **Five held-out weeks.** One Atlantic week (mid-December) carries much of the storm sample. The Pacific has about 200 storm events and almost no 64 kt cells.
- **The 44 kt / +6 kt rule comes from the drill deck,** 174 lows from two winters including 2025-26. Some of those lows fall in held-out weeks, so the drill variant is not fully clean of them. The tune-only equal-area pick (+4 kt at 42 kt, Atlantic +6 pts over the GEFS lift at the same area) is the clean check, and it points the same way.
- **Training weeks were mostly scored at 00/12Z-valid steps.** The store lacks low-level fields at 06/18Z steps of tune cycles, and lag runs for 12Z tune cycles. Held-out uses every step and pass.
- **Case sets differ slightly.** The 7 Pacific held-out cycles of 5-11 Jan have no ensembles, so the page products are missing there and the GFE products are scored. Atlantic 2025-12-11 has no lag runs, so no #95 blend. Each comparison is paired on the cases both products have.
- **What was not scored:** HSF draft text, the HF line and the chances. One winter; warm season untested. The all-water check against the analysis (in `final_summary.csv`, 00/12Z only) confirms where, not how strong.

## How it was done
- `build.py` rebuilt every winter case: the page blend, core likelihood and gale-core chance through the core-lift-bias code; the #95 blend (`rk.features.det_blend`, GFS + ECMWF, 12/24 h lags); GFS and ECMWF 10 m speeds; GEFS 48 kt share at 0.5 deg; GFS 925 mb wind and temperatures; and ASCAT.
- `score.py` tuned every lift on training weeks, chose mechanically by the #70 win line (`tune_selection.csv`, `FINAL_CHOICE.json`), and scored held-out weeks once (`FINAL_RUN.json`).
- `equal_area.py` added equal-area picks from training weeks before the held-out run.
- `summarize.py` gives the headline intervals.
- The lift is `rk.features.strong_lift` (tested), so a page or GFE port uses one definition.
- Checked by: an independent agent recomputed every number in the table, the paired intervals (5,000 whole-week draws, another seed) and the storm-line rows from `final_case_counts.csv.gz` and `lines_summary.csv` alone, without the write-up. All matched. It flagged that the Pacific equal-area pick is not equal area (0.63 vs 0.51x, gale area 1.17x), and that the first draft undersold the comparison with Core Lifted (the lift catches more, not about as much) and left out the lower gale CSI. Both are fixed above. It also flagged the thin sample: 5 weeks, 722 Atlantic and 208 Pacific storm tiles, which are correlated within a cycle.
