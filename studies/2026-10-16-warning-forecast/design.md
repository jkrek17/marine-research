# Warning forecast experiment: design card

*Decided in the "Warning forecast experiment" thread on 2026-10-16 before the kit existed. Jason's answers are noted; the study moved onto `rk/` the same day.*

**Question** (Jason, 2026-10-16 04:17Z): "build the perfect forecast from the models at your disposal. We are scoring on warnings and you need to hit at least 80% on all warning categories."

**What would change if the answer is yes:** the hazard lines on the marine wind page (gale, storm, hurricane force), and later a GFE warning-area step. Nothing changes until Jason agrees.

**Truth:**
- Gale and storm: ASCAT (`rk.truth.ascat_grid`, real 10 m wind, Metop-B/C intercalibrated, +-90 min). ASCAT is the project's referee for how strong; analyses understate peaks.
- Hurricane force: the OPC hurricane-force low archive (`rk.truth.hf_fixes`, jkrek17/hf-low), because ASCAT reads low above ~60 kt. An HF low counts as caught when a warned cell lies within 500 km of its centre (issued HF areas sit a median 30 nm from their own lows; the radius allows for position error at 24-48 h).

**Baseline to beat:** the desk's issued High Seas Forecast warning areas (IEM archive, parsed to grids), plus the live page blend and each model.

**Win means** (Jason's picks): "hit" = detection: at least 80% of verified gale, storm and HF events caught by a warning at that level or higher (card answered 04:24Z), with false alarms and warning area no worse than the desk's on the same hours ("Match the desk", 04:25Z). Read on the held-out weeks.

**Cases:** winter 2025-26 (1 Nov to 31 Mar), 00 and 12 UTC runs, +24 and +48 h (the HSF times), both basins, scored inside the OPC high seas areas (Atlantic 31-67N west of 35W, cut at 75W by the box; Pacific per Jason's parser). Desk issuances 0430 and 1630 UTC match the 00 and 12 UTC valid times. Only hours whose desk text parsed completely (about 2 in 3) are compared. Held-out weeks per `rk.cases.held_out` (2025-W45, W50, 2026-W02, W07, W12). Results by month, since HF lows bunch in Dec-Feb.

**Data:** full members (GEFS 31, ENS 51, AIFS ENS 51) of 10 m speed, three models' 10 m wind and MSLP, 925 mb wind and temperatures, under `extra/warning-experiment/cases` (604 cases, about 3 GB). The store carries only member statistics, so full members live in the extra folder. The analyses were imported into `truth/analysis`. Desk masks are in `extra/warning-experiment/desk`.

**Reused / new:**
- Reused: `rk.truth.ascat` and the store analyses, the HSF parser (`/mnt/project-files/hsf/code`, copied as `hsf_parse_wx.py` with Atlantic fixes), and the live blend recipe.
- Added to `rk/` for the next study: `truth.ascat_grid`, `truth.hf_archive`, `truth.hf_fixes`, `score.warning_events`, `score.warning_points`.
- `build_cases.py` predates `rk.fetch`. It uses the basins study's `bfetch` and is kept as the record of how the cases were built.

**Methods tried, simplest first:**
1. Each model alone, and the strongest of the three, with an offset.
2. The page blend with an offset, and with a lift only where the member chance is high (core lift).
3. Member chance at the cell, and within ~1 deg (neighbourhood), at the level and at lower member thresholds.
4. For HF, member chance of 52-64 kt within ~1-2 deg.

**Known traps:** ASCAT snapping (floor, not rint); condition on the forecast; resample weeks; Pacific ASCAT is thin at 12 UTC; ASCAT reads low at HF; a single-cell ASCAT 48 is noise (events need 2+ cells).

**Out of scope:** seas, freezing spray, text wording (the "High seas text from the grids" thread does that).
