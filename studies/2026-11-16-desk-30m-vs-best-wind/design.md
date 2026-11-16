# Desk 30 m winds vs Best Wind: design card

*Jason approved the question and the use of stored data only (2026-11-16). Read and score only; nothing on the page or in GFE changes.*

**Question** (Jason's words): "How does the current desk practices of using 30m winds score vs ascat"

**What would change if the answer is yes:** nothing directly. It tells the desk, in the same units the page grids were scored in, what its Stability Height (30 m) practice does to gale and storm area, storm catch and error, next to Best Wind and Make_BestWind. Any change to the GFE tool or the page would be its own study and need Jason's yes.

**Truth:** RSS ASCAT real 10 m wind (`rk.truth.ascat_target`: intercalibrated, rain dropped, passes within 90 min of valid time), open water, seen cells only. How strong and how big, which is what a drawn grid claims.

**Baseline:** Best Wind as the page draws it today (gale floor at 80% gale-core chance), with Make_BestWind (GFE, HF core on and off) and the plain GFE det blend #95 beside it. Raw GFS and ECMWF 10 m are the references for the per-model desk products.

**Win means:** decided now, before any scoring: **a descriptive comparison, no pick.** No product is declared the winner and no threshold is set. The deliverable is one table per basin of the same metrics for every product, plus desk practice minus Best Wind for storm-tile catch, gale area ratio and error with whole-week 95% intervals. A difference is called real only when its interval excludes zero; with five held-out weeks and one winter that is a limit on what the numbers can say, not a result to tune against.

**Cases:** winter 2025-26, both basins (natl, npac), every 00/12Z cycle in the 5 held-out ISO weeks (`rk.cases.held_out`), +24 to +126 h in the earlier studies' steps (24, 30, 48, 54, 72, 78, 96, 102, 120, 126; 06/18Z-valid steps included). Pooled over leads and shown alone at +24 and +48 h. Nothing is tuned: no parameter of any product is chosen here, so the held-out weeks are scored once.

**Data:** stored data only. The held-out cases are rebuilt from the `rk.store` release cycle zips (each ~66 MB, dropped after use; about 140 basin-cycles plus lag runs) and the truth releases, by the two earlier case builders. No NOAA/ECMWF forecast pull. The one thing the truth layer fetches on its own is the GFS land/ice mask at 06/18Z valid times (no analysis is stored for those hours), a byte-range read of two small messages per time, about 100 MB in all.

**Reused / new:**
- Reused unchanged: `2026-11-07-most-likely-wind/build_cases.py` (page blend pieces, Best Wind inputs, ASCAT), `2026-11-06-strong-core-lift/build.py` (GFE det blend, GFS and ECMWF temperature and pressure for the stability mask, GFS 925 mb), `score_cells.best` (Best Wind), `gfe_score.products` (Make_BestWind, HF core on/off), `strong-core-lift/score.py desk_stability_wind` (the Stability_Model_Blender step: theta925 <= theta_sfc, x(30/10)^0.15 = x1.179, mask grown 2 cells and tapered), `fit_score.Tiles` (5x5 deg tile counts, >= 150 seen cells), `rk.score.band_error`, the equal-area catch from `most-likely-wind/summarize.eq_area`, `rk.compare.paired_counts` (whole-week resampling).
- New (study-only): `build_cases.py` runs both builders on one pass over the cycle zips; `score.py` adds the per-model desk products (Stability Height on GFS strict, on ECMWF loose, then averaged) that the 6 Nov score did not have; `summarize.py` is the table writer. Nothing here is general enough for `rk/` yet.

**Products** (how the desk uses the tool, per `Stability_Model_Blender.py`: it is applied to each model's own grids, then the models are blended):
1. GFS 10 m; ECMWF 10 m.
2. **Desk practice:** Stability Height on GFS (strict mask: theta925 <= theta of 2 m air, as the tool reads `t:FHAG2`) and on ECMWF (loose mask: skin temperature, `t:SFC`), then the mean of the two. Also the two halves alone.
3. The 6 Nov form, for continuity: the tool on the det blend #95 (strict; also loose and "Entire").
4. Plain det blend #95 and plain page blend.
5. Best Wind (page, 80% floor; the 60% floor of the 7 Nov study as a continuity row), Make_BestWind HF core off and on.

**Scores (per basin; pooled over leads and at +24, +48):** area ratio forecast/ASCAT at 34, 48, 64 kt (seen cells); 5x5 deg tile catch and false tiles at 48 and 64 kt; equal-area storm catch; MAE and bias on cells where ASCAT or any grid is >= 30 kt; bias by the grid's own value (<20, 20-33, 34-47, 48-63); for the stability products, the share of lifted cells ASCAT has at gale and the mean error on lifted cells whose base was under 34 kt. Paired differences desk practice minus Best Wind (and minus Make_BestWind) for storm-tile catch, gale area ratio and decision-cell MAE. Per-case rows kept so worked cases can be picked.

**Checks before reporting:** the tool-on-blend strict rows must reproduce the 6 Nov held-out numbers (Atlantic storm-tile catch 75%, gale area 1.88; Pacific 60%, 2.53) and Best Wind the 7 Nov held-out table (storm tiles 74% Atlantic / 58% Pacific). A mismatch is explained before anything is written up.

**Known traps:** `LESSONS.md`: the tool's surface pressure is approximated by MSLP over open water; ASCAT reads a few kt low in the strongest cores; one storm at several leads is not independent (weeks are the resampling unit); the strict and loose masks need low-level fields that a few cases lack, so every summary is on the common cases (every product built); Pacific HF has very few tiles.

**Out of scope:** "Boosted" and the other tool modes, the .995 sigma and 30 m GFS-level options, other models in the desk blend (CMC, UKMET, NAM), wave height, buoys.
