# Gale cores: design card

*Approved 2026-10-17 00:59Z (Jason "go" in the Global view thread on its proposed design). Win line preset here before any run.*

**Question** (Jason): "should we be looking for 'cores' of 30 kts too? we are really only focusing on storm and HF. what if the core is an area of 34 kts and the gale decision is hard"

**What would change if yes:** the Core Lifted wind would also be raised to 34 kt where a gale-core chance is high, so a hard gale call shows gale on the page. Page change only with Jason's go, via the Global view thread.

**Truth:** ASCAT real 10 m wind (`rk.truth.ascat_target(thr=34)`, intercal, floor(x+0.5)), all passes within 90 min; 34+ within ~50 km (5x7 cells) at cells ASCAT saw.

**Gale-core chance:** the same features, model settings and both-basin training as the storm-core retrain (`live28+basin`, HistGradientBoosting, live settings), trained on the 34 kt target; candidate cells: open water with blend 24+ kt or any model 30+ kt (the near-gale band where the call is hard). Tuned on tune weeks with 5-fold whole-week CV.

**Products (wind grid, kt):**
- Core Lifted today (baseline): blend + 5 where live storm-core chance >= 35%.
- Gale-core lift: Core Lifted, then max(wind, 34) where gale-core chance >= t; t chosen on tune weeks (0.3 to 0.7).
- Reference, no model: the same max(wind, 34) where the calibrated member gale chance (P34 remap from the Chance calibration thread) >= t. This separates the core idea from the calibration fix: if the reference does as well, the gain is the calibration, not the core model.

**Win line (preset; held-out weeks, both basins, +24..+120 h, Core Lifted as baseline):**
1. ASCAT gale cells caught (seen cells with ASCAT 34+, forecast 34+): higher, with the whole-week 95% interval above zero, in both basins; and
2. forecast 34+ area / ASCAT 34+ area at seen cells stays at or below 1.3 in both basins; and
3. gale-tile CSI (5x5 deg) not lower than baseline.
It must also beat the no-model reference on point 1 to be called a core result; otherwise the finding is "the calibrated gale chance does it".

**Cases:** winter 2025-26, 00/12 UTC cycles, +24..+120 h, both basins; Pacific 06/18 UTC valid steps added for the held-out score when stored (as the retrain).

**Reused / new:** the retrain's table builder, train/predict/score code and the stored fields (no new pull); `rk.truth.ascat_target(thr=34)`; chance-calibration p34 remap curves. New: a target-threshold and candidate-rule option in the retrain code, and a gale-cell scorer.

**Known traps:** whole-grid boosts win peaks and lose gales (x1.10: gale FA 12% -> 30%); this lifts only where the gale-core chance is high, and the area cap guards it. Gale chances were ~10 points low; the reference product controls for that.
