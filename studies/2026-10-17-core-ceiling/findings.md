# Core wind ceiling at HF lows: ASCAT sees hurricane force that no product shows

*2026-10-17, rerun 2026-10-18 at all four synoptic hours · winter Nov 2025 - Mar 2026 (the months the store holds full fields) · hf-low archive HF fixes, 86 cases per lead from 48 storms in 21 weeks, 78 of them Atlantic · truth: ASCAT real 10 m wind, intercalibrated, rain dropped, cells seen within 500 km of the fix*

## The answer
Jason asked what a downscaled (sharper) wind could really gain. This measures the most it could gain near the lows the desk calls hurricane force.

- **At storm force, little is left.** Core Lifted covers 74-85% of ASCAT's 48 kt cells near these lows. Its peak runs 5.5 / 7.0 / 8.5 kt under ASCAT's at day 1 / 2 / 3.
- **At hurricane force, nearly everything is left.**
  - ASCAT reaches 64 kt near 42% of the HF fixes.
  - Core Lifted reaches 64 kt in 12% / 7% / 2% of cases, and covers 5% / 3% / 1% of ASCAT's 64 kt cells.
  - No product gets closer: GFS, the closest raw model, covers 5-8% of those cells.
- **AIFS is the weakest in the core.**
  - It runs 15-17 kt under ASCAT at every lead.
  - It never reaches 64 kt in any case.
  - It covers 6-9% of ASCAT's 48 kt cells (GFS 51-55%, IFS 22-26%).

Gap = ASCAT peak minus product peak over the same seen cells, kt. 95% intervals resample whole weeks.

| Lead | ASCAT peak | GFS | IFS | AIFS | Blend | Core Lifted | ASCAT / Core Lifted reach 64 kt |
|---|---|---|---|---|---|---|---|
| +24 | 60.4 | 4.9 [3.4, 6.6] | 6.7 [5.2, 8.3] | 15.0 [13.4, 17.0] | 10.2 [8.7, 11.9] | 5.5 [4.2, 7.1] | 42% / 12% |
| +48 | 60.4 | 5.5 [3.8, 7.2] | 7.8 [5.9, 9.8] | 16.3 [14.3, 18.6] | 11.4 [9.7, 13.2] | 7.0 [5.5, 8.7] | 42% / 7% |
| +72 | 60.4 | 6.4 [4.7, 7.9] | 8.6 [5.9, 11.0] | 17.0 [14.9, 19.4] | 12.9 [10.6, 15.2] | 8.5 [6.2, 11.0] | 42% / 2% |

The same gaps hold using the 5th-strongest seen cell instead of the single peak (Core Lifted 5.6 / 7.1 / 8.6 kt), so one noisy ASCAT cell does not set them.

## The momentum is aloft, but that alone proves little (added 2026-10-18)
Jason asked for a downscaling that makes physical sense: a 10 m wind can only mix down what is above it. So, of ASCAT's 64 kt cells, how many have 64 kt or more at 925 mb in the model within about 50 km?

| Lead | GFS 925 | IFS 925 | AIFS 925 | GFS 850 | IFS 850 | AIFS 850 |
|---|---|---|---|---|---|---|
| +24 | 98% | 97% | 95% | 98% | 98% | 94% |
| +48 | 95% | 92% | 91% | 93% | 94% | 92% |
| +72 | 90% | 66% | 78% | 91% | 63% | 81% |

Both basins, 1,721 ASCAT 64 kt cells (1,688 Atlantic) in 36 cases; the top 5 cases hold half the cells, and averaged per case the day 3 GFS share is 73%, not 90%.

**What this shows:** the models are not short of momentum. Hurricane-force wind sits just above nearly every place ASCAT saw it at the surface, even in AIFS, which is 15-17 kt short at 10 m. A downscaling that mixes momentum down, capped by the 925 mb wind, has the wind it needs.

**What it does not show (the independent check's point):** that the 925 mb wind picks out where hurricane force reaches the surface. 64 kt at 925 mb is common near HF lows. The GFS 925 mb peak reaches 64 kt in 84% of cases where ASCAT stayed below 64 kt, because 925 mb normally runs 20-30% above 10 m. So this is a necessary condition passed, not evidence that mixing explains the gap. The deciding test is the other direction: of the cells with 64 kt aloft, which reached the surface, and do stability (SST minus T850, cold advection) and core position sort them? That needs those cells counted, which this table does not store.

## What it means for downscaling
The gain is at hurricane force or nowhere. That is where the truth is weakest:
- ASCAT is unsettled above about 56 kt (storm-force truth study).
- Rain cells are dropped here on both sides, so the strongest cores are under-counted.

A downscaler would have to learn 64 kt cores from about 1,700 ASCAT 64 kt cells a winter, from about 40 storms.

## Limits
- **Mostly the Atlantic.** The Pacific has 8 cases per lead. The rerun filled the missing 06/18 UTC core-model inputs (f030/f054/f078, 2026-10-18), which added 3. The real limit is ASCAT sampling: most Pacific HF fixes (123 of 147) and most 06/18 UTC Atlantic fixes are not seen by 200+ ASCAT cells within 90 min of the fix time.
- **Some fixes dropped.** Fixes ASCAT saw poorly were dropped because ASCAT saw fewer than 200 cells within 500 km.
- **ASCAT peak may run slightly high.** An ASCAT cell keeps its highest observation within ±90 min, and the core can move 50-75 km in that time; each model gives one value at the valid hour.
- **The leads are not independent.** All three share the same fixes and truth.
- **One winter.** Nothing was tuned on it.

Check: an independent agent recomputed every number above from cases.csv with its own code (counts, gaps, 64 kt shares, area ratios, momentum shares), on the first run and again on the 2026-10-18 rerun, and they matched. It confirmed the Core Lifted rule matches awips-tools storm.py (P >= 0.35, +5 kt), and it raised the limits listed here.

`ceiling.py` builds `cases.csv`; `summary.py` writes `summary.csv` (also per basin) and `status.csv` (skipped cases).
