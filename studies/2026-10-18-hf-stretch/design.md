# Core stretch near hurricane-force lows: design card

*Jason, 2026-10-18 05:02Z "so is this something downscalling could fix?", 05:04Z "so how would you apply it then? based on low depth?", 05:11Z "yes". Follows `studies/2026-10-18-hf-depth/`: the models' lows are deep enough, but the core wind is 6-7 kt (GFS, IFS) too weak for that depth.*

**Question:** does a statistical stretch of the core wind, gated by the live core probability and keyed to the low's pressure drop, catch more of ASCAT's hurricane-force cells than Core Lifted without spreading false hurricane-force area?

**What would change:** if it passes, it is a candidate for a hurricane-force tier on the marine wind page, which waits for Jason. If not, a statistical stretch is off the table and only structure-aware methods remain.

**Cases:** the core-ceiling cases (archive HF and S fixes, every synoptic hour, Nov 2025 - Mar 2026, +24/+48/+72 h, at least 200 ASCAT cells seen within 500 km). Every cell within 500 km of the fix.

**Inputs per cell:** the blend `r10`, the live core probability P, Core Lifted (`r10 + 5` where P >= 0.35), ASCAT (real 10 m, intercalibrated, rain dropped), and:
- the low's pressure drop: mean of the three models' MSLP, its low nearest the fix within 300 km (else the fix), `rk.score.pressure_drop` (500 km ring minus centre);
- the geostrophic wind from the same mean MSLP (smoothed one cell), as the cap.

**The stretch (set now):**
- Core = P >= 0.35 (the live lift threshold). Outside the core the field stays Core Lifted.
- In the core, empirical quantile mapping from `r10` to ASCAT over seen core cells, quantiles 1-99 by 1 plus 99.5, linear between, constant shift beyond the ends. Learned separately for pressure-drop bins < 20, 20-30, >= 30 hPa and for each lead; a bin with fewer than 2,000 seen core cells or fewer than 30 ASCAT 64 kt cells pools its leads.
- Never lower than Core Lifted: stretched = max(Core Lifted, mapped).
- Cap: no higher than 0.8 x the geostrophic wind, unless Core Lifted already is.
- The mapping aims at ASCAT; ASCAT above 56 kt is unsettled, which the findings must weigh.

**Scores, on seen cells, held-out weeks only (`rk.cases.held_out`), per lead and pooled:**
- POD 64: share of ASCAT >= 64 kt cells with a forecast >= 64 kt within 5 x 5 cells (~50 km).
- Success ratio 64: share of forecast >= 64 kt cells with ASCAT >= 64 kt within 5 x 5 cells.
- CSI 64 from those two, area ratio 64 (forecast cells / ASCAT cells), and the same at 48 kt.
- Intervals: whole-week bootstrap of the difference stretched minus Core Lifted.

**Pass rule (set now):** on held-out weeks, pooled over leads:
1. CSI 64 higher than Core Lifted's, with the 95% interval of the difference above zero;
2. area ratio 64 at most 1.5 (no runaway hurricane-force area);
3. CSI 48 no more than 0.02 below Core Lifted's.
Fit on tune weeks only; score held-out once. Report weeks, storms and distinct 64 kt cell-times (cells repeat across leads).

**Data:** the store, the filled low-level files (local cache) and ASCAT truth. No new pulls.

**Reused / new:**
- Reused: the core-ceiling case loop (`ceiling.jobs`, `circle`, `evict`, `live`), `rk.features.core`, `rk.score.pressure_drop`, `find_lows`, `match_lows`, `rk.compare.boot_sums`.
- New: none in `rk/`; a cell table, a fit and score script.

**Known traps:** never tune on held-out weeks; cells repeat across leads; ASCAT unsettled above 56 kt; the cap uses the models' own pressure, so it cannot add wind the low cannot drive, but a too-smooth gradient caps too low (report how often the cap binds).

**Out of scope:** structure (where in the core the extra wind goes beyond what P and r10 rank); the Pacific beyond the cases ASCAT sampled; any page change.
