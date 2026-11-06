# Front drill (frontal analysis trainer): design card

*A training game, not a scored study. Sibling of the pattern drill (`studies/2026-11-05-pattern-drill/`). Agreed with Jason in the thread "Build a frontal analysis trainer from OPC archives", 2026-11-06 11:33-11:53Z.*

**Question** (Jason's words): "another good training tool would be frontal analysis. could we use archived OPC analysis to build a database?"; "we need the full unified surface analysis at synoptic hours ... We want to focus on one storm system so we dont need a ton of time. it should be rapid fire because we dont have forever to make decisions on the desk"; "Drawing should tap points. we need several front type selections. Scoring on the distance should be generous. scoring should be stricter on front type"; "for data, we should get MSLP, 1000-850 equivilent potential temp, IR, 250 mb wind speed".

**What it is:** a web page. Each case is one storm system at one synoptic hour, maps shown, fronts hidden. The trainee taps points to lay each front, picks its type, then submits. The reveal overlays the Unified Surface Analysis fronts and lows and scores the drawing. Timed, about 60-90 s a case, many cases, session stats only (no accounts), same look as the pattern drill (cream, navy, oxblood).

**Truth:** the Unified Surface Analysis (OPC, WPC, NHC) as coded by WPC in the CODSUS bulletin (`ASUS02 KWBC`, 0.1 deg points, archived by IEM). Synoptic hours only (00, 06, 12, 18 UTC): the 03/09/15/21 bulletins are not the full ocean analysis. Types carried: cold, warm, occluded, stationary, trough; highs and lows with central pressure. Checked against OPC's two Atlantic charts for 2026-11-01 12Z: fronts and lows line up (`/mnt/project-files/frontal-trainer/opc-vs-coded-fronts-2026110112Z.png`). Coverage is about 20-30W to 170-180W, 16-83N: the whole Atlantic HSF area, not the far east Atlantic or the west Pacific beyond ~170W. 0.1 deg bulletins exist from ~2011, whole-degree back to 2005.

**Maps** (GFS analysis f000, 0.25 deg, box coarsened to 0.5 deg like the drill):
1. MSLP with 1000-500 thickness (default view).
2. 1000-850 mean equivalent potential temperature (`rk.diag.theta_e` at 1000, 925, 850).
3. IR (GridSat-B1 via `rk.satellite`, as the drill).
4. 250 hPa isotachs.
5. 10 m wind barbs (GFS f000), and ASCAT barbs when a pass is within 90 min (optional overlay).
Jason's four plus wind barbs and thickness, proposed 11:53Z; dropped if he says so.

**Drawing:** tap points along a front, choose a type from cold / warm / occluded / stationary / trough, finish, start the next; undo and delete; place the low (L) by tap. Works on a phone.

**Scoring** (generous on position, strict on type):
- Each analysed front in the box is matched to the trainee front nearest it (mean distance from the analysed front's points to the drawn line).
- Position: full credit within 150 nm, sliding to none at 300 nm.
- Type: full credit only for the right type, none otherwise; type is worth twice position.
- A front the analysis drew and the trainee did not costs the most. Extra trainee fronts cost a little (troughs are drawn inconsistently, so an extra trough costs nothing).
- Low: full credit within 60 nm. Pressure call optional later.
Constants live in one place in the page so they can be tuned after forecasters play it.

**Cases:** a case = a CODSUS low over open water inside the OPC area with at least one front attached (a front end within ~300 km of the low), at 00/06/12/18Z, winters (Nov-Mar) 2024-25 and 2025-26 first, both basins; at most one case per low per day; balanced so occluded, warm and stationary fronts are not swamped by cold fronts. First deck ~200 cases, like the drill. Box centred on the low.

**Data:** GFS f000 records per case time (MSLP, 1000/500 hgt, T and RH at 1000/925/850, 250 u/v, 10 m u/v) through `rk.fetch.gfs_global`, ~12 MB per time, ~200-400 times, a few GB streamed, resumable per-time caches under `rk.paths.data("extra", "front-drill")`. CODSUS text: one IEM request per day, cached. Well under 50 GB.

**Reused / new:**
- Reused: `rk.fetch.gfs_global`, `rk.diag` (theta_e, smooth, coarsen), `rk.satellite`, `rk.truth.ascat`, the drill's box, quantise, satellite and export code (`build_deck.py`, `page/export_site.py`), page skin.
- New in `rk/`: `rk/fronts.py` (fetch + parse CODSUS into fronts and pressure centres, cached; with a test), so any later study (front-relative ASCAT, frontal wind maxima) can use the analysed fronts.
- New here: `find_cases.py`, `build_deck.py`, `page/`.

**Publish:** its own folder on the drill site (jkrek17/pattern-drill, `/fronts/`) once Jason has played a private preview.

**Out of scope for v1:** whole-basin analysis mode, highs, pressure calls, squall lines and dry lines, years before 2021 (no GFS analyses on AWS; ERA5 would be needed).
