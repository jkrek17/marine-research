# Day 5-7 pressure forecast: design card

*Agreed with Jason in the project thread, 2026-10-16 05:01Z. Full rules fixed before scoring: `preregistration.md`.*

**Question** (Jason's words): "craft a system that will beat the deterministic models" for "a day 5-7 forecast period", judged on the lows' "position and depth", using "ALL" runs, giving a "single best guess, plus maybe a confidence score".

**What would change if the answer is yes:** a day 5-7 best-guess MSLP layer with the lows labelled by confidence, first on a web page, GFE only if Jason agrees.

**Truth:** anl (GFS+IFS 12 UTC analysis mean). Analyses place lows well; no wind is scored.

**Baseline to beat:** GFS, ECMWF IFS and AIFS deterministic runs, each one; the grand ensemble mean as the obvious alternative.

**Win means:** on held-out weeks, smaller position error (a missed low costs 1000 km) and smaller central-pressure error than each model, without drawing more false lows than that model.

**Cases:** 12 UTC runs, 1 Mar 2025 to 8 Oct 2026, both basins (30-67N; Pacific also at 12 UTC here), leads +120/+144/+168 h; held-out weeks per `rk.cases.held_out`, tuning also drops runs whose valid date is held out.

**Data:** every GEFS/ENS/AIFS ENS member's MSLP plus the three deterministic runs (~10 MB per run, ~6 GB total), fetched with `download.py` (byte ranges, quick 503 retries, waits out build windows). Local cache `RK_CACHE/extra/mslp-d5-7`; to be published as a store extension.

**Reused / new:** reused `rk.score` (low finding, distances, false lows), `rk.cases` (held-out weeks), `rk.style`, the member-own-low idea from the live ensemble low track (storm-relative-tracking). New: member-vote lows (`method.py`), the aligned-average best-guess map (`bestguess.py`), the capped position/depth headline (`lib.py`), equal-false-low comparison (`tune.py`).

**Methods tried, simplest first:**
1. Each deterministic run.
2. Grand ensemble mean (equal weight per ensemble).
3. Member-vote lows: every member and model votes for its own lows; keep lows with enough weighted support; position = weighted mean of the voters' own lows, depth = weighted median of their own central pressures.
4. Variants: lagged runs, ensemble/model weights, support radius, depth calibration.

**Known traps:** a smooth mean wins field scores while filling lows; more lows drawn means fewer misses, so compare at equal false lows; flat-bottomed lows give twin minima.

**Out of scope:** field RMSE (Jason chose lows), winds, leads before +120 h, 00/06/18 UTC runs.
