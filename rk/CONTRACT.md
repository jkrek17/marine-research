# rk: module contract

The interfaces every module in `rk/` keeps, so studies can rely on them. Change a signature here first, then in code.

## Conventions
- Python 3.11+, numpy. No absolute paths in code except the `RK_DATA` default in `rk/paths.py`. Find the repo from `__file__`.
- Times: cycles and valid times are naive UTC `datetime.datetime`. String form `YYYYMMDDHH` (`rk.cases.tag(dt)`).
- Grids: 0.25 deg, rows north to south, columns west to east, longitudes 0-360 (continuous across the date line; the Atlantic box stays below 360).
- Units in public returns: wind speed in **kt**, u/v in **m/s**, MSLP in **hPa**. `rk.KT = 1.943844` (m/s to kt).
- Missing data: a loader returns `None`; it never fabricates or fills. 403/404 from a server means "not posted".

## rk/paths.py
- `REPO`: repository root (`Path`, from `__file__`).
- `DATA`: `Path(os.environ.get("RK_DATA", "/mnt/project-files/research-data"))`.
- `data(*parts) -> Path`: path under DATA; creates parent dirs.

## rk/basins.py
- `BASINS = {"natl": {...}, "npac": {...}}` with keys `name, north, south, west, east, hour`.
  - natl: "North Atlantic", 67, 30, 285.0, 359.75, hour 12
  - npac: "North Pacific", 67, 30, 160.0, 245.0, hour 0
  (These are the boxes every study since 10-13 was tuned and scored on. `hour` is the default cycle and valid hour: ASCAT covers the Atlantic at 12 UTC and the Pacific at 00 UTC.)
- `grid(basin) -> (lats, lons)` 1-D arrays.
- `crop(basin) -> (iy: slice, ix: np.ndarray)` indices into the global grid (lat 90..-90 721 rows, lon 0..359.75 1440 cols).
- `sample(field, basin, lat, lon) -> np.ndarray` bilinear; lon any convention.
- `inside(basin, lat, lon) -> bool array`.
- `to_quarter(field_half, basin) -> np.ndarray` bilinear regrid of a 0.5 deg field (every second 0.25 point of the box, same north/west origin) onto the basin's 0.25 deg grid; exact at shared points; a trailing 0.25 row/column with no 0.5 neighbour repeats the last (natl has 300 columns).

