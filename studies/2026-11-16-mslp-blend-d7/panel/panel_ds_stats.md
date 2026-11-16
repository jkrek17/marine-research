# MSLP to day 7: design from a forecast-verification statistician

Part A (most likely field) is scored on error; Part B (probabilities) on reliability and skill against an honest baseline.

## Shared ground rules (both parts)
- **Truth:**
  - Score against **both** the GFS and IFS analyses separately. The headline is the mean of the two scores, and a claim counts only if it has the **same sign under both**.
  - Report the analysis-to-analysis disagreement (field RMSE, low position and depth) as the noise floor. Differences below it at +24/+48 are ties.
  - Score a low only where the two analyses agree within 150 km and 4 hPa. Report how many lows this drops.
- **Grid and precision:** compare on one common grid. Anything involving members is scored at 0.5 deg, with **every** candidate regridded. One stored precision throughout.
- **Resampling:** whole ISO weeks of the **initial time**, with both basins and both cycles kept in the same block, 2000 draws. Never pool leads. Count each valid time once per lead.
- **Tuning:**
  - Untuned candidates leak nothing, so they are scored on **all ~22 winter weeks**.
  - Tuned ones use out-of-fold forecasts from leave-one-month-out cross-validation, with a **7-day purge** at the fold edges (+168 runs spill into the next week, LESSONS line 112).
  - The ~4 held-out weeks are a **sign-confirmation gate** only; a bootstrap on 4 blocks is degenerate.
  - The frozen member vote was tuned on this winter's tune weeks, so only its held-out weeks are clean.
- **Power (assumed numbers; recompute on the tune weeks before scoring):** per-case position difference SD about 150 km, about 28 cases per week, design effect about 2.
  - Smallest detectable difference (80% power): about 25 km over 22 weeks, about 60 km on 4 held-out weeks.
  - Roughly 300 lows of 980 hPa or deeper per lead over the winter; about 75 at +144/+168.
- **Multiple comparisons:** Benjamini-Hochberg at q = 0.10 over candidates × leads on each part's primary score. Secondary scores are non-inferiority gates.
- **Lock it in advance:** put the win rules, margins and parameter grids in `prereg.json` and commit its hash before any all-week scoring.

## Part A: the most likely field

**Scores** (open water only, inside the basin inset by 3 deg)
- **Field:** cos(lat)-weighted MSE per case. RMSE = sqrt(mean MSE). Do the paired bootstrap on the per-case MSE with `boot_sums`. (new tested `rk.score.field_mse`). MAE is a diagnostic.
- **Should smoothing be stopped?** Not in the field score. The ensemble mean is the proper RMSE estimate, and the double penalty is the honest price of a misplaced low. The low scores hold smoothing in check. Beside RMSE:
  - **Large-scale RMSE**, with both fields smoothed by a Gaussian of sigma 300 km.
  - **Sharpness ratio:** forecast |Laplacian| divided by the analysis |Laplacian|.
- **Position:**
  - Use `low_case` as in the day 5-7 study. Analysed lows under 1000 hPa, forecast lows under 1010, nearest within 1000 km.
  - **The headline is the mean, with a miss charged 1000 km.** Report the hit rate within 300 km beside it.
- **False lows:** forecast lows under 1000 with no analysed low under 1005 within 500 km, counted per map.
  - Candidates with a threshold have it set on tune weeks to match **IFS's false lows per map at that lead and basin**.
  - The means are flagged if their upper bound is above IFS × 1.10.
- **Depth of strong lows:** for analysed lows of 980 hPa or deeper, report bias and MAE. A miss is scored as the field at the analysed centre minus the analysed value.
  - Selecting on analysed depth makes every forecast look too shallow (LESSONS line 20). That is fine for ranking, but any "fills by N hPa" claim also needs the forecast-selected direction.

**Candidates**
- **Cut:**
  - Weighted blend per lead and recent-skill weighting (dead ends).
  - The lead-dependent switch as a candidate. It is the result, and its skill must be estimated with the selection done inside cross-validation.
- **Untuned:**
  - Single models: IFS (reference), GFS, AIFS, AI-GFS.
  - Simple means: GFS+IFS, and the 4-deterministic mean.
  - Ensemble means: GEFS, ENS, grand.
  - The frozen vote at +120/144/168.
- **Tuned:**
  - The aligned blend, in a GFE version (GFS, IFS, AI-GFS, GEFS mean) and a full version.
  - The aligned blend with median own-depth at the centre.
  - The bounded strong-low deepening, with a **constant-offset rival fitted the same way**.

