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
- **ERA5 is too weak to referee gales** (catches 49 of 131 buoy gales vs 80 for the operational analyses). Fine for pressure.
- **Don't trust MSLP gradients over Greenland or within ~80 km of land** for wind; they are reduction artefacts.

## Method
- **Condition bias on the forecast, not on the truth.** Binning on observed speed manufactures a low bias (regression to the mean); "storm areas 5 kt low" was this artefact.
- **The sample is weeks, not cases.** Storms within a week are not independent; resample whole weeks. *`rk.compare.paired`.*
- **Hold out weeks before you look.** The fixed held-out weeks are in `rk.cases.held_out`; tune on the rest, score the held-out weeks once.
- **Name a method for what it does.** "A 60th-percentile lean" not "bias correction"; Jason catches oversold labels.
- **A recipe can win on averages and lose the peaks.** Score storm force on tile peaks as well as cell scores (`rk.score.tile_peaks`).
- **Don't overstate one score.** "AIFS for track" was claimed from one metric and walked back; check position, depth and misses together.

## Running
- **Don't run heavy downloads during the marine wind build** (~02:30, 08:30, 14:30, 20:30 UTC) or alongside a verification backfill: ECMWF pulls fail. *`rk.fetch.wait_for_quiet`.*
- **Fresh ECMWF ENS files return 503 SlowDown.** Retry fast with jitter, many times. *`rk.fetch.get`.*
- **Caches in session folders die with the session.** Fields and truth go in the shared data folder through `rk.store`.
- **`pkill -f pattern` and `pgrep -f pattern` match their own shell.** Wait on a PID or a log line.
- **Don't mix runs in one case.** If a model is missing for a cycle, skip the cycle.
- **Fork plus OpenMP deadlocks** after an sklearn fit: use a spawn pool.
- **Date line:** keep Pacific longitudes 160-245; -180..180 broke distances and lost lows once.
- **netCDF4/HDF5 is not thread-safe.** Reading SMAP files from 4 threads raised `NetCDF: HDF error` and hung the fill. *`rk.truth._smap_cells` holds a lock around the read.*
