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

## rk/cases.py
- `tag(dt) -> "YYYYMMDDHH"`, `parse(tag) -> datetime`.
- `cycles(basin, start, end, every_days=1, hour=None) -> list[datetime]` (hour defaults to the basin's).
- `winter(dt) -> bool`: November to March.
- `held_out(dt) -> bool`: the fixed held-out weeks. ISO week w of ISO year y is held out when `(y * 53 + w) % 5 == 0` (about one week in five). Never tune on these. Fixed 2026-10-16; never change it.
- `split(dt) -> "tune" | "held_out"`.
- `available(model, dt) -> bool`: archive start dates on AWS: gfs, gefs, ifs, ens, aifs from 2025-03-01; aifs-ens from 2025-08-01.
- `STEPS = (24, 48, 72, 96, 120)` default leads (h).

## rk/fetch.py (AWS open-data mirrors, byte-range GRIB)
- `get(url, rng=None)`: pooled session; None on 403/404; 503 SlowDown retried fast with jitter (up to 60 times); other errors exponential backoff.
- Before any network work, `wait_for_quiet()`: if the UTC time is within the marine wind page build windows (02:15-03:15, 08:15-09:15, 14:15-15:15, 20:15-21:15 UTC), sleep until the window ends and say so on stderr. `RK_IGNORE_BUILD_WINDOWS=1` skips it.
- Every decoder crops both basins from one GRIB message.
- `det(model, cycle, step) -> {basin: {"u","v","msl"}} | None` for model in `gfs`, `ifs`, `aifs` (u, v m/s, msl hPa). Step 0 of gfs/ifs is the analysis.
- `members(ens, cycle, step, msl=True) -> {basin: {"u": [n,y,x], "v": [n,y,x], "msl": [n,y,x]}} | None` for ens in `gefs` (c00 + p01..p30), `ens` (IFS ENS, `-ef`), `aifs-ens` (`-cf` + `-pf`).
- `gdas_background(valid) -> {basin: {"u": [7,y,x], "v": [7,y,x], "land"}}`: the previous GDAS cycle's f003..f009 10 m wind, for building ship and buoy winds.

## rk/store.py (shared field cache under DATA/fields)
- Layout: `fields/{basin}/{YYYYMMDDHH}/{model}_f{step:03d}.npz` (deterministic: u, v float16 m/s, msl float32 hPa) and `{ens}_f{step:03d}.npz` (member statistics: `mean_u`, `mean_v` (mean of members' u, v), `spd_mean`, `spd_std` (kt), `p34`, `p48`, `p64` (fraction of members), `msl_mean`, `msl_std` (hPa), `n` members). Written with `np.savez_compressed`, atomically (temp file then rename).
- `load_det(basin, cycle, model, step) -> {"u","v","speed","msl"} | None` (speed in kt, float32).
- `load_ens(basin, cycle, ens, step) -> dict | None`.
- `fill(cycle, steps=STEPS, models=..., ens=..., workers=6) -> report dict`: fetch what is missing for both basins at once; skip a cycle's ensemble if fewer than 20 members came back; never mix runs.
- `analysis(basin, valid) -> {"gfs": det, "ifs": det, "mean_speed" (kt), "msl" (hPa, mean), "mask" (open, ice-free water)} | None`, cached under `truth/analysis/{basin}/{YYYYMMDDHH}.npz`. `analysis_arrays(g, i, land, ice)` builds the stored arrays (shared with `tools/import_wx_cache.py`, which imports another study's analysis cache into this layout).

## rk/truth.py
- `analysis(basin, valid)`: re-export of `store.analysis`. The project's standard truth for WHERE.
- `obs(basin, valid, platforms=("buoy","drifter"), adjust10m=True) -> dict of 1-D arrays | None`: ship and buoy winds rebuilt as GDAS first guess + O-B departure from `gdas.YYYYMMDD/HH/atmos/wdqms/gdas.tHHz.marine.csv`, background from the previous cycle's f003-f009. Status 0 only, +-1 h, open water, blacklist (`rk/data/obs_blacklist_basins.txt`) and the 75 fixed coastal stations (`rk/data/fixed_stations.txt`) removed. Buoys raised from 4 m to 10 m (neutral Charnock); ships scaled by 0.88. Fields: lat, lon, speed_kt, speed_kt_raw, u, v, station_id, platform.
- `ascat(basin, valid, max_dt_min=90, real=True, intercal=True) -> dict | None`: RSS ASCAT v2.1 (Metop-B, C) cells within the window, rain dropped, open water only; `spd_kt` is real 10 m wind (converted from equivalent-neutral with the analysis air-sea temperature difference) when `real=True`, else equivalent-neutral; also `spd_enw_kt`, `spd_enw_raw_kt`, `dt_min`, `sat`. `intercal` (default on) meets Metop-B and C halfway: half the speed-dependent B-C gap (+0.30 kt at 25-35 kt to +1.25 at 55+, table `INTERCAL_*`, from winter 2025-26 same-cell pairs, `chance-calibration/ascat_noise/results.md`, 2026-10-16) is subtracted from B and added to C on the equivalent-neutral speed before the real-wind conversion, so `spd_enw_kt` and `spd_kt` carry it; `spd_enw_raw_kt` is unadjusted; `intercal=False` gives the raw RSS values. Raw daily cells cached under `truth/ascat/{YYYYMMDD}.npz`.
- `enw_to_real(enw_kt, dT)`.
- ASCAT on the model grid (offline helpers plus one loader):
  - `ascat_to_grid(basin, lat, lon, spd_kt) -> (grid, count)`: snap to the basin's 0.25 deg grid with floor(x+0.5); cells in the same grid cell are averaged; NaN where none.
  - `box_mean(grid_kt, min_valid=6, size=3) -> (mean, n_valid)`: mean of valid cells in the 3x3 box, NaN where fewer than 6 of 9 are valid (edges count missing cells as invalid; the centre need not be valid).
  - `ascat_grid(basin, valid, correct=True, real=True) -> {"cells", "box", "n_box"} | None`: `ascat()` cells, from `ascat(..., intercal=)` (Metop offset handled there), on the basin grid (kt, float32, NaN = no truth). Event = `box >= thr` (the main truth for chances) or `cells >= thr` (single cell, for comparison).

## rk/calibrate.py (plain numpy arrays in; chances 0-1, knots in percent)
- `EDGES`: bin edges `[0, .01, .02, .05, .10, .15, .20, .30, .40, .50, .60, .70, .80, .90, 1.00001]`. `LEAD_GROUPS = {"le48": (24, 48), "72": (72,), "ge96": (96, 120)}`; `lead_group(step)`.
- `table(p, event, edges=EDGES, w=None) -> dict` of per-bin arrays `n, events, sum_p, sum_p2, sum_p_ev` (w = optional counts); `add_tables(*tabs)` sums them, so many cycles pool without keeping cells.
- `reliability(p, event, edges=EDGES) -> dict`: per bin `n`, `events`, `mean_fc` (mean forecast), `obs_freq` (NaN if empty), `edges`.
- `fit(table, nmin=2000) -> (raw_knots_pct, cal_knots_pct)`: the page's fitter (`wind-focus/basins/code/fit_calibration.py`): bin mean raw -> observed frequency, shrunk toward raw by min(1, n/nmin), starts (0, 0), ends (100, 100) if the data stop short, calibrated forced non-decreasing. Takes a summed table or a `reliability()` dict; one truth.
- `apply(p, raw_knots, cal_knots)` -> 0-1; `cal_at(raw_pct, raw, cal)` -> percent; `raw_for(target_pct, raw, cal)` -> the lowest raw percent that gives the calibrated target (NaN if never reached).
- `brier(p, event, w=None)`, `brier_skill(p, event, clim, w=None)` (1 - BS/BS of the constant clim; NaN when climate is perfect), `reliability_error(table)` (n-weighted RMS of mean forecast minus observed frequency over bins, 0-1).
- `to_page_json(curves, note="", path=None)`: `curves = {(thr, basin, group): (raw, cal)}` -> the layout of awips-tools `marine_wind/pipeline/calibration.json`: `{"note", "thresholds": {"48": {"natl": {"le48": {"raw", "cal"}, "72": ..., "ge96": ...}, "npac": ...}, "64": ..., "34": ...}}`.

## rk/score.py (grids: forecast and truth on the same grid; mask optional)
- `contingency(fc, ob, thr, mask=None) -> (hits, false_alarms, misses)`.
- `csi`, `pod`, `far`, `area_ratio(fc, ob, thr, mask=None)` (area ratio = forecast area / observed area).
- `fss(fc, ob, thr, n=5, mask=None)`.
- `error(fc, ob, min_kt=25, mask=None) -> {"bias","mae","rmse","n"}` over cells where either is at least min_kt.
- `tile_peaks(fc_at_obs, ob, lat, lon, size_deg=5, min_n=150, min_peak=34) -> DataFrame` one row per tile: obs max and p98, forecast max and p98 at the same points.
- `points(fc, basin, obs) -> DataFrame` sample a grid at obs points, with error columns.

## rk/compare.py
- `paired(df, method, baseline, value, by=None, block="week", n_boot=2000, seed=0) -> DataFrame`: mean difference method minus baseline with 95% intervals from resampling whole ISO weeks (storms within a week are not independent). Column `significant`.
- `table(df, methods, baseline, value, by="step") -> DataFrame` formatted for a findings file.

## rk/style.py (light figures; see STYLE.md)
- `use()`: apply the house matplotlib style.
- `METHOD_COLORS`, `METHOD_LABELS`: fixed per method key (gfs, ifs, aifs, mean3, blend, corelift, gefs, ens, aifs-ens, desk, analysis, ascat, buoys).
- `WIND_LEVELS`, `wind_cmap()`, `wind_norm()`: the page's knot breaks; gale and above in the page's colours.
- `HAZARD_COLORS` for gale, storm, hf. `BASIN_COLORS` (natl, npac): one colour per basin, for figures that compare basins (distinct from the method hues).
- `title(ax, finding, detail)`: finding as the title, case count and period beneath.
- `save(fig, path)`: PNG at 150 dpi plus the same name in SVG.
