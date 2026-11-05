# Bias correction on Core Lifted: design card

*Status: approved 2026-11-05 15:34Z ("try that and see what you find"): the three recommendations below.*

**Question** (Jason, 2026-11-05 15:21Z): "what about bias correction on the core lifted?"

Read as: would a correction that changes with lead time, wind band and basin, fitted against ASCAT on the training weeks, catch more of the 34/48/64 kt water than today's Core Lifted on the held-out weeks without blowing up the warned area?

**Where we start from.** Core Lifted is already a bias correction, but a blunt one: +5 kt wherever the core likelihood is 35% or more, and a 34 kt floor where the gale-core chance is 60% or more, the same at every lead and in both basins. What we know (STUDIES.md):
- Models run 2-6 kt under ASCAT peaks and the shortfall **grows with lead**; it is not larger in bombs.
- A flat +8 kt core lift doubles false alarms; whole-grid boosts win peaks and lose gales; shrink-toward-raw fitting and a deepening-rate lift are dead ends.
- Near HF lows a ~13 kt core lift catches far more 64 kt water, but only lows the desk had called HF; across all cores 95% under a 50 kt blend peak never reach 64 kt, so any HF piece must be gated on the blend peak.

What has **not** been tried: letting the lift size change with lead (small at day 1, larger at day 4-5), and matching how often Core Lifted draws 34/48/64 kt to how often ASCAT sees them, per basin and lead.

**What would change if the answer is yes:** the size of the Core Lifted lift on the marine wind page (and so the storm warning line and the HSF storm draft, which sit on Core Lifted at 39 kt), later the same step in the GFE blend. Any page change waits for Jason's yes after the result.

**Truth:** ASCAT real 10 m wind (`rk.truth.ascat_target`, intercalibrated, rain dropped), every pass near the valid time; Pacific scored with its 06/18Z passes. Winter 2025-26 RSS ASCAT is complete, so the October 2026 RSS outage does not touch this study. Beside every ASCAT score, an all-water score against the model's own analysis (00/12Z), with ASCAT's share of the water stated.

**Baseline to beat:** today's Core Lifted (AIFS half weight, +5 kt at core likelihood >= 35%, gale-core floor), rebuilt on the same cases. Also the simplest rival: one constant lift size per basin chosen on the same training weeks the same way (LESSONS: test a fancy correction against a constant one chosen the same way).

**Win means (decided now, held-out weeks, each basin on its own, paired over whole weeks with 95% intervals):**
1. Storm tiles (5x5 deg, any ASCAT 48+): catch at least 5 points more than Core Lifted, interval above zero.
2. Storm area: forecast 48+ / ASCAT 48+ stays at or under 1.5x.
3. Gale: tile CSI no worse than Core Lifted by more than 0.01, gale area at or under 1.3x ASCAT.
4. Beats the constant-lift rival on point 1 by at least 2 points; otherwise the constant one is the answer.
5. 64 kt: cells caught and area reported, not gated (about 7 HF storms in held-out weeks).

**Cases:** winter 2025-26 (1 Nov - 31 Mar), both basins, 00Z and 12Z cycles, steps +24 to +126 h including the 06/18Z-valid steps (302 cycles per basin). Fit on training weeks (5-fold whole-week CV); held-out weeks `rk.cases.held_out` ((y*53+w)%5==0, 70 cycles per basin) scored once at the end.

**Data:** everything is in the store already (GFS, GEFS, IFS, ENS, AIFS, AIFS ENS for the winter; ASCAT truth cached for every winter day). No new download. Held-out Core Lifted grids from the retrain study exist but use AIFS at full weight and no gale floor, so all 302 cycles per basin are rebuilt with the current recipe (a few CPU hours, one whole-winter reader at a time, resumable by cycle).

