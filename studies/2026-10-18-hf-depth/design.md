# Too shallow or too smooth? Design card

*Jason, 2026-10-18 04:05Z: "seems like the issue might be models underforecasting"; 04:08Z "how will you determine the depth is too shallow"; 04:10Z "yes". Follows `studies/2026-10-17-core-ceiling/` (models 5-17 kt under ASCAT's core peak near archive HF lows) and `studies/2026-10-18-hf-mixing/`.*

**Question:** when the models' core wind falls short of ASCAT near hurricane-force lows, is it because the low is too shallow (depth), or because a low of the right depth has its core smoothed (resolution)?

**What would change:** depth points to correcting the pressure (or scaling the wind with the depth error); resolution points to sharpening the core (a statistical stretch or generative downscaling). No page change from this study.

**Cases:** the core-ceiling cases with status ok (archive HF fixes, every synoptic hour, Nov 2025 - Mar 2026, +24/+48/+72 h, at least 200 ASCAT cells seen within 500 km), and the wind gaps already in its `cases.csv`.

**Truth for depth:**
1. The archive central pressure at the fix (the desk's analysis; not independent of the models, so it can understate a model's shallowness).
2. The GFS+IFS analysis mean MSLP (`rk.truth.analysis`) at 00/12 UTC valid times: its low nearest the fix (within 300 km) and its pressure drop. It is a model too and may share some smoothing.

**Per model (GFS, IFS, AIFS deterministic) and case:**
- The model's low: `rk.score.find_lows(msl, below=1020)` nearest the fix within 300 km; a miss is charged the lowest MSLP within 150 km of the fix (from `pressure_drop`; corrected 2026-10-18 after the recheck, the run did this, not the field at the fix, so a miss's depth error is understated by 2-9 hPa).
- Depth error = model central pressure minus archive (positive = too shallow), and minus the analysis.
- Pressure drop = mean MSLP on the 500 km ring minus the lowest within 150 km of the model's low (`rk.score.pressure_drop`), against the analysis' drop at its own low.
- Wind gap = ASCAT peak minus the model's 10 m peak over the same seen cells within 500 km (from core-ceiling `cases.csv`). Also the model's peak over all cells within 500 km.

**Decision rule (set now):** per model, pool leads, fit gap = a + b x depth error (least squares), 95% intervals by resampling whole weeks.
- **Depth explains it** if b > 0 (interval above zero) and the gap at zero depth error, a, has an interval reaching below 2 kt.
- **Resolution** if a is at least 2 kt with its interval above zero: lows of the right depth still come up short.
- Both can hold: then the share a / mean gap says how much is resolution.
- Cross-check: the mean gap among cases with depth error within +-3 hPa, and the same fit against the analysis instead of the archive, and with the pressure drop ratio (model / analysis) as the predictor.

No fitting of a forecast product, so no tune/held-out split: all weeks are used and nothing is chosen from the result.

**Data:** the store (deterministic MSLP and winds at the core-ceiling cycles), the analysis truth, the archive. No new pulls beyond re-reading store cycles.

**Reused / new:**
- Reused: core-ceiling case list and wind gaps, `rk.score.find_lows`, `match_lows`, `km`, `rk.truth.analysis`, `rk.compare.boot_sums`.
- New in `rk/`: `rk.score.pressure_drop` (with a test).

**Known traps:**
- Count storms and weeks, not only cases (one storm gives several fixes and three leads).
- Position errors move the model's peak out of ASCAT's swath: report the all-cells peak too.
- ASCAT is unsettled above 56 kt; part of the gap may be ASCAT.
- The three leads repeat the same fix: report per lead as well as pooled.

**Out of scope:** correcting anything; the Pacific beyond the cases ASCAT sampled.
