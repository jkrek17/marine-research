# AI vs physics on the storms that matter: design card

*For Jason's yes before any run. Asked 2026-10-17 08:40Z ("can we do something fun and experimental like google deepmind"); picked idea 1 of 5 and the defaults at 08:51Z.*

**Question:** On the lows the desk warns hurricane force, does the AI model (AIFS) forecast them as well as the physics models (IFS, GFS) at days 1-5? Where does it lose: position, depth, the strength of the core, or how fast the low deepens?

**What would change if the answer is yes:** nothing on the marine wind page or in GFE. New: a public experimental page, wxmap.pro/lab, that draws each model's low tracks on the globe and carries the scoreboard. It's a separate page, so the main map stays as it is.

**What we already know:** the day 5-7 study (all analysed lows below 1000 hPa) found AIFS the best of the three on central pressure, the worst on position, and the one that draws the fewest lows. Nobody has scored days 1-5, the HF lows on their own, or the wind in the core.

**Truth:**
- Where and how deep: the hf-low archive fixes, which are the desk's own analysis of each HF low. The GFS+IFS analysis lows are a check.
- How strong: ASCAT, real 10 m wind with the Metop intercalibration applied (`rk.truth.ascat`). The analysis understates storm peaks, so it can't referee the core.

**Pre-set scores**, per model and lead (+24 to +120 h). The forecast low is the nearest one within 1000 km; it's a hit when it is within 300 km (the `rk.score.low_case` rule).
1. Position error in km, counting a miss as 1000 km, and the share found within 300 km.
2. Central pressure error against the archive pressure.
3. Core strength: the model's peak 10 m wind within 500 km of its own low, minus ASCAT's peak within 500 km of the archive fix. Scored only where ASCAT saw at least 200 cells inside that circle within 90 min. Also the share of lows where the model reaches 48 kt and 64 kt.
4. Deepening: the 24 h pressure fall in the archive against the forecast fall over the same 24 h from the same run, for leads of +48 h and longer.

**What counts as a finding (decided now):** "AIFS is weaker in the core" (or deeper, or slower to deepen, or farther off) is claimed only when AIFS minus IFS (and AIFS minus GFS) has a 95% interval excluding zero at 3 or more of the 5 leads, resampling whole weeks. Otherwise it's reported as no clear difference. Nothing is tuned, so every week is scored. The held-out split doesn't apply.

**Cases:** archive fixes inside the two basin boxes, valid at 00 or 12 UTC, March 2025 to May 2026 (the store starts in March 2025, and the sheet's last fixes are from May 2026). That's 231 Atlantic and 112 Pacific HF fixes at all hours, about half of them at 00/12 UTC, from 73 and 45 storms. Storm-force (S) fixes are a second, larger sample. The sample is weeks.

**Data:** everything is already in the store (GFS, IFS, AIFS deterministic, +24 to +120 h, both basins) plus ASCAT truth. The only downloads are the release zips of the cycles that reach a fix: about 1,500 basin-cycles at roughly 15 MB, under 25 GB, evicted after scoring. There are no AWS pulls for the retrospective scores.

**Live page (after the scores):**
- **Tracks:** after each 00/12Z run, a job on the VPS takes 6-hourly MSLP and 10 m wind for the three models from the AWS mirrors through `rk.fetch.det`. That's about 0.3 GB per run, and it waits out the build windows. The job tracks the lows to +120 h and writes a small JSON for the lab page.
- **Live scores:** three days later, once ASCAT is in, the same job scores those tracks against the analysis lows and ASCAT. It appends the results as a standing-score preset, so the record keeps growing out of sample.
- **The page:** wxmap.pro/lab reuses the map's globe, marine wind base and time slider. Each model's track is drawn in its own colour, and clicking a low opens its scorecard. The page is labelled experimental.

**Reused / new:**
- **Reused:** `rk.store.load_det`, `rk.truth.hf_archive` / `analysis` / `ascat`, `rk.score.find_lows` / `low_case` / `km`, `rk.compare.paired`, `rk.style`, the preset harness, and on the page the globe kit, the marine wind base page and the wxmap.pro map's loader.
- **New in `rk/`, with tests:** `rk.score.track_lows` (links each step's lows into tracks; the page's ensemble tracker lives in awips-tools, which this repo can't import) and `rk.score.peak_near` (the peak wind within a radius of a point).

**Methods:** this is a scoreboard, not a method; the three models are scored as they come. A fourth "method", the three-model mean low, sits beside them as a sanity line.

**Known traps:**
- Analysis for where, ASCAT for how strong.
- The sample is weeks.
- Score position, depth and misses together (the "AIFS for track" walk-back).
- RSS ASCAT lags about 2 days.
- The archive has typo dates.
- Pacific longitudes run 160-245.
- Don't score from a cache that is being refilled.
- A one-shot gate refuses when truth is missing: the counts of fixes skipped for no ASCAT are reported.

**Out of scope:** changing the marine wind page or the blend; ensembles (that is idea 4, next); other basins until this works in two.
