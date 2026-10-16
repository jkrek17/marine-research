# AIFS in the blend: design card

*Approved 2026-10-16 09:22Z (Jason: "should the AIFS be in the Core Lifted?", then "go" to the coordinator's offer). Win line preset here before any run.*

**Question** (Jason): "should the AIFS be in the Core Lifted?"

**What would change if the answer is yes/no:** the three deterministic runs feeding the page's blend wind (and so Core Lifted = blend + 5 kt where core likelihood >= 35%). The chances and the core likelihood keep AIFS ENS either way; this test touches the deterministic AIFS only. Any page change goes through the Global view thread after Jason agrees.

**Truth:** ASCAT real 10 m wind (`rk.truth.ascat_target`, intercal, floor(x+0.5)), all passes within 90 min of the valid time; buoys (`rk.truth.obs`) as a check on bias at 34+ kt.

**Variants** (identical except the deterministic weights; the live rule otherwise: support-weighted base from awips-tools `build.support_base`, + min(k x member spread, 5 kt), k 0.15 at +24 h, 0.25 after; member spread is GEFS+ENS and does not depend on which deterministic runs are used):
- A: GFS + IFS + AIFS, as live.
- B: GFS + IFS only.
- C: GFS + IFS + AIFS with AIFS weight halved (its support weight x 0.5).
Each also scored with the +5 kt core lift applied where the live core likelihood >= 35% (live model, unchanged), so the answer covers Core Lifted itself.

**Win line (preset):** B or C replaces A only if, on held-out weeks, in BOTH basins, pooled over +24..+120 h:
1. gale tiles (5x5 deg, any ASCAT 34+): CSI higher, with the whole-week 95% interval above zero; and
2. storm tiles (48+): catch not lower by more than 2 points; and
3. 34+ area ratio (forecast / ASCAT at seen cells) not further from 1 than A's.
The verdict is taken on Core Lifted (Jason's question); the plain blend's verdict is printed beside it. If B and C both pass, take the one with the higher gale CSI. If neither passes, AIFS stays as is. Per-lead and buoy numbers are reported but do not decide.

**Cases:** winter 2025-26 (1 Nov - 31 Mar), 00 and 12 UTC cycles, +24..+120 h, both basins; held-out weeks per `rk.cases.held_out`. Nothing is fitted, so tune weeks are also reported as a second look, labelled as such.

**Data:** stored GFS, IFS, AIFS, GEFS, ENS (no new pull). IFS/AIFS/ENS land as the ECMWF fill resumes (~09:48Z, several hours). Pacific 06/18 UTC steps added when stored.

**Reused / new:** `rk.features` (blend pieces), `rk.truth.ascat_target`, `rk.score.tile_hits`, `rk.compare.paired_counts`, `rk.style`; the core-lift retrain's case scoring (`studies/2026-10-16-core-lift-retrain/score.py` products). New: a weights argument for the support-weighted base in `rk.features`.

**Known traps:** AIFS ~4 kt low at gales in cold air (stability study); recent-skill weighting is a dead end (this is a fixed-weight test, not that); score peaks on tiles, not only cells.
