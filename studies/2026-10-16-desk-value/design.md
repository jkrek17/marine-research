# Desk added value: design card

*Draft for Jason's yes, 2026-10-16. Research agenda avenue 3.*

**Question** (Jason, 16 Oct): "How would you measure the desk's added value?" and "What portion of the forecast is routine and what portion needs attention?" Yardstick: "producing the forecast should not take longer than evaluating it."

**What would change if we know:** where the first guess can be taken as it stands (routine water, desk edits that do not move the grid toward the truth) and where desk time pays. That shapes which page layers become GFE first-guess tools and where the page asks the forecaster to look. No page or GFE change from this study.

**What the archive shows (checked 16 Oct).** The desk's final wind grids are the NDFD oceanic sector, `noaa-ndfd-pds/wmo/wspd/YYYY/MM/DD/YCYZ98_KWBN_*` (days 1-3, 3-hourly steps, 10 km Mercator, both basin boxes covered; `YCYZ97` holds days 4-7). A snapshot is posted every 3 h. On 15 Jan 2026 the OPC water changed in the snapshots after about 04, 10, 13-16 and 22 UTC and not in between, so each shift's issued grid is the snapshot after its send time. The 04 and 22 UTC updates (after the new 00/12Z GFS) changed 26-32% of cells by more than 1 kt; the 10 and 16 UTC updates 4-14%.

**Grids compared at each issuance** (same valid time):
1. **Desk**: the shift's issued grid.
2. **Previous grid**: the earlier shift's grid, the one the forecaster started from.
3. **Auto-update**: the previous grid plus the change in the blend between the runs each shift had. This is what an automatic update would hand the forecaster; it separates the forecaster's judgement from the newer model runs.
4. **GFS** and **ECMWF IFS** alone (Jason: compare the desk to the raw models it reads).
5. **Blend** (3-model mean + member spread lean, the page recipe) from the runs available at issue time, and **Core Lifted** where the page's core model can be replayed from stored fields (Atlantic winter 2025-26 is its training winter, so Atlantic Core Lifted scores are flagged in-sample).

**Truth:** ASCAT (`rk.truth.ascat`, real 10 m, Metop B/C met halfway) for how strong; analyses (`rk.truth.analysis`) for where; buoys as a check. Desk grids averaged onto the 0.25 deg grid (3-4 NDFD cells per box) so no grid gets a resolution advantage against ASCAT.

**Scores**, at 24, 48 and 72 h, both basins, Atlantic at 00/12Z and Pacific at 00/06/18Z valid (ASCAT coverage): detection, false alarm and warned area at 34, 48 and 64 kt; storm-force tile peaks; error by wind band (forecast-conditioned).

**Routine vs attention:** each cell gets the page's class (ride, agree, focus, high impact) from GFS, ECMWF and AIFS at issue time, with the page's own rule. Report the share of open water, of forecast hours, and of desk edits (cells moved more than 2 kt) in each class, and the scores above within each class.

**Decisions, set now:**
- The desk **adds value in a class** when its grid beats the auto-update on ASCAT error at 25+ kt or on storm-tile catch, with no worse false alarms, and the 95% interval from resampling whole weeks excludes zero.
- A class is **routine** when desk edits there do not beat the auto-update (interval includes zero or worse). Those are the cells a first-guess tool can fill.
- No fitting, so all weeks are scored; held-out weeks (`rk.cases.held_out`) are reported separately as a check.
- Aggregate only, never per forecaster.

**Cases:** winter 2025-26 (1 Nov - 31 Mar), four shifts a day, both basin boxes (`rk.basins`).

**Data:** NDFD `YCYZ98` wind speed, four snapshots a day, about 28 MB each: about 17 GB streamed for the winter, decoded once and stored on the 0.25 deg basin grids (about 0.3 GB) under `research-data/desk/`; raw files not kept. Model fields: GFS and GEFS are in the store; the ECMWF half (IFS, AIFS, ENS) is still filling, so GFS scores and the desk-edit measures run first and the ECMWF and blend columns follow when it lands. No new ECMWF pull. ASCAT and analyses for the winter are cached.

**Reused / new:** reuses `rk.cases`, `rk.store`, `rk.truth` (ASCAT, analyses, buoys), `rk.score` (contingency, tile peaks, error), `rk.compare.paired`, `rk.style`. New in `rk/`, each with a test: `rk.desk` (NDFD oceanic grids: list a day's issuances, decode, average onto the basin grids, cache) so the warning and HSF studies can use the desk grids too; `rk.classes` (the page's ride/agree/focus/high-impact rule, tested to match `focus_grid` in awips-tools `marine_wind/pipeline/build.py` cell for cell).

**Methods, simplest first:**
1. Share of water, hours and desk edits by class.
2. Desk vs previous grid vs auto-update vs GFS, by class and lead.
3. Add ECMWF, blend and Core Lifted columns when the ECMWF half lands.
4. Sort the desk's edits into kinds (core raised, area trimmed or grown, gradient shifted, timing moved) and score each kind.
5. Situations (deepening low, mature low, cold outbreak, Greenland barrier flow): the agenda's table, after 1-4.

**Known traps** (`LESSONS.md`): condition error on the forecast, not the truth; the sample is weeks; ASCAT sees storm force about 6 times as often as analyses, so storm scores are ASCAT only; snap RSS cells with floor(x + 0.5); Pacific longitudes 160-245.

**Out of scope:** seas (no wave truth; Jason: "just use the wave forecast"); per-forecaster results; any page or GFE change.
