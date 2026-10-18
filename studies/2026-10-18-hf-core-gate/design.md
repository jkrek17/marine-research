# Which forecast cores reach hurricane force? Every core, every ASCAT pass: design card

*Jason, 2026-10-18 06:44Z "you cant blindly add 13 kts to every core", 06:45Z "is the core probability higher when there is HF?", 06:46Z "yes we need to map across all ascat". Follows `studies/2026-10-18-hf-stretch/`, whose 13 kt lift was learned only near lows the desk had called HF or storm.*

**Question:** across every forecast storm core that ASCAT saw this winter, not just the archive's lows, can forecast-time information tell the cores that reach hurricane force from those that don't?

**What would change:** if yes, any core lift becomes conditional on that chance (none for ordinary cores). If no, the honest product is a chance-of-hurricane-force shading, not lifted winds. No page change from this study.

**Cases:** every 00/12 UTC cycle, 1 Nov 2025 - 31 Mar 2026 (the months the store holds full fields), both basins, steps 24/30, 48/54, 72/78 (lead days 1-3; 06/18 UTC valid times use the filled low-level files).

**A core:** an 8-connected area of live core probability P >= 0.35 (the live lift threshold) over open water, at least 20 cells. **Scored** when ASCAT saw at least 100 cells of it (the core grown by 2 cells, ~50 km) and at least 30% of it.

**Truth:** ASCAT real 10 m, intercalibrated, rain dropped. **HF core** = at least 3 seen cells >= 64 kt (one cell can be noise). Also kept: the seen peak and the 5th-highest seen cell.

**Forecast-time predictors per core (set now):**
- P max, P mean, core area (cells).
- Blend r10: max and 95th percentile; three-model max (mod_max); the 925 mb mean speed s925 max.
- Pooled ensemble chance of 64 kt (p64) max; GEFS and ENS p64 max separately.
- Depth: the three-model mean MSLP minimum within 300 km of the core; `rk.score.pressure_drop` there; ensemble mean MSLP minimum (GEFS and ENS mean of msl_mean) within 300 km; ensemble MSLP spread at that point.
- Latitude of the P max, lead.

**Baselines:** P max alone; r10 max alone.

**Method:** logistic regression on the standardised predictors, fit on tune weeks. A shallow boosted model too; the higher week-grouped cross-validation ROC on tune weeks is scored.

**Pass rule (set now):** on held-out weeks (`rk.cases.held_out`), ROC area of the chosen model beats P max alone, the 95% whole-week interval of the difference above zero, and Brier skill above zero. Also report, without a pass line: at the probability that would flag as many cores as ASCAT found HF on tune weeks, the held-out hit rate and false-alarm ratio, by basin and lead.
- Fit on tune weeks only; score held-out once.
- Report weeks, storms (distinct cores per valid time are not independent across leads), and HF cores.

**Data:** the store (about 600 cycle files, ~55 MB each, about 33 GB streamed and evicted as it goes; under the 50 GB line), the filled low-level files (local cache), ASCAT truth. No new pulls from outside the store.

**Reused / new:**
- Reused: `rk.features.core`, the live core model (`ceiling.live`), `rk.truth.ascat_grid`, `rk.store.load_det` / `load_ens`, `rk.score.pressure_drop`, `rk.score.auc` / `brier_skill`, `rk.compare.boot_sums`, `ceiling.evict`.
- New: none in `rk/`; a core table and a fit script.

**Known traps:**
- The same storm appears at three leads and several valid times: resample whole weeks; count distinct valid-time cores.
- ASCAT is unsettled above 56 kt; 3 cells >= 64 is the line, and the 5th-highest cell is reported too.
- A core seen only at its edge can miss its peak: the 30% coverage floor.
- Never tune on held-out weeks.

**Out of scope:** the lift itself; any page change.
