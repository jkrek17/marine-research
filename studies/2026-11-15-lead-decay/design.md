# How Best Wind and the warning lines hold up at 72 and 96 h: design card

*Jason said yes (2026-11-15 19:21Z) to the side-by-side the coordinator offered. Read and score only; nothing on the page changes.*

**Question** (Jason's words): "what about winds at F96 or F72?"

**What would change if the answer is yes:** nothing directly. It tells the desk how far to trust the page grid and lines at day 3-4, and whether the lines should widen (or the grid lift) with lead. Any such change would be its own study.

**Truth:** RSS ASCAT real 10 m wind (`rk.truth.ascat_target`: intercalibrated, rain dropped, passes within 90 min of valid time). How strong and how big, which is what the grid and lines claim. Pacific includes 06/18Z valid times (its main ASCAT passes).

**Baseline:** the same products at 24 h. Beside them: raw GFS, ECMWF, AIFS and the plain blend, so the decay of Best Wind can be read against each model's own.

**Products (as live, winter build):**
- Grid: Best Wind (page grid).
- Lines: gale (strongest model >= 30), storm (Core Lifted >= 39), HF (strongest >= 44 and GEFS 64 kt share >= 1%), inside the OPC High Seas areas.

**Scores, per basin and lead (24, 48, 72, 96; 120 shown for free):**
- Grid at 34/48/64 kt: area / ASCAT area (1.0 = right size), cells caught, equal-area catch (placement with size taken out), storm and HF tile catch (5x5 deg) with false tiles.
- Lines: share of ASCAT gale/storm/HF water inside the line, line area / ASCAT area, events caught, share of the line with nothing nearby.
- How much each drops from 24 h, with a whole-week bootstrap interval.

**Win means:** not a contest. The answer is the decay table. A claim like "storm line still covers X% at 96 h" needs a week-resampled interval beside it.

**Cases:** winter 2025-26 (1 Nov - 31 Mar), both basins, every 00/12Z run; valid 00/12Z (+ Pacific 06/18Z: steps 30/54/78/102). All weeks (nothing is tuned); held-out weeks shown alone as a check.

**Data:** all in the store and truth releases: the most-likely-wind case build (2026-11-07), re-run at these steps. About 10-15 GB from the data releases, no AWS pull, about 1 h.

**Reused / new:** `most-likely-wind/build_cases.py` (Best Wind pieces, ASCAT), `core-lift-bias/lines.py` counts (storm line by lead already exist for the whole winter), `rk.score.warning_events`, the tile counter from strong-core-lift, `rk.compare` week bootstrap. New: a per-case, per-lead score writer for the gale and HF lines and the grid catch (the earlier study pooled leads together).

**Known traps:** one storm counted at several leads is not independent (weeks are the resampling unit); ASCAT reads a few kt low in the strongest cores; Pacific HF has few cases (report counts); equal-area catch and raw area say different things, keep both.

**Out of scope:** desk grids and HSF; this fall's live runs (forecast records keep 14 days; the scatterometer page holds latest/24/48 h only).
