# Panel proposal: NWP and ensemble meteorologist

At day 5-7 most of the error in a strong low is displacement, mostly along the track (timing). Averaging lows that sit in different places fills them, about 10 hPa at +168 in our own study. So: **fix position by moving features, then set depth from the members' own lows.** Never deepen a smeared mean where it lies. Part A builds that map. Part B says how much to trust each low on it.

## Common ground
- **Truth.** Score against the GFS and IFS analyses separately; a win must hold against both. The headline uses their mean. A model family scored against its own analysis goes in an appendix only. Print the analysis-vs-analysis disagreement (field RMSE, low position, depth) as the noise floor. A win smaller than that floor is not a meteorological win.
- **Matching.** Pair analysed and forecast lows one-to-one by Hungarian assignment. Cost = km + 30 km per hPa of depth difference. Gate 1000 km; a miss costs 1000 km. Nearest-neighbour matching lets two analysed lows claim the same forecast low, so it is out.
- **Sample.** Member candidates: 12Z, +120/144/168, the full year Mar 2025 to Oct 2026 (17 held-out weeks, ~640 lows per lead), with winter as a stratum. Deterministic and GFE candidates: both cycles, +24 to +168. Pair only on cycles where every compared source exists; never impute AI-GFS, and score it to +144 at most. Tune with leave-one-month-out, leaving a 3-day buffer around held-out weeks because one storm spans several cycles. Significance: paired differences, resampled by whole weeks (2000 draws). Power: the paired position difference has an SD of ~200 km per low, and there are ~150 effective lows per lead, so the smallest detectable difference is about 35 km. Smaller effects are reported as "not resolved".

## Part A: the most likely pressure field

**Scores**
- **Field:** RMSE over open water, reported honestly. Smoothing should win RMSE, because RMSE rewards the conditional mean, so it enters only as a non-inferiority bound. Beside it, **S1** (Teweles-Wobus): the gradient score, which punishes smoothing because the gradients carry the wind.
- **Position:** the error of matched lows below 990 hPa, split into along-track and cross-track using the analysed 12 h motion.
- **Depth:** signed and absolute central-pressure error for lows below 980 hPa. Relative depth (500 km ring minus centre), because a low can read right inside a wrongly placed background. The slope of forecast against analysed depth: below 1 means filling.
- **False lows:** compare at equal rates, as the house lesson says.

**Candidates.** Cut the per-lead fitted blend and recent-skill weighting (dead ends). Cut the stand-alone deepening of a mean: it puts a sharp low at the smeared spot, a double penalty. Keep:
- each deterministic run
- the GFS+IFS mean
- the **GFE mean** (GFS, IFS, AI-GFS and the GEFS mean)
- the ensemble means and the grand mean
- a lead switch, fixed on tuning weeks
- the member vote
- the **aligned blend**, in two forms: from the members at +120-168, and a GFE form from GFS, IFS, AI-GFS and the GEFS mean at every lead

**The aligned blend, step by step**
1. *Objects.* Lows below 1012 hPa with a 500 km pressure drop of at least 4 hPa, so troughs are left alone. Find each low's footprint with `rk.score.pressure_basins`. A low within 800 km of a deeper low in the same basin, or across a col less than 2 hPa deep, is a **secondary** (a triple-point or frontal wave). It moves with its parent and gets no target of its own.
2. *Consensus.* Cluster the primary lows. Each run contributes **at most one low per cluster** (Hungarian assignment, iterated twice). Position = the block-weighted spherical mean.
   - **Bimodality:** if the voters form two groups more than 2R apart, each holding at least 25% of the weight, keep two objects. Never average them into a mid-point low that no run forecast.
3. *Displacement.* For each run and object, d_k = consensus position minus the run's low.
   - **Cap** |d_k| at D(lead) ≈ 1.25 × the tuning median error (~400, 450 and 520 km at +120, +144 and +168). A run beyond the cap is left unwarped and blends in as spread.
   - Build the smooth field u(x) = Σ d_k·W(|x−x_k|/L_k), with W a Wendland C2 kernel (compact support) and u = 0 at unmatched lows and highs. Take L_k = max(3|d_k|, 1200 km), but no more than 0.8 × the distance to the nearest object that moves differently.
   - **Jacobian check:** keep det(I−∇u) within 0.6-1.4 everywhere, scaling u down if needed. This holds gradients, and so the geostrophic wind, within about 40%.
   - Set u = 0 over terrain above 500 m (Greenland, the Rockies, Alaska), where reduced MSLP is an artefact, and taper it to zero within 300 km of the domain edge. The present `bestguess.py` shifts fields with `np.roll`, which wraps the east edge onto the west. That has to go.