**Reused / new:** reused: `rk.features.blend` and `rk.features.core` (live blend and core likelihood), the gale-core model (`studies/2026-10-17-gale-core/gale_core_model.json`), `rk.truth.ascat_target`, `rk.score.tile_hits` / `tile_peaks`, `rk.compare.paired_counts`, `rk.cases`, `rk.style`, and the scoring layout of `studies/2026-10-16-core-lift-retrain/score.py`. New in `rk/`: `rk.calibrate.quantile_map` (fit and apply a frequency-matching map per basin and lead group, with a test), so any later grid (GFE blend, AI-GFS) can use the same step.

**Methods tried, simplest first** (each must beat the one before it on CV to stay in):
1. Today's Core Lifted (baseline) and the constant-lift rival (+3 to +8 kt in cores, one size per basin).
2. Lift size by lead: +L(lead) in cores (P >= 0.35), L fitted per lead group (day 1, 2, 3, 4-5) from the storm hit-versus-area curve.
3. Frequency matching by lead and basin: map Core Lifted speeds so that, over seen water, the forecast draws 34/48/64 kt as often as ASCAT sees them. Applied only on candidate cells (wind 28+ kt or any model 34+), so calm water is untouched.
4. Method 3 split by in-core / out-of-core (core likelihood above or below 35%), only if 3 passes and the split adds on CV.
Reference only, not a candidate: the average correction (mean ASCAT for a given forecast speed). It gives the best average kt error but pulls high forecasts down, so it is shown to make that point, not to warn with.

**Known traps:** condition on the forecast, never the truth (regression to the mean manufactured a fake "5 kt low" once); whole-grid boosts win peaks and lose gales; the held-out gate refuses to score when truth is missing (check `missing_*` counts); Pacific dateline (lon 160-245); count the 60 nm ring as area; weeks, not cases, are the sample; check a gate on the tune weeks too.

**Out of scope:** the chances (P34/P48/P64), the HF warning line, the low track and cone, any page or GFE change.

## Questions for Jason
1. **Which kind of correction.** A forecaster's "bias correction" can mean two things. (a) Frequency matching: make Core Lifted draw 48 kt as often as ASCAT sees 48 kt, by lead. This raises the peaks and is aimed at warning catch. (b) Average correction: the mean ASCAT wind for each forecast speed. This gives the best average error but pulls high forecasts down, because a 55 kt forecast is on average a bit too high. Recommended: (a), with (b) shown as a reference.
2. **What it depends on.** Lead time, basin and wind band only, or also month (Nov-Dec vs Jan-Mar) or model agreement? One winter cuts thin quickly. Recommended: lead, basin and wind band, plus in-core vs out-of-core if it earns its place.
3. **Win line.** Storm catch +5 points held-out, storm area at most 1.5x ASCAT, gale CSI within 0.01 and gale area at most 1.3x, and it must beat a plain constant lift. Right bar, or would you take more storm area for more catch?

## Jason's answers (2026-11-05 15:34Z, "try that and see what you find")
Taken as the three recommendations: (1) frequency matching, average correction as reference only; (2) lead, basin and wind band, plus in-core / out-of-core if it earns its place; (3) the win line as written.

## Run notes (filled in while running)
- Lead groups for every fitted piece: d1 = +24/+30 h, d2 = +48/+54, d3 = +72/+78, d45 = +96..+126.
- Candidate cells for the maps: open water with Core Lifted >= 28 kt (the saved cases do not keep the per-model maximum, so "any model 34+" is left out of the candidate rule).
- The gale floor is applied on the whole basin grid (the page limits it to the OPC boxes; the basin grids sit inside them).
- Port check: `build.py` with AIFS at full weight reproduces the retrain study's held-out grids (blend within 0.016 kt, float16; core likelihood within 0.0002; same lifted cells) on natl +24 h and npac +30 h of 2025-11-03 00Z.
- Selection on the tune weeks, mechanical: a product passes when storm area <= 1.5x ASCAT, gale area <= 1.3x and gale-tile CSI >= Core Lifted - 0.01 (pooled, out of fold for fitted maps); constant and lead-by-lead lift sizes are the passing size with the highest storm-tile catch.
