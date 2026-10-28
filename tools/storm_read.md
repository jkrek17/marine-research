# tools/storm_read.py: storm read

One named low, followed through every model run and ensemble member, written up as a page. Built from the 1 Nov 2026 central Atlantic bomb read.

    python3 tools/storm_read.py --valid 2026110112 --parent 2026103112,36,-50 --basin natl --name "Central Atlantic bomb"

| Option | Meaning |
|---|---|
| `--valid YYYYMMDDHH` | the time the read is about (the key time) |
| `--parent YYYYMMDDHH,lat,lon` | a parent low: time and position (lon 0-360 or negative west). Must be on the 6 h grid within valid-48 h .. valid+24 h |
| `--basin natl\|npac` | which `rk.basins` box to pull and track in (it starts at 30N, and `rk.bomb` ignores lows within 6 cells of the edge) |
| `--cycle YYYYMMDDHH` | newest run (default: newest 00/12 UTC cycle with ECMWF ENS posted for valid+24 h) |
| `--runs N` | deterministic runs, 12 h apart, ending at `--cycle` (default 5) |
| `--no-ens` | deterministic models only (a few hundred MB for 1 run) |
| `--name`, `--out DIR` | page title; output folder (default `RK_DATA/extra/storm-read/<valid>-<basin>`) |
| `--page-run REF` | git ref of the marine wind page data in the sibling `awips-tools` clone (default `origin/marine-wind-live`, `none` skips) |

## Method

- Lows: `rk.bomb.find_lows` on 6-hourly MSLP from valid-48 h to valid+24 h (13 steps).
- Track FORWARD from the parent (`rk.storm_read.track`): nearest low within 700 km of the given position at the parent time, then both directions, nearest low within 800 km of the last point each 6 h. Per point: lat, lon, hPa, highest 10 m wind (kt) within 600 km.
- Bergeron number: largest over every 24 h window along the track, and the 24 h ending at the key time (1 = bomb).
- Deterministic: GFS, ECMWF IFS, AIFS, AI-GFS (`aigfs`, `#0f9d9a`), the last `--runs` cycles. Ensembles: GEFS, ECMWF ENS, AIFS ENS from the newest run, hue = parent model, wind only from valid-24 h to valid+12 h (about 6 steps; MSLP-only elsewhere, a third of the bytes).
- A member that loses the low counts as no bomb and no wind in every share. Pooled shares are member-weighted over all ensembles.

## What it reuses

`rk.fetch.det` and `rk.fetch.members` (both basins cut from one decode, build-window wait, no new downloader), `rk.bomb` (low finder, dec), `rk.basins`, `rk.paths`, `rk.score.km`, `rk.style`. New and shared: `rk/storm_read.py` (tracking, Bergeron along a track, member summaries, generated sentences; `rk/CONTRACT.md`).

## Output (in `--out`)

`summary.json` (meta, per-model and per-ensemble numbers, pooled shares, generated sentences), `tracks.json` (every point of every run and member), `pressure|bomb|wind|runs|map` (`.png` and `.svg`), `page.html` (figures inlined as base64, a fragment with no document wrapper, ready to publish as an artifact). `page.html` is filled from `tools/storm_read_page.html`: numbers and sentences are generated; the block `id="forecaster-read"` is a marked spot for the thread to edit. Rerun after editing the template; re-edit the block afterwards (it is overwritten).

The map needs the marine wind page's run to cover the valid time (its manifest steps) and a clone of `awips-tools` next to this repository (read with `git show`, decoded as the page does); otherwise the page says so and skips it.

## Cache and size

Fields are cached under `rk.paths.cache("storm-read", basin)` (MSLP as int16 hPa x 10, wind as float16 kt), so a rerun, or a second read of the same storm, pulls only what is missing. Typical pull: 5 runs x 4 models x 13 steps, plus about 133 members x 11 steps of MSLP and about 6 steps of wind, about 3 GB and about 25 min. Well under the 50 GB go-ahead line. Needs `PYTHONPATH` to include the `nwp` package (awips-tools/nwp) as for `rk.fetch`.

## Not in it

No verification (nothing to verify against yet at day 4-5); the ERA5 and ASCAT checks are separate. The wind caveat (models run 2-6 kt below ASCAT peaks) and the bomb-watch evidence line are fixed text in `rk.storm_read.CAVEATS`.