4. *Warp, average, set depth.*
   - Map backward: warped(x) = f(x−u(x)), bicubic in local km. Average the warped fields by block.
   - Then set each object's centre to the weighted median of the voters' own depths, adding Δp × s(x), where s is the composite's own normalised anomaly inside its basin. The low keeps its radius; a fixed 250 km Gaussian would not.
   - Cap Δp at 6 hPa. Apply it only where support is at least 0.3, and only to deepen.
5. *Partial alignment* α in [0, 1] per lead. Where position really is uncertain, α < 1 trades sharpness against the double penalty. α and D are the only tuned settings.

Merges and splits: assignment is one-to-one and unmatched lows get zero displacement, so a disputed merge stays smeared, which honestly shows the uncertainty.

**Win rule, per lead, fixed now.** X beats B only if all four hold:
- **(a)** The position difference for lows below 990 hPa has a 95% interval below zero against **both** analyses.
- **(b)** The absolute depth error for lows below 980 hPa is not worse by more than 0.5 hPa, and the depth slope is at least B's.
- **(c)** False lows per map are no more than B + 0.1, or the comparison is rerun at equal false lows.
- **(d)** RMSE is not worse by more than 0.3 hPa, and S1 is not worse.

"Best" is the candidate that beats the most others; ties go to the one GFE can build. Name two champions: best overall, and best on GFE. **Seam gate:** gradient jumps across blend rings stay under 1 hPa per 100 km, and the run-to-run jump in a low's position at a fixed valid time is no worse than IFS's.

## Part B: what probability says about each low

Every quantity comes from the same objects as Part A. The map's low is the 50th percentile of its own depth distribution, so the two parts cannot disagree.

| Product | Built from | Verified by |
|---|---|---|
| **P(low exists)** within 300 km | weighted support in the vote, already near-reliable (stated 50% verified 51%) | reliability diagram and Brier skill against the climatological rate, by lead. Also completeness: the share of analysed lows below 990 with any object at p ≥ 0.1 |
| **Depth range** 10/50/90% | weighted quantiles of the voters' own depths. Member depth range is known to predict error | PIT histogram and CRPS of matched lows; 10-90% coverage should be 80% |
| **P(depth below 980 / 970 / 960)** | weighted fraction of voters, deep tail | reliability for each threshold. Bins hold at least 30 cases, else widen them. Brier skill against "deterministic IFS says yes/no" |
| **Position uncertainty** | **not** raw member spread (r ≈ 0.1 with error). Use an along/cross-track error ellipse by lead, fitted on the tuning weeks; scale it by spread only if a test on the tuning weeks says spread helps | coverage: the share of analysed centres inside the 50% and 90% ellipses |
| **Scenarios** | (i) the second mode from the bimodality split, with its weight; (ii) a "deeper storm": the aligned composite of the deepest 20% of that object's voters | the analysed low's frequency in each scenario against its stated weight; the deep scenario should verify about 20% of the time |
| **Field probability** P(MSLP < 980) | member fraction, 100 km neighbourhood maximum | reliability and the fractions skill score |

- **Calibration:** only if the PIT shows bias, and only as a single depth shift per lead, applied to the depth distribution and never to existence. Calibration added false lows last time.
- **GFE version:** only the deterministic runs plus the GEFS probability grids. A 4-5-member poor man's ensemble is underdispersive, so its depth range must pass the same coverage test before it is shown.
- **Pass rule for each product:** every reliability bin has a 95% interval containing the diagonal (weekly bootstrap), and the product beats climatology and the deterministic yes/no. Otherwise it is not shown.

## Three biggest traps
1. **A false consensus.** A bimodal ensemble (cut-off against progressive) averaged into one deep, confident low that nobody forecast. Guarded by the bimodality split, the cap and α, plus an eye check of the 20 worst cases.
2. **Self-grading and smoothness.** An ECMWF-family blend gains a few tenths of a hPa against its own analysis, and smooth fields win RMSE. Hence the two-analysis rule, S1, and RMSE used only as a bound.
3. **Matching and selection.** Nearest-neighbour stealing, scoring only analysed lows (which sees misses but not false alarms), and int16 precision changing the low counts. Use Hungarian matching, score in both directions, and keep thresholds and precision identical across every candidate and every probability.
