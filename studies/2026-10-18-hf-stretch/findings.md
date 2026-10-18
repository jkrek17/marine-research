# Core stretch near hurricane-force lows: it passes, but what works is a bigger lift, not the depth key

*2026-10-18 · the core-ceiling cases (archive HF and S fixes, every synoptic hour, Nov 2025 - Mar 2026, +24/+48/+72 h) · 303 cases, 487,284 cells within 500 km · truth: ASCAT real 10 m, intercalibrated, rain dropped · pre-set rule: `design.md`*

## The answer
Jason asked whether downscaling could fix the weak core, and whether to apply it by low depth. The stretch maps the blend's core wind (core probability at least 0.35) onto ASCAT's distribution, keyed to the low's pressure drop and lead and capped at 0.8 x the geostrophic wind. It was learned on training weeks and scored once on held-out weeks.

**It passes the pre-set rule.** Scored within about 50 km (5 x 5 cells), on cells ASCAT saw, held-out weeks pooled over leads:

| | Core Lifted | Stretch |
|---|---|---|
| ASCAT 64 kt cells caught | 12% | 48% |
| Its 64 kt cells confirmed by ASCAT 64 kt within ~50 km | 58% | 74% |
| CSI 64 | 0.11 | 0.41 |
| 64 kt area / ASCAT's | 0.06 | 0.52 |
| CSI 48 | 0.758 | 0.779 |

- CSI 64 stretch minus Core Lifted: +0.30 [+0.05, +0.38] (whole weeks resampled). CSI 48: +0.02 [+0.02, +0.03].
- By lead: +0.24 [-0.12, +0.33] at day 1 (crosses zero), +0.41 at day 2, +0.26 at day 3.

**But the depth key adds nothing.** An independent recheck found that a plain constant lift in the core, chosen on the same training weeks (about +13 kt instead of Core Lifted's +5), does as well or better: held-out CSI 64 0.46-0.54. In the range that decides whether a cell reaches 64 kt (blend 50-60 kt), the stretch adds 12-14 kt almost everywhere, so in practice it is a 13 kt lift. The pressure-drop bins and the quantile shape don't help, and the cap barely matters (it binds in 4% of core cells; without it CSI 64 is 0.42).

## What it means
- **The core wind near deep lows is short by about a constant amount, and lifting it by that amount finds most of ASCAT's hurricane force.** That fits the depth study: the low is right, its core is uniformly too weak.
- **So the answer to "based on low depth?" is no, on this evidence.** A single larger lift gated by the core probability is as good, and simpler.
- **It is not ready for a page.** Every case here is a low the desk already called hurricane force or storm. The real use would fire on every core on the map, and this sample can't say how often it would paint false hurricane force around lows that never got there (only 3 held-out and 41 training storm-force cases). On training weeks the stretch showed 64 kt in 14 of 103 HF cases where ASCAT's core stayed under 64 kt.

## How solid
- **The held-out evidence is small.** 69 cases, 5 weeks, 13 storms, but only 519 distinct ASCAT 64 kt cell-times (each cell counts once per lead, 1,557 in all) from 7 storms. 63% come from one storm in one week (2025-W50).
- Leaving out each week, the gain is +0.20 to +0.34. Weighting each storm equally it is about +0.17; 5 of 8 storms improve, 2 are unchanged and 1 is slightly worse.
- Of the stretch's held-out 64 kt cells that ASCAT saw, 42% have ASCAT 64 kt in the same cell, 25% are 56-64 kt and 17% are below 48 kt. The 74% leans on the 50 km window.
- ASCAT is unsettled above 56 kt, so the target itself may run high.
- An independent recheck reproduced every number and the mapping tables exactly.

## Next
Before any page, the lift (a plain core lift of about 13 kt is the simpler candidate) needs a false-alarm test on every core with an ASCAT pass, not just the archive's lows. That uses the same store winter and no new pulls.

## Files
`cells.py` (cell table to `RK_CACHE/extra/hf-stretch/cells.parquet`, `cases.csv`), `fit.py` (tables and tune scores; `--final` once), `tables.csv`, `tune_results.md`, `final_results.md`, `final_results.json`, `design.md`.
