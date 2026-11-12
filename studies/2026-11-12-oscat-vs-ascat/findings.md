# OSCAT-3 and STAR ASCAT against RSS ASCAT

*2026-11-12 · both basins and the rest of 15-70N · 13 Oct-7 Nov 2026 (22 days ASCAT, 21 OSCAT) · truth: RSS ASCAT as served*

## The answer
OSCAT-3 as NOAA STAR serves it reads low at high winds. Against RSS ASCAT in the same 0.25 deg cells within 30 minutes it ran about 3 kt low at 20-34 kt and 5 kt low at 34-48 kt. Above 48 kt it ran 15-20 kt low, but that figure rests on few storms: one day (14 Oct) gives most of the cells, though OSCAT read low on all 7 days that ASCAT saw 48 kt. It saw two-thirds of ASCAT's gale area, a tenth of its storm area and almost none of its hurricane-force area. **So OSCAT-3 is not a referee for storm or HF.** Use it for where the wind is, not for how strong it is. STAR's own high-res ASCAT matches RSS ASCAT (bias 0.0 kt, SD 1.2 kt), so it can stand in for RSS ASCAT on the live page and during RSS outages.

## The evidence
Bias is STAR minus RSS, binned by the mean of the two winds (so neither side's noise sets the bin).

| Comparison | cells | 20-34 kt | 34-48 kt | 48+ kt | gale area | storm area | HF area |
|---|---|---|---|---|---|---|---|
| STAR high-res ASCAT, same Metop, within 30 min | 246,809 | +0.4 (SD 1.5) | +0.1 (SD 1.6) | 1 cell | 1.21x | 4 vs 0 cells | none |
| OSCAT-3, within 15 min | 97,093 | -2.9 (SD 7.9) | -8.8 (SD 12.2) | -19.5 (SD 5.9), n 405 | 0.58x | 0.07x | 1 vs 129 cells |
| OSCAT-3, within 30 min | 182,853 | -2.6 (SD 8.3) | -5.6 (SD 12.2) | -17.5 (SD 6.8), n 548 | 0.68x | 0.10x | 1 vs 129 cells |
| OSCAT-3, within 60 min | 347,387 | -2.0 (SD 7.9) | -4.6 (SD 13.2) | -17.0 (SD 7.0), n 575 | 0.76x | 0.09x | 1 vs 213 cells |

The 48+ kt shortfall is largest at the closest times (-19.5 kt within 15 min, -11.5 at 15-30 min), the opposite of what a timing error would give.

The sample is thin. At 48+ kt within 30 min there are 548 cells from 3 days, and 14 Oct holds 467 of them. Counting cells where ASCAT had 48 kt or more, there are 7 days. Every one reads OSCAT low, with day means from -10 to -41 kt.

At 34-48 kt the sign flips on some days (3 of the 8 biggest days read high), so the -5 kt figure is soft.

## What it does not show
- **Scatter vs bias.** OSCAT-3 pass times from STAR are unreliable: file stamps bunch up when STAR catches up. The correlation with ASCAT varies by day (r 0.46-0.96), so part of the 5-13 kt scatter is timing. The low bias at storm force is not.
- **STAR ASCAT at storm force.** STAR ASCAT was never tested there: only one same-satellite cell above 48 kt.
- **Cell averaging.** At 48+ kt a STAR cell holds about 2 OSCAT points, so part of the gap may be averaging and resolution rather than the product itself. These pairs cannot separate the two.
- **Wind type.** Both are compared as served. RSS is equivalent-neutral. STAR does not say which its wind is.
- **Season.** These are October-November cases, not mid-winter storms.

## How it was done
- Truth: RSS ASCAT daily maps (`rk.truth.ascat_day`), rain flag dropped.
- STAR passes: `rk.truth.star_day`. Each pass is gridded to RSS 0.25 deg cells (cell mean of unflagged points) and timed at the middle of its file bracket.
- Code: `collocate.py` (pairs), `summarize.py` (results.csv). The pairs file is at `RK_DATA/extra/oscat-vs-ascat/pairs.csv.gz` (16 MB).
- Checked by: a second agent recomputed every headline number from pairs.csv.gz alone and found that all of them matched. It flagged the one-storm-day dominance at 48+ and the soft 34-48 sign; both are added above.
