# Chance calibration, GEFS first look: design card

*Summary of `chance-calibration/design.md` (Jason's thread, 2026-10-16). First look only; nothing on the live page changes.*

**Question:** "Are the page's gale, storm and hurricane-force chances honest, against the analyses and against ASCAT, and what remap would make them so?"

**What would change if the answer is yes:** the page's P34 (never calibrated) and P48/P64 (calibrated to the analyses only) curves, and the raw-share meaning of the 30% gale and storm hazard lines. Goes to the page thread; Jason decides.

**Truth:** ASCAT 3x3 box mean (main: real 10 m wind, Metop-B/C offset met halfway by `rk.truth.ascat`, cells snapped with floor(x+0.5), box kept where >= 6 of 9 cells are valid, event = box mean >= threshold); ASCAT single cells (comparison, single cells inflate crossings in the steep tail); analysis `mean_speed` with its open-water mask (what the page was fitted to).

**Baseline to beat:** the raw GEFS member fraction, and climatology of the held-out weeks for Brier skill.

**Win means:** on held-out weeks the remapped chance has higher Brier skill and lower reliability error than the raw chance for a threshold x lead group x basin, with enough events (about 30 cycles with any event) to say so. Otherwise it is stated as a thin sample.

**Cases:** both basins at the basin hour (natl 12 UTC, npac 00 UTC), winter 2025-26, +24..+120, only cycles already in the store with GEFS. Split by `rk.cases.held_out` on the cycle date; fit on tune weeks, score held-out once.

**Data:** the store only (GEFS `p34/p48/p64`, analyses). ASCAT daily bytemaps and the GFS air-sea analysis come through `rk.truth` (small downloads, cached in the store). No model downloads. `extra/warning-experiment/ascat_day` was checked: it holds a different layout (no equivalent-neutral speed, no rain bytes), so `rk.truth`'s own cache is used.

**Reused / new:** reused `rk.cases`, `rk.store`, `rk.truth.ascat/analysis`, `rk.style`. New in `rk/`: `rk.calibrate` (reliability, fit, apply, scores, threshold translation, page JSON) and `rk.truth.ascat_grid/ascat_to_grid/box_mean` (ASCAT truth on the model grid), both with tests, so the page and GFE can call them.

**Methods tried, simplest first:**
1. Raw GEFS member fraction.
2. Page-style remap (binned, shrunk toward raw by min(1, n/2000), non-decreasing), fine bins under 10%, fitted per threshold x lead group x basin x truth.

**Known traps:** GEFS only (the page pools GEFS + ECMWF ENS + AIFS ENS, so none of these curves is for the page); the sample is weeks, not cells (neighbouring cells and leads are not independent; the cell counts overstate the evidence); ASCAT sees the swath only; the Pacific hour differs; floor(x+0.5) snapping; 64 kt will be too thin.

**Out of scope:** ECMWF ENS and AIFS ENS, core likelihood, the hazard-line change itself, buoys.
