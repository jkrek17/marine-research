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
- `data(*parts) -> Path`: path under DATA; creates parent dirs. DATA holds truth tables and small results (`truth/...`, `extra/...`). It no longer receives model fields (see `rk/store.py`).
- `CACHE`: `Path(os.environ.get("RK_CACHE") or Path.home() / ".cache" / "marine-research")`. Local, per-machine cache of the model fields.
- `cache(*parts) -> Path`: path under CACHE; creates parent dirs.

## rk/basins.py
- `BASINS = {"natl": {...}, "npac": {...}}` with keys `name, north, south, west, east, hour`.
  - natl: "North Atlantic", 67, 30, 285.0, 359.75, hour 12
  - npac: "North Pacific", 67, 30, 160.0, 245.0, hour 0
  (These are the boxes every study since 10-13 was tuned and scored on. `hour` is the default cycle and valid hour: ASCAT covers the Atlantic at 12 UTC and the Pacific at 00 UTC.)
- `grid(basin) -> (lats, lons)` 1-D arrays.
- `crop(basin) -> (iy: slice, ix: np.ndarray)` indices into the global grid (lat 90..-90 721 rows, lon 0..359.75 1440 cols).
- `sample(field, basin, lat, lon) -> np.ndarray` bilinear; lon any convention.
- `inside(basin, lat, lon) -> bool array`.
- `OPC_AREAS = {"natl": [...], "npac": [...]}`: the High Seas Forecast areas as (lon 0-360, lat) outlines, copied from awips-tools `marine_wind/hsf/areas.py` (HSFAT1: 31-67N west of 35W; HSFEP1: 30-67N east of the Bering Strait - 53N172E - 50N180W - 30N180W line). `opc_mask(basin) -> bool [ny, nx]`: cells of the basin grid inside its OPC area (land not removed). Score desk products on this water only.
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
- `members(ens, cycle, step, msl=True) -> {basin: {"u": [n,y,x], "v": [n,y,x], "msl": [n,y,x]}} | None` for ens in `gefs` (c00 + p01..p30), `ens` (IFS ENS, `-ef`), `aifs-ens` (`-cf` + `-pf`).
- `gdas_background(valid) -> {basin: {"u": [7,y,x], "v": [7,y,x], "land"}}`: the previous GDAS cycle's f003..f009 10 m wind, for building ship and buoy winds.

