# Pattern drill: design card

*A training game, not a scored study. Agreed with Jason in the thread "Build a cyclogenesis pattern drill for forecasters", 2026-11-05 15:54-16:02Z.*

**Question** (Jason's words): "is it possible to make a training tool using past events ... basin maps of 500 mb heights, 250 mb isotachs, eddy growth rate ... then we see the results". Then: "pattern recognition ... we have thousands of cases we could go through quickly rather than trying to just build experience through normal daily work"; "only use ones where there is ascat, and we can zoom on an area"; "for +24, maybe not where, but what category. gale, storm, HF, or none ... growth vs decay"; "maybe they are different games. one is what is happening right now, one is forecast"; "gamify ... track session stats, and have a lot of cases so they cant learn them"; "personal stats per session. lets start with 200 cases to test and iterate".

**What it is:** a web page with two games on one deck of cases.
- *Right now*: maps at the time of an ASCAT pass, pass hidden. Call the peak wind around the circled low: none (< 34 kt), gale (34-47), storm (48-63), HF (64+). Reveal the pass.
- *Forecast*: maps at the start time plus the start-time ASCAT category. Call the category 24 h later. Reveal the +24 h pass and pressure.
- Session stats only (no accounts, nothing stored past the session): points, streak, called-vs-observed 4x4 table, time per case, timed blitz, weak-spot mode. Points: miss costs more than a false alarm, an HF miss the most. Dates hidden.

**Truth (version 2, Jason 2026-11-05):** the strongest RSS ASCAT wind anywhere in the map box (3rd highest 0.25 deg cell, `scene.py`), and the circled low is the deepest low in the box at both times; a case counts only when ASCAT saw the circled low's own circulation (its pressure basin, `rk.score.pressure_basins`, up to 1000 km; `find_cases.py` version 2). Version 1, below, attributed winds to one low within 500 km and cut off big lows' cold-sector storm winds and mis-scored scenes with several lows.

**Truth (version 1):** RSS ASCAT (`rk.truth.ascat`, real 10 m wind, Metop B/C intercalibrated) within 500 km of the low centre, ±90 min of the map time. Category = the 3rd highest ASCAT cell (so one noisy or rain cell does not set it). A snapshot counts only when ASCAT saw at least half of the open water within 500 km.

**Maps** (GFS analysis f000, 0.25 deg, cut to a 25 x 40 deg box and coarsened to 0.5 deg): MSLP with 1000-500 thickness; 500 hPa heights with absolute vorticity; 250 hPa isotachs with heights; Eady growth rate 850-500 hPa (0.31 f |dV/dz| / N, per day); 850 hPa temperature advection with 850 heights and temperature; sea minus 2 m air temperature. Model 10 m wind is not shown.

**Cases (first deck):** winter 2025-26 (Nov-Mar), both basins, 00/06/12/18 UTC, GFS lows deeper than 1012 hPa. A case = one low with ASCAT seen at both T and T+24 h (tracked in 6 h steps). 200 cases, balanced across the four +24 h categories as far as HF allows, at most one case per low per day. Later decks: earlier winters (GFS analyses on AWS go back to 2021; ERA5 for older years).

**Data:** GFS f000 MSLP for every 6 h of the winter (one record per time, ~0.3 GB) to find lows; ASCAT days from the truth store; full map fields only for the chosen case times (~400 times x ~16 records, ~5 GB streamed). Well under 50 GB. Nothing new in the field store.

**Reused / new:**
- Reused: `nwp` through `rk.fetch` (GFS), `rk.truth.ascat`, `rk.score.find_lows`, `rk.storm_read.follow`, `rk.basins`, page wind colours.
- New in `rk/`: `rk.fetch.gfs_analysis(valid, keys)` (whole-globe GFS f000 records by name) and `rk/diag.py` (Eady growth rate, temperature advection, thickness, smoothing on a lat-lon grid), with tests.
- New here: `find_cases.py`, `pick.py`, `build_deck.py` (resumable, per-time caches under `rk.paths.data("extra", "pattern-drill")`) and the page `page/`.

## Deck format (contract between `build_deck.py` and the page)

`deck/manifest.json`:
```
{"version": 1, "res": 0.5, "ny": 51, "nx": 81,
 "fields": [{"key": "msl", "name": "...", "units": "hPa", "offset": 940, "scale": 0.5}, ...],
 "cases": [{"id": "c0001", "basin": "natl",
            "lat0": 62.0, "lon0": 300.0,          # north-west cell centre of the box, lon 0-360
            "t0": {"lat": .., "lon": .., "hpa": .., "cat": 2, "peak": 51.0, "cover": 0.7},
            "t24": {"lat": .., "lon": .., "hpa": .., "cat": 1, "peak": 42.0, "cover": 0.6}}, ...]}
```
Version 2 adds `"truth": "scene"` and per snapshot `plat`, `plon` (the ASCAT cell that set the answer); `t0`/`t24` `lat`, `lon` are the circled low snapped to the drawn MSLP minimum within 200 km, and the box is centred on the low at T.
`cat`: 0 none, 1 gale, 2 storm, 3 HF. Valid times are not in the manifest (dates hidden); a separate `key.csv` beside it, not published, maps ids to times.

`deck/<id>.bin`: two snapshots (t0 then t24), each = for every field in `fields` order a `ny x nx` uint8 array (row 0 = north, value = offset + scale x byte, 255 = missing), then ASCAT speed (kt, 1 kt steps, 255 = not seen; highest cell in each 0.5 deg box), ASCAT direction (meteorological degrees / 2, 255 = not seen), land (1 land or ice, 0 water).

## Beat the model (Jason 2026-11-06)

Replaces grow / hold / decay as the forecast game (Benchmark and Pairs still use the change call). The trainee sees each model's full +24 h forecast maps (`fc_deck.py`: GFS for every case, ECMWF open data for 00/12Z runs from March 2025), switchable with the analysis now, plus the model's own 10 m wind and its strongest wind on the map; calls the category ASCAT will show at +24 h; each model's own category is scored the same way. `deck/<id>_fc_<model>.bin` is one snapshot in the .bin layout with the model's 10 m wind speed and direction in the ASCAT layers; `case.fc[model] = {peak, cat}` in the manifest.

Models on the 174-case deck (3rd-highest 10 m wind on the map vs ASCAT's): GFS exact 67% (persistence 45%), too low 20%, too high 13%; storm cases right 60% (38% low), HF right 12% (88% low). ECMWF (57 cases) exact 58%, too low 33%; median 3 kt under ASCAT.

## Storm or HF? and three more winters (Jason 2026-11-06)

Pairs is retired (it trained the growth call, the lowest-ceiling skill). Storm or HF? shows only maps with storm force or stronger somewhere: half are analysis snapshots at an ASCAT pass, half are +24 h forecast cases (GFS/ECMWF maps, ASCAT at +24 h storm or stronger). Call 48-63 or 64+; category points as elsewhere; stats show HF caught and HF over-called, you vs GFS and vs 925 x stability.

Deck: winters 2021-22, 2022-23, 2023-24 added (find_cases.py, scene.py, pick.py --scene --keep ... --strong). Jason chose about half the new candidates with satellite (the full set with satellite measured ~95 GB, ~265 MB a case; GFS f000 35 MB a time, IR + air-mass ~98 MB a time): every new HF low first (61), then a random fill, 160 new cases, deck 334. Cases marked pool=hf (44) are storm-force extras shown only in Storm or HF?, so the other games keep their mix. Storm or HF? pool: 366 analysis snapshots (95 HF, was 28), 180 forecast cases (51 HF, was 16). No ECMWF before March 2025. The ingredient statistics stay on the two winters 2024-26 (ingredients.csv); new cases have no ingredient debrief.

### 925 x stability (rule925.py)

Jason: "really can just use the Air-sea and 925 winds to pinpoint and determine winds". The shortcut as the page computes it: strongest 925 mb wind over water on the map (3rd of the top 20 cells) x a factor from the largest sea minus 2 m air among those 20 cells. Factors = median ASCAT answer / 925 by class, fitted on 2024-26 analysis snapshots: 0.68 (< 2 C), 0.76 (2-5 C), 0.82 (5 C+); refit on all five winters 0.70 / 0.79 / 0.83 (in the manifest as rule925). The per-low factors in the earlier hint (0.87-1.13, 925 near the centre) run ~10 kt high map-wide.

| Test (factors from 2024-26) | n | Exact | Storm+ exact | HF caught | HF over-called (of storm) | GFS 10 m exact | GFS storm+ exact | GFS HF caught |
|---|---|---|---|---|---|---|---|---|
| Analysis, 2024-26 (in sample) | 348 | 70% | 64% | 16/28 | 6/112 | | | |
| Analysis, 2021-24 (held out) | 320 | 68% | 62% | 32/67 | 4/159 | | | |
| GFS +24 h maps, 2024-26 | 174 | 72% | 68% | 6/16 | 2/50 | 67% | 48% | 2/16 |
| GFS +24 h maps, 2021-24 (held out) | 160 | 65% | 61% | 19/35 | 7/79 | 54% | 44% | 7/35 |

It holds out of sample and beats the GFS 10 m wind at +24 h, most at the top end; it still misses about half the HF. It is shown in every result and scored like a model in the stats.

### Benchmark and reading-the-wind page (Jason 2026-11-06)

"The benchmark test does growth/decay. that needs to change": Benchmark v2 = 20 fixed Beat the model cases (make_bench.py, 5 per +24 h category, GFS forecast required, no pool=hf extras), scored like the game; summary shows you vs GFS, ECMWF and 925 x stability, history per device (new storage key; v1 change-call runs are not compared). "Redo the main page removing growth/decay. the ingredients page needs to tell you about wind speed detection": the Ingredients page is now Reading the wind (manifest.speed from rule925.py): factor table with the 925 wind each category needs (sea-air < 2 C: 49/69/91 kt for gale/storm/HF; 2-5 C: 43/61/81; 5 C+: 41/58/77), held-out test, model 10 m bias by ASCAT category (GFS +3/+1/-5/-10 kt for none/gale/storm/HF; ECMWF 0/-8/-10 at gale/storm/HF, few cases), and the +24 h shoot-out on 334 cases: GFS 10 m 61% right, storm/HF 46%, HF 9/51; GFS +8 kt where GFS 44+ 71%, 79%, 37/51 (over-calls 22%); 925 x stability 70%, 71%, 31/51 (over 17%). The growth-ingredient debrief is removed from the result card.
