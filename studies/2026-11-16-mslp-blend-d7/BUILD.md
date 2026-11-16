# Build spec (lead's instructions to the coding team)

Read design.md first; it is locked. This file fixes the code interfaces so the pieces can be built in parallel.

## Inputs
- `extract.py` (being written now) writes one file per basin-cycle: `rk.paths.cache("extra","mslp-blend-d7",basin,"YYYYMMDDHH.npz")`, float32 hPa on the basin grid (natl 149x300; lat 67..30 by -0.25, lon 285..359.75 by 0.25; npac per rk.basins). Keys, lead L in 24..168 step 24 (zero-padded 3 digits):
  `gfs_fLLL ifs_fLLL aifs_fLLL aigfs_fLLL` (det, missing keys simply absent),
  `gefs_mean_fLLL ens_mean_fLLL aifs-ens_mean_fLLL` and `*_std_fLLL` (to f120 only),
  `an_gfs_vLLL an_ifs_vLLL mask_vLLL` (truth at cycle+L; mask uint8 open water).
- Day 5-7 members (12Z only): `rk.store.load(basin, "YYYYMMDD12", "mslpd57_noaa"|"mslpd57_ec")`, int16 hPa*10-10000; members `mem_{gefs|ens|aifsens}_{basin}_{L}` [n, 75, 150] at 0.5 deg; each member's own lows `low_{ens}_{basin}_{L}` [k,4]; det `det_{gfs|ifs|aifs}_{basin}_{L}` at 0.25. See studies/2026-10-16-pressure-d5-7/lib.py (dec, to_quarter) and method.py (consensus/vote) and reuse them by import, not copy.
- Ensemble means at f144/f168 come from those members (mean over members, each ensemble one block), 12Z only.

## candidates.py (Agent A)
`build(basin, cycle, lead, z, members=None, params=None) -> dict[name -> 2-D float32 field]`
- `z`: the extract npz as a dict; `members`: dict from the mslpd57 files or None; `params`: tuned settings (dict), default = untuned values.
- Names (skip a candidate when an input is missing; never impute):
  singles `gfs ifs aifs aigfs`; means `m_gi` (GFS+IFS), `m_gia` (+AI-GFS), `m_gif` (+AIFS); ens means `gefs ens aifsens grand` (grand = equal blocks);
  weighted blend `wb` and `wb_gfe` (weights from params["w"][basin][lead] over the available inputs, renormalised over present inputs);
  aligned blend `al` (inputs: gfs, ifs, aifs, aigfs and the three ensemble means, each one run; equal weight; ensemble means count as runs for position but their depth is not used for the depth target) and `al_gfe` (gfs, ifs, aigfs, gefs);
  aligned + depth fix `ald`, `ald_gfe`; rival `bowl` / `bowl_gfe` (plain equal blend of the same inputs + the same depth bowl, no warp); rival `off` (plain blend + constant offset params["off"][lead] at gated lows);
  outlier drop `od` / `od_gfe` with X = params["X"][lead] (km); also expose `od_dropped(...)` returning which model was dropped per storm group, its distance to consensus, and its low position, for the risk table.
- Aligned blend, depth fix and outlier drop exactly as design.md items 5, 6, 8. Displacement cap = params["cap"][lead] (grid {300,450,600}). Use scipy.ndimage.map_coordinates(order=3, mode="nearest"); NO np.roll. Distances on a local tangent plane in km. Check det(I - grad D) > 0.3 everywhere, else scale D down until it holds.
- `grid_values()` returns the tuning grids so the runner can build every setting in one pass.
- Unit tests in tests/ style of the repo (tests/test_*.py, plain python asserts): a synthetic field with one Gaussian low displaced in 3 runs -> `al` puts the low at the mean position with depth close to the runs' median; a run with no low is not moved; field unchanged far from lows; box edges untouched; two camps > 800 km apart are not merged.

## score.py + run.py + analyze.py (Agent B)
- `score.case(fc, an, mask, basin) -> (field_row: dict, lows: DataFrame, false_n, n_fc)`: field_row has rmse (cos-lat weighted, open water), bias, rmse_ls (both smoothed with a Gaussian of 300 km before differencing), sharp (mean |grad p| forecast / analysis within 1000 km of analysed lows < 1000 hPa). Lows via rk.score.low_case (house form) + Hungarian one-to-one sensitivity (scipy linear_sum_assignment, cost = km, 1000 km cap) + along/cross-track split (track direction from the analysed low 24 h earlier, nearest within 1000 km; NaN if none). Put any general helper (cos-lat weighted field MSE) into rk/score.py with a test.
- `run.py`: loop basin-cycles (resumable, one reader at a time), call candidates.build for every setting in grid_values(), score against an_gfs and an_ifs and their mean, append rows to `rk.paths.cache("extra","mslp-blend-d7","scores")` as parquet per basin-month (field rows, lows rows, false-low rows), columns: basin, cycle, lead, valid, truth, cand, setting, week, split (rk.cases.split on cycle), month. Also save, per case, the deterministic and vote low lists needed for the outlier risk table.
- `analyze.py`: (1) tuning: per lead pick cap, X, offset, weights by leave-one-month-out on split=="tune" with a 7-day purge (cycles within 7 days of a held-out fold's edge excluded from its training), on the headline truth (mean analysis), objective = mean position error subject to the RMSE and false-low guards in design.md; write params.json; (2) score every candidate per lead: untuned on all weeks, tuned on their LOMO out-of-fold rows, held-out weeks as a sign check; paired differences vs IFS with rk.compare.paired (week blocks, 2000 draws), BH q=0.10 across candidates x leads; the design.md win rule applied mechanically; both truths; both basins; (3) tables to studies/.../results/*.csv (small), including the outlier risk table and strong-low depth table.
- Smoke-test on 10 basin-cycles before the full run.

## Rules
Repo CLAUDE.md applies: no data in git, no git add -A, find repo from __file__, no /home or /tmp paths. Do not commit; the lead commits. Report the numbers you got and anything you could not do as specified.
