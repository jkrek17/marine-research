# Too shallow or too smooth? The lows are deep enough; the core is too weak for its depth

*2026-10-18 · the core-ceiling cases: hf-low archive HF fixes, every synoptic hour, Nov 2025 - Mar 2026, +24/+48/+72 h, 86 fixes x 3 leads from 48 storms in 21 weeks, 78 of 86 fixes Atlantic · depth truth: archive central pressure, and the GFS+IFS analysis at 00/12 UTC · wind truth: ASCAT · pre-set rule: `design.md`*

## The answer
Jason suspected the models underforecast these storms and asked how to tell whether the lows are too shallow. They mostly are not.

- **GFS and IFS get the depth about right at day 1-2.** GFS's low is 1.3 / 0.4 hPa *deeper* than the archive at day 1 / 2; IFS is 0.2 / 1.3 hPa shallower. By day 3 GFS is 2.0 hPa and IFS 4.1 hPa too shallow. AIFS is shallow throughout: 1.9 / 3.5 / 5.0 hPa.
- **The pressure drop from 500 km to the centre matches the analysis** (model / analysis: GFS 1.02-1.08, IFS 0.93-1.01, AIFS 0.85-0.95). On the scale of the whole low, the gradient is there.
- **Yet the wind still falls short at zero depth error.** Fitting gap = a + b x depth error, the gap at zero error is:

| Model | Gap at zero depth error (kt) | Mean gap (kt) | kt per hPa too shallow |
|---|---|---|---|
| GFS | 6.1 [4.7, 7.4] | 6.2 | +0.35 [+0.15, +0.52] |
| IFS | 7.3 [5.5, 9.0] | 8.1 | +0.44 [+0.01, +0.74] |
| AIFS | 15.9 [14.2, 17.6] | 17.0 | +0.31 [+0.01, +0.55] |

Gap = ASCAT peak minus the model's 10 m peak over the same seen cells within 500 km. Intervals resample whole weeks.

By the pre-set rule this is **resolution, not depth**: the gap at zero error is well above 2 kt with its interval above zero, for every model and every lead (GFS 5.8-6.2, IFS 6.9-7.8, AIFS 15.3-16.5 kt). The depth errors add only about 0 kt for GFS, about 1 kt for IFS (about 2 kt at day 3), and 1-1.5 kt for AIFS.

## What it means
- **The models build a low of the right depth and width, but its core wind is too weak for that depth.** That points to the inner core: the tightest gradient and the low-level jet near the bent-back front are smoothed, or the boundary layer doesn't bring the wind down. It is not the low being misplaced. Over the same seen cells, the gap doesn't depend on how far the model low sits from the fix, and lows within 100 km and 3 hPa still fall short by 6 / 7 / 17 kt.
- **Correcting the pressure would not fix the wind.** A depth correction would win at most 1-2 kt, mostly at day 3 and for AIFS.
- **The fix has to sharpen the core:** a statistical stretch of the strongest winds near deep lows, or the generative downscaling idea. The mixing test (`studies/2026-10-18-hf-mixing/`) showed the physical inputs we have don't say where; the core model already ranks those cells best.
- **AIFS is the smoothest by far.** Its lows are a few hPa shallow, but its wind is 15 kt short even when the depth is right: the known smoothing of AI models trained on a loss that rewards the mean.
- **It isn't one peak cell.** Among seen cells, ASCAT averages 171 cells at 48 kt or more per case; GFS has 90, IFS 40 and AIFS 14.

## How solid
An independent recheck reproduced every number and spot-checked the low finder on three store cycles. The gap at zero error holds:
- per lead, on matched lows only (misses removed), with each storm weighted equally (GFS 5.8, IFS 7.1, AIFS 15.5 kt), and without the five busiest storms;
- using the 5th-strongest seen cell instead of the peak (6.9 / 8.7 / 15.4 kt).

## Limits
- **Depth truth is not independent.** The archive pressure is set with models in view, and the analysis is a model. Even so, the archive would have to be 10-15 hPa too shallow to bring the gap at zero error under 2 kt.
- **ASCAT is unsettled above 56 kt**, and ASCAT's peak is above that in 70% of these cases, so part of the gap may be ASCAT reading high.
- The "kt per hPa" slope is only marginally above zero for IFS and AIFS against the archive.
- 30 cases (10 fixes, 3 storms) have no archive pressure; filling them from the analysis lowers the gap at zero error by 0.4-1.1 kt. The conclusion stands.
- A forecast with no low within 300 km is charged the lowest pressure within 150 km of the fix, which understates its depth error by 2-9 hPa. On matched lows only the result is unchanged.
- The "gap all cells" column in `summary.md` (the model's peak anywhere within 500 km) is not a fair comparison: ASCAT saw a median 41% of the circle. Where it saw at least 60%, that gap equals the seen-cell gap.
- North Atlantic almost entirely; the Pacific is limited by ASCAT sampling.

## Files
`depth.py` (extraction to `lows.csv`; `--summary` to `summary.md`), `lows.csv`, `summary.md`, `design.md`. New in `rk/`: `rk.score.pressure_drop` with a test.
