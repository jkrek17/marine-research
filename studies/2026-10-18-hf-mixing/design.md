# Which hurricane-force winds aloft reach the surface? Design card

*Jason, 2026-10-18 00:47Z: "it has to make physical sense. how would we downscale it"; 03:48Z "yes" to this test. Follows `studies/2026-10-17-core-ceiling/`, which found 64 kt at 925 mb within ~50 km of 91-98% of ASCAT's 64 kt cells near archive HF lows (day 1-2), but also near most lows where ASCAT stayed below 64 kt.*

**Question:** of the cells with hurricane-force wind at 925 mb near a deep low, can physical inputs (stability, cold advection, the 925 mb wind itself, position relative to the low) tell which ones have hurricane force at the surface in ASCAT?

**What would change:** if yes, a physically bounded hurricane-force downscaling is worth building: 10 m wind capped by the 925 mb wind, with the share mixed down set by these inputs, only in the core. If no, it isn't. No page change from this study.

**Truth:** ASCAT real 10 m wind, intercalibrated, rain dropped (`rk.truth.ascat_grid`). Event: an ASCAT cell >= 64 kt.

**Candidate cells:** seen ASCAT cells within 500 km of an archive fix (HF or S, every synoptic hour, Nov 2025 - Mar 2026, +24/+48/+72 h, the core-ceiling cases), where the three-model mean 925 mb speed (`s925`, as the core model uses) is >= 64 kt. That covers every cell a 925-capped downscaling could make hurricane force.

**Predictors (physical only, set now):**
- `s925`: the momentum available.
- `s925_minus_r10`: how much of it isn't reaching 10 m yet.
- `sst_t850`, `sst_t925`, `dT`: stability.
- `tadv850`, `tadv925`: cold advection.
- `gradT850`: frontal zone.
- Distance from the fix, and bearing from it as sin/cos: position in the low.
- `r10`: the blend.

**Baselines:**
1. `s925` alone: the "momentum is aloft" test.
2. The live core probability P (the 48 kt core model, which already sees most of these inputs).

**Methods, simplest first:**
1. Logistic regression on the standardised predictors.
2. A shallow gradient-boosted model with the same inputs, monotone increasing in `s925` and `sst_t850`.

Either one stays only if it beats method 1 or the baselines.

**Pass rule (decided now):** on held-out weeks (`rk.cases.held_out`), the physical model's ROC area beats both `s925` alone and the live P. The 95% interval of the difference (whole-week bootstrap) must exclude zero against both, and the Brier skill must be positive. The coefficient signs must be physical: more momentum and more instability mean more hurricane force. If they aren't, it fails whatever the score.
- Fit on tune weeks only.
- Score held-out weeks once.
- Report how many held-out weeks, storms and ASCAT 64 kt cells the verdict rests on.

**Data:** the store, the low-level files filled for the core-ceiling check (local cache), and ASCAT truth. No new pulls.

**Reused / new:**
- Reused: the core-ceiling case list and loop, `rk.features.core`, `rk.score.km` and `rk.compare.boot_sums`.
- Reused, in `rk.score`: `auc` and `brier_skill`.
- New: none in `rk/`; a cell table and a fit script.

**Known traps:**
- Cells within a storm are not independent: resample whole weeks.
- Never tune on held-out weeks.
- ASCAT is unsettled above 56 kt.
- A one-shot gate refuses when truth is missing.
- Conditioning on the archive category is the desk's call, not ASCAT.

**Out of scope:** building the downscaler; the Pacific beyond the cases ASCAT sampled.
