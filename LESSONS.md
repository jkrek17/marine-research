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

- **Count the chances' sample in weeks, and check the cycles with an event.** Hundreds of thousands of cells came from 14 held-out cycles per basin; 64 kt had 1-4 cycles with an event. State it before any curve. *Counts in `studies/2026-10-16-chance-calibration/` results.csv.*
- **A chance calibrated on one ensemble does not carry to the pool.** GEFS alone over-forecasts gale against ASCAT in the Atlantic while the pooled page chance under-forecasts it.
- **Count the reach in the area.** `rk.score.warning_events` lets a warned cell catch an event 60 nm away without billing that ring as warned area; around small blobs the ring is 2-6x the drawn area. Report cell coverage and area including the reach beside events caught (audit 2026-10-17: strongest-model storm line 1/4 of the desk's area as published, about 0.6 counted fairly).
- **Shrink thin calibration bins toward a neighbouring curve, not toward the raw chance, and pool bins instead of a running maximum.** `rk.calibrate.fit` shrinks toward the raw share, which is what is wrong, and the running maximum leaves shelves: the page shows 66-76% Atlantic day 3-5 storm chance where held-out cells verified 85-100%, and Pacific storm chance stays near the raw share. Check the high bins on held-out weeks; the overall reliability error hides them.
- **Pair a forecast with the desk product issued after the forecast was available.** The 0430 UTC HSF could not see the 00 UTC ECMWF, AIFS or their ensembles; giving the models those runs flatters them (the warning study's gale win does not survive a full day's staleness; storm and HF do).
- **Say what a filter dropped.** The HSF hours that failed to parse were busier: a third of the storm events and two fifths of the HF lows.
- **Re-test claims made against analyses once ASCAT is the referee.** "A lone storm-force model verifies 1-3%" (analysis) is about 80% within 50 km of ASCAT 48+ (Atlantic winter; `/mnt/project-files/audit/`).

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
- **NDFD oceanic GRIB uses alternative row scanning, and eccodes 2.50 leaves the values in file order while its latitudes and longitudes run west to east on every row.** Every second row came out mirrored; the first winter of desk grids scored 15 kt MAE against ASCAT before the High seas thread caught it. Check a new grid's north-south roughness against its east-west roughness before scoring. *`rk.desk.unscan` and its row check; `tests/test_desk.py`.*
- **Compare low-finding methods at equal false lows.** A method that draws more lows misses fewer and so looks better on position; one that draws fewer looks better on false alarms. The day 5-7 vote was tuned on whole curves (position vs false lows per map), not single points. *`studies/2026-10-16-pressure-d5-7/tune.py`.*
- **"Lowest false alarms that still pass" picks rules that only just pass.** Pre-set the warning-rule choice with a margin (or report the most-margin passing rule too): the gale pick by lowest false area held out at 82%, while the strongest-model +1 kt rule passed the same desk test at 97%. *`studies/2026-10-16-warning-forecast/summarize.py`.*
- **Say which desk definition a desk hit uses.** Desk HF catch is 56% counting areas whose wind range reaches 64 kt, 66% counting any low under a HURRICANE FORCE header; two thirds of the misses were HF-header lows with ranges topped at 55-60 kt.
- **Retry reads from the shared folder.** It is a network mount; one transient I/O error killed a 40-minute scoring pool. Wrap per-case work in a short retry.
- **A study's stored precision is part of its method.** The day 5-7 study kept MSLP as int16 in 0.1 hPa; at that step shallow minima tie or vanish, and float store fields give 3% fewer analysed lows (275 vs 284). The standing-score preset rounds the same way, which brings the GFS day-5 score to 347.6 vs 350.1 km and IFS/AIFS to the last digit. *`studies/2026-10-16-pressure-d5-7/preset.py`.*
- **Snapshot the desk's NDFD grid about 3 h after the issuance hour, per basin.** The full Atlantic update shows in the 10Z/22Z snapshots, the Pacific one only at 13Z/01Z (its 10Z/22Z files are nearly unchanged), and winter edits keep landing later. *Global view and Desk value threads; awips-tools #122.*
- **Score every method on the desk's own cells when the desk is a method.** NDFD oceanic covers only 37-81% of each basin box; use `rk.basins.opc_mask` (HSF areas: no water east of 35W or in the western Pacific) so harness, Desk value and verification-page numbers match.
- **Check what an archive covers before setting a study's period.** NDFD oceanic grids carry OPC high-seas water only from 2026-01-13 22Z; the desk-value design assumed the whole winter. Measure coverage on one file per month first.
- **Never score from a cache that is being re-filled.** Desk-value issuances scored mid-refill came back with 0 rows and silently dropped out of the means. Finish the fill, then score; check row counts per issuance.
- **Average error rewards smooth fields; pair it with storm-force catch.** The 3-model mean beats the desk by about 1 kt on error at 25+ kt and catches 8% of ASCAT 48+ kt cells to the desk's 64%. Never rank methods on error alone.
- **Name columns for the cells they count.** `toward`/`away` in the desk-value rows counted every ASCAT cell, `toward_ed`/`away_ed` only edited cells; a draft quoted the wrong pair until the independent check caught it.
- **Test that a spread display sorts cases before drawing it.** Day 5-7 member low centres, scaled to the right average size, barely sort good lows from bad (error 320 km tight vs 349 km wide, r ~0.1); member central-pressure ranges do (3 vs 5-7 hPa). Check coverage and whether wider means worse, per display.
- **Long downloads die with the session container.** nohup/setsid jobs were killed twice when the container idled; run them as a tracked background task (≤2 h, re-armed) and make them resumable by date.
- **Version-stamp caches written by a reader that later changed.** A desk grid decoded before `rk.desk.unscan` (research-data/desk/natl/2026011510.npz) stayed in the shared cache and differs from a fresh read by 4.6 kt on average, up to 47 kt; `rk.desk.load` would have returned it.
- **Count the catching ring as area.** A line credited with any event within 60 nm, but charged only for its own cells, rewards thin lines: the gale +1 kt rule "caught" 96% while covering 88% of the gale water (desk 97%). Report cells covered and the area with the ring, and pick offsets on coverage.
- **Group lead times the way the page does.** `rk.calibrate.lead_group` put +54 h and +78 h steps in day 4-5 while the page build puts them in day 3; any 06/18 UTC or 6 h step score would have used the wrong curve. Kit helpers that mirror page logic get a test pinned to the page's rule.
