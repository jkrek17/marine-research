# Storm-force truth: design card

**Question** (Jason's "go", 2026-10-16, on avenue 2 of the research agenda): when ASCAT says storm or hurricane force, how strong is the wind really? Every storm-force number in the project (the core lift's 49%, storm chances, warning detection) rests on ASCAT, and ASCAT has never been checked at 48 kt or more: 0 buoy pairs at 48+, 11 at 34-48 (`/mnt/project-files/wind-focus/ascat/buoy_check.md`).

**What is already settled** (`/mnt/project-files/chance-calibration/ascat_noise/results.md`): ASCAT's random error is small (about 2 kt per cell at storm force) and inflates the 48 kt frequency by only 3-6%. Metop-B reads about 1 kt above Metop-C at storm force; `rk.truth.ascat` already meets them halfway. What is **not** known is a systematic offset at the top end. That is what matters: 1 kt of offset moves the 48 kt frequency by about 17%.

**What would change if ASCAT is off:** an optional high-wind adjustment in `rk.truth.ascat`, and re-scored headlines (the core lift's storm catch, chance calibration, warning detection). No page change from this study.

**Truth:** no perfect truth exists at storm force, so this compares two independent instruments and the few buoys and ships.
- **SMAP** (RSS v1.0 FINAL, L-band radiometer, daily 0.25 deg, equivalent-neutral 10 m wind, the same quantity as ASCAT). L-band keeps sensitivity in storms and is little affected by rain. Its footprint is about 40 km, coarser than ASCAT's 25 km, so ASCAT is averaged to SMAP's footprint before comparing.
- **Buoys and ships** from the GDAS marine file (`rk.truth.obs`), every season, both basins.

**Feasibility, checked on 15 Jan 2026:** SMAP passes about 3.5 h (local time) from the Metop passes, so same-cell pairs within 90 min are rare (about 900 cells a day, all north of 57N). Within 3 h there are about 23,000 cells a day, about 100 of them at ASCAT 48+ kt. Storms move in 3 h, so the main comparison is per storm, not per cell.

**Decision rules, set now:**
- SMAP minus ASCAT at storm-force peaks within +/-2 kt (95% interval from whole-week resampling inside +/-2): ASCAT stands as storm-force truth, unchanged.
- An offset larger than 2 kt at 48-64 kt, the same sign in both basins and on held-out weeks: fit a speed-dependent adjustment on tune weeks, add it to `rk.truth.ascat` as an option (default off), and re-score the core lift with it.
- 64 kt and up: report counts and the offset if there are at least 30 storm-passes; otherwise say it cannot be settled.

**Cases:** winter 2025-26 (1 Nov - 31 Mar), 30-67N, both basin boxes (`rk.basins`). Buoys and ships: Mar 2025 - Sep 2026 for more storm-force reports. Held-out weeks (`rk.cases.held_out`) used only if an adjustment is fitted.

**Data:** SMAP FINAL daily files, about 0.9 MB each, about 0.15 GB for the winter (new, from data.remss.com, which already serves ASCAT). ASCAT days: `truth/ascat` holds 77 days; the rest download through `rk.truth.ascat_day`. GDAS marine csv through `rk.truth.obs`. No ECMWF or model downloads. Under 5 GB in total.

**Reused / new:** reuses `rk.truth.ascat_day` / `ascat` (rain flags, Metop intercalibration), `rk.truth.obs` (buoy height and ship scaling, fixed stations removed), `rk.cases`, `rk.compare.paired`, `rk.style`. New: `rk.truth.smap_day()` with a test, so later studies have a second instrument.

**Methods, simplest first:**
1. **Storm peaks per pass pair.** For each ASCAT pass with 48+ kt (after averaging to SMAP's footprint), find the SMAP pass over the same area within 3 h. Compare each instrument's peak and 95th percentile within 300 km of the ASCAT peak. Report SMAP minus ASCAT by the mean of the two peaks (not by either one, to avoid regression to the mean), with whole-week resampling.
2. **Cell pairs within 90 min** (high latitudes only) as a check on method 1 without storm motion.
3. **Buoys and ships** within 30 min and 25 km of an ASCAT cell, binned by the mean of the pair: 34-48 and 48+.
4. **Rain:** ASCAT drops rain-flagged cells; SMAP keeps them. Report how many SMAP storm-force cells fall where ASCAT was rain-flagged, since those are invisible to every ASCAT score.
5. **What it means:** translate any offset into the 48 and 64 kt frequency and the core lift's storm catch.

**Known traps** (`LESSONS.md`): condition on the mean of the pair, not on one instrument; sample is weeks, not cells; RSS cell centres need floor(x + 0.5) snapping; Metop-B/C offset; SMAP land, ice and radio-interference masks near Greenland and coasts.

**Out of scope:** AMSR2 and GMI (rain-affected radiometers); any change to the page, chances or HF rule.