## rk/cases.py
- `tag(dt) -> "YYYYMMDDHH"`, `parse(tag) -> datetime`.
- `cycles(basin, start, end, every_days=1, hour=None) -> list[datetime]` (hour defaults to the basin's).
- `winter(dt) -> bool`: November to March.
- `held_out(dt) -> bool`: the fixed held-out weeks. ISO week w of ISO year y is held out when `(y * 53 + w) % 5 == 0` (about one week in five). Never tune on these. Fixed 2026-10-16; never change it.
- `split(dt) -> "tune" | "held_out"`.
- `available(model, dt) -> bool`: archive start dates on AWS: gfs, gefs, ifs, ens, aifs from 2025-03-01; aifs-ens from 2025-08-01.
- `STEPS = (24, 48, 72, 96, 120)` default leads (h).

## rk/fetch.py (AWS open-data mirrors, byte-range GRIB)
- Delegates to the shared `nwp` package (awips-tools/nwp) at b38f9d437ec8acdfc48a344fbe4bc16096eaee1d, pinned in requirements.txt; bump deliberately. HTTP, retries, index parsing, URLs, decoding and the MSLET fallback live in nwp; rk keeps the build-window wait, the two-basin cut of one global decode, Pa to hPa and member assembly. The public API below is unchanged.
- `get(url, rng=None)`: pooled session; None on 403/404; 503 SlowDown retried fast with jitter (up to 60 times); other errors exponential backoff.
- Before any network work, `wait_for_quiet()`: if the UTC time is within the marine wind page build windows (02:15-03:15, 08:15-09:15, 14:15-15:15, 20:15-21:15 UTC), sleep until the window ends and say so on stderr. `RK_IGNORE_BUILD_WINDOWS=1` skips it.
- Every decoder crops both basins from one GRIB message.
- `det(model, cycle, step) -> {basin: {"u","v","msl"}} | None` for model in `gfs`, `ifs`, `aifs` (u, v m/s, msl hPa). Step 0 of gfs/ifs is the analysis.
- `low(model, cycle, step) -> {basin: {"t2","skt","u925","v925","t925","u850","v850"[, "land","ice"]}} | None` for model in `gfs`, `ifs`, `aifs` (temperatures K, winds m/s; `land` and `ice` 0-1, gfs only, from LAND and ICEC). Key maps `GFS_LOW`, `EC_LOW_SFC`, `EC_LOW_PL` copied from the marine wind page. None if not posted or any field is missing.
- `members(ens, cycle, step, msl=True) -> {basin: {"u": [n,y,x], "v": [n,y,x], "msl": [n,y,x]}} | None` for ens in `gefs` (c00 + p01..p30), `ens` (IFS ENS, `-ef`), `aifs-ens` (`-cf` + `-pf`).
- `gdas_background(valid) -> {basin: {"u": [7,y,x], "v": [7,y,x], "land"}}`: the previous GDAS cycle's f003..f009 10 m wind, for building ship and buoy winds.

## rk/store.py (shared field cache under DATA/fields)
- Layout: `fields/{basin}/{YYYYMMDDHH}/{model}_f{step:03d}.npz` (deterministic: u, v float16 m/s, msl float32 hPa) and `{ens}_f{step:03d}.npz` (member statistics: `mean_u`, `mean_v` (mean of members' u, v), `spd_mean`, `spd_std` (kt), `p34`, `p48`, `p64` (fraction of members), `msl_mean`, `msl_std` (hPa), `n` members). Written with `np.savez_compressed`, atomically (temp file then rename).
- `load_det(basin, cycle, model, step) -> {"u","v","speed","msl"} | None` (speed in kt, float32).
- `load_ens(basin, cycle, ens, step) -> dict | None`.
- Lower-level fields: `fields/{basin}/{YYYYMMDDHH}/{model}_low_f{step:03d}.npz` (`t2`, `skt`, `t925`, `t850` float32 K; `u925`, `v925`, `u850`, `v850` float16 m/s; gfs only `land` uint8 = LAND >= 0.5 and `ice` uint8 = ICEC x 100). `save_low(basin, cycle, model, step, r, root=None)` (atomic) and `load_low(basin, cycle, model, step, root=None) -> dict | None` (all float32; `land` bool, `ice` fraction 0-1). `root` overrides `rk.paths.DATA`, so a local cache can be used while the shared folder is short of space. Filled by `tools/fill_low.py`.
- `fill(cycle, steps=STEPS, models=..., ens=..., workers=6) -> report dict`: fetch what is missing for both basins at once; skip a cycle's ensemble if fewer than 20 members came back; never mix runs.
- `analysis(basin, valid) -> {"gfs": det, "ifs": det, "mean_speed" (kt), "msl" (hPa, mean), "mask" (open, ice-free water)} | None`, cached under `truth/analysis/{basin}/{YYYYMMDDHH}.npz`. `analysis_arrays(g, i, land, ice)` builds the stored arrays (shared with `tools/import_wx_cache.py`, which imports another study's analysis cache into this layout).

## rk/truth.py
- `analysis(basin, valid)`: re-export of `store.analysis`. The project's standard truth for WHERE.
- `obs(basin, valid, platforms=("buoy","drifter"), adjust10m=True) -> dict of 1-D arrays | None`: ship and buoy winds rebuilt as GDAS first guess + O-B departure from `gdas.YYYYMMDD/HH/atmos/wdqms/gdas.tHHz.marine.csv`, background from the previous cycle's f003-f009. Status 0 only, +-1 h, open water, blacklist (`rk/data/obs_blacklist_basins.txt`) and the 75 fixed coastal stations (`rk/data/fixed_stations.txt`) removed. Buoys raised from 4 m to 10 m (neutral Charnock); ships scaled by 0.88. Fields: lat, lon, speed_kt, speed_kt_raw, u, v, station_id, platform.
- `ascat(basin, valid, max_dt_min=90, real=True, intercal=True) -> dict | None`: RSS ASCAT v2.1 (Metop-B, C) cells within the window, rain dropped, open water only; `spd_kt` is real 10 m wind (converted from equivalent-neutral with the analysis air-sea temperature difference) when `real=True`, else equivalent-neutral; also `spd_enw_kt`, `spd_enw_raw_kt`, `dt_min`, `sat`. `intercal` (default on) meets Metop-B and C halfway: half the speed-dependent B-C gap (+0.30 kt at 25-35 kt to +1.25 at 55+, table `INTERCAL_*`, from winter 2025-26 same-cell pairs, `chance-calibration/ascat_noise/results.md`, 2026-10-16) is subtracted from B and added to C on the equivalent-neutral speed before the real-wind conversion, so `spd_enw_kt` and `spd_kt` carry it; `spd_enw_raw_kt` is unadjusted; `intercal=False` gives the raw RSS values. Raw daily cells cached under `truth/ascat/{YYYYMMDD}.npz`.
- `smap_day(day) -> dict | None`: all valid ocean cells of one UTC day of RSS SMAP v1.0 L3 daily winds (L-band radiometer, 0.25 deg, both nodes, 15-70N, all longitudes), or None when neither file is posted. Fields: `lat`, `lon` (0-360), `t_min` (int16 minute of the UTC day), `spd_enw_kt` (equivalent-neutral 10 m wind, kt, float32), `node` (uint8; 0 ascending ~18 h local, 1 descending ~06 h local). Source `data.remss.com/smap/wind/L3/v01.0/daily/FINAL/` first, then `.../NRT/` (RSS answers a missing file with an HTML page; the bytes must carry the netCDF/HDF5 signature). Cached under `truth/smap/{YYYYMMDD}.npz` with `final` (1 FINAL, 0 NRT); a cached NRT day is not refreshed. Not rain-masked and not intercalibrated with ASCAT.
- `enw_to_real(enw_kt, dT)`.
- `ascat_target(basin, valid, thr=48.0, box=(5, 7), max_dt_min=90) -> {"seen","spd","max_nb","y"} | None`: the storm-core target on the basin grid from `ascat(real=True, intercal=True)`, cells snapped with floor(x + 0.5) (highest observation wins in a cell). `seen` (bool: ASCAT saw the cell), `spd` (kt, NaN unseen), `max_nb` (maximum of `spd` over the `box` of rows x columns, unseen cells ignored, NaN at unseen cells; (5, 7) is about 50 km, as `wind-focus/core/code/ascat_target.py`), `y` = seen & max_nb >= thr. None when a needed ASCAT day or the analysis is not posted; no seen cell gives an all-False case.

## rk/features.py (storm-core features from the store)
- `FEATURES`: the 28 feature names in `core_model.json` order of the marine wind page (awips-tools `storm.core_features`). `LOW_FEATURES`: the eight that need lower-level fields.
- `core(basin, cycle, step, low_root=None, models=("gfs","ifs","aifs"), ens=("gefs","ens"), low=True) -> dict | None`: the 28 feature grids (float32, basin grid) plus `ocean` (GFS land < 0.5 and ice < 0.5), `cand` (ocean & (r10 >= 28 | mod_max >= 34), the cells the live model scores), `basin_pac` (0 natl, 1 npac) and `no_low` (True when `low=False`). None when any required input is missing (a model, an ensemble, a low-level file, GFS land/ice); never fills. `aifs-ens` is optional (`pa48` is NaN without it).
- The store keeps ensemble statistics, so the live member operations are replaced: GEFS + ENS pooled n-weighted (`p34/p48/p64` exact, `mmean` and `sigma` exact), `m90` = pooled mean + 1.2816 x SD (live: 90th percentile of members), `r10`'s support weighting uses the closed form for normal members. `low=False` sets the eight low-level features to NaN and takes the ocean mask from `truth.analysis`. Every approximation is in the module docstring; `studies/2026-10-16-core-lift-retrain/check_live.py` compares against the live code on full members.
- `pool(stats)`, `support_closed_form(speeds, stats)`, `assemble(...)`, `k_for(step)`: the pieces, for tests and other feature sets. Constants copied from awips-tools (`SUPPORT_KT`, `CAP_KT`, `NB`), not imported.

## rk/score.py (grids: forecast and truth on the same grid; mask optional)
- `contingency(fc, ob, thr, mask=None) -> (hits, false_alarms, misses)`.
- `csi`, `pod`, `far`, `area_ratio(fc, ob, thr, mask=None)` (area ratio = forecast area / observed area).
- `fss(fc, ob, thr, n=5, mask=None)`.
- `error(fc, ob, min_kt=25, mask=None) -> {"bias","mae","rmse","n"}` over cells where either is at least min_kt.
- `tile_peaks(fc_at_obs, ob, lat, lon, size_deg=5, min_n=150, min_peak=34) -> DataFrame` one row per tile: obs max and p98, forecast max and p98 at the same points.
- `points(fc, basin, obs) -> DataFrame` sample a grid at obs points, with error columns.
- Low centres (MSLP in hPa on the basin grid; defaults are the day 5-7 lows study's `lib.py`: 13-cell window, 150 km dedupe, 300 km hit radius; lows table columns `lat, lon (0-360), hpa`):
  - `find_lows(msl, basin, below=1000.0, size=13, inset_deg=0.0, sep_km=150.0) -> DataFrame[lat, lon, hpa]`: local minima below `below`, 2 cells in from the grid edge, optionally `inset_deg` inside the box, deduplicated within `sep_km` keeping the deepest (sorted deepest first).
  - `km(lat1, lon1, lat2, lon2)`: great-circle km, longitudes in any convention (date line safe).
  - `match_lows(truth_lows, fc_lows, radius_km=300.0, miss_penalty_km=None, miss_depth="nan", fc_msl=None, basin=None) -> DataFrame` one row per truth low: `lat, lon, hpa` (truth), `matched`, `pos_err_km`, `depth_err_hpa` (forecast minus truth, negative = forecast too deep), `fc_lat, fc_lon, fc_hpa`. The nearest forecast low within the radius is the match; by default unmatched rows carry NaN errors. `miss_penalty_km` (study: 1000) gives a miss that position error, so a method that drops hard lows cannot look better by skipping them; `miss_depth="field"` (needs `fc_msl`, `basin`) gives a miss the forecast field value at the analysed centre minus the truth depth.
  - `false_lows(truth_lows_all, fc_lows, radius_km=300.0) -> int`: forecast lows with no truth low (any depth in the table given) within the radius.
  - `low_scores(truth_msl, fc_msl, basin, below=1000.0, radius_km=300.0, fc_below=None, false_radius_km=None, false_truth_below=None, miss_penalty_km=None, miss_depth="nan") -> dict(hits, misses, false, pos_err_km_median, depth_err_hpa_mean, n_truth)`: truth lows from `find_lows(..., below, inset_deg=3.0)`, forecast lows for matching from `find_lows(fc, fc_below)` (default `below`), false lows = those forecast lows deeper than `below` with no truth low under `false_truth_below` (default `below + 5`) within `false_radius_km` (default `radius_km`). Miss options go to `match_lows`; the error statistics use the filled values. Day 5-7 study call: `below=1000, fc_below=1010, radius_km=300, false_radius_km=500, false_truth_below=1005, miss_penalty_km=1000, miss_depth="field"`.

## rk/compare.py
- `paired(df, method, baseline, value, by=None, block="week", n_boot=2000, seed=0) -> DataFrame`: mean difference method minus baseline with 95% intervals from resampling whole ISO weeks (storms within a week are not independent). Column `significant`.
- `table(df, methods, baseline, value, by="step") -> DataFrame` formatted for a findings file.

## rk/style.py (light figures; see STYLE.md)
- `use()`: apply the house matplotlib style.
- `METHOD_COLORS`, `METHOD_LABELS`: fixed per method key (gfs, ifs, aifs, mean3, blend, corelift, gefs, ens, aifs-ens, desk, analysis, ascat, buoys).
- `WIND_LEVELS`, `wind_cmap()`, `wind_norm()`: the page's knot breaks; gale and above in the page's colours.
- `HAZARD_COLORS` for gale, storm, hf.
- `title(ax, finding, detail)`: finding as the title, case count and period beneath.
- `save(fig, path)`: PNG at 150 dpi plus the same name in SVG.