## rk/store.py (model-field store: GitHub Releases, local cache; plus the analysis cache under DATA)
- Names: field files are `fields/{basin}/{YYYYMMDDHH}/{name}.npz` where `name` is `{model}_f{step:03d}` (`gfs_f024`, `aifs-ens_f120`) or any other name a study adds with `put` (`gfs_low_f024`). Steps are not limited to `STEPS`: f144, f168 and the 06/18 UTC cycles (f030, f054, ...) use the same names. Deterministic files hold `u`, `v` (float16 m/s) and `msl` (float32 hPa); ensemble files hold member statistics `mean_u`, `mean_v` (mean of members' u, v), `spd_mean`, `spd_std` (kt), `p34`, `p48`, `p64` (fraction of members), `msl_mean`, `msl_std` (hPa), `n` members. Written with `np.savez_compressed`, atomically (temp file then rename). File names and contents did not change with the move to releases.
- Remote (public, no auth): one GitHub release per basin and month, tag `fields-{basin}-{YYYYMM}` (e.g. `fields-natl-202511`) on `jkrek17/marine-research-data`; one asset per basin-cycle, `{basin}_{YYYYMMDDHH}.zip`, a `ZIP_STORED` zip of that cycle's npz files under their names in the layout above (flat, `{name}.npz`). URL: `https://github.com/jkrek17/marine-research-data/releases/download/{tag}/{asset}`. `RK_RELEASES` overrides the base URL (`.../releases/download`). Helpers: `release_tag(basin, cycle)`, `asset_name(basin, cycle)`, `release_url(basin, cycle)`.
- Local cache: `rk.paths.CACHE` (`RK_CACHE`), same layout, `CACHE/fields/{basin}/{cycle}/{name}.npz`. Unzipped release cycles land here. Files written here and not yet published are listed in `CACHE/fields/{basin}/{cycle}/.dirty/{name}.npz` (empty marker files, one per member).
- Read order for every field file: (a) the cache cycle dir; (b) the legacy `DATA/fields/...` dir (kept while the move to releases happens; never written); (c) download the cycle's zip from the release, unzip it into the cache (members already in the cache are kept, so unpublished local files are never overwritten), then read. A 404/403 on the zip is remembered for the process (one request per missing cycle), and so is a cycle already pulled (a member absent from a pulled zip does not trigger another download). Other HTTP errors are retried (pooled session, urllib3 retries with backoff) and then raise; they are never turned into None. `RK_OFFLINE=1` skips step (c).
- `load_det(basin, cycle, model, step) -> {"u","v","speed","msl"} | None` (speed in kt, float32).
- `load_ens(basin, cycle, ens, step) -> dict | None`.
- `load(basin, cycle, name) -> {key: array} | None`: any file by name (as stored, no dtype conversion).
- `put(basin, cycle, name, **arrays) -> Path`: write `name.npz` (no `.npz` in `name`; letters, digits, `_`, `-`, `.`) into the cache cycle dir atomically and mark it dirty. The one way studies add files (`gfs_low_f024`, f144, 06/18 UTC steps). `cycle` is a datetime or a `YYYYMMDDHH` string.
- `dirty(basin=None) -> {(basin, "YYYYMMDDHH"): [member file names]}`: cache cycles holding files not yet published. `mark_clean(basin, cycle, names)` clears marks (the publisher does this after its push).
- `fill(cycle, steps=STEPS, models=..., ens=..., workers=6) -> report dict`: fetch what is missing for both basins at once (missing = in none of cache, legacy dir, release); writes go through `put`, so they are dirty until published. Skip a cycle's ensemble if fewer than 20 members came back; never mix runs.
- `analysis(basin, valid) -> {"gfs": det, "ifs": det, "mean_speed" (kt), "msl" (hPa, mean), "mask" (open, ice-free water)} | None`, cached under `DATA/truth/analysis/{basin}/{YYYYMMDDHH}.npz` (truth stays in DATA, not in the release store). `analysis_arrays(g, i, land, ice)` builds the stored arrays (shared with `tools/import_wx_cache.py`, which imports another study's analysis cache into this layout).
- `build_zip(out, local, remote=None) -> dict`: write the release zip for a cycle from `local` ({member: Path}) merged over `remote` (zip bytes of the published asset, or None). Remote-only members are kept, local ones add or replace; deterministic bytes. Used by `tools/publish_store.py`.
- Publishing: `tools/publish_store.py --repo <clone of marine-research-data>` (or `RK_DATA_REPO`) zips each dirty cycle merged with its published asset, commits `incoming/{basin}/{cycle}.zip` on a branch `upload/<utc-timestamp>-<n>` (at most ~500 MB per branch), pushes, then clears the marks. The workflow in marine-research-data turns the zips into release assets and deletes the branch.

## rk/truth.py
- `analysis(basin, valid)`: re-export of `store.analysis`. The project's standard truth for WHERE.
- `obs(basin, valid, platforms=("buoy","drifter"), adjust10m=True) -> dict of 1-D arrays | None`: ship and buoy winds rebuilt as GDAS first guess + O-B departure from `gdas.YYYYMMDD/HH/atmos/wdqms/gdas.tHHz.marine.csv`, background from the previous cycle's f003-f009. Status 0 only, +-1 h, open water, blacklist (`rk/data/obs_blacklist_basins.txt`) and the 75 fixed coastal stations (`rk/data/fixed_stations.txt`) removed. Buoys raised from 4 m to 10 m (neutral Charnock); ships scaled by 0.88. Fields: lat, lon, speed_kt, speed_kt_raw, u, v, station_id, platform.
- `ascat(basin, valid, max_dt_min=90, real=True, intercal=True) -> dict | None`: RSS ASCAT v2.1 (Metop-B, C) cells within the window, rain dropped, open water only; `spd_kt` is real 10 m wind (converted from equivalent-neutral with the analysis air-sea temperature difference) when `real=True`, else equivalent-neutral; also `spd_enw_kt`, `spd_enw_raw_kt`, `dt_min`, `sat`. `intercal` (default on) meets Metop-B and C halfway: half the speed-dependent B-C gap (+0.30 kt at 25-35 kt to +1.25 at 55+, table `INTERCAL_*`, from winter 2025-26 same-cell pairs, `chance-calibration/ascat_noise/results.md`, 2026-10-16) is subtracted from B and added to C on the equivalent-neutral speed before the real-wind conversion, so `spd_enw_kt` and `spd_kt` carry it; `spd_enw_raw_kt` is unadjusted; `intercal=False` gives the raw RSS values. Raw daily cells cached under `truth/ascat/{YYYYMMDD}.npz`.
- `smap_day(day) -> dict | None`: all valid ocean cells of one UTC day of RSS SMAP v1.0 L3 daily winds (L-band radiometer, 0.25 deg, both nodes, 15-70N, all longitudes), or None when neither file is posted. Fields: `lat`, `lon` (0-360), `t_min` (int16 minute of the UTC day), `spd_enw_kt` (equivalent-neutral 10 m wind, kt, float32), `node` (uint8; 0 ascending ~18 h local, 1 descending ~06 h local). Source `data.remss.com/smap/wind/L3/v01.0/daily/FINAL/` first, then `.../NRT/` (RSS answers a missing file with an HTML page; the bytes must carry the netCDF/HDF5 signature). Cached under `truth/smap/{YYYYMMDD}.npz` with `final` (1 FINAL, 0 NRT); a cached NRT day is not refreshed. Not rain-masked and not intercalibrated with ASCAT.
- `enw_to_real(enw_kt, dT)`.
- `ascat_grid(basin, valid, **ascat_kwargs) -> (seen bool, spd_kt float32) | (None, None)`: `ascat()` snapped to the basin grid with floor(x + 0.5) (never np.rint: RSS centres sit 0.125 deg off the grid); `spd_kt` is the largest cell value per grid point, 0 where unseen.
- `hf_archive(basin, refresh=False) -> DataFrame(event_id, valid, lat, lon (0-360), hpa, category) | None`: the jkrek17/hf-low OPC hurricane-force low archive (`data/hf_lows/HF_Data_-_{Atl,Pac}.csv` on main, read over HTTPS), cached under `truth/hf_lows/`. Categories as archived: HF, S, DHF, DS.
- `hf_fixes(basin, valid, categories=("HF",), in_box=True) -> DataFrame | None`: archive fixes at one valid time.

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

- Warnings (a warned area = boolean grid at one level):
  - `warning_events(warned, truth_kt, seen, thr, mask=None, slack=4, min_cells=2, min_area_cells=3, judge_frac=0.3, judge_min=10) -> dict(events, hits, areas, judged, false, cells, bad_cells, warned_cells)`: events are 8-connected observed areas >= thr (>= min_cells seen cells); a hit has a warned cell within `slack` cells; a warned area is judged when the observations saw >= judge_min cells and >= judge_frac of it, and false when no observed >= thr lies within `slack` of it; `bad_cells` are seen warned cells with no observed >= thr within `slack`.
  - `warning_points(warned, basin, lat, lon, radius_km, mask=None, min_area_cells=3) -> dict` (same keys): point events (e.g. hurricane-force low centres) hit when a warned cell is within radius_km; a warned area is false when no point is within radius_km of it.

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

## rk/desk.py (the marine desk's issued wind grids: NDFD oceanic wind speed, 10 m)
- Source: public S3 bucket `noaa-ndfd-pds` (`wmo/wspd/YYYY/MM/DD/{product}_KWBN_{YYYYMMDDHHMM}`, one snapshot about every 3 h). Products: `YCYZ98` (days 1-3, ~27-32 MB, steps 2,5,8,... h from the issuance hour, Mercator 2517 x 1793, 10 km) and `YCYZ97` (days 4-7, ~15 MB; its grid and steps are read from the file, never assumed equal to YCYZ98). `PRODUCTS = ("YCYZ98", "YCYZ97")`, primary first. 10 m wind speed (`10si`), m/s, missing 9999 (land and off-grid). Raw files are never kept.
- Full updates go out after the 00Z and 12Z model cycles: the 10Z and 22Z snapshots. `HOURS = (10, 22)`.
- `issuances(day, product="YCYZ98") -> list[(datetime snapshot, key, size)]` for one UTC date, sorted.
- `pick(day, hour, product="YCYZ98") -> key | None`: the first snapshot of the product at or after `hour`:00 on that day and before hour+3.
- `box_index(lat, lon, basin) -> int array` flat index into the basin's 0.25 deg grid (row-major, `ny*nx`) of the box each NDFD cell centre falls in, -1 outside. Snapping is `floor(x/0.25 + 0.5)` (never `np.rint`). `area_mean(values, idx, n) -> float32 [n]`: mean over the cells of each box, NaN where no cell is valid (values at or above 9998, or non-finite, are missing).
- `load(issue_dt) -> {basin: {"ref": datetime, "valid": [datetimes], "speed": float16 [n_valid, ny, nx] (kt, NaN where no valid NDFD cell), "product": [str per valid], "refs": [datetime per valid]}} | None` for `issue_dt` at 10Z or 22Z. Merges YCYZ98 and YCYZ97 into one valid-time list (00, 06, 12, 18 UTC only) out to day 7; where both products have a valid time, YCYZ98 wins. `ref` is the YCYZ98 GRIB data date/time. None when YCYZ98 is not posted; when only YCYZ97 is missing the result holds days 1-3 and `fill` counts it under `partial`. Area mean: every NDFD cell whose centre falls in a 0.25 deg box contributes (values are 10 km cell means, not point winds).
- Cache: `{cache}/{basin}/{YYYYMMDDHH}.npz` (`speed` float16 kt, `valid` YYYYMMDDHH strings, `ref`, `refs`, `product`), written atomically; `cache = $RK_DESK` or `rk.paths.data("desk")`. The cell-to-box mapping is cached as `{cache}/map_{product}.npz`.
- `fill(start, end, hours=(10, 22), workers=3) -> {"ok", "missing", "failed", "partial", "cached"}` (counts; lists of tags for failed and partial under `failed_tags`, `partial_tags`). `partial` is a subset of `ok`. Skips cached issuances; one download gives both basins.

## rk/classes.py (the marine wind page's routine / attention classes)
- `RIDE, AGREE, FOCUS, HIGH = 0, 1, 2, 3`; `NAMES = ("ride", "agree", "focus", "high impact")`.
- `classes(speeds) -> uint8 [y, x]` for `speeds` [3, y, x] kt (GFS, IFS, AIFS). The page rule (`focus_grid` in awips-tools `marine_wind/pipeline/build.py` at commit 3eb2ff5), copied and kept identical for basin boxes (reflect mode at the edges). If the page rule changes, this changes with it.
