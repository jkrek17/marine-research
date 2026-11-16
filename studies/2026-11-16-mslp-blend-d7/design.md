# Best MSLP forecast to day 7: design card

*Merged 2026-11-16 from a four-person panel (ensemble-NWP meteorologist, marine desk forecaster, verification statistician, blending data scientist); their drafts are in `panel/`. Fixed before any result.*

**Question** (Jason, 2026-11-16): "what is the best MSLP forecast or blending strategy at lead times out to 7 days." "best means closest to the actual MSLP and lowest position error." "at longer lead times the pressure may not be deep enough for strong storms and its in the wrong place. how can we mitigate both errors." "there are two problems. what is the 'Best pressure forecast' IE, most likely, then what does probability say about it." "so is the better forecast to converge on the 'best pressure' and fit the field around that?"

**What would change:** a most-likely MSLP layer and a low-centre probability layer on the marine page (later GFE), and which models the desk leans on at each lead.

## Truth
- GFS analysis and IFS analysis, each scored separately at 00/12Z valid times; headline = their mean. A claim counts only if its sign is the same against both. The GFS-vs-IFS analysis difference is reported as the noise floor; gaps below it at +24/+48 are ties.
- Deep-low depth also checked against the OPC central pressures of hf-low archive storms (both analyses run compact HF cores shallow).
- ERA5 not pulled unless the two analyses disagree on a headline (would need Jason's go, ~2 GB).

## Cases
- Winter 2025-26 (1 Nov - 31 Mar), 00Z and 12Z cycles, both basins (N Atlantic 30-67N 75W-0; N Pacific 30-67N 160E-115W), leads +24, +48, ..., +168.
- Untuned candidates (singles, equal means, ensemble means): scored on every winter week (~22 weeks; smallest detectable position gap ~25 km vs ~60 km on held-out only).
- Tuned candidates: leave-one-month-out forecasts with a 7-day purge at fold edges; the ~4 held-out winter weeks are a sign check only, never used for a choice.
- Resampling block: ISO week of the initial time, both basins and both cycles together (2000 draws).
- Day 5-7 member products: 12Z only (members stored only there); full year Mar 2025 - Oct 2026 for Part B calibration, winter reported as headline. The full-year held-out weeks already chose the member vote, so comparisons against the vote are not blind there; said so in the write-up.
- AI-GFS stops near +150 h and misses some cycles: scored where present, never imputed; candidates using it compared only on matched cases.

## Part A: the most likely field
**Scores (per lead, basin, truth):**
1. *Closest to actual MSLP:* cos(lat)-weighted RMSE over open water (analysis mask); also bias and a large-scale RMSE after 300 km smoothing, and a sharpness ratio (forecast vs analysed pressure gradient in storm zones), so a smooth field's RMSE win is visible as such.
2. *Position error:* every analysed low < 1000 hPa (3 deg inside the box) matched to the nearest forecast low < 1010 hPa within 1000 km; a miss costs 1000 km (house rule, so dropping hard lows can't help). Mean, plus median and along/cross-track split. One-to-one (Hungarian) matching as a sensitivity check.
3. *False lows* per map (forecast < 1000 with no analysed < 1005 within 500 km); methods compared at IFS's false-low rate where they differ.
4. *Depth of strong lows:* bias and MAE for analysed lows < 980 hPa, and for forecast lows < 980 (both directions, because picking lows by analysed depth makes every forecast look shallow).

**Candidates, simplest first** (each must beat the one before it to stay in):
1. Singles: GFS, IFS, AIFS, AI-GFS.
2. Equal means: GFS+IFS; GFS+IFS+AI-GFS; GFS+IFS+AIFS.
3. Ensemble means: GEFS, ENS, AIFS-ENS, grand mean (each ensemble one block).
4. Weighted blend: non-negative weights summing to 1 per basin, shrunk toward equal, smooth in lead (~8 tuned values). Rival: equal mean of the same inputs. No hard switch by lead; at most a logistic ramp >= 48 h wide (no step jumps).
5. **Aligned blend ("converge on the best low, fit the field around it")**: find each run's lows (< 1010 hPa, 500 km drop >= 4 hPa), group them across runs one per run (day 5-7 study's consensus, R = 450 km); target = support-weighted mean position. For groups with support >= 0.5 whose lows pair one-to-one, build a smooth displacement field per run (Wendland C2 radial functions, radius max(1200 km, 2.5 x displacement), cap tuned from {300, 450, 600} km per lead, no fold-over, tapered to zero within 300 km of the box edge) and warp each run with cubic interpolation before averaging. A run with no low in the group is not moved. Groups split into camps > 800 km apart are not warped (draw the more likely camp, offer the other as a scenario). Replaces the edge-wrapping `np.roll` shift in the day 5-7 `bestguess.py`.
6. **Depth fix** on the aligned blend: for groups with support >= 0.5 and centre <= 990 hPa, set the minimum to the median of the runs' own depths with a 250 km bowl, only ever deepening, at most 6-8 hPa. Rivals: (a) plain blend + the same bowl with no warping (what does moving add?), (b) a constant offset under the same gate. A quantile-mapped depth correction is tried only if the median is still shallow.
7. Member vote lows (day 5-7, 12Z): position and depth only (not a field).
8. **Outlier drop (the desk habit, Jason 2026-11-16 16:33Z):** per storm group, the consensus position = mean of the ensemble-mean lows (GEFS, ENS, AIFS-ENS; GEFS only in the GFE version). Any deterministic run whose low in that group sits more than X km from the consensus is left out of the blend near that storm (field weight tapered to zero within ~1000 km of the low, so no seams), and the rest are blended. X fixed per lead on tuning weeks from {200, 300, 400, 600} km (fit as a fraction of the lead's typical spread if a fixed X doesn't hold across leads). Rivals: the plain blend of the same runs and the aligned blend. Also reported: how often a dropped run was the closest to the analysed low (the risk of the habit), by lead, basin and which model was dropped.

**Two answers:** best possible, and best with Jason's AWIPS inputs (GFS, ECMWF, AI-GFS, GEFS mean; the GEFS mean helps place lows but never sets depth).

**Win rule per lead (set now):** a candidate is "best" if, against IFS (the reference single model):
- mean position error >= 10 km and 5% lower, interval excluding zero, surviving Benjamini-Hochberg (q = 0.10) across candidates x leads;
- RMSE no more than 0.15 hPa worse (upper interval bound);
- false lows no more than +0.15 per map (or it wins at equal false lows);
- strong-low depth bias no worse by more than 0.5 hPa;
- same sign against both analyses, in both basins, and on the held-out weeks.
Ties go to the simpler method, then to the one GFE can use. A mirror rule names a separate "best field on RMSE" so Jason sees both if they differ.

## Part B: what probability says about it
Each product must beat a simple rival fitted the same way (the tuning-week error climatology by lead) and be reliable.
- **Chance the low exists:** vote support, recalibrated (isotonic) per lead. Event: analysed low < 1000 within 300 km.
- **Depth:** chance below 990/980/970/960 hPa and a 10-90% range from the runs' own depths, one spread factor per lead (flat PIT). The map low sits at the 50% depth.
- **Position:** fixed 50%/80% error circles per lead (and support tercile), not member scatter (r ~ 0.1 with error).
- **Alternative scenario:** at most 2 member clusters besides the most likely, shown only with >= 20% of members and > 300 km or > 8 hPa different.
- **Verification:** reliability (bins within +-10 points, counted in event-weeks; < 5 event-weeks = "not verifiable"), fair Brier / CRPS skill vs the rival, 80% range covering 72-88%, and both directions (every analysed low and every forecast low).
- Days 1-4 and 00Z have no stored members: Part B there rests on the deterministic runs, error climatology and ensemble spread, and is labelled weaker. A member pull for days 1-4 needs Jason's go.

## Display (proposal, built only after Part A/B pass; screenshots first)
Default: most-likely isobars every 4 hPa, plain; each low labelled "L 956 (948-966) 95%" (depth, 10-90% range, chance it exists); a faint "L?" below 30%; G/E/AI marks where the single models put it. On request: low-track chance shading, deep-storm chance (< 980/970), alternative scenario, member Ls. GFE: the most-likely MSLP as a normal grid; chances in a table, not more grids.

## Worked cases
Chosen by rule before scoring: the deepest analysed low per month per basin, and the largest model split at day 5. Each shows ensemble mean with member lows, our most-likely field, and the analysis.

## Traps (from the panel and LESSONS.md)
Smooth fields winning RMSE; scoring a model on its own analysis; equal false lows when comparing low finders; a confident consensus low that no run forecast; more tuned values than one winter supports (cap ~12 new); int16 store precision changes low counts; whole-winter reads fill the disk (read each basin-cycle once, keep MSLP only, delete the unpacked cycle).

## Data
All in the store; no pull. ~600 basin-cycles x ~60 MB read once, reduced to MSLP-only local files.

## Out of scope
Wind from pressure (dead end, 2026-10-13); recent-skill weighting (dead end, 2026-10-13); page and GFE changes until Jason agrees.

## Notes from the independent recompute (2026-11-16, after scoring)
- Headline position, hit rate, false lows and RMSE for IFS, GFS and GFS+IFS reproduced to rounding (`verify.py`, `results/verify.csv`).
- `strong_bias` counts every analysed low < 980 hPa, charging a miss the forecast field value at the analysed centre; it is not hits only (GFS +168: 10.0 with misses, 7.3 hits only). Quote it as such.
- IFS at +144/+168 is scored on 604 cases where its keys exist; GFS and the GFS+IFS mean on 585. Matched-case comparisons shift IFS +144 by about 1 km.
