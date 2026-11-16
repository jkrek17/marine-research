# Panel: operational marine forecaster (high seas desk)

The desk uses MSLP to place and grade gale, storm and HF warnings. So I would score what turns into a warning: deep lows, rapidly deepening lows, and lows near a category boundary. A blend that wins RMSE but draws 992 where the analysis has 968 costs a missed HF warning. **Part A** is one most-likely field a forecaster will trust to draw from. **Part B** carries the tail: the deeper storm, the displaced storm, and how likely the low is to exist. Don't over-deepen the Part A map to cover the worst case; that belongs in Part B.

## Shared: truth and which lows count
- **Truth:** GFS+IFS analysis mean on open water (house standard). Also score each candidate against the *other* centre's analysis. If the ranking flips, report "not separable".
- **Deep-low depth truth:** both 0.25 deg analyses fill compact HF cores. For hf-low archive lows, also score depth against the OPC analysed central pressure. ERA5 isn't worth a pull for this: it is ECMWF-family and smoother.
- **Strata, fixed now:** A = analysed lows <1000 hPa (headline, house matcher). B = <980 hPa. C = deepening ≥12 hPa per 24 h ending at valid time. D = archive HF lows.

# Part A: the most-likely pressure field

## A1. Scores
- **Position:** house matcher (miss = 1000 km), plus "found within the desk tolerance": **150/200/250/300/350/400/450 km at +24…+168**.
- **Depth:** signed and absolute central-pressure error, with **shallow bias** reported separately for B/C/D. Desk tolerance is 4 hPa at day 1-3 and 6 hPa at day 4-7.
- **Usable-low rate (the forecaster's score):** the share of B+C lows with a forecast low inside *both* the position and depth tolerances.
- **Field:** cos-latitude RMSE on open water, plus storm-zone RMSE within 1000 km of A lows. Don't handicap smoothing inside RMSE. Gate it instead with a **sharpness ratio**: forecast mean |∇p| over analysed mean |∇p| in storm zones. Below 0.90 disqualifies a candidate for the desk.
- **False lows** per map (forecast <1000 with no analysed <1005 within 500 km). Position is also compared at equal false-low rate.
- **Consistency:** median cycle-to-cycle change in low position and depth for the same valid time.

## A2. Candidates
Cut: fitted per-lead weights, recent-skill weighting, lagged runs, depth calibration (all dead). The grand ensemble mean stays only as a filling baseline.

**Best possible:**
- singles (ECMWF, GFS, AIFS, AI-GFS)
- GFS+ECMWF mean
- ensemble means
- the member vote at +120-168 (frozen)
- an aligned blend of the det runs and ensemble means at +24-120, with depth = median of the runs' own depths

**GFE (GFS, ECMWF, AI-GFS, GEFS mean):**
- (a) the 3-model mean
- (b) a 3+1 vote: det lows at weight 1, GEFS-mean lows at 0.5, used for position only
- (c) an aligned blend of the 3 det runs, with GEFS mean used for consensus position and **never** for depth
- (d) (c) plus a bounded deepening: where ≥2 runs are <990, depth = deepest-but-one run, at most 4 hPa below the median

When AI-GFS is missing (00Z December), fall back to GFS+ECMWF and score the fallback on those cycles.

**Aligned blend (codeable):**
1. Find lows per run (house finder, <1010). Cluster them across runs with 600 km single linkage. Keep a cluster if it carries ≥50% of the weight. Consensus centre = weighted mean position.
2. For run i and cluster k: d_ik = consensus − own low.
3. Displacement field: D_i(x) = Σ_k d_ik·exp(−r_k²/2σ²), with σ = 600 km. Folding is impossible while |d| < σ√e. Cap |d| at 0.6σ = 360 km. A run beyond the cap is not warped and only votes. Clusters within 1.5σ in the same run are moved as one complex with a common d, so the trough and front stay with the low.
4. Backward-map aligned_i(x) = p_i(x − D_i(x)): one fixed-point iteration, bilinear, on a local great-circle projection.
5. Average with equal weights.
6. Restore depth: add c·exp(−r²/2s²) at the centre, where c = median own depth − blended minimum (deepen only) and s = half-drop radius floored at 200 km.
7. **Split rule:** if the members' lows form two clusters more than 800 km apart, don't warp. Draw the bigger cluster and send the other to Part B as a scenario.

## A3. Sample and gaps
- Winter 2025-26 det runs, 6-hourly, both basins, 00Z+12Z: about 600 basin-cycles per lead, but only about 110 held out, with perhaps 15-25 B lows per lead. That is too thin.
- **Power:** candidates with no fitted parameters (singles, means, aligned blend with σ and the cap fixed here) are scored leave-one-month-out over all winter weeks: about 21 weeks and 100+ B lows per lead. Tuned items stay held-out-only. At day 5-7, the full-year member set (17 held-out weeks) decides.
- 00Z and 12Z are pooled, with a split shown as a check. AI-GFS is scored only on common cycles. Ensemble means are scored at their 24 h steps.
- **Seam at +120:** both methods exist there. If the median low jump between them is >150 km or 3 hPa, cross-fade linearly over +96 to +144 instead of switching.

## A4. Win rule (per lead; baseline ECMWF for both tracks)
A candidate wins a lead only if all of these hold:
1. Usable-low rate (B+C) is higher with the 95% interval (resampled by week) excluding 0, *or* A position is lower with the interval excluding 0 and B depth is no worse.
2. B shallow bias is no worse than ECMWF's.
3. Field RMSE is no more than 2% worse, and sharpness is ≥0.90.
4. False lows are within +0.2 per map.
5. Consistency is no worse.

No winner means "use ECMWF"; ties go to the simpler candidate.

# Part B: the probability layer

## B1. What the desk would use (in order)
1. **P(storm-force / HF winds with this low)**: a gradient-wind proxy (max geostrophic wind within 600 km), quantile-mapped to ASCAT gale/storm/HF on tuning weeks using the hf-depth matched set. This is closest to the warning decision.
2. **P(central pressure < 990/980/970/960)** per low, from the members' own depths. 970/960 bracket most HF-relevant lows.
3. **Depth range** (widened 10-90%, as proven): "L 978 (970-990)".
4. **P(low exists)**: the vote's confidence, already reliable.
5. **Position:** a fixed ring per lead (about 320/370/410 km at +120/144/168), because member spread does not predict position error. Re-test this at day 1-4 before drawing anything per-low.
6. **Scenarios:** cluster member lows on position and depth (k ≤ 3, minimum cluster weight 20%). Name them by what changes the warning ("deeper/slower 25%: L 962, HF"). Each scenario field is an aligned blend of its own members.

**GFE version:** B2-B3 from a logistic/quantile fit on tuning weeks (det median depth, det depth range, lead, latitude, GEFS-mean depth), plus GEFS probability grids where they exist. Verified the same way.

## B2. Verification (held-out, both directions)
- **Event sets:** per analysed low (catches low-P misses) *and* per forecast low (catches overconfidence).
- **Reliability** diagrams with ≥20 events per bin (wider bins for <970 and HF). Pass: calibration slope 0.8-1.2, and every bin's 95% interval covers the diagonal.
- **Skill:** Brier skill > 0, with the interval excluding 0, against (i) climatology by lead, latitude and month and (ii) the raw member fraction. If the calibration adds nothing over the raw fraction, drop it.
- **Discrimination:** ROC area for HF and <970, reported with the event count.
- **Depth range:** 80% range coverage of 76-84%, a PIT histogram, CRPS against the vote's median-only. Report the width so a wide-but-useless range can't pass.
- **Scenarios:** how often the analysed low falls nearer the alternative than the main scenario, against the stated weight (a 25% scenario should verify about 25%). A scenario that verifies less than half its stated weight gets cut.
- **Consistency:** flag cycle-to-cycle P(HF) jumps >30 points with no matching det-run change.
- **Desk check:** if HF were issued whenever P(HF) ≥ 20/30/40%, give POD, FAR and the costed score (miss two categories = 3, under one = 1, over one = 0.5) against warning off the Part A depth alone. Part B earns its place by beating that.

# Display (web page and GFE)
One map per lead and one point per low. The question at a glance is "where is the low, how deep, and could it be HF?"

**Web page, by default:**
- Part A isobars every 4 hPa, black, no colour fill.
- Each low has one label, "L 978 (970-986) HF 30%". The range is the verified 10-90% band. Show P(HF) only when it is ≥10%, and show P(storm) instead when P(HF) is below 10%.
- One grey ring per lead at the fixed 50% radius (about 320/370/410 km at day 5/6/7). Every low gets the same size of ring, so the ring cannot pretend to be specific to that low.
- Draw lows with P(exists) <30% as an open "L?" with no isobars forced around them.
- Use a lead slider, not a loop. A shaded cross-fade seam is invisible, and that is the point.

**Web page, on request (one toggle each, off at load):**
- member low centres as dots, coloured by ensemble, so a split shows
- the scenario maps (a thumbnail strip under the main map: "deeper/slower 25%")
- the depth fan per low over the leads, plus the analysis once verified
- a P(HF) shading layer

**GFE:**
- The most-likely MSLP goes in as one grid that edits like any model.
- The probabilities go in as a point table that the forecaster sees when composing: low ID, depth label, P(storm), P(HF), scenario. They stay off the grid stack.
- Optional single grid: P(HF wind) for the warning-area tool.
- No ring grid. The ring is a lead-time rule of thumb printed in the table.

**Never:** spaghetti by default, per-low ellipses, more than one probability shading at a time, or rainbow colour scales.

# Worked cases (picked by rule before scoring, from held-out weeks)
Pick:
- the 3 deepest archive HF lows per basin, each shown as a +168→+24 d(prog)/dt sequence
- the 2 largest consensus position busts at +120
- 1 bifurcation case
- 1 GFS phantom deep low
- 1 case where AIFS wins RMSE but misses an A low

Each panel: Part A field (4 hPa isobars), analysis, low label with range and P(HF), scenarios. Mark what a forecaster distrusts: isobars bowed at the warp-taper edge, a low pulled off its trough, a closed low that blinks out between leads, a too-round centre. Blind review of 20 maps (source hidden) before "desk-ready".

# Three biggest traps
1. **Smoothness wins the field score.** RMSE rewards filling. Without the sharpness and shallow-bias gates, the "best blend" is a warning-miss machine.
2. **Analyses as depth truth, and self-grading.** Both analyses under-deepen HF cores, and each model flatters itself against its own analysis. Use the cross-truth check and the archive depths.
3. **False confidence.** An aligned blend draws a crisp low where members disagree, and probabilities verified only on forecast lows hide misses. Use the split rule, scenarios and two-way verification.
