# Core wind ceiling at HF lows: design card

*Asked 2026-10-17 09:09Z ("what would we really gain from 3?"; idea 3 is a generative downscaler of the wind). Go at 09:11Z: "yes. what about our HF archive. does that give us an idea of where to look?"*

**Question** (Jason's words): "what would we really gain from 3?" This card asks it as: how much core wind does ASCAT still see above Core Lifted near the lows the desk calls hurricane force?

**What would change if the answer is yes:** whether a downscaling experiment is worth a GPU. It changes nothing on the page.

**Truth:** ASCAT real 10 m wind, intercalibrated, rain dropped (`rk.truth.ascat_grid`). ASCAT is the project's referee for how strong; it is unsettled above about 56 kt.

**Baseline:** Core Lifted, the live page layer, rebuilt with the live core model from awips-tools. The blend, GFS, IFS and AIFS are shown beside it.

**Measure (no win line: this is a ceiling, not a method):**
- Peak over ASCAT-seen cells within 500 km of each archive fix, for ASCAT and each product, using the same cells for both.
- The same with the 5th-strongest cell, as a peak not set by one noisy cell.
- The share of cases that reach 48 and 64 kt, and the area ratio at 48 and 64 kt.
- Mean gaps carry whole-week 95% intervals.

**Cases:**
- Archive HF fixes (and S as a second sample) inside the basin boxes.
- Forecasts at +24, +48 and +72 h.
- Nov 2025 - Mar 2026, the only months the store holds full fields.
- Nothing is tuned, so held-out weeks don't apply.

**Data:** store release zips of the needed cycles, about 320 basin-cycles at roughly 50 MB, evicted after use. ASCAT truth files.

**Reused / new:**
- Reused: `rk.store`, `rk.features.core`, `rk.truth.hf_archive` / `ascat_grid`, `rk.score.km`, `rk.compare.boot_sums`, and the live `storm.core_grid`.
- New: nothing in `rk/`. The script is a one-off measurement.

**Known traps:**
- Condition on the archive category (the desk's call), not on ASCAT's peak.
- The sample is weeks.
- Count storms by (basin, event_id).
