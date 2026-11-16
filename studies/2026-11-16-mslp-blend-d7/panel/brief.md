# Experiment design brief: best MSLP forecast / blend out to day 7

You are one member of a design panel (meteorologists and data scientists) for the NOAA Ocean Prediction Center marine desk (forecaster: Jason). Your job is to DESIGN the experiment, not to run it. Write your proposal as markdown to the file path given in your prompt (under 1,200 words). Be concrete: name methods, parameters, scores, sample sizes, and pass/fail rules. Flag traps.

## Jason's question and choices (his words in quotes)
- "what is the best MSLP forecast or blending strategy at lead times out to 7 days"
- "best means closest to the actual MSLP and lowest position error" -> two headline scores: field error vs analysed MSLP, and low-centre position error.
- "at longer lead times the pressure may not be deep enough for strong storms and its in the wrong place. how can we mitigate both errors." -> the design must include methods that fix BOTH the depth (filling/too shallow, esp. ensemble means and blends) and position error of strong lows at long leads, and must show the depth of strong lows.
- Open Atlantic and Pacific, for the marine desk. Desk forecasts the highest wind; a miss costs more than a false alarm; Jason dislikes step jumps in fields.

## What is already known (cite, don't re-test unless you argue why)
- Day 5-7 pressure study (2026-10-16): a "member vote" for lows (every GEFS/ENS/AIFS-ENS member votes for its own lows <1008 hPa, each ensemble one block, GFS/IFS/AIFS 0.3 each; low kept where weighted support within 450 km >= ~0.12-0.16; position = weighted mean of voters' lows, depth = weighted median of voters' depths) beats ECMWF/GFS/AIFS at +120/144/168 h on position (26-100 km) and depth (0.7-3.5 hPa), at ECMWF's false-low rate. Grand ensemble mean fills lows ~10 hPa by +168. Member low-centre spread does NOT predict position error (r~0.1); member depth range does. Lagged runs and depth calibration did not help (calibration added false lows).
- Recent MSLP skill (2026-10-13): weighting by trailing 3/7/15-day skill adds nothing; picking the hot model is worse. AIFS best static MSLP RMSE on ~60% of runs, largely by smoothness (misses most lows, fills deep lows ~2 hPa more). At +72 h paired low position error GFS 243, ECMWF 215, AIFS 218 km (N Atlantic).
- For wind (may or may not carry over to pressure): fitted mixes, bias correction and recent-skill weighting were dead ends.
- Lesson: compare low-finding methods at equal false lows. Lesson: stored int16 0.1 hPa precision changes low counts slightly.

## Data available now (no new downloads without Jason's go)
- Winter 2025-26 (1 Nov - 31 Mar), 00Z and 12Z cycles, two basin grids at 0.25 deg: N Atlantic 30-67N, 75W-0 (149x300); N Pacific 30-67N, 160E-115W.
- Deterministic GFS, ECMWF IFS, ECMWF AIFS: every 6 h to +168. NOAA AI-GFS (GraphCast-based): to ~+150 h, some cycles missing (e.g. 00Z in Dec).
- Ensembles GEFS (31), ECMWF ENS (51), AIFS-ENS (51): only member MEAN and SPREAD of MSLP stored at +24..+120 every 24 h (and 06/18Z-valid steps). ALL individual members' MSLP (0.5 deg) plus each member's own low centres only at +120/+144/+168, 12Z cycles, Mar 2025 - Oct 2026 (full year), with GFS/IFS/AIFS det at those leads.
- Truth: GFS analysis and IFS analysis separately at 00/12Z (plus an open-water mask). ERA5 (independent but ECMWF-family, older cycle) would be a ~2 GB pull needing a go. Scoring a model against its own analysis favours it.
- Held-out ISO weeks: (y*53+w)%5==0 (about 1 in 5; roughly 4 weeks in winter 2025-26, ~110 basin-cycles per lead). Tune only on other weeks; leave-one-month-out within tuning is the house habit. Significance: paired differences, resampled by whole weeks (2000 draws).
- Shared tools: low finder (13x13-cell local minimum, below threshold, 150 km dedupe), match lows (nearest forecast low; day 5-7 headline form: analysed lows <1000 hPa 3 deg inside box, forecast lows <1010 anywhere, nearest within 1000 km, miss costs 1000 km; hit = within 300 km; false = forecast low <1000 with no analysed <1005 within 500 km), pressure drop (ring 500 km minus centre).
- Jason's AWIPS has: det GFS, ECMWF, AI-GFS, CMC, UKMET, and GEFS probability grids. No ENS, AIFS or members. So we want two answers: best possible, and best with what GFE can use (GFS, ECMWF, AI-GFS, GEFS mean).

## Candidates on the table so far (critique, cut, add)
Single models; simple means (GFS+ECMWF, +AIFS/AI-GFS); ensemble means (GEFS, ENS, AIFS-ENS, grand); a weighted blend per lead; a lead-dependent switch; the member vote; a feature-ALIGNED blend (find each run's lows, consensus position, warp each run's field so its low moves to the consensus spot before averaging, keeping depth); centre depth from median of runs' own depths; a bounded deepening correction for strong lows only.

## Answer these in your proposal
1. Truth and how to avoid self-grading.
2. Scores: exact definitions for "closest to actual MSLP" and "position error"; how to combine or rank the two; how to stop smoothing from winning the field score unfairly (or argue it shouldn't be stopped); depth of strong lows; false lows.
3. Candidate list (cut what you'd cut) and how each is built, incl. the alignment/warping method in enough detail to code.
4. Sample, tuning vs held-out, how to get enough power, what to do about the 00Z/12Z and lead coverage gaps.
5. Win rule decided in advance, per lead.
6. The 3 biggest traps.
Write from your discipline's point of view (stated in your prompt).
