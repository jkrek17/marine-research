# Core wind ceiling at HF lows: ASCAT sees hurricane force that no product shows

*2026-10-17 · winter Nov 2025 - Mar 2026 (the months the store holds full fields) · hf-low archive HF fixes at 00/12 UTC, 79-82 cases per lead from 44 storms in 20 weeks, 74-77 of them Atlantic · truth: ASCAT real 10 m wind, intercalibrated, rain dropped, cells seen within 500 km of the fix*

## The answer
Jason asked what a downscaled (sharper) wind could really gain. This measures the most it could gain near the lows the desk calls hurricane force.

- **At storm force, little is left.** Core Lifted covers 75-84% of ASCAT's 48 kt cells near these lows. Its peak runs 5.5 / 7.0 / 8.6 kt under ASCAT's at day 1 / 2 / 3.
- **At hurricane force, nearly everything is left.**
  - ASCAT reaches 64 kt near 42-43% of the HF fixes.
  - Core Lifted reaches 64 kt in 13% / 7% / 2% of cases, and covers 6% / 3% / 1% of ASCAT's 64 kt cells.
  - No product gets closer: GFS, the closest raw model, covers 6-8% of those cells.
- **AIFS is the weakest in the core.**
  - It runs 15-17 kt under ASCAT at every lead.
  - It never reaches 64 kt in any case.
  - It covers 7-8% of ASCAT's 48 kt cells (GFS 51-53%, IFS 22-24%).

Gap = ASCAT peak minus product peak over the same seen cells, kt. 95% intervals resample whole weeks.

| Lead | ASCAT peak | GFS | IFS | AIFS | Blend | Core Lifted | ASCAT / Core Lifted reach 64 kt |
|---|---|---|---|---|---|---|---|
| +24 | 60.5 | 4.8 [3.2, 6.5] | 6.8 [5.2, 8.7] | 15.1 [13.4, 17.1] | 10.2 [8.7, 12.0] | 5.5 [4.1, 7.2] | 42% / 13% |
| +48 | 60.7 | 5.7 [4.1, 7.5] | 7.8 [5.8, 10.0] | 16.4 [14.4, 18.8] | 11.5 [9.8, 13.5] | 7.0 [5.3, 9.0] | 43% / 7% |
| +72 | 60.6 | 6.5 [4.8, 8.0] | 8.6 [6.0, 11.1] | 17.1 [15.0, 19.4] | 13.1 [10.7, 15.2] | 8.6 [6.2, 11.1] | 43% / 2% |

The same gaps hold using the 5th-strongest seen cell instead of the single peak (Core Lifted 5.6 / 7.1 / 8.7 kt), so one noisy ASCAT cell does not set them.

## What it means for downscaling
The gain is at hurricane force or nowhere. That is where the truth is weakest:
- ASCAT is unsettled above about 56 kt (storm-force truth study).
- Rain cells are dropped here on both sides, so the strongest cores are under-counted.

A downscaler would have to learn 64 kt cores from about 1,500-1,700 ASCAT 64 kt cells a winter, from about 40 storms.

## Limits
- **Mostly the Atlantic.** The Pacific has 5 cases per lead: its ASCAT passes are at 06/18 UTC, and the store holds no low-level (Core Lifted input) files at f030/f054/f078.
- **Some fixes dropped.** 37% of fixes that had a forecast were dropped because ASCAT saw fewer than 200 cells within 500 km.
- **ASCAT peak may run slightly high.** An ASCAT cell keeps its highest observation within ±90 min, and the core can move 50-75 km in that time; each model gives one value at the valid hour.
- **The leads are not independent.** All three share the same fixes and truth.
- **One winter.** Nothing was tuned on it.

Check: an independent agent recomputed every number above from cases.csv with its own code (counts, gaps, 64 kt shares, area ratios) and they matched. It confirmed the Core Lifted rule matches awips-tools storm.py (P >= 0.35, +5 kt), and it raised the limits listed here.

`ceiling.py` builds `cases.csv`; `summary.py` writes `summary.csv` (also per basin) and `status.csv` (skipped cases).
