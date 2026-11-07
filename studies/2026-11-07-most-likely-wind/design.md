# The page wind grid as a most-likely wind: design card

*Jason said go (thread "Score the wind grid as most likely wind", 2026-11-07 15:17Z) to the study the coordinator offered; the run starts on this card, nothing on the page changes until he says so.*

**Question** (Jason's words): "if the polygon goal is to catch possible, then the grid should try to get as close to truth as possible. what is the best strategy there."

**What would change if the answer is yes:** the ramp sizes / starts in Best Wind (awips-tools `storm.BEST_RAMPS`, `BEST_HF`), the AIFS weight in the page blend, or the spread term. Only if a variant wins on held-out error without losing core catch. The warning polygons are not touched.

**Truth:** RSS ASCAT real 10 m wind (`rk.truth.ascat_target`: intercalibrated, rain dropped, passes within 90 min). A most-likely grid is judged on how close it is to what the satellite saw, cell by cell. Pacific includes its 06/18Z passes.

**Candidates (all from the store, same cells):** raw GFS, ECMWF, AIFS; page blend (support-weighted GFS/ECMWF/AIFS, AIFS half weight, + spread term); blend without the spread term; blend with AIFS weight 0 and 1; Core Lifted (blend + 5 where core likelihood >= 35%, gale-core floor); Best Wind (blend + 0-6 kt over 36-40 and 0-4 over 44-48 of the stronger of GFS/ECMWF, + HF core 0-6 over 52-56 where GEFS 48 kt share >= 30% nearby, gale-core floor) exactly as `storm.best_wind`; Best Wind with the ramps x0.5 / x1.5 / x2 and starts moved -4 / +4 kt.

**Scores:** bias and mean absolute error (kt) over open water ASCAT saw, per basin:
- by ASCAT band (<30, 30-47, 48-63, 64+ kt) as asked, and
- by the grid's own band (same edges). This second cut is the fair "does the grid mean what it says" test: sorting by the truth band makes every smooth forecast look high in the low band and low in the high band (regression to the mean), so "runs hot below gale" is judged by the forecast band.
- by forecast hour (+24 .. +126).
- Beside it, so nothing is lost: storm and HF tile catch with area (the established 5x5 deg tile count), and gale/storm cell catch at equal area (each grid's own threshold set so its area equals ASCAT's).

**Win means (decided now):** a variant replaces Best Wind only if, on held-out weeks in both basins, it lowers the MAE over the 30+ kt grid band (where the desk's decisions live) with a whole-week bootstrap interval excluding zero, does not raise the all-water MAE, and keeps storm-tile catch within 2 points and HF tile catch from falling. Ramp size / starts and AIFS weight are picked on tune weeks by that rule, then scored once on held-out weeks.

**Cases:** both basins, every 00/12Z cycle 1 Nov 2025 - 31 Mar 2026, steps +24..+126 h including 06/18Z-valid steps (the strong-core-lift case set); held-out weeks per `rk.cases.held_out` (about 1 in 5).

**Data:** all in the store and truth releases (dets, GEFS/ENS stats, GFS low files for the core likelihood, ASCAT). ~600 basin-cycles x ~15-25 MB = ~10-15 GB streamed from the data releases, no AWS pull; cases saved small under `RK_CACHE/extra/most-likely-wind`.

**Reused / new:** `rk.store`, `rk.features` (support_closed_form, k_for, pool, NB), `rk.truth.ascat_target`, core-lift-bias `build.case_job` (live core models), strong-core-lift tile `Counter`, `rk.compare` week bootstrap. New: `rk.score.band_error` (bias/MAE sums by band, with a test) so the verification page and later studies use one definition.

**Methods, simplest first:** 1. the table as is (no tuning). 2. ramp size/start sweep on Best Wind. 3. AIFS weight and spread term under Best Wind.

**Known traps:** truth-band sorting manufactures bias (above); ASCAT runs a few kt low in the strongest cores (storm-force truth study), so a small negative bias at 64+ is partly the referee; one cell counted at several leads is not independent (weeks are the resampling unit); whole-grid boosts and bias correction are dead ends and are not retried.

**Out of scope:** the GFE Make_BestWind (deterministic #95 blend) grid; the warning lines and HSF.
