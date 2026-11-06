# Does a strong 925 mb wind mix down to gales?

*2026-11-06 · North Atlantic and North Pacific, every 00/12Z cycle of winter 2025-26, +24 to +126 h (Pacific with its 06/18Z passes) · truth: RSS ASCAT real 10 m wind, cells within 90 min · 925 mb wind and sea minus air from GFS (skin minus 2 m air) · 6,042 forecast cases, 26.5 million ASCAT cells*

## The answer
**No. In GFS this case almost never happens, because GFS already mixes the 925 wind down.** Over winter 2025-26 open water, wherever sea minus air was 5 C or more and the 925 mb wind was 35 kt or more:
- GFS 10 m carried about 0.81 of the 925 wind.
- GFS 10 m was unbiased against ASCAT (+0.3 kt overall; -1.0 kt at sea minus air 8 C+).
- ASCAT had gale in 56% of those cells.

In stable air (sea minus air under 2 C), GFS keeps only 0.66 of the 925 wind and runs 2 kt high.

- **Jason's exact case is nearly absent in GFS.** A 925 wind of 40 kt or more, GFS 10 m under 20 kt and sea minus air of 8 C or more happened in 2 ASCAT cells all winter. The broader gap (GFS 925 of 35+, GFS 10 m under 25, sea minus air of 5+) happened in 309 cells out of 26.5 million. In those cells:
  - ASCAT had gale in 10% (Atlantic 13%, Pacific 5%).
  - ASCAT's median was 25 kt, beside a GFS 10 m median of 23.
  - ASCAT kept a median 0.65 of the 925 wind, about what it keeps in stable air (0.58).
  - The GFE blend was 0.3 kt low. GFS itself was 2.8 kt low (Atlantic 3.9), which is partly how these cells were picked (weak GFS 10 m).
- **Where the case does happen is ECMWF.** ECMWF runs about 4 kt low in strongly unstable air (5 kt at 8 C+); the GFS family has the right strength there. With the GFS 925 wind 40 kt or more, ECMWF 10 m under 20 kt and sea minus air 8 C or more (2,273 cells):
  - ASCAT came in between the models, median 24 kt, with gale in 22%.
  - ECMWF was 11 kt low, GFS 12 kt high, and the GFE blend 3 kt high.
  - So 40 kt at 925 did not reach the surface. The ECMWF-low gap is a model disagreement, and the blend already splits it.
- **As a grid lift (most likely wind):** raising the blend to gale in gap cells is mostly false gale.
  - Defined on the blend's own 10 m wind, as Make_BestWind would see it, the lifted cells verified at gale 10% of the time in the Atlantic (147 of 1,520 held-out cells) and 3% in the Pacific (19 of 636).
  - A blend gale cell verifies 68% of the time.
  - In the Atlantic that 10% is above the 5% of the cells a 28 kt line would add, so the gap carries a little signal. As a gale call it is still wrong 9 times in 10.
  - Raising to 925 x the tune-week ratio (0.65 / 0.66) changed no cell to gale.
- **As a gale warning trigger (warned area):** the gap adds almost nothing, because the 30 kt strongest-model line already covers nearly all of it: GFS has 30+ kt in most of these cells.
  - Gap cells outside the line, on held-out weeks: 244 Atlantic and 132 Pacific. Of those, 8% and 6% verified at gale.
  - That is the same as the cells a 28 kt line would add (5% and 4%).
  - Catch gain: +0.005 and +0.006 points. Area gain: 0.03%.
  - Defined on ECMWF's 10 m wind, the trigger adds +0.03 / +0.02 points of catch for +0.12 / +0.16% area. At about 1 in 11 to 1 in 33, those cells verify no better than lowering the line.

**What to use instead:** do not mix 925 down as a rule. In strongly unstable air, read **GFS 10 m** (it already holds about 0.8 of the 925 wind and is unbiased). Where ECMWF is much weaker than GFS there, expect the truth in between, closer to the blend. The 925 x stability number stays what the pattern drill found it to be: a peak and HF-ceiling check near lows, not a gridded lift. **This read leans on the GFS family:** GFS 925, GFS skin minus 2 m air, and GFS 10 m.

