# Research harness: design card

*For Jason's yes before any build. Asked 2026-10-16 11:52Z: "Can any of the work be put into a harness" -> "Go" (11:53Z) to design.*

**What it is:** scheduled jobs that keep the research store filled and keep finished studies scoring themselves as new truth arrives, so a finding becomes a running record and nobody pulls data by hand.

**What would change:** no page or GFE change. New: jobs and a results page. Anything that changes the marine wind page or awips-tools still waits for Jason.

## Three parts

### 1. Daily store fill (new job, in the public data repo)
- After each 00Z and 12Z cycle is complete, store GFS, GEFS, IFS, AIFS, ENS and AIFS ENS for both basins.
  - Steps: +24..+120 (plus the 06/18Z-valid and day 6-7 steps the studies asked for).
  - Format: the same per-cycle zip the kit reads today.
- Truth goes in the same way as release files, one per day:
  - analyses
  - ASCAT, 3 days back (RSS lags ~2 days)
  - buoys and ships, and the issued HSF and NDFD grids
  This takes truth out of the 10 GB shared folder too.
- **Reused:** nwp (the shared downloader), rk.fetch/rk.store/rk.truth, the release layout, and the publish workflow.
- **New:** the job itself, and release-backed truth in rk.truth (the same cache -> release pattern as fields).
- **Catch-up:** every run looks back 14 days and fills any missing cycle or day. GitHub skipped every scheduled job for 7 h on 10-16, so the run never assumes the previous one ran.

### 2. Standing scores (new job, weekly)
Each finished study gets a `preset.py` that re-scores the newest weeks with the method and truth it was judged on, and appends one results table per study. New weeks are out-of-sample by construction, so this tests whether a finding holds.

| Study | What keeps being scored | Truth |
|---|---|---|
| Warning rules | Desk vs ensemble gale/storm rules: catch and area | ASCAT; HF from the hf-low fixes |
| Day 5-7 pressure | Member vote vs GFS/ECMWF/AIFS: low position and depth, day 5-7 | Analyses |
| Chance calibration | Reliability of P34/P48 as the page shows them | ASCAT 75 km box |
| Storm-force truth | ASCAT vs SMAP vs buoys at 48+ kt, as new pairs arrive | Buoys |

Already standing in awips-tools, so reused and not copied:
- Core Lifted storm catch (storm-verify job)
- HSF draft vs issued (page job)
- Page scores (verification job)

### 3. Desk in the nightly loop (awips-tools change: needs Jason's yes)
- Add the desk's NDFD grids as one more method in the verification page scoring. The NDFD reader already exists in nwp.ndfd, and the HSF draft vs issued comparison already runs.
- Desk vs Core Lifted vs models then becomes a standing number on the page instead of a study.

## Schedule and limits
- **Store fill** (two times a day): 10:15 and 22:15 UTC.
  - ENS is complete about 8 h after the cycle, and these times stay clear of the page build windows (08:15-09:15, 20:15-21:15) and the 21:45 scorecard.
  - Cost: ~1.5 GB streamed per cycle, so ~3 GB/day (the audit's 19 GB/day becomes ~22). Kept: ~30-40 MB per cycle, about 25-30 GB a year in releases.
- **Truth fill:** daily at 04:00 UTC.
- **Standing scores:** Mondays 06:00 UTC.
- **Limits:**
  - One heavy ECMWF pull at a time: the jobs use one concurrency group and rk.fetch.wait_for_quiet.
  - Jobs are capped at 6 h; a cycle takes ~5 min.
  - The scheduler can skip runs; the catch-up pass covers that.
- **Cost:** none. Public repo, so Actions minutes are free.

## What stays manual
Choosing what goes on the page, new studies, and judging a drift alert. The weekly job flags it when a study's number moves outside its original confidence interval; a person decides what that means.

## Decisions for Jason
1. **Where the code runs.** The kit (rk/) lives in the private repo, which has 2,000 Actions minutes a month; the jobs need ~1,500-3,000. Options:
   - (a) Make marine-research public. One copy of the code, free minutes. *Recommended.*
   - (b) Keep it private and give the data repo a read token, which Jason creates and adds as a secret.
2. **Results page.** Options:
   - (a) A "Research scores" page on the public site in the globe-kit style, one table and a trend line per study. *Recommended.*
   - (b) Tables only in the data repo.
3. **Desk in the nightly verification (awips-tools change).** Yes / not now. *Recommended: yes.*

## Build order after a yes
1. Truth in releases.
2. Fill job and catch-up.
3. Presets for warning rules and day 5-7 (they have run scripts).
4. Chance calibration and storm-force truth presets.
5. Results page.
6. NDFD on the verification page.

Each step merges on its own and is checked against today's numbers before the next.
