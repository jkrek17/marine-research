# Lessons

Anything that made us change a result we had treated as finished, or cost a study a day. One line each: the rule, then why. When a lesson can be a check in `rk/` or `tests/`, make it one and say so here.

## Truth
- **Analysis for where, ASCAT and buoys for how strong.** Analyses understate storm peaks; ASCAT is sharper than any 0.25 deg grid (verifying analysis caught 25% of ASCAT storm tiles).
- **ASCAT is equivalent-neutral wind.** Convert to real 10 m wind with the air-sea temperature difference before comparing with model wind. *In `rk.truth.ascat(real=True)`.*
- **ASCAT coverage follows the satellite, not the study.** At 12 UTC it covers the Atlantic and barely the western edge of the Pacific box; the Pacific is seen at 00 UTC. *Basin default hours in `rk.basins`.*
- **75 fixed coastal stations hide in the ship table** and read 3-5 kt low in offshore cold flow. *Removed in `rk.truth.obs`.*
- **Buoys sit at ~4 m, ships run high.** Raise buoys to 10 m (neutral profile), scale ships by 0.88. *In `rk.truth.obs`.*
- **RSS ASCAT cell centres sit 0.125 deg off the 0.25 deg model grid.** Snap with floor(x + 0.5), not np.rint: half-to-even rounding empties every other row and column.
- **Metop-B reads ~1 kt higher than Metop-C at storm force**, and 1 kt moves the 48 kt frequency ~17%; single-cell noise matters far less (~5%). *`rk.truth.ascat(intercal=True)` meets them halfway.*
- **RSS ASCAT lags about 2 days.** Score days at least 3 days back, or the truth is missing, not the wind.
- **The hf-low archive has typo dates** (e.g. `2018232906` in the Atlantic sheet); a strict date parse fails the whole file. *`rk.truth.hf_archive` drops rows whose date does not parse.* Fixes belong in the spreadsheet (hf-low's "Fixes wanted in the sheet").
- **Score warnings on issued areas only where the text parsed completely.** The HSF parser reads about 2 in 3 winter hours fully; a partial mask makes the desk look like it missed.
- **ERA5 is too weak to referee gales** (catches 49 of 131 buoy gales vs 80 for the operational analyses). Fine for pressure.
- **Don't trust MSLP gradients over Greenland or within ~80 km of land** for wind; they are reduction artefacts.

## Method
- **Condition bias on the forecast, not on the truth.** Binning on observed speed manufactures a low bias (regression to the mean); "storm areas 5 kt low" was this artefact.
- **The sample is weeks, not cases.** Storms within a week are not independent; resample whole weeks. *`rk.compare.paired`.*
- **Hold out weeks before you look.** The fixed held-out weeks are in `rk.cases.held_out`; tune on the rest, score the held-out weeks once.
- **Name a method for what it does.** "A 60th-percentile lean" not "bias correction"; Jason catches oversold labels.
- **A recipe can win on averages and lose the peaks.** Score storm force on tile peaks as well as cell scores (`rk.score.tile_peaks`).
- **A peak miss is usually smoothing, not stability.** The 30 m/10 m switch and x1.10 catch storm peaks only by adding wind everywhere (gale false alarms 12% to 30%, buoys +3.9 kt); +5 kt only where core likelihood >= 35% caught the same 49% with 15% false alarms. Fix the core, not the field.
- **Models already place the core.** 60 synoptic and conceptual clues (fronts, jets, quadrant, storm type, pressure gradient) added ~0.01 BSS beyond the models' and members' own winds; test a new clue against that baseline before building on it.
- **Set each hazard line from its own hit-versus-area curve, and show real cases.** Reusing the storm-core score for the HF line made a huge HF area; Jason wants lines that follow the probabilities, unpadded.
- **Check a live port against the research table at matched cells.** The storm-core model's live features matched the study within r >= 0.994 before it shipped; do this for any exported model.
- **Don't overstate one score.** "AIFS for track" was claimed from one metric and walked back; check position, depth and misses together.

## Running
- **Don't run heavy downloads during the marine wind build** (~02:30, 08:30, 14:30, 20:30 UTC) or alongside a verification backfill: ECMWF pulls fail. *`rk.fetch.wait_for_quiet`.*
- **Fresh ECMWF ENS files return 503 SlowDown.** Retry fast with jitter, many times. *`rk.fetch.get`.*
- **Caches in session folders die with the session.** Fields and truth go in the shared data folder through `rk.store`.
- **`pkill -f pattern` and `pgrep -f pattern` match their own shell.** Wait on a PID or a log line.
- **Don't mix runs in one case.** If a model is missing for a cycle, skip the cycle.
- **The session container is reclaimed when idle and kills detached (nohup) jobs; keep a background watcher running while they work.**
- **Fork plus OpenMP deadlocks** after an sklearn fit: use a spawn pool.
- **Date line:** keep Pacific longitudes 160-245; -180..180 broke distances and lost lows once.
- **The forecast-record grid starts at 180W, not 0E.** Crop with `(IX - 720) % 1440`, and test crops on real data shapes, not toy grids.
- **GitHub can skip scheduled jobs for hours** (every one from 01:41 to 08:28Z on 10-16). Check the Actions run history before blaming code; dispatch a missed cycle by hand only after its ensembles are complete.
- **Draft PRs must be marked ready before they merge.** Fetch force-pushed data branches with a `+` refspec, or the fetch is refused.
- **The shared folder has a 10 GB quota.** It filled on 10-16 and blocked every thread's writes. Model fields go through `rk.store` to the data repo releases; the shared folder holds truth and small results only.
- **netCDF4/HDF5 is not thread-safe.** Reading SMAP files from 4 threads raised `NetCDF: HDF error` and hung the fill. *`rk.truth._smap_cells` holds a lock around the read.*
- **Apply the decision rule with the method the design named.** The first storm-truth draft passed the rule on a check method (same-cell pairs) when the pre-set storm-peak test had failed; the independent check caught it. Say "not passed" and give the default.
- **Peaks picked by one instrument flatter it.** Storm peaks selected in ASCAT put SMAP 6 kt higher at 56-64 kt; selected in SMAP, 1 kt lower. Always run both directions.
- **A missing remote file can come back as an HTML page, not an error.** SMAP FINAL files have no `_FINAL` suffix; the guessed name returned an HTML 404 page that looked like a download. Check the file's magic bytes before caching. *`rk.truth._smap_get`.*
- **Check a proposed avenue against the dead ends before ranking it.** The research agenda's first draft ranked aligned-member wind #1; `core/lift.md` had already tested it (CSI .30 vs .45). Search the findings before calling anything new.
- **Compare low-finding methods at equal false lows.** A method that draws more lows misses fewer and so looks better on position; one that draws fewer looks better on false alarms. The day 5-7 vote was tuned on whole curves (position vs false lows per map), not single points. *`studies/2026-10-16-pressure-d5-7/tune.py`.*
- **A study's stored precision is part of its method.** The day 5-7 study kept MSLP as int16 in 0.1 hPa; at that step shallow minima tie or vanish, and float store fields give 3% fewer analysed lows (275 vs 284). The standing-score preset rounds the same way, which brings the GFS day-5 score to 347.6 vs 350.1 km and IFS/AIFS to the last digit. *`studies/2026-10-16-pressure-d5-7/preset.py`.*
- **Snapshot the desk's NDFD grid about 3 h after the issuance hour, per basin.** The full Atlantic update shows in the 10Z/22Z snapshots, the Pacific one only at 13Z/01Z (its 10Z/22Z files are nearly unchanged), and winter edits keep landing later. *Global view and Desk value threads; awips-tools #122.*
- **Score every method on the desk's own cells when the desk is a method.** NDFD oceanic covers only 37-81% of each basin box; use `rk.basins.opc_mask` (HSF areas: no water east of 35W or in the western Pacific) so harness, Desk value and verification-page numbers match.