## The evidence
| Cells (all leads, both basins) | Cells | ASCAT gale | ASCAT median | GFS 10 m / 925 | GFS bias | ECMWF bias | GFE blend bias |
|---|---|---|---|---|---|---|---|
| 925 >= 35, sea-air >= 5 C (any 10 m) | 683,969 | 56% | 35 kt | 0.81 | +0.3 | -3.9 | -0.9 |
| 925 >= 35, sea-air >= 8 C (any 10 m) | 165,331 | 63% | 36 kt | 0.82 | -1.0 | -4.9 | -2.0 |
| 925 >= 35, sea-air < 2 C (stable) | 3,849,950 | 14% | 27 kt | 0.66 | +2.1 | -0.9 | +1.6 |
| **Gap on GFS:** 925 >= 35, GFS 10 m < 25, sea-air >= 5 | 309 | 10% | 25 kt | 0.61 | -2.8 | -0.8 | -0.3 |
| Gap, sea-air 8+ | 37 | 14% | 25 kt | | | | -3.5 |
| **Gap on ECMWF:** 925 >= 40, ECMWF 10 m < 20, sea-air >= 8 | 2,273 | 22% | 24 kt | 0.81 | +11.9 | -11.3 | +3.2 |
| Gap on the GFE blend: 925 >= 35, blend < 25, sea-air >= 5 | 8,497 | 8% | 21 kt | 0.82 | +10.5 | -8.3 | +0.5 |

*Bias = model minus ASCAT, kt. "Gap on GFS" at +24/+30 h only: 71 cells, 10% gale. Gulf Stream / Kuroshio boxes vs elsewhere: 52 vs 257 gap cells, 6% vs 11% gale (`gap_cells.csv`), with no warm-current signal. Rows are cells. A cell scored at several leads counts once per lead; distinct cell-times are in the CSVs (284 for the GFS gap).*

## What it does not show
- **Cells are not independent.** Cells cluster within a forecast and a storm, so the independent sample is forecasts (160 for the GFS gap) and, at most, one winter. Read "adds almost nothing" as "low precision (3-10% gale)", not as proven zero.
- **One winter (Nov-Mar 2025-26).** The GFS-gap sample is small: 309 cells in 160 forecasts, 37 at sea-air 8+. The sea-air 8+ subset hints the blend runs 3-4 kt low there, but that rests on 37 cells.
- **ASCAT misses the heaviest rain and samples each place twice a day.** Some convective gusts under strong 925 flow are not in the truth.
- **Sea minus air is GFS skin minus GFS 2 m air,** the SeaMinusAir grid's definition. ECMWF's own stability was not used.
- **The equal-area controls in `summary.csv` are not truly equal area.** The gap products move less than 0.03% of the area, smaller than the controls' threshold step, so the comparison there is moot; `gap_blend_products.csv` is the readable version.
- **Tune weeks have no low-level fields at 06/18Z-valid steps,** so the tune-week factor (0.65) comes from 00/12Z valid times. Held-out uses every step.

## How it was done
- `build.py` read every case from the shared store: GFS and ECMWF 10 m, the GFE #95 blend (`rk.features.det_blend`, GFS + ECMWF, 12/24 h lags), GFS 925 wind and skin minus 2 m air. It saved only the cells ASCAT saw over open water (`rk.truth.ascat_target`).
- `analyze.py` builds the gap tables (`gap_cells.csv`) and the GFS-gap products with week-resampled intervals (`summary.csv`, `heldout_paired.csv`). `extra_rows.py` adds the gap on ECMWF and the blend (`gap_variants.csv`). `gap_blend_products.py` scores the lift and trigger as Make_BestWind would see them (`gap_blend_products.csv`).
- The gap is `rk.features.mixdown_gap` (tested), so any tool uses one definition.
- Checked by: an independent agent recomputed every number in the table and the held-out lift and trigger counts from the cell table alone, without the write-up or the analysis scripts. All matched. It flagged four overstatements, all fixed above: "unbiased" holds for unstable air overall but not in the GFS gap cells (GFS -2.8 kt there); "0.8" is a median; the Atlantic lift has some signal over a 28 kt line (10% vs 5%); and cells are not independent.
