# Strong-core lift for the blends: design card

*Status: running. Jason 2026-11-06 12:10Z: "use your best judgement" -> the three recommended answers below.*

**Question** (Jason, 2026-11-06, pattern drill thread): "can this apply to our core lifted model blend? can we make a new model blend based on this and see how it compares" and "since we dont have members in GFE this might be a better gfe tool so lets test it".

"This" is the drill's Beat-the-model rule: on 174 lows (in-sample), GFS's strongest wind on the map runs ~3 kt high below gale, ~1 kt high at gale, ~5 kt low at storm and ~11 kt low at HF against ASCAT 24 h later; adding 6-8 kt where GFS shows 44+ kt raised storm+ catch 71->95% and HF 12->44-62% at over-call 13->26-28%; the stronger of GFS/ECMWF helped; going halfway to 925 mb wind x a sea-air stability factor caught 75% of HF but ran straight cases hot.

Read as: does a lift that switches on where the models already show strong wind (no ensemble members) catch more ASCAT storm and HF water than today's lifts, on held-out weeks, without blowing up the warned area? Above all on the GFE deterministic blend (GFS + ECMWF, lagged runs, PR #95), where the member-based core likelihood is not available.

**What would change if yes:** the storm step of the GFE blend (PR #95; Jason checks on AWIPS) and possibly the Core Lifted step on /marine-wind/ (Jason's call). The storm warning line and HSF storm draft (Core Lifted >= 39 kt) are re-scored before either.

**Truth:** ASCAT real 10 m (`rk.truth.ascat_target`, intercalibrated, rain dropped, all passes within 90 min; Pacific with its 06/18Z passes). Beside it, all water vs the model's own analysis (00/12Z), with ASCAT's share stated.

**Baselines** (rebuilt on the same cases):
- Page: Core Lifted today (+5 kt where core likelihood >= 35%, gale-core floor) and +8 kt in cores (#70).
- GFE: PR #95 deterministic blend (`rk.features.det_blend`, GFS + ECMWF, 12/24 h lagged runs, spread bump) as is, and with the GEFS no-model storm lift (+5 kt where GEFS 48 kt share within ~1 deg >= 25%, GEFS-only study).

**Candidates** (deterministic inputs only: GFS, ECMWF, AI-GFS where it helps, GFS 925 mb, skin temperature):
1. **Strong-core lift:** +L kt where the strongest of GFS/ECMWF is >= T kt. L in 4..10, T in 40..50, picked on tune weeks (44/+6-8 from the drill is in-sample, held-out decides).
2. **Strongest model at storm force:** the stronger of GFS/ECMWF where either is >= T, blend elsewhere.
3. **925 mb mix-down:** where sea minus 925 mb air is warm, move part way (a fitted) toward 925 mb wind x the drill's stability factor (0.87 / 0.94 / 1.04 / 1.13 by sea-air bands), raise only.
4. Best pair of the above if both pass on CV.
Each candidate is also laid on the page blend (Core Lifted with its lift replaced or added to), so both questions are answered.

**Win means (decided now; held-out weeks, each basin, paired by whole week, 95% intervals), same line as #70:**
1. Storm tiles (5x5 deg, any ASCAT 48+): catch at least 5 pts more than the baseline it replaces, interval above zero.
2. Storm area (forecast 48+ / ASCAT 48+) at or under 1.5x.
3. Gale tile CSI within 0.01 of the baseline; gale area at or under 1.3x (or no more than baseline + 0.01).
4. Beats the simplest rival (a constant lift in the same cells / the GEFS lift for GFE) by 2 pts on point 1.
5. HF (64 kt cells, catch and area) and false storm tiles reported, not gated. The 39 kt storm line and HSF storm draft re-scored for the winner.

**Cases:** winter 2025-26 (1 Nov - 31 Mar), both basins, 00/12Z cycles, +24..+126 h incl. 06/18Z-valid steps. Tune on `rk.cases.split == "tune"` (5-fold whole-week CV); held-out weeks ((y*53+w)%5==0) scored once at the end. Candidate 3 tunes at 00/12Z-valid steps only (low-level fields at 06/18Z exist for held-out cycles only, LESSONS).

**Data:** all in the store (det GFS/ECMWF/AIFS/AI-GFS incl. lagged runs, ensembles for Core Lifted, GFS/IFS low-level fields, ASCAT). No new download. One whole-winter reader at a time (disk).

**Reused / new:** reused `rk.features.det_blend`, `core`, `blend`; the core-lift-bias `build.py` / `fit_score.py` / `lines.py` layout; `rk.score.tile_hits`, `warning_events`; `rk.compare.paired`; the GEFS-only lift rule. New in `rk/`: `rk.features.strong_lift` (the lift as a function of model grids, with a test) so the page and a GFE port share one definition.

**Known traps:** the 44 kt switch was chosen on the 174 cases (held-out decides); whole-grid boosts win peaks and lose gales; a deepening-rate lift and core retrain were dead ends; the drill scored one peak per map (equal-area cell scores here); 925 mb wind is saturated near deep lows (test which cells reach the surface, not whether momentum is aloft); held-out gate must refuse when truth is missing; Pacific dateline (lon 160-245); weeks are the sample.

**Port check:** say for the winner whether it runs on Jason's AWIPS (det GFS, ECMWF, AI-GFS, CMC, UKMET, GEFS 34/48/64 probabilities; no ENS, no AIFS).

**Out of scope:** chances, HF line, track and cone, any page or GFE change.

## Questions for Jason
1. Where the lift switches on: the strongest of GFS/ECMWF at 44+ kt (drill rule; catches a storm one model has), or the blend at 44+? Recommended: strongest model, threshold re-picked on training weeks.
2. GFE bar: plain #95 blend, or #95 plus the GEFS 48 kt lift? Recommended: report both; the lift must beat plain #95 and match or beat the GEFS lift to be worth carrying.
3. Win line as #70 (storm catch +5 pts, storm area <= 1.5x, gales unchanged). Recommended: same, HF reported not gated.

## Jason's answers (2026-11-06 12:10Z, "use your best judgement")
Taken as the three recommendations: (1) switch on where the strongest of GFS/ECMWF >= T, T re-picked on tune weeks; (2) report both GFE bars, must beat plain #95 and match or beat the GEFS lift; (3) the #70 win line, HF reported.
