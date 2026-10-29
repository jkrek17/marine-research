# Hurricane-force lows at day 5-7, three free checks: design card

*Jason 2026-10-29 02:01Z: "What is a research project we could do to try and improve HF low detection in a long range forecast." An expert panel (ensemble, ML, desk forecaster, verification) ranked a per-member setup model first and asked for three checks on data already in hand before any pull or GPU. Jason 02:46Z: "sure" (to the checks and the panel's event and truth answers); "we have ascat at 18z/00z for the pacific. it is not untestable."*

**Question:** at day 5-7, (1) would more ensemble members find more hurricane-force lows, (2) does the run-to-run trend of the member signal add skill, and (3) how well do the desk's own day 5-7 wind grids call them?

**What would change:** (1) decides whether a huge AI ensemble is worth renting a GPU for; (2) could become a lab layer beside the bomb watch; (3) is the baseline every later HF method must beat. No page change from this study.

**Event** (panel answer to (a), one rule everywhere): a 2 deg ocean cell of the bomb-watch grid has an event when an OPC archive HF fix lies within 500 km of it within +-12 h of the 12 UTC valid time (a 24 h window, fixes every 6 h). Leads +120, +144, +168 h from 12 UTC runs.

**Truth** (panel answer to (b)):
- T1 archive: the hf-low archive HF fixes (OPC analyses; partly informed by imagery). The large sample.
- T2 ASCAT referee: the same, counting only storms ASCAT confirmed (RSS ASCAT real 10 m, `rk.truth.ascat_target` 64 kt neighbourhood maximum within 300 km of one of the storm's HF fixes, +-3 h; every pass time, so the Pacific 18 and 00 UTC passes count). Cells near HF fixes of unconfirmed storms are left out of T2. Pass or fail rests on T2, in each basin; T1 must agree in sign.

**Member signal (the baseline for all three):** the share of the 133 members (31 GEFS, 51 ENS, 51 AIFS ENS where present) with a low at or below P* hPa within 500 km at the valid time, from the stored member lows (`mslpd57_*`). P* per basin and lead chosen on training weeks from 940-990 hPa in 5 hPa steps, then fixed.

**Checks and reading lines (set now):**
1. *Ensemble size.* Random member subsets of 8, 16, 32, 64 and all 133 (each ensemble in proportion, 50 draws), plus the fair Brier score (Ferro 2014) for an unlimited ensemble of the same systems. More members help if the unlimited-ensemble BSS beats the 133-member BSS by 0.02 or more at day 6 or 7, interval lower bound above 0. If not, the GPU ensemble is dropped.
2. *Run-to-run trend.* Logistic fit on training weeks: share now, against share now plus the change since the run 24 h earlier at the same valid time (day 5 and 6; day 7 needs +192 h, not stored). The trend earns a place if the held-out BSS gain is above zero with the lower bound above zero, and the 30%+ reliability moves toward the diagonal.
3. *Desk baseline.* The NDFD oceanic wind (`rk.desk`, the issuance after the run was available, `issue_for`): desk yes when its wind reaches 64 kt within 500 km (48 kt as a second line). Brier, hits and false alarms beside the member share. Descriptive, no pass rule.

**Cases:** 12 UTC runs Mar 2025 to May 2026 (the archive copy ends May 2026), both basins. Held-out weeks per `rk.cases.held_out`, scored once; training rows that share a valid time with a held-out row are dropped (LESSONS line 102). Intervals: 95%, 2,000 resamples of whole weeks.

**Sample, stated before scoring:** 72 Atlantic and 42 Pacific archive HF storms since Mar 2025; about 1 in 5 falls in held-out weeks (~15 and ~8). The top bins will be thin and every result is reported with its storm and week counts.

**Data:** member and analysis lows already stored (`mslpd57_*`, bomb-watch study). ASCAT truth files in the release (fill any missing days with `rk.truth`). Desk grids: none cached yet. Days 5-7 need only YCYZ97 (~15 MB), but `rk.desk.load` also reads YCYZ98 (~30 MB): about 13 GB streamed with a YCYZ97-only option, about 40 GB without. Raw files are not kept. Under the 50 GB line either way; run outside the build windows.

**Reused / new:** reused `rk.bomb` (lows, cells, ocean mask), the bomb study's store reader, `rk.truth.hf_archive` / `hf_fixes`, `rk.truth.ascat_target`, `rk.desk`, `rk.cases`, `rk.compare`, `rk.calibrate`. New in `rk/` with tests: the fair Brier score (`rk.score`) and a days 4-7-only desk read.

**Known traps:** held-out runs spill into the next week; thin bins above 30% (count storms, not cells); neighbouring cells share a storm; the desk must be paired with the issuance it could have seen; the archive HF label is partly from imagery, so ASCAT decides.

**Out of scope:** the setup model itself (option 1) and its reforecast pull; any page change.