**How to build the aligned blend:**
1. In each run, find lows under 1010 hPa.
2. Cluster across runs, at most one low per run per cluster, linking lows within D = 600 km. Keep a cluster when its runs carry at least half the weight.
3. Consensus = weighted spherical mean. Each run's displacement is d_k = consensus minus its own low, capped at 0.8R.
4. Warp field D(x) = Σ d_k·exp(−r_k²/2R²), with R = 500 km.
5. Map backward, new(x) = old(x − D(x)), with bilinear interpolation, then average the warped fields.
6. Depth option: add δ·exp(−r²/2·(250 km)²), where δ = median own-depth minus the blended centre value. Apply it only when δ < 0, and cap it at 8 hPa.

That leaves four parameters (D, R, minimum support, cap), tuned on a grid of at most 27 combinations.

**Win rule (per lead, basins pooled, against IFS).** All of these must hold:
- (a) The position mean is lower by at least 10 km **and** 5%, and survives BH.
- (b) The upper bound on false lows per map is at most IFS × 1.10.
- (c) The upper bound on ΔRMSE is at most +0.15 hPa or 3%, whichever is larger.
- (d) The upper bound on Δ|depth error| for lows of 980 hPa or deeper is at most +0.5 hPa.
- (e) Same sign under both truths and in both basins.
- (f) Same sign on the held-out weeks.

"Best" is the passing candidate with the lowest position score. When intervals overlap, prefer the one with fewer parameters, then the GFE-able one. Report the best overall and the best GFE-able, plus "best field" under the mirror rule (RMSE primary, position within +25 km).

## Part B: the probability layer

**Data limit:** members exist only at +120/144/168, 12Z. Use the **full year Mar 2025 – Oct 2026** (about 580 cycles × 2 basins) for calibration, and report winter alone as the headline. At +24 to +120 only the mean and spread exist. Per-cell P(MSLP < threshold) can come from a Gaussian built on the mean and spread, but there are no member lows.

**Products, scores and baselines.** Every product must beat a **calibrated simple baseline fitted on the same weeks**, not climatology alone.

| Product | Verification | Baseline it must beat |
|---|---|---|
| P(low within 300 km of a point), per cell | Fair Brier (ensemble sizes differ; `rk.score.fair_brier`), reliability diagram, ROC area | The Part A best field's lows dressed with a lead-dependent constant error kernel |
| P(cluster is real), per forecast low cluster | Event Brier and reliability: analysed low within 500 km? | Weighted vote support taken as the probability, without recalibration |
| P(centre < 990/980/970/960 hPa), given the low exists | Brier and reliability on matched lows; misses scored as "no" | Logistic regression on the best field's centre depth (out-of-fold) |
| Depth range (10–90%) | Coverage (target 80%), PIT histogram, fair CRPS of centre depth | Best depth ± a constant interval from tune-week errors |
| Position ellipse (80%) | Coverage, and error binned by predicted size | A constant-radius circle per lead (prior result: member spread barely sorts error, r ~ 0.1) |
| Alternative scenarios (member clusters by position and depth, e.g. "deeper/east") | How often each scenario is the one nearest the analysis vs its stated probability; Brier over scenarios | A single scenario |

**Calibration:**
- Fit on tune weeks by leave-one-month-out (isotonic regression with pooled bins, or a logistic on the raw share).
- Shrink thin high-probability bins toward a neighbouring curve (LESSONS line 36).
- Count each bin in **weeks and events** (LESSONS line 33). A bin with fewer than 5 weeks carrying an event is reported as "not verifiable", not as a pass.

**Win rule (per product, per lead).** All of these must hold:
- **Skill:** BSS (or CRPSS) against its baseline above 0, with the week-bootstrap interval excluding 0. Basins are reported separately, and both must point the same way.
- **Reliability:** the calibration-line slope interval contains 1, and the observed frequency in every verifiable bin lies within ±10 points of the forecast.
- **Coverage:** 80% intervals and ellipses cover 72–88% in both basins.
- **Resolution:** forecasts in the wider-spread or higher-probability tercile verify worse (or more often) than the lowest tercile, with the interval excluding 0. If the position ellipse fails this, ship the constant circle instead (LESSONS line 83).
- **Agreement with Part A:** the most likely field's low must sit inside the 50% position area and inside the 25–75% depth range in at least 90% of cases. Otherwise the two layers tell the forecaster different stories.

## Three biggest traps
1. **Leakage passed off as skill:**
   - The vote's in-sample winter.
   - Day-7 runs crossing fold edges.
   - Picking the per-lead winner (or the probability calibration) on the same scores used to report it.
2. **Smoothing and conditioning artefacts:**
   - Means win RMSE and false lows by drawing fewer lows.
   - Selecting on analysed depth fakes a filling bias.
   - The guards are equal false lows, the depth check in both directions, and the sharpness ratio.
3. **Probabilities that look calibrated but carry no information, or rest on thin bins:**
   - Overall reliability hides the empty high bins where strong storms live.
   - Always show the event and week counts, and the constant-baseline comparison.
