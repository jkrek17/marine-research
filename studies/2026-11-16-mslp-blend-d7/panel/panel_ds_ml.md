# Panel proposal: forecast combination and post-processing view

**Part A** is the most likely MSLP field; **Part B** is what probability says about it. They must agree: the map draws a low only where Part B gives it at least a 0.3 chance, at Part B's median depth and at the centre of Part B's position circle.

## Shared: truth and sample
- **Truth:** the mean of the GFS and IFS analyses over open water. A win counts only if its sign also holds against each analysis alone. ERA5 (~2 GB, needs Jason's go) would only check signs; it is ECMWF-family too.
- **Held-out set:** ~110 of ~600 basin-cycles per lead (4 winter weeks). Before opening it, compute the minimum detectable effect on the tuning weeks; a smaller gap is a tie unless every held-out week agrees. Settings come from leave-one-month-out; intervals resample whole weeks.
- **Member candidates** (+120 to +168, 12Z) use the full year (17 held-out weeks). Those weeks already chose the vote, so they are not blind for vote-versus-vote choices; say so.
- **Same cases for every candidate.** There is no ensemble field at +144/168 on 00Z. When AI-GFS is missing, renormalise the weights (set before scoring) and score those cycles separately; ramp it out before +150.

---

## Part A: the most likely field

### Scores
- **Field:** cos-lat-weighted RMSE over open water. **Smoothness is not penalised:** under position doubt the lowest-error field is smooth, fairly. Its cost shows in the **storm-area RMSE** (within 800 km of an analysed low below 990 hPa) and the Keil-Craig **DAS** split into displacement and amplitude error.
- **Position:** `rk.score.low_case`, in the same form as the day 5-7 study (miss = 1000 km), plus the hit rate within 300 km.
- **Depth of strong lows:** for analysed lows below 980 hPa, the signed central-pressure error, the pressure-drop ratio, and the **frequency bias** (forecast lows below 980 per map ÷ analysed lows below 980 per map).
- **False lows:** per map, counted by running the low finder on the *finished field*. Compare methods at equal false lows.

### Candidates, each against its simplest rival
| Candidate | How it is built | Must beat |
|---|---|---|
| Single models, GFS+ECMWF mean, 3-4 deterministic mean, ensemble means, grand mean | as stored | (baselines) |
| **Weighted blend** | Weights ≥0 that sum to 1, per basin, fit by least squares on the tuning weeks. Shrink toward equal weights by λ, chosen by leave-one-month-out. Weights are quadratic in lead, so they change smoothly from lead to lead. At most ~8 tuned values. | Equal-weight mean of the same inputs. Equal weights usually win, and recent-skill weighting has already failed here. |
| **Lead switch** | **Cut the hard switch.** It is a weighted blend with all the weight on one model, so it cannot beat the blend on average, and it makes step jumps. Keep only a logistic ramp at least 48 h wide, with just its midpoint fitted. | Smooth weighted blend |
| **Feature-aligned blend** | See below | (a) The plain blend with the same weights. (b) The rigid-shift map in `bestguess.py`. (c) **The plain blend plus the depth bowl only, with no warping.** (c) is the key test of what the warp itself adds. |
| **Strong-low depth fix** | See below | A constant offset under the same gate, chosen the same way. Also the median of the runs' own depths. |
| Cut | EMOS or bias removal on the whole field; recent-skill weights | |

### Feature-aligned blend, step by step
1. **Lows:** `find_lows(below=1010)` on each run (Gaussian σ = 1 cell first), keeping lows with a 500 km drop of at least 4 hPa.
2. **Groups:** `method.consensus` (R = 450, sep = 600 km), one low per run. Target c_j = support-weighted mean position. Align only groups with support ≥0.5 whose lows pair off one-to-one.
3. **Vectors:** d_kj = c_j − x_kj (km, tangent plane). Drop any over 800 km (a mismatch). A run with no low gets no vector; never invent a low.
4. **Displacement field:** D_k(x) = Σ α_j φ(|x − c_j|/L_j), φ = Wendland C2 (zero beyond L_j), solved so D_k(c_j) = d_kj. L_j = max(1200 km, 2.5|d|); require det(I − ∇D) > 0.3 (no fold-over). Taper to zero within 300 km of the box edge; Pacific longitudes 160-245.
5. **Warp:** f̃_k(x) = f_k(x − D_k(x)) with `map_coordinates(order=3)`. Cubic keeps the minimum. No seams: far from lows D = 0, unlike the edge-wrapping `np.roll` in `bestguess.py`.
6. **Average** with the blend weights. In the GFE version the GEFS mean counts only away from lows; its lows are filled.
7. **Depth bowl:** for support ≥0.5, a 250 km Gaussian sets the minimum to Part B's median depth (cap 8 hPa). Weaker groups keep the averaged, partly filled depth, the right answer when only some runs have the low.

**Cost:** ~21k warps (600 basin-cycles × 7 leads × 5 runs) take under 5 CPU-minutes. Store reads are the real cost: read each basin-cycle once, score everything, delete the unpacked files. Try dense optical flow (TV-L1) only if this wins.

### Deepening strong lows without adding false lows
The earlier calibration deepened shallow candidates past 1000 hPa and so added false lows. Here the list of lows is fixed first and only depth changes, and only for lows already ≤990 hPa (or drop ≥15 hPa) with support ≥0.5. Quantile-map forecast central pressure to the analysed lows' distribution (no pairing), pooled basins, slope linear in lead, ≤7 knots, monotone, ≤6 hPa, shrunk toward zero. Never fit errors on pairs sorted by the truth (regression to the mean).

### Win rule per lead (set in advance)
C beats R (the best single model on the tuning weeks, and the equal mean of C's inputs) if all of these hold on the held-out weeks:
1. Position error is lower, with the interval excluding 0.
2. RMSE is no more than 0.15 hPa worse than C's plain-blend rival (upper bound of the interval).
3. False lows are within +0.15 per map, or C wins at equal false lows.
4. The bias of lows below 980 hPa moves toward 0.
5. Rules 1 and 4 hold against each analysis separately.

C must also beat its named rival. On a tie, the simpler method wins.

---

## Part B: what probability says about it

Every product below has a simple rival: the **climatological error from the tuning weeks, by lead** (and by support bin where relevant). A raw member share must also beat a calibrated version of itself, or the reverse.

| Product | How it is built | How it is verified |
|---|---|---|
| **Chance a low exists** (per drawn or listed low) | The vote's weighted support, recalibrated by isotonic regression per lead group. Shrink sparse bins toward the neighbouring lead's curve, not toward the raw share. It is already nearly reliable: stated 50% verified 51%. | Reliability diagram and Brier skill against climatology. Event: an analysed low below 1000 hPa within 300 km. |
| **Low-chance map**, P(a low within 300 km of each point) | The weighted share of voters with a low within 300 km | Fair Brier score, reliability and ROC area on the grid. This also counts analysed lows that the list missed. |
| **Depth distribution**: P(central pressure < 990 / 980 / 970 hPa), with a 10-90% range | The weighted empirical distribution of the voters' own depths. The member depth range *does* predict error, so keep the spread but scale it with one inflation factor per lead, fit so the PIT is flat. | CRPS on matched lows, the PIT histogram, and coverage of the 10-90% range (target 80 ± 5%). Rival: the median plus a fixed error spread by lead. |
| **Position uncertainty** | **Do not size it from the member scatter** (r ~ 0.1 with error). Use the 50% and 80% error radii from the tuning weeks, by lead and support tercile. | Coverage: the analysed low should fall inside the 80% circle 80% of the time, also within each support tercile. |
| **Other scenarios**: deeper, displaced, or a second centre | Cluster the members within each group window into at most 3 scenarios (k-medoids on low lat, lon and depth). Each scenario's weight is its member share. Show one only if its share is at least 20% and it differs from the most likely by more than 300 km or more than 8 hPa. | Reliability of the scenario weights: how often the scenario closest to the analysis carries each weight bin. |

- **Without members** (below +120, and 00Z), Part B rests on the deterministic runs, climatological radii, and depth spreads scaled by ensemble spread. Say it is weaker.
- **GFE version** (GEFS plus GFS, ECMWF, AI-GFS) needs its own calibration; GEFS is under-dispersive and a pooled curve does not carry over.
- **Power:** lows below 970 hPa are rare. Count the event cycles before drawing a curve, pool leads with lead as a predictor, and require reliability plus a Brier/CRPS gain.

---

## Three biggest traps
1. **Smoothness wins RMSE.** The grand mean and AIFS fill lows by up to 10 hPa and still win the field score; never rank on RMSE alone.
2. **Too many knobs for one winter.** Freeze what the day 5-7 study set, shrink toward equal weights or zero, and cap new tuned values at ~12 across Parts A and B.
3. **Matching errors become field errors and wrong chances.** A merged group or long vector drags a structure across the map. Enforce one-to-one matching, the 800 km cap and the fold-over check, and count false lows on the finished field.
